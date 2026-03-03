from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/orders/", include("orders.urls")),
    path('api/vouchers/', include('vouchers.urls')),
    path("api/users/login/", TokenObtainPairView.as_view()),
    path("api/users/refresh/", TokenRefreshView.as_view()),
    path("api/users/", include("users.urls")),
]
