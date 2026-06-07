from django.contrib import admin

from apps.inventory.models import (
    Inventory,
    InventoryReservation,
    StockAlert,
    StockMovement,
)


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "quantity",
        "reserved_quantity",
        "available_quantity",
        "status",
        "last_updated",
    )
    list_filter = ("status", "last_updated")
    search_fields = ("product__name", "product__farmer__email")
    readonly_fields = ("id", "created_at", "last_updated")

    fieldsets = (
        ("Product Information", {"fields": ("product",)}),
        (
            "Stock Levels",
            {
                "fields": (
                    "quantity",
                    "reserved_quantity",
                    "minimum_stock",
                    "maximum_stock",
                )
            },
        ),
        (
            "Reorder Settings",
            {"fields": ("reorder_point", "reorder_quantity")},
        ),
        (
            "Status",
            {"fields": ("status", "warehouse_location", "shelf_number")},
        ),
        (
            "Timestamps",
            {"fields": ("last_updated", "last_restocked", "created_at")},
        ),
    )

    def available_quantity(self, obj):
        return obj.available_quantity

    available_quantity.short_description = "Available"


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "inventory",
        "movement_type",
        "quantity",
        "user",
        "created_at",
    )
    list_filter = ("movement_type", "created_at")
    search_fields = ("inventory__product__name", "reason", "reference_id")
    readonly_fields = ("id", "created_at")


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ("inventory", "alert_type", "status", "created_at")
    list_filter = ("alert_type", "status", "created_at")
    search_fields = ("inventory__product__name", "message")
    readonly_fields = ("id", "created_at")


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = (
        "inventory",
        "order_id",
        "quantity",
        "status",
        "expires_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order_id", "inventory__product__name")
    readonly_fields = ("id", "created_at")
