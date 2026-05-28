from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.orders.models import Order, OrderActivity
from apps.orders.tasks import send_order_status_update_email

@receiver(post_save, sender=Order)
def order_status_change_handler(sender, instance, created, **kwargs):
    """Handle order status changes"""
    if not created:
        # Check if status changed
        if instance.pk:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.order_status != instance.order_status:
                # Send status update email
                send_order_status_update_email.delay(
                    instance.id,
                    old_instance.order_status,
                    instance.order_status
                )
                
                # Log status change if not already logged
                OrderActivity.objects.create(
                    order=instance,
                    activity_type=OrderActivity.ActivityType.STATUS_CHANGED,
                    description=f"Order status changed from {old_instance.order_status} to {instance.order_status}",
                    old_status=old_instance.order_status,
                    new_status=instance.order_status
                )
