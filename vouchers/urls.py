from django.urls import path
from .views import CreateVoucherAPI, CheckVoucherAPI, SendVoucherEmailAPI, SendVoucherSMSAPI

urlpatterns = [
    path('create/', CreateVoucherAPI.as_view()),
    path('check/', CheckVoucherAPI.as_view()),
    path('send-email/', SendVoucherEmailAPI.as_view()),
    path('send-sms/', SendVoucherSMSAPI.as_view()),
]
