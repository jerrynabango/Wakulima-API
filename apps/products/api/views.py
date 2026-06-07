import logging

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.api.serializers import (
    CategoryCreateSerializer,
    CategorySerializer,
    InventoryHistorySerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductUpdateSerializer,
    ReorderImagesSerializer,
    SetPrimaryImageSerializer,
    UploadProductImageSerializer,
)
from apps.products.filters import ProductFilter
from apps.products.models import (
    Category,
    InventoryHistory,
    Product,
    ProductImage,
    ProductReview,
)
from apps.products.permissions import (
    IsAdminOrReadOnly,
    IsFarmerOrAdmin,
    IsOwnerOrReadOnly,
)
from apps.products.services import (
    CategoryService,
    InventoryService,
    ProductService,
    ReviewService,
)

logger = logging.getLogger(__name__)


# ========== Helper function for Swagger ==========
def is_swagger_request(view):
    """Check if the request is for Swagger schema generation"""
    return getattr(view, "swagger_fake_view", False)


# ========== Category Views (Grouped under Products tag) ==========


class CategoryListView(generics.ListAPIView):
    """List all categories (GET only)"""

    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Products"],
        description="Get all product categories. Use parent parameter to filter by parent category.",
        responses={200: CategorySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Category.objects.none()
        parent_id = self.request.query_params.get("parent")
        return CategoryService.get_active_categories(parent_id)


class AddCategoryView(generics.CreateAPIView):
    """Create a new category (Admin only)"""

    serializer_class = CategoryCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

    @extend_schema(
        tags=["Products"],
        description="Create a new product category (Admin only)",
        request=CategoryCreateSerializer,
        responses={201: CategorySerializer()},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        return CategoryService.create_category(
            serializer.validated_data, self.request.user
        )


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a category"""

    queryset = CategoryService.get_active_categories()
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsAdminOrReadOnly,
    ]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return CategoryCreateSerializer
        return CategorySerializer

    def get_queryset(self):
        if is_swagger_request(self):
            return Category.objects.none()
        return super().get_queryset()

    @extend_schema(
        tags=["Products"],
        description="Get category details by ID",
        responses={200: CategorySerializer()},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Update a category (Admin only)",
        request=CategoryCreateSerializer,
        responses={200: CategorySerializer()},
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Partially update a category (Admin only)",
        request=CategoryCreateSerializer,
        responses={200: CategorySerializer()},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Delete a category (Admin only)",
        responses={204: None},
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def perform_update(self, serializer):
        return CategoryService.update_category(
            self.get_object(), serializer.validated_data
        )

    def perform_destroy(self, instance):
        return CategoryService.delete_category(instance)


# ========== Product Views ==========


class ProductListView(generics.ListAPIView):
    """List all products (GET only)"""

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "name",
        "description",
        "short_description",
        "farmer__full_name",
    ]
    ordering_fields = [
        "price",
        "created_at",
        "quantity",
        "views_count",
        "orders_count",
    ]
    ordering = ["-created_at"]
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Products"],
        description="Get list of products with filtering, searching, and ordering",
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_filterset_class(self):
        if is_swagger_request(self):
            return None
        return ProductFilter

    def get_queryset(self):
        if is_swagger_request(self):
            return Product.objects.none()

        filters = {
            "featured": self.request.query_params.get("featured"),
            "category": self.request.query_params.get("category"),
            "min_price": self.request.query_params.get("min_price"),
            "max_price": self.request.query_params.get("max_price"),
            "is_organic": self.request.query_params.get("is_organic"),
            "quality_grade": self.request.query_params.get("quality_grade"),
        }
        filters = {k: v for k, v in filters.items() if v}

        user = (
            self.request.user if self.request.user.is_authenticated else None
        )
        return ProductService.get_products_for_user(user, filters)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AddProductView(APIView):
    """
    Create a new product (JSON only)
    Images are uploaded separately via /products/{id}/images/
    """

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Products"],
        description="Create a new product (Farmer or Admin only)",
        request=ProductCreateSerializer,
        responses={201: ProductDetailSerializer()},
    )
    def post(self, request):
        serializer = ProductCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        detail_serializer = ProductDetailSerializer(
            product, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product"""

    queryset = Product.objects.all()
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly,
    ]

    @extend_schema(
        tags=["Products"],
        description="Get product details by ID",
        responses={200: ProductDetailSerializer()},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Update a product (Owner or Admin only)",
        request=ProductUpdateSerializer,
        responses={200: ProductDetailSerializer()},
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Partially update a product (Owner or Admin only)",
        request=ProductUpdateSerializer,
        responses={200: ProductDetailSerializer()},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Delete a product (Soft delete - marks as discontinued)",
        responses={204: None},
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return ProductUpdateSerializer
        return ProductDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        if is_swagger_request(self):
            return Product.objects.none()
        return super().get_queryset()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        ProductService.increment_view_count(instance)
        serializer = self.get_serializer(
            instance, context={"request": request}
        )
        return Response(serializer.data)

    def perform_update(self, serializer):
        return serializer.save()

    def perform_destroy(self, instance):
        result = ProductService.delete_product(instance, self.request.user)
        if not result["success"]:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                result.get("errors", {"error": "Product deletion failed"})
            )


class FarmerProductsView(generics.ListAPIView):
    """List all products for the authenticated farmer"""

    serializer_class = ProductListSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Products"],
        description="Get all products for the authenticated farmer",
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Product.objects.none()
        return Product.objects.filter(farmer=self.request.user).select_related(
            "category"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class FeaturedProductsView(generics.ListAPIView):
    """Get featured products"""

    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Products"],
        description="Get featured products (limit 10)",
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Product.objects.none()
        return ProductService.get_featured_products(limit=10)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class RelatedProductsView(generics.ListAPIView):
    """Get related products based on category"""

    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Products"],
        description="Get products related to a specific product (based on category)",
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return Product.objects.none()

        product_id = self.kwargs.get("product_id")
        if not product_id:
            return Product.objects.none()

        try:
            product = Product.objects.get(id=product_id)
            return ProductService.get_related_products(product, limit=10)
        except Product.DoesNotExist:
            return Product.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


# ========== Product Image Views ==========


class UploadProductImagesView(APIView):
    """
    Upload images for a product
    POST /products/{id}/images/
    """

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Products"],
        description="Upload one or more images for a product (multipart/form-data)",
        request=UploadProductImageSerializer,
        responses={200: ProductDetailSerializer()},
    )
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {
                    "error": "You do not have permission to upload images for this product"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UploadProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        images = serializer.validated_data["images"]
        uploaded_images = []
        has_existing_images = product.images.exists()

        for index, image in enumerate(images):
            is_primary = not has_existing_images and index == 0

            product_image = ProductImage.objects.create(
                product=product,
                image=image,
                is_primary=is_primary,
                order=product.images.count() + index,
            )
            uploaded_images.append(product_image)

        if not has_existing_images and uploaded_images:
            primary_count = product.images.filter(is_primary=True).count()
            if primary_count != 1:
                product.images.update(is_primary=False)
                first_image = product.images.first()
                if first_image:
                    first_image.is_primary = True
                    first_image.save(update_fields=["is_primary"])

        detail_serializer = ProductDetailSerializer(
            product, context={"request": request}
        )
        return Response(
            {
                "message": f"Successfully uploaded {len(uploaded_images)} images",
                "product": detail_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ProductImageView(APIView):
    """
    Handle individual product image operations (RESTful)
    - GET: Get image details
    - DELETE: Delete the image
    """

    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsFarmerOrAdmin,
    ]

    @extend_schema(
        tags=["Products"],
        description="Get a single product image by ID",
        responses={200: ProductImageSerializer()},
    )
    def get(self, request, product_id, image_id):
        product = get_object_or_404(Product, id=product_id)
        image = get_object_or_404(ProductImage, id=image_id, product=product)

        serializer = ProductImageSerializer(
            image, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Products"],
        description="Delete a product image",
        responses={200: None},
    )
    def delete(self, request, product_id, image_id):
        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        image = get_object_or_404(ProductImage, id=image_id, product=product)
        was_primary = image.is_primary

        image.delete()

        if was_primary:
            first_image = product.images.first()
            if first_image:
                first_image.is_primary = True
                first_image.save()

        for index, img in enumerate(product.images.all()):
            img.order = index
            img.save()

        return Response(
            {"message": "Image deleted successfully"},
            status=status.HTTP_200_OK,
        )


class SetPrimaryImageView(APIView):
    """Set an image as the primary image for a product"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Products"],
        description="Set an image as the primary image for a product",
        request=SetPrimaryImageSerializer,
        responses={200: ProductDetailSerializer()},
    )
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SetPrimaryImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image_id = serializer.validated_data["image_id"]
        image = get_object_or_404(ProductImage, id=image_id, product=product)

        product.images.update(is_primary=False)
        image.is_primary = True
        image.save()

        detail_serializer = ProductDetailSerializer(
            product, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class ReorderImagesView(APIView):
    """Reorder product images"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Products"],
        description="Reorder product images by providing a list of image IDs in desired order",
        request=ReorderImagesSerializer,
        responses={200: ProductDetailSerializer()},
    )
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReorderImagesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image_order = serializer.validated_data["image_order"]
        existing_ids = set(product.images.values_list("id", flat=True))

        if set(image_order) != existing_ids:
            return Response(
                {"error": "Invalid image IDs provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for index, image_id in enumerate(image_order):
            ProductImage.objects.filter(id=image_id, product=product).update(
                order=index
            )

        if image_order:
            product.images.update(is_primary=False)
            ProductImage.objects.filter(
                id=image_order[0], product=product
            ).update(is_primary=True)

        detail_serializer = ProductDetailSerializer(
            product, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


# ========== Review Views ==========


class ProductReviewListView(generics.ListCreateAPIView):
    """List reviews for a product or create new review"""

    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Products"],
        description="Get all reviews for a product",
        responses={200: ProductReviewSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["Products"],
        description="Create a new review for a product",
        request=ProductReviewSerializer,
        responses={201: ProductReviewSerializer()},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return ProductReview.objects.none()

        product_id = self.kwargs.get("product_id")
        if not product_id:
            return ProductReview.objects.none()

        return ReviewService.get_product_reviews(
            product_id, approved_only=True
        )

    def perform_create(self, serializer):
        result = ReviewService.create_review(
            user=self.request.user,
            product_id=self.kwargs["product_id"],
            review_data=serializer.validated_data,
        )

        if not result["success"]:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                result.get("errors", {"error": "Review creation failed"})
            )

        return result["review"]


# ========== Inventory Views ==========


class InventoryHistoryView(generics.ListAPIView):
    """View inventory change history for farmer's products"""

    serializer_class = InventoryHistorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    filter_backends = []

    @extend_schema(
        tags=["Inventory"],
        description="Get inventory change history for farmer's products",
        responses={200: InventoryHistorySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if is_swagger_request(self):
            return InventoryHistory.objects.none()
        return InventoryService.get_inventory_history(
            self.request.user, limit=100
        )


class UpdateStockView(APIView):
    """Update product stock level"""

    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @extend_schema(
        tags=["Inventory"],
        description="Update product stock quantity",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "quantity": {
                        "type": "number",
                        "description": "New quantity",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for change",
                    },
                },
                "required": ["quantity"],
            }
        },
        responses={200: ProductDetailSerializer()},
    )
    def post(self, request, product_id):
        if is_swagger_request(self):
            return Response({"message": "Stock update (mock)"})

        product = get_object_or_404(Product, id=product_id)

        if not request.user.is_admin_user and product.farmer != request.user:
            return Response(
                {"error": "You do not have permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        new_quantity = request.data.get("quantity")
        reason = request.data.get("reason", "Manual stock update")

        if new_quantity is None:
            return Response(
                {"error": "Quantity is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_quantity = float(new_quantity)
        except ValueError:
            return Response(
                {"error": "Invalid quantity value"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = InventoryService.update_stock(
            product, request.user, new_quantity, reason
        )

        if result["success"]:
            detail_serializer = ProductDetailSerializer(
                result["product"], context={"request": request}
            )
            return Response(
                {
                    "message": result["message"],
                    "product": detail_serializer.data,
                }
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
