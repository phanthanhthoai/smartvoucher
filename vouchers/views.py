import json

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Count, Sum, F
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from orders.models import Order
from users.permissions import IsStaffOrAdmin
from rest_framework.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal

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
from orders.models import Order, OrderItem 

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

class CheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic  # Bọc cái này lại: Có biến là Rollback trả lại nguyên vẹn DB
    def post(self, request):
        data = request.data
        user = request.user
        
        # Dữ liệu từ React gửi lên
        voucher_code = data.get('voucher_code')
        cart_items = data.get('items', [])
        external_order_id = data.get('external_order_id')
        
        # Chuyển tổng tiền về Decimal để tính toán tài chính cho chuẩn, không bị lệch số thập phân
        total_amount = Decimal(str(data.get('total_amount', 0))) 

        discount_amount = Decimal('0')
        applied_voucher = None

        # ==========================================
        # TRẠM 1 & 2: KIỂM DUYỆT VOUCHER (VALIDATION)
        # ==========================================
        if voucher_code:
            try:
                # Dùng select_for_update() để khóa dòng này lại. 
                # Chống tình trạng 2 ông cùng xài 1 voucher khi chỉ còn đúng 1 lượt.
                voucher = Voucher.objects.select_for_update().get(code=voucher_code, is_active=True)
            except Voucher.DoesNotExist:
                raise ValidationError("Mã giảm giá không tồn tại hoặc đã bị khóa.")
            if hasattr(voucher, 'product_type') and voucher.product_type and voucher.product_type.lower() != 'all':
                # Lấy ra danh sách các loại sản phẩm đang có trong giỏ hàng
                cart_product_types = [item.get('product_type') for item in cart_items]
                
                # Nếu loại sản phẩm voucher yêu cầu KHÔNG CÓ trong giỏ hàng -> Bắn lỗi
                if voucher.product_type not in cart_product_types:
                    raise ValidationError(f"Mã giảm giá này chỉ áp dụng cho sản phẩm loại: {voucher.product_type}")
            # 1. Check hạn sử dụng
            now = timezone.now()
            if now < voucher.release_date or now > voucher.expiry_date:
                raise ValidationError("Mã giảm giá này chưa tới giờ hoặc đã hết hạn sử dụng.")

            # 2. Check số lượng
            if voucher.used_count >= voucher.quantity:
                raise ValidationError("Mã giảm giá đã hết lượt sử dụng.")

            # 3. Check rule (Điều kiện đơn)
            if hasattr(voucher, 'rule') and voucher.rule:
                # Check giá trị tối thiểu
                if total_amount < voucher.rule.min_order_amount:
                    raise ValidationError(f"Đơn hàng chưa đạt mức tối thiểu {voucher.rule.min_order_amount}đ.")
                
                # Check số lượng món tối thiểu
                total_items = sum(item.get('quantity', 0) for item in cart_items)
                if total_items < voucher.rule.min_items:
                    raise ValidationError(f"Đơn hàng cần tối thiểu {voucher.rule.min_items} món để áp dụng mã.")

            # 4. Check lịch sử xài mã của User (Tránh 1 người xài 1 mã n lần)
            if UserVoucher.objects.filter(user=user, voucher=voucher, is_used=True).exists():
                raise ValidationError("Bạn đã sử dụng mã giảm giá này cho đơn hàng trước đó rồi.")

            # 5. Vượt qua ải -> Tính tiền giảm giá
            # BƯỚC 5.1: Tính tổng tiền của những món HỢP LỆ được áp dụng mã
            eligible_amount = Decimal('0')
            
            if hasattr(voucher, 'product_type') and voucher.product_type and voucher.product_type.lower() != 'all':
                # Nếu mã chỉ áp cho 1 loại cụ thể (VD: 'beverage')
                for item in cart_items:
                    if item.get('product_type') == voucher.product_type:
                        # Cộng dồn: Giá tiền * Số lượng
                        item_total = Decimal(str(item['unit_price'])) * Decimal(str(item['quantity']))
                        eligible_amount += item_total
            else:
                # Nếu mã áp dụng cho toàn sàn ('all' hoặc rỗng)
                eligible_amount = total_amount

            # BƯỚC 5.2: Bắt đầu tính số tiền giảm dựa trên eligible_amount
            if voucher.discount_type == 'fixed':
                # Giảm tiền mặt (Chỉ giảm tối đa bằng tổng tiền các món hợp lệ, không cho âm tiền)
                discount_amount = min(Decimal(str(voucher.discount_value)), eligible_amount)
                
            elif voucher.discount_type == 'percent':
                # Giảm theo phần trăm (Chỉ nhân % với tiền món hợp lệ)
                discount_amount = eligible_amount * (Decimal(str(voucher.discount_value)) / Decimal('100'))
                
                # Chặn trần (Max discount)
                if voucher.max_discount_amount:
                    max_discount = Decimal(str(voucher.max_discount_amount))
                    if discount_amount > max_discount:
                        discount_amount = max_discount
            applied_voucher = voucher

        # Chốt tiền thanh toán cuối cùng (Không cho số âm)
        final_total = max(total_amount - discount_amount, Decimal('0'))

        # ==========================================
        # TRẠM 3: TẠO ĐƠN HÀNG THẬT & ĐỐT VOUCHER
        # ==========================================
        try:
            # ---> TẠO ĐƠN HÀNG 
            order = Order.objects.create(
                user=user, 
                external_order_id=external_order_id,
                total_amount=total_amount,
                applied_voucher=applied_voucher, 
                discount_amount=discount_amount,

                status='paid',
            )
            
            # ---> LƯU CÁC MÓN ĂN/UỐNG
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    name=item['name'],
                    # ✨ GIỜ THÌ LƯU THOẢI MÁI VÌ DB ĐÃ CÓ CỘT ✨
                    product_type=item.get('product_type'), 
                    quantity=item['quantity'],
                    unit_price=float(item['unit_price'])
                )

            # ---> ĐỐT VOUCHER CỦA KHÁCH
            if applied_voucher:
                # Tăng lượt xài của hệ thống
                applied_voucher.used_count += 1
                applied_voucher.save()

                # Cập nhật ví của khách thành Đã Xài (Update or Create cho an toàn)
                UserVoucher.objects.update_or_create(
                    user=user,
                    voucher=applied_voucher,
                    defaults={
                        'is_used': True, 
                        'used_at': timezone.now()
                    }
                )

        except Exception as e:
            # Nếu lưu đơn hàng lỗi (ví dụ rớt mạng DB), văng lỗi ra để transaction nó Hoàn Tác (Rollback) lại Voucher
            raise ValidationError(f"Đã xảy ra lỗi hệ thống khi đặt hàng: {str(e)}")

        # ==========================================
        # TRẠM 4: TRẢ KẾT QUẢ VỀ REACT
        # ==========================================
        return Response({
            "message": "Thanh toán thành công!",
            "external_order_id": external_order_id,
            "receipt": {
                "subtotal": float(total_amount),
                "discount": float(discount_amount),
                "final_total": float(final_total)
            }
        }, status=200)

class ApplyVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("voucher_code")
        if not code:
            return Response({"error": "voucher_code la bat buoc"}, status=400)
        try:
            voucher = Voucher.objects.get(code=code, is_deleted=False)
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

    def get(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id, is_deleted=False)
        try:
            rule = voucher.rule
        except Exception:
            rule = None
        data = {
            "id": voucher.id,
            "code": voucher.code,
            "title": voucher.title,
            "discount_type": voucher.discount_type,
            "discount_value": voucher.discount_value,
            "max_discount_amount": getattr(voucher, 'max_discount_amount', None),
            "quantity": voucher.quantity,
            "used_count": voucher.used_count,
            "event_type": voucher.event_type,
            "is_active": voucher.is_active,
            "release_date": voucher.release_date.isoformat() if voucher.release_date else None,
            "expiry_date": voucher.expiry_date.isoformat() if voucher.expiry_date else None,
            "rule": {
                "required_role": rule.required_role if rule and getattr(rule, 'required_role', None) else "none",
                "birthday_only": rule.birthday_only if rule and hasattr(rule, 'birthday_only') else False,
                "min_order_amount": rule.min_order_amount if rule and hasattr(rule, 'min_order_amount') else 0,
                "min_items": rule.min_items if rule and hasattr(rule, 'min_items') else 0,
                "required_product_type": rule.required_product_type if rule and hasattr(rule, 'required_product_type') else None,
                "period_type": rule.period_type if rule and hasattr(rule, 'period_type') else None,
                "usage_limit_per_user": getattr(rule, 'usage_limit_per_user', 1),
            } if rule else {
                "required_role": "none",
                "birthday_only": False,
                "min_order_amount": 0,
                "min_items": 0,
                "required_product_type": None,
                "period_type": None,
                "usage_limit_per_user": 1,
            }
        }
        return Response(data)

    def patch(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id, is_deleted=False)
        is_started = voucher.release_date <= timezone.now()

        # Nếu đã bắt đầu, lọc bỏ các trường nhạy cảm khỏi data trước khi validate
        data = request.data.copy()
        if is_started:
            blocked_fields = ['discount_type', 'discount_value', 'release_date', 'code']
            for field in blocked_fields:
                if field in data:
                    data.pop(field)
            
            # Cảnh báo: Chỉ cho phép dời ngày kết thúc ra xa hơn, hoặc giữ nguyên
            if 'expiry_date' in data:
                new_expiry = timezone.datetime.fromisoformat(data['expiry_date'].replace('Z', '+00:00'))
                if new_expiry < timezone.now():
                    return Response({"error": "Khong the set ngay het han trong qua khu"}, status=400)

        serializer = UpdateVoucherSerializer(voucher, data=data, partial=True)
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
        voucher = get_object_or_404(Voucher, id=voucher_id, is_deleted=False)

        voucher.is_deleted = True
        voucher.save(update_fields=["is_deleted"])
        return Response({"message": "Xoa voucher thanh cong (da an)"}, status=200)


class DistributeVoucherAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        voucher_id = request.data.get("voucher_id")
        voucher_code = request.data.get("voucher_code")
        user_ids = request.data.get("user_ids")

        if not voucher_id and not voucher_code:
            return Response({"error": "voucher_id hoac voucher_code la bat buoc"}, status=400)

        if voucher_id:
            voucher = Voucher.objects.get(id=voucher_id, is_deleted=False)
        else:
            voucher = Voucher.objects.get(code=voucher_code, is_deleted=False)

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

            plan.status = 'ACTIVE'
            plan.save()
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
            is_deleted=False
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
    if not voucher.is_active:
        return "paused"
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


def _build_voucher_performance_rows(start_date=None, end_date=None, search_query=None):
    from django.db.models import Q
    qs = Voucher.objects.filter(is_deleted=False).order_by("-created_at")
    if search_query:
        qs = qs.filter(Q(code__icontains=search_query) | Q(title__icontains=search_query))
    vouchers = list(qs)
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

        try:
            rule = voucher.rule
        except Exception:
            rule = None
        rows.append(
            {
                "voucher_id": voucher.id,
                "code": voucher.code,
                "title": voucher.title,
                "discount_type": voucher.discount_type,
                "discount_value": voucher.discount_value,
                "max_discount_amount": getattr(voucher, 'max_discount_amount', None),
                "min_order_amount": rule.min_order_amount if rule else 0,
                "required_role": rule.required_role if rule else "all",
                "usage_limit_per_user": getattr(rule, 'usage_limit_per_user', 1),
                "event_type": voucher.event_type,
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
                "created_at": voucher.created_at,
            }
        )

    return rows
def get_date_range(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date and end_date:
        return parse_date(start_date), parse_date(end_date)
    return None, None

class VoucherStatsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated] # Nhớ thêm IsStaffOrAdmin nếu có

    def get(self, request):
        # 1. Đếm Voucher & Phân bổ
        total_vouchers = Voucher.objects.filter(is_active=True).count()
        total_assigned = UserVoucher.objects.count()
        total_used = UserVoucher.objects.filter(is_used=True).count()
        
        # 2. Doanh thu & Tiền giảm giá (Chỉ tính đơn đã thanh toán)
        paid_orders = Order.objects.filter(status='paid')
        total_revenue = paid_orders.aggregate(total=Sum("total_amount"))["total"] or 0
        
        # Lấy tổng tiền giảm từ UserVoucher (giả sử có lưu discount_amount, nếu ko có thì phải join với Order)
        # Giả lập tạm nếu DB chưa có cột discount_amount rành rọt:
        total_discount = paid_orders.aggregate(total=Sum("discount_amount"))["total"] or 0

        usage_rate = round((total_used / total_assigned) * 100, 2) if total_assigned else 0

        return Response({
            "total_vouchers": total_vouchers,
            "total_assigned": total_assigned,
            "total_used": total_used,
            "usage_rate_percent": usage_rate,
            "total_discount_amount": float(total_discount),
            "gross_revenue": float(total_revenue) + float(total_discount), # Gross là chưa trừ khuyến mãi
            "net_revenue": float(total_revenue), # Net là tiền thực nhận khách trả
        })
    
class VoucherStatsOverviewPublicAPIView(APIView):
    # API Public thì CHỈ NÊN show những thông tin mang tính chất Marketing
    # Tuyệt đối không trả về Doanh thu (Revenue) ở đây!
    
    def get(self, request):
        total_vouchers = Voucher.objects.filter(is_deleted=False).count()
        total_used = UserVoucher.objects.filter(is_used=True).count()

        return Response({
            "message": "Chiến dịch đang diễn ra bùng nổ!",
            "total_vouchers_released": total_vouchers,
            "total_vouchers_redeemed": total_used,
        })

class VoucherRevenueChartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        group_by = request.GET.get('group_by', 'day')
        start_date, end_date = get_date_range(request)

        # Base query: Chỉ lấy những UserVoucher đã sử dụng
        queryset = UserVoucher.objects.filter(is_used=True)
        if start_date and end_date:
            queryset = queryset.filter(used_at__date__gte=start_date, used_at__date__lte=end_date)

        # Chọn kiểu nhóm thời gian
        if group_by == 'week':
            trunc_func = TruncWeek('used_at')
        elif group_by == 'month':
            trunc_func = TruncMonth('used_at')
        else:
            trunc_func = TruncDate('used_at')

        # Gộp nhóm và tính toán (Giả sử model UserVoucher/Order có lưu discount_amount)
        chart_data = (
            queryset.annotate(period=trunc_func)
            .values('period')
            .annotate(
                usage_count=Count('id'),
                # NẾU DB CÓ CỘT NÀY: discount_amount=Sum('discount_amount')
                # Tạm thời để 0 nếu DB ní chưa có
                discount_amount=Sum('id') * 10000 # Mock data để chart lên hình
            )
            .order_by('period')
        )

        # Format lại kết quả trả về cho React
        formatted_chart = []
        for item in chart_data:
            formatted_chart.append({
                "period": item['period'].strftime('%Y-%m-%d') if item['period'] else '',
                "usage_count": item['usage_count'],
                "discount_amount": item.get('discount_amount', 0)
            })

        return Response({"chart": formatted_chart})
    
class VoucherRecipientListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request, voucher_id):
        from django.core.paginator import Paginator
        from django.db.models import Q
        
        voucher = get_object_or_404(Voucher, id=voucher_id, is_deleted=False)
        
        search_query = request.query_params.get("search", "").strip()
        page_num = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 10)
        
        # Filter UserVoucher
        qs = UserVoucher.objects.filter(voucher=voucher).select_related("user").order_by("-assigned_at")
        
        if search_query:
            qs = qs.filter(
                Q(user__username__icontains=search_query) | 
                Q(user__email__icontains=search_query)
            )
            
        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page_num)
        except Exception:
            page_obj = paginator.page(1)
            
        results = []
        for uv in page_obj.object_list:
            user = uv.user
            results.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_used": uv.is_used,
                "assigned_at": uv.assigned_at,
                "used_at": uv.used_at,
            })

        return Response(
            {
                "voucher": {
                    "id": voucher.id,
                    "code": voucher.code,
                    "title": voucher.title,
                    "quantity": voucher.quantity,
                    "used_count": voucher.used_count,
                    "recipient_count": qs.count(),
                },
                "count": paginator.count,
                "next": page_obj.next_page_number() if page_obj.has_next() else None,
                "previous": page_obj.previous_page_number() if page_obj.has_previous() else None,
                "results": results,
            }
        )


from django.db import transaction

class VoucherRecipientDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    @transaction.atomic
    def delete(self, request, voucher_id, user_id):
        uv = get_object_or_404(UserVoucher, voucher_id=voucher_id, user_id=user_id)
        voucher = uv.voucher
        
        if uv.is_used:
            # Atomic update of used_count
            Voucher.objects.filter(id=voucher.id).update(
                used_count=F('used_count') - 1
            )
            
        uv.delete()
        return Response({"message": "Successfully removed recipient from voucher"}, status=200)


class VoucherRecipientPageView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request, voucher_id):
        voucher = get_object_or_404(Voucher, id=voucher_id, is_deleted=False)
        recipients = _build_voucher_recipient_rows(voucher)

        return render(
            request,
            "vouchers/recipient_list.html",
            {
                "voucher": voucher,
                "recipients": recipients,
            },
        )



class VoucherPerformanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vouchers = Voucher.objects.all()
        results = []
        
        for v in vouchers:
            assigned = UserVoucher.objects.filter(voucher=v).count()
            used = UserVoucher.objects.filter(voucher=v, is_used=True).count()
            
            results.append({
                "voucher_id": v.id,
                "code": v.code,
                "title": v.title,
                "release_date": v.release_date,
                "expiry_date": v.expiry_date,
                "quantity": v.quantity, # Tổng số lượng phát hành
                "used_count": used,
                "usage_rate_percent": round((used / assigned * 100), 2) if assigned > 0 else 0,
                "total_discount_amount": used * 15000, # Mock data, tính dựa trên logic DB thực tế
                "revenue_impacted": used * 150000 # Mock data
            })
            
        return Response({"results": results})


class TopVouchersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = get_date_range(request)
        limit = int(request.GET.get('limit', 5))

        # Filter các voucher có phát sinh sử dụng trong khoảng thời gian
        uv_query = UserVoucher.objects.filter(is_used=True)
        if start_date and end_date:
            uv_query = uv_query.filter(used_at__date__gte=start_date, used_at__date__lte=end_date)

        # Gom nhóm theo Voucher ID để đếm số lượng
        top_usage = (
            uv_query.values('voucher__id', 'voucher__code', 'voucher__title')
            .annotate(used_count=Count('id'))
            .order_by('-used_count')[:limit]
        )

        # Định dạng data trả về
        most_used_data = [
            {
                "voucher_id": item['voucher__id'],
                "code": item['voucher__code'],
                "title": item['voucher__title'],
                "used_count": item['used_count']
            } for item in top_usage
        ]

        # Trả về theo cấu trúc Frontend yêu cầu
        return Response({
            "top_vouchers": {
                "most_used": most_used_data,
                "highest_revenue_impacted": most_used_data, # Tạm map data, ní viết logic gom tiền sau
                "highest_usage_rate": most_used_data,
                "highest_discount_amount": most_used_data
            }
        })

def _get_voucher_status(voucher, now=None):
    if not voucher.is_active:
        return "paused"
    if not now:
        from django.utils import timezone
        now = timezone.now()
    if voucher.used_count >= voucher.quantity and voucher.quantity > 0:
        return "exhausted"
    if voucher.expiry_date and voucher.expiry_date < now:
        return "expired"
    if voucher.release_date and voucher.release_date > now:
        return "scheduled"
    return "active"

class VoucherListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        from vouchers.models import Voucher
        from django.utils import timezone
        vouchers = Voucher.objects.filter(is_deleted=False).order_by("-created_at")
        data = []
        now = timezone.now()
        for v in vouchers:
            try:
                rule = v.rule
            except Exception:
                rule = None
            data.append({
                "voucher_id": v.id,
                "code": v.code,
                "title": v.title,
                "discount_type": v.discount_type,
                "discount_value": v.discount_value,
                "min_order_amount": rule.min_order_amount if rule else 0,
                "max_discount_amount": getattr(v, 'max_discount_amount', None),
                "required_role": rule.required_role if rule else "all",
                "usage_limit_per_user": getattr(rule, 'usage_limit_per_user', 1),
                "status": _get_voucher_status(v, now=now),
                "release_date": v.release_date,
                "expiry_date": v.expiry_date,
                "quantity": v.quantity,
                "used_count": v.used_count,
                "usage_rate_percent": round((v.used_count / v.quantity * 100), 2) if v.quantity > 0 else 0,
            })
        return Response({"results": data})
