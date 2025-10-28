from rest_framework.permissions import BasePermission
from django.conf import settings

class HasInternalAPIToken(BasePermission):
    def has_permission(self, request, view):
        expected = getattr(settings, 'API_INTERNAL_TOKEN', None)
        got = request.headers.get('X-Internal-Token')
        return bool(expected) and got == expected
