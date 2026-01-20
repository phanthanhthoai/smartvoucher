from django.contrib import admin
from .models import Voucher

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'discount_type',
        'discount_value',
        'is_active',
        'used_count',
        'usage_limit',
        'start_date',
        'end_date'
    )
    search_fields = ('code',)
