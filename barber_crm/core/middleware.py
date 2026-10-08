from .backup import create_daily_backup_if_needed, cleanup_old_backups

class DailyBackupMiddleware:
    """First request of each day creates an automatic backup."""
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        try:
            create_daily_backup_if_needed()
            cleanup_old_backups()
        except Exception:
            # A backup failure must never break the CRM.
            pass
        return self.get_response(request)
