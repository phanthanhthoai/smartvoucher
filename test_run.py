import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartvoucher.settings')

try:
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'runserver', '--noreload'])
except Exception:
    with open('crash.txt', 'w') as f:
        f.write(traceback.format_exc())
