import logging

from django.core.cache import cache
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.orders.models import OrderActivity
from apps.payments.models import Payment, PaymentWebhook

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Payment)
def payment_status_change_handler(sender, instance, created, **kwargs):
    """Handle payment status changes"""
    if not created:
        if instance.pk:
            try:
                old_instance = sender.objects.get(pk=instance.pk)
                if old_instance.status != instance.status:
                    # Clear cache for this payment
                    cache_key = f"payment_{instance.id}_status"
                    cache.delete(cache_key)

                    # Determine activity type
                    if instance.status == Payment.PaymentStatus.SUCCESS:
                        activity_type = (
                            OrderActivity.ActivityType.PAYMENT_CONFIRMED
                        )
                        description = f"Payment successful - Amount: {
                            instance.amount} {
                            instance.currency}"
                    elif instance.status == Payment.PaymentStatus.FAILED:
                        activity_type = "payment_failed"
                        description = f"Payment failed - Gateway: {
                            instance.gateway}"
                    elif instance.status == Payment.PaymentStatus.REFUNDED:
                        activity_type = (
                            OrderActivity.ActivityType.REFUND_COMPLETED
                        )
                        description = f"Payment refunded - Amount: {
                            instance.amount} {
                            instance.currency}"
                    elif instance.status == Payment.PaymentStatus.CANCELLED:
                        activity_type = "payment_cancelled"
                        description = "Payment was cancelled"
                    else:
                        activity_type = "payment_updated"
                        description = f"Payment status changed from {
                            old_instance.status} to {
                            instance.status}"

                    # Log activity
                    OrderActivity.objects.create(
                        order=instance.order,
                        activity_type=activity_type,
                        description=description,
                        performed_by=instance.user,
                        ip_address="system",
                        old_status=old_instance.status,
                        new_status=instance.status,
                    )

                    logger.info(f"Payment {
                            instance.id} status changed: {
                            old_instance.status} -> {
                            instance.status}")

            except sender.DoesNotExist:
                pass
    else:
        # New payment created
        OrderActivity.objects.create(
            order=instance.order,
            activity_type="payment_initiated",
            description=f"Payment initiated - Amount: {
                instance.amount} {
                instance.currency} via {
                instance.gateway}",
            performed_by=instance.user,
            ip_address="system",
            new_status=instance.status,
        )


@receiver(pre_save, sender=Payment)
def payment_pre_save_handler(sender, instance, **kwargs):
    """Handle payment before save - check for duplicate transactions"""
    if instance.transaction_id and instance.pk:
        # Check if this transaction_id is already used
        existing = (
            Payment.objects.filter(transaction_id=instance.transaction_id)
            .exclude(pk=instance.pk)
            .exists()
        )

        if existing:
            logger.warning(
                f"Duplicate transaction_id detected: {instance.transaction_id}"
            )
            # Don't raise error, just log - let the caller handle it


@receiver(post_save, sender=PaymentWebhook)
def webhook_saved_handler(sender, instance, created, **kwargs):
    """Handle new webhook saved"""
    if created:
        logger.info(
            f"New webhook received: {instance.gateway} - {instance.event_type}"
        )

        # For critical webhooks, process immediately if not already processed
        critical_events = ["stk_callback_0", "PAYMENT.CAPTURE.COMPLETED"]
        if instance.event_type in critical_events and not instance.processed:
            # Trigger async processing
            from apps.payments.tasks import process_unprocessed_webhooks

            process_unprocessed_webhooks.delay()
