from django.urls import path
from .views import RegisterAPI, MeAPI, PermissionListAPI, CreateGroupAPI, AssignGroupToUserAPI, SyncBusinessUserAPI


urlpatterns = [
    path("register/", RegisterAPI.as_view()),
    path("me/", MeAPI.as_view()),
    path("permissions/", PermissionListAPI.as_view()),
    path("groups/create/", CreateGroupAPI.as_view()), 
    path("groups/assign/", AssignGroupToUserAPI.as_view()),
    path("sync/", SyncBusinessUserAPI.as_view()),
]
