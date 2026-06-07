from django.urls import path

from apps.products.api.views import (  # Categories; Products; Product Images; Reviews; Inventory
    AddCategoryView,
    AddProductView,
    CategoryDetailView,
    CategoryListView,
    FarmerProductsView,
    FeaturedProductsView,
    InventoryHistoryView,
    ProductDetailView,
    ProductImageView,
    ProductListView,
    ProductReviewListView,
    RelatedProductsView,
    ReorderImagesView,
    SetPrimaryImageView,
    UpdateStockView,
    UploadProductImagesView,
)

urlpatterns = [
    # ========== Categories ==========
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("categories/add/", AddCategoryView.as_view(), name="category-add"),
    path(
        "categories/<uuid:pk>/",
        CategoryDetailView.as_view(),
        name="category-detail",
    ),
    # ========== Products ==========
    path("products/", ProductListView.as_view(), name="product-list"),
    path("products/add/", AddProductView.as_view(), name="product-add"),
    path(
        "products/farmer/",
        FarmerProductsView.as_view(),
        name="farmer-products",
    ),
    path(
        "products/featured/",
        FeaturedProductsView.as_view(),
        name="product-featured",
    ),
    path(
        "products/<uuid:pk>/",
        ProductDetailView.as_view(),
        name="product-detail",
    ),
    path(
        "products/<uuid:pk>/related/",
        RelatedProductsView.as_view(),
        name="product-related",
    ),
    # ========== Product Images - RESTful (same pattern as products) ==========
    # Upload images: POST /products/{id}/images/
    path(
        "products/<uuid:product_id>/images/",
        UploadProductImagesView.as_view(),
        name="upload-images",
    ),
    # Get/Delete single image: GET/DELETE /products/{id}/images/{image_id}/
    path(
        "products/<uuid:product_id>/images/<uuid:image_id>/",
        ProductImageView.as_view(),
        name="product-image",
    ),
    # Set primary image: POST /products/{id}/images/set-primary/
    path(
        "products/<uuid:product_id>/images/set-primary/",
        SetPrimaryImageView.as_view(),
        name="set-primary-image",
    ),
    # Reorder images: POST /products/{id}/images/reorder/
    path(
        "products/<uuid:product_id>/images/reorder/",
        ReorderImagesView.as_view(),
        name="reorder-images",
    ),
    # ========== Product Reviews ==========
    path(
        "products/<uuid:product_id>/reviews/",
        ProductReviewListView.as_view(),
        name="product-reviews",
    ),
    # ========== Inventory Management ==========
    path(
        "inventory/history/",
        InventoryHistoryView.as_view(),
        name="inventory-history",
    ),
    path(
        "products/<uuid:product_id>/stock/",
        UpdateStockView.as_view(),
        name="update-stock",
    ),
]
