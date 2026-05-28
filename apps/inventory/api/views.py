from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.inventory.models import Inventory
from apps.inventory.api.serializers import (
    InventorySerializer, StockMovementSerializer, StockAlertSerializer,
    UpdateStockSerializer, BulkUpdateStockSerializer, StockAdjustmentSerializer
)
from apps.inventory.services import InventoryService, StockMovementService, StockAlertService
from apps.products.models import Product
from apps.products.permissions import IsFarmerOrAdmin
import logging

logger = logging.getLogger(__name__)


class InventoryListView(generics.ListAPIView):
    """List inventory for farmer's products"""
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    def get_queryset(self):
        filters = {
            'status': self.request.query_params.get('status'),
            'low_stock': self.request.query_params.get('low_stock')
        }
        return InventoryService.get_inventory_for_user(self.request.user, filters)


class InventoryDetailView(generics.RetrieveAPIView):
    """Get inventory details for a specific product"""
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_admin_user:
            return Inventory.objects.all()
        return Inventory.objects.filter(product__farmer=user)


class UpdateStockView(APIView):
    """Update stock for a product"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Update product stock",
        request_body=UpdateStockSerializer,
        responses={200: InventorySerializer()}
    )
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        
        serializer = UpdateStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = InventoryService.update_stock(
            product=product,
            user=request.user,
            new_quantity=serializer.validated_data['quantity'],
            reason=serializer.validated_data.get('reason', 'Manual stock update')
        )
        
        if result['success']:
            return Response(InventorySerializer(result['inventory']).data)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_403_FORBIDDEN if 'permission' in result['message'].lower() else status.HTTP_400_BAD_REQUEST
            )


class StockMovementHistoryView(generics.ListAPIView):
    """Get stock movement history for farmer's products"""
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    def get_queryset(self):
        movement_type = self.request.query_params.get('movement_type')
        return StockMovementService.get_movement_history(
            user=self.request.user,
            movement_type=movement_type,
            limit=200
        )


class StockAlertListView(generics.ListAPIView):
    """Get stock alerts for farmer's products"""
    serializer_class = StockAlertSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    def get_queryset(self):
        status_filter = self.request.query_params.get('status')
        return StockAlertService.get_alerts(self.request.user, status_filter)


class ResolveStockAlertView(APIView):
    """Resolve a stock alert"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Resolve a stock alert",
        responses={200: 'Alert resolved'}
    )
    def post(self, request, alert_id):
        from apps.inventory.models import StockAlert
        alert = get_object_or_404(StockAlert, id=alert_id)
        
        result = InventoryService.resolve_stock_alert(alert, request.user)
        
        if result['success']:
            return Response({'message': result['message']})
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_403_FORBIDDEN
            )


class BulkUpdateStockView(APIView):
    """Bulk update stock for multiple products"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Bulk update stock for multiple products",
        request_body=BulkUpdateStockSerializer,
        responses={200: 'Bulk update completed'}
    )
    def post(self, request):
        serializer = BulkUpdateStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = InventoryService.bulk_update_stock(
            user=request.user,
            updates=serializer.validated_data['updates']
        )
        
        return Response({
            'message': 'Bulk update completed',
            'results': result['results'],
            'summary': result['summary']
        })


class LowStockReportView(generics.ListAPIView):
    """Get low stock report for farmer"""
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    def get_queryset(self):
        return InventoryService.get_low_stock_report(self.request.user)


class StockSummaryView(APIView):
    """Get stock summary statistics"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Get stock summary statistics",
        responses={200: 'Stock summary'}
    )
    def get(self, request):
        summary = InventoryService.get_stock_summary(request.user)
        return Response(summary)


class StockAdjustmentView(APIView):
    """Add or subtract stock from inventory"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Add or subtract stock",
        request_body=StockAdjustmentSerializer,
        responses={200: InventorySerializer()}
    )
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = InventoryService.adjust_stock(
            product=product,
            user=request.user,
            quantity=serializer.validated_data['quantity'],
            adjustment_type=serializer.validated_data['adjustment_type'],
            reason=serializer.validated_data['reason']
        )
        
        if result['success']:
            return Response(InventorySerializer(result['inventory']).data)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
