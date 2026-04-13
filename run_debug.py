import os, sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartvoucher.settings')

try:
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8000', '--noreload', '--nothreading'])
except Exception as e:
    import traceback
    with open('error_log.txt', 'w') as f:
        f.write(traceback.format_exc())
