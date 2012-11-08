import atexit
import Queue
import threading
import functools

from django.core.mail import mail_admins

def _worker():
    while True:
        func, args, kwargs = _queue.get()
        try:
            func(*args, **kwargs)
        except:
            import traceback
            details = traceback.format_exc()
            mail_admins('Background process exception', details)
        finally:
            _queue.task_done()  # so we can join at exit

def postpone(f):
    @functools.wraps(f)
    def wrapper (*args, **kwargs):
        _queue.put((f, args, kwargs))
    return wrapper


_queue = Queue.Queue()
_thread = threading.Thread(target=_worker)
_thread.daemon = True
_thread.start()

def _cleanup():
    _queue.join()   # so we don't exit too soon

atexit.register(_cleanup)