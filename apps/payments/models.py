import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from apps.accounts.models import User
from apps.orders.models import Order

class Payment(models.Model):
    """Payment transaction model"""
    
    class PaymentGateway(models.TextChoices):
        MPESA = 'mpesa', _('M-Pesa')
        PAYPAL = 'paypal', _('PayPal')
    
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PROCESSING = 'processing', _('Processing')
        SUCCESS = 'success', _('Success')
        FAILED = 'failed', _('Failed')
        REFUNDED = 'refunded', _('Refunded')
        CANCELLED = 'cancelled', _('Cancelled')
    
    class PaymentChannel(models.TextChoices):
        MOBILE = 'mobile', _('Mobile Money')
        CARD = 'card', _('Credit/Debit Card')
        BANK = 'bank', _('Bank Transfer')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    
    # Payment details
    amount = models.DecimalField(_('amount'), max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(_('currency'), max_length=3, default='KES')
    gateway = models.CharField(_('payment gateway'), max_length=10, choices=PaymentGateway.choices)
    status = models.CharField(_('payment status'), max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    # Gateway specific IDs
    transaction_id = models.CharField(_('transaction ID'), max_length=200, blank=True, unique=True, null=True)
    gateway_reference = models.CharField(_('gateway reference'), max_length=200, blank=True)
    
    # Request/Response data
    request_data = models.JSONField(_('request data'), default=dict, blank=True)
    response_data = models.JSONField(_('response data'), default=dict, blank=True)
    webhook_data = models.JSONField(_('webhook data'), default=dict, blank=True)
    
    # M-Pesa specific fields
    mpesa_checkout_request_id = models.CharField(max_length=100, blank=True)
    mpesa_merchant_request_id = models.CharField(max_length=100, blank=True)
    mpesa_result_code = models.CharField(max_length=10, blank=True)
    mpesa_result_desc = models.CharField(max_length=255, blank=True)
    
    # PayPal specific fields
    paypal_order_id = models.CharField(max_length=100, blank=True)
    paypal_payer_id = models.CharField(max_length=100, blank=True)
    paypal_payment_id = models.CharField(max_length=100, blank=True)
    
    # Metadata
    payment_method = models.CharField(_('payment method'), max_length=50, blank=True)
    payment_channel = models.CharField(_('payment channel'), max_length=20, choices=PaymentChannel.choices, blank=True)
    customer_phone = models.CharField(_('customer phone'), max_length=15, blank=True)
    customer_email = models.EmailField(_('customer email'), blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    paid_at = models.DateTimeField(_('paid at'), blank=True, null=True)
    refunded_at = models.DateTimeField(_('refunded at'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('payment')
        verbose_name_plural = _('payments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['gateway', 'status']),
            models.Index(fields=['order', 'status']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"Payment {self.transaction_id or self.id} - {self.amount} {self.currency}"
    
    @property
    def is_successful(self):
        return self.status == self.PaymentStatus.SUCCESS
    
    @property
    def is_pending(self):
        return self.status == self.PaymentStatus.PENDING

class PaymentWebhook(models.Model):
    """Store incoming webhook data from payment gateways"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(_('gateway'), max_length=10, choices=Payment.PaymentGateway.choices)
    event_type = models.CharField(_('event type'), max_length=100)
    payload = models.JSONField(_('payload'))
    processed = models.BooleanField(_('processed'), default=False)
    processed_at = models.DateTimeField(_('processed at'), blank=True, null=True)
    error_message = models.TextField(_('error message'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('payment webhook')
        verbose_name_plural = _('payment webhooks')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.gateway} - {self.event_type} - {self.created_at}"

class Refund(models.Model):
    """Refund transactions"""
    
    class RefundStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PROCESSING = 'processing', _('Processing')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refunds')
    
    amount = models.DecimalField(_('amount'), max_digits=10, decimal_places=2)
    reason = models.TextField(_('reason'))
    status = models.CharField(_('status'), max_length=20, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    
    # Gateway reference
    refund_id = models.CharField(_('refund ID'), max_length=200, blank=True)
    gateway_response = models.JSONField(_('gateway response'), default=dict, blank=True)
    
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    completed_at = models.DateTimeField(_('completed at'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('refund')
        verbose_name_plural = _('refunds')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Refund {self.amount} for payment {self.payment.id}"
