from rest_framework import permissions


class IsOrderOwnerOrAdmin(permissions.BasePermission):
    """Allow access only to order owner or admin"""

    def has_object_permission(self, request, view, obj):
        # Admin can access any order
        if request.user.is_admin_user or request.user.is_support_user:
            return True

        # Order owner can access their own order
        return obj.user == request.user
