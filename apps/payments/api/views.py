import json
import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.permissions import IsOrderOwnerOrAdmin
from apps.payments.api.serializers import (
    CapturePayPalPaymentSerializer,
    InitiateMpesaPaymentSerializer,
    InitiatePayPalPaymentSerializer,
    PaymentSerializer,
    RefundSerializer,
)
from apps.payments.models import Payment
from apps.payments.services import (
    MpesaPaymentService,
    PaymentService,
    PayPalPaymentService,
    RefundService,
)
from apps.payments.webhook_handlers import (
    MpesaWebhookHandler,
    PayPalWebhookHandler,
)

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Helper function to get client IP"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0]
    return request.META.get("REMOTE_ADDR")


class InitiateMpesaPaymentView(APIView):
    """Initiate M-Pesa STK Push payment"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Initiate M-Pesa payment for an order",
        request=InitiateMpesaPaymentSerializer,
        responses={200: PaymentSerializer()},
    )
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, user=request.user)

        serializer = InitiateMpesaPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MpesaPaymentService.initiate_payment(
            order=order,
            user=request.user,
            phone_number=serializer.validated_data["phone_number"],
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "payment": PaymentSerializer(result["payment"]).data,
                    "checkout_request_id": result.get("checkout_request_id"),
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class MpesaCallbackView(APIView):
    """M-Pesa webhook callback endpoint using webhook handler"""

    permission_classes = [permissions.AllowAny]
    parser_classes = []  # Disable DRF parsing to access raw body

    @extend_schema(
        description="M-Pesa callback endpoint (webhook)",
        request={
            "application/json": {
                "type": "object",
                "description": "M-Pesa callback payload",
            }
        },
        responses={200: None},
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        logger.info(f"M-Pesa callback received from IP: {client_ip}")

        # Get raw body and parse JSON
        raw_body = request.body
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse M-Pesa callback JSON: {str(e)}")
            return Response(
                {"ResultCode": 1, "ResultDesc": "Invalid JSON"},
                status=status.HTTP_200_OK,
            )

        handler = MpesaWebhookHandler()

        if not handler.validate_signature(
            request_data=data, client_ip=client_ip, raw_body=raw_body
        ):
            logger.error(
                f"M-Pesa webhook validation failed for IP: {client_ip}"
            )
            return Response(
                {"ResultCode": 1, "ResultDesc": "Invalid signature"},
                status=status.HTTP_200_OK,
            )

        result = handler.process_event(data)

        if result.get("success"):
            return Response(
                {
                    "ResultCode": 0,
                    "ResultDesc": result.get("result_desc", "Success"),
                }
            )
        else:
            return Response(
                {
                    "ResultCode": result.get("result_code", 1),
                    "ResultDesc": result.get("result_desc", "Failed"),
                },
                status=status.HTTP_200_OK,
            )


class QueryMpesaPaymentView(APIView):
    """Query M-Pesa payment status"""

    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]

    @extend_schema(
        description="Query M-Pesa payment status",
        responses={200: PaymentSerializer()},
    )
    def get(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id, request.user)
        result = MpesaPaymentService.query_payment_status(payment)

        return Response(
            {
                "payment": PaymentSerializer(payment).data,
                "query_result": result,
            }
        )


class InitiatePayPalPaymentView(APIView):
    """Initiate PayPal payment"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Initiate PayPal payment for an order",
        request=InitiatePayPalPaymentSerializer,
        responses={200: None},
    )
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, user=request.user)

        serializer = InitiatePayPalPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = PayPalPaymentService.initiate_payment(
            order=order,
            user=request.user,
            return_url=serializer.validated_data["return_url"],
            cancel_url=serializer.validated_data["cancel_url"],
        )

        if result["success"]:
            return Response(
                {
                    "approval_url": result["approval_url"],
                    "order_id": result["order_id"],
                    "payment_id": result["payment"].id,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CapturePayPalPaymentView(APIView):
    """Capture PayPal payment after approval"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Capture PayPal payment after user approval",
        request=CapturePayPalPaymentSerializer,
        responses={200: PaymentSerializer()},
    )
    def post(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id, request.user)

        serializer = CapturePayPalPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = PayPalPaymentService.capture_payment(
            payment=payment, payer_id=serializer.validated_data["payer_id"]
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "payment": PaymentSerializer(payment).data,
                    "capture_id": result["capture_id"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PayPalWebhookView(APIView):
    """PayPal webhook endpoint"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        description="PayPal webhook endpoint",
        request=None,
        responses={200: None},
    )
    def post(self, request):
        headers = {
            "PayPal-Transmission-Id": request.headers.get(
                "PayPal-Transmission-Id"
            ),
            "PayPal-Transmission-Time": request.headers.get(
                "PayPal-Transmission-Time"
            ),
            "PayPal-Cert-Url": request.headers.get("PayPal-Cert-Url"),
            "PayPal-Auth-Algo": request.headers.get("PayPal-Auth-Algo"),
            "PayPal-Transmission-Sig": request.headers.get(
                "PayPal-Transmission-Sig"
            ),
        }

        result = PayPalPaymentService.process_webhook(
            request.data, headers, request.body
        )

        if result.get("success"):
            return Response({"status": "received"}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": result.get("error", "Processing failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PaymentHistoryView(APIView):
    """Get user's payment history"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Get user's payment history",
        responses={200: PaymentSerializer(many=True)},
    )
    def get(self, request):
        payments = PaymentService.get_user_payments(request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)


class InitiateRefundView(APIView):
    """Initiate refund for a payment"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Initiate refund for a payment",
        request=RefundSerializer,
        responses={200: None},
    )
    def post(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id)

        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = RefundService.process_refund(
            payment=payment,
            amount=serializer.validated_data["amount"],
            reason=serializer.validated_data["reason"],
            user=request.user,
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "refund_id": result.get("refund_id"),
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
