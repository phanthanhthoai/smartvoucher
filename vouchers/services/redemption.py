from django.utils import timezone

from vouchers.models import UserVoucher, VoucherUsage


def get_discount_base_amount(voucher, order):
    rule = voucher.rule

    if not rule.required_product_type:
        return order.total_amount

    matching_items = order.items.filter(
        product_type__iexact=rule.required_product_type
    )
    return sum(item.line_total for item in matching_items)


def calculate_discount_amount(voucher, order):
    base_amount = get_discount_base_amount(voucher, order)

    if base_amount <= 0:
        return 0

    if voucher.discount_type == "percent":
        return round(base_amount * (voucher.discount_value / 100), 2)

    # Fixed voucher cannot discount more than eligible subtotal.
    return min(voucher.discount_value, base_amount)


def redeem_voucher(user, voucher, order):
    user_voucher = UserVoucher.objects.get(
        user=user,
        voucher=voucher
    )

    if user_voucher.is_used:
        return False, "Voucher da duoc su dung"

    user_voucher.is_used = True
    user_voucher.used_at = timezone.now()
    user_voucher.save()

    voucher.used_count += 1
    voucher.save()

    discount_amount = calculate_discount_amount(voucher, order)

    VoucherUsage.objects.create(
        user_voucher=user_voucher,
        order_id=order.id,
        discount_amount=discount_amount
    )

    return True, discount_amount
