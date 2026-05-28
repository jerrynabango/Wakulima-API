from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from apps.cart.models import Cart, CartItem
from apps.products.models import Product
import logging

logger = logging.getLogger(__name__)

class CartService:
    """Business logic for shopping cart operations"""
    
    @staticmethod
    def get_or_create_cart(user):
        """Get or create cart for user"""
        cart, created = Cart.objects.get_or_create(user=user)
        return cart
    
    @staticmethod
    def add_to_cart(user, product_id, quantity):
        """
        Add product to cart with validation
        Returns: {'success': bool, 'message': str, 'cart': Cart, 'errors': dict}
        """
        try:
            # Get product with validation
            product = get_object_or_404(Product, id=product_id)
            
            # Validate product availability
            if not product.is_available or product.status != 'active':
                return {
                    'success': False,
                    'message': 'Product is not available for purchase',
                    'errors': {'product': 'Not available'}
                }
            
            # Validate stock
            if quantity > product.quantity:
                return {
                    'success': False,
                    'message': f'Only {product.quantity} {product.unit_type} available',
                    'errors': {'quantity': f'Max {product.quantity} {product.unit_type}'}
                }
            
            # Get or create cart
            cart, _ = Cart.objects.get_or_create(user=user)
            
            # Add or update cart item
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity, 'unit_price': product.price}
            )
            
            if not created:
                new_quantity = cart_item.quantity + quantity
                if new_quantity > product.quantity:
                    return {
                        'success': False,
                        'message': f'Cannot add {quantity}. Only {product.quantity - cart_item.quantity} more available',
                        'errors': {'quantity': 'Exceeds available stock'}
                    }
                cart_item.quantity = new_quantity
                cart_item.save()
            
            logger.info(f"Added {quantity} of {product.name} to cart {cart.id}")
            
            return {
                'success': True,
                'message': f'Added {quantity} {product.unit_type} of {product.name} to cart',
                'cart': cart,
                'cart_item': cart_item
            }
            
        except Product.DoesNotExist:
            return {
                'success': False,
                'message': 'Product not found',
                'errors': {'product': 'Does not exist'}
            }
        except Exception as e:
            logger.error(f"Error adding to cart: {str(e)}")
            return {
                'success': False,
                'message': 'Failed to add item to cart',
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    def update_cart_item(user, item_id, quantity):
        """
        Update cart item quantity
        Returns: {'success': bool, 'message': str, 'cart': Cart}
        """
        try:
            cart_item = get_object_or_404(CartItem, id=item_id, cart__user=user)
            
            if quantity <= 0:
                cart_item.delete()
                message = "Item removed from cart"
            else:
                # Validate stock
                if quantity > cart_item.product.quantity:
                    return {
                        'success': False,
                        'message': f'Only {cart_item.product.quantity} {cart_item.product.unit_type} available',
                        'errors': {'quantity': 'Insufficient stock'}
                    }
                
                cart_item.quantity = quantity
                cart_item.save()
                message = f"Quantity updated to {quantity}"
            
            cart = Cart.objects.get(user=user)
            
            return {
                'success': True,
                'message': message,
                'cart': cart
            }
            
        except CartItem.DoesNotExist:
            return {
                'success': False,
                'message': 'Cart item not found',
                'errors': {'item': 'Does not exist'}
            }
    
    @staticmethod
    def remove_cart_item(user, item_id):
        """Remove item from cart"""
        try:
            cart_item = get_object_or_404(CartItem, id=item_id, cart__user=user)
            cart_item.delete()
            
            cart = Cart.objects.get(user=user)
            
            return {
                'success': True,
                'message': 'Item removed from cart',
                'cart': cart
            }
        except CartItem.DoesNotExist:
            return {
                'success': False,
                'message': 'Cart item not found',
                'errors': {'item': 'Does not exist'}
            }
    
    @staticmethod
    def clear_cart(user):
        """Clear all items from cart"""
        cart = Cart.objects.filter(user=user).first()
        if cart:
            cart.clear()
            return {'success': True, 'message': 'Cart cleared successfully'}
        return {'success': True, 'message': 'Cart is already empty'}
    
    @staticmethod
    def get_cart_summary(user):
        """Get cart summary for checkout"""
        cart, _ = Cart.objects.get_or_create(user=user)
        return {
            'success': True,
            'cart': cart,
            'summary': {
                'total_items': cart.total_items,
                'subtotal': cart.subtotal,
                'delivery_fee': cart.delivery_fee,
                'tax': cart.tax,
                'total': cart.total
            }
        }
