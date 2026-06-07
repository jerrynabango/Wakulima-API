import logging

from django.db import transaction
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

from apps.inventory.api.serializers import (
    BulkUpdateStockSerializer,
    InventorySerializer,
    StockAdjustmentSerializer,
    StockAlertSerializer,
    StockMovementSerializer,
    UpdateStockSerializer,
)
from apps.inventory.models import Inventory, StockAlert, StockMovement
from apps.inventory.services import (
    InventoryService,
    StockAlertService,
    StockMovementService,
)
from apps.products.models import Product
from apps.products.permissions import IsFarmerOrAdmin

logger = logging.getLogger(__name__)


def is_swagger_request(view):
    """Check if the request is for Swagger schema generation"""
    return getattr(view, "swagger_fake_view", False)


class InventoryListView(generics.ListAPIView):
    """List inventory for farmer's products"""

    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="List all inventory for farmer's products",
        responses={200: InventorySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Inventory.objects.none()

        filters = {
            "status": self.request.query_params.get("status"),
            "low_stock": self.request.query_params.get("low_stock"),
        }
        return InventoryService.get_inventory_for_user(
            self.request.user, filters
        )


class InventoryDetailView(APIView):
    """Get inventory details for a specific product"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Get inventory details for a specific product",
        responses={200: InventorySerializer()},
    )
    def get(self, request, product_id):
        if is_swagger_request(self):
            return Response({"message": "Swagger mock response"})

        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission to view this inventory"},
                status=status.HTTP_403_FORBIDDEN,
            )

        inventory, created = Inventory.objects.get_or_create(product=product)
        serializer = InventorySerializer(
            inventory, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateStockView(APIView):
    """Update product stock level"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Update product stock quantity",
        request=UpdateStockSerializer,
        responses={200: InventorySerializer()},
    )
    def post(self, request, product_id):
        if is_swagger_request(self):
            return Response({"message": "Swagger mock response"})

        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission to update this product"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UpdateStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = InventoryService.update_stock(
            product=product,
            user=request.user,
            new_quantity=serializer.validated_data["quantity"],
            reason=serializer.validated_data.get(
                "reason", "Manual stock update"
            ),
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "inventory": InventorySerializer(
                        result["inventory"], context={"request": request}
                    ).data,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=(
                    status.HTTP_403_FORBIDDEN
                    if "permission" in result["message"].lower()
                    else status.HTTP_400_BAD_REQUEST
                ),
            )


class StockMovementHistoryView(generics.ListAPIView):
    """Get stock movement history for farmer's products"""

    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Get stock movement history for farmer's products",
        responses={200: StockMovementSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return StockMovement.objects.none()

        movement_type = self.request.query_params.get("movement_type")
        return StockMovementService.get_movement_history(
            user=self.request.user, movement_type=movement_type, limit=200
        )


class StockAlertListView(generics.ListAPIView):
    """Get stock alerts for farmer's products"""

    serializer_class = StockAlertSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Get stock alerts for farmer's products",
        responses={200: StockAlertSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return StockAlert.objects.none()

        status_filter = self.request.query_params.get("status")
        return StockAlertService.get_alerts(self.request.user, status_filter)


class ResolveStockAlertView(APIView):
    """Resolve a stock alert"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Resolve a stock alert",
        responses={200: None},
    )
    def post(self, request, alert_id):
        if is_swagger_request(self):
            return Response({"message": "Alert resolved (mock)"})

        alert = get_object_or_404(StockAlert, id=alert_id)

        result = InventoryService.resolve_stock_alert(alert, request.user)

        if result["success"]:
            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_403_FORBIDDEN
            )


class BulkUpdateStockView(APIView):
    """Bulk update stock for multiple products"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Bulk update stock for multiple products",
        request=BulkUpdateStockSerializer,
        responses={200: None},
    )
    def post(self, request):
        if is_swagger_request(self):
            return Response({"message": "Bulk update completed (mock)"})

        serializer = BulkUpdateStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = InventoryService.bulk_update_stock(
            user=request.user, updates=serializer.validated_data["updates"]
        )

        return Response(
            {
                "message": "Bulk update completed",
                "results": result["results"],
                "summary": result["summary"],
            },
            status=status.HTTP_200_OK,
        )


class LowStockReportView(generics.ListAPIView):
    """Get low stock report for farmer"""

    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Get low stock report for farmer",
        responses={200: InventorySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Inventory.objects.none()
        return InventoryService.get_low_stock_report(self.request.user)


class StockSummaryView(APIView):
    """Get stock summary statistics"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Get stock summary statistics",
        responses={200: None},
    )
    def get(self, request):
        if is_swagger_request(self):
            return Response(
                {
                    "total_products": 0,
                    "total_quantity": 0,
                    "low_stock_count": 0,
                    "out_of_stock_count": 0,
                    "stock_value": 0,
                    "healthy_stock_count": 0,
                }
            )

        summary = InventoryService.get_stock_summary(request.user)
        return Response(summary, status=status.HTTP_200_OK)


class StockAdjustmentView(APIView):
    """Add or subtract stock from inventory"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        description="Add or subtract stock from inventory",
        request=StockAdjustmentSerializer,
        responses={200: InventorySerializer()},
    )
    def post(self, request, product_id):
        if is_swagger_request(self):
            return Response({"message": "Stock adjusted (mock)"})

        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = InventoryService.adjust_stock(
            product=product,
            user=request.user,
            quantity=serializer.validated_data["quantity"],
            adjustment_type=serializer.validated_data["adjustment_type"],
            reason=serializer.validated_data["reason"],
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "inventory": InventorySerializer(
                        result["inventory"], context={"request": request}
                    ).data,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
