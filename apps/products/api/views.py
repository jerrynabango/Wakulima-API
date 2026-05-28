from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.products.models import Product, ProductReview
from apps.products.api.serializers import (
    CategorySerializer, CategoryCreateSerializer,
    ProductListSerializer, ProductDetailSerializer,
    ProductCreateUpdateSerializer, ProductReviewSerializer,
    InventoryHistorySerializer
)
from apps.products.permissions import IsFarmerOrAdmin, IsOwnerOrReadOnly, IsAdminOrReadOnly
from apps.products.filters import ProductFilter
from apps.products.services import CategoryService, ProductService, InventoryService, ReviewService


class CategoryListView(generics.ListCreateAPIView):
    """List all categories or create new category"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAdminOrReadOnly]

    def get_queryset(self):
        parent_id = self.request.query_params.get('parent')
        return CategoryService.get_active_categories(parent_id)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CategoryCreateSerializer
        return CategorySerializer
    
    def perform_create(self, serializer):
        return CategoryService.create_category(serializer.validated_data, self.request.user)


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a category"""
    queryset = CategoryService.get_active_categories()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return CategoryCreateSerializer
        return CategorySerializer
    
    def perform_update(self, serializer):
        return CategoryService.update_category(self.get_object(), serializer.validated_data)
    
    def perform_destroy(self, instance):
        return CategoryService.delete_category(instance)


class ProductListView(generics.ListCreateAPIView):
    """List all products or create new product"""
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'short_description', 'farmer__full_name']
    ordering_fields = ['price', 'created_at', 'quantity', 'views_count', 'orders_count']
    ordering = ['-created_at']

    def get_queryset(self):
        # Build filters from query params
        filters = {
            'featured': self.request.query_params.get('featured'),
            'category': self.request.query_params.get('category'),
            'min_price': self.request.query_params.get('min_price'),
            'max_price': self.request.query_params.get('max_price'),
            'is_organic': self.request.query_params.get('is_organic'),
            'quality_grade': self.request.query_params.get('quality_grade'),
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v}
        
        return ProductService.get_products_for_user(self.request.user, filters)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductCreateUpdateSerializer
        return ProductListSerializer
    
    def perform_create(self, serializer):
        images = self.request.FILES.getlist('images')
        result = ProductService.create_product(
            user=self.request.user,
            product_data=serializer.validated_data,
            images=images
        )
        
        if not result['success']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(result.get('errors', {'error': 'Product creation failed'}))
        
        return result['product']


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product"""
    queryset = Product.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count via service
        ProductService.increment_view_count(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def perform_update(self, serializer):
        images = self.request.FILES.getlist('images')
        result = ProductService.update_product(
            product=self.get_object(),
            product_data=serializer.validated_data,
            user=self.request.user,
            new_images=images
        )
        
        if not result['success']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(result.get('errors', {'error': 'Product update failed'}))
        
        return result['product']
    
    def perform_destroy(self, instance):
        result = ProductService.delete_product(instance, self.request.user)
        if not result['success']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(result.get('errors', {'error': 'Product deletion failed'}))


class ProductReviewListView(generics.ListCreateAPIView):
    """List reviews for a product or create new review"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        product_id = self.kwargs['product_id']
        return ReviewService.get_product_reviews(product_id, approved_only=True)

    def get_serializer_class(self):
        return ProductReviewSerializer

    def perform_create(self, serializer):
        result = ReviewService.create_review(
            user=self.request.user,
            product_id=self.kwargs['product_id'],
            review_data=serializer.validated_data
        )
        
        if not result['success']:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(result.get('errors', {'error': 'Review creation failed'}))
        
        return result['review']


class FarmerProductsView(generics.ListAPIView):
    """List all products for the authenticated farmer"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    def get_queryset(self):
        return Product.objects.filter(farmer=self.request.user).select_related('category')


class InventoryHistoryView(generics.ListAPIView):
    """View inventory change history for farmer's products"""
    serializer_class = InventoryHistorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    def get_queryset(self):
        return InventoryService.get_inventory_history(self.request.user, limit=100)


class UpdateStockView(APIView):
    """Update product stock level"""
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrAdmin]

    @swagger_auto_schema(
        operation_description="Update product stock quantity",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'quantity': openapi.Schema(type=openapi.TYPE_NUMBER, description='New quantity'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Reason for change'),
            },
            required=['quantity']
        )
    )
    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, farmer=request.user)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        new_quantity = request.data.get('quantity')
        reason = request.data.get('reason', 'Manual stock update')

        if new_quantity is None:
            return Response(
                {'error': 'Quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_quantity = float(new_quantity)
        except ValueError:
            return Response(
                {'error': 'Invalid quantity value'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = InventoryService.update_stock(product, request.user, new_quantity, reason)
        
        if result['success']:
            return Response({
                'message': result['message'],
                'product': ProductDetailSerializer(result['product']).data
            })
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class FeaturedProductsView(generics.ListAPIView):
    """Get featured products"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return ProductService.get_featured_products(limit=10)


class RelatedProductsView(generics.ListAPIView):
    """Get related products based on category"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        product_id = self.kwargs['product_id']
        try:
            product = Product.objects.get(id=product_id)
            return ProductService.get_related_products(product, limit=10)
        except Product.DoesNotExist:
            return Product.objects.none()
