from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from apps.products.models import Product

@shared_task
def check_low_stock_products():
    """Check all products for low stock and send alerts"""
    low_stock_products = Product.objects.filter(
        quantity__lte=models.F('minimum_stock'),
        status=Product.ProductStatus.ACTIVE
    ).select_related('farmer')
    
    for product in low_stock_products:
        # Send email to farmer
        send_mail(
            subject=f'Low Stock Alert: {product.name}',
            message=f'Your product {product.name} is running low on stock. Current stock: {product.quantity} {product.unit_type}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[product.farmer.email],
            fail_silently=True,
        )
    
    return f"Checked {low_stock_products.count()} low stock products"

@shared_task
def update_product_search_index():
    """Update search index for products (for future Elasticsearch integration)"""
    # Placeholder for search index update
    pass
