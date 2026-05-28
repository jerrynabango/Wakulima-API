from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.notifications.models import Notification
from apps.notifications.api.serializers import (
    NotificationSerializer, MarkNotificationReadSerializer,
    SendTestEmailSerializer, SendTestSMSSerializer
)
from apps.notifications.services import (
    NotificationService, InAppNotificationService,
    SendGridEmailService, AfricaTalkingSMSService
)
import logging

logger = logging.getLogger(__name__)


class NotificationListView(generics.ListAPIView):
    """List user's notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        unread_only = self.request.query_params.get('unread_only', 'false').lower() == 'true'
        return InAppNotificationService.get_user_notifications(
            self.request.user,
            unread_only=unread_only
        )


class UnreadCountView(APIView):
    """Get unread notification count"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get unread notification count",
        responses={200: openapi.Response('Count', schema=openapi.Schema(type=openapi.TYPE_INTEGER))}
    )
    def get(self, request):
        count = InAppNotificationService.get_unread_count(request.user)
        return Response({'unread_count': count})


class MarkNotificationReadView(APIView):
    """Mark a notification as read"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Mark notification as read",
        request_body=MarkNotificationReadSerializer,
        responses={200: 'Marked as read'}
    )
    def post(self, request):
        serializer = MarkNotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = InAppNotificationService.mark_as_read(
            serializer.validated_data['notification_id'],
            request.user
        )
        
        if result['success']:
            return Response({'message': 'Notification marked as read'})
        else:
            return Response(
                {'error': result.get('error', 'Failed to mark as read')},
                status=status.HTTP_404_NOT_FOUND
            )


class MarkAllReadView(APIView):
    """Mark all notifications as read"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Mark all notifications as read",
        responses={200: 'All marked as read'}
    )
    def post(self, request):
        result = InAppNotificationService.mark_all_as_read(request.user)
        return Response({'message': f"{result['count']} notifications marked as read"})


class TestEmailView(APIView):
    """Test email service (admin only)"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Test email service (admin only)",
        request_body=SendTestEmailSerializer,
        responses={200: 'Email sent'}
    )
    def post(self, request):
        if not request.user.is_admin_user:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SendTestEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email_service = SendGridEmailService()
        result = email_service.send_email(
            to_email=serializer.validated_data['to_email'],
            subject=serializer.validated_data['subject'],
            template_type='test',
            context={'message': serializer.validated_data['message']}
        )
        
        if result['success']:
            return Response({'message': 'Test email sent', 'message_id': result.get('message_id')})
        else:
            return Response(
                {'error': result.get('error', 'Failed to send email')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TestSMSView(APIView):
    """Test SMS service (admin only)"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Test SMS service (admin only)",
        request_body=SendTestSMSSerializer,
        responses={200: 'SMS sent'}
    )
    def post(self, request):
        if not request.user.is_admin_user:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SendTestSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        sms_service = AfricaTalkingSMSService()
        result = sms_service.send_sms(
            to_phone=serializer.validated_data['to_phone'],
            message=serializer.validated_data['message'],
            template_type='test'
        )
        
        if result['success']:
            return Response({'message': 'Test SMS sent', 'message_id': result.get('message_id')})
        else:
            return Response(
                {'error': result.get('error', 'Failed to send SMS')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
