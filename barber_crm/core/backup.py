from __future__ import annotations
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings

KEEP_BACKUPS = 14


def create_backup() -> Path | None:
    """Create a safe SQLite + media ZIP backup. Returns its path."""
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        return None
    backup_dir = Path(settings.BASE_DIR) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"barber_aura_backup_{stamp}.zip"

    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(suffix=".sqlite3", dir=str(backup_dir))
        os.close(fd)
        tmp = Path(tmp_name)
        source = sqlite3.connect(str(db_path), timeout=30)
        target = sqlite3.connect(str(tmp))
        with target:
            source.backup(target)
        target.close()
        source.close()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp, "db.sqlite3")
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                for p in media.rglob("*"):
                    if p.is_file():
                        zf.write(p, str(Path("media") / p.relative_to(media)))
        return zip_path
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def create_daily_backup_if_needed() -> Path | None:
    backup_dir = Path(settings.BASE_DIR) / "backups"
    today = datetime.now().strftime("%Y%m%d")
    if any(backup_dir.glob(f"barber_aura_backup_{today}_*.zip")):
        return None
    return create_backup()


def cleanup_old_backups() -> None:
    backup_dir = Path(settings.BASE_DIR) / "backups"
    backups = sorted(backup_dir.glob("barber_aura_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass
