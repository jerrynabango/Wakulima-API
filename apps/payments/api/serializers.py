from rest_framework import serializers

from apps.orders.models import Order
from apps.payments.models import Payment, Refund


class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer"""

    order_number = serializers.CharField(
        source="order.order_number", read_only=True
    )
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "order_number",
            "user",
            "user_email",
            "amount",
            "currency",
            "gateway",
            "status",
            "transaction_id",
            "payment_method",
            "payment_channel",
            "created_at",
            "updated_at",
            "paid_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "paid_at")


class InitiateMpesaPaymentSerializer(serializers.Serializer):
    """Serializer for initiating M-Pesa payment"""

    phone_number = serializers.CharField(max_length=15, required=True)

    def validate_phone_number(self, value):
        import re

        phone_pattern = re.compile(r"^\+?254\d{9}$")
        if not phone_pattern.match(value):
            raise serializers.ValidationError(
                "Phone number must be in Kenyan format (e.g., +254712345678 or 0712345678)"
            )
        return value


class InitiatePayPalPaymentSerializer(serializers.Serializer):
    """Serializer for initiating PayPal payment"""

    return_url = serializers.URLField(required=True)
    cancel_url = serializers.URLField(required=True)


class CapturePayPalPaymentSerializer(serializers.Serializer):
    """Serializer for capturing PayPal payment"""

    payer_id = serializers.CharField(required=True)


class RefundSerializer(serializers.Serializer):
    """Serializer for initiating refund"""

    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )
    reason = serializers.CharField(required=True, max_length=500)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
