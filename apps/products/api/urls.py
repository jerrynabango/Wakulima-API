from django.urls import path
from apps.products.api.views import (
    CategoryListView, CategoryDetailView,
    ProductListView, ProductDetailView,
    ProductReviewListView, FarmerProductsView,
    InventoryHistoryView, UpdateStockView,
    FeaturedProductsView, RelatedProductsView
)

urlpatterns = [
    # Categories
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<uuid:pk>/', CategoryDetailView.as_view(), name='category-detail'),
    
    # Products
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/featured/', FeaturedProductsView.as_view(), name='product-featured'),
    path('products/farmer/', FarmerProductsView.as_view(), name='farmer-products'),
    path('products/<uuid:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('products/<uuid:pk>/related/', RelatedProductsView.as_view(), name='product-related'),
    
    # Product Reviews
    path('products/<uuid:product_id>/reviews/', ProductReviewListView.as_view(), name='product-reviews'),
    
    # Inventory Management (Farmer only)
    path('inventory/history/', InventoryHistoryView.as_view(), name='inventory-history'),
    path('products/<uuid:product_id>/update-stock/', UpdateStockView.as_view(), name='update-stock'),
]
