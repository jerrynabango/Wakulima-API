from django.urls import path
from apps.cart.api.views import (
    GetCartView, AddToCartView, UpdateCartItemView,
    RemoveFromCartView, ClearCartView, CartSummaryView
)

urlpatterns = [
    path('cart/', GetCartView.as_view(), name='cart-detail'),
    path('cart/add/', AddToCartView.as_view(), name='cart-add'),
    path('cart/item/<uuid:item_id>/', UpdateCartItemView.as_view(), name='cart-item-update'),
    path('cart/item/<uuid:item_id>/remove/', RemoveFromCartView.as_view(), name='cart-item-remove'),
    path('cart/clear/', ClearCartView.as_view(), name='cart-clear'),
    path('cart/summary/', CartSummaryView.as_view(), name='cart-summary'),
]
