import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from apps.products.models import Product
from apps.accounts.models import User

class Inventory(models.Model):
    """Main inventory model linked to products"""
    
    class StockStatus(models.TextChoices):
        IN_STOCK = 'in_stock', _('In Stock')
        LOW_STOCK = 'low_stock', _('Low Stock')
        OUT_OF_STOCK = 'out_of_stock', _('Out of Stock')
        DISCONTINUED = 'discontinued', _('Discontinued')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name=_('product')
    )
    
    # Stock levels
    quantity = models.DecimalField(
        _('current quantity'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    reserved_quantity = models.DecimalField(
        _('reserved quantity'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Thresholds
    minimum_stock = models.DecimalField(
        _('minimum stock'),
        max_digits=10,
        decimal_places=2,
        default=5,
        help_text=_("Alert when stock falls below this level")
    )
    maximum_stock = models.DecimalField(
        _('maximum stock'),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Maximum stock limit (optional)")
    )
    reorder_point = models.DecimalField(
        _('reorder point'),
        max_digits=10,
        decimal_places=2,
        default=10,
        help_text=_("Stock level that triggers reorder")
    )
    reorder_quantity = models.DecimalField(
        _('reorder quantity'),
        max_digits=10,
        decimal_places=2,
        default=20,
        help_text=_("Quantity to reorder when stock reaches reorder point")
    )
    
    # Status
    status = models.CharField(
        _('stock status'),
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.OUT_OF_STOCK
    )
    
    # Location
    warehouse_location = models.CharField(_('warehouse location'), max_length=200, blank=True)
    shelf_number = models.CharField(_('shelf number'), max_length=50, blank=True)
    
    # Timestamps
    last_updated = models.DateTimeField(_('last updated'), auto_now=True)
    last_restocked = models.DateTimeField(_('last restocked'), blank=True, null=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('inventory')
        verbose_name_plural = _('inventories')
        ordering = ['-last_updated']
        indexes = [
            models.Index(fields=['product', 'status']),
            models.Index(fields=['quantity', 'minimum_stock']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} {self.product.unit_type}"
    
    @property
    def available_quantity(self):
        """Calculate available stock (quantity - reserved)"""
        return self.quantity - self.reserved_quantity
    
    @property
    def is_low_stock(self):
        """Check if stock is below minimum threshold"""
        return self.available_quantity <= self.minimum_stock
    
    @property
    def needs_reorder(self):
        """Check if stock needs reordering"""
        return self.available_quantity <= self.reorder_point
    
    def update_status(self):
        """Update stock status based on current quantity"""
        if self.quantity <= 0:
            self.status = self.StockStatus.OUT_OF_STOCK
        elif self.quantity <= self.minimum_stock:
            self.status = self.StockStatus.LOW_STOCK
        else:
            self.status = self.StockStatus.IN_STOCK
        self.save(update_fields=['status'])
    
    def reserve_stock(self, quantity):
        """Reserve stock for an order"""
        if quantity > self.available_quantity:
            raise ValueError(f"Insufficient stock. Available: {self.available_quantity}")
        self.reserved_quantity += quantity
        self.save(update_fields=['reserved_quantity'])
        return True
    
    def release_reserved_stock(self, quantity):
        """Release reserved stock (e.g., when order is cancelled)"""
        if quantity > self.reserved_quantity:
            quantity = self.reserved_quantity
        self.reserved_quantity -= quantity
        self.save(update_fields=['reserved_quantity'])
        return True
    
    def deduct_stock(self, quantity):
        """Deduct stock after order is confirmed"""
        if quantity > self.quantity:
            raise ValueError(f"Insufficient stock. Available: {self.quantity}")
        self.quantity -= quantity
        self.reserved_quantity -= min(quantity, self.reserved_quantity)
        self.save()
        self.update_status()
        return True
    
    def add_stock(self, quantity, user=None, reason=None):
        """Add stock to inventory"""
        self.quantity += quantity
        self.last_restocked = timezone.now()
        self.save()
        self.update_status()
        
        # Create stock movement record
        StockMovement.objects.create(
            inventory=self,
            user=user,
            movement_type=StockMovement.MovementType.RESTOCK,
            quantity=quantity,
            previous_quantity=self.quantity - quantity,
            new_quantity=self.quantity,
            reason=reason or "Manual restock"
        )
        return True


class StockMovement(models.Model):
    """Track all stock movements"""
    
    class MovementType(models.TextChoices):
        RESTOCK = 'restock', _('Restock')
        SALE = 'sale', _('Sale')
        RETURN = 'return', _('Return')
        DAMAGE = 'damage', _('Damage')
        ADJUSTMENT = 'adjustment', _('Adjustment')
        RESERVATION = 'reservation', _('Reservation')
        RELEASE = 'release', _('Release')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='movements')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    
    movement_type = models.CharField(_('movement type'), max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(_('quantity'), max_digits=10, decimal_places=2)
    previous_quantity = models.DecimalField(_('previous quantity'), max_digits=10, decimal_places=2)
    new_quantity = models.DecimalField(_('new quantity'), max_digits=10, decimal_places=2)
    
    reason = models.TextField(_('reason'), blank=True)
    reference_id = models.CharField(_('reference ID'), max_length=100, blank=True, help_text="Order ID, etc.")
    
    metadata = models.JSONField(_('metadata'), default=dict, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('stock movement')
        verbose_name_plural = _('stock movements')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['inventory', '-created_at']),
            models.Index(fields=['movement_type']),
        ]
    
    def __str__(self):
        return f"{self.movement_type}: {self.quantity} - {self.inventory.product.name}"


class StockAlert(models.Model):
    """Track stock alerts and notifications"""
    
    class AlertType(models.TextChoices):
        LOW_STOCK = 'low_stock', _('Low Stock')
        OUT_OF_STOCK = 'out_of_stock', _('Out of Stock')
        EXPIRING = 'expiring', _('Expiring Soon')
    
    class AlertStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SENT = 'sent', _('Sent')
        RESOLVED = 'resolved', _('Resolved')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(_('alert type'), max_length=20, choices=AlertType.choices)
    message = models.TextField(_('alert message'))
    status = models.CharField(_('status'), max_length=20, choices=AlertStatus.choices, default=AlertStatus.PENDING)
    sent_at = models.DateTimeField(_('sent at'), blank=True, null=True)
    resolved_at = models.DateTimeField(_('resolved at'), blank=True, null=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('stock alert')
        verbose_name_plural = _('stock alerts')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.alert_type} - {self.inventory.product.name}"


class InventoryReservation(models.Model):
    """Temporary inventory reservations for pending orders"""
    
    class ReservationStatus(models.TextChoices):
        ACTIVE = 'active', _('Active')
        CONFIRMED = 'confirmed', _('Confirmed')
        CANCELLED = 'cancelled', _('Cancelled')
        EXPIRED = 'expired', _('Expired')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='reservations')
    order_id = models.CharField(_('order ID'), max_length=100, db_index=True)
    quantity = models.DecimalField(_('quantity'), max_digits=10, decimal_places=2)
    status = models.CharField(_('status'), max_length=20, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE)
    expires_at = models.DateTimeField(_('expires at'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('inventory reservation')
        verbose_name_plural = _('inventory reservations')
        indexes = [
            models.Index(fields=['order_id', 'status']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"Reservation for {self.order_id}: {self.quantity}"
    
    def is_expired(self):
        """Check if reservation has expired"""
        return self.expires_at < timezone.now()
