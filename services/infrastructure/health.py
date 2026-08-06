"""Health check system for TikTok Auto-Posting Machine.

Provides comprehensive health checks for all system components.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.infrastructure.config import get_config
from services.infrastructure.database import Database
from services.infrastructure.logging import get_logger
from services.infrastructure.proxy_adapter import ProxyAdapter
from services.infrastructure.rclone_adapter import RcloneAdapter
from services.utils.paths import db_path, drive_root

logger = get_logger(__name__)


class HealthCheckResult:
    """Result of a health check."""

    def __init__(
        self,
        name: str,
        status: str,  # "healthy", "degraded", "unhealthy"
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


class HealthCheck:
    """Base class for health checks."""

    def __init__(self, name: str):
        self.name = name

    def check(self) -> HealthCheckResult:
        """Run the health check."""
        start = time.perf_counter()
        try:
            result = self._check()
            duration_ms = (time.perf_counter() - start) * 1000
            result.duration_ms = duration_ms
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception("Health check %s failed", self.name)
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=str(exc),
                duration_ms=duration_ms,
            )

    def _check(self) -> HealthCheckResult:
        """Implement the actual check logic."""
        raise NotImplementedError


class DatabaseHealthCheck(HealthCheck):
    """Check database connectivity and schema."""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__("database")
        self.db_path = db_path or str(db_path())

    def _check(self) -> HealthCheckResult:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")

            # Check critical tables exist
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}

            required_tables = {
                "posts",
                "raw_stock",
                "caption_pool",
                "competitor_data",
                "system_events",
                "videos",
                "daily_metrics",
                "competitor_videos",
                "competitor_daily",
                "daily_summary",
            }

            missing = required_tables - table_names

            conn.close()

            if missing:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=f"Missing tables: {', '.join(sorted(missing))}",
                    details={"missing_tables": sorted(missing)},
                )

            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="Database accessible, all tables present",
                details={"tables_count": len(table_names)},
            )

        except sqlite3.Error as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Database error: {exc}",
            )


class ConfigHealthCheck(HealthCheck):
    """Check configuration validity."""

    def _check(self) -> HealthCheckResult:
        try:
            cfg = get_config()
            config_data = cfg.get_section("")

            issues = []

            # Check required sections
            required_sections = [
                "telegram",
                "proxy",
                "ai",
                "tiktok",
                "posting",
                "content",
                "encoding",
                "analytics",
                "google_drive",
                "apify",
                "logging",
                "timezone",
            ]

            for section in required_sections:
                if section not in config_data:
                    issues.append(f"Missing section: {section}")

            # Check critical values
            telegram = config_data.get("telegram", {})
            if not telegram.get("bot_token"):
                issues.append("Missing telegram.bot_token")
            if not telegram.get("allowed_user_id"):
                issues.append("Missing telegram.allowed_user_id")

            proxy = config_data.get("proxy", {})
            if not proxy.get("endpoint"):
                issues.append("Missing proxy.endpoint")

            ai = config_data.get("ai", {})
            if ai.get("enable_ai") and not ai.get("api_key"):
                issues.append("AI enabled but no api_key")

            tiktok = config_data.get("tiktok", {})
            if not tiktok.get("session_username"):
                issues.append("Missing tiktok.session_username")

            status = "healthy" if not issues else "degraded"
            message = "Configuration valid" if not issues else f"Issues found: {len(issues)}"

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                details={"issues": issues},
            )

        except Exception as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Config check failed: {exc}",
            )


class StorageHealthCheck(HealthCheck):
    """Check storage availability."""

    def _check(self) -> HealthCheckResult:
        try:
            root = drive_root()
            details = {}

            # Check raw directory
            raw_dir = root / "raw"
            details["raw_exists"] = raw_dir.exists()
            if raw_dir.exists():
                products = [d for d in raw_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
                details["product_folders"] = len(products)

            # Check processed directory
            processed_dir = root / "processed"
            details["processed_exists"] = processed_dir.exists()

            # Check disk space
            stat = os.statvfs(root)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
            details["disk_free_gb"] = round(free_gb, 2)
            details["disk_total_gb"] = round(total_gb, 2)
            details["disk_usage_pct"] = round((1 - free_gb / total_gb) * 100, 1)

            if free_gb < 1.0:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=f"Low disk space: {free_gb:.1f} GB free",
                    details=details,
                )
            elif free_gb < 5.0:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message=f"Low disk space: {free_gb:.1f} GB free",
                    details=details,
                )

            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message=f"Storage OK: {free_gb:.1f} GB free",
                details=details,
            )

        except Exception as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Storage check failed: {exc}",
            )


class ProxyHealthCheck(HealthCheck):
    """Check proxy connectivity and geo."""

    def _check(self) -> HealthCheckResult:
        try:
            adapter = ProxyAdapter()
            proxy_url = adapter.get_current_proxy()

            if not proxy_url:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    message="No proxy configured",
                    details={"configured": False},
                )

            # Quick connectivity check (without geo)
            import requests
            proxies = {"http": proxy_url, "https": proxy_url}
            try:
                r = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=10)
                if r.status_code == 200:
                    return HealthCheckResult(
                        name=self.name,
                        status="healthy",
                        message="Proxy reachable",
                        details={"configured": True, "proxy": proxy_url[:20] + "..."},
                    )
                else:
                    return HealthCheckResult(
                        name=self.name,
                        status="unhealthy",
                        message=f"Proxy returned {r.status_code}",
                        details={"configured": True},
                    )
            except requests.Timeout:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="Proxy timeout",
                    details={"configured": True},
                )
            except requests.RequestException as exc:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message=f"Proxy connection failed: {exc}",
                    details={"configured": True},
                )

        except Exception as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"Proxy check failed: {exc}",
            )


class RcloneHealthCheck(HealthCheck):
    """Check rclone availability."""

    def _check(self) -> HealthCheckResult:
        import subprocess
        try:
            result = subprocess.run(
                ["rclone", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="rclone available",
                    details={"version": version_line},
                )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="rclone command failed",
                )
        except FileNotFoundError:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="rclone not installed",
            )
        except Exception as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"rclone check failed: {exc}",
            )


class FFmpegHealthCheck(HealthCheck):
    """Check ffmpeg availability."""

    def _check(self) -> HealthCheckResult:
        import subprocess
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    message="ffmpeg available",
                    details={"version": version_line},
                )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="unhealthy",
                    message="ffmpeg command failed",
                )
        except FileNotFoundError:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message="ffmpeg not installed",
            )
        except Exception as exc:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"ffmpeg check failed: {exc}",
            )


class HealthCheckRegistry:
    """Registry for managing and running health checks."""

    def __init__(self):
        self.checks: List[HealthCheck] = []

    def register(self, check: HealthCheck) -> None:
        """Register a health check."""
        self.checks.append(check)

    def run_all(self) -> Dict[str, Any]:
        """Run all registered health checks."""
        results = {}
        overall_status = "healthy"

        for check in self.checks:
            result = check.check()
            results[check.name] = result.to_dict()

            if result.status == "unhealthy":
                overall_status = "unhealthy"
            elif result.status == "degraded" and overall_status == "healthy":
                overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": results,
        }

    def run_check(self, name: str) -> Optional[HealthCheckResult]:
        """Run a specific health check by name."""
        for check in self.checks:
            if check.name == name:
                return check.check()
        return None


# Global registry instance
health_registry = HealthCheckRegistry()

# Register default checks
health_registry.register(DatabaseHealthCheck())
health_registry.register(ConfigHealthCheck())
health_registry.register(StorageHealthCheck())
health_registry.register(ProxyHealthCheck())
health_registry.register(RcloneHealthCheck())
health_registry.register(FFmpegHealthCheck())


def run_health_checks() -> Dict[str, Any]:
    """Run all health checks and return results."""
    return health_registry.run_all()


def get_health_status() -> str:
    """Get overall health status."""
    results = health_registry.run_all()
    return results["status"]


if __name__ == "__main__":
    import json
    results = run_health_checks()
    print(json.dumps(results, indent=2))