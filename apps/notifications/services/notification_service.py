import logging
from django.conf import settings
from django.utils import timezone
from apps.notifications.models import Notification
from apps.notifications.choices import NotificationType, NotificationCategory, NotificationPriority
from .email_service import SendGridEmailService
from .sms_service import AfricaTalkingSMSService

logger = logging.getLogger(__name__)

class NotificationService:
    """Main notification service that orchestrates email and SMS"""
    
    def __init__(self):
        self.email_service = SendGridEmailService()
        self.sms_service = AfricaTalkingSMSService()
    
    def send_notification(self, user, title, message, category, priority=NotificationPriority.NORMAL, 
                          send_email=True, send_sms=False, email_template_type=None, 
                          sms_template_type=None, reference_id=None, metadata=None):
        """
        Send notification to user via specified channels
        
        Returns: dict with results for each channel
        """
        results = {'email': None, 'sms': None, 'notification': None}
        
        # Create in-app notification
        notification = Notification.objects.create(
            user=user,
            notification_type=NotificationType.IN_APP,
            category=category,
            priority=priority,
            title=title,
            message=message,
            reference_id=reference_id,
            metadata=metadata or {}
        )
        results['notification'] = {'id': str(notification.id)}
        
        # Send email if requested
        if send_email and user.email:
            email_result = self._send_email_notification(
                user, title, message, email_template_type, reference_id, metadata
            )
            results['email'] = email_result
        
        # Send SMS if requested
        if send_sms and user.phone_number:
            sms_result = self._send_sms_notification(
                user, message, sms_template_type, reference_id, metadata
            )
            results['sms'] = sms_result
        
        return results
    
    def _send_email_notification(self, user, subject, message, template_type, reference_id, metadata):
        """Send email notification"""
        if not template_type:
            # Use a generic template
            context = {
                'user': user,
                'title': subject,
                'message': message,
                'support_email': settings.SUPPORT_EMAIL or '',
                'year': timezone.now().year
            }
            template_type = 'generic'
        
        result = self.email_service.send_email(
            to_email=user.email,
            subject=subject,
            template_type=template_type,
            context=metadata or {'user': user, 'message': message}
        )
        
        return result
    
    def _send_sms_notification(self, user, message, template_type, reference_id, metadata):
        """Send SMS notification"""
        result = self.sms_service.send_sms(
            to_phone=user.phone_number,
            message=message[:160],  # SMS length limit
            template_type=template_type or 'generic',
            reference_id=reference_id,
            metadata=metadata
        )
        
        return result
    
    def send_order_confirmation(self, order):
        """Send order confirmation notification"""
        user = order.user
        
        title = f"Order Confirmed - #{order.order_number}"
        message = f"Your order #{order.order_number} has been confirmed. Total: KES {order.total}"
        
        return self.send_notification(
            user=user,
            title=title,
            message=message,
            category=NotificationCategory.ORDER,
            priority=NotificationPriority.HIGH,
            send_email=True,
            send_sms=True if user.phone_number else False,
            email_template_type='order_confirmation',
            sms_template_type='order_confirmation',
            reference_id=str(order.id),
            metadata={'order_id': str(order.id), 'order_number': order.order_number, 'total': str(order.total)}
        )
    
    def send_payment_received(self, payment):
        """Send payment received notification"""
        user = payment.user
        order = payment.order
        
        title = f"Payment Received - Order #{order.order_number}"
        message = f"We've received your payment of KES {payment.amount} for order #{order.order_number}"
        
        return self.send_notification(
            user=user,
            title=title,
            message=message,
            category=NotificationCategory.PAYMENT,
            priority=NotificationPriority.HIGH,
            send_email=True,
            send_sms=True if user.phone_number else False,
            email_template_type='payment_received',
            sms_template_type='payment_received',
            reference_id=str(payment.id),
            metadata={'payment_id': str(payment.id), 'order_id': str(order.id), 'amount': str(payment.amount)}
        )
    
    def send_order_shipped(self, order):
        """Send order shipped notification"""
        user = order.user
        
        title = f"Order Shipped - #{order.order_number}"
        message = f"Your order #{order.order_number} has been shipped! Tracking: {order.tracking_number or 'will be updated soon'}"
        
        return self.send_notification(
            user=user,
            title=title,
            message=message,
            category=NotificationCategory.ORDER,
            priority=NotificationPriority.HIGH,
            send_email=True,
            send_sms=True if user.phone_number else False,
            email_template_type='order_shipped',
            sms_template_type='order_shipped',
            reference_id=str(order.id),
            metadata={'order_id': str(order.id), 'tracking_number': order.tracking_number}
        )
    
    def send_low_stock_alert(self, product, farmer):
        """Send low stock alert to farmer"""
        title = f"Low Stock Alert: {product.name}"
        message = f"Your product {product.name} is running low! Current stock: {product.quantity} {product.unit_type}"
        
        return self.send_notification(
            user=farmer,
            title=title,
            message=message,
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.URGENT,
            send_email=True,
            send_sms=True if farmer.phone_number else False,
            email_template_type='low_stock',
            sms_template_type='low_stock',
            reference_id=str(product.id),
            metadata={'product_id': str(product.id), 'product_name': product.name, 'quantity': str(product.quantity)}
        )


class InAppNotificationService:
    """Service for in-app notifications (read/unread tracking)"""
    
    @staticmethod
    def get_user_notifications(user, limit=50, unread_only=False):
        """Get notifications for a user"""
        queryset = Notification.objects.filter(user=user)
        
        if unread_only:
            queryset = queryset.filter(read=False)
        
        return queryset[:limit]
    
    @staticmethod
    def mark_as_read(notification_id, user):
        """Mark a notification as read"""
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.mark_as_read()
            return {'success': True}
        except Notification.DoesNotExist:
            return {'success': False, 'error': 'Notification not found'}
    
    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications as read for a user"""
        count = Notification.objects.filter(user=user, read=False).update(
            read=True,
            read_at=timezone.now()
        )
        return {'success': True, 'count': count}
    
    @staticmethod
    def get_unread_count(user):
        """Get unread notification count for a user"""
        return Notification.objects.filter(user=user, read=False).count()
