from celery import shared_task
from django.utils import timezone
from apps.inventory.models import Inventory, StockAlert, InventoryReservation
import logging

logger = logging.getLogger(__name__)


@shared_task
def check_all_low_stock():
    """Check all inventory for low stock and create alerts"""
    low_stock_inventory = Inventory.objects.filter(quantity__lte=models.F('minimum_stock'))
    
    alerts_created = 0
    for inventory in low_stock_inventory:
        alert, created = StockAlert.objects.get_or_create(
            inventory=inventory,
            alert_type=StockAlert.AlertType.LOW_STOCK,
            defaults={
                'message': f"Low stock alert: {inventory.product.name} has {inventory.quantity} {inventory.product.unit_type} remaining",
                'status': StockAlert.AlertStatus.PENDING
            }
        )
        if created:
            alerts_created += 1
            # Send notification
            from apps.notifications.tasks import send_low_stock_alert
            send_low_stock_alert.delay(inventory.product.id, inventory.product.farmer.id)
    
    return {'alerts_created': alerts_created, 'low_stock_count': low_stock_inventory.count()}


@shared_task
def expire_old_reservations():
    """Expire inventory reservations that are older than 30 minutes"""
    expired = InventoryReservation.objects.filter(
        status=InventoryReservation.ReservationStatus.ACTIVE,
        expires_at__lt=timezone.now()
    )
    
    expired_count = 0
    for reservation in expired:
        reservation.status = InventoryReservation.ReservationStatus.EXPIRED
        reservation.save()
        
        # Release reserved stock
        inventory = reservation.inventory
        inventory.release_reserved_stock(reservation.quantity)
        expired_count += 1
    
    logger.info(f"Expired {expired_count} inventory reservations")
    return {'expired_count': expired_count}


@shared_task
def generate_inventory_report(farmer_id):
    """Generate inventory report for a farmer"""
    from apps.accounts.models import User
    
    try:
        farmer = User.objects.get(id=farmer_id, role=User.Role.FARMER)
        inventory = Inventory.objects.filter(product__farmer=farmer)
        
        total_products = inventory.count()
        total_value = sum(float(i.quantity) * float(i.product.price) for i in inventory)
        low_stock = inventory.filter(quantity__lte=models.F('minimum_stock')).count()
        out_of_stock = inventory.filter(quantity=0).count()
        
        report = {
            'farmer_email': farmer.email,
            'generated_at': timezone.now().isoformat(),
            'summary': {
                'total_products': total_products,
                'total_inventory_value': round(total_value, 2),
                'low_stock_count': low_stock,
                'out_of_stock_count': out_of_stock,
                'healthy_stock_count': total_products - low_stock - out_of_stock
            },
            'products': [
                {
                    'name': inv.product.name,
                    'quantity': float(inv.quantity),
                    'unit': inv.product.unit_type,
                    'price': float(inv.product.price),
                    'value': round(float(inv.quantity) * float(inv.product.price), 2),
                    'status': inv.status
                }
                for inv in inventory
            ]
        }
        
        logger.info(f"Inventory report generated for farmer {farmer.email}")
        return report
        
    except User.DoesNotExist:
        logger.error(f"Farmer {farmer_id} not found")
        return None
