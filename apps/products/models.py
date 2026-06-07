import os
import uuid

from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


def product_image_path(instance, filename):
    """Generate file path for product images"""
    ext = filename.split(".")[-1]
    filename = f"{instance.product.id}_{uuid.uuid4().hex}.{ext}"
    return os.path.join("products", str(instance.product.id), filename)


class Category(models.Model):
    """Product category model"""

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name", "slug"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=120, unique=True)
    description = models.TextField(_("description"), blank=True)
    icon = models.CharField(
        _("icon"),
        max_length=50,
        blank=True,
        help_text="Font awesome icon class",
    )
    image = models.ImageField(
        _("image"), upload_to="categories/", blank=True, null=True
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories",
        verbose_name=_("parent category"),
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """Product model for agricultural items"""

    class UnitType(models.TextChoices):
        KILOGRAM = "kg", _("Kilogram")
        GRAM = "g", _("Gram")
        PIECE = "piece", _("Piece")
        BUNCH = "bunch", _("Bunch")
        LITRE = "litre", _("Litre")
        MILLILITRE = "ml", _("Millilitre")
        DOZEN = "dozen", _("Dozen")
        BOX = "box", _("Box")
        SACK = "sack", _("Sack")

    class ProductStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Pending Approval")
        ACTIVE = "active", _("Active")
        OUT_OF_STOCK = "out_of_stock", _("Out of Stock")
        DISCONTINUED = "discontinued", _("Discontinued")

    class QualityGrade(models.TextChoices):
        PREMIUM = "premium", _("Premium")
        GRADE_A = "grade_a", _("Grade A")
        GRADE_B = "grade_b", _("Grade B")
        GRADE_C = "grade_c", _("Grade C")
        STANDARD = "standard", _("Standard")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farmer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="products",
        limit_choices_to={"role": User.Role.FARMER},
        verbose_name=_("farmer"),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name="products",
        verbose_name=_("category"),
    )

    # Basic Information
    name = models.CharField(_("product name"), max_length=200, db_index=True)
    slug = models.SlugField(
        _("slug"), max_length=220, unique=True, db_index=True
    )
    description = models.TextField(_("description"))
    short_description = models.CharField(
        _("short description"), max_length=300, blank=True
    )

    # Pricing
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    compare_price = models.DecimalField(
        _("compare price"),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Original price for discount display",
    )
    cost_per_unit = models.DecimalField(
        _("cost per unit"),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    # Stock and Inventory
    unit_type = models.CharField(
        _("unit type"),
        max_length=10,
        choices=UnitType.choices,
        default=UnitType.KILOGRAM,
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    minimum_stock = models.DecimalField(
        _("minimum stock"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Alert when stock falls below this level",
    )
    maximum_stock = models.DecimalField(
        _("maximum stock"),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Maximum stock limit",
    )

    # Quality and Origin
    quality_grade = models.CharField(
        _("quality grade"),
        max_length=10,
        choices=QualityGrade.choices,
        default=QualityGrade.STANDARD,
    )
    origin = models.CharField(
        _("origin"),
        max_length=200,
        blank=True,
        help_text="Farm or region of origin",
    )
    harvest_date = models.DateField(_("harvest date"), blank=True, null=True)
    expiry_date = models.DateField(_("expiry date"), blank=True, null=True)

    # Certification and Attributes
    is_organic = models.BooleanField(_("organic certified"), default=False)
    is_locally_sourced = models.BooleanField(
        _("locally sourced"), default=True
    )
    is_featured = models.BooleanField(_("featured product"), default=False)

    # Status and Visibility
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
    )
    is_available = models.BooleanField(_("available for sale"), default=True)
    views_count = models.PositiveIntegerField(_("views count"), default=0)
    orders_count = models.PositiveIntegerField(_("orders count"), default=0)

    # Tax and Shipping
    tax_rate = models.DecimalField(
        _("tax rate (%)"), max_digits=5, decimal_places=2, default=0
    )
    weight = models.DecimalField(
        _("weight (kg)"), max_digits=8, decimal_places=2, blank=True, null=True
    )
    length = models.DecimalField(
        _("length (cm)"), max_digits=6, decimal_places=2, blank=True, null=True
    )
    width = models.DecimalField(
        _("width (cm)"), max_digits=6, decimal_places=2, blank=True, null=True
    )
    height = models.DecimalField(
        _("height (cm)"), max_digits=6, decimal_places=2, blank=True, null=True
    )

    # SEO
    meta_title = models.CharField(_("meta title"), max_length=200, blank=True)
    meta_description = models.TextField(
        _("meta description"), max_length=500, blank=True
    )
    meta_keywords = models.CharField(
        _("meta keywords"), max_length=200, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    published_at = models.DateTimeField(
        _("published at"), blank=True, null=True
    )

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["farmer", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["name", "slug"]),
            models.Index(fields=["price"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_featured", "status"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)

        # Auto-update status based on stock - Use Product.ProductStatus
        if self.quantity <= 0:
            self.is_available = False
            if self.status == Product.ProductStatus.ACTIVE:
                self.status = Product.ProductStatus.OUT_OF_STOCK
        else:
            self.is_available = True
            if (
                self.status == Product.ProductStatus.OUT_OF_STOCK
                and self.quantity > 0
            ):
                self.status = Product.ProductStatus.ACTIVE

        # Set published_at when status changes to active
        if (
            self.status == Product.ProductStatus.ACTIVE
            and not self.published_at
        ):
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def discount_percentage(self):
        """Calculate discount percentage"""
        if self.compare_price and self.compare_price > self.price:
            return round(
                ((self.compare_price - self.price) / self.compare_price) * 100,
                2,
            )
        return 0

    @property
    def stock_status(self):
        """Return stock status message"""
        if self.quantity <= 0:
            return "out_of_stock"
        elif self.quantity <= self.minimum_stock:
            return "low_stock"
        return "in_stock"

    @property
    def is_low_stock(self):
        """Check if product is low on stock"""
        return self.quantity <= self.minimum_stock


class ProductImage(models.Model):
    """Product images gallery"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(_("image"), upload_to=product_image_path)
    alt_text = models.CharField(_("alt text"), max_length=200, blank=True)
    is_primary = models.BooleanField(_("primary image"), default=False)
    order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["product", "is_primary"]),
        ]

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        # If this image is being set as primary
        if self.is_primary:
            # Set all other images of this product to not primary
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exclude(id=self.id).update(is_primary=False)
        else:
            # If this is the first image and no primary exists, make it primary
            if not ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exists():
                self.is_primary = True

        super().save(*args, **kwargs)


class ProductReview(models.Model):
    """Product reviews and ratings"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"), validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(_("review title"), max_length=200)
    comment = models.TextField(_("comment"))
    is_verified_purchase = models.BooleanField(
        _("verified purchase"), default=False
    )
    is_approved = models.BooleanField(_("approved"), default=False)
    helpful_count = models.PositiveIntegerField(_("helpful votes"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("product review")
        verbose_name_plural = _("product reviews")
        ordering = ["-created_at"]
        unique_together = ["product", "user"]

    def __str__(self):
        return f"Review by {self.user.email} for {self.product.name}"


class InventoryHistory(models.Model):
    """Track inventory changes"""

    class ChangeType(models.TextChoices):
        ADD = "add", _("Stock Added")
        REMOVE = "remove", _("Stock Removed")
        ORDER = "order", _("Order Placed")
        RETURN = "return", _("Product Returned")
        ADJUSTMENT = "adjustment", _("Manual Adjustment")
        DAMAGE = "damage", _("Damaged Product")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_history"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inventory_changes",
    )
    change_type = models.CharField(
        _("change type"), max_length=20, choices=ChangeType.choices
    )
    quantity_change = models.DecimalField(
        _("quantity change"), max_digits=10, decimal_places=2
    )
    previous_quantity = models.DecimalField(
        _("previous quantity"), max_digits=10, decimal_places=2
    )
    new_quantity = models.DecimalField(
        _("new quantity"), max_digits=10, decimal_places=2
    )
    reason = models.TextField(_("reason"), blank=True)
    reference_id = models.CharField(
        _("reference ID"),
        max_length=100,
        blank=True,
        help_text="Order ID or other reference",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("inventory history")
        verbose_name_plural = _("inventory histories")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["change_type"]),
        ]

    def __str__(self):
        return f"{
            self.change_type}: {
            self.quantity_change} of {
            self.product.name}"
