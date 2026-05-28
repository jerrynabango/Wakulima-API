from rest_framework import serializers
from django.utils import timezone
from apps.orders.models import Order, OrderItem, OrderActivity
from apps.cart.models import Cart
from apps.products.models import Product, InventoryHistory

class OrderItemSerializer(serializers.ModelSerializer):
    """Order item serializer"""
    product_id = serializers.UUIDField(source='product.id', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = (
            'id', 'product', 'product_id', 'product_name', 'product_price',
            'quantity', 'unit_price', 'total_price'
        )
        read_only_fields = ('id',)

class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight order serializer for listings"""
    total_items = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'total', 'order_status', 'payment_status',
            'payment_method', 'created_at', 'total_items'
        )
        read_only_fields = ('id', 'order_number', 'created_at')
    
    def get_total_items(self, obj):
        return obj.items.aggregate(total=models.Sum('quantity'))['total'] or 0

class OrderDetailSerializer(serializers.ModelSerializer):
    """Detailed order serializer"""
    items = OrderItemSerializer(many=True, read_only=True)
    activities = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'user', 'subtotal', 'delivery_fee', 'tax',
            'discount', 'total', 'order_status', 'payment_status', 'payment_method',
            'shipping_address', 'shipping_city', 'shipping_zip_code', 'shipping_phone',
            'tracking_number', 'customer_note', 'admin_note', 'items', 'activities',
            'created_at', 'updated_at', 'paid_at', 'delivered_at', 'cancelled_at'
        )
        read_only_fields = ('id', 'order_number', 'created_at', 'updated_at')
    
    def get_activities(self, obj):
        from apps.orders.api.serializers import OrderActivitySerializer
        return OrderActivitySerializer(obj.activities.all()[:20], many=True).data

class OrderCreateSerializer(serializers.Serializer):
    """Serializer for creating order from cart"""
    shipping_address = serializers.CharField(required=True)
    shipping_city = serializers.CharField(required=True)
    shipping_zip_code = serializers.CharField(required=True)
    shipping_phone = serializers.CharField(required=True)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices, required=True)
    customer_note = serializers.CharField(required=False, allow_blank=True)
    
    def validate_shipping_phone(self, value):
        """Validate phone number format"""
        import re
        phone_pattern = re.compile(r'^\+?1?\d{9,15}$')
        if not phone_pattern.match(value):
            raise serializers.ValidationError("Invalid phone number format")
        return value

class OrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating order status"""
    order_status = serializers.ChoiceField(choices=Order.OrderStatus.choices)
    admin_note = serializers.CharField(required=False, allow_blank=True)

class OrderActivitySerializer(serializers.ModelSerializer):
    """Order activity serializer"""
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True)
    
    class Meta:
        model = OrderActivity
        fields = (
            'id', 'activity_type', 'description', 'old_status', 'new_status',
            'performed_by', 'performed_by_name', 'ip_address', 'created_at'
        )
        read_only_fields = ('id', 'created_at')
