import logging

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.api.serializers import (
    MarkNotificationReadSerializer,
    NotificationSerializer,
    SendTestEmailSerializer,
    SendTestSMSSerializer,
)
from apps.notifications.models import Notification
from apps.notifications.services import (
    AfricaTalkingSMSService,
    EmailService,
    InAppNotificationService,
    NotificationService,
)

logger = logging.getLogger(__name__)


# ========== Helper function for Swagger ==========
def is_swagger_request(view):
    """Check if the request is for Swagger schema generation"""
    return getattr(view, "swagger_fake_view", False)


class NotificationListView(generics.ListAPIView):
    """List user's notifications"""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="List user's notifications",
        parameters=[
            OpenApiParameter(
                name="unread_only",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter to show only unread notifications (true/false)",
                required=False,
            ),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Notification.objects.none()

        unread_only = (
            self.request.query_params.get("unread_only", "false").lower()
            == "true"
        )
        return InAppNotificationService.get_user_notifications(
            self.request.user, unread_only=unread_only
        )


class UnreadCountView(APIView):
    """Get unread notification count"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Get unread notification count",
        responses={200: None},
    )
    def get(self, request):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Response({"unread_count": 0})

        count = InAppNotificationService.get_unread_count(request.user)
        return Response({"unread_count": count})


class MarkNotificationReadView(APIView):
    """Mark a notification as read"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Mark a notification as read",
        request=MarkNotificationReadSerializer,
        responses={200: None},
    )
    def post(self, request):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Response({"message": "Notification marked as read (mock)"})

        serializer = MarkNotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = InAppNotificationService.mark_as_read(
            serializer.validated_data["notification_id"], request.user
        )

        if result["success"]:
            return Response({"message": "Notification marked as read"})
        else:
            return Response(
                {"error": result.get("error", "Failed to mark as read")},
                status=status.HTTP_404_NOT_FOUND,
            )


class MarkAllReadView(APIView):
    """Mark all notifications as read"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Mark all notifications as read",
        responses={200: None},
    )
    def post(self, request):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Response(
                {"message": "0 notifications marked as read (mock)"}
            )

        result = InAppNotificationService.mark_all_as_read(request.user)
        return Response(
            {"message": f"{result['count']} notifications marked as read"}
        )


class TestEmailView(APIView):
    """Test email service (admin only)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Test email service (admin only)",
        request=SendTestEmailSerializer,
        responses={200: None},
    )
    def post(self, request):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Response({"message": "Test email sent (mock)"})

        if not request.user.is_admin_user:
            return Response(
                {"error": "Admin access required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SendTestEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email_service = EmailService()
        result = email_service.send_email(
            to_email=serializer.validated_data["to_email"],
            subject=serializer.validated_data["subject"],
            template_type="test",
            context={"message": serializer.validated_data["message"]},
        )

        if result["success"]:
            return Response({"message": "Test email sent"})
        else:
            return Response(
                {"error": result.get("error", "Failed to send email")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TestSMSView(APIView):
    """Test SMS service (admin only)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Test SMS service (admin only)",
        request=SendTestSMSSerializer,
        responses={200: None},
    )
    def post(self, request):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Response({"message": "Test SMS sent (mock)"})

        if not request.user.is_admin_user:
            return Response(
                {"error": "Admin access required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SendTestSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sms_service = AfricaTalkingSMSService()
        result = sms_service.send_sms(
            to_phone=serializer.validated_data["to_phone"],
            message=serializer.validated_data["message"],
            template_type="test",
        )

        if result["success"]:
            return Response({"message": "Test SMS sent"})
        else:
            return Response(
                {"error": result.get("error", "Failed to send SMS")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
