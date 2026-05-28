from rest_framework import serializers
from apps.notifications.models import Notification
from apps.notifications.choices import NotificationType, NotificationCategory, NotificationPriority


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    
    class Meta:
        model = Notification
        fields = (
            'id', 'title', 'message', 'notification_type', 'category',
            'priority', 'read', 'read_at', 'created_at', 'reference_id'
        )
        read_only_fields = ('id', 'created_at', 'read_at')


class MarkNotificationReadSerializer(serializers.Serializer):
    """Serializer for marking notification as read"""
    notification_id = serializers.UUIDField(required=True)


class SendTestEmailSerializer(serializers.Serializer):
    """Serializer for testing email service"""
    to_email = serializers.EmailField(required=True)
    subject = serializers.CharField(required=True, max_length=200)
    message = serializers.CharField(required=True)


class SendTestSMSSerializer(serializers.Serializer):
    """Serializer for testing SMS service"""
    to_phone = serializers.CharField(required=True, max_length=15)
    message = serializers.CharField(required=True, max_length=160)
