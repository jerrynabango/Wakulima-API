import uuid
import secrets
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, RegexValidator
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from apps.accounts.models import User
from apps.products.models import Product

class Order(models.Model):
    """Order model"""
    
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Payment')
        PROCESSING = 'processing', _('Processing')
        CONFIRMED = 'confirmed', _('Confirmed')
        SHIPPED = 'shipped', _('Shipped')
        DELIVERED = 'delivered', _('Delivered')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')
        REFUNDED = 'refunded', _('Refunded')
    
    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PAID = 'paid', _('Paid')
        FAILED = 'failed', _('Failed')
        REFUNDED = 'refunded', _('Refunded')
        PARTIALLY_REFUNDED = 'partially_refunded', _('Partially Refunded')
    
    class PaymentMethod(models.TextChoices):
        MPESA = 'mpesa', _('M-Pesa')
        PAYPAL = 'paypal', _('PayPal')
        CASH_ON_DELIVERY = 'cod', _('Cash on Delivery')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(_('order number'), max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    
    # Order amounts
    subtotal = models.DecimalField(_('subtotal'), max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(_('delivery fee'), max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(_('tax'), max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(_('discount'), max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(_('total'), max_digits=10, decimal_places=2)
    
    # Status
    order_status = models.CharField(_('order status'), max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    payment_status = models.CharField(_('payment status'), max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_method = models.CharField(_('payment method'), max_length=20, choices=PaymentMethod.choices)
    
    # Shipping information
    shipping_address = models.TextField(_('shipping address'))
    shipping_city = models.CharField(_('city'), max_length=100)
    shipping_zip_code = models.CharField(_('zip code'), max_length=20)
    shipping_phone = models.CharField(_('phone number'), max_length=15)
    tracking_number = models.CharField(_('tracking number'), max_length=100, blank=True)
    
    # Payment references
    payment_id = models.CharField(_('payment ID'), max_length=200, blank=True)
    payment_response = models.JSONField(_('payment response'), default=dict, blank=True)
    
    # Notes
    customer_note = models.TextField(_('customer note'), blank=True)
    admin_note = models.TextField(_('admin note'), blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    paid_at = models.DateTimeField(_('paid at'), blank=True, null=True)
    delivered_at = models.DateTimeField(_('delivered at'), blank=True, null=True)
    cancelled_at = models.DateTimeField(_('cancelled at'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('order')
        verbose_name_plural = _('orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['order_status']),
            models.Index(fields=['payment_status']),
        ]
    
    def __str__(self):
        return f"Order {self.order_number}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        """Generate unique order number"""
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_part = secrets.token_hex(3).upper()
        return f"ORD-{timestamp}-{random_part}"
    
    @property
    def can_cancel(self):
        """Check if order can be cancelled"""
        return self.order_status in [
            self.OrderStatus.PENDING,
            self.OrderStatus.PROCESSING
        ]
    
    @property
    def can_refund(self):
        """Check if order can be refunded"""
        return self.payment_status == self.PaymentStatus.PAID and \
               self.order_status not in [self.OrderStatus.REFUNDED, self.OrderStatus.CANCELLED]

class OrderItem(models.Model):
    """Order item model"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='order_items')
    product_name = models.CharField(_('product name'), max_length=200)
    product_price = models.DecimalField(_('product price'), max_digits=10, decimal_places=2)
    quantity = models.DecimalField(_('quantity'), max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(_('unit price'), max_digits=10, decimal_places=2)
    total_price = models.DecimalField(_('total price'), max_digits=10, decimal_places=2)
    
    class Meta:
        verbose_name = _('order item')
        verbose_name_plural = _('order items')
    
    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

class OrderActivity(models.Model):
    """Order activity log"""
    
    class ActivityType(models.TextChoices):
        CREATED = 'created', _('Order Created')
        PAYMENT_INITIATED = 'payment_initiated', _('Payment Initiated')
        PAYMENT_CONFIRMED = 'payment_confirmed', _('Payment Confirmed')
        STATUS_CHANGED = 'status_changed', _('Status Changed')
        CANCELLED = 'cancelled', _('Order Cancelled')
        REFUND_INITIATED = 'refund_initiated', _('Refund Initiated')
        REFUND_COMPLETED = 'refund_completed', _('Refund Completed')
        NOTE_ADDED = 'note_added', _('Note Added')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    description = models.TextField()
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='order_activities')
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('order activity')
        verbose_name_plural = _('order activities')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.order.order_number} - {self.activity_type}"
