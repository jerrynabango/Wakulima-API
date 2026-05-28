import json
import hmac
import hashlib
import base64
from typing import Dict, Any
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
import requests
from apps.payments.models import Payment, PaymentWebhook
from apps.orders.models import Order, OrderActivity
from .base_handler import BaseWebhookHandler
import logging

logger = logging.getLogger(__name__)

class PayPalWebhookHandler(BaseWebhookHandler):
    """Production-ready PayPal webhook handler with proper signature verification"""
    
    def __init__(self):
        super().__init__(gateway='paypal')
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.webhook_id = getattr(settings, 'PAYPAL_WEBHOOK_ID', None)
        
        # Set API URL based on mode
        if settings.PAYPAL_MODE == 'live':
            self.api_url = "https://api.paypal.com"
        else:
            self.api_url = "https://api.sandbox.paypal.com"
    
    def validate_signature(self, request_data: Dict[str, Any], signature: str = None, raw_body: bytes = None, headers: Dict[str, str] = None) -> bool:
        """
        Validate PayPal webhook signature using PayPal's verification API
        This is the official PayPal recommended method
        """
        # For development environment, allow without strict validation
        if settings.DEBUG or settings.PAYPAL_MODE == 'sandbox':
            if not settings.DEBUG:
                # Even in sandbox, we still validate but with more tolerance
                logger.info("Sandbox environment - performing PayPal signature validation")
            else:
                logger.info("Development environment - skipping PayPal signature validation")
                return True
        
        # Production validation using PayPal API
        if not headers or not raw_body:
            logger.error("Missing headers or raw body for PayPal webhook validation")
            return False
        
        # Get PayPal verification headers
        transmission_id = headers.get('PayPal-Transmission-Id')
        transmission_time = headers.get('PayPal-Transmission-Time')
        cert_url = headers.get('PayPal-Cert-Url')
        auth_algo = headers.get('PayPal-Auth-Algo')
        transmission_sig = headers.get('PayPal-Transmission-Sig')
        
        if not all([transmission_id, transmission_time, cert_url, auth_algo, transmission_sig]):
            logger.error("Missing required PayPal verification headers")
            return False
        
        # Get access token
        access_token = self._get_access_token()
        if not access_token:
            logger.error("Failed to get PayPal access token for webhook verification")
            return False
        
        # Verify webhook signature using PayPal API
        verification_url = f"{self.api_url}/v1/notifications/verify-webhook-signature"
        
        # Prepare verification payload
        verification_payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": self.webhook_id,
            "webhook_event": request_data
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                verification_url,
                json=verification_payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            verification_status = result.get('verification_status')
            
            if verification_status == 'SUCCESS':
                logger.info("PayPal webhook signature verified successfully")
                return True
            else:
                logger.error(f"PayPal webhook verification failed: {verification_status}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error verifying PayPal webhook signature: {str(e)}")
            return False
    
    def _get_access_token(self) -> str:
        """Get PayPal access token for API calls"""
        # Check cache first
        cache_key = "paypal_access_token"
        token = cache.get(cache_key)
        
        if token:
            return token
        
        # Get new token
        auth_url = f"{self.api_url}/v1/oauth2/token"
        
        auth = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(auth_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            token = result.get('access_token')
            
            # Cache token for 30 minutes (PayPal tokens expire in ~45 minutes)
            if token:
                cache.set(cache_key, token, timeout=1800)
            
            return token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get PayPal access token: {str(e)}")
            return None
    
    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process different PayPal webhook event types"""
        event_type = webhook_data.get('event_type')
        event_id = webhook_data.get('id')
        
        # Check for duplicate webhook
        if self._is_duplicate_webhook(event_id):
            logger.info(f"Duplicate PayPal webhook ignored: {event_id}")
            return {'success': True, 'message': 'Duplicate webhook ignored'}
        
        # Save webhook record
        self.save_webhook_record(
            event_type=event_type,
            payload=webhook_data,
            processed=False
        )
        
        # Route to appropriate handler based on event type
        handlers = {
            'PAYMENT.CAPTURE.COMPLETED': self._handle_payment_capture_completed,
            'PAYMENT.CAPTURE.DENIED': self._handle_payment_capture_denied,
            'PAYMENT.CAPTURE.REFUNDED': self._handle_payment_refunded,
            'PAYMENT.CAPTURE.REVERSED': self._handle_payment_reversed,
            'CHECKOUT.ORDER.APPROVED': self._handle_order_approved,
            'CHECKOUT.ORDER.COMPLETED': self._handle_order_completed,
            'CUSTOMER.DISPUTE.CREATED': self._handle_dispute_created,
            'CUSTOMER.DISPUTE.RESOLVED': self._handle_dispute_resolved,
            'PAYMENT.AUTHORIZATION.VOIDED': self._handle_authorization_voided,
        }
        
        handler = handlers.get(event_type)
        if handler:
            result = handler(webhook_data)
            self._mark_webhook_processed(event_id, result.get('success', False))
            return result
        else:
            logger.info(f"Unhandled PayPal webhook event type: {event_type}")
            return {
                'success': True,
                'message': f'Event {event_type} received but not processed',
                'event_type': event_type
            }
    
    def _is_duplicate_webhook(self, event_id: str) -> bool:
        """Check for duplicate webhook events"""
        if not event_id:
            return False
        
        cache_key = f"paypal_webhook_{event_id}"
        
        if cache.get(cache_key):
            return True
        
        # Also check database
        if PaymentWebhook.objects.filter(
            gateway='paypal',
            payload__id=event_id,
            processed=True
        ).exists():
            cache.set(cache_key, True, timeout=86400)
            return True
        
        cache.set(cache_key, False, timeout=3600)
        return False
    
    def _handle_payment_capture_completed(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment capture completed event"""
        resource = webhook_data.get('resource', {})
        capture_id = resource.get('id')
        order_id = resource.get('supplementary_data', {}).get('related_ids', {}).get('order_id')
        amount = resource.get('amount', {})
        seller_receivable_breakdown = resource.get('seller_receivable_breakdown', {})
        
        # Find the payment by capture ID or order ID
        payment = Payment.objects.filter(
            transaction_id=capture_id
        ).first()
        
        if not payment and order_id:
            payment = Payment.objects.filter(
                paypal_order_id=order_id
            ).first()
        
        if not payment:
            logger.error(f"PayPal payment not found for capture: {capture_id}")
            return {
                'success': False,
                'error': 'Payment not found',
                'capture_id': capture_id
            }
        
        # Update payment status
        payment.status = Payment.PaymentStatus.SUCCESS
        payment.transaction_id = capture_id
        payment.paid_at = timezone.now()
        payment.response_data = {
            'capture': resource,
            'seller_receivable': seller_receivable_breakdown
        }
        payment.save()
        
        # Update order
        order = payment.order
        order.payment_status = Order.PaymentStatus.PAID
        order.paid_at = timezone.now()
        
        if order.order_status == Order.OrderStatus.PENDING:
            order.order_status = Order.OrderStatus.PROCESSING
        
        order.save()
        
        # Calculate actual amount received (after fees)
        net_amount = seller_receivable_breakdown.get('net_amount', {}).get('value', amount.get('value'))
        
        # Log activity
        OrderActivity.objects.create(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
            description=f"PayPal payment captured - Capture ID: {capture_id} - Amount: {amount.get('value')} {amount.get('currency_code')} (Net: {net_amount})",
            performed_by=payment.user,
            ip_address='webhook'
        )
        
        logger.info(f"PayPal payment captured: {payment.id} - Capture ID: {capture_id}")
        
        # Trigger post-payment actions
        self._trigger_post_payment_actions(order)
        
        return {
            'success': True,
            'message': 'Payment capture completed',
            'payment_id': str(payment.id),
            'capture_id': capture_id
        }
    
    def _handle_payment_capture_denied(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment capture denied event"""
        resource = webhook_data.get('resource', {})
        capture_id = resource.get('id')
        status_details = resource.get('status_details', {})
        reason = status_details.get('reason', 'Unknown')
        
        payment = Payment.objects.filter(transaction_id=capture_id).first()
        
        if payment:
            payment.status = Payment.PaymentStatus.FAILED
            payment.response_data = {
                'capture_denied': resource,
                'denied_reason': reason,
                'denied_at': timezone.now().isoformat()
            }
            payment.save()
            
            OrderActivity.objects.create(
                order=payment.order,
                activity_type='payment_failed',
                description=f"PayPal payment capture denied: {reason}",
                performed_by=payment.user,
                ip_address='webhook'
            )
            
            logger.warning(f"PayPal payment capture denied: {payment.id} - {reason}")
        
        return {
            'success': True,
            'message': 'Payment capture denied processed'
        }
    
    def _handle_payment_refunded(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment refunded event"""
        resource = webhook_data.get('resource', {})
        links = resource.get('links', [])
        
        # Extract capture ID from links
        capture_id = None
        for link in links:
            if link.get('rel') == 'up':
                capture_id = link.get('href', '').split('/')[-1]
                break
        
        refund_id = resource.get('id')
        amount = resource.get('amount', {})
        
        payment = Payment.objects.filter(transaction_id=capture_id).first()
        
        if payment:
            # Update payment status
            payment.status = Payment.PaymentStatus.REFUNDED
            payment.refunded_at = timezone.now()
            
            if not payment.response_data:
                payment.response_data = {}
            
            payment.response_data['refund'] = {
                'refund_id': refund_id,
                'amount': amount.get('value'),
                'currency': amount.get('currency_code'),
                'refunded_at': timezone.now().isoformat()
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
                description=f"PayPal refund processed - Refund ID: {refund_id} - Amount: {amount.get('value')} {amount.get('currency_code')}",
                performed_by=None,
                ip_address='webhook'
            )
            
            logger.info(f"PayPal refund processed: {payment.id} - Refund ID: {refund_id}")
        
        return {
            'success': True,
            'message': 'Refund processed',
            'refund_id': refund_id
        }
    
    def _handle_payment_reversed(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment reversal event (chargeback)"""
        resource = webhook_data.get('resource', {})
        sale_id = resource.get('sale_id')
        reason = resource.get('reason', 'No reason provided')
        
        payment = Payment.objects.filter(transaction_id=sale_id).first()
        
        if payment:
            payment.status = Payment.PaymentStatus.REFUNDED
            payment.refunded_at = timezone.now()
            
            if not payment.response_data:
                payment.response_data = {}
            
            payment.response_data['chargeback'] = {
                'reversed_at': timezone.now().isoformat(),
                'reason': reason,
                'webhook_data': resource
            }
            payment.save()
            
            order = payment.order
            order.payment_status = Order.PaymentStatus.REFUNDED
            order.save()
            
            OrderActivity.objects.create(
                order=order,
                activity_type='payment_reversed',
                description=f"PayPal payment reversed (chargeback): {reason}",
                performed_by=None,
                ip_address='webhook'
            )
            
            logger.warning(f"PayPal payment reversed: {payment.id} - {reason}")
        
        return {
            'success': True,
            'message': 'Payment reversal processed'
        }
    
    def _handle_order_approved(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle order approved event (customer approved payment)"""
        resource = webhook_data.get('resource', {})
        order_id = resource.get('id')
        
        payment = Payment.objects.filter(paypal_order_id=order_id).first()
        
        if payment:
            if payment.status == Payment.PaymentStatus.PENDING:
                payment.status = Payment.PaymentStatus.PROCESSING
                payment.save()
            
            logger.info(f"PayPal order approved: {order_id}")
        
        return {
            'success': True,
            'message': 'Order approval processed'
        }
    
    def _handle_order_completed(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle order completed event"""
        resource = webhook_data.get('resource', {})
        order_id = resource.get('id')
        
        payment = Payment.objects.filter(paypal_order_id=order_id).first()
        
        if payment and payment.status != Payment.PaymentStatus.SUCCESS:
            from apps.payments.services.paypal_service import PayPalService
            service = PayPalService()
            status_result = service.get_order_status(payment)
            
            if status_result.get('status') == 'COMPLETED':
                payment.status = Payment.PaymentStatus.SUCCESS
                payment.paid_at = timezone.now()
                payment.save()
                
                order = payment.order
                order.payment_status = Order.PaymentStatus.PAID
                order.save()
        
        return {
            'success': True,
            'message': 'Order completion processed'
        }
    
    def _handle_dispute_created(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dispute created event (customer opened dispute)"""
        resource = webhook_data.get('resource', {})
        dispute_id = resource.get('dispute_id')
        transaction_id = resource.get('transaction_id')
        reason = resource.get('reason')
        amount = resource.get('disputed_amount', {})
        
        payment = Payment.objects.filter(transaction_id=transaction_id).first()
        
        if payment:
            if not payment.response_data:
                payment.response_data = {}
            
            payment.response_data['dispute'] = {
                'dispute_id': dispute_id,
                'reason': reason,
                'amount': amount.get('value'),
                'status': 'OPEN',
                'created_at': timezone.now().isoformat()
            }
            payment.save()
            
            OrderActivity.objects.create(
                order=payment.order,
                activity_type='dispute_created',
                description=f"PayPal dispute opened: {reason} - Amount: {amount.get('value')} {amount.get('currency_code')}",
                performed_by=None,
                ip_address='webhook'
            )
            
            logger.warning(f"PayPal dispute created for payment {payment.id}: {dispute_id}")
        
        return {
            'success': True,
            'message': 'Dispute creation processed'
        }
    
    def _handle_dispute_resolved(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dispute resolved event"""
        resource = webhook_data.get('resource', {})
        dispute_id = resource.get('dispute_id')
        status = resource.get('status')
        
        payment = Payment.objects.filter(
            response_data__dispute__dispute_id=dispute_id
        ).first()
        
        if payment and payment.response_data.get('dispute'):
            payment.response_data['dispute']['status'] = status
            payment.response_data['dispute']['resolved_at'] = timezone.now().isoformat()
            payment.save()
            
            OrderActivity.objects.create(
                order=payment.order,
                activity_type='dispute_resolved',
                description=f"PayPal dispute resolved with status: {status}",
                performed_by=None,
                ip_address='webhook'
            )
            
            logger.info(f"PayPal dispute resolved: {dispute_id} - {status}")
        
        return {
            'success': True,
            'message': 'Dispute resolution processed'
        }
    
    def _handle_authorization_voided(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle authorization voided event"""
        resource = webhook_data.get('resource', {})
        authorization_id = resource.get('id')
        
        payment = Payment.objects.filter(transaction_id=authorization_id).first()
        
        if payment:
            payment.status = Payment.PaymentStatus.CANCELLED
            payment.save()
            
            OrderActivity.objects.create(
                order=payment.order,
                activity_type='payment_cancelled',
                description="PayPal authorization voided",
                performed_by=None,
                ip_address='webhook'
            )
            
            logger.info(f"PayPal authorization voided: {authorization_id}")
        
        return {
            'success': True,
            'message': 'Authorization voided processed'
        }
    
    def _mark_webhook_processed(self, event_id: str, success: bool):
        """Mark webhook as processed in database"""
        if event_id:
            webhook = PaymentWebhook.objects.filter(
                payload__id=event_id,
                processed=False
            ).first()
            
            if webhook:
                webhook.processed = success
                webhook.processed_at = timezone.now()
                webhook.save()
                
                # Cache to prevent duplicates
                if success:
                    cache.set(f"paypal_webhook_{event_id}", True, timeout=86400)
    
    def _trigger_post_payment_actions(self, order: Order):
        """Trigger actions after successful payment"""
        from apps.orders.tasks import send_order_confirmation_email
        send_order_confirmation_email.delay(order.id)
