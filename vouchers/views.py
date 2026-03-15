import json

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from users.permissions import IsStaffOrAdmin

from .models import UserVoucher, Voucher, VoucherEventLog, VoucherUsage
from .serializers import (
    CreateAndDistributeVoucherSerializer,
    CreateVoucherSerializer,
    OrderSuccessEventSerializer,
    UpdateVoucherSerializer,
)
from .services.distribution import (
    assign_voucher_to_user,
    create_distribution_plan,
    distribute_voucher,
    execute_distribution_plan,
    get_target_users,
)
from .services.redemption import calculate_discount_amount, redeem_voucher
from .services.rule_engine import is_voucher_eligible


class _EventOrderItems:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def filter(self, **kwargs):
        product_type = kwargs.get("product_type__iexact")
        if product_type is None:
            return _EventOrderItems(self._items)

        filtered = [
            item for item in self._items
            if (item.get("product_type") or "").lower() == str(product_type).lower()
        ]
        return _EventOrderItems(filtered)

    def exists(self):
        return len(self._items) > 0


class _EventOrder:
    def __init__(self, total_amount, items):
        self.total_amount = total_amount
        self.items = _EventOrderItems(items)


def _get_order_from_request(request):
    order_id = request.data.get("order_id")
    external_order_id = request.data.get("external_order_id")

    if not order_id and not external_order_id:
        return None, Response({"error": "order_id hoac external_order_id la bat buoc"}, status=400)

    try:
        if external_order_id:
            order = Order.objects.get(external_order_id=external_order_id)
        else:
            order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return None, Response({"error": "Order khong ton tai"}, status=404)

    if order.user_id != request.user.id:
        return None, Response({"error": "Ban khong co quyen voi order nay"}, status=403)

    if order.status == Order.STATUS_CANCELED:
        return None, Response({"error": "Order da bi huy"}, status=400)

    return order, None


class ApplyVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("voucher_code")
        if not code:
            return Response({"error": "voucher_code la bat buoc"}, status=400)
        try:
            voucher = Voucher.objects.get(code=code)
        except Voucher.DoesNotExist:
            return Response({"error": "Voucher khong ton tai"}, status=404)

        order, error_response = _get_order_from_request(request)
        if error_response:
            return error_response

        if voucher.expiry_date < timezone.now():
            return Response({"error": "Voucher het han"}, status=400)

        if voucher.used_count >= voucher.quantity:
            return Response({"error": "Voucher da het luot"}, status=400)

        if not is_voucher_eligible(request.user, voucher, order, Order):
            return Response({"error": "Khong du dieu kien"}, status=403)

        return Response({
            "message": "Voucher hop le",
            "discount_preview": calculate_discount_amount(voucher, order),
        })


class ConfirmVoucherUsageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("voucher_code")
        if not code:
            return Response({"error": "voucher_code la bat buoc"}, status=400)
        try:
            voucher = Voucher.objects.get(code=code)
        except Voucher.DoesNotExist:
            return Response({"error": "Voucher khong ton tai"}, status=404)

        order, error_response = _get_order_from_request(request)
        if error_response:
            return error_response

        success, result = redeem_voucher(request.user, voucher, order)

        if not success:
            return Response({"error": result}, status=400)

        return Response({
            "message": "Ap dung voucher thanh cong",
            "discount": result,
        })


class CreateVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        serializer = CreateVoucherSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        voucher = serializer.save()

        return Response(
            {
                "message": "Tao voucher thanh cong",
                "voucher_id": voucher.id,
                "code": voucher.code,
            },
            status=201,
        )


class VoucherDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def patch(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id)

        if voucher.release_date <= timezone.now():
            return Response(
                {"error": "Chi duoc sua voucher khi voucher chua phat hanh"},
                status=400,
            )

        serializer = UpdateVoucherSerializer(voucher, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_voucher = serializer.save()

        return Response(
            {
                "message": "Cap nhat voucher thanh cong",
                "voucher": {
                    "id": updated_voucher.id,
                    "code": updated_voucher.code,
                    "title": updated_voucher.title,
                    "release_date": updated_voucher.release_date,
                    "expiry_date": updated_voucher.expiry_date,
                },
            }
        )

    def delete(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id)

        if voucher.release_date <= timezone.now():
            return Response(
                {"error": "Chi duoc xoa voucher khi voucher chua phat hanh"},
                status=400,
            )

        voucher.delete()
        return Response({"message": "Xoa voucher thanh cong"}, status=200)


class DistributeVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        voucher_id = request.data.get("voucher_id")
        voucher_code = request.data.get("voucher_code")
        user_ids = request.data.get("user_ids")

        if not voucher_id and not voucher_code:
            return Response({"error": "voucher_id hoac voucher_code la bat buoc"}, status=400)

        if voucher_id:
            voucher = Voucher.objects.get(id=voucher_id)
        else:
            voucher = Voucher.objects.get(code=voucher_code)

        users = get_target_users(user_ids=user_ids)
        created, skipped, eligible = distribute_voucher(voucher, users)

        return Response(
            {
                "message": "Phan phoi voucher hoan tat",
                "eligible_users": eligible,
                "assigned": created,
                "already_assigned": skipped,
            }
        )


class CreateAndDistributeVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        serializer = CreateAndDistributeVoucherSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        voucher = serializer.save()
        user_ids = getattr(voucher, "_distribution_user_ids", None)

        plan = create_distribution_plan(voucher, user_ids=user_ids)

        if voucher.release_date <= timezone.now():
            created, skipped, eligible = execute_distribution_plan(plan)
            return Response(
                {
                    "message": "Tao va phan phoi voucher thanh cong",
                    "voucher_id": voucher.id,
                    "code": voucher.code,
                    "release_date": voucher.release_date,
                    "distributed_now": True,
                    "eligible_users": eligible,
                    "assigned": created,
                    "already_assigned": skipped,
                },
                status=201,
            )

        return Response(
            {
                "message": "Tao voucher thanh cong, da len lich phan phoi tu dong",
                "voucher_id": voucher.id,
                "code": voucher.code,
                "release_date": voucher.release_date,
                "distributed_now": False,
                "plan_id": plan.id,
            },
            status=201,
        )


class ProcessOrderSuccessEventAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        serializer = OrderSuccessEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        json_safe_data = json.loads(json.dumps(data, cls=DjangoJSONEncoder))

        event_log, created = VoucherEventLog.objects.get_or_create(
            event_id=data["event_id"],
            defaults={
                "event_type": VoucherEventLog.EVENT_TYPE_ORDER_SUCCESS,
                "order_id": data["order_id"],
                "user_id": data["user_id"],
                "payload": json_safe_data,
            },
        )
        if not created:
            return Response(
                {
                    "message": "Event already processed",
                    "event_id": data["event_id"],
                    "result": event_log.result,
                },
                status=200,
            )

        User = get_user_model()

        try:
            user = User.objects.get(id=data["user_id"])
        except User.DoesNotExist:
            event_log.status = VoucherEventLog.STATUS_SKIPPED
            event_log.result = {"error": "User khong ton tai"}
            event_log.save(update_fields=["status", "result"])
            return Response({"error": "User khong ton tai"}, status=404)

        items = data["items"]
        normalized_items = []
        for item in items:
            normalized_items.append(
                {
                    "name": item.get("name"),
                    "product_type": item.get("product_type"),
                    "quantity": int(item.get("quantity", 0)),
                    "unit_price": float(item.get("unit_price", 0)),
                }
            )

        event_order = _EventOrder(total_amount=data["total_amount"], items=normalized_items)

        vouchers = Voucher.objects.filter(
            event_type="order_success",
            release_date__lte=timezone.now(),
            expiry_date__gte=timezone.now(),
        )

        assigned_codes = []
        skipped_codes = []

        for voucher in vouchers:
            if voucher.used_count >= voucher.quantity:
                skipped_codes.append(voucher.code)
                continue

            if not is_voucher_eligible(user, voucher, event_order, Order):
                skipped_codes.append(voucher.code)
                continue

            created = assign_voucher_to_user(user, voucher)
            if created:
                assigned_codes.append(voucher.code)
            else:
                skipped_codes.append(voucher.code)

        result = {
            "message": "Da xu ly su kien order thanh cong",
            "event_id": data["event_id"],
            "user_id": user.id,
            "order_id": data["order_id"],
            "assigned_count": len(assigned_codes),
            "assigned_vouchers": assigned_codes,
            "skipped_vouchers": skipped_codes,
        }
        event_log.status = VoucherEventLog.STATUS_PROCESSED
        event_log.result = result
        event_log.save(update_fields=["status", "result"])
        return Response(result)


def _get_date_range(request):
    start_date = parse_date(request.query_params.get("start_date", ""))
    end_date = parse_date(request.query_params.get("end_date", ""))
    return start_date, end_date


def _get_usage_queryset(start_date=None, end_date=None):
    usage_qs = VoucherUsage.objects.select_related("user_voucher", "user_voucher__voucher")
    if start_date:
        usage_qs = usage_qs.filter(used_at__date__gte=start_date)
    if end_date:
        usage_qs = usage_qs.filter(used_at__date__lte=end_date)
    return usage_qs


def _get_voucher_status(voucher, now=None):
    now = now or timezone.now()
    if voucher.expiry_date < now:
        return "expired"
    if voucher.release_date > now:
        return "scheduled"
    if voucher.used_count >= voucher.quantity:
        return "exhausted"
    return "active"


def _build_voucher_recipient_rows(voucher):
    user_vouchers = (
        UserVoucher.objects.filter(voucher=voucher)
        .select_related("user")
        .order_by("-assigned_at")
    )

    rows = []
    for user_voucher in user_vouchers:
        user = user_voucher.user
        rows.append(
            {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_used": user_voucher.is_used,
                "assigned_at": user_voucher.assigned_at,
                "used_at": user_voucher.used_at,
            }
        )

    return rows


def _build_voucher_performance_rows(start_date=None, end_date=None):
    vouchers = list(Voucher.objects.all().order_by("-created_at"))
    voucher_ids = [voucher.id for voucher in vouchers]
    assigned_counts = {
        row["voucher_id"]: row["assigned_count"]
        for row in UserVoucher.objects.filter(voucher_id__in=voucher_ids)
        .values("voucher_id")
        .annotate(assigned_count=Count("id"))
    }

    usage_qs = _get_usage_queryset(start_date, end_date).filter(
        user_voucher__voucher_id__in=voucher_ids
    )
    usage_summary = {
        row["user_voucher__voucher_id"]: {
            "usage_count": row["usage_count"],
            "total_discount_amount": row["total_discount_amount"] or 0,
        }
        for row in usage_qs
        .values("user_voucher__voucher_id")
        .annotate(
            usage_count=Count("id"),
            total_discount_amount=Sum("discount_amount"),
        )
    }

    voucher_order_ids = defaultdict(set)
    for row in usage_qs.values("user_voucher__voucher_id", "order_id"):
        voucher_order_ids[row["user_voucher__voucher_id"]].add(row["order_id"])

    all_order_ids = {
        order_id
        for order_ids in voucher_order_ids.values()
        for order_id in order_ids
    }
    order_amounts = {
        order.id: order.total_amount
        for order in Order.objects.filter(id__in=all_order_ids)
    }

    now = timezone.now()
    rows = []
    for voucher in vouchers:
        assigned_count = assigned_counts.get(voucher.id, 0)
        summary = usage_summary.get(voucher.id, {})
        usage_count = summary.get("usage_count", 0)
        total_discount_amount = summary.get("total_discount_amount", 0)
        revenue_impacted = round(
            sum(
                order_amounts.get(order_id, 0)
                for order_id in voucher_order_ids.get(voucher.id, set())
            ),
            2,
        )
        usage_rate = round((usage_count / assigned_count) * 100, 2) if assigned_count else 0

        rows.append(
            {
                "voucher_id": voucher.id,
                "code": voucher.code,
                "title": voucher.title,
                "status": _get_voucher_status(voucher, now=now),
                "release_date": voucher.release_date,
                "expiry_date": voucher.expiry_date,
                "quantity": voucher.quantity,
                "used_count": voucher.used_count,
                "remaining_quantity": max(voucher.quantity - voucher.used_count, 0),
                "assigned_count": assigned_count,
                "usage_count": usage_count,
                "usage_rate_percent": usage_rate,
                "total_discount_amount": total_discount_amount,
                "revenue_impacted": revenue_impacted,
            }
        )

    return rows


class VoucherStatsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        total_vouchers = Voucher.objects.count()
        total_assigned = UserVoucher.objects.count()
        total_used = VoucherUsage.objects.count()
        total_discount = VoucherUsage.objects.aggregate(total=Sum("discount_amount"))["total"] or 0
        total_revenue = Order.objects.aggregate(total=Sum("total_amount"))["total"] or 0
        usage_rate = round((total_used / total_assigned) * 100, 2) if total_assigned else 0

        return Response(
            {
                "total_vouchers": total_vouchers,
                "total_assigned": total_assigned,
                "total_used": total_used,
                "usage_rate_percent": usage_rate,
                "total_discount_amount": total_discount,
                "gross_revenue": total_revenue,
                "net_revenue": total_revenue - total_discount,
            }
        )


class VoucherRecipientListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id)
        recipients = _build_voucher_recipient_rows(voucher)

        return Response(
            {
                "voucher": {
                    "id": voucher.id,
                    "code": voucher.code,
                    "title": voucher.title,
                    "quantity": voucher.quantity,
                    "used_count": voucher.used_count,
                    "recipient_count": len(recipients),
                },
                "results": recipients,
            }
        )


class VoucherRecipientPageView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id)
        recipients = _build_voucher_recipient_rows(voucher)

        return render(
            request,
            "vouchers/recipient_list.html",
            {
                "voucher": voucher,
                "recipients": recipients,
            },
        )


class VoucherRevenueChartAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        group_by = request.query_params.get("group_by", "day")
        trunc_map = {
            "day": TruncDay,
            "week": TruncWeek,
            "month": TruncMonth,
        }
        trunc_func = trunc_map.get(group_by, TruncDay)

        start_date, end_date = _get_date_range(request)
        usage_qs = _get_usage_queryset(start_date, end_date)

        chart_rows = (
            usage_qs
            .annotate(period=trunc_func("used_at"))
            .values("period")
            .annotate(
                usage_count=Count("id"),
                discount_amount=Sum("discount_amount"),
            )
            .order_by("period")
        )

        chart = [
            {
                "period": row["period"],
                "usage_count": row["usage_count"],
                "discount_amount": row["discount_amount"] or 0,
            }
            for row in chart_rows
        ]

        return Response(
            {
                "group_by": group_by,
                "start_date": start_date,
                "end_date": end_date,
                "chart": chart,
            }
        )


class VoucherPerformanceAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        start_date, end_date = _get_date_range(request)
        ordering = request.query_params.get("ordering", "-usage_count")
        performance = _build_voucher_performance_rows(start_date, end_date)

        ordering_map = {
            "code": ("code", False),
            "-code": ("code", True),
            "assigned_count": ("assigned_count", False),
            "-assigned_count": ("assigned_count", True),
            "usage_count": ("usage_count", False),
            "-usage_count": ("usage_count", True),
            "usage_rate_percent": ("usage_rate_percent", False),
            "-usage_rate_percent": ("usage_rate_percent", True),
            "total_discount_amount": ("total_discount_amount", False),
            "-total_discount_amount": ("total_discount_amount", True),
            "revenue_impacted": ("revenue_impacted", False),
            "-revenue_impacted": ("revenue_impacted", True),
            "expiry_date": ("expiry_date", False),
            "-expiry_date": ("expiry_date", True),
            "release_date": ("release_date", False),
            "-release_date": ("release_date", True),
        }
        sort_key, reverse = ordering_map.get(ordering, ("usage_count", True))
        performance.sort(key=lambda row: row[sort_key], reverse=reverse)

        return Response(
            {
                "start_date": start_date,
                "end_date": end_date,
                "ordering": ordering,
                "count": len(performance),
                "results": performance,
            }
        )


class VoucherTopStatsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        start_date, end_date = _get_date_range(request)
        limit = request.query_params.get("limit", "5")
        try:
            limit = max(int(limit), 1)
        except ValueError:
            limit = 5

        performance = _build_voucher_performance_rows(start_date, end_date)
        most_used = sorted(
            performance,
            key=lambda row: (row["usage_count"], row["total_discount_amount"], row["assigned_count"]),
            reverse=True,
        )[:limit]
        highest_usage_rate = sorted(
            [row for row in performance if row["assigned_count"] > 0],
            key=lambda row: (row["usage_rate_percent"], row["usage_count"], row["assigned_count"]),
            reverse=True,
        )[:limit]
        highest_discount = sorted(
            performance,
            key=lambda row: (row["total_discount_amount"], row["usage_count"]),
            reverse=True,
        )[:limit]
        highest_revenue = sorted(
            performance,
            key=lambda row: (row["revenue_impacted"], row["usage_count"]),
            reverse=True,
        )[:limit]

        return Response(
            {
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
                "top_vouchers": {
                    "most_used": most_used,
                    "highest_usage_rate": highest_usage_rate,
                    "highest_discount_amount": highest_discount,
                    "highest_revenue_impacted": highest_revenue,
                },
            }
        )

