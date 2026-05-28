from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from apps.orders.models import Order, OrderItem, OrderActivity
from apps.cart.models import Cart
from apps.products.models import InventoryHistory
from apps.orders.tasks import send_order_confirmation_email
import logging

logger = logging.getLogger(__name__)

class OrderService:
    """Business logic for order operations"""
    
    @staticmethod
    @transaction.atomic
    def create_order_from_cart(user, order_data, request_ip=None):
        """
        Create order from user's cart
        Returns: {'success': bool, 'order': Order, 'message': str, 'errors': dict}
        """
        try:
            # Get user's cart
            cart = get_object_or_404(Cart, user=user)
            
            if cart.total_items == 0:
                return {
                    'success': False,
                    'message': 'Cart is empty',
                    'errors': {'cart': 'No items to checkout'}
                }
            
            # Validate cart items stock
            for item in cart.items.all():
                if item.quantity > item.product.quantity:
                    return {
                        'success': False,
                        'message': f'{item.product.name} only has {item.product.quantity} {item.product.unit_type} in stock',
                        'errors': {'stock': item.product.name}
                    }
            
            # Create order
            order = Order.objects.create(
                user=user,
                subtotal=cart.subtotal,
                delivery_fee=cart.delivery_fee,
                tax=cart.tax,
                total=cart.total,
                payment_method=order_data['payment_method'],
                shipping_address=order_data['shipping_address'],
                shipping_city=order_data['shipping_city'],
                shipping_zip_code=order_data['shipping_zip_code'],
                shipping_phone=order_data['shipping_phone'],
                customer_note=order_data.get('customer_note', '')
            )
            
            # Create order items and update inventory
            for cart_item in cart.items.all():
                # Create order item
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    product_name=cart_item.product.name,
                    product_price=cart_item.product.price,
                    quantity=cart_item.quantity,
                    unit_price=cart_item.unit_price,
                    total_price=cart_item.total_price
                )
                
                # Update product inventory
                cart_item.product.quantity -= cart_item.quantity
                cart_item.product.save()
                
                # Create inventory history
                InventoryHistory.objects.create(
                    product=cart_item.product,
                    user=user,
                    change_type=InventoryHistory.ChangeType.ORDER,
                    quantity_change=-cart_item.quantity,
                    previous_quantity=cart_item.product.quantity + cart_item.quantity,
                    new_quantity=cart_item.product.quantity,
                    reason=f"Order #{order.order_number}",
                    reference_id=str(order.id)
                )
            
            # Log order activity
            OrderActivity.objects.create(
                order=order,
                activity_type=OrderActivity.ActivityType.CREATED,
                description="Order created via cart checkout",
                performed_by=user,
                ip_address=request_ip or 'system'
            )
            
            # Clear cart
            cart.clear()
            
            # Send confirmation email (async)
            send_order_confirmation_email.delay(order.id)
            
            logger.info(f"Order {order.order_number} created for user {user.email}")
            
            return {
                'success': True,
                'order': order,
                'message': f'Order {order.order_number} created successfully'
            }
            
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return {
                'success': False,
                'message': 'Failed to create order',
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    @transaction.atomic
    def cancel_order(order, user, request_ip=None):
        """
        Cancel order and restore inventory
        Returns: {'success': bool, 'message': str}
        """
        if not order.can_cancel:
            return {
                'success': False,
                'message': f'Order cannot be cancelled in {order.order_status} status'
            }
        
        # Restore inventory for each item
        for item in order.items.all():
            if item.product:
                item.product.quantity += item.quantity
                item.product.save()
                
                # Create inventory history
                InventoryHistory.objects.create(
                    product=item.product,
                    user=user,
                    change_type=InventoryHistory.ChangeType.RETURN,
                    quantity_change=item.quantity,
                    previous_quantity=item.product.quantity - item.quantity,
                    new_quantity=item.product.quantity,
                    reason=f"Order cancelled - {order.order_number}",
                    reference_id=str(order.id)
                )
        
        # Update order status
        order.order_status = Order.OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        order.save()
        
        # Log activity
        OrderActivity.objects.create(
            order=order,
            activity_type=OrderActivity.ActivityType.CANCELLED,
            description=f"Order cancelled by {user.email}",
            performed_by=user,
            ip_address=request_ip or 'system'
        )
        
        logger.info(f"Order {order.order_number} cancelled by {user.email}")
        
        return {
            'success': True,
            'message': 'Order cancelled successfully'
        }
    
    @staticmethod
    def get_user_orders(user, filters=None):
        """Get orders for a user with optional filters"""
        queryset = Order.objects.filter(user=user)
        
        if filters:
            if filters.get('status'):
                queryset = queryset.filter(order_status=filters['status'])
            if filters.get('from_date'):
                queryset = queryset.filter(created_at__date__gte=filters['from_date'])
            if filters.get('to_date'):
                queryset = queryset.filter(created_at__date__lte=filters['to_date'])
        
        return queryset.select_related('user').order_by('-created_at')
    
    @staticmethod
    def get_farmer_orders(farmer):
        """Get orders containing farmer's products"""
        if not farmer.is_farmer:
            return Order.objects.none()
        
        return Order.objects.filter(
            items__product__farmer=farmer
        ).distinct().select_related('user')
