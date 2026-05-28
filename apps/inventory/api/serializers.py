from rest_framework import serializers
from apps.inventory.models import Inventory, StockMovement, StockAlert, InventoryReservation
from apps.products.api.serializers import ProductListSerializer


class InventorySerializer(serializers.ModelSerializer):
    """Main inventory serializer"""
    product_detail = ProductListSerializer(source='product', read_only=True)
    available_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Inventory
        fields = (
            'id', 'product', 'product_detail', 'quantity', 'reserved_quantity',
            'available_quantity', 'minimum_stock', 'maximum_stock', 'reorder_point',
            'reorder_quantity', 'status', 'is_low_stock', 'needs_reorder',
            'warehouse_location', 'shelf_number', 'last_updated', 'last_restocked'
        )
        read_only_fields = ('id', 'status', 'last_updated', 'created_at')


class StockMovementSerializer(serializers.ModelSerializer):
    """Stock movement serializer"""
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    product_name = serializers.CharField(source='inventory.product.name', read_only=True)
    
    class Meta:
        model = StockMovement
        fields = (
            'id', 'inventory', 'product_name', 'movement_type', 'quantity',
            'previous_quantity', 'new_quantity', 'reason', 'reference_id',
            'user', 'user_name', 'metadata', 'created_at'
        )
        read_only_fields = ('id', 'created_at')


class StockAlertSerializer(serializers.ModelSerializer):
    """Stock alert serializer"""
    product_name = serializers.CharField(source='inventory.product.name', read_only=True)
    
    class Meta:
        model = StockAlert
        fields = (
            'id', 'inventory', 'product_name', 'alert_type', 'message',
            'status', 'sent_at', 'resolved_at', 'created_at'
        )
        read_only_fields = ('id', 'created_at')


class UpdateStockSerializer(serializers.Serializer):
    """Serializer for updating stock"""
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class BulkUpdateStockSerializer(serializers.Serializer):
    """Serializer for bulk stock updates"""
    updates = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )


class StockAdjustmentSerializer(serializers.Serializer):
    """Serializer for stock adjustment"""
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    reason = serializers.CharField(required=True)
    adjustment_type = serializers.ChoiceField(choices=['add', 'subtract'], required=True)


class StockTransferSerializer(serializers.Serializer):
    """Serializer for transferring stock between locations"""
    from_inventory_id = serializers.UUIDField(required=True)
    to_inventory_id = serializers.UUIDField(required=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    reason = serializers.CharField(required=False, allow_blank=True)
