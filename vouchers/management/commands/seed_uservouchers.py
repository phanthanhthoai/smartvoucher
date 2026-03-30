from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
from datetime import timedelta
from vouchers.models import Voucher, UserVoucher, VoucherUsage

User = get_user_model()

class Command(BaseCommand):
    help = 'Cấy lượng lớn dữ liệu Khách hàng nhận Voucher phục vụ Test Danh sách Người nhận'

    def handle(self, *args, **kwargs):
        self.stdout.write("Khởi động làm dày dữ liệu danh sách Nhận Voucher...")
        
        # 1. Tạo thêm 50 Users để làm giàu cơ sở Dữ Liệu Khách hàng
        created_count = 0
        for i in range(1, 51):
            username = f"thanhvien_vip_{i}"
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(
                    username=username,
                    password="password123",
                    email=f"{username}@vipdomain.com",
                    first_name=random.choice(["Lê", "Nguyễn", "Phạm", "Trần", "Huỳnh", "Đỗ"]),
                    last_name=f"Văn {i} VIP"
                )
                created_count += 1
        
        users = list(User.objects.all())
        
        now = timezone.now()
        # Chỉ rải cho các voucher đã release (ko chọn scheduled)
        vouchers = list(Voucher.objects.filter(release_date__lt=now))
        
        total_uv = 0
        total_usage = 0

        # Với mỗi Voucher, bốc ngẫu nhiên 15 - 40 Users để phát Voucher
        for v in vouchers:
            num_receivers = random.randint(15, min(40, len(users)))
            sample_users = random.sample(users, num_receivers)
            
            for u in sample_users:
                # Tránh trùng lặp UniqueConstraint
                if not UserVoucher.objects.filter(user=u, voucher=v).exists():
                    is_used = random.choice([True, False, False, True, True]) # Tỷ lệ dùng cao hơn
                    
                    uv = UserVoucher.objects.create(
                        user=u,
                        voucher=v,
                        is_used=is_used,
                        assigned_at=now - timedelta(days=random.randint(1, 10)),
                        used_at=now - timedelta(hours=random.randint(1, 100)) if is_used else None
                    )
                    total_uv += 1
                    
                    if is_used:
                        dis_amt = v.discount_value if v.discount_type == 'fixed' else random.choice([15000, 25000, 35000, 50000, 100000])
                        VoucherUsage.objects.create(
                            user_voucher=uv,
                            order_id=random.randint(20000, 999999),
                            discount_amount=dis_amt
                        )
                        total_usage += 1
                        
            # Cập nhật số lượng đã sử dụng vào kho tổng của Voucher để đồng bộ
            actual_used = UserVoucher.objects.filter(voucher=v, is_used=True).count()
            v.used_count = actual_used
            
            # Đảm bảo lượng cấp phát ko nhiều hơn số lượng kho
            actual_distributed = UserVoucher.objects.filter(voucher=v).count()
            if actual_distributed > v.quantity:
                v.quantity = actual_distributed + random.randint(10, 50)
            
            v.save()

        self.stdout.write(self.style.SUCCESS(f'Hoàn thành Data khống: Đã tạo {created_count} KH VIP.'))
        self.stdout.write(self.style.SUCCESS(f'Phát hành thành công {total_uv} lượt cấp phát Voucher và khai sinh {total_usage} hóa đơn sử dụng Voucher!'))
