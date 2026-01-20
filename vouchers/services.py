import random
from django.utils import timezone
import string
from .models import Voucher
from django.core.mail import send_mail
from django.conf import settings
from .models import VoucherUsage


def generate_voucher_code(length=8):
    while True:
        code = 'VC-' + ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=length)
        )
        if not Voucher.objects.filter(code=code).exists():
            return code

def check_voucher(voucher_code, order_total, user=None):
    try:
        voucher = Voucher.objects.get(code=voucher_code)
    except Voucher.DoesNotExist:
        return {"valid": False, "reason": "Voucher not found"}

    if not voucher.is_active:
        return {"valid": False, "reason": "Voucher inactive"}

    now = timezone.now()
    if voucher.start_date > now or voucher.end_date < now:
        return {"valid": False, "reason": "Voucher expired"}

    if not voucher.can_use():
        return {"valid": False, "reason": "Voucher usage limit reached"}

    if order_total < voucher.min_order_value:
        return {"valid": False, "reason": "Order total too low"}

    if voucher.discount_type == "percent":
        discount_amount = order_total * voucher.discount_value / 100
    else:
        discount_amount = voucher.discount_value

    final_price = order_total - discount_amount
    if final_price < 0:
        final_price = 0

    VoucherUsage.objects.create(
        voucher=voucher,
        user=user,
        order_total=order_total,
        discount_amount=discount_amount,
        final_price=final_price
    )

    voucher.used_count += 1
    voucher.save()

    return {
        "valid": True,
        "voucher_code": voucher.code,
        "discount": float(discount_amount),
        "final_price": float(final_price),
    }



def send_voucher_email(email, voucher_code):
    send_mail(
        subject="Your Discount Voucher",
        message=f"Your voucher code is: {voucher_code}",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[email],
        fail_silently=False,
    )


def send_voucher_sms(phone, voucher_code):
    print(f"[SMS] Send to {phone}: Your voucher code is {voucher_code}")
