import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import F, Sum
from apps.inventory.models import Inventory, StockMovement, StockAlert, InventoryReservation
from apps.products.models import Product
from apps.accounts.models import User

logger = logging.getLogger(__name__)


class InventoryService:
    """Core inventory business logic"""
    
    @staticmethod
    def get_inventory_for_user(user, filters=None):
        """
        Get inventory based on user role and filters
        Returns queryset
        """
        if user.is_admin_user:
            queryset = Inventory.objects.all()
        else:
            queryset = Inventory.objects.filter(product__farmer=user)
        
        if filters:
            status_filter = filters.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            
            low_stock = filters.get('low_stock')
            if low_stock == 'true':
                queryset = queryset.filter(quantity__lte=F('minimum_stock'))
        
        return queryset.select_related('product', 'product__farmer')
    
    @staticmethod
    def get_or_create_inventory(product):
        """Get or create inventory for a product"""
        inventory, created = Inventory.objects.get_or_create(product=product)
        return inventory
    
    @staticmethod
    @transaction.atomic
    def update_stock(product, user, new_quantity, reason="Manual stock update"):
        """
        Update product stock to a specific quantity
        Returns: {'success': bool, 'inventory': Inventory, 'message': str}
        """
        # Check permission
        if not user.is_admin_user and product.farmer != user:
            return {
                'success': False,
                'message': 'You do not have permission to update this product'
            }
        
        # Get or create inventory
        inventory = InventoryService.get_or_create_inventory(product)
        old_quantity = inventory.quantity
        
        # Update stock
        inventory.quantity = new_quantity
        if new_quantity > old_quantity:
            inventory.last_restocked = timezone.now()
        inventory.save()
        inventory.update_status()
        
        # Create stock movement record
        StockMovement.objects.create(
            inventory=inventory,
            user=user,
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            quantity=new_quantity - old_quantity,
            previous_quantity=old_quantity,
            new_quantity=new_quantity,
            reason=reason
        )
        
        # Check and create alert if low stock
        if inventory.is_low_stock:
            InventoryService.create_low_stock_alert(inventory, product)
        
        logger.info(f"Stock updated for {product.name} by {user.email}: {old_quantity} -> {new_quantity}")
        
        return {
            'success': True,
            'inventory': inventory,
            'message': f'Stock updated from {old_quantity} to {new_quantity}'
        }
    
    @staticmethod
    @transaction.atomic
    def adjust_stock(product, user, quantity, adjustment_type, reason):
        """
        Add or subtract stock from inventory
        Returns: {'success': bool, 'inventory': Inventory, 'message': str}
        """
        # Check permission
        if not user.is_admin_user and product.farmer != user:
            return {
                'success': False,
                'message': 'You do not have permission to update this product'
            }
        
        inventory = InventoryService.get_or_create_inventory(product)
        old_quantity = inventory.quantity
        
        if adjustment_type == 'add':
            inventory.quantity += quantity
            movement_quantity = quantity
            movement_type = StockMovement.MovementType.RESTOCK
            message = f"Added {quantity} units"
        else:
            if quantity > inventory.quantity:
                return {
                    'success': False,
                    'message': f'Cannot subtract {quantity}. Only {inventory.quantity} available'
                }
            inventory.quantity -= quantity
            movement_quantity = -quantity
            movement_type = StockMovement.MovementType.ADJUSTMENT
            message = f"Subtracted {quantity} units"
        
        if adjustment_type == 'add':
            inventory.last_restocked = timezone.now()
        
        inventory.save()
        inventory.update_status()
        
        StockMovement.objects.create(
            inventory=inventory,
            user=user,
            movement_type=movement_type,
            quantity=movement_quantity,
            previous_quantity=old_quantity,
            new_quantity=inventory.quantity,
            reason=reason
        )
        
        # Check and create alert if low stock
        if inventory.is_low_stock:
            InventoryService.create_low_stock_alert(inventory, product)
        
        logger.info(f"Stock adjusted for {product.name} by {user.email}: {old_quantity} -> {inventory.quantity}")
        
        return {
            'success': True,
            'inventory': inventory,
            'message': message
        }
    
    @staticmethod
    @transaction.atomic
    def bulk_update_stock(user, updates):
        """
        Bulk update stock for multiple products
        Returns: {'success': bool, 'results': list, 'summary': dict}
        """
        results = []
        successful = 0
        failed = 0
        
        for update in updates:
            product_id = update.get('product_id')
            quantity = update.get('quantity')
            reason = update.get('reason', 'Bulk stock update')
            
            try:
                product = Product.objects.get(id=product_id)
                result = InventoryService.update_stock(product, user, quantity, reason)
                
                if result['success']:
                    successful += 1
                    results.append({
                        'product_id': str(product_id),
                        'success': True,
                        'old_quantity': float(result['inventory'].quantity - (quantity - result['inventory'].quantity)),
                        'new_quantity': float(quantity)
                    })
                else:
                    failed += 1
                    results.append({
                        'product_id': str(product_id),
                        'success': False,
                        'error': result['message']
                    })
                    
            except Product.DoesNotExist:
                failed += 1
                results.append({
                    'product_id': str(product_id),
                    'success': False,
                    'error': 'Product not found'
                })
        
        return {
            'success': True,
            'results': results,
            'summary': {
                'total': len(updates),
                'successful': successful,
                'failed': failed
            }
        }
    
    @staticmethod
    def create_low_stock_alert(inventory, product):
        """Create low stock alert if not exists"""
        alert, created = StockAlert.objects.get_or_create(
            inventory=inventory,
            alert_type=StockAlert.AlertType.LOW_STOCK,
            defaults={
                'message': f"Low stock alert: {product.name} has {inventory.quantity} {product.unit_type} remaining",
                'status': StockAlert.AlertStatus.PENDING
            }
        )
        
        if created:
            logger.info(f"Low stock alert created for product: {product.name}")
            # Trigger async notification
            from apps.notifications.tasks import send_low_stock_alert
            send_low_stock_alert.delay(product.id, product.farmer.id)
        
        return alert
    
    @staticmethod
    def resolve_stock_alert(alert, user):
        """Resolve a stock alert"""
        if not user.is_admin_user and alert.inventory.product.farmer != user:
            return {
                'success': False,
                'message': 'You do not have permission to resolve this alert'
            }
        
        alert.status = StockAlert.AlertStatus.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save()
        
        logger.info(f"Stock alert resolved for {alert.inventory.product.name} by {user.email}")
        
        return {
            'success': True,
            'message': 'Alert resolved successfully'
        }
    
    @staticmethod
    def get_low_stock_report(user):
        """Get low stock report for user"""
        if user.is_admin_user:
            return Inventory.objects.filter(quantity__lte=F('minimum_stock'))
        return Inventory.objects.filter(
            product__farmer=user,
            quantity__lte=F('minimum_stock')
        )
    
    @staticmethod
    def get_stock_summary(user):
        """Get stock summary statistics"""
        if user.is_admin_user:
            inventory = Inventory.objects.all()
        else:
            inventory = Inventory.objects.filter(product__farmer=user)
        
        total_products = inventory.count()
        total_quantity = inventory.aggregate(total=Sum('quantity'))['total'] or 0
        low_stock_count = inventory.filter(quantity__lte=F('minimum_stock')).count()
        out_of_stock_count = inventory.filter(quantity=0).count()
        
        # Stock value calculation
        stock_value = 0
        for inv in inventory.select_related('product'):
            stock_value += float(inv.quantity) * float(inv.product.price)
        
        return {
            'total_products': total_products,
            'total_quantity': float(total_quantity),
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'stock_value': round(stock_value, 2),
            'healthy_stock_count': total_products - low_stock_count - out_of_stock_count
        }


class StockMovementService:
    """Service for stock movement tracking"""
    
    @staticmethod
    def get_movement_history(user, movement_type=None, limit=200):
        """Get stock movement history for user"""
        if user.is_admin_user:
            queryset = StockMovement.objects.all()
        else:
            queryset = StockMovement.objects.filter(inventory__product__farmer=user)
        
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        
        return queryset.select_related('inventory__product', 'user')[:limit]
    
    @staticmethod
    def create_movement(inventory, user, movement_type, quantity, previous_quantity, new_quantity, reason=None, reference_id=None):
        """Create a stock movement record"""
        return StockMovement.objects.create(
            inventory=inventory,
            user=user,
            movement_type=movement_type,
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reason=reason or '',
            reference_id=reference_id or ''
        )


class StockAlertService:
    """Service for stock alert management"""
    
    @staticmethod
    def get_alerts(user, status_filter=None):
        """Get stock alerts for user"""
        if user.is_admin_user:
            queryset = StockAlert.objects.all()
        else:
            queryset = StockAlert.objects.filter(inventory__product__farmer=user)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related('inventory__product')
    
    @staticmethod
    def create_alert(inventory, alert_type, message):
        """Create a new stock alert"""
        return StockAlert.objects.create(
            inventory=inventory,
            alert_type=alert_type,
            message=message,
            status=StockAlert.AlertStatus.PENDING
        )
    
    @staticmethod
    def get_pending_alerts(user):
        """Get pending alerts for user"""
        if user.is_admin_user:
            return StockAlert.objects.filter(status=StockAlert.AlertStatus.PENDING)
        return StockAlert.objects.filter(
            inventory__product__farmer=user,
            status=StockAlert.AlertStatus.PENDING
        )


class InventoryReservationService:
    """Service for inventory reservations (for orders)"""
    
    @staticmethod
    def create_reservation(inventory, order_id, quantity, expires_minutes=30):
        """
        Create a temporary inventory reservation for an order
        Returns: {'success': bool, 'reservation': InventoryReservation, 'message': str}
        """
        if quantity > inventory.available_quantity:
            return {
                'success': False,
                'message': f'Insufficient stock. Available: {inventory.available_quantity}'
            }
        
        expires_at = timezone.now() + timezone.timedelta(minutes=expires_minutes)
        
        reservation = InventoryReservation.objects.create(
            inventory=inventory,
            order_id=order_id,
            quantity=quantity,
            expires_at=expires_at,
            status=InventoryReservation.ReservationStatus.ACTIVE
        )
        
        # Reserve the stock
        inventory.reserve_stock(quantity)
        
        logger.info(f"Reservation created for order {order_id}: {quantity} units")
        
        return {
            'success': True,
            'reservation': reservation,
            'message': f'Reservation created. Expires at {expires_at}'
        }
    
    @staticmethod
    def confirm_reservation(order_id):
        """
        Confirm a reservation (convert to actual sale)
        Returns: {'success': bool, 'message': str}
        """
        reservations = InventoryReservation.objects.filter(
            order_id=order_id,
            status=InventoryReservation.ReservationStatus.ACTIVE
        )
        
        confirmed_count = 0
        for reservation in reservations:
            reservation.status = InventoryReservation.ReservationStatus.CONFIRMED
            reservation.save()
            
            # Deduct stock permanently
            inventory = reservation.inventory
            inventory.deduct_stock(reservation.quantity)
            confirmed_count += 1
        
        logger.info(f"Confirmed {confirmed_count} reservations for order {order_id}")
        
        return {
            'success': True,
            'confirmed_count': confirmed_count,
            'message': f'Confirmed {confirmed_count} reservations'
        }
    
    @staticmethod
    def cancel_reservation(order_id):
        """
        Cancel a reservation (release reserved stock)
        Returns: {'success': bool, 'message': str}
        """
        reservations = InventoryReservation.objects.filter(
            order_id=order_id,
            status=InventoryReservation.ReservationStatus.ACTIVE
        )
        
        cancelled_count = 0
        for reservation in reservations:
            reservation.status = InventoryReservation.ReservationStatus.CANCELLED
            reservation.save()
            
            # Release reserved stock
            inventory = reservation.inventory
            inventory.release_reserved_stock(reservation.quantity)
            cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} reservations for order {order_id}")
        
        return {
            'success': True,
            'cancelled_count': cancelled_count,
            'message': f'Cancelled {cancelled_count} reservations'
        }
    
    @staticmethod
    def expire_old_reservations():
        """Expire reservations older than expiry time"""
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
        
        return {
            'success': True,
            'expired_count': expired_count
        }
    
    @staticmethod
    def get_active_reservations_for_order(order_id):
        """Get active reservations for a specific order"""
        return InventoryReservation.objects.filter(
            order_id=order_id,
            status=InventoryReservation.ReservationStatus.ACTIVE
        )
