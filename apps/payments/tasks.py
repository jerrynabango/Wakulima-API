from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from apps.payments.models import Payment, PaymentWebhook
from apps.payments.services.mpesa_service import MpesaService
from apps.payments.webhook_handlers import MpesaWebhookHandler, PayPalWebhookHandler
from apps.orders.models import Order
import logging

logger = logging.getLogger(__name__)

@shared_task
def check_pending_payments():
    """
    Check pending payments and update status
    Runs every 5 minutes via Celery beat
    """
    # Check M-Pesa payments older than 10 minutes
    pending_mpesa = Payment.objects.filter(
        gateway=Payment.PaymentGateway.MPESA,
        status=Payment.PaymentStatus.PROCESSING,
        created_at__lt=timezone.now() - timezone.timedelta(minutes=10)
    )
    
    mpesa_service = MpesaService()
    results = []
    
    for payment in pending_mpesa:
        try:
            # Check for duplicate queries (rate limiting)
            cache_key = f"mpesa_query_{payment.id}"
            if cache.get(cache_key):
                logger.info(f"Skipping duplicate query for payment {payment.id}")
                continue
            
            result = mpesa_service.query_status(payment)
            cache.set(cache_key, True, timeout=300)  # 5 minutes
            
            results.append({
                'payment_id': str(payment.id),
                'success': result.get('success', False),
                'status': payment.status
            })
            
            logger.info(f"Checked pending payment {payment.id}: {result}")
        except Exception as e:
            logger.error(f"Failed to check payment {payment.id}: {str(e)}")
            results.append({
                'payment_id': str(payment.id),
                'error': str(e)
            })
    
    # Also check PayPal pending payments (older than 30 minutes)
    pending_paypal = Payment.objects.filter(
        gateway=Payment.PaymentGateway.PAYPAL,
        status=Payment.PaymentStatus.PROCESSING,
        created_at__lt=timezone.now() - timezone.timedelta(minutes=30)
    )
    
    from apps.payments.services.paypal_service import PayPalService
    paypal_service = PayPalService()
    
    for payment in pending_paypal:
        try:
            cache_key = f"paypal_query_{payment.id}"
            if cache.get(cache_key):
                logger.info(f"Skipping duplicate PayPal query for payment {payment.id}")
                continue
            
            result = paypal_service.get_order_status(payment)
            cache.set(cache_key, True, timeout=300)
            
            # If order is completed but payment not updated
            if result.get('success') and result.get('status') == 'COMPLETED':
                if payment.status != Payment.PaymentStatus.SUCCESS:
                    payment.status = Payment.PaymentStatus.SUCCESS
                    payment.paid_at = timezone.now()
                    payment.save()
                    
                    # Update order
                    order = payment.order
                    order.payment_status = Order.PaymentStatus.PAID
                    order.paid_at = timezone.now()
                    order.save()
                    
                    logger.info(f"Updated PayPal payment {payment.id} to SUCCESS via scheduled task")
            
            results.append({
                'payment_id': str(payment.id),
                'success': True,
                'status': payment.status
            })
        except Exception as e:
            logger.error(f"Failed to check PayPal payment {payment.id}: {str(e)}")
            results.append({
                'payment_id': str(payment.id),
                'error': str(e)
            })
    
    return {
        'checked_mpesa': pending_mpesa.count(),
        'checked_paypal': pending_paypal.count(),
        'results': results
    }


@shared_task
def process_unprocessed_webhooks():
    """
    Process unprocessed webhook events
    This is a fallback in case real-time processing failed
    """
    # Get unprocessed webhooks older than 5 minutes
    webhooks = PaymentWebhook.objects.filter(
        processed=False, 
        created_at__lt=timezone.now() - timezone.timedelta(minutes=5)
    )
    
    processed_count = 0
    failed_count = 0
    
    for webhook in webhooks:
        try:
            if webhook.gateway == Payment.PaymentGateway.MPESA:
                # Use webhook handler instead of service
                handler = MpesaWebhookHandler()
                result = handler.process_event(webhook.payload)
                
                if result.get('success'):
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.save()
                    processed_count += 1
                    logger.info(f"Processed M-Pesa webhook {webhook.id}")
                else:
                    webhook.error_message = result.get('error', 'Unknown error')
                    webhook.save()
                    failed_count += 1
                    logger.error(f"Failed to process M-Pesa webhook {webhook.id}: {result.get('error')}")
                    
            elif webhook.gateway == Payment.PaymentGateway.PAYPAL:
                # Use webhook handler
                handler = PayPalWebhookHandler()
                result = handler.process_event(webhook.payload)
                
                if result.get('success'):
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.save()
                    processed_count += 1
                    logger.info(f"Processed PayPal webhook {webhook.id}")
                else:
                    webhook.error_message = result.get('error', 'Unknown error')
                    webhook.save()
                    failed_count += 1
                    logger.error(f"Failed to process PayPal webhook {webhook.id}: {result.get('error')}")
                    
        except Exception as e:
            logger.error(f"Failed to process webhook {webhook.id}: {str(e)}")
            webhook.error_message = str(e)
            webhook.save()
            failed_count += 1
    
    return {
        'processed': processed_count,
        'failed': failed_count,
        'total': webhooks.count()
    }


@shared_task
def cleanup_old_webhooks():
    """
    Delete webhooks older than 30 days to keep database clean
    Runs weekly
    """
    cutoff_date = timezone.now() - timezone.timedelta(days=30)
    deleted_count = PaymentWebhook.objects.filter(
        created_at__lt=cutoff_date,
        processed=True
    ).delete()[0]
    
    # Also delete old pending payments (older than 7 days)
    old_payments = Payment.objects.filter(
        status__in=[Payment.PaymentStatus.PENDING, Payment.PaymentStatus.PROCESSING],
        created_at__lt=timezone.now() - timezone.timedelta(days=7)
    ).delete()[0]
    
    logger.info(f"Cleaned up {deleted_count} old webhooks and {old_payments} old pending payments")
    
    return {
        'deleted_webhooks': deleted_count,
        'deleted_pending_payments': old_payments
    }


@shared_task
def retry_failed_webhooks():
    """
    Retry failed webhooks that might have been processed later
    """
    # Get failed webhooks from last hour
    failed_webhooks = PaymentWebhook.objects.filter(
        processed=False,
        error_message__isnull=False,
        created_at__gt=timezone.now() - timezone.timedelta(hours=1)
    )
    
    retried = 0
    success = 0
    
    for webhook in failed_webhooks:
        try:
            if webhook.gateway == Payment.PaymentGateway.MPESA:
                handler = MpesaWebhookHandler()
                result = handler.process_event(webhook.payload)
                
                if result.get('success'):
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.error_message = ''
                    webhook.save()
                    success += 1
                    
            elif webhook.gateway == Payment.PaymentGateway.PAYPAL:
                handler = PayPalWebhookHandler()
                result = handler.process_event(webhook.payload)
                
                if result.get('success'):
                    webhook.processed = True
                    webhook.processed_at = timezone.now()
                    webhook.error_message = ''
                    webhook.save()
                    success += 1
                    
            retried += 1
            
        except Exception as e:
            logger.error(f"Failed to retry webhook {webhook.id}: {str(e)}")
    
    return {
        'retried': retried,
        'successful': success,
        'failed': retried - success
    }
