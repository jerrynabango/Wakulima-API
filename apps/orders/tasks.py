import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.orders.models import Order

logger = logging.getLogger(__name__)


@shared_task
def send_order_confirmation_email(order_id):
    """Send order confirmation email asynchronously"""
    try:
        order = Order.objects.get(id=order_id)

        context = {
            "order": order,
            "items": order.items.all(),
            "total": order.total,
            "support_email": settings.SUPPORT_EMAIL
            or settings.DEFAULT_FROM_EMAIL,
            "frontend_url": settings.FRONTEND_URL,
            "year": timezone.now().year,
        }

        # CORRECTED: Use full path to your template
        # Your templates are in:
        # notifications/emails/orders/order_confirmation.html
        html_message = render_to_string(
            "notifications/emails/orders/order_confirmation.html", context
        )
        plain_message = strip_tags(html_message)

        result = send_mail(
            subject=f"Order Confirmation - {order.order_number}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        if result == 1:
            logger.info(f"Order confirmation email sent to {
                    order.user.email} for order {
                    order.order_number}")
        else:
            logger.warning(f"Order confirmation email may not have sent to {
                    order.user.email}")

        return result == 1

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return False
    except Exception as e:
        logger.error(f"Failed to send order confirmation email: {str(e)}")
        return False


@shared_task
def send_order_status_update_email(order_id, old_status, new_status):
    """Send order status update email"""
    try:
        order = Order.objects.get(id=order_id)

        context = {
            "order": order,
            "old_status": old_status,
            "new_status": new_status,
            "tracking_number": order.tracking_number,
            "support_email": settings.SUPPORT_EMAIL
            or settings.DEFAULT_FROM_EMAIL,
            "frontend_url": settings.FRONTEND_URL,
            "year": timezone.now().year,
        }

        # CORRECTED: Use full path to your template
        html_message = render_to_string(
            "notifications/emails/orders/order_status_update.html", context
        )
        plain_message = strip_tags(html_message)

        result = send_mail(
            subject=f"Order Status Update - {order.order_number}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        if result == 1:
            logger.info(f"Order status update email sent to {
                    order.user.email} for order {
                    order.order_number}")

        return result == 1

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return False
    except Exception as e:
        logger.error(f"Failed to send order status update email: {str(e)}")
        return False
