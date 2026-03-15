from django.urls import path
from .views import (
    RegisterAPI,
    MeAPI,
    PermissionListAPI,
    CreateGroupAPI,
    AssignGroupToUserAPI,
    CustomerListAPI,
    StaffListAPI,
    UpdateUserRoleAPI,
    UpdateUserPermissionsAPI,
    DeleteUserAPI,
)


urlpatterns = [
    path("register/", RegisterAPI.as_view()),
    path("me/", MeAPI.as_view()),
    path("customers/", CustomerListAPI.as_view()),
    path("staff/", StaffListAPI.as_view()),
    path("permissions/", PermissionListAPI.as_view()),
    path("groups/create/", CreateGroupAPI.as_view()), 
    path("groups/assign/", AssignGroupToUserAPI.as_view()),
    path("<int:user_id>/role/", UpdateUserRoleAPI.as_view()),
    path("<int:user_id>/permissions/", UpdateUserPermissionsAPI.as_view()),
    path("<int:user_id>/", DeleteUserAPI.as_view()),
]
