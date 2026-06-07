import django_filters
from django_filters import rest_framework as filters

from apps.products.models import Product


class ProductFilter(filters.FilterSet):
    """Filter for products"""

    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    category = filters.UUIDFilter(field_name="category__id")
    category_slug = filters.CharFilter(field_name="category__slug")
    is_organic = filters.BooleanFilter(field_name="is_organic")
    is_locally_sourced = filters.BooleanFilter(field_name="is_locally_sourced")
    quality_grade = filters.ChoiceFilter(choices=Product.QualityGrade.choices)
    min_rating = filters.NumberFilter(method="filter_by_min_rating")

    class Meta:
        model = Product
        fields = [
            "category",
            "is_organic",
            "is_locally_sourced",
            "quality_grade",
            "unit_type",
            "status",
        ]

    def filter_by_min_rating(self, queryset, name, value):
        """Filter products by minimum average rating"""
        return queryset.annotate(
            avg_rating=models.Avg("reviews__rating")
        ).filter(avg_rating__gte=value)
