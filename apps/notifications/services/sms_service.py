import logging

import africastalking
from django.conf import settings

from apps.notifications.choices import SMSTemplateType
from apps.notifications.models import SMSLog

logger = logging.getLogger(__name__)


class AfricaTalkingSMSService:
    """SMS service using Africa's Talking API (free credits available)"""

    def __init__(self):
        # All values must come from .env - no hardcoded defaults
        self.username = settings.AFRICASTALKING_USERNAME
        self.api_key = settings.AFRICASTALKING_API_KEY
        self.sandbox = settings.AFRICASTALKING_SANDBOX
        self.sender_id = settings.AFRICASTALKING_SENDER_ID

        # Validate configuration
        if not self.username:
            logger.error("AFRICASTALKING_USERNAME not set in .env file")
        if not self.api_key:
            logger.error("AFRICASTALKING_API_KEY not set in .env file")
        if not self.sender_id:
            logger.error("AFRICASTALKING_SENDER_ID not set in .env file")

        if self.username and self.api_key:
            africastalking.initialize(self.username, self.api_key)
            self.sms = africastalking.SMS
            logger.info(
                f"Africa's Talking SMS service initialized - Sandbox: {self.sandbox}"
            )
        else:
            logger.warning(
                "Africa's Talking credentials not configured - check your .env file"
            )
            self.sms = None

    def send_sms(
        self,
        to_phone,
        message,
        template_type,
        reference_id=None,
        metadata=None,
    ):
        """
        Send SMS using Africa's Talking API

        Args:
            to_phone: Recipient phone number (Kenyan format: 2547XXXXXXXX)
            message: SMS message content
            template_type: Type of SMS template
            reference_id: Reference ID (order ID, etc.)
            metadata: Additional metadata

        Returns:
            dict: {'success': bool, 'message_id': str, 'error': str}
        """
        if not self.sms:
            return {
                "success": False,
                "error": "SMS service not configured. Please check AFRICASTALKING_USERNAME, AFRICASTALKING_API_KEY in .env",
            }

        if not self.sender_id:
            return {
                "success": False,
                "error": "AFRICASTALKING_SENDER_ID not configured in .env file",
            }

        try:
            # Format phone number (ensure it starts with 254)
            formatted_phone = self._format_phone_number(to_phone)

            # Send SMS
            response = self.sms.send(
                message, [formatted_phone], sender_id=self.sender_id
            )

            # Parse response
            if response and response.get("SMSMessageData"):
                recipients = response["SMSMessageData"].get("Recipients", [])
                if recipients:
                    recipient = recipients[0]
                    status = recipient.get("status")
                    message_id = recipient.get("messageId")
                    cost = recipient.get("cost", "0")

                    # Log the SMS
                    sms_log = SMSLog.objects.create(
                        to_phone=formatted_phone,
                        from_phone=self.sender_id,
                        message=message,
                        template_type=template_type,
                        status="sent" if status == "Success" else status,
                        message_id=message_id,
                        cost=float(cost) if cost else 0,
                        reference_id=reference_id,
                        metadata=metadata or {},
                    )

                    logger.info(f"SMS sent to {formatted_phone} from {
                            self.sender_id} - Template: {template_type}")

                    return {
                        "success": status == "Success",
                        "message_id": message_id,
                        "log_id": str(sms_log.id),
                        "status": status,
                    }

            logger.error(f"SMS sending failed: {response}")
            return {
                "success": False,
                "error": "Failed to send SMS",
                "response": response,
            }

        except Exception as e:
            logger.error(f"Failed to send SMS to {to_phone}: {str(e)}")

            # Log failed SMS
            SMSLog.objects.create(
                to_phone=self._format_phone_number(to_phone),
                message=message,
                template_type=template_type,
                status="failed",
                error_message=str(e),
                reference_id=reference_id,
                metadata=metadata or {},
            )

            return {"success": False, "error": str(e)}

    def _format_phone_number(self, phone_number):
        """Format phone number to international format (254XXXXXXXXX)"""
        phone_number = phone_number.strip()

        # Remove leading '+'
        if phone_number.startswith("+"):
            phone_number = phone_number[1:]

        # If starts with 0, replace with 254
        if phone_number.startswith("0"):
            phone_number = "254" + phone_number[1:]

        # If starts with 7 or 1, add 254
        if phone_number.startswith("7") or phone_number.startswith("1"):
            phone_number = "254" + phone_number

        return phone_number

    def send_bulk_sms(self, recipients, message, template_type):
        """
        Send bulk SMS to multiple recipients

        Args:
            recipients: List of phone numbers
            message: SMS message content
            template_type: Type of SMS template

        Returns:
            dict: Summary of results
        """
        results = []

        for recipient in recipients:
            result = self.send_sms(recipient, message, template_type)
            results.append(result)

        return {
            "total": len(recipients),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results,
        }


class SMSTemplateService:
    """Service for generating SMS message content from templates"""

    @staticmethod
    def get_order_confirmation_message(order):
        """Generate order confirmation SMS"""
        return f"Wakulima: Order #{
            order.order_number} confirmed! Amount: KES {
            order.total}. We'll notify you when shipped."

    @staticmethod
    def get_order_shipped_message(order):
        """Generate order shipped SMS"""
        tracking = f" Tracking: {
                order.tracking_number}" if order.tracking_number else ""
        return f"Wakulima: Order #{
            order.order_number} shipped!{tracking} Expected delivery in 2-3 days."

    @staticmethod
    def get_order_delivered_message(order):
        """Generate order delivered SMS"""
        return f"Wakulima: Order #{
            order.order_number} delivered! Thank you for shopping with us."

    @staticmethod
    def get_payment_received_message(payment):
        """Generate payment received SMS"""
        return f"Wakulima: Payment of KES {
            payment.amount} received for Order #{
            payment.order.order_number}. Thank you!"

    @staticmethod
    def get_otp_message(otp_code, purpose="verification"):
        """Generate OTP verification SMS"""
        return f"Wakulima: Your OTP for {purpose} is {otp_code}. Valid for 10 minutes."

    @staticmethod
    def get_low_stock_message(product):
        """Generate low stock alert SMS for farmers"""
        return f"Wakulima Alert: {
            product.name} is running low! Current stock: {
            product.quantity} {
            product.unit_type}. Restock soon."
