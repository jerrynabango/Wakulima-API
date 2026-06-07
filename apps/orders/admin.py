from django.contrib import admin
from django.utils.html import format_html

from apps.orders.models import Order, OrderActivity, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    readonly_fields = ("product_name", "quantity", "unit_price", "total_price")
    extra = 0
    can_delete = False


class OrderActivityInline(admin.TabularInline):
    model = OrderActivity
    readonly_fields = ("activity_type", "description", "created_at")
    extra = 0
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "total",
        "order_status",
        "payment_status",
        "created_at",
    )
    list_filter = (
        "order_status",
        "payment_status",
        "payment_method",
        "created_at",
    )
    search_fields = (
        "order_number",
        "user__email",
        "user__full_name",
        "shipping_phone",
    )
    readonly_fields = (
        "order_number",
        "created_at",
        "updated_at",
        "paid_at",
        "delivered_at",
    )
    inlines = [OrderItemInline, OrderActivityInline]

    fieldsets = (
        (
            "Order Information",
            {"fields": ("order_number", "user", "created_at")},
        ),
        (
            "Amounts",
            {
                "fields": (
                    "subtotal",
                    "delivery_fee",
                    "tax",
                    "discount",
                    "total",
                )
            },
        ),
        (
            "Status",
            {"fields": ("order_status", "payment_status", "payment_method")},
        ),
        (
            "Shipping",
            {
                "fields": (
                    "shipping_address",
                    "shipping_city",
                    "shipping_zip_code",
                    "shipping_phone",
                    "tracking_number",
                )
            },
        ),
        ("Notes", {"fields": ("customer_note", "admin_note")}),
        (
            "Timestamps",
            {
                "fields": (
                    "paid_at",
                    "delivered_at",
                    "cancelled_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(OrderActivity)
class OrderActivityAdmin(admin.ModelAdmin):
    list_display = ("order", "activity_type", "performed_by", "created_at")
    list_filter = ("activity_type", "created_at")
    search_fields = ("order__order_number", "description")
    readonly_fields = ("id", "created_at")
