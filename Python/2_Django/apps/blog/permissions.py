# apps/blog/permissions.py
from rest_framework import permissions

class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Read access: anyone (authenticated or not)
    Write access: only the author of the object
    """
    def has_permission(self, request, view):
        # Model-level: allow read always, write only if authenticated
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Object-level: read always, write only if author
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, 'author', None) == request.user