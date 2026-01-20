from django.urls import path
from .views import DashboardStatsAPI, VoucherUsageChartAPI, RevenueChartAPI

urlpatterns = [
    path("stats/", DashboardStatsAPI.as_view()),
    path("chart/usage/", VoucherUsageChartAPI.as_view()),
    path("chart/revenue/", RevenueChartAPI.as_view()),
]
