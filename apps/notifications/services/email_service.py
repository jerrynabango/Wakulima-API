import logging
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment
import base64
from apps.notifications.models import EmailLog
from apps.notifications.choices import EmailTemplateType

logger = logging.getLogger(__name__)

class SendGridEmailService:
    """Email service using SendGrid API (free tier - 100 emails/day)"""
    
    def __init__(self):
        # All values must come from .env - no hardcoded defaults
        self.api_key = settings.SENDGRID_API_KEY
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.from_name = settings.EMAIL_FROM_NAME
        
        # Validate configuration
        if not self.api_key:
            logger.error("SENDGRID_API_KEY not set in .env file")
        if not self.from_email:
            logger.error("DEFAULT_FROM_EMAIL not set in .env file")
        if not self.from_name:
            logger.warning("EMAIL_FROM_NAME not set in .env file - using default")
            self.from_name = "Wakulima"
        
        if self.api_key and self.from_email:
            self.client = SendGridAPIClient(self.api_key)
        else:
            logger.warning("SendGrid not configured - check SENDGRID_API_KEY and DEFAULT_FROM_EMAIL in .env")
            self.client = None
    
    def send_email(self, to_email, subject, template_type, context, from_email=None, attachments=None):
        """
        Send email using SendGrid
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            template_type: Type of email template (from EmailTemplateType)
            context: Dictionary of template variables
            from_email: Sender email (optional)
            attachments: List of file attachments (optional)
        
        Returns:
            dict: {'success': bool, 'message_id': str, 'error': str}
        """
        if not self.client:
            return {
                'success': False,
                'error': 'Email service not configured. Please check SENDGRID_API_KEY and DEFAULT_FROM_EMAIL in .env'
            }
        
        if not self.from_email:
            return {
                'success': False,
                'error': 'DEFAULT_FROM_EMAIL not configured in .env file'
            }
        
        try:
            # Render email templates
            html_content = self._render_template(template_type, context, html=True)
            plain_text_content = self._render_template(template_type, context, html=False)
            
            # Create email message
            from_email_addr = from_email or self.from_email
            message = Mail(
                from_email=Email(from_email_addr, self.from_name),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", plain_text_content)
            )
            
            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    encoded_file = base64.b64encode(attachment['content']).decode()
                    attached_file = Attachment(
                        file_content=encoded_file,
                        file_type=attachment['content_type'],
                        file_name=attachment['filename'],
                        disposition='attachment'
                    )
                    message.add_attachment(attached_file)
            
            # Send email
            response = self.client.send(message)
            
            # Log the email
            email_log = EmailLog.objects.create(
                to_email=to_email,
                from_email=from_email_addr,
                subject=subject,
                template_type=template_type,
                html_content=html_content,
                plain_text_content=plain_text_content,
                status='sent' if response.status_code == 202 else 'failed',
                sendgrid_message_id=response.headers.get('X-Message-Id', ''),
                metadata=context
            )
            
            logger.info(f"Email sent to {to_email} from {from_email_addr} - Template: {template_type}")
            
            return {
                'success': response.status_code == 202,
                'message_id': response.headers.get('X-Message-Id', ''),
                'log_id': str(email_log.id)
            }
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            
            # Log failed email
            EmailLog.objects.create(
                to_email=to_email,
                from_email=from_email or self.from_email,
                subject=subject,
                template_type=template_type,
                status='failed',
                error_message=str(e),
                metadata=context
            )
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def _render_template(self, template_type, context, html=True):
        """Render email template with context"""
        template_map = {
            EmailTemplateType.WELCOME: 'welcome.html',
            EmailTemplateType.ORDER_CONFIRMATION: 'orders/order_confirmation.html',
            EmailTemplateType.ORDER_SHIPPED: 'orders/order_shipped.html',
            EmailTemplateType.ORDER_DELIVERED: 'orders/order_delivered.html',
            EmailTemplateType.ORDER_CANCELLED: 'orders/order_cancelled.html',
            EmailTemplateType.PAYMENT_RECEIVED: 'orders/payment_received.html',
            EmailTemplateType.PAYMENT_FAILED: 'orders/payment_failed.html',
            EmailTemplateType.PASSWORD_RESET: 'auth/password_reset.html',
            EmailTemplateType.EMAIL_VERIFICATION: 'auth/email_verification.html',
            EmailTemplateType.LOW_STOCK: 'farmer/low_stock.html',
            EmailTemplateType.FARMER_WELCOME: 'farmer/welcome.html',
            EmailTemplateType.REFUND_PROCESSED: 'orders/refund_processed.html',
        }
        
        template_name = template_map.get(template_type, 'default.html')
        template_path = f'notifications/emails/{template_name}'
        
        # Add support email from settings (must be set in .env)
        if 'support_email' not in context:
            context['support_email'] = settings.SUPPORT_EMAIL or ''
        
        if 'year' not in context:
            context['year'] = timezone.now().year
        
        try:
            if html:
                return render_to_string(template_path, context)
            else:
                html_content = render_to_string(template_path, context)
                return strip_tags(html_content)
        except Exception as e:
            logger.error(f"Failed to render template {template_path}: {str(e)}")
            return f"Email template not found: {template_type}"
    
    def send_bulk_emails(self, recipients, subject, template_type, context_func):
        """
        Send bulk emails to multiple recipients
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            template_type: Type of email template
            context_func: Function that takes email and returns context dict
        """
        results = []
        
        for recipient in recipients:
            context = context_func(recipient) if callable(context_func) else context_func
            result = self.send_email(recipient, subject, template_type, context)
            results.append(result)
        
        return {
            'total': len(recipients),
            'successful': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success']),
            'results': results
        }


class EmailTemplateService:
    """Service for managing email templates"""
    
    @staticmethod
    def get_welcome_context(user):
        """Context for welcome email"""
        return {
            'user': user,
            'login_url': f"{settings.FRONTEND_URL}/login",
            'support_email': settings.SUPPORT_EMAIL or '',
            'year': timezone.now().year
        }
    
    @staticmethod
    def get_order_confirmation_context(order):
        """Context for order confirmation email"""
        return {
            'order': order,
            'items': order.items.all(),
            'order_url': f"{settings.FRONTEND_URL}/orders/{order.id}",
            'support_email': settings.SUPPORT_EMAIL or '',
            'year': timezone.now().year
        }
    
    @staticmethod
    def get_payment_received_context(payment):
        """Context for payment received email"""
        return {
            'payment': payment,
            'order': payment.order,
            'payment_url': f"{settings.FRONTEND_URL}/payments/{payment.id}",
            'support_email': settings.SUPPORT_EMAIL or '',
            'year': timezone.now().year
        }
