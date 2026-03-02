from django.contrib import admin
from .models import Voucher

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'title',
        'discount_type',
        'discount_value',
        'used_count',
        'quantity',
        'expiry_date',
        'event_type',
        'created_at',
    )
    search_fields = ('code',)
