from rest_framework import permissions

class IsFarmerOrAdmin(permissions.BasePermission):
    """Allow access only to farmers or admin users"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'farmer' or 
            request.user.role == 'admin' or
            request.user.is_superuser
        )

class IsOwnerOrReadOnly(permissions.BasePermission):
    """Allow edit only to the product owner (farmer) or admin"""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to the farmer who owns the product or admin
        return obj.farmer == request.user or request.user.role == 'admin'

class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow edit only to admin users"""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'admin'
