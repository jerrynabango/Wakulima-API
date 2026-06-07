import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.choices import (
    NotificationCategory,
    NotificationPriority,
    NotificationType,
)
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product

from .tasks import (
    send_low_stock_alert,
    send_order_confirmation_notification,
    send_payment_received_notification,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Order)
def order_created_handler(sender, instance, created, **kwargs):
    """Send notification when order is created"""
    if created:
        logger.info(f"Order created signal received for order {instance.id}")

        # Create in-app notification via signal (as backup)
        Notification.objects.get_or_create(
            user=instance.user,
            reference_id=str(instance.id),
            defaults={
                "notification_type": NotificationType.IN_APP,
                "category": NotificationCategory.ORDER,
                "priority": NotificationPriority.HIGH,
                "title": f"Order Confirmed - #{
                    instance.order_number}",
                "message": f"Your order #{
                    instance.order_number} has been confirmed. Total: KES {
                    instance.total}",
                "metadata": {
                    "order_id": str(instance.id),
                    "order_number": instance.order_number,
                    "total": str(instance.total),
                },
            },
        )

        # Send email notification (async)
        send_order_confirmation_notification.delay(instance.id)


@receiver(post_save, sender=Payment)
def payment_success_handler(sender, instance, created, **kwargs):
    """Send notification when payment is successful"""
    if instance.status == Payment.PaymentStatus.SUCCESS:
        logger.info(f"Payment success signal received for payment {
                instance.id}")

        # Create in-app notification
        Notification.objects.create(
            user=instance.user,
            notification_type=NotificationType.IN_APP,
            category=NotificationCategory.PAYMENT,
            priority=NotificationPriority.HIGH,
            title=f"Payment Received - Order #{
                instance.order.order_number}",
            message=f"We've received your payment of KES {
                instance.amount} for order #{
                instance.order.order_number}",
            reference_id=str(instance.id),
            metadata={
                "payment_id": str(instance.id),
                "order_id": str(instance.order.id),
                "amount": str(instance.amount),
            },
        )

        # Send email notification (async)
        send_payment_received_notification.delay(instance.id)


@receiver(post_save, sender=Product)
def product_low_stock_handler(sender, instance, **kwargs):
    """Send alert when product stock is low"""
    if instance.quantity <= instance.minimum_stock and instance.quantity > 0:
        logger.info(f"Low stock signal received for product {instance.id}")

        # Create in-app notification for farmer
        Notification.objects.create(
            user=instance.farmer,
            notification_type=NotificationType.IN_APP,
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.URGENT,
            title=f"Low Stock Alert: {
                instance.name}",
            message=f"Your product {
                instance.name} is running low! Current stock: {
                instance.quantity} {
                    instance.unit_type}",
            reference_id=str(instance.id),
            metadata={
                "product_id": str(instance.id),
                "product_name": instance.name,
                "quantity": str(instance.quantity),
            },
        )

        # Send email notification (async)
        send_low_stock_alert.delay(instance.id, instance.farmer.id)
