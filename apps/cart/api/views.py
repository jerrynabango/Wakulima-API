from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.cart.api.serializers import (
    CartSerializer, AddToCartSerializer,
    UpdateCartItemSerializer, CartSummarySerializer
)
from apps.cart.services import CartService

class GetCartView(APIView):
    """Get current user's cart"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get user's shopping cart",
        responses={200: CartSerializer()}
    )
    def get(self, request):
        cart = CartService.get_or_create_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

class AddToCartView(APIView):
    """Add item to cart"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Add product to cart",
        request_body=AddToCartSerializer,
        responses={200: CartSerializer()}
    )
    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = CartService.add_to_cart(
            user=request.user,
            product_id=serializer.validated_data['product_id'],
            quantity=serializer.validated_data['quantity']
        )
        
        if result['success']:
            cart_serializer = CartSerializer(result['cart'])
            return Response(cart_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message'], 'details': result.get('errors', {})},
                status=status.HTTP_400_BAD_REQUEST
            )

class UpdateCartItemView(APIView):
    """Update cart item quantity"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Update cart item quantity",
        request_body=UpdateCartItemSerializer,
        responses={200: CartSerializer()}
    )
    def put(self, request, item_id):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = CartService.update_cart_item(
            user=request.user,
            item_id=item_id,
            quantity=serializer.validated_data['quantity']
        )
        
        if result['success']:
            cart_serializer = CartSerializer(result['cart'])
            return Response(cart_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )

class RemoveFromCartView(APIView):
    """Remove item from cart"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Remove item from cart",
        responses={200: CartSerializer()}
    )
    def delete(self, request, item_id):
        result = CartService.remove_cart_item(
            user=request.user,
            item_id=item_id
        )
        
        if result['success']:
            cart_serializer = CartSerializer(result['cart'])
            return Response(cart_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_404_NOT_FOUND
            )

class ClearCartView(APIView):
    """Clear all items from cart"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Clear entire cart",
        responses={200: 'Cart cleared'}
    )
    def delete(self, request):
        result = CartService.clear_cart(request.user)
        return Response({'message': result['message']}, status=status.HTTP_200_OK)

class CartSummaryView(APIView):
    """Get cart summary for checkout"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get cart summary for checkout",
        responses={200: CartSummarySerializer()}
    )
    def get(self, request):
        result = CartService.get_cart_summary(request.user)
        serializer = CartSummarySerializer(result['summary'])
        return Response(serializer.data)
