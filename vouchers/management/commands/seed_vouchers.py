from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
from datetime import timedelta
from vouchers.models import Voucher, VoucherRule, UserVoucher, VoucherUsage

User = get_user_model()

class Command(BaseCommand):
    help = 'Tạo dữ liệu Voucher mẫu (seed data) phục vụ hiển thị Form Admin'

    def handle(self, *args, **kwargs):
        self.stdout.write("Khởi động tạo dữ liệu mẫu Voucher...")

        # 1. Tạo thêm User mẫu
        for i in range(1, 10):
            username = f"khachhang_{i}"
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(
                    username=username,
                    password="password123",
                    email=f"{username}@example.com",
                    first_name="Khách",
                    last_name=f"Hàng {i}"
                )
        users = list(User.objects.all())

        event_types = ['regular', 'welcome', 'holiday', 'flash_sale', 'birthday']
        discount_types = ['percent', 'fixed']
        roles = ['all', 'new', 'vip']

        now = timezone.now()

        # 2. Sinh vòng lặp 25 Vouchers
        for i in range(25):
            dtype = random.choice(discount_types)
            if dtype == 'percent':
                dvalue = random.choice([5, 10, 15, 20, 25, 30, 50])
            else:
                dvalue = random.choice([15000, 20000, 30000, 50000, 100000, 200000])

            status_scenario = random.choice(['active', 'active', 'active', 'expired', 'scheduled', 'exhausted', 'paused'])
            
            if status_scenario == 'expired':
                release = now - timedelta(days=30)
                expiry = now - timedelta(days=2)
                quantity = random.randint(50, 200)
                used_qty = random.randint(10, quantity)
                is_active = True
            elif status_scenario == 'scheduled':
                release = now + timedelta(days=random.randint(2, 5))
                expiry = now + timedelta(days=30)
                quantity = random.randint(50, 500)
                used_qty = 0
                is_active = True
            elif status_scenario == 'exhausted':
                release = now - timedelta(days=10)
                expiry = now + timedelta(days=20)
                quantity = 150
                used_qty = 150
                is_active = True
            elif status_scenario == 'paused':
                release = now - timedelta(days=5)
                expiry = now + timedelta(days=25)
                quantity = 500
                used_qty = random.randint(0, 100)
                is_active = False
            else: # active
                release = now - timedelta(days=5)
                expiry = now + timedelta(days=random.randint(5, 45))
                quantity = random.randint(100, 1000)
                used_qty = random.randint(0, 300)
                is_active = True

            # Tạo Voucher Object (Django tự tạo code random nhờ model default)
            v = Voucher.objects.create(
                title=f"Siêu ưu đãi {status_scenario.upper()}",
                discount_type=dtype,
                discount_value=dvalue,
                release_date=release,
                expiry_date=expiry,
                quantity=quantity,
                used_count=used_qty,
                is_active=is_active,
                event_type=random.choice(event_types)
            )

            # Khai báo Rule
            VoucherRule.objects.create(
                voucher=v,
                required_role=random.choice(roles),
                min_order_amount=random.choice([0, 50000, 100000, 200000, 300000, 500000]),
                min_items=random.choice([0, 1, 2, 3]),
                birthday_only=random.choice([True, False, False, False])
            )

            # Cấp thử danh sách User
            if status_scenario in ['active', 'expired', 'exhausted'] and users:
                sample_users = random.sample(users, min(len(users), random.randint(2, 8)))
                
                # Mock số liệu khống để có Khấu trừ kho và Lượt dùng
                for u in sample_users:
                    is_used = random.choice([True, False, True])
                    uv = UserVoucher.objects.create(
                        user=u,
                        voucher=v,
                        is_used=is_used,
                        used_at=now - timedelta(days=random.randint(0, 5)) if is_used else None
                    )
                    if is_used:
                        dis_amt = v.discount_value if v.discount_type == 'fixed' else random.choice([10000, 20000, 30000, 50000])
                        VoucherUsage.objects.create(
                            user_voucher=uv,
                            order_id=random.randint(1000, 99999),
                            discount_amount=dis_amt
                        )

        self.stdout.write(self.style.SUCCESS(f'OK! Đã tạo thành công 25 Voucher tự động với đầy đủ các kịch bản Data để Test hệ thống React!'))
