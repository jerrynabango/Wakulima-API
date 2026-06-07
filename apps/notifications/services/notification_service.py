import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.notifications.choices import (
    NotificationCategory,
    NotificationPriority,
    NotificationType,
)
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Main notification service that orchestrates email and SMS"""

    def __init__(self):
        self.from_email = settings.DEFAULT_FROM_EMAIL

    def send_notification(
        self,
        user,
        title,
        message,
        category,
        priority=NotificationPriority.NORMAL,
        send_email=True,
        send_sms=False,
        email_template_type=None,
        sms_template_type=None,
        reference_id=None,
        metadata=None,
    ):
        """
        Send notification to user via specified channels

        Returns: dict with results for each channel
        """
        results = {"email": None, "sms": None, "notification": None}

        # Create in-app notification
        notification = Notification.objects.create(
            user=user,
            notification_type=NotificationType.IN_APP,
            category=category,
            priority=priority,
            title=title,
            message=message,
            reference_id=reference_id,
            metadata=metadata or {},
        )
        results["notification"] = {"id": str(notification.id)}

        # Send email if requested
        if send_email and user.email:
            email_result = self._send_email_notification(
                user,
                title,
                message,
                email_template_type,
                reference_id,
                metadata,
                order_id=reference_id,
            )
            results["email"] = email_result
            if email_result.get("success"):
                logger.info(f"Email sent to {user.email} for {title}")
            else:
                logger.error(f"Failed to send email to {
                        user.email}: {
                        email_result.get('error')}")

        # Send SMS if requested
        if send_sms and user.phone_number:
            sms_result = self._send_sms_notification(
                user, message, sms_template_type, reference_id, metadata
            )
            results["sms"] = sms_result

        return results

    def _send_email_notification(
        self,
        user,
        subject,
        message,
        template_type,
        reference_id,
        metadata,
        order_id=None,
    ):
        """Send email notification directly via SMTP"""
        try:
            # Prepare context for template
            context = {
                "user": user,
                "title": subject,
                "message": message,
                "support_email": settings.SUPPORT_EMAIL
                or settings.DEFAULT_FROM_EMAIL,
                "frontend_url": settings.FRONTEND_URL,
                "year": timezone.now().year,
            }

            # If it's an order notification, add order details
            if order_id and template_type == "order_confirmation":
                from apps.orders.models import Order

                try:
                    order = Order.objects.get(id=order_id)
                    context["order"] = order
                    context["items"] = order.items.all()
                    context["order_url"] = f"{
                        settings.FRONTEND_URL}/orders/{
                        order.id}"
                except Order.DoesNotExist:
                    pass

            # Render email template
            template_path = (
                f"notifications/emails/{template_type}.html"
                if template_type
                else "notifications/emails/default.html"
            )

            try:
                html_message = render_to_string(template_path, context)
                plain_message = strip_tags(html_message)
            except Exception as e:
                logger.error(f"Template rendering failed: {str(e)}")
                # Fallback to plain message
                html_message = f"<h2>{subject}</h2><p>{message}</p>"
                plain_message = f"{subject}\n\n{message}"

            # Send email
            result = send_mail(
                subject=subject,
                message=plain_message,
                from_email=self.from_email,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            return {
                "success": result == 1,
                "message": (
                    "Email sent successfully"
                    if result == 1
                    else "Failed to send"
                ),
            }

        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
            return {"success": False, "error": str(e)}

    def _send_sms_notification(
        self, user, message, template_type, reference_id, metadata
    ):
        """Send SMS notification"""
        # Implement SMS if needed
        return {"success": False, "message": "SMS not configured"}

    def send_order_confirmation(self, order):
        """Send order confirmation notification"""
        user = order.user

        title = f"Order Confirmed - #{order.order_number}"
        message = f"Your order #{
            order.order_number} has been confirmed. Total: KES {
            order.total}"

        return self.send_notification(
            user=user,
            title=title,
            message=message,
            category=NotificationCategory.ORDER,
            priority=NotificationPriority.HIGH,
            send_email=True,
            email_template_type="order_confirmation",
            reference_id=str(order.id),
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "total": str(order.total),
            },
        )

    def send_payment_received(self, payment):
        """Send payment received notification"""
        user = payment.user
        order = payment.order

        title = f"Payment Received - Order #{order.order_number}"
        message = f"We've received your payment of KES {
            payment.amount} for order #{
            order.order_number}"

        return self.send_notification(
            user=user,
            title=title,
            message=message,
            category=NotificationCategory.PAYMENT,
            priority=NotificationPriority.HIGH,
            send_email=True,
            email_template_type="payment_received",
            reference_id=str(payment.id),
            metadata={
                "payment_id": str(payment.id),
                "order_id": str(order.id),
                "amount": str(payment.amount),
            },
        )

    def send_low_stock_alert(self, product, farmer):
        """Send low stock alert to farmer"""
        title = f"Low Stock Alert: {product.name}"
        message = f"Your product {
            product.name} is running low! Current stock: {
            product.quantity} {
            product.unit_type}"

        return self.send_notification(
            user=farmer,
            title=title,
            message=message,
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.URGENT,
            send_email=True,
            email_template_type="low_stock",
            reference_id=str(product.id),
            metadata={
                "product_id": str(product.id),
                "product_name": product.name,
                "quantity": str(product.quantity),
            },
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
            notification = Notification.objects.get(
                id=notification_id, user=user
            )
            notification.read = True
            notification.read_at = timezone.now()
            notification.save()
            return {"success": True}
        except Notification.DoesNotExist:
            return {"success": False, "error": "Notification not found"}

    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications as read for a user"""
        count = Notification.objects.filter(user=user, read=False).update(
            read=True, read_at=timezone.now()
        )
        return {"success": True, "count": count}

    @staticmethod
    def get_unread_count(user):
        """Get unread notification count for a user"""
        return Notification.objects.filter(user=user, read=False).count()
