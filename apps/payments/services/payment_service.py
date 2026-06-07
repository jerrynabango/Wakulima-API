import logging
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.orders.models import Order, OrderActivity
from apps.payments.models import Payment, Refund
from apps.payments.services.mpesa_service import MpesaService
from apps.payments.services.paypal_service import PayPalService

logger = logging.getLogger(__name__)


class PaymentService:
    """Business logic for payment operations"""

    @staticmethod
    def check_order_payment_status(order):
        """Check if order already has a successful payment"""
        return order.payments.filter(
            status=Payment.PaymentStatus.SUCCESS
        ).exists()

    @staticmethod
    @transaction.atomic
    def create_payment_record(
        order, user, amount, currency, gateway, **kwargs
    ):
        """Create a payment record"""
        return Payment.objects.create(
            order=order,
            user=user,
            amount=amount,
            currency=currency,
            gateway=gateway,
            status=Payment.PaymentStatus.PROCESSING,
            **kwargs,
        )

    @staticmethod
    def get_user_payments(user, limit=100):
        """Get user's payment history"""
        return Payment.objects.filter(user=user).select_related("order")[
            :limit
        ]

    @staticmethod
    def get_payment(payment_id, user=None):
        """Get payment with permission check"""
        query = Payment.objects.filter(id=payment_id)
        if user and not user.is_admin_user:
            query = query.filter(user=user)
        return get_object_or_404(query)

    @staticmethod
    def update_payment_status(payment, status, **kwargs):
        """Update payment status with validation"""
        old_status = payment.status
        payment.status = status

        for key, value in kwargs.items():
            setattr(payment, key, value)

        payment.save()

        # If payment succeeded, update order
        if status == Payment.PaymentStatus.SUCCESS and old_status != status:
            order = payment.order
            order.payment_status = Order.PaymentStatus.PAID
            order.paid_at = timezone.now()

            if order.order_status == Order.OrderStatus.PENDING:
                order.order_status = Order.OrderStatus.PROCESSING
            order.save()

            # Log activity
            OrderActivity.objects.create(
                order=order,
                activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
                description=f"Payment confirmed via {
                    payment.gateway} - Amount: {
                    payment.amount} {
                    payment.currency}",
                performed_by=payment.user,
                ip_address="system",
            )

        logger.info(f"Payment {
                payment.id} status updated: {old_status} -> {status}")
        return payment


class MpesaPaymentService:
    """M-Pesa specific payment operations"""

    @staticmethod
    def initiate_payment(order, user, phone_number):
        """
        Initiate M-Pesa STK Push payment
        Returns: {'success': bool, 'payment': Payment, 'message': str, 'checkout_id': str}
        """
        # Check if order already has successful payment
        if PaymentService.check_order_payment_status(order):
            return {
                "success": False,
                "message": "Order already has a successful payment",
            }

        # Create payment record
        payment = PaymentService.create_payment_record(
            order=order,
            user=user,
            amount=order.total,
            currency="KES",
            gateway=Payment.PaymentGateway.MPESA,
            customer_phone=phone_number,
        )

        # Initiate STK Push
        mpesa_service = MpesaService()
        result = mpesa_service.stk_push(payment, phone_number)

        if result["success"]:
            return {
                "success": True,
                "payment": payment,
                "message": result.get(
                    "customer_message", "STK Push initiated"
                ),
                "checkout_request_id": result.get("checkout_request_id"),
            }
        else:
            # Update payment as failed
            PaymentService.update_payment_status(
                payment,
                Payment.PaymentStatus.FAILED,
                response_data={"error": result.get("error")},
            )
            return {
                "success": False,
                "message": result.get("error", "Failed to initiate payment"),
            }

    @staticmethod
    def query_payment_status(payment):
        """Query M-Pesa payment status"""
        mpesa_service = MpesaService()
        return mpesa_service.query_status(payment)

    @staticmethod
    def process_webhook(webhook_data, client_ip):
        """Process M-Pesa webhook callback"""
        from apps.payments.webhook_handlers import MpesaWebhookHandler

        handler = MpesaWebhookHandler()

        # Validate signature
        if not handler.validate_signature(
            request_data=webhook_data, client_ip=client_ip, raw_body=None
        ):
            logger.error(
                f"M-Pesa webhook validation failed for IP: {client_ip}"
            )
            return {
                "success": False,
                "result_code": 1,
                "result_desc": "Invalid signature",
            }

        # Process event
        result = handler.process_event(webhook_data)

        return {
            "success": result.get("success", False),
            "result_code": 0 if result.get("success") else 1,
            "result_desc": result.get(
                "result_desc", "Success" if result.get("success") else "Failed"
            ),
        }


class PayPalPaymentService:
    """PayPal specific payment operations"""

    @staticmethod
    def initiate_payment(order, user, return_url, cancel_url):
        """
        Initiate PayPal payment
        Returns: {'success': bool, 'payment': Payment, 'approval_url': str}
        """
        # Check if order already has successful payment
        if PaymentService.check_order_payment_status(order):
            return {
                "success": False,
                "message": "Order already has a successful payment",
            }

        # Create payment record
        payment = PaymentService.create_payment_record(
            order=order,
            user=user,
            amount=order.total,
            currency="USD",  # Convert as needed
            gateway=Payment.PaymentGateway.PAYPAL,
        )

        # Create PayPal order
        paypal_service = PayPalService()
        result = paypal_service.create_order(payment, return_url, cancel_url)

        if result["success"]:
            return {
                "success": True,
                "payment": payment,
                "approval_url": result["approval_url"],
                "order_id": result["order_id"],
            }
        else:
            PaymentService.update_payment_status(
                payment,
                Payment.PaymentStatus.FAILED,
                response_data={"error": result.get("error")},
            )
            return {
                "success": False,
                "message": result.get(
                    "error", "Failed to create PayPal order"
                ),
            }

    @staticmethod
    def capture_payment(payment, payer_id):
        """
        Capture PayPal payment after approval
        Returns: {'success': bool, 'message': str, 'capture_id': str}
        """
        paypal_service = PayPalService()
        result = paypal_service.capture_order(payment, payer_id)

        if result["success"]:
            return {
                "success": True,
                "message": "Payment captured successfully",
                "capture_id": result["capture_id"],
            }
        else:
            return {
                "success": False,
                "message": result.get("error", "Failed to capture payment"),
            }

    @staticmethod
    def process_webhook(webhook_data, headers, raw_body):
        """Process PayPal webhook"""
        from apps.payments.webhook_handlers import PayPalWebhookHandler

        handler = PayPalWebhookHandler()

        # Validate signature
        if not handler.validate_signature(
            request_data=webhook_data, headers=headers, raw_body=raw_body
        ):
            logger.error("PayPal webhook signature validation failed")
            return {"success": False, "error": "Invalid signature"}

        # Process event
        result = handler.process_event(webhook_data)

        return result


class RefundService:
    """Business logic for refunds"""

    @staticmethod
    def validate_refund(payment, amount, user):
        """Validate refund request"""
        # Check permissions
        if user != payment.user and not user.is_admin_user:
            return {"success": False, "message": "Permission denied"}

        # Check if payment is successful
        if payment.status != Payment.PaymentStatus.SUCCESS:
            return {
                "success": False,
                "message": "Only successful payments can be refunded",
            }

        # Check amount
        if amount <= 0:
            return {
                "success": False,
                "message": "Refund amount must be greater than 0",
            }

        if amount > payment.amount:
            return {
                "success": False,
                "message": "Refund amount cannot exceed payment amount",
            }

        return {"success": True}

    @staticmethod
    def process_refund(payment, amount, reason, user):
        """
        Process refund for a payment
        Returns: {'success': bool, 'message': str, 'refund_id': str}
        """
        # Validate
        validation = RefundService.validate_refund(payment, amount, user)
        if not validation["success"]:
            return validation

        # Process based on gateway
        if payment.gateway == Payment.PaymentGateway.PAYPAL:
            paypal_service = PayPalService()
            result = paypal_service.refund_payment(payment, amount, reason)

            if result["success"]:
                return {
                    "success": True,
                    "message": "Refund processed successfully",
                    "refund_id": result["refund_id"],
                }
            else:
                return {
                    "success": False,
                    "message": result.get("error", "Refund failed"),
                }

        elif payment.gateway == Payment.PaymentGateway.MPESA:
            return {
                "success": False,
                "message": "M-Pesa refunds must be processed manually via the portal",
            }

        return {"success": False, "message": "Unsupported payment gateway"}
