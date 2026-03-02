from django.conf import settings
from django.core.mail import send_mail

from vouchers.models import VoucherDeliveryLog


def send_voucher_email(user, voucher):
    recipient = user.email

    if not recipient:
        VoucherDeliveryLog.objects.create(
            user=user,
            voucher=voucher,
            channel=VoucherDeliveryLog.CHANNEL_EMAIL,
            status=VoucherDeliveryLog.STATUS_SKIPPED_NO_EMAIL,
            recipient="",
            error_message="User has no email",
        )
        return False

    subject = f"[SmartVoucher] You received voucher {voucher.code}"
    message = (
        f"Hello {user.username},\n\n"
        f"You received a voucher: {voucher.title}\n"
        f"Code: {voucher.code}\n"
        f"Type: {voucher.discount_type}\n"
        f"Value: {voucher.discount_value}\n"
        f"Release date: {voucher.release_date}\n"
        f"Expiry date: {voucher.expiry_date}\n"
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        VoucherDeliveryLog.objects.create(
            user=user,
            voucher=voucher,
            channel=VoucherDeliveryLog.CHANNEL_EMAIL,
            status=VoucherDeliveryLog.STATUS_SENT,
            recipient=recipient,
        )
        return True
    except Exception as exc:
        VoucherDeliveryLog.objects.create(
            user=user,
            voucher=voucher,
            channel=VoucherDeliveryLog.CHANNEL_EMAIL,
            status=VoucherDeliveryLog.STATUS_FAILED,
            recipient=recipient,
            error_message=str(exc),
        )
        return False
