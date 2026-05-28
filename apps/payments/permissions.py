from rest_framework import permissions

class IsPaymentOwnerOrAdmin(permissions.BasePermission):
    """Allow access only to payment owner or admin"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_user or request.user.is_support_user:
            return True
        return obj.user == request.user
