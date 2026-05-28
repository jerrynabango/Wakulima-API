from celery import shared_task
from django.utils import timezone
from apps.notifications.models import Notification, EmailLog, SMSLog
from apps.notifications.services import NotificationService, SendGridEmailService, AfricaTalkingSMSService
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_order_confirmation_notification(order_id):
    """Send order confirmation notification asynchronously"""
    from apps.orders.models import Order
    
    try:
        order = Order.objects.get(id=order_id)
        notification_service = NotificationService()
        result = notification_service.send_order_confirmation(order)
        
        logger.info(f"Order confirmation notification sent for order {order_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to send order confirmation for order {order_id}: {str(e)}")
        return {'error': str(e)}


@shared_task
def send_payment_received_notification(payment_id):
    """Send payment received notification asynchronously"""
    from apps.payments.models import Payment
    
    try:
        payment = Payment.objects.get(id=payment_id)
        notification_service = NotificationService()
        result = notification_service.send_payment_received(payment)
        
        logger.info(f"Payment received notification sent for payment {payment_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to send payment notification for payment {payment_id}: {str(e)}")
        return {'error': str(e)}


@shared_task
def send_low_stock_alert(product_id, farmer_id):
    """Send low stock alert to farmer asynchronously"""
    from apps.products.models import Product
    from apps.accounts.models import User
    
    try:
        product = Product.objects.get(id=product_id)
        farmer = User.objects.get(id=farmer_id)
        
        notification_service = NotificationService()
        result = notification_service.send_low_stock_alert(product, farmer)
        
        logger.info(f"Low stock alert sent for product {product_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to send low stock alert: {str(e)}")
        return {'error': str(e)}


@shared_task
def retry_failed_notifications():
    """Retry failed notifications"""
    # Retry failed emails from the last hour
    failed_emails = EmailLog.objects.filter(
        status='failed',
        created_at__gt=timezone.now() - timezone.timedelta(hours=1)
    )
    
    email_service = SendGridEmailService()
    retried = 0
    success = 0
    
    for email in failed_emails:
        result = email_service.send_email(
            to_email=email.to_email,
            subject=email.subject,
            template_type=email.template_type,
            context=email.metadata
        )
        
        if result['success']:
            email.status = 'sent'
            email.error_message = ''
            email.save()
            success += 1
        
        retried += 1
    
    # Retry failed SMS
    failed_sms = SMSLog.objects.filter(
        status='failed',
        sent_at__gt=timezone.now() - timezone.timedelta(hours=1)
    )
    
    sms_service = AfricaTalkingSMSService()
    sms_retried = 0
    sms_success = 0
    
    for sms in failed_sms:
        result = sms_service.send_sms(
            to_phone=sms.to_phone,
            message=sms.message,
            template_type=sms.template_type,
            reference_id=sms.reference_id,
            metadata=sms.metadata
        )
        
        if result['success']:
            sms.status = 'sent'
            sms.error_message = ''
            sms.save()
            sms_success += 1
        
        sms_retried += 1
    
    return {
        'email_retried': retried,
        'email_success': success,
        'sms_retried': sms_retried,
        'sms_success': sms_success
    }


@shared_task
def cleanup_old_notifications():
    """Delete notifications older than 90 days"""
    cutoff_date = timezone.now() - timezone.timedelta(days=90)
    
    deleted_notifications = Notification.objects.filter(
        created_at__lt=cutoff_date,
        read=True
    ).delete()[0]
    
    deleted_emails = EmailLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()[0]
    
    deleted_sms = SMSLog.objects.filter(
        sent_at__lt=cutoff_date
    ).delete()[0]
    
    logger.info(f"Cleaned up: {deleted_notifications} notifications, {deleted_emails} emails, {deleted_sms} SMS")
    
    return {
        'deleted_notifications': deleted_notifications,
        'deleted_emails': deleted_emails,
        'deleted_sms': deleted_sms
    }
