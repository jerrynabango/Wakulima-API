from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from apps.orders.models import Order, OrderActivity
from apps.orders.api.serializers import (
    OrderListSerializer, OrderDetailSerializer, OrderCreateSerializer,
    OrderStatusUpdateSerializer, OrderActivitySerializer
)
from apps.orders.services import OrderService
from apps.orders.permissions import IsOrderOwnerOrAdmin

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

class CreateOrderView(APIView):
    """Create order from cart"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Create order from current cart",
        request_body=OrderCreateSerializer,
        responses={201: OrderDetailSerializer()}
    )
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = OrderService.create_order_from_cart(
            user=request.user,
            order_data=serializer.validated_data,
            request_ip=get_client_ip(request)
        )
        
        if result['success']:
            order_serializer = OrderDetailSerializer(result['order'])
            return Response(order_serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'error': result['message'], 'details': result.get('errors', {})},
                status=status.HTTP_400_BAD_REQUEST
            )

class OrderListView(generics.ListAPIView):
    """List user's orders"""
    serializer_class = OrderListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_admin_user or user.is_support_user:
            # Admin/support can see all orders with filters
            filters = {
                'status': self.request.query_params.get('status'),
                'from_date': self.request.query_params.get('from_date'),
                'to_date': self.request.query_params.get('to_date')
            }
            # Remove None values
            filters = {k: v for k, v in filters.items() if v}
            
            queryset = Order.objects.all()
            if filters.get('status'):
                queryset = queryset.filter(order_status=filters['status'])
            if filters.get('from_date'):
                queryset = queryset.filter(created_at__date__gte=filters['from_date'])
            if filters.get('to_date'):
                queryset = queryset.filter(created_at__date__lte=filters['to_date'])
            
            return queryset.select_related('user')
        else:
            # Regular users see only their orders
            return OrderService.get_user_orders(user)

class FarmerOrdersView(generics.ListAPIView):
    """List orders containing farmer's products"""
    serializer_class = OrderListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return OrderService.get_farmer_orders(self.request.user)

class OrderDetailView(generics.RetrieveUpdateAPIView):
    """Get or update order details"""
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return OrderStatusUpdateSerializer
        return OrderDetailSerializer

class CancelOrderView(APIView):
    """Cancel order and restore inventory"""
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]
    
    @swagger_auto_schema(
        operation_description="Cancel order and restore stock",
        responses={200: 'Order cancelled'}
    )
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        
        result = OrderService.cancel_order(
            order=order,
            user=request.user,
            request_ip=get_client_ip(request)
        )
        
        if result['success']:
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )

class OrderActivityView(generics.ListAPIView):
    """Get order activity log"""
    serializer_class = OrderActivitySerializer
    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]
    
    def get_queryset(self):
        order_id = self.kwargs['order_id']
        return OrderActivity.objects.filter(order_id=order_id)

class OrderTrackingView(APIView):
    """Get order tracking information"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Get order tracking by order number",
        responses={200: OrderDetailSerializer()}
    )
    def get(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)
