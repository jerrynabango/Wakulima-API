from rest_framework import serializers
from django.db import transaction
from django.utils.text import slugify
from apps.products.models import (
    Category, Product, ProductImage, ProductReview, InventoryHistory
)
from apps.accounts.models import User

class CategorySerializer(serializers.ModelSerializer):
    """Category serializer"""
    subcategories_count = serializers.IntegerField(source='subcategories.count', read_only=True)
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    
    class Meta:
        model = Category
        fields = (
            'id', 'name', 'slug', 'description', 'icon', 'image',
            'parent', 'is_active', 'subcategories_count', 'products_count',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'slug', 'created_at', 'updated_at')

class CategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating categories"""
    
    class Meta:
        model = Category
        fields = ('name', 'description', 'icon', 'image', 'parent', 'is_active')
    
    def validate_name(self, value):
        if Category.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Category with this name already exists")
        return value

class ProductImageSerializer(serializers.ModelSerializer):
    """Product image serializer"""
    
    class Meta:
        model = ProductImage
        fields = ('id', 'image', 'alt_text', 'is_primary', 'order', 'created_at')
        read_only_fields = ('id', 'created_at')

class ProductReviewSerializer(serializers.ModelSerializer):
    """Product review serializer"""
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = ProductReview
        fields = (
            'id', 'user', 'user_name', 'user_email', 'rating', 'title',
            'comment', 'is_verified_purchase', 'is_approved', 'helpful_count',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'is_verified_purchase')
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings"""
    primary_image = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    stock_status = serializers.CharField(read_only=True)
    
    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'price', 'compare_price', 'discount_percentage',
            'unit_type', 'quantity', 'stock_status', 'primary_image',
            'category', 'category_name', 'farmer', 'farmer_name',
            'quality_grade', 'is_organic', 'is_featured', 'views_count',
            'created_at'
        )
    
    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first()
        if primary:
            return self.context['request'].build_absolute_uri(primary.image.url)
        return None

class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single product view"""
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ProductReviewSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    farmer_phone = serializers.CharField(source='farmer.phone_number', read_only=True)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    stock_status = serializers.CharField(read_only=True)
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'compare_price', 'discount_percentage',
            'unit_type', 'quantity', 'stock_status', 'minimum_stock',
            'quality_grade', 'origin', 'harvest_date', 'expiry_date',
            'is_organic', 'is_locally_sourced', 'is_featured', 'is_available',
            'status', 'views_count', 'orders_count',
            'tax_rate', 'weight', 'length', 'width', 'height',
            'images', 'reviews', 'average_rating', 'reviews_count',
            'category', 'category_name', 'farmer', 'farmer_name', 'farmer_phone',
            'created_at', 'updated_at', 'published_at'
        )
        read_only_fields = ('id', 'slug', 'views_count', 'orders_count', 'created_at', 'updated_at')
    
    def get_average_rating(self, obj):
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return 0
    
    def get_reviews_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()

class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products"""
    images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        help_text="Upload multiple images"
    )
    
    class Meta:
        model = Product
        fields = (
            'name', 'description', 'short_description', 'category',
            'price', 'compare_price', 'cost_per_unit', 'unit_type',
            'quantity', 'minimum_stock', 'maximum_stock', 'quality_grade',
            'origin', 'harvest_date', 'expiry_date', 'is_organic',
            'is_locally_sourced', 'is_featured', 'status', 'tax_rate',
            'weight', 'length', 'width', 'height', 'images',
            'meta_title', 'meta_description', 'meta_keywords'
        )
    
    def validate_name(self, value):
        if Product.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Product with this name already exists")
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop('images', [])
        validated_data['farmer'] = self.context['request'].user
        
        product = Product.objects.create(**validated_data)
        
        # Create inventory history entry
        InventoryHistory.objects.create(
            product=product,
            user=self.context['request'].user,
            change_type=InventoryHistory.ChangeType.ADD,
            quantity_change=product.quantity,
            previous_quantity=0,
            new_quantity=product.quantity,
            reason="Initial stock setup"
        )
        
        # Handle image uploads
        for index, image in enumerate(images):
            ProductImage.objects.create(
                product=product,
                image=image,
                is_primary=(index == 0),
                order=index
            )
        
        return product
    
    @transaction.atomic
    def update(self, instance, validated_data):
        images = validated_data.pop('images', None)
        
        # Track quantity change for inventory history
        old_quantity = instance.quantity
        new_quantity = validated_data.get('quantity', old_quantity)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Create inventory history if quantity changed
        if new_quantity != old_quantity:
            InventoryHistory.objects.create(
                product=instance,
                user=self.context['request'].user,
                change_type=InventoryHistory.ChangeType.ADJUSTMENT,
                quantity_change=new_quantity - old_quantity,
                previous_quantity=old_quantity,
                new_quantity=new_quantity,
                reason="Stock adjustment"
            )
        
        # Handle new images
        if images:
            for index, image in enumerate(images):
                ProductImage.objects.create(
                    product=instance,
                    image=image,
                    is_primary=(index == 0 and not instance.images.exists()),
                    order=instance.images.count() + index
                )
        
        return instance

class InventoryHistorySerializer(serializers.ModelSerializer):
    """Inventory history serializer"""
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = InventoryHistory
        fields = (
            'id', 'product', 'product_name', 'user', 'user_name',
            'change_type', 'quantity_change', 'previous_quantity',
            'new_quantity', 'reason', 'reference_id', 'created_at'
        )
        read_only_fields = ('id', 'created_at')
