import paypalrestsdk
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from apps.payments.models import Payment, Refund
from apps.orders.models import Order, OrderActivity
import logging

logger = logging.getLogger(__name__)

class PayPalService:
    """PayPal payment integration service"""
    
    def __init__(self):
        paypalrestsdk.configure({
            "mode": settings.PAYPAL_MODE,  # sandbox or live
            "client_id": settings.PAYPAL_CLIENT_ID,
            "client_secret": settings.PAYPAL_CLIENT_SECRET
        })
    
    def create_order(self, payment: Payment, return_url: str, cancel_url: str) -> Dict[str, Any]:
        """Create PayPal order"""
        try:
            # Determine currency (PayPal requires USD for sandbox in some regions)
            currency = "USD"  # Force USD for simplicity, or implement conversion
            
            order_data = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(payment.order.order_number),
                    "amount": {
                        "currency_code": currency,
                        "value": str(round(float(payment.amount), 2)),
                        "breakdown": {
                            "item_total": {
                                "currency_code": currency,
                                "value": str(round(float(payment.amount), 2))
                            }
                        }
                    },
                    "description": f"Order {payment.order.order_number}",
                    "custom_id": str(payment.order.id),
                    "invoice_id": payment.order.order_number
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "brand_name": "Wakulima",
                    "landing_page": "BILLING",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "SET_PROVIDED_ADDRESS"
                }
            }
            
            # Create order
            order = paypalrestsdk.Order.create(order_data)
            
            if not order.success():
                logger.error(f"PayPal order creation failed: {order.error}")
                return {
                    'success': False,
                    'error': order.error.get('message', 'Unknown error')
                }
            
            # Store PayPal order ID
            payment.paypal_order_id = order.id
            payment.request_data = order_data
            payment.save(update_fields=['paypal_order_id', 'request_data'])
            
            # Find approval URL
            approval_url = None
            for link in order.links:
                if link.rel == "approve":
                    approval_url = link.href
                    break
            
            logger.info(f"PayPal order created for payment {payment.id} - Order ID: {order.id}")
            
            return {
                'success': True,
                'order_id': order.id,
                'approval_url': approval_url,
                'status': order.status
            }
        except paypalrestsdk.exceptions.ConnectionError as e:
            logger.error(f"PayPal connection error: {str(e)}")
            return {'success': False, 'error': f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"PayPal order creation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def capture_order(self, payment: Payment, payer_id: str) -> Dict[str, Any]:
        """Capture PayPal payment after approval"""
        try:
            order = paypalrestsdk.Order.find(payment.paypal_order_id)
            
            if not order:
                return {
                    'success': False,
                    'error': f"Order {payment.paypal_order_id} not found"
                }
            
            # Capture payment
            capture = order.capture({})
            
            if capture.success():
                # Extract capture details
                capture_id = capture.id
                capture_amount = capture.amount.total if hasattr(capture, 'amount') else None
                
                # Payment successful
                payment.paypal_payer_id = payer_id
                payment.transaction_id = capture_id
                payment.status = Payment.PaymentStatus.SUCCESS
                payment.paid_at = timezone.now()
                payment.response_data = capture.to_dict()
                payment.save()
                
                # Update order
                order_obj = payment.order
                order_obj.payment_status = Order.PaymentStatus.PAID
                order_obj.paid_at = timezone.now()
                
                if order_obj.order_status == Order.OrderStatus.PENDING:
                    order_obj.order_status = Order.OrderStatus.PROCESSING
                order_obj.save()
                
                # Log activity
                OrderActivity.objects.create(
                    order=order_obj,
                    activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
                    description=f"PayPal payment captured - Transaction: {capture_id} - Amount: {capture_amount}",
                    performed_by=payment.user,
                    ip_address='system'
                )
                
                logger.info(f"PayPal payment captured for payment {payment.id} - Capture ID: {capture_id}")
                
                return {
                    'success': True,
                    'capture_id': capture_id,
                    'status': capture.state,
                    'amount': capture_amount
                }
            else:
                error_message = capture.error.get('message', 'Unknown error') if capture.error else 'Capture failed'
                payment.status = Payment.PaymentStatus.FAILED
                payment.response_data = {'error': capture.error}
                payment.save()
                
                # Log failure
                OrderActivity.objects.create(
                    order=payment.order,
                    activity_type='payment_failed',
                    description=f"PayPal payment capture failed: {error_message}",
                    performed_by=payment.user,
                    ip_address='system'
                )
                
                logger.error(f"PayPal capture failed for payment {payment.id}: {capture.error}")
                
                return {
                    'success': False,
                    'error': error_message
                }
        except paypalrestsdk.exceptions.ResourceNotFound as e:
            logger.error(f"PayPal order not found: {str(e)}")
            return {'success': False, 'error': 'Order not found'}
        except paypalrestsdk.exceptions.ConnectionError as e:
            logger.error(f"PayPal connection error: {str(e)}")
            return {'success': False, 'error': f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"PayPal capture failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def refund_payment(self, payment: Payment, amount: Decimal, reason: str) -> Dict[str, Any]:
        """Refund PayPal payment"""
        try:
            # Find the capture
            capture = paypalrestsdk.Capture.find(payment.transaction_id)
            
            if not capture:
                return {
                    'success': False,
                    'error': f"Capture {payment.transaction_id} not found"
                }
            
            # Create refund
            refund_data = {
                "amount": {
                    "currency_code": "USD",
                    "value": str(round(float(amount), 2))
                },
                "invoice_number": f"REF-{payment.order.order_number}",
                "note_to_payer": reason[:150]  # PayPal limit
            }
            
            refund = capture.refund(refund_data)
            
            if refund.success():
                # Update refund record
                refund_obj = Refund.objects.create(
                    payment=payment,
                    order=payment.order,
                    user=payment.user,
                    amount=amount,
                    reason=reason,
                    status=Refund.RefundStatus.COMPLETED,
                    refund_id=refund.id,
                    gateway_response=refund.to_dict(),
                    completed_at=timezone.now()
                )
                
                # Update payment status
                # Check if full refund or partial
                if amount >= payment.amount:
                    payment.status = Payment.PaymentStatus.REFUNDED
                else:
                    payment.status = Payment.PaymentStatus.PARTIALLY_REFUNDED
                
                payment.refunded_at = timezone.now()
                
                if not payment.response_data:
                    payment.response_data = {}
                payment.response_data['refund'] = refund.to_dict()
                payment.save()
                
                # Update order
                order = payment.order
                if amount >= payment.amount:
                    order.payment_status = Order.PaymentStatus.REFUNDED
                else:
                    order.payment_status = Order.PaymentStatus.PARTIALLY_REFUNDED
                order.save()
                
                # Log activity
                OrderActivity.objects.create(
                    order=order,
                    activity_type=OrderActivity.ActivityType.REFUND_COMPLETED,
                    description=f"PayPal refund processed - Amount: {amount} - Reason: {reason[:100]}",
                    performed_by=payment.user,
                    ip_address='system'
                )
                
                logger.info(f"PayPal refund processed for payment {payment.id} - Refund ID: {refund.id}")
                
                return {
                    'success': True,
                    'refund_id': refund.id,
                    'status': refund.state
                }
            else:
                error_message = refund.error.get('message', 'Unknown error') if refund.error else 'Refund failed'
                logger.error(f"PayPal refund failed for payment {payment.id}: {refund.error}")
                
                return {
                    'success': False,
                    'error': error_message
                }
        except paypalrestsdk.exceptions.ResourceNotFound as e:
            logger.error(f"PayPal capture not found: {str(e)}")
            return {'success': False, 'error': 'Capture not found'}
        except paypalrestsdk.exceptions.ConnectionError as e:
            logger.error(f"PayPal connection error: {str(e)}")
            return {'success': False, 'error': f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"PayPal refund failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_order_status(self, payment: Payment) -> Dict[str, Any]:
        """Get PayPal order status"""
        try:
            order = paypalrestsdk.Order.find(payment.paypal_order_id)
            
            if not order:
                return {
                    'success': False,
                    'error': 'Order not found'
                }
            
            return {
                'success': True,
                'status': order.status,
                'order_details': order.to_dict()
            }
        except paypalrestsdk.exceptions.ResourceNotFound as e:
            logger.error(f"PayPal order not found: {str(e)}")
            return {'success': False, 'error': 'Order not found'}
        except Exception as e:
            logger.error(f"Failed to get PayPal order status: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_capture_details(self, payment: Payment) -> Dict[str, Any]:
        """Get capture details for a payment"""
        try:
            capture = paypalrestsdk.Capture.find(payment.transaction_id)
            
            if not capture:
                return {
                    'success': False,
                    'error': 'Capture not found'
                }
            
            return {
                'success': True,
                'capture': capture.to_dict(),
                'status': capture.state,
                'amount': capture.amount.total if hasattr(capture, 'amount') else None
            }
        except Exception as e:
            logger.error(f"Failed to get capture details: {str(e)}")
            return {'success': False, 'error': str(e)}
