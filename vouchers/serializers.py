from rest_framework import serializers
from .models import Voucher

class CheckVoucherSerializer(serializers.Serializer):
    voucher_code = serializers.CharField()
    order_total = serializers.DecimalField(max_digits=10, decimal_places=2)

class CreateVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voucher
        fields = [
            'discount_type',
            'discount_value',
            'min_order_value',
            'start_date',
            'end_date',
            'usage_limit',
            'is_active'
        ]