"""Diagnostics module for TikTok Auto-Posting Machine.

Collects comprehensive system information for debugging and troubleshooting.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.infrastructure.config import get_config
from services.infrastructure.database import Database
from services.infrastructure.logging import get_logger
from services.utils.paths import db_path, drive_root

logger = get_logger(__name__)


def get_system_info() -> Dict[str, Any]:
    """Collect system-level information."""
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_executable": sys.executable,
        },
        "environment": {
            "user": os.getenv("USER", "unknown"),
            "home": os.getenv("HOME", "unknown"),
            "pwd": os.getcwd(),
            "timezone": time.tzname,
        },
        "process": {
            "pid": os.getpid(),
            "start_time": datetime.fromtimestamp(time.time()).isoformat(),
        },
    }


def get_dependency_versions() -> Dict[str, str]:
    """Get versions of key dependencies."""
    versions = {}

    # Python packages
    packages = [
        "requests",
        "yaml",
        "sqlite3",
        "ffmpeg",
        "skia",
        "rclone",
    ]

    for pkg in packages:
        try:
            if pkg == "yaml":
                import yaml
                versions[pkg] = yaml.__version__
            elif pkg == "sqlite3":
                versions[pkg] = "built-in"
            elif pkg == "requests":
                import requests
                versions[pkg] = requests.__version__
            elif pkg in ["ffmpeg", "skia", "rclone"]:
                # External tools
                try:
                    result = subprocess.run(
                        [pkg, "-version"] if pkg != "rclone" else [pkg, "version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        versions[pkg] = result.stdout.split("\n")[0]
                    else:
                        versions[pkg] = "not found"
                except FileNotFoundError:
                    versions[pkg] = "not installed"
        except ImportError:
            versions[pkg] = "not installed"

    return versions


def get_config_summary() -> Dict[str, Any]:
    """Get sanitized configuration summary (no secrets)."""
    try:
        cfg = get_config()
        config = cfg.get_section("")

        # Remove sensitive values
        sensitive_keys = [
            "api_key",
            "token",
            "password",
            "secret",
            "bot_token",
            "allowed_user_id",
            "endpoint",
        ]

        def sanitize(obj: Any, path: str = "") -> Any:
            if isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    full_path = f"{path}.{k}" if path else k
                    if any(sensitive in k.lower() for sensitive in sensitive_keys):
                        result[k] = "***REDACTED***"
                    else:
                        result[k] = sanitize(v, full_path)
                return result
            elif isinstance(obj, list):
                return [sanitize(item, path) for item in obj]
            else:
                return obj

        return sanitize(config)

    except Exception as exc:
        return {"error": f"Failed to get config: {exc}"}


def get_directory_structure(root: Path, max_depth: int = 3, current_depth: int = 0) -> Dict[str, Any]:
    """Get directory structure up to max_depth."""
    if current_depth >= max_depth:
        return {"...": "max depth reached"}

    result = {}
    try:
        for item in sorted(root.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                result[item.name] = get_directory_structure(item, max_depth, current_depth + 1)
            else:
                stat = item.stat()
                result[item.name] = {
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
    except PermissionError:
        result["<permission denied>"] = True
    except Exception:
        result["<error>"] = True

    return result


def get_file_system_info() -> Dict[str, Any]:
    """Get filesystem information."""
    root = drive_root()
    result = {}

    try:
        stat = os.statvfs(root)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        used_gb = total_gb - free_gb

        result["disk"] = {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "usage_pct": round((used_gb / total_gb) * 100, 1),
        }

        # Directory structure
        result["structure"] = get_directory_structure(root, max_depth=2)

    except Exception as exc:
        result["error"] = f"Failed to get filesystem info: {exc}"

    return result


def get_database_info() -> Dict[str, Any]:
    """Get database information."""
    result = {}

    try:
        db_file = Path(db_path())
        if db_file.exists():
            stat = db_file.stat()
            result["file"] = {
                "path": str(db_file),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

        # Get table info
        conn = sqlite3.connect(str(db_path()), timeout=5)
        conn.row_factory = sqlite3.Row

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        table_info = {}
        for table in tables:
            name = table["name"]
            count = conn.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()["c"]
            table_info[name] = {"rows": count}

        result["tables"] = table_info

        conn.close()

    except Exception as exc:
        result["error"] = f"Failed to get database info: {exc}"

    return result


def get_queue_status() -> Dict[str, Any]:
    """Get upload queue status."""
    from services.utils.paths import queue_dir

    result = {"queue_dir": str(queue_dir()), "videos": []}

    try:
        qdir = queue_dir()
        if qdir.exists():
            for mp4 in qdir.glob("*.mp4"):
                stat = mp4.stat()
                result["videos"].append({
                    "name": mp4.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        result["count"] = len(result["videos"])
    except Exception as exc:
        result["error"] = f"Failed to get queue status: {exc}"

    return result


def get_process_info() -> Dict[str, Any]:
    """Get current process information."""
    import psutil

    process = psutil.Process(os.getpid())

    return {
        "pid": os.getpid(),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
        "threads": process.num_threads(),
        "open_files": len(process.open_files()),
        "connections": len(process.connections()),
        "create_time": datetime.fromtimestamp(process.create_time()).isoformat(),
    }


def get_network_info() -> Dict[str, Any]:
    """Get network connectivity information."""
    import socket

    result = {}

    # Check key endpoints
    endpoints = {
        "tiktok_api": "api.tiktok.com",
        "google_drive": "www.googleapis.com",
        "telegram": "api.telegram.org",
        "ip_api": "ip-api.com",
        "ipinfo": "ipinfo.io",
    }

    for name, host in endpoints.items():
        try:
            start = time.time()
            socket.create_connection((host, 443), timeout=5)
            latency = round((time.time() - start) * 1000, 2)
            result[name] = {"status": "reachable", "latency_ms": latency}
        except Exception as exc:
            result[name] = {"status": "unreachable", "error": str(exc)}

    return result


def collect_diagnostics(include_sensitive: bool = False) -> Dict[str, Any]:
    """Collect comprehensive diagnostics report.

    Args:
        include_sensitive: Whether to include sensitive config values

    Returns:
        Complete diagnostics report
    """
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "system": get_system_info(),
        "dependencies": get_dependency_versions(),
        "config": get_config_summary() if not include_sensitive else get_config_summary(),
        "filesystem": get_file_system_info(),
        "database": get_database_info(),
        "queue": get_queue_status(),
        "process": get_process_info(),
        "network": get_network_info(),
    }

    return report


def write_diagnostics_report(
    output_path: Optional[str] = None,
    include_sensitive: bool = False,
) -> str:
    """Write diagnostics report to file.

    Args:
        output_path: Path to write report (auto-generated if None)
        include_sensitive: Whether to include sensitive config values

    Returns:
        Path to written report
    """
    import json

    if output_path is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = f"logs/diagnostics_{timestamp}.json"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    report = collect_diagnostics(include_sensitive=include_sensitive)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Diagnostics report written to %s", output_path)
    return output_path


def print_diagnostics(include_sensitive: bool = False) -> None:
    """Print diagnostics report to stdout."""
    import json
    report = collect_diagnostics(include_sensitive=include_sensitive)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    print_diagnostics()