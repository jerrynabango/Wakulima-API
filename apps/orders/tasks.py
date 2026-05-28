from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from apps.orders.models import Order

@shared_task
def send_order_confirmation_email(order_id):
    """Send order confirmation email asynchronously"""
    try:
        order = Order.objects.get(id=order_id)
        
        context = {
            'order': order,
            'items': order.items.all(),
            'total': order.total
        }
        
        html_message = render_to_string('orders/emails/order_confirmation.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'Order Confirmation - {order.order_number}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Order.DoesNotExist:
        pass

@shared_task
def send_order_status_update_email(order_id, old_status, new_status):
    """Send order status update email"""
    try:
        order = Order.objects.get(id=order_id)
        
        context = {
            'order': order,
            'old_status': old_status,
            'new_status': new_status,
            'tracking_number': order.tracking_number
        }
        
        html_message = render_to_string('orders/emails/order_status_update.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'Order Status Update - {order.order_number}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Order.DoesNotExist:
        pass
