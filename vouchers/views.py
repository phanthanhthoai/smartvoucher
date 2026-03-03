import json

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order

from .models import UserVoucher, Voucher, VoucherEventLog, VoucherUsage
from .serializers import (
    CreateAndDistributeVoucherSerializer,
    CreateVoucherSerializer,
    OrderSuccessEventSerializer,
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
    permission_classes = [IsAuthenticated]

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


class DistributeVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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


class VoucherStatsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

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


class VoucherRevenueChartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        group_by = request.query_params.get("group_by", "day")
        trunc_map = {
            "day": TruncDay,
            "week": TruncWeek,
            "month": TruncMonth,
        }
        trunc_func = trunc_map.get(group_by, TruncDay)

        start_date, end_date = _get_date_range(request)
        usage_qs = VoucherUsage.objects.all()
        if start_date:
            usage_qs = usage_qs.filter(used_at__date__gte=start_date)
        if end_date:
            usage_qs = usage_qs.filter(used_at__date__lte=end_date)

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

