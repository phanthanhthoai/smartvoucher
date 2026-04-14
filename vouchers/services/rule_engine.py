from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count


def check_user_condition(user, rule):
    if rule.required_role and user.role != rule.required_role:
        return False

    if rule.birthday_only:
        if not user.birthday:
            return False
        if user.birthday.day != timezone.now().day or user.birthday.month != timezone.now().month:
            return False

    return True


def check_order_condition(order, rule):
    if order.total_amount < rule.min_order_amount:
        return False

    total_items = sum(item.quantity for item in order.items.all())
    if total_items < rule.min_items:
        return False

    if rule.required_product_type:
        has_required_product_type = order.items.filter(
            product_type__iexact=rule.required_product_type
        ).exists()
        if not has_required_product_type:
            return False

    return True


def check_time_condition(user, rule, Order):
    if not rule.period_type:
        return True

    now = timezone.now()

    if rule.period_type == "day":
        start = now.replace(hour=0, minute=0, second=0)
    elif rule.period_type == "week":
        start = now - timedelta(days=now.weekday())
    elif rule.period_type == "month":
        start = now.replace(day=1)
    else:
        return True

    return Order.objects.filter(
        user=user,
        created_at__gte=start
    ).exists()

from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

def check_accumulated_condition(user, rule, Order):
    # --- 1. LẤY YÊU CẦU TỪ RULE (Mặc giáp 'or 0' chống lỗi None) ---
    req_spent = rule.min_accumulated_spent or 0
    req_orders = rule.min_accumulated_orders or 0

    # Nếu không có yêu cầu gì cả -> Auto pass (Mở cổng cho qua)
    if req_spent <= 0 and req_orders <= 0:
        return True

    # --- 2. LẤY ĐƠN HÀNG CƠ BẢN ---
    orders = Order.objects.filter(user=user, status='paid')

    # --- 3. LỌC THEO THỜI GIAN (Tách biệt hoàn toàn để không đá nhau) ---
    target_year = getattr(rule, 'target_year', 0) or 0
    target_month = getattr(rule, 'target_month', 0) or 0
    lookback = getattr(rule, 'lookback_days', 0) or 0

    if target_year > 0:
        orders = orders.filter(created_at__year=target_year)
    
    if target_month > 0:
        orders = orders.filter(created_at__month=target_month)
    
    # Chỉ áp dụng Lookback nếu người ta KHÔNG set Năm và KHÔNG set Tháng
    if lookback > 0 and target_year == 0 and target_month == 0:
        start = timezone.now() - timedelta(days=lookback)
        orders = orders.filter(created_at__gte=start)

    # --- 4. TÍNH TOÁN THỰC TẾ ---
    stats = orders.aggregate(
        total_spent=Sum('total_amount'),
        total_count=Count('id')
    )

    actual_spent = stats['total_spent'] or 0
    actual_count = stats['total_count'] or 0

    # --- 5. CHỐT HẠ (So sánh an toàn) ---
    if actual_spent < req_spent:
        return False
        
    if actual_count < req_orders:
        return False

    return True

# HÀM NÀY BẮT BUỘC PHẢI CÓ
def is_voucher_eligible(user, voucher, order, Order):
    rule = voucher.rule
    return (
        check_user_condition(user, rule)
        and check_order_condition(order, rule)
        and check_time_condition(user, rule, Order)
    )
