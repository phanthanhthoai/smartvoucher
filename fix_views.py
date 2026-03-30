import os
import django
from django.utils import timezone

# Không cần setup django nếu chỉ xử lý file text
path = 'vouchers/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_view = """

def _get_voucher_status(voucher, now=None):
    if not now:
        from django.utils import timezone
        now = timezone.now()
    if voucher.used_count >= voucher.quantity and voucher.quantity > 0:
        return "exhausted"
    if voucher.expiry_date and voucher.expiry_date < now:
        return "expired"
    if voucher.release_date and voucher.release_date > now:
        return "scheduled"
    return "active"

class VoucherListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        from vouchers.models import Voucher
        from django.utils import timezone
        vouchers = Voucher.objects.all().order_by("-created_at")
        data = []
        now = timezone.now()
        for v in vouchers:
            data.append({
                "voucher_id": v.id,
                "code": v.code,
                "title": v.title,
                "status": _get_voucher_status(v, now=now),
                "release_date": v.release_date,
                "expiry_date": v.expiry_date,
                "quantity": v.quantity,
                "used_count": v.used_count,
                "usage_rate_percent": round((v.used_count / v.quantity * 100), 2) if v.quantity > 0 else 0,
            })
        return Response({"results": data})
"""

# Append if not already there
if "class VoucherListAPIView" not in content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.rstrip() + new_view)
    print("Added VoucherListAPIView")
else:
    print("VoucherListAPIView already exists")
