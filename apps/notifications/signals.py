from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product
from .tasks import send_order_confirmation_notification, send_payment_received_notification, send_low_stock_alert
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Order)
def order_created_handler(sender, instance, created, **kwargs):
    """Send notification when order is created"""
    if created:
        send_order_confirmation_notification.delay(instance.id)


@receiver(post_save, sender=Payment)
def payment_success_handler(sender, instance, created, **kwargs):
    """Send notification when payment is successful"""
    if instance.status == Payment.PaymentStatus.SUCCESS:
        send_payment_received_notification.delay(instance.id)


@receiver(post_save, sender=Product)
def product_low_stock_handler(sender, instance, **kwargs):
    """Send alert when product stock is low"""
    if instance.quantity <= instance.minimum_stock and instance.quantity > 0:
        send_low_stock_alert.delay(instance.id, instance.farmer.id)
