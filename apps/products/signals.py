import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.notifications.services import NotificationService
from apps.products.models import InventoryHistory, Product

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Product)
def check_low_stock(sender, instance, **kwargs):
    """
    Check if product is low on stock and trigger alert
    Runs BEFORE product is saved to compare old vs new stock
    """
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)

            # Check if stock just fell below minimum stock
            if (
                old_instance.quantity > instance.minimum_stock
                and instance.quantity <= instance.minimum_stock
            ):
                logger.warning(f"Low stock alert triggered for product: {
                        instance.name} (Stock: {
                        instance.quantity})")

                # Create low stock alert via notification service
                notification_service = NotificationService()
                notification_service.send_low_stock_alert(
                    instance, instance.farmer
                )

        except sender.DoesNotExist:
            # Product is new, no old instance to compare
            pass


@receiver(post_save, sender=InventoryHistory)
def log_inventory_change(sender, instance, created, **kwargs):
    """
    Log inventory changes for audit and real-time notifications
    Runs AFTER inventory history is created
    """
    if created:
        logger.info(f"Inventory change recorded: {
                instance.change_type} - {
                instance.quantity_change} units for {
                instance.product.name}")

        # For order-related inventory changes, trigger notifications
        if instance.change_type in [
            InventoryHistory.ChangeType.ORDER,
            InventoryHistory.ChangeType.RETURN,
        ]:
            # Could send real-time WebSocket notifications here
            pass


@receiver(post_save, sender=Product)
def create_inventory_for_new_product(sender, instance, created, **kwargs):
    """
    Automatically create inventory record when a new product is created
    (This works with the Inventory app)
    """
    if created:
        try:
            from apps.inventory.models import Inventory

            inventory, created = Inventory.objects.get_or_create(
                product=instance,
                defaults={
                    "quantity": instance.quantity,
                    "minimum_stock": 5,
                    "reorder_point": 10,
                    "reorder_quantity": 20,
                    "status": (
                        Inventory.StockStatus.IN_STOCK
                        if instance.quantity > 0
                        else Inventory.StockStatus.OUT_OF_STOCK
                    ),
                },
            )
            logger.info(f"Inventory record created for new product: {
                    instance.name}")
        except ImportError:
            # Inventory app not installed yet
            logger.info(
                f"Inventory app not available - skipping inventory creation for {instance.name}"
            )
        except Exception as e:
            logger.error(f"Failed to create inventory for {
                    instance.name}: {
                    str(e)}")


@receiver(post_save, sender=Product)
def update_inventory_on_product_save(sender, instance, **kwargs):
    """
    Update inventory when product stock changes via product update
    (Works with Inventory app)
    """
    if not kwargs.get("created", False):  # Only for updates, not new products
        try:
            from apps.inventory.models import Inventory

            inventory = Inventory.objects.get(product=instance)

            # Update inventory quantity if changed
            if inventory.quantity != instance.quantity:
                inventory.quantity = instance.quantity
                inventory.save(update_fields=["quantity"])
                inventory.update_status()
                logger.info(f"Inventory updated for product {
                        instance.name}: new quantity {
                        instance.quantity}")

        except ImportError:
            pass  # Inventory app not installed
        except Inventory.DoesNotExist:
            # Create inventory if it doesn't exist
            try:
                from apps.inventory.models import Inventory

                Inventory.objects.create(
                    product=instance,
                    quantity=instance.quantity,
                    minimum_stock=5,
                    reorder_point=10,
                    reorder_quantity=20,
                )
                logger.info(f"Inventory created for existing product: {
                        instance.name}")
            except ImportError:
                pass
        except Exception as e:
            logger.error(f"Failed to update inventory for {
                    instance.name}: {
                    str(e)}")
