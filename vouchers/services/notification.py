from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

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

    subject = f"[SmartVoucher] Bạn nhận được voucher mới {voucher.code}"
    
    # Prepare context for template
    context = {
        'user': user,
        'voucher': voucher,
    }
    
    # Render HTML and plain text version
    html_message = render_to_string('vouchers/email/voucher_email.html', context)
    plain_message = strip_tags(html_message)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient],
            html_message=html_message,
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
