"""Database backup and safety utilities for production operations."""

import os
import sqlite3
import shutil
import json
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import subprocess
import hashlib


class DatabaseBackupManager:
    """Manages database backups with rotation, validation, and restore capabilities."""
    
    def __init__(self, db_path: str, backup_dir: str = "backups", 
                 max_backups: int = 30, compress: bool = True):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.compress = compress
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def create_backup(self, app_version: str = "unknown") -> Path:
        """Create a timestamped backup of the database with metadata."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{self.db_path.stem}_{timestamp}"
        
        if self.compress:
            backup_path = self.backup_dir / f"{base_name}.db.gz"
            # Create compressed backup using sqlite3 dump + gzip
            self._create_compressed_backup(backup_path)
        else:
            backup_path = self.backup_dir / f"{base_name}.db"
            shutil.copy2(self.db_path, backup_path)
        
        # Create metadata file
        metadata = {
            "timestamp": timestamp,
            "source_db": str(self.db_path),
            "backup_file": backup_path.name,
            "app_version": app_version,
            "schema_version": self._get_schema_version(),
            "size_bytes": backup_path.stat().st_size,
            "checksum_sha256": self._compute_checksum(backup_path),
        }
        
        metadata_path = backup_path.with_suffix(backup_path.suffix + ".meta.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        # Rotate old backups
        self._rotate_backups()
        
        return backup_path
    
    def _create_compressed_backup(self, backup_path: Path):
        """Create compressed backup using sqlite3 dump."""
        with sqlite3.connect(self.db_path) as conn:
            # Get the SQL dump
            dump_lines = []
            for line in conn.iterdump():
                dump_lines.append(line)
        
        # Compress and write
        dump_text = "\n".join(dump_lines)
        with gzip.open(backup_path, "wt", encoding="utf-8") as f:
            f.write(dump_text)
    
    def _get_schema_version(self) -> str:
        """Get schema version from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT * FROM pragma_user_version").fetchone()
                if row:
                    return str(row[0])
        except Exception:
            pass
        return "unknown"
    
    def _compute_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _rotate_backups(self):
        """Remove old backups beyond max_backups limit."""
        backups = sorted(self.backup_dir.glob("*.db*"))
        if len(backups) > self.max_backups:
            for old in backups[:-self.max_backups]:
                old.unlink(missing_ok=True)
                # Also remove metadata
                meta = old.with_suffix(old.suffix + ".meta.json")
                meta.unlink(missing_ok=True)
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups with metadata."""
        backups = []
        for backup_file in sorted(self.backup_dir.glob("*.db*")):
            if backup_file.suffix == ".json":
                continue
            meta_file = backup_file.with_suffix(backup_file.suffix + ".meta.json")
            meta = {}
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)
            backups.append({
                "file": backup_file.name,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "modified": datetime.fromtimestamp(backup_file.stat().st_mtime, tz=timezone.utc).isoformat(),
                "metadata": meta,
            })
        return backups
    
    def validate_backup(self, backup_path: Path) -> Dict[str, Any]:
        """Validate a backup file integrity."""
        result = {
            "valid": False,
            "checksum_match": False,
            "schema_readable": False,
            "table_count": 0,
            "row_counts": {},
            "errors": []
        }
        
        try:
            # Verify checksum if metadata exists
            meta_path = backup_path.with_suffix(backup_path.suffix + ".meta.json")
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                expected_checksum = meta.get("checksum_sha256")
                actual_checksum = self._compute_checksum(backup_path)
                result["checksum_match"] = (expected_checksum == actual_checksum)
                if not result["checksum_match"]:
                    result["errors"].append("Checksum mismatch")
            
            # Try to read schema and count tables/rows
            if backup_path.suffix == ".gz":
                import gzip
                with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                    content = f.read()
            else:
                with open(backup_path, "r") as f:
                    content = f.read()
            
            # Count CREATE TABLE statements
            import re
            tables = re.findall(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["\']?(\w+)["\']?', content, re.IGNORECASE)
            result["table_count"] = len(tables)
            result["schema_readable"] = True
            
            # Try to restore to temp and count rows
            temp_db = Path("/tmp") / f"validate_{datetime.now().timestamp()}.db"
            try:
                with sqlite3.connect(temp_db) as conn:
                    conn.executescript(content)
                    for table in tables:
                        try:
                            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                            result["row_counts"][table] = count
                        except Exception:
                            result["row_counts"][table] = "error"
                result["valid"] = True
            finally:
                temp_db.unlink(missing_ok=True)
                
        except Exception as e:
            result["errors"].append(str(e))
        
        return result
    
    def restore_backup(self, backup_path: Path, target_path: Optional[Path] = None) -> bool:
        """Restore database from backup."""
        if target_path is None:
            target_path = self.db_path
        
        # Backup current database first if it exists
        if target_path.exists():
            current_backup = target_path.with_suffix(f".pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy2(target_path, current_backup)
        
        try:
            if backup_path.suffix == ".gz":
                import gzip
                with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                    content = f.read()
            else:
                with open(backup_path, "r") as f:
                    content = f.read()
            
            with sqlite3.connect(target_path) as conn:
                conn.executescript(content)
            
            return True
        except Exception as e:
            # Try to restore original if we made a backup
            if 'current_backup' in locals() and current_backup.exists():
                shutil.copy2(current_backup, target_path)
            raise RuntimeError(f"Restore failed: {e}")
    
    def check_integrity(self) -> Dict[str, Any]:
        """Run integrity checks on the current database."""
        result = {
            "integrity_ok": False,
            "foreign_keys_ok": False,
            "indexes_ok": False,
            "page_count": 0,
            "freelist_count": 0,
            "errors": []
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # PRAGMA integrity_check
                integrity = conn.execute("PRAGMA integrity_check").fetchone()
                result["integrity_ok"] = (integrity[0] == "ok")
                if not result["integrity_ok"]:
                    result["errors"].append(f"Integrity check failed: {integrity[0]}")
                
                # PRAGMA foreign_key_check
                fk_check = conn.execute("PRAGMA foreign_key_check").fetchall()
                result["foreign_keys_ok"] = len(fk_check) == 0
                if not result["foreign_keys_ok"]:
                    result["errors"].append(f"Foreign key violations: {fk_check}")
                
                # Page counts
                page_info = conn.execute("PRAGMA page_count").fetchone()
                result["page_count"] = page_info[0] if page_info else 0
                
                freelist = conn.execute("PRAGMA freelist_count").fetchone()
                result["freelist_count"] = freelist[0] if freelist else 0
                
                # Quick index check
                indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
                result["indexes_ok"] = len(indexes) > 0
                
        except Exception as e:
            result["errors"].append(str(e))
        
        return result


def create_backup_manager(db_path: str, backup_dir: str = "backups") -> DatabaseBackupManager:
    """Factory function for DatabaseBackupManager."""
    return DatabaseBackupManager(db_path, backup_dir)