import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartvoucher.settings')
django.setup()

from vouchers.models import Voucher, VoucherRule

def seed():
    # Xoa dữ liệu cũ nếu muốn (tùy chọn)
    # Voucher.objects.all().delete()
    
    vouchers_data = [
        {
            "code": "WELCOME2024",
            "title": "Chương trình Chào Mừng Thành Viên 2024",
            "discount_type": "percent",
            "discount_value": 20,
            "quantity": 1000,
            "event_type": "welcome",
            "rule": {"required_role": "customer", "min_order_amount": 0}
        },
        {
            "code": "SUMMER_SALE",
            "title": "Siêu Ưu Đãi Mùa Hè - Giảm 50k",
            "discount_type": "fixed",
            "discount_value": 50000,
            "quantity": 500,
            "event_type": "",
            "rule": {"required_role": "", "min_order_amount": 200000}
        },
        {
            "code": "BIRTHDAY_GIFT",
            "title": "Quà Tặng Sinh Nhật Đặc Biệt",
            "discount_type": "percent",
            "discount_value": 30,
            "quantity": 100,
            "event_type": "birthday",
            "rule": {"required_role": "customer", "birthday_only": True}
        }
    ]

    for data in vouchers_data:
        rule_data = data.pop("rule")
        voucher, created = Voucher.objects.update_or_create(
            code=data["code"],
            defaults={
                **data,
                "release_date": timezone.now() - timezone.timedelta(days=1),
                "expiry_date": timezone.now() + timezone.timedelta(days=30),
            }
        )
        VoucherRule.objects.update_or_create(
            voucher=voucher,
            defaults=rule_data
        )
        print(f"{'Created' if created else 'Updated'} voucher: {voucher.code}")

if __name__ == "__main__":
    seed()
