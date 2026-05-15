import threading
import logging
from notifications.tasks import send_queued_emails
from certificates.tasks import generate_pending_certificates

logger = logging.getLogger('certiflow')

def run_tasks_async():
    """
    Runs pending tasks in a separate thread.
    Useful for development when a dedicated Celery worker/cron isn't running.
    """
    def task_runner():
        try:
            # Process emails
            send_queued_emails()
            # Process certificates
            generate_pending_certificates()
        except Exception as e:
            logger.error(f"Error in async task runner: {str(e)}")

    thread = threading.Thread(target=task_runner)
    thread.daemon = True # Thread dies when main process dies
    thread.start()

def trigger_background_tasks():
    """
    Public function to trigger tasks. 
    Can be called from views or signals.
    """
    run_tasks_async()
