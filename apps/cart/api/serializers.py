from rest_framework import serializers

from apps.cart.models import Cart, CartItem
from apps.products.api.serializers import ProductListSerializer
from apps.products.models import Product


class CartItemSerializer(serializers.ModelSerializer):
    """Serializer for cart items"""

    product_detail = ProductListSerializer(source="product", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(
        source="product.price", read_only=True, max_digits=10, decimal_places=2
    )
    total_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = (
            "id",
            "product",
            "product_detail",
            "product_name",
            "product_price",
            "quantity",
            "unit_price",
            "total_price",
            "available_stock",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "unit_price", "created_at", "updated_at")

    def get_available_stock(self, obj):
        """Check available stock for product"""
        return obj.product.quantity

    def validate_quantity(self, value):
        """Validate quantity against available stock"""
        product_id = self.initial_data.get("product")
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                if value > product.quantity:
                    raise serializers.ValidationError(f"Only {
                            product.quantity} {
                            product.unit_type} available in stock")
            except Product.DoesNotExist:
                raise serializers.ValidationError("Product not found")
        return value


class AddToCartSerializer(serializers.Serializer):
    """Serializer for adding item to cart"""

    product_id = serializers.UUIDField(required=True)
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01, required=True
    )


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer for updating cart item quantity"""

    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01, required=True
    )


class CartSummarySerializer(serializers.Serializer):
    """Serializer for cart summary"""

    total_items = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartSerializer(serializers.ModelSerializer):
    """Full cart serializer"""

    items = CartItemSerializer(many=True, read_only=True)
    summary = CartSummarySerializer(source="*", read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    delivery_fee = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    tax = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    total = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )

    class Meta:
        model = Cart
        fields = (
            "id",
            "items",
            "total_items",
            "subtotal",
            "delivery_fee",
            "tax",
            "total",
            "summary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
