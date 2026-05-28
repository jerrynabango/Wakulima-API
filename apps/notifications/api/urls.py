from django.urls import path
from apps.notifications.api.views import (
    NotificationListView, UnreadCountView, MarkNotificationReadView,
    MarkAllReadView, TestEmailView, TestSMSView
)

urlpatterns = [
    # User notifications
    path('notifications/', NotificationListView.as_view(), name='notification-list'),
    path('notifications/unread-count/', UnreadCountView.as_view(), name='notification-unread-count'),
    path('notifications/mark-read/', MarkNotificationReadView.as_view(), name='notification-mark-read'),
    path('notifications/mark-all-read/', MarkAllReadView.as_view(), name='notification-mark-all-read'),
    
    # Test endpoints (admin only)
    path('notifications/test-email/', TestEmailView.as_view(), name='test-email'),
    path('notifications/test-sms/', TestSMSView.as_view(), name='test-sms'),
]
