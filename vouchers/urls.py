from django.urls import path
from .views import (
    ApplyVoucherAPIView,
    ConfirmVoucherUsageAPIView,
    CreateVoucherAPIView,
    DistributeVoucherAPIView,
    CreateAndDistributeVoucherAPIView,
    ProcessOrderSuccessEventAPIView,
    VoucherStatsOverviewAPIView,
    VoucherRevenueChartAPIView,
)

urlpatterns = [
    path("create/", CreateVoucherAPIView.as_view()),
    path("create-and-distribute/", CreateAndDistributeVoucherAPIView.as_view()),
    path("distribute/", DistributeVoucherAPIView.as_view()),
    path("events/order-success/", ProcessOrderSuccessEventAPIView.as_view()),
    path("stats/overview/", VoucherStatsOverviewAPIView.as_view()),
    path("stats/revenue-chart/", VoucherRevenueChartAPIView.as_view()),
    path("apply/", ApplyVoucherAPIView.as_view()),
    path("confirm/", ConfirmVoucherUsageAPIView.as_view()),
]
