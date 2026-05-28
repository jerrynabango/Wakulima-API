from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from apps.products.models import Product
from apps.inventory.models import Inventory, StockAlert
from apps.notifications.tasks import send_low_stock_alert
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def create_inventory_for_product(sender, instance, created, **kwargs):
    """Create inventory record when a new product is created"""
    if created:
        Inventory.objects.get_or_create(
            product=instance,
            defaults={
                'quantity': instance.quantity,
                'minimum_stock': 5,
                'reorder_point': 10,
                'reorder_quantity': 20
            }
        )
        logger.info(f"Inventory created for new product: {instance.name}")


@receiver(post_save, sender=Inventory)
def check_low_stock_alert(sender, instance, created, **kwargs):
    """Create alert when stock is low"""
    if not created and instance.is_low_stock:
        alert, created = StockAlert.objects.get_or_create(
            inventory=instance,
            alert_type=StockAlert.AlertType.LOW_STOCK,
            defaults={
                'message': f"Low stock alert: {instance.product.name} has {instance.quantity} {instance.product.unit_type} remaining",
                'status': StockAlert.AlertStatus.PENDING
            }
        )
        
        if created:
            # Send notification to farmer
            send_low_stock_alert.delay(instance.product.id, instance.product.farmer.id)
            logger.info(f"Low stock alert created for product: {instance.product.name}")
