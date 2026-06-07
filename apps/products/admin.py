from django.contrib import admin
from django.utils.html import format_html

from apps.products.models import (
    Category,
    InventoryHistory,
    Product,
    ProductImage,
    ProductReview,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "created_at")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "farmer",
        "category",
        "price",
        "quantity",
        "status",
        "is_available",
        "created_at",
    )
    list_filter = (
        "status",
        "is_available",
        "is_organic",
        "category",
        "quality_grade",
    )
    search_fields = (
        "name",
        "description",
        "farmer__email",
        "farmer__full_name",
    )
    readonly_fields = (
        "id",
        "slug",
        "views_count",
        "orders_count",
        "created_at",
        "updated_at",
    )
    list_editable = ("price", "quantity", "status")

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "short_description",
                    "category",
                    "farmer",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "price",
                    "compare_price",
                    "cost_per_unit",
                    "tax_rate",
                )
            },
        ),
        (
            "Inventory",
            {
                "fields": (
                    "unit_type",
                    "quantity",
                    "minimum_stock",
                    "maximum_stock",
                )
            },
        ),
        (
            "Quality & Origin",
            {
                "fields": (
                    "quality_grade",
                    "origin",
                    "harvest_date",
                    "expiry_date",
                )
            },
        ),
        (
            "Attributes",
            {"fields": ("is_organic", "is_locally_sourced", "is_featured")},
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "is_available",
                    "views_count",
                    "orders_count",
                )
            },
        ),
        (
            "SEO",
            {"fields": ("meta_title", "meta_description", "meta_keywords")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at", "published_at")},
        ),
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "is_primary", "order", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "alt_text")


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "user",
        "rating",
        "title",
        "is_approved",
        "created_at",
    )
    list_filter = ("rating", "is_approved", "is_verified_purchase")
    search_fields = ("product__name", "user__email", "title", "comment")
    list_editable = ("is_approved",)


@admin.register(InventoryHistory)
class InventoryHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "change_type",
        "quantity_change",
        "user",
        "created_at",
    )
    list_filter = ("change_type", "created_at")
    search_fields = ("product__name", "user__email", "reason")
    readonly_fields = ("id", "created_at")
