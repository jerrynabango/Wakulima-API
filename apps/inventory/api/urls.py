from django.urls import path
from apps.inventory.api.views import (
    InventoryListView, InventoryDetailView, UpdateStockView,
    StockMovementHistoryView, StockAlertListView, ResolveStockAlertView,
    BulkUpdateStockView, LowStockReportView, StockSummaryView,
    StockAdjustmentView
)

urlpatterns = [
    # Inventory management
    path('inventory/', InventoryListView.as_view(), name='inventory-list'),
    path('inventory/<uuid:product_id>/', InventoryDetailView.as_view(), name='inventory-detail'),
    path('inventory/<uuid:product_id>/update-stock/', UpdateStockView.as_view(), name='update-stock'),
    path('inventory/<uuid:product_id>/adjust-stock/', StockAdjustmentView.as_view(), name='adjust-stock'),
    
    # Bulk operations
    path('inventory/bulk-update/', BulkUpdateStockView.as_view(), name='bulk-update-stock'),
    
    # Reports
    path('inventory/reports/low-stock/', LowStockReportView.as_view(), name='low-stock-report'),
    path('inventory/reports/summary/', StockSummaryView.as_view(), name='stock-summary'),
    
    # History and alerts
    path('inventory/movements/', StockMovementHistoryView.as_view(), name='stock-movements'),
    path('inventory/alerts/', StockAlertListView.as_view(), name='stock-alerts'),
    path('inventory/alerts/<uuid:alert_id>/resolve/', ResolveStockAlertView.as_view(), name='resolve-alert'),
]
