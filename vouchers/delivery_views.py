from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin
from vouchers.models import VoucherDeliveryLog, UserVoucher, Voucher
from vouchers.services.notification import send_voucher_email


class VoucherDeliveryLogAPIView(APIView):
    """Xem lịch sử gửi email voucher cho 1 voucher cụ thể."""
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request, voucher_id):
        logs = (
            VoucherDeliveryLog.objects
            .filter(voucher_id=voucher_id)
            .select_related("user", "voucher")
            .order_by("-created_at")
        )

        data = []
        for log in logs:
            data.append({
                "id": log.id,
                "user_id": log.user_id,
                "username": log.user.username if log.user else "N/A",
                "email": log.recipient or "",
                "channel": log.channel,
                "status": log.status,
                "status_display": log.get_status_display() if hasattr(log, 'get_status_display') else log.status,
                "error_message": log.error_message or "",
                "sent_at": log.created_at,
            })

        # Thống kê
        total = len(data)
        sent = sum(1 for d in data if d["status"] == VoucherDeliveryLog.STATUS_SENT)
        failed = sum(1 for d in data if d["status"] == VoucherDeliveryLog.STATUS_FAILED)
        skipped = total - sent - failed

        return Response({
            "voucher_id": voucher_id,
            "summary": {
                "total": total,
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
            },
            "results": data,
        })


class ResendVoucherEmailAPIView(APIView):
    """Gửi lại email voucher cho 1 user cụ thể."""
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request, voucher_id):
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"error": "user_id là bắt buộc"}, status=400)

        try:
            uv = UserVoucher.objects.select_related("user", "voucher").get(
                voucher_id=voucher_id, user_id=user_id
            )
        except UserVoucher.DoesNotExist:
            return Response({"error": "User chưa được phân phối voucher này"}, status=404)

        success = send_voucher_email(uv.user, uv.voucher)

        if success:
            return Response({"message": f"Email đã gửi thành công đến {uv.user.email}"})
        else:
            return Response({"error": f"Gửi email thất bại cho {uv.user.email}"}, status=500)


class SendVoucherToEmailAPIView(APIView):
    """Gửi voucher đến 1 email cụ thể (nhập email thủ công)."""
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request, voucher_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        email = request.data.get("email")
        if not email:
            return Response({"error": "email là bắt buộc"}, status=400)

        try:
            voucher = Voucher.objects.get(id=voucher_id, is_deleted=False)
        except Voucher.DoesNotExist:
            return Response({"error": "Voucher không tồn tại"}, status=404)

        # Tìm user theo email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": f"Không tìm thấy user với email {email}"}, status=404)

        # Tạo UserVoucher nếu chưa có
        uv, created = UserVoucher.objects.get_or_create(user=user, voucher=voucher)

        # Gửi email
        success = send_voucher_email(user, voucher)

        if success:
            return Response({
                "message": f"Đã phân phối voucher '{voucher.code}' và gửi email đến {email}",
                "already_assigned": not created,
            })
        else:
            return Response({
                "error": f"Đã phân phối voucher nhưng gửi email thất bại cho {email}",
                "already_assigned": not created,
            }, status=500)
