import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.notifications.choices import EmailTemplateType
from apps.notifications.models import EmailLog

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using Django's SMTP (configured in settings)"""

    def __init__(self):
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.from_name = settings.EMAIL_FROM_NAME

        if not self.from_email:
            logger.error("DEFAULT_FROM_EMAIL not set in .env file")

    def send_email(
        self,
        to_email,
        subject,
        template_type,
        context,
        from_email=None,
        attachments=None,
    ):
        """
        Send email using Django's SMTP

        Returns:
            dict: {'success': bool, 'message_id': str, 'error': str}
        """
        if not self.from_email:
            return {
                "success": False,
                "error": "DEFAULT_FROM_EMAIL not configured in .env file",
            }

        try:
            # Render email templates
            html_content = self._render_template(
                template_type, context, html=True
            )
            plain_text_content = self._render_template(
                template_type, context, html=False
            )

            # Send email via SMTP
            result = send_mail(
                subject=subject,
                message=plain_text_content,
                from_email=from_email or self.from_email,
                recipient_list=[to_email],
                html_message=html_content,
                fail_silently=False,
            )

            # Log the email
            email_log = EmailLog.objects.create(
                to_email=to_email,
                from_email=from_email or self.from_email,
                subject=subject,
                template_type=template_type,
                html_content=html_content,
                plain_text_content=plain_text_content,
                status="sent" if result == 1 else "failed",
                metadata=context,
            )

            logger.info(f"Email sent to {to_email} from {
                    self.from_email} - Template: {template_type}")

            return {"success": result == 1, "log_id": str(email_log.id)}

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")

            # Log failed email
            EmailLog.objects.create(
                to_email=to_email,
                from_email=from_email or self.from_email,
                subject=subject,
                template_type=template_type,
                status="failed",
                error_message=str(e),
                metadata=context,
            )

            return {"success": False, "error": str(e)}

    def _render_template(self, template_type, context, html=True):
        """Render email template with context"""
        template_map = {
            EmailTemplateType.WELCOME: "welcome.html",
            EmailTemplateType.ORDER_CONFIRMATION: "orders/order_confirmation.html",
            EmailTemplateType.ORDER_SHIPPED: "orders/order_shipped.html",
            EmailTemplateType.ORDER_DELIVERED: "orders/order_delivered.html",
            EmailTemplateType.ORDER_CANCELLED: "orders/order_cancelled.html",
            EmailTemplateType.PAYMENT_RECEIVED: "orders/payment_received.html",
            EmailTemplateType.PAYMENT_FAILED: "orders/payment_failed.html",
            EmailTemplateType.PASSWORD_RESET: "auth/password_reset.html",
            EmailTemplateType.EMAIL_VERIFICATION: "auth/email_verification.html",
            EmailTemplateType.LOW_STOCK: "farmer/low_stock.html",
            EmailTemplateType.FARMER_WELCOME: "farmer/welcome.html",
            EmailTemplateType.REFUND_PROCESSED: "orders/refund_processed.html",
        }

        template_name = template_map.get(template_type, "default.html")
        template_path = f"notifications/emails/{template_name}"

        # Add support email from settings
        if "support_email" not in context:
            context["support_email"] = (
                settings.SUPPORT_EMAIL or settings.DEFAULT_FROM_EMAIL or ""
            )

        if "frontend_url" not in context:
            context["frontend_url"] = (
                settings.FRONTEND_URL or "http://localhost:3000"
            )

        if "year" not in context:
            context["year"] = timezone.now().year

        try:
            if html:
                return render_to_string(template_path, context)
            else:
                html_content = render_to_string(template_path, context)
                return strip_tags(html_content)
        except Exception as e:
            logger.error(f"Failed to render template {template_path}: {
                    str(e)}")
            return f"Email template not found: {template_type}"


class EmailTemplateService:
    """Service for managing email templates"""

    @staticmethod
    def get_welcome_context(user):
        """Context for welcome email"""
        return {
            "user": user,
            "login_url": f"{settings.FRONTEND_URL}/login",
            "support_email": settings.SUPPORT_EMAIL or "",
            "year": timezone.now().year,
        }

    @staticmethod
    def get_order_confirmation_context(order):
        """Context for order confirmation email"""
        return {
            "order": order,
            "items": order.items.all(),
            "order_url": f"{settings.FRONTEND_URL}/orders/{order.id}",
            "support_email": settings.SUPPORT_EMAIL or "",
            "year": timezone.now().year,
        }

    @staticmethod
    def get_payment_received_context(payment):
        """Context for payment received email"""
        return {
            "payment": payment,
            "order": payment.order,
            "payment_url": f"{settings.FRONTEND_URL}/payments/{payment.id}",
            "support_email": settings.SUPPORT_EMAIL or "",
            "year": timezone.now().year,
        }
