import threading, sys, time, traceback, os

def dump_stack():
    time.sleep(5)
    with open("stack.txt", "w") as f:
        for thread_id, frame in sys._current_frames().items():
            f.write(f"\n--- Thread {thread_id} ---\n")
            traceback.print_stack(frame, file=f)
    os._exit(1)

threading.Thread(target=dump_stack, daemon=True).start()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartvoucher.settings')
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py', 'runserver', '--noreload'])
