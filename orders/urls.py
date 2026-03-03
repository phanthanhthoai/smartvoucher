from django.urls import path

from .views import CancelOrderAPIView, SyncOrderAPIView

urlpatterns = [
    path("sync/", SyncOrderAPIView.as_view()),
    path("cancel/", CancelOrderAPIView.as_view()),
]
