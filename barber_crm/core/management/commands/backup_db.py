from django.core.management.base import BaseCommand
from core.backup import create_backup, cleanup_old_backups

class Command(BaseCommand):
    help = "BARBER AURA ma'lumotlar bazasi va media fayllarining zaxira nusxasini yaratadi."

    def handle(self, *args, **options):
        path = create_backup()
        cleanup_old_backups()
        if path:
            self.stdout.write(self.style.SUCCESS(f"Backup yaratildi: {path}"))
        else:
            self.stdout.write(self.style.WARNING("DB topilmadi, backup yaratilmadi."))
