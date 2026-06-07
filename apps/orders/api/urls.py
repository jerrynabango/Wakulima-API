from django.urls import path

from apps.orders.api.views import (
    CancelOrderView,
    CreateOrderView,
    FarmerOrdersView,
    OrderActivityView,
    OrderDetailView,
    OrderListView,
    OrderTrackingView,
)

urlpatterns = [
    # Order management
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/create/", CreateOrderView.as_view(), name="order-create"),
    path("orders/farmer/", FarmerOrdersView.as_view(), name="farmer-orders"),
    path("orders/<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path(
        "orders/<uuid:order_id>/cancel/",
        CancelOrderView.as_view(),
        name="order-cancel",
    ),
    path(
        "orders/<uuid:order_id>/activities/",
        OrderActivityView.as_view(),
        name="order-activities",
    ),
    # Tracking (public)
    path(
        "orders/track/<str:order_number>/",
        OrderTrackingView.as_view(),
        name="order-track",
    ),
]
