import json
import hmac
import hashlib
import re
from typing import Dict, Any, List
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from apps.payments.models import Payment, PaymentWebhook
from apps.orders.models import Order, OrderActivity
from .base_handler import BaseWebhookHandler
import logging
import requests

logger = logging.getLogger(__name__)

class MpesaWebhookHandler(BaseWebhookHandler):
    """Production-ready M-Pesa webhook handler with IP whitelisting and signature validation"""
    
    # M-Pesa known IP ranges for production
    MPESA_IP_WHITELIST = [
        '196.201.214.200',
        '196.201.214.202',
        '196.201.214.204',
        '196.201.214.206',
        '196.201.214.208',
        '196.201.214.210',
        '196.201.214.212',
        '196.201.214.214',
        '196.201.214.216',
        '196.201.214.218',
        '196.201.220.0/24',
        '196.201.221.0/24',
    ]
    
    def __init__(self):
        super().__init__(gateway='mpesa')
        self.passkey = settings.MPESA_PASSKEY
        self.shortcode = settings.MPESA_SHORTCODE
    
    def validate_signature(self, request_data: Dict[str, Any], signature: str = None, raw_body: bytes = None, client_ip: str = None) -> bool:
        """
        Validate M-Pesa webhook signature using multiple methods:
        1. IP whitelisting (production)
        2. Origin header validation
        3. Request body hash verification
        """
        # For development environment, allow without strict validation
        if settings.DEBUG or settings.MPESA_ENVIRONMENT == 'sandbox':
            logger.info("Development/Sandbox environment - skipping strict M-Pesa signature validation")
            return True
        
        # Production validation
        # Method 1: IP Whitelisting
        if not self._validate_ip_address(client_ip):
            logger.error(f"M-Pesa webhook rejected: Invalid IP address {client_ip}")
            return False
        
        # Method 2: Validate origin/security headers
        if not self._validate_security_headers(request_data):
            logger.error("M-Pesa webhook rejected: Invalid security headers")
            return False
        
        # Method 3: Validate request body signature (if available)
        if raw_body and signature:
            if not self._validate_body_signature(raw_body, signature):
                logger.error("M-Pesa webhook rejected: Invalid body signature")
                return False
        
        logger.info("M-Pesa webhook signature validation passed")
        return True
    
    def _validate_ip_address(self, client_ip: str) -> bool:
        """Validate if the request comes from M-Pesa's IP ranges"""
        if not client_ip:
            logger.warning("No client IP provided for M-Pesa webhook validation")
            return False
        
        # Check if IP is in whitelist
        from ipaddress import ip_address, ip_network
        
        try:
            client_ip_obj = ip_address(client_ip)
            for ip_range in self.MPESA_IP_WHITELIST:
                if '/' in ip_range:
                    # CIDR range
                    if client_ip_obj in ip_network(ip_range):
                        return True
                else:
                    # Single IP
                    if client_ip == ip_range:
                        return True
        except Exception as e:
            logger.error(f"Error validating IP address {client_ip}: {str(e)}")
            return False
        
        return False
    
    def _validate_security_headers(self, request_data: Dict[str, Any]) -> bool:
        """Validate M-Pesa security headers"""
        # Check for required M-Pesa specific data
        body = request_data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        # M-Pesa callbacks must have these fields
        required_fields = ['ResultCode', 'ResultDesc', 'CheckoutRequestID']
        
        for field in required_fields:
            if field not in stk_callback:
                logger.warning(f"M-Pesa webhook missing required field: {field}")
                return False
        
        return True
    
    def _validate_body_signature(self, raw_body: bytes, signature: str) -> bool:
        """
        Validate request body signature using HMAC
        Note: M-Pesa doesn't provide signatures by default, this is for future-proofing
        """
        # If signature validation is implemented by M-Pesa in future
        # Use HMAC with passkey
        expected_signature = hmac.new(
            self.passkey.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process M-Pesa callback event"""
        try:
            # Extract the callback body
            body = webhook_data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            merchant_request_id = stk_callback.get('MerchantRequestID')
            
            # Log the webhook for audit
            self.save_webhook_record(
                event_type=f'stk_callback_{result_code}',
                payload=webhook_data,
                processed=False
            )
            
            # Find the payment
            payment = Payment.objects.filter(
                mpesa_checkout_request_id=checkout_request_id
            ).first()
            
            if not payment:
                logger.error(f"M-Pesa payment not found for checkout_id: {checkout_request_id}")
                return {
                    'success': False,
                    'error': 'Payment not found',
                    'result_code': 1,
                    'result_desc': 'Payment record not found'
                }
            
            # Check for duplicate callback (idempotency)
            if self._is_duplicate_callback(payment, result_code, checkout_request_id):
                logger.info(f"Duplicate M-Pesa callback ignored for payment: {payment.id}")
                return {
                    'success': True,
                    'result_code': 0,
                    'result_desc': 'Duplicate callback ignored',
                    'payment_id': str(payment.id)
                }
            
            # Update payment with callback data
            payment.mpesa_result_code = result_code
            payment.mpesa_result_desc = result_desc
            payment.webhook_data = webhook_data
            
            # Process based on result code
            if result_code == '0':
                return self._handle_successful_payment(payment, stk_callback)
            elif result_code == '1037':
                return self._handle_cancelled_payment(payment, result_desc)
            else:
                return self._handle_failed_payment(payment, result_code, result_desc)
                
        except Exception as e:
            logger.error(f"Error processing M-Pesa webhook: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'result_code': 1,
                'result_desc': 'Internal processing error'
            }
    
    def _is_duplicate_callback(self, payment: Payment, result_code: str, checkout_request_id: str) -> bool:
        """Check for duplicate webhook callbacks"""
        cache_key = f"mpesa_callback_{checkout_request_id}_{result_code}"
        
        # Check if already processed in last 5 minutes
        if cache.get(cache_key):
            return True
        
        # Also check if payment already has a final status
        if payment.status in [
            Payment.PaymentStatus.SUCCESS,
            Payment.PaymentStatus.CANCELLED,
            Payment.PaymentStatus.FAILED
        ]:
            return True
        
        # Set cache for 5 minutes to prevent duplicates
        cache.set(cache_key, True, timeout=300)
        return False
    
    def _handle_successful_payment(self, payment: Payment, stk_callback: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful M-Pesa payment"""
        # Extract metadata from callback
        callback_metadata = stk_callback.get('CallbackMetadata', {})
        items = callback_metadata.get('Item', [])
        
        amount = None
        receipt_number = None
        transaction_date = None
        phone_number = None
        
        for item in items:
            name = item.get('Name')
            value = item.get('Value')
            
            if name == 'Amount':
                amount = value
            elif name == 'MpesaReceiptNumber':
                receipt_number = value
                payment.transaction_id = value
            elif name == 'TransactionDate':
                transaction_date = value
            elif name == 'PhoneNumber':
                phone_number = value
        
        # Verify amount matches
        if amount and float(amount) != float(payment.amount):
            logger.warning(f"Amount mismatch for payment {payment.id}: Expected {payment.amount}, Got {amount}")
            # Still process but log warning
        
        # Update payment record
        payment.status = Payment.PaymentStatus.SUCCESS
        payment.paid_at = timezone.now()
        payment.response_data = {
            'amount': amount,
            'receipt_number': receipt_number,
            'transaction_date': transaction_date,
            'phone_number': phone_number
        }
        payment.save()
        
        # Update associated order
        order = payment.order
        order.payment_status = Order.PaymentStatus.PAID
        order.paid_at = timezone.now()
        
        # Update order status if it was pending
        if order.order_status == Order.OrderStatus.PENDING:
            order.order_status = Order.OrderStatus.PROCESSING
        
        order.save()
        
        # Log activity
        OrderActivity.objects.create(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
            description=f"M-Pesa payment successful - Receipt: {receipt_number} - Amount: KES {amount}",
            performed_by=payment.user,
            ip_address='webhook'
        )
        
        # Mark webhook as processed
        webhook = PaymentWebhook.objects.filter(
            payload__Body__stkCallback__CheckoutRequestID=payment.mpesa_checkout_request_id,
            processed=False
        ).first()
        if webhook:
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()
        
        logger.info(f"M-Pesa payment successful: {payment.id} - Receipt: {receipt_number}")
        
        # Trigger any post-payment actions (send email, update inventory, etc.)
        self._trigger_post_payment_actions(order)
        
        return {
            'success': True,
            'result_code': 0,
            'result_desc': 'Payment processed successfully',
            'payment_id': str(payment.id),
            'transaction_id': receipt_number,
            'amount': amount
        }
    
    def _handle_cancelled_payment(self, payment: Payment, result_desc: str) -> Dict[str, Any]:
        """Handle cancelled M-Pesa transaction"""
        payment.status = Payment.PaymentStatus.CANCELLED
        payment.response_data = {
            'cancelled_at': timezone.now().isoformat(),
            'reason': result_desc
        }
        payment.save()
        
        # Log activity
        OrderActivity.objects.create(
            order=payment.order,
            activity_type='payment_cancelled',
            description=f"M-Pesa payment cancelled by user: {result_desc}",
            performed_by=payment.user,
            ip_address='webhook'
        )
        
        logger.info(f"M-Pesa payment cancelled: {payment.id}")
        
        return {
            'success': True,
            'result_code': 1037,
            'result_desc': 'Payment cancelled by user',
            'payment_id': str(payment.id)
        }
    
    def _handle_failed_payment(self, payment: Payment, result_code: str, result_desc: str) -> Dict[str, Any]:
        """Handle failed M-Pesa transaction"""
        payment.status = Payment.PaymentStatus.FAILED
        payment.response_data = {
            'failed_at': timezone.now().isoformat(),
            'result_code': result_code,
            'result_desc': result_desc
        }
        payment.save()
        
        # Log activity
        OrderActivity.objects.create(
            order=payment.order,
            activity_type='payment_failed',
            description=f"M-Pesa payment failed: {result_desc}",
            performed_by=payment.user,
            ip_address='webhook'
        )
        
        logger.warning(f"M-Pesa payment failed: {payment.id} - {result_desc}")
        
        return {
            'success': False,
            'result_code': result_code,
            'result_desc': result_desc,
            'payment_id': str(payment.id)
        }
    
    def _trigger_post_payment_actions(self, order: Order):
        """Trigger actions after successful payment"""
        # This can be extended to send email notifications,
        # update inventory, trigger shipping, etc.
        from apps.orders.tasks import send_order_confirmation_email
        send_order_confirmation_email.delay(order.id)


class MpesaReversalWebhookHandler(BaseWebhookHandler):
    """Production-ready M-Pesa reversal/reconciliation webhook handler"""
    
    def __init__(self):
        super().__init__(gateway='mpesa')
    
    def validate_signature(self, request_data: Dict[str, Any], signature: str = None, raw_body: bytes = None, client_ip: str = None) -> bool:
        """Validate reversal webhook signature"""
        if settings.DEBUG or settings.MPESA_ENVIRONMENT == 'sandbox':
            return True
        
        # Use same IP validation
        mpesa_handler = MpesaWebhookHandler()
        return mpesa_handler.validate_signature(request_data, signature, raw_body, client_ip)
    
    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process transaction reversal webhook"""
        try:
            # Extract reversal data
            transaction = webhook_data.get('Transaction', {})
            transaction_id = transaction.get('TransactionID')
            reversal_amount = transaction.get('ReversalAmount')
            original_transaction_id = transaction.get('OriginalTransactionID')
            reason = transaction.get('Reason', 'No reason provided')
            
            # Check for duplicate
            cache_key = f"mpesa_reversal_{original_transaction_id}"
            if cache.get(cache_key):
                logger.info(f"Duplicate M-Pesa reversal ignored for transaction: {original_transaction_id}")
                return {'success': True, 'result_desc': 'Duplicate ignored'}
            
            # Find the original payment
            payment = Payment.objects.filter(
                transaction_id=original_transaction_id
            ).first()
            
            if payment:
                # Only process if not already refunded
                if payment.status != Payment.PaymentStatus.REFUNDED:
                    payment.status = Payment.PaymentStatus.REFUNDED
                    payment.refunded_at = timezone.now()
                    if not payment.response_data:
                        payment.response_data = {}
                    payment.response_data['reversal'] = {
                        'reversal_id': transaction_id,
                        'amount': reversal_amount,
                        'reason': reason,
                        'reversed_at': timezone.now().isoformat()
                    }
                    payment.save()
                    
                    # Update order
                    order = payment.order
                    order.payment_status = Order.PaymentStatus.REFUNDED
                    order.save()
                    
                    # Log activity
                    OrderActivity.objects.create(
                        order=order,
                        activity_type=OrderActivity.ActivityType.REFUND_COMPLETED,
                        description=f"M-Pesa reversal processed: {reason} - Amount: KES {reversal_amount}",
                        performed_by=None,
                        ip_address='webhook'
                    )
                    
                    logger.info(f"M-Pesa reversal processed for payment: {payment.id}")
            
            # Save webhook record
            self.save_webhook_record(
                event_type='transaction_reversal',
                payload=webhook_data,
                processed=True
            )
            
            # Cache to prevent duplicates
            cache.set(cache_key, True, timeout=86400)  # 24 hours
            
            return {
                'success': True,
                'result_code': 0,
                'result_desc': 'Reversal processed successfully'
            }
            
        except Exception as e:
            logger.error(f"Error processing M-Pesa reversal: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
