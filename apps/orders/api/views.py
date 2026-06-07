from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import (
    OrderActivitySerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderStatusUpdateSerializer,
)
from apps.orders.models import Order, OrderActivity
from apps.orders.permissions import IsOrderOwnerOrAdmin
from apps.orders.services import OrderService


# ========== Helper function for Swagger ==========
def is_swagger_request(view):
    """Check if the request is for Swagger schema generation"""
    return getattr(view, "swagger_fake_view", False)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0]
    return request.META.get("REMOTE_ADDR")


class CreateOrderView(APIView):
    """Create order from cart"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Create order from current cart",
        request=OrderCreateSerializer,
        responses={201: OrderDetailSerializer()},
    )
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = OrderService.create_order_from_cart(
            user=request.user,
            order_data=serializer.validated_data,
            request_ip=get_client_ip(request),
        )

        if result["success"]:
            order_serializer = OrderDetailSerializer(result["order"])
            return Response(
                order_serializer.data, status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {
                    "error": result["message"],
                    "details": result.get("errors", {}),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class OrderListView(generics.ListAPIView):
    """List user's orders"""

    serializer_class = OrderListSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="List user's orders",
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by order status (pending, processing,confirmed, shipped, delivered, completed, cancelled)",
                required=False,
            ),
            OpenApiParameter(
                name="from_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter orders from this date (YYYY-MM-DD)",
                required=False,
            ),
            OpenApiParameter(
                name="to_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter orders to this date (YYYY-MM-DD)",
                required=False,
            ),
        ],
        responses={200: OrderListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Order.objects.none()

        user = self.request.user

        if user.is_admin_user or user.is_support_user:
            # Admin/support can see all orders with filters
            filters = {
                "status": self.request.query_params.get("status"),
                "from_date": self.request.query_params.get("from_date"),
                "to_date": self.request.query_params.get("to_date"),
            }
            # Remove None values
            filters = {k: v for k, v in filters.items() if v}

            queryset = Order.objects.all()
            if filters.get("status"):
                queryset = queryset.filter(order_status=filters["status"])
            if filters.get("from_date"):
                queryset = queryset.filter(
                    created_at__date__gte=filters["from_date"]
                )
            if filters.get("to_date"):
                queryset = queryset.filter(
                    created_at__date__lte=filters["to_date"]
                )

            return queryset.select_related("user")
        else:
            # Regular users see only their orders
            return OrderService.get_user_orders(user)


class FarmerOrdersView(generics.ListAPIView):
    """List orders containing farmer's products"""

    serializer_class = OrderListSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="List orders containing farmer's products",
        responses={200: OrderListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return Order.objects.none()
        return OrderService.get_farmer_orders(self.request.user)


class OrderDetailView(generics.RetrieveUpdateAPIView):
    """Get or update order details"""

    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]

    @extend_schema(
        description="Get order details by ID",
        responses={200: OrderDetailSerializer()},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        description="Update order status (Admin/Farmer only)",
        request=OrderStatusUpdateSerializer,
        responses={200: OrderDetailSerializer()},
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        description="Partially update order status (Admin/Farmer only)",
        request=OrderStatusUpdateSerializer,
        responses={200: OrderDetailSerializer()},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Order.objects.none()
        return super().get_queryset()

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return OrderStatusUpdateSerializer
        return OrderDetailSerializer


class CancelOrderView(APIView):
    """Cancel order and restore inventory"""

    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]

    @extend_schema(
        description="Cancel order and restore stock",
        responses={200: None},
    )
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)

        result = OrderService.cancel_order(
            order=order, user=request.user, request_ip=get_client_ip(request)
        )

        if result["success"]:
            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class OrderActivityView(generics.ListAPIView):
    """Get order activity log"""

    serializer_class = OrderActivitySerializer
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]

    @extend_schema(
        description="Get order activity log",
        responses={200: OrderActivitySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return OrderActivity.objects.none()

        order_id = self.kwargs.get("order_id")
        if not order_id:
            return OrderActivity.objects.none()
        return OrderActivity.objects.filter(order_id=order_id)


class OrderTrackingView(APIView):
    """Get order tracking information"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        description="Get order tracking by order number",
        responses={200: OrderDetailSerializer()},
    )
    def get(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)
