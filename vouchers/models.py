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

    release_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField()
    quantity = models.IntegerField(default=0)
    used_count = models.IntegerField(default=0)

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

    required_role = models.CharField(max_length=50, null=True, blank=True)
    birthday_only = models.BooleanField(default=False)

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
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED_NO_EMAIL = "skipped_no_email"

    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
    ]
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED_NO_EMAIL, "Skipped No Email"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL)
    recipient = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
