"""Structured logging infrastructure for TikTok Auto-Posting Machine.

Provides centralized logging configuration with:
- Consistent formatting
- Console and rotating file handlers
- Configurable log levels
- Correlation ID support for request tracing
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from services.infrastructure.config import get_config


# Context variable for correlation ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        return True


class SecretMaskingFilter(logging.Filter):
    """Mask secrets in log records before they are emitted."""

    # Patterns for common secret types
    MASK_PATTERNS = [
        # API keys
        (re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        # Tokens
        (re.compile(r'(?i)(token|access[_-]?token|bearer)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        # Passwords
        (re.compile(r'(?i)(password|passwd|secret)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        # Cookies/session
        (re.compile(r'(?i)(cookie|session[_-]?id)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        # Proxy URLs with credentials
        (re.compile(r'(?i)(proxy[_-]?(?:url|endpoint)?)\s*[:=]\s*["\']?(https?://[^"\'\s]+)'), r'\1=****'),
        # URLs with credentials in general
        (re.compile(r'https?://[^:\s]+:[^@\s]+@'), r'http://***:***@'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        # Mask secrets in the message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._mask_string(record.msg)
        # Also mask args if they are strings
        if hasattr(record, 'args') and record.args:
            masked_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    masked_args.append(self._mask_string(arg))
                else:
                    masked_args.append(arg)
            record.args = tuple(masked_args)
        return True

    def _mask_string(self, value: str) -> str:
        """Mask secrets in a string."""
        for pattern, replacement in self.MASK_PATTERNS:
            value = pattern.sub(replacement, value)
        return value


class StructuredFormatter(logging.Formatter):
    """Structured log formatter with correlation ID."""

    def format(self, record: logging.LogRecord) -> str:
        # Ensure correlation_id is present
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id_var.get() or "-"
        return super().format(record)


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = False,
) -> logging.Logger:
    """Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None to disable file logging)
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
        json_format: Whether to use JSON formatting

    Returns:
        Root logger instance
    """
    cfg = get_config()
    log_cfg = cfg.get_section("logging")

    # Determine log level
    if level is None:
        level = log_cfg.get("level", "INFO")
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Determine log file path
    if log_file is None:
        log_file = log_cfg.get("file")

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.addFilter(CorrelationFilter())
    console_handler.addFilter(SecretMaskingFilter())

    if json_format:
        console_handler.setFormatter(
            StructuredFormatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "correlation_id": "%(correlation_id)s", '
                '"message": "%(message)s"}',
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    else:
        console_handler.setFormatter(
            StructuredFormatter(
                "%(asctime)s [%(levelname)s] %(name)s [%(correlation_id)s]: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(console_handler)

    # File handler (rotating)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.addFilter(CorrelationFilter())
        file_handler.addFilter(SecretMaskingFilter())

        if json_format:
            file_handler.setFormatter(
                StructuredFormatter(
                    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                    '"logger": "%(name)s", "correlation_id": "%(correlation_id)s", '
                    '"message": "%(message)s"}',
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        else:
            file_handler.setFormatter(
                StructuredFormatter(
                    "%(asctime)s [%(levelname)s] %(name)s [%(correlation_id)s]: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for current context.

    Args:
        correlation_id: Correlation ID (generated if None)

    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    correlation_id_var.set(correlation_id)
    return correlation_id


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id_var.set(None)


def with_correlation(correlation_id: Optional[str] = None):
    """Context manager for correlation ID.

    Usage:
        with with_correlation("job-123"):
            logger.info("Processing job")
    """
    from contextlib import contextmanager

    @contextmanager
    def _context():
        old_id = correlation_id_var.get()
        try:
            set_correlation_id(correlation_id)
            yield
        finally:
            if old_id is not None:
                correlation_id_var.set(old_id)
            else:
                clear_correlation_id()

    return _context()