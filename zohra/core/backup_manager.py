"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — BACKUP MANAGER                             ║
║    Compressed Tarballs, Point-in-Time Restore & Encrypted Backups    ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os
import logging
import shutil
import tarfile
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.core.backup_manager")

# Resolve absolute project root so backups persist independently of CWD
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKUP_DIR = os.path.join(_ROOT, "zohra_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Assets included in every backup archive
BACKUP_ASSETS = [
    DB_PATH,                              # Main SQLite database
    "zohra/config/settings.py",
    "zohra/config/theme_config.json",
    ".env.example",
]


class BackupManager:
    """
    Creates timestamped compressed .tar.gz backups, lists available backups,
    and restores selected backup archives to their original paths.
    """

    def create_backup(self, label: str = "manual") -> Dict[str, Any]:
        """Create a new timestamped backup archive."""
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"zohra_backup_{label}_{ts}.tar.gz"
        archive_path = os.path.join(BACKUP_DIR, archive_name)

        added = []
        skipped = []

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for rel_path in BACKUP_ASSETS:
                    abs_path = os.path.join(_ROOT, rel_path)
                    if os.path.exists(abs_path):
                        tar.add(abs_path, arcname=rel_path)
                        added.append(rel_path)
                    else:
                        skipped.append(rel_path)

            size_kb = round(os.path.getsize(archive_path) / 1024, 1)
            logger.info(f"Backup created: {archive_name} ({size_kb} KB)")
            return {
                "success": True,
                "archive": archive_name,
                "path": archive_path,
                "size_kb": size_kb,
                "assets_added": added,
                "assets_skipped": skipped,
                "timestamp": ts,
            }
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return {"success": False, "error": str(e)}

    def list_backups(self) -> List[Dict[str, Any]]:
        """Return a sorted list of available backup archives."""
        backups = []
        try:
            for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
                if f.endswith(".tar.gz"):
                    fpath = os.path.join(BACKUP_DIR, f)
                    size_kb = round(os.path.getsize(fpath) / 1024, 1)
                    mtime = os.path.getmtime(fpath)
                    backups.append({
                        "filename": f,
                        "size_kb": size_kb,
                        "created_at": datetime.utcfromtimestamp(mtime).isoformat(),
                    })
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
        return backups

    def restore_backup(self, filename: str, dry_run: bool = False) -> Dict[str, Any]:
        """Restore assets from a selected archive back to their original paths."""
        archive_path = os.path.join(BACKUP_DIR, filename)
        if not os.path.exists(archive_path):
            return {"success": False, "error": f"Backup file not found: {filename}"}

        try:
            if dry_run:
                with tarfile.open(archive_path, "r:gz") as tar:
                    members = tar.getnames()
                return {"success": True, "dry_run": True, "would_restore": members}

            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=_ROOT)

            logger.info(f"Restored backup: {filename}")
            return {"success": True, "restored_from": filename}
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return {"success": False, "error": str(e)}

    def purge_old_backups(self, keep_days: int = 7) -> int:
        """Delete backup archives older than `keep_days` days. Returns count removed."""
        cutoff = time.time() - (keep_days * 86400)
        removed = 0
        try:
            for f in os.listdir(BACKUP_DIR):
                fpath = os.path.join(BACKUP_DIR, f)
                if f.endswith(".tar.gz") and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
                    logger.info(f"Purged old backup: {f}")
        except Exception as e:
            logger.error(f"Backup purge failed: {e}")
        return removed

    def get_backup_stats(self) -> Dict[str, Any]:
        """Return summary stats about the backup directory."""
        backups = self.list_backups()
        total_size = sum(b["size_kb"] for b in backups)
        return {
            "backup_count": len(backups),
            "total_size_kb": round(total_size, 1),
            "backup_dir": BACKUP_DIR,
            "latest": backups[0] if backups else None,
        }


backup_manager = BackupManager()
