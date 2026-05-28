from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count
from apps.products.models import Category, Product, ProductReview, ProductImage, InventoryHistory
import logging

logger = logging.getLogger(__name__)

class CategoryService:
    """Business logic for category operations"""
    
    @staticmethod
    def get_active_categories(parent_id=None):
        """Get active categories, optionally filtered by parent"""
        queryset = Category.objects.filter(is_active=True)
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        return queryset
    
    @staticmethod
    def create_category(data, user):
        """Create a new category"""
        category = Category.objects.create(
            name=data['name'],
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            image=data.get('image'),
            parent=data.get('parent'),
            is_active=data.get('is_active', True)
        )
        logger.info(f"Category {category.name} created by {user.email}")
        return category
    
    @staticmethod
    def update_category(category, data):
        """Update an existing category"""
        for key, value in data.items():
            setattr(category, key, value)
        category.save()
        logger.info(f"Category {category.name} updated")
        return category
    
    @staticmethod
    def delete_category(category):
        """Soft delete category (deactivate) or hard delete if no products"""
        if category.products.exists():
            category.is_active = False
            category.save()
            logger.info(f"Category {category.name} deactivated (has products)")
        else:
            category.delete()
            logger.info(f"Category {category.name} deleted")
        return True


class ProductService:
    """Business logic for product operations"""
    
    @staticmethod
    def get_products_for_user(user, filters=None):
        """
        Get products based on user role and filters
        Returns queryset with proper permissions
        """
        # Base queryset
        if not user.is_authenticated or user.role != 'farmer':
            # Public users see only active, available products
            queryset = Product.objects.filter(
                status=Product.ProductStatus.ACTIVE,
                is_available=True
            )
        elif user.is_farmer:
            # Farmers see their own products (all statuses)
            queryset = Product.objects.filter(farmer=user)
        else:
            # Admin/support see all products
            queryset = Product.objects.all()
        
        # Apply filters
        if filters:
            # Featured filter
            if filters.get('featured') == 'true':
                queryset = queryset.filter(is_featured=True)
            
            # Category filter
            if filters.get('category'):
                queryset = queryset.filter(category_id=filters['category'])
            
            # Price range filter
            if filters.get('min_price'):
                queryset = queryset.filter(price__gte=filters['min_price'])
            if filters.get('max_price'):
                queryset = queryset.filter(price__lte=filters['max_price'])
            
            # Organic filter
            if filters.get('is_organic') is not None:
                queryset = queryset.filter(is_organic=filters['is_organic'])
            
            # Quality grade filter
            if filters.get('quality_grade'):
                queryset = queryset.filter(quality_grade=filters['quality_grade'])
        
        return queryset.select_related('category', 'farmer').prefetch_related('images')
    
    @staticmethod
    def get_featured_products(limit=10):
        """Get featured products"""
        return Product.objects.filter(
            is_featured=True,
            status=Product.ProductStatus.ACTIVE,
            is_available=True
        )[:limit]
    
    @staticmethod
    def get_related_products(product, limit=10):
        """Get related products based on category"""
        return Product.objects.filter(
            category=product.category,
            status=Product.ProductStatus.ACTIVE,
            is_available=True
        ).exclude(id=product.id)[:limit]
    
    @staticmethod
    @transaction.atomic
    def create_product(user, product_data, images=None):
        """
        Create a new product with images
        Returns: {'success': bool, 'product': Product, 'errors': dict}
        """
        try:
            # Validate name uniqueness for this farmer
            if Product.objects.filter(
                name__iexact=product_data['name'],
                farmer=user
            ).exists():
                return {
                    'success': False,
                    'errors': {'name': 'You already have a product with this name'}
                }
            
            # Create product
            product = Product.objects.create(
                farmer=user,
                **product_data
            )
            
            # Create inventory history entry
            InventoryHistory.objects.create(
                product=product,
                user=user,
                change_type=InventoryHistory.ChangeType.ADD,
                quantity_change=product.quantity,
                previous_quantity=0,
                new_quantity=product.quantity,
                reason="Initial stock setup"
            )
            
            # Handle image uploads
            if images:
                for index, image in enumerate(images):
                    ProductImage.objects.create(
                        product=product,
                        image=image,
                        is_primary=(index == 0),
                        order=index
                    )
            
            logger.info(f"Product {product.name} created by farmer {user.email}")
            
            return {
                'success': True,
                'product': product,
                'message': f'Product {product.name} created successfully'
            }
            
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            return {
                'success': False,
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    @transaction.atomic
    def update_product(product, product_data, user, new_images=None):
        """
        Update an existing product
        Returns: {'success': bool, 'product': Product, 'errors': dict}
        """
        try:
            # Track quantity change for inventory history
            old_quantity = product.quantity
            new_quantity = product_data.get('quantity', old_quantity)
            
            # Update product fields
            for key, value in product_data.items():
                setattr(product, key, value)
            product.save()
            
            # Create inventory history if quantity changed
            if new_quantity != old_quantity:
                InventoryHistory.objects.create(
                    product=product,
                    user=user,
                    change_type=InventoryHistory.ChangeType.ADJUSTMENT,
                    quantity_change=new_quantity - old_quantity,
                    previous_quantity=old_quantity,
                    new_quantity=new_quantity,
                    reason="Stock adjustment via product update"
                )
            
            # Handle new images
            if new_images:
                for index, image in enumerate(new_images):
                    ProductImage.objects.create(
                        product=product,
                        image=image,
                        is_primary=(index == 0 and not product.images.exists()),
                        order=product.images.count() + index
                    )
            
            logger.info(f"Product {product.name} updated by {user.email}")
            
            return {
                'success': True,
                'product': product,
                'message': f'Product {product.name} updated successfully'
            }
            
        except Exception as e:
            logger.error(f"Error updating product: {str(e)}")
            return {
                'success': False,
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    def delete_product(product, user):
        """
        Delete a product (soft delete by marking as discontinued)
        Returns: {'success': bool, 'message': str}
        """
        try:
            # Soft delete - mark as discontinued
            product.status = Product.ProductStatus.DISCONTINUED
            product.is_available = False
            product.save()
            
            logger.info(f"Product {product.name} marked as discontinued by {user.email}")
            
            return {
                'success': True,
                'message': f'Product {product.name} has been discontinued'
            }
        except Exception as e:
            logger.error(f"Error deleting product: {str(e)}")
            return {
                'success': False,
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    def increment_view_count(product):
        """Increment product view count"""
        product.views_count += 1
        product.save(update_fields=['views_count'])
        return product
    
    @staticmethod
    def get_product_with_details(product_id):
        """Get product with all related data"""
        return Product.objects.select_related('category', 'farmer').prefetch_related(
            'images', 'reviews'
        ).get(id=product_id)


class InventoryService:
    """Business logic for inventory operations"""
    
    @staticmethod
    def update_stock(product, user, new_quantity, reason=None):
        """
        Update product stock level with history
        Returns: {'success': bool, 'product': Product, 'message': str}
        """
        try:
            old_quantity = product.quantity
            
            if new_quantity < 0:
                return {
                    'success': False,
                    'message': 'Quantity cannot be negative'
                }
            
            product.quantity = new_quantity
            product.save()
            
            # Create inventory history
            InventoryHistory.objects.create(
                product=product,
                user=user,
                change_type=InventoryHistory.ChangeType.ADJUSTMENT,
                quantity_change=new_quantity - old_quantity,
                previous_quantity=old_quantity,
                new_quantity=new_quantity,
                reason=reason or f"Manual stock update from {old_quantity} to {new_quantity}"
            )
            
            logger.info(f"Stock updated for {product.name}: {old_quantity} -> {new_quantity}")
            
            return {
                'success': True,
                'product': product,
                'message': f'Stock updated from {old_quantity} to {new_quantity}'
            }
            
        except Exception as e:
            logger.error(f"Error updating stock: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to update stock: {str(e)}'
            }
    
    @staticmethod
    def get_inventory_history(farmer, limit=100):
        """Get inventory history for farmer's products"""
        return InventoryHistory.objects.filter(
            product__farmer=farmer
        ).select_related('product', 'user')[:limit]


class ReviewService:
    """Business logic for product reviews"""
    
    @staticmethod
    def get_product_reviews(product_id, approved_only=True):
        """Get reviews for a product"""
        queryset = ProductReview.objects.filter(product_id=product_id)
        if approved_only:
            queryset = queryset.filter(is_approved=True)
        return queryset.select_related('user')
    
    @staticmethod
    def create_review(user, product_id, review_data):
        """
        Create a product review
        Returns: {'success': bool, 'review': ProductReview, 'errors': dict}
        """
        try:
            product = get_object_or_404(Product, id=product_id)
            
            # Check if user already reviewed this product
            if ProductReview.objects.filter(product=product, user=user).exists():
                return {
                    'success': False,
                    'errors': {'user': 'You have already reviewed this product'}
                }
            
            review = ProductReview.objects.create(
                product=product,
                user=user,
                rating=review_data['rating'],
                title=review_data['title'],
                comment=review_data['comment'],
                is_verified_purchase=False  # Can be set based on order history
            )
            
            logger.info(f"Review created for {product.name} by {user.email}")
            
            return {
                'success': True,
                'review': review,
                'message': 'Review submitted successfully'
            }
            
        except Exception as e:
            logger.error(f"Error creating review: {str(e)}")
            return {
                'success': False,
                'errors': {'system': str(e)}
            }
    
    @staticmethod
    def get_product_rating(product):
        """Calculate average rating and count for a product"""
        reviews = product.reviews.filter(is_approved=True)
        if reviews.exists():
            return {
                'average_rating': round(reviews.aggregate(Avg('rating'))['rating__avg'], 1),
                'reviews_count': reviews.count()
            }
        return {'average_rating': 0, 'reviews_count': 0}
