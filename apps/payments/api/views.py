from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.payments.models import Payment
from apps.payments.api.serializers import (
    PaymentSerializer, InitiateMpesaPaymentSerializer,
    InitiatePayPalPaymentSerializer, CapturePayPalPaymentSerializer,
    RefundSerializer
)
from apps.payments.services import PaymentService, MpesaPaymentService, PayPalPaymentService, RefundService
from apps.orders.models import Order
from apps.orders.permissions import IsOrderOwnerOrAdmin
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Helper function to get client IP"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


class InitiateMpesaPaymentView(APIView):
    """Initiate M-Pesa STK Push payment"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Initiate M-Pesa payment for an order",
        request_body=InitiateMpesaPaymentSerializer,
        responses={200: PaymentSerializer()}
    )
    def post(self, request, order_id):
        # Get order
        order = get_object_or_404(Order, id=order_id, user=request.user)
        
        # Validate request
        serializer = InitiateMpesaPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Process payment via service
        result = MpesaPaymentService.initiate_payment(
            order=order,
            user=request.user,
            phone_number=serializer.validated_data['phone_number']
        )
        
        if result['success']:
            return Response({
                'message': result['message'],
                'payment': PaymentSerializer(result['payment']).data,
                'checkout_request_id': result.get('checkout_request_id')
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class MpesaCallbackView(APIView):
    """M-Pesa webhook callback endpoint"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="M-Pesa callback endpoint (webhook)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description="M-Pesa callback payload"
        ),
        responses={200: 'OK'}
    )
    def post(self, request):
        client_ip = get_client_ip(request)
        
        result = MpesaPaymentService.process_webhook(request.data, client_ip)
        
        return Response(
            {'ResultCode': result['result_code'], 'ResultDesc': result['result_desc']},
            status=status.HTTP_200_OK
        )


class QueryMpesaPaymentView(APIView):
    """Query M-Pesa payment status"""
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Query M-Pesa payment status",
        responses={200: PaymentSerializer()}
    )
    def get(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id, request.user)
        result = MpesaPaymentService.query_payment_status(payment)
        
        return Response({
            'payment': PaymentSerializer(payment).data,
            'query_result': result
        })


class InitiatePayPalPaymentView(APIView):
    """Initiate PayPal payment"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Initiate PayPal payment for an order",
        request_body=InitiatePayPalPaymentSerializer,
        responses={200: 'Payment URL'}
    )
    def post(self, request, order_id):
        # Get order
        order = get_object_or_404(Order, id=order_id, user=request.user)
        
        # Validate request
        serializer = InitiatePayPalPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Process payment via service
        result = PayPalPaymentService.initiate_payment(
            order=order,
            user=request.user,
            return_url=serializer.validated_data['return_url'],
            cancel_url=serializer.validated_data['cancel_url']
        )
        
        if result['success']:
            return Response({
                'approval_url': result['approval_url'],
                'order_id': result['order_id'],
                'payment_id': result['payment'].id
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class CapturePayPalPaymentView(APIView):
    """Capture PayPal payment after approval"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Capture PayPal payment after user approval",
        request_body=CapturePayPalPaymentSerializer,
        responses={200: PaymentSerializer()}
    )
    def post(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id, request.user)
        
        serializer = CapturePayPalPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = PayPalPaymentService.capture_payment(
            payment=payment,
            payer_id=serializer.validated_data['payer_id']
        )
        
        if result['success']:
            return Response({
                'message': result['message'],
                'payment': PaymentSerializer(payment).data,
                'capture_id': result['capture_id']
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class PayPalWebhookView(APIView):
    """PayPal webhook endpoint"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Get headers for signature validation
        headers = {
            'PayPal-Transmission-Id': request.headers.get('PayPal-Transmission-Id'),
            'PayPal-Transmission-Time': request.headers.get('PayPal-Transmission-Time'),
            'PayPal-Cert-Url': request.headers.get('PayPal-Cert-Url'),
            'PayPal-Auth-Algo': request.headers.get('PayPal-Auth-Algo'),
            'PayPal-Transmission-Sig': request.headers.get('PayPal-Transmission-Sig'),
        }
        
        result = PayPalPaymentService.process_webhook(request.data, headers, request.body)
        
        if result.get('success'):
            return Response({'status': 'received'}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result.get('error', 'Processing failed')},
                status=status.HTTP_400_BAD_REQUEST
            )


class PaymentHistoryView(APIView):
    """Get user's payment history"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get user's payment history",
        responses={200: PaymentSerializer(many=True)}
    )
    def get(self, request):
        payments = PaymentService.get_user_payments(request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)


class InitiateRefundView(APIView):
    """Initiate refund for a payment"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Initiate refund for a payment",
        request_body=RefundSerializer,
        responses={200: 'Refund initiated'}
    )
    def post(self, request, payment_id):
        payment = PaymentService.get_payment(payment_id)
        
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = RefundService.process_refund(
            payment=payment,
            amount=serializer.validated_data['amount'],
            reason=serializer.validated_data['reason'],
            user=request.user
        )
        
        if result['success']:
            return Response({
                'message': result['message'],
                'refund_id': result.get('refund_id')
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
