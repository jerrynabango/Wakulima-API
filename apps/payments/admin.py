from django.contrib import admin
from apps.payments.models import Payment, PaymentWebhook, Refund

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'user', 'amount', 'gateway', 'status', 'created_at')
    list_filter = ('gateway', 'status', 'created_at')
    search_fields = ('order__order_number', 'user__email', 'transaction_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Order Information', {'fields': ('order', 'user', 'amount', 'currency')}),
        ('Payment Details', {'fields': ('gateway', 'status', 'transaction_id', 'gateway_reference')}),
        ('M-Pesa Details', {'fields': ('mpesa_checkout_request_id', 'mpesa_merchant_request_id', 
                                       'mpesa_result_code', 'mpesa_result_desc')}),
        ('PayPal Details', {'fields': ('paypal_order_id', 'paypal_payer_id', 'paypal_payment_id')}),
        ('Customer Information', {'fields': ('customer_phone', 'customer_email')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'paid_at', 'refunded_at')}),
    )

@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = ('gateway', 'event_type', 'processed', 'created_at')
    list_filter = ('gateway', 'processed', 'created_at')
    readonly_fields = ('id', 'created_at')
    search_fields = ('event_type', 'error_message')

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('payment', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    readonly_fields = ('id', 'created_at')
    search_fields = ('payment__order__order_number', 'reason')
