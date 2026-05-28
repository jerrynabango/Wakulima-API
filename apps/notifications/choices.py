from django.db import models
from django.utils.translation import gettext_lazy as _

class NotificationType(models.TextChoices):
    """Types of notifications"""
    EMAIL = 'email', _('Email')
    SMS = 'sms', _('SMS')
    PUSH = 'push', _('Push Notification')
    IN_APP = 'in_app', _('In-App Notification')

class NotificationCategory(models.TextChoices):
    """Categories of notifications"""
    ORDER = 'order', _('Order')
    PAYMENT = 'payment', _('Payment')
    AUTH = 'auth', _('Authentication')
    PROMOTION = 'promotion', _('Promotion')
    ALERT = 'alert', _('Alert')
    SYSTEM = 'system', _('System')

class NotificationPriority(models.TextChoices):
    """Priority levels for notifications"""
    LOW = 'low', _('Low')
    NORMAL = 'normal', _('Normal')
    HIGH = 'high', _('High')
    URGENT = 'urgent', _('Urgent')

class EmailTemplateType(models.TextChoices):
    """Email template types"""
    WELCOME = 'welcome', _('Welcome Email')
    ORDER_CONFIRMATION = 'order_confirmation', _('Order Confirmation')
    ORDER_SHIPPED = 'order_shipped', _('Order Shipped')
    ORDER_DELIVERED = 'order_delivered', _('Order Delivered')
    ORDER_CANCELLED = 'order_cancelled', _('Order Cancelled')
    PAYMENT_RECEIVED = 'payment_received', _('Payment Received')
    PAYMENT_FAILED = 'payment_failed', _('Payment Failed')
    PASSWORD_RESET = 'password_reset', _('Password Reset')
    EMAIL_VERIFICATION = 'email_verification', _('Email Verification')
    LOW_STOCK = 'low_stock', _('Low Stock Alert')
    FARMER_WELCOME = 'farmer_welcome', _('Farmer Welcome')
    REFUND_PROCESSED = 'refund_processed', _('Refund Processed')

class SMSTemplateType(models.TextChoices):
    """SMS template types"""
    ORDER_CONFIRMATION = 'order_confirmation', _('Order Confirmation')
    ORDER_SHIPPED = 'order_shipped', _('Order Shipped')
    ORDER_DELIVERED = 'order_delivered', _('Order Delivered')
    OTP_VERIFICATION = 'otp_verification', _('OTP Verification')
    PAYMENT_RECEIVED = 'payment_received', _('Payment Received')
    LOW_STOCK = 'low_stock', _('Low Stock Alert')
