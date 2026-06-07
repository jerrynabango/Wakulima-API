from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.accounts.models import User
from apps.products.models import (
    Category,
    InventoryHistory,
    Product,
    ProductImage,
    ProductReview,
)


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer"""

    subcategories_count = serializers.IntegerField(
        source="subcategories.count", read_only=True
    )
    products_count = serializers.IntegerField(
        source="products.count", read_only=True
    )

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "image",
            "parent",
            "is_active",
            "subcategories_count",
            "products_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class CategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating categories"""

    class Meta:
        model = Category
        fields = (
            "name",
            "description",
            "icon",
            "image",
            "parent",
            "is_active",
        )

    def validate_name(self, value):
        if Category.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(
                "Category with this name already exists"
            )
        return value


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image serializer"""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "image",
            "image_url",
            "alt_text",
            "is_primary",
            "order",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url if obj.image else None


class ProductReviewSerializer(serializers.ModelSerializer):
    """Product review serializer"""

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = ProductReview
        fields = (
            "id",
            "user",
            "user_name",
            "user_email",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "is_approved",
            "helpful_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "created_at",
            "updated_at",
            "is_verified_purchase",
        )

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings"""

    primary_image = serializers.SerializerMethodField()
    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    farmer_name = serializers.CharField(
        source="farmer.full_name", read_only=True
    )
    discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    stock_status = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "price",
            "compare_price",
            "discount_percentage",
            "unit_type",
            "quantity",
            "stock_status",
            "primary_image",
            "category",
            "category_name",
            "farmer",
            "farmer_name",
            "quality_grade",
            "is_organic",
            "is_featured",
            "views_count",
            "created_at",
        )

    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first()
        if primary and primary.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(primary.image.url)
            return primary.image.url
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single product view"""

    images = serializers.SerializerMethodField()
    reviews = ProductReviewSerializer(many=True, read_only=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    farmer_name = serializers.CharField(
        source="farmer.full_name", read_only=True
    )
    farmer_phone = serializers.CharField(
        source="farmer.phone_number", read_only=True
    )
    discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    stock_status = serializers.CharField(read_only=True)
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "short_description",
            "price",
            "compare_price",
            "discount_percentage",
            "unit_type",
            "quantity",
            "stock_status",
            "minimum_stock",
            "quality_grade",
            "origin",
            "harvest_date",
            "expiry_date",
            "is_organic",
            "is_locally_sourced",
            "is_featured",
            "is_available",
            "status",
            "views_count",
            "orders_count",
            "tax_rate",
            "weight",
            "length",
            "width",
            "height",
            "images",
            "reviews",
            "average_rating",
            "reviews_count",
            "category",
            "category_name",
            "farmer",
            "farmer_name",
            "farmer_phone",
            "created_at",
            "updated_at",
            "published_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "views_count",
            "orders_count",
            "created_at",
            "updated_at",
        )

    def get_images(self, obj):
        request = self.context.get("request")
        serializer = ProductImageSerializer(
            obj.images.all(), many=True, context={"request": request}
        )
        return serializer.data

    def get_average_rating(self, obj):
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            return round(
                reviews.aggregate(models.Avg("rating"))["rating__avg"], 1
            )
        return 0

    def get_reviews_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class ProductCreateSerializer(serializers.ModelSerializer):
    """JSON-only serializer for creating products (no images)"""

    class Meta:
        model = Product
        fields = (
            "name",
            "description",
            "short_description",
            "category",
            "price",
            "compare_price",
            "cost_per_unit",
            "unit_type",
            "quantity",
            "minimum_stock",
            "maximum_stock",
            "quality_grade",
            "origin",
            "harvest_date",
            "expiry_date",
            "is_organic",
            "is_locally_sourced",
            "is_featured",
            "status",
            "tax_rate",
            "weight",
            "length",
            "width",
            "height",
            "meta_title",
            "meta_description",
            "meta_keywords",
        )

    def validate_name(self, value):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            if Product.objects.filter(
                name__iexact=value, farmer=request.user
            ).exists():
                raise serializers.ValidationError(
                    "You already have a product with this name"
                )
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative")
        return value

    @transaction.atomic
    def create(self, validated_data):
        validated_data["farmer"] = self.context["request"].user
        product = Product.objects.create(**validated_data)

        # Create inventory history entry
        InventoryHistory.objects.create(
            product=product,
            user=self.context["request"].user,
            change_type=InventoryHistory.ChangeType.ADD,
            quantity_change=product.quantity,
            previous_quantity=0,
            new_quantity=product.quantity,
            reason="Initial stock setup",
        )

        return product


class ProductUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating products"""

    class Meta:
        model = Product
        fields = (
            "name",
            "description",
            "short_description",
            "category",
            "price",
            "compare_price",
            "cost_per_unit",
            "unit_type",
            "quantity",
            "minimum_stock",
            "maximum_stock",
            "quality_grade",
            "origin",
            "harvest_date",
            "expiry_date",
            "is_organic",
            "is_locally_sourced",
            "is_featured",
            "status",
            "tax_rate",
            "weight",
            "length",
            "width",
            "height",
            "meta_title",
            "meta_description",
            "meta_keywords",
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        old_quantity = instance.quantity
        new_quantity = validated_data.get("quantity", old_quantity)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Create inventory history if quantity changed
        if new_quantity != old_quantity:
            InventoryHistory.objects.create(
                product=instance,
                user=self.context["request"].user,
                change_type=InventoryHistory.ChangeType.ADJUSTMENT,
                quantity_change=new_quantity - old_quantity,
                previous_quantity=old_quantity,
                new_quantity=new_quantity,
                reason="Stock adjustment via product update",
            )

        return instance


class UploadProductImageSerializer(serializers.Serializer):
    """Serializer for uploading product images"""

    images = serializers.ListField(
        child=serializers.ImageField(),
        required=True,
        help_text="Upload one or more images",
    )

    def validate_images(self, value):
        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 images per product")

        for image in value:
            if image.size > 5 * 1024 * 1024:  # 5MB
                raise serializers.ValidationError(
                    f"Image {image.name} exceeds 5MB limit"
                )

        return value


class SetPrimaryImageSerializer(serializers.Serializer):
    """Serializer for setting primary image"""

    image_id = serializers.UUIDField(required=True)


class ReorderImagesSerializer(serializers.Serializer):
    """Serializer for reordering images"""

    image_order = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        help_text="List of image IDs in desired order",
    )


class InventoryHistorySerializer(serializers.ModelSerializer):
    """Inventory history serializer"""

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = InventoryHistory
        fields = (
            "id",
            "product",
            "product_name",
            "user",
            "user_name",
            "change_type",
            "quantity_change",
            "previous_quantity",
            "new_quantity",
            "reason",
            "reference_id",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
