from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import get_random_string


def generate_unique_voucher_code():
    while True:
        code = f"VC-{get_random_string(10).upper()}"
        if not Voucher.objects.filter(code=code).exists():
            return code


class Voucher(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        default=generate_unique_voucher_code
    )
    title = models.CharField(max_length=255)

    discount_type = models.CharField(
        max_length=20,
        choices=[("percent", "Percent"), ("fixed", "Fixed")]
    )
    discount_value = models.FloatField()
    max_discount_amount = models.FloatField(null=True, blank=True)

    release_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField()
    quantity = models.IntegerField(default=0)
    used_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    event_type = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class VoucherRule(models.Model):
    voucher = models.OneToOneField(
        Voucher,
        on_delete=models.CASCADE,
        related_name="rule"
    )
    # Điều kiện để phân phối voucher
    required_role = models.CharField(max_length=50, null=True, blank=True)
    birthday_only = models.BooleanField(default=False)

        # Điều kiện tích lũy lịch sử
    min_accumulated_spent = models.FloatField(
        default=0, 
        help_text="Tổng số tiền tối thiểu user phải từng tiêu để được nhận mã"
    )
    min_accumulated_orders = models.IntegerField(
        default=0, 
        help_text="Tổng số đơn hàng thành công tối thiểu để được nhận mã"
    )
    
        # Lọc thời gian cho điều kiện tích lũy
    target_month = models.IntegerField(null=True, blank=True, help_text="Tháng cụ thể (1-12)")
    target_year = models.IntegerField(null=True, blank=True, help_text="Năm cụ thể (ví dụ: 2025)")
    lookback_days = models.IntegerField(
        default=0, 
        help_text="Số ngày tính ngược từ hiện tại (ví dụ: 30 ngày qua). Bị bỏ qua nếu có target_month/year"
    )

    # Điều kiện áp dụng cho đơn hàng
    min_order_amount = models.FloatField(default=0)
    min_items = models.IntegerField(default=0)
    required_product_type = models.CharField(max_length=100, null=True, blank=True)

    period_type = models.CharField(
        max_length=10,
        choices=[("day", "Day"), ("week", "Week"), ("month", "Month")],
        null=True,
        blank=True
    )


class UserVoucher(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE)

    is_used = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "voucher")


class VoucherUsage(models.Model):
    user_voucher = models.ForeignKey(UserVoucher, on_delete=models.CASCADE)
    order_id = models.IntegerField()
    discount_amount = models.FloatField()
    used_at = models.DateTimeField(auto_now_add=True)


class VoucherDistributionPlan(models.Model):
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_SKIPPED_EXPIRED = "skipped_expired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_SKIPPED_EXPIRED, "Skipped Expired"),
    ]

    voucher = models.OneToOneField(
        Voucher,
        on_delete=models.CASCADE,
        related_name="distribution_plan"
    )
    user_ids = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    distributed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VoucherEventLog(models.Model):
    EVENT_TYPE_ORDER_SUCCESS = "order_success"
    STATUS_PROCESSED = "processed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PROCESSED, "Processed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=50, default=EVENT_TYPE_ORDER_SUCCESS)
    order_id = models.IntegerField()
    user_id = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROCESSED)
    payload = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VoucherDeliveryLog(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED_NO_EMAIL = "skipped_no_email"
    STATUS_SKIPPED_NO_PHONE = "skipped_no_phone"

    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
    ]
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED_NO_EMAIL, "Skipped No Email"),
        (STATUS_SKIPPED_NO_PHONE, "Skipped No Phone"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL)
    recipient = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
