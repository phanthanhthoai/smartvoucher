from django.utils import timezone
from datetime import timedelta


def check_user_condition(user, rule):
    if rule.required_role and user.role != rule.required_role:
        return False

    if rule.birthday_only:
        if not user.birthday:
            return False
        if user.birthday.month != timezone.now().month:
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


# HÀM NÀY BẮT BUỘC PHẢI CÓ
def is_voucher_eligible(user, voucher, order, Order):
    rule = voucher.rule

    return (
        check_user_condition(user, rule)
        and check_order_condition(order, rule)
        and check_time_condition(user, rule, Order)
    )
