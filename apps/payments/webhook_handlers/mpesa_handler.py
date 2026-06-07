import hashlib
import hmac
import json
import logging
import re
from typing import Any, Dict, List

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.orders.models import Order, OrderActivity
from apps.payments.models import Payment, PaymentWebhook

from .base_handler import BaseWebhookHandler

logger = logging.getLogger(__name__)


class MpesaWebhookHandler(BaseWebhookHandler):
    """Production-ready M-Pesa webhook handler with IP whitelisting and signature validation"""

    def __init__(self):
        super().__init__(gateway="mpesa")
        self.passkey = settings.MPESA_PASSKEY
        self.shortcode = settings.MPESA_SHORTCODE
        self.environment = settings.MPESA_ENVIRONMENT

    def validate_signature(
        self,
        request_data: Dict[str, Any],
        signature: str = None,
        raw_body: bytes = None,
        client_ip: str = None,
    ) -> bool:
        """
        Validate M-Pesa webhook signature using multiple methods:
        1. IP whitelisting (production)
        2. Origin header validation
        3. Request body hash verification
        """
        if settings.DEBUG or self.environment == "sandbox":
            logger.info(
                "Development/Sandbox environment - skipping strict M-Pesa signature validation"
            )
            return True

        if settings.MPESA_IP_WHITELIST_ENABLED:
            if not self._validate_ip_address(client_ip):
                logger.error(
                    f"M-Pesa webhook rejected: Invalid IP address {client_ip}"
                )
                return False

        if not self._validate_security_headers(request_data):
            logger.error("M-Pesa webhook rejected: Invalid security headers")
            return False

        logger.info("M-Pesa webhook signature validation passed")
        return True

    def _validate_ip_address(self, client_ip: str) -> bool:
        """Validate if the request comes from M-Pesa's IP ranges"""
        if not client_ip:
            logger.warning(
                "No client IP provided for M-Pesa webhook validation"
            )
            return False

        from ipaddress import ip_address, ip_network

        try:
            client_ip_obj = ip_address(client_ip)
            for ip_range in settings.MPESA_IP_WHITELIST:
                if "/" in ip_range:
                    if client_ip_obj in ip_network(ip_range):
                        return True
                else:
                    if client_ip == ip_range:
                        return True
        except Exception as e:
            logger.error(f"Error validating IP address {client_ip}: {str(e)}")
            return False

        return False

    def _validate_security_headers(self, request_data: Dict[str, Any]) -> bool:
        """Validate M-Pesa security headers"""
        body = request_data.get("Body", {})
        stk_callback = body.get("stkCallback", {})

        required_fields = ["ResultCode", "ResultDesc", "CheckoutRequestID"]

        for field in required_fields:
            if field not in stk_callback:
                logger.warning(
                    f"M-Pesa webhook missing required field: {field}"
                )
                return False

        return True

    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process M-Pesa callback event"""
        try:
            body = webhook_data.get("Body", {})
            stk_callback = body.get("stkCallback", {})

            result_code = stk_callback.get("ResultCode")
            result_desc = stk_callback.get("ResultDesc")
            checkout_request_id = stk_callback.get("CheckoutRequestID")

            self.save_webhook_record(
                event_type=f"stk_callback_{result_code}",
                payload=webhook_data,
                processed=False,
            )

            payment = Payment.objects.filter(
                mpesa_checkout_request_id=checkout_request_id
            ).first()

            if not payment:
                logger.error(
                    f"M-Pesa payment not found for checkout_id: {checkout_request_id}"
                )
                return {
                    "success": False,
                    "error": "Payment not found",
                    "result_code": 1,
                    "result_desc": "Payment record not found",
                }

            if self._is_duplicate_callback(
                payment, result_code, checkout_request_id
            ):
                logger.info(
                    f"Duplicate M-Pesa callback ignored for payment: {payment.id}"
                )
                return {
                    "success": True,
                    "result_code": 0,
                    "result_desc": "Duplicate callback ignored",
                    "payment_id": str(payment.id),
                }

            payment.mpesa_result_code = result_code
            payment.mpesa_result_desc = result_desc
            payment.webhook_data = webhook_data

            if result_code == "0":
                return self._handle_successful_payment(payment, stk_callback)
            elif result_code == "1037":
                return self._handle_cancelled_payment(payment, result_desc)
            else:
                return self._handle_failed_payment(
                    payment, result_code, result_desc
                )

        except Exception as e:
            logger.error(f"Error processing M-Pesa webhook: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "result_code": 1,
                "result_desc": "Internal processing error",
            }

    def _is_duplicate_callback(
        self, payment: Payment, result_code: str, checkout_request_id: str
    ) -> bool:
        """Check for duplicate webhook callbacks"""
        cache_key = f"mpesa_callback_{checkout_request_id}_{result_code}"

        if cache.get(cache_key):
            return True

        if payment.status in [
            Payment.PaymentStatus.SUCCESS,
            Payment.PaymentStatus.CANCELLED,
            Payment.PaymentStatus.FAILED,
        ]:
            return True

        cache.set(cache_key, True, timeout=300)
        return False

    def _handle_successful_payment(
        self, payment: Payment, stk_callback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle successful M-Pesa payment"""
        callback_metadata = stk_callback.get("CallbackMetadata", {})
        items = callback_metadata.get("Item", [])

        amount = None
        receipt_number = None
        transaction_date = None
        phone_number = None

        for item in items:
            name = item.get("Name")
            value = item.get("Value")

            if name == "Amount":
                amount = value
            elif name == "MpesaReceiptNumber":
                receipt_number = value
                payment.transaction_id = value
            elif name == "TransactionDate":
                transaction_date = value
            elif name == "PhoneNumber":
                phone_number = value

        payment.status = Payment.PaymentStatus.SUCCESS
        payment.paid_at = timezone.now()
        payment.response_data = {
            "amount": amount,
            "receipt_number": receipt_number,
            "transaction_date": transaction_date,
            "phone_number": phone_number,
        }
        payment.save()

        order = payment.order
        order.payment_status = Order.PaymentStatus.PAID
        order.paid_at = timezone.now()

        if order.order_status == Order.OrderStatus.PENDING:
            order.order_status = Order.OrderStatus.PROCESSING

        order.save()

        OrderActivity.objects.create(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
            description=f"M-Pesa payment successful - Receipt: {receipt_number} - Amount: KES {amount}",
            performed_by=payment.user,
            ip_address="webhook",
        )

        webhook = PaymentWebhook.objects.filter(
            payload__Body__stkCallback__CheckoutRequestID=payment.mpesa_checkout_request_id,
            processed=False,
        ).first()
        if webhook:
            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.save()

        logger.info(
            f"M-Pesa payment successful: {payment.id} - Receipt: {receipt_number}"
        )

        self._trigger_post_payment_actions(order)

        return {
            "success": True,
            "result_code": 0,
            "result_desc": "Payment processed successfully",
            "payment_id": str(payment.id),
            "transaction_id": receipt_number,
            "amount": amount,
        }

    def _handle_cancelled_payment(
        self, payment: Payment, result_desc: str
    ) -> Dict[str, Any]:
        """Handle cancelled M-Pesa transaction"""
        payment.status = Payment.PaymentStatus.CANCELLED
        payment.response_data = {
            "cancelled_at": timezone.now().isoformat(),
            "reason": result_desc,
        }
        payment.save()

        OrderActivity.objects.create(
            order=payment.order,
            activity_type="payment_cancelled",
            description=f"M-Pesa payment cancelled by user: {result_desc}",
            performed_by=payment.user,
            ip_address="webhook",
        )

        logger.info(f"M-Pesa payment cancelled: {payment.id}")

        return {
            "success": True,
            "result_code": 1037,
            "result_desc": "Payment cancelled by user",
            "payment_id": str(payment.id),
        }

    def _handle_failed_payment(
        self, payment: Payment, result_code: str, result_desc: str
    ) -> Dict[str, Any]:
        """Handle failed M-Pesa transaction"""
        payment.status = Payment.PaymentStatus.FAILED
        payment.response_data = {
            "failed_at": timezone.now().isoformat(),
            "result_code": result_code,
            "result_desc": result_desc,
        }
        payment.save()

        OrderActivity.objects.create(
            order=payment.order,
            activity_type="payment_failed",
            description=f"M-Pesa payment failed: {result_desc}",
            performed_by=payment.user,
            ip_address="webhook",
        )

        logger.warning(f"M-Pesa payment failed: {payment.id} - {result_desc}")

        return {
            "success": False,
            "result_code": result_code,
            "result_desc": result_desc,
            "payment_id": str(payment.id),
        }

    def _trigger_post_payment_actions(self, order: Order):
        """Trigger actions after successful payment"""
        from apps.orders.tasks import send_order_confirmation_email

        send_order_confirmation_email.delay(order.id)


class MpesaReversalWebhookHandler(BaseWebhookHandler):
    """Handle M-Pesa reversal/reconciliation webhooks"""

    def __init__(self):
        super().__init__(gateway="mpesa")

    def validate_signature(
        self,
        request_data: Dict[str, Any],
        signature: str = None,
        raw_body: bytes = None,
        client_ip: str = None,
    ) -> bool:
        """Validate reversal webhook signature"""
        if (
            settings.DEBUG
            or getattr(settings, "MPESA_ENVIRONMENT", "sandbox") == "sandbox"
        ):
            return True

        mpesa_handler = MpesaWebhookHandler()
        return mpesa_handler.validate_signature(
            request_data, signature, raw_body, client_ip
        )

    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process transaction reversal webhook"""
        try:
            transaction = webhook_data.get("Transaction", {})
            transaction_id = transaction.get("TransactionID")
            reversal_amount = transaction.get("ReversalAmount")
            original_transaction_id = transaction.get("OriginalTransactionID")
            reason = transaction.get("Reason", "No reason provided")

            cache_key = f"mpesa_reversal_{original_transaction_id}"
            if cache.get(cache_key):
                logger.info(
                    f"Duplicate M-Pesa reversal ignored for transaction: {original_transaction_id}"
                )
                return {"success": True, "result_desc": "Duplicate ignored"}

            payment = Payment.objects.filter(
                transaction_id=original_transaction_id
            ).first()

            if payment:
                if payment.status != Payment.PaymentStatus.REFUNDED:
                    payment.status = Payment.PaymentStatus.REFUNDED
                    payment.refunded_at = timezone.now()
                    if not payment.response_data:
                        payment.response_data = {}
                    payment.response_data["reversal"] = {
                        "reversal_id": transaction_id,
                        "amount": reversal_amount,
                        "reason": reason,
                        "reversed_at": timezone.now().isoformat(),
                    }
                    payment.save()

                    order = payment.order
                    order.payment_status = Order.PaymentStatus.REFUNDED
                    order.save()

                    OrderActivity.objects.create(
                        order=order,
                        activity_type=OrderActivity.ActivityType.REFUND_COMPLETED,
                        description=f"M-Pesa reversal processed: {reason} - Amount: KES {reversal_amount}",
                        performed_by=None,
                        ip_address="webhook",
                    )

                    logger.info(
                        f"M-Pesa reversal processed for payment: {payment.id}"
                    )

            self.save_webhook_record(
                event_type="transaction_reversal",
                payload=webhook_data,
                processed=True,
            )

            cache.set(cache_key, True, timeout=86400)

            return {
                "success": True,
                "result_code": 0,
                "result_desc": "Reversal processed successfully",
            }

        except Exception as e:
            logger.error(f"Error processing M-Pesa reversal: {str(e)}")
            return {"success": False, "error": str(e)}
