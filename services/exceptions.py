"""Exception hierarchy for TikTok Auto-Posting Machine.

Provides a structured exception system for proper error handling,
retry logic, and operational visibility.
"""

from __future__ import annotations


class TiktokFlowsError(Exception):
    """Base exception for all TikTok Flows errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# Configuration Errors
class ConfigurationError(TiktokFlowsError):
    """Raised when configuration is invalid or missing."""

    pass


class ConfigValidationError(ConfigurationError):
    """Raised when config validation fails."""

    pass


class ConfigNotFoundError(ConfigurationError):
    """Raised when config file is not found."""

    pass


# Storage Errors
class StorageError(TiktokFlowsError):
    """Raised when storage operations fail."""

    pass


class DriveSyncError(StorageError):
    """Raised when Google Drive sync fails."""

    pass


class DriveCleanupError(StorageError):
    """Raised when Drive cleanup fails."""

    pass


class LocalStorageError(StorageError):
    """Raised when local file operations fail."""

    pass


class InsufficientSpaceError(StorageError):
    """Raised when storage space is insufficient."""

    pass


# Upload Errors
class UploadError(TiktokFlowsError):
    """Raised when upload operations fail."""

    pass


class ProxyError(UploadError):
    """Raised when proxy-related issues occur."""

    pass


class ProxyTransportError(ProxyError):
    """Raised when proxy transport fails (connection, timeout)."""

    pass


class ProxyGeoError(ProxyError):
    """Raised when proxy geo verification fails."""

    pass


class ProxyAuthError(ProxyError):
    """Raised when proxy authentication fails."""

    pass


class CookieError(UploadError):
    """Raised when session cookies are invalid or expired."""

    pass


class TikTokAPIError(UploadError):
    """Raised when TikTok API returns an error."""

    pass


class TikTokRateLimitError(TikTokAPIError):
    """Raised when TikTok API rate limit is hit."""

    pass


class TikTokAuthError(TikTokAPIError):
    """Raised when TikTok authentication fails."""

    pass


# Compliance Errors
class ComplianceError(TiktokFlowsError):
    """Raised when compliance checks fail."""

    pass


class BannedPhraseError(ComplianceError):
    """Raised when banned phrase is detected."""

    pass


class MedicalClaimError(ComplianceError):
    """Raised when medical claim is detected."""

    pass


class PriceGuaranteeError(ComplianceError):
    """Raised when price guarantee is detected."""

    pass


class SuperlativeError(ComplianceError):
    """Raised when superlative claim is detected."""

    pass


class GuaranteedResultError(ComplianceError):
    """Raised when guaranteed result claim is detected."""

    pass


# Network Errors
class NetworkError(TiktokFlowsError):
    """Raised when network operations fail."""

    pass


class TimeoutError(NetworkError):
    """Raised when network operation times out."""

    pass


class ConnectionError(NetworkError):
    """Raised when connection fails."""

    pass


class DNSError(NetworkError):
    """Raised when DNS resolution fails."""

    pass


# Analytics Errors
class AnalyticsError(TiktokFlowsError):
    """Raised when analytics operations fail."""

    pass


class ScrapeError(AnalyticsError):
    """Raised when competitor scraping fails."""

    pass


class ReconcileError(AnalyticsError):
    """Raised when metrics reconciliation fails."""

    pass


class ReportGenerationError(AnalyticsError):
    """Raised when report generation fails."""

    pass


# Scheduler Errors
class SchedulerError(TiktokFlowsError):
    """Raised when scheduler operations fail."""

    pass


class QuietHoursError(SchedulerError):
    """Raised when attempting to post during quiet hours."""

    pass


# AI Errors
class AIError(TiktokFlowsError):
    """Raised when AI operations fail."""

    pass


class AIUnavailableError(AIError):
    """Raised when AI service is unavailable."""

    pass


class AIRateLimitError(AIError):
    """Raised when AI rate limit is exceeded."""

    pass


class AIQuotaExceededError(AIError):
    """Raised when AI daily quota is exceeded."""

    pass


class AIResponseError(AIError):
    """Raised when AI returns invalid response."""

    pass


# Database Errors
class DatabaseError(TiktokFlowsError):
    """Raised when database operations fail."""

    pass


class SchemaError(DatabaseError):
    """Raised when database schema is invalid."""

    pass


class MigrationError(DatabaseError):
    """Raised when database migration fails."""

    pass


# Retry Classification
class RetryableError(TiktokFlowsError):
    """Base class for errors that can be retried.

    Errors inheriting from this class indicate transient failures
    that may succeed on retry.
    """

    def __init__(self, message: str, details: dict = None, retry_after: float = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class FatalError(TiktokFlowsError):
    """Base class for errors that should NOT be retried.

    Errors inheriting from this class indicate permanent failures
    that will not succeed on retry.
    """

    pass


# Mix-in for retryable network errors
class RetryableNetworkError(NetworkError, RetryableError):
    """Network error that can be retried."""

    pass


# Mix-in for retryable proxy errors
class RetryableProxyError(ProxyError, RetryableError):
    """Proxy error that can be retried."""

    pass


# Mix-in for retryable AI errors
class RetryableAIError(AIError, RetryableError):
    """AI error that can be retried."""

    pass


# Mix-in for retryable storage errors
class RetryableStorageError(StorageError, RetryableError):
    """Storage error that can be retried."""

    pass


# Mix-in for fatal configuration errors
class FatalConfigurationError(ConfigurationError, FatalError):
    """Configuration error that cannot be resolved by retry."""

    pass


# Mix-in for fatal auth errors
class FatalAuthError(TikTokAuthError, FatalError):
    """Authentication error that cannot be resolved by retry."""

    pass


def is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: Exception to check

    Returns:
        True if error is retryable, False otherwise
    """
    return isinstance(exc, RetryableError)


def is_fatal_error(exc: Exception) -> bool:
    """Check if an exception is fatal (non-retryable).

    Args:
        exc: Exception to check

    Returns:
        True if error is fatal, False otherwise
    """
    return isinstance(exc, FatalError)


def classify_error(exc: Exception) -> str:
    """Classify an error for logging/metrics.

    Args:
        exc: Exception to classify

    Returns:
        Error category string
    """
    if isinstance(exc, RetryableError):
        return "retryable"
    elif isinstance(exc, FatalError):
        return "fatal"
    elif isinstance(exc, ConfigurationError):
        return "configuration"
    elif isinstance(exc, StorageError):
        return "storage"
    elif isinstance(exc, UploadError):
        return "upload"
    elif isinstance(exc, ComplianceError):
        return "compliance"
    elif isinstance(exc, NetworkError):
        return "network"
    elif isinstance(exc, AnalyticsError):
        return "analytics"
    elif isinstance(exc, SchedulerError):
        return "scheduler"
    elif isinstance(exc, AIError):
        return "ai"
    elif isinstance(exc, DatabaseError):
        return "database"
    else:
        return "unknown"