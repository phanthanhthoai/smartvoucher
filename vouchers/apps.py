# vouchers/apps.py
import os
from django.apps import AppConfig

class VouchersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vouchers'

    def ready(self):
        # CHỈ CHẠY khi đây là tiến trình chính (tránh chạy 2 lần do autoreload)
        if os.environ.get('RUN_MAIN') == 'true':
            from . import scheduler
            scheduler.start_jobs()