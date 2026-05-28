from django.urls import path
from apps.payments.api.views import (
    InitiateMpesaPaymentView, MpesaCallbackView, QueryMpesaPaymentView,
    InitiatePayPalPaymentView, CapturePayPalPaymentView, PayPalWebhookView,
    PaymentHistoryView, InitiateRefundView
)

urlpatterns = [
    # M-Pesa routes
    path('payments/mpesa/initiate/<uuid:order_id>/', 
         InitiateMpesaPaymentView.as_view(), name='mpesa-initiate'),
    path('payments/mpesa/callback/', 
         MpesaCallbackView.as_view(), name='mpesa-callback'),
    path('payments/mpesa/query/<uuid:payment_id>/', 
         QueryMpesaPaymentView.as_view(), name='mpesa-query'),
    
    # PayPal routes
    path('payments/paypal/initiate/<uuid:order_id>/', 
         InitiatePayPalPaymentView.as_view(), name='paypal-initiate'),
    path('payments/paypal/capture/<uuid:payment_id>/', 
         CapturePayPalPaymentView.as_view(), name='paypal-capture'),
    path('payments/paypal/webhook/', 
         PayPalWebhookView.as_view(), name='paypal-webhook'),
    
    # General payment routes
    path('payments/history/', 
         PaymentHistoryView.as_view(), name='payment-history'),
    path('payments/<uuid:payment_id>/refund/', 
         InitiateRefundView.as_view(), name='payment-refund'),
]
