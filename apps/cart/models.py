import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.products.models import Product


class Cart(models.Model):
    """Shopping cart model"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name=_("user"),
    )
    session_key = models.CharField(
        _("session key"), max_length=40, blank=True, null=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Cart for {self.user.email if self.user else 'Anonymous'}"

    @property
    def total_items(self):
        """Total number of items in cart"""
        total = self.items.aggregate(total=models.Sum("quantity"))["total"]
        return total if total else Decimal("0.00")

    @property
    def subtotal(self):
        """Subtotal without delivery fee and tax"""
        total = Decimal("0.00")
        for item in self.items.all():
            total += item.total_price
        return total

    @property
    def delivery_fee(self):
        """Calculate delivery fee based on subtotal"""
        if self.subtotal >= Decimal("1000.00"):
            return Decimal("0.00")
        return Decimal("100.00")

    @property
    def tax(self):
        """Calculate tax (e.g., 16% VAT)"""
        tax_rate = Decimal("0.16")
        return self.subtotal * tax_rate

    @property
    def total(self):
        """Grand total including delivery fee and tax"""
        return self.subtotal + self.delivery_fee + self.tax

    def clear(self):
        """Remove all items from cart"""
        self.items.all().delete()

    def merge_with_anonymous_cart(self, session_key):
        """Merge anonymous cart with user cart when user logs in"""
        anonymous_cart = Cart.objects.filter(session_key=session_key).first()
        if anonymous_cart:
            for item in anonymous_cart.items.all():
                cart_item, created = CartItem.objects.get_or_create(
                    cart=self,
                    product=item.product,
                    defaults={
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                    },
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save()
            anonymous_cart.delete()


class CartItem(models.Model):
    """Individual cart item"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="cart_items"
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_price = models.DecimalField(
        _("unit price"), max_digits=10, decimal_places=2
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        unique_together = ["cart", "product"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def total_price(self):
        """Total price for this item"""
        return self.quantity * self.unit_price

    def save(self, *args, **kwargs):
        # Set unit price from product if not set
        if not self.unit_price:
            self.unit_price = self.product.price
        super().save(*args, **kwargs)
