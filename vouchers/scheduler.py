# vouchers/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django.utils import timezone

def start_jobs():
    scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())
    
    # 1. Thêm JobStore để lưu lịch sử vào DB
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # 2. Thay vì dùng Decorator @, ní dùng hàm add_job trực tiếp như vầy:
    scheduler.add_job(
        process_due_distribution_plans,   # Tên hàm (không có ngoặc đơn)
        trigger="interval",
        seconds=60,
        id="auto_distribute_voucher",
        max_instances=1,
        replace_existing=True,            # Giờ thì nó sẽ không bị lỗi lặp tham số nữa
    )

    # 3. Đăng ký sự kiện và bắt đầu
    register_events(scheduler)
    scheduler.start()
    print("⏰ Đã bật hệ thống phát Voucher tự động thành công!")

def process_due_distribution_plans():
    # Phải import bên trong hàm để tránh lỗi Circular Import (Vòng lặp import)
    from .models import VoucherDistributionPlan
    from .services.distribution import execute_distribution_plan
    from django.utils import timezone

    now = timezone.now()
    print(f"[{now}] 🕒 Scheduler đang quét Voucher còn hạn...")

    # Lọc Voucher còn hạn và đang hoạt động
    plans = VoucherDistributionPlan.objects.filter(
        status__in=['PENDING', 'ACTIVE'],
        voucher__release_date__lte=now,
        voucher__expiry_date__gte=now,
        voucher__is_active=True
    )

    if not plans.exists():
        return 0

    processed_count = 0
    for plan in plans:
        try:
            if plan.voucher.used_count < plan.voucher.quantity:
                execute_distribution_plan(plan)
                processed_count += 1
            else:
                plan.status = 'COMPLETED'
                plan.save()
        except Exception as e:
            print(f"❌ Lỗi Plan {plan.id}: {str(e)}")
            
    return processed_count