from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count
from django.utils.timezone import now, timedelta

from vouchers.models import Voucher, VoucherUsage


class DashboardStatsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total_vouchers = Voucher.objects.count()
        active_vouchers = Voucher.objects.filter(is_active=True).count()
        total_usage = VoucherUsage.objects.count()
        total_revenue = VoucherUsage.objects.aggregate(
            total=Sum("final_price")
        )["total"] or 0

        return Response({
            "total_vouchers": total_vouchers,
            "active_vouchers": active_vouchers,
            "total_usage": total_usage,
            "total_revenue": float(total_revenue)
        })


class VoucherUsageChartAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        last_7_days = now() - timedelta(days=7)

        data = (
            VoucherUsage.objects
            .filter(created_at__gte=last_7_days)
            .extra(select={"day": "date(created_at)"})
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        return Response(list(data))


class RevenueChartAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        last_7_days = now() - timedelta(days=7)

        data = (
            VoucherUsage.objects
            .filter(created_at__gte=last_7_days)
            .extra(select={"day": "date(created_at)"})
            .values("day")
            .annotate(revenue=Sum("final_price"))
            .order_by("day")
        )

        return Response(list(data))
