from rest_framework.permissions import BasePermission


class IsStaffOrAdmin(BasePermission):
    message = "Ban khong co quyen truy cap tai nguyen nay"

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) in {"staff", "admin"}
        )
