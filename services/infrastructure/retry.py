"""Centralized retry framework for TikTok Auto-Posting Machine.

Provides consistent retry logic with:
- Configurable retry count and delay
- Exponential backoff with jitter
- Retry classification (transient vs permanent)
- Detailed logging of retry attempts
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Type, Tuple

from services.exceptions import (
    RetryableError,
    FatalError,
    is_retryable_error,
    is_fatal_error,
    classify_error,
    RetryableProxyError,
    RetryableNetworkError,
    RetryableStorageError,
    RetryableAIError,
)

logger = logging.getLogger(__name__)


class RetryPolicy:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: float = 0.1,
        retryable_exceptions: Tuple[Type[Exception], ...] = (
            RetryableError,
            RetryableProxyError,
            RetryableNetworkError,
            RetryableStorageError,
            RetryableAIError,
        ),
        fatal_exceptions: Tuple[Type[Exception], ...] = (FatalError,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
        self.fatal_exceptions = fatal_exceptions

    def should_retry(self, exc: Exception, attempt: int) -> bool:
        """Determine if an exception should be retried."""
        if attempt >= self.max_retries:
            return False

        # Check fatal exceptions first
        if isinstance(exc, self.fatal_exceptions):
            return False

        # Check if explicitly retryable
        if isinstance(exc, self.retryable_exceptions):
            return True

        # Use classification functions
        if is_fatal_error(exc):
            return False

        if is_retryable_error(exc):
            return True

        return False

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay,
        )
        # Add jitter
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)


# Default policies for different operations
DEFAULT_POLICY = RetryPolicy(max_retries=3, base_delay=1.0, max_delay=60.0)

UPLOAD_POLICY = RetryPolicy(
    max_retries=2,
    base_delay=30.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=0.2,
)

STORAGE_POLICY = RetryPolicy(
    max_retries=3,
    base_delay=2.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=0.1,
)

AI_POLICY = RetryPolicy(
    max_retries=2,
    base_delay=5.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=0.2,
)

SCRAPE_POLICY = RetryPolicy(
    max_retries=3,
    base_delay=10.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=0.1,
)


def retry_with_policy(
    policy: RetryPolicy,
    operation_name: str = "operation",
    logger: Optional[logging.Logger] = None,
):
    """Decorator for retrying functions with a given policy.

    Args:
        policy: RetryPolicy to use
        operation_name: Name for logging
        logger: Logger instance (uses root if None)

    Returns:
        Decorated function
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None
            for attempt in range(policy.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    error_category = classify_error(exc)

                    if not policy.should_retry(exc, attempt):
                        logger.error(
                            "%s failed (attempt %d/%d): %s | Category: %s | Fatal: %s",
                            operation_name,
                            attempt + 1,
                            policy.max_retries + 1,
                            exc,
                            error_category,
                            is_fatal_error(exc),
                        )
                        raise

                    delay = policy.get_delay(attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s | Category: %s | Retrying in %.1fs",
                        operation_name,
                        attempt + 1,
                        policy.max_retries + 1,
                        exc,
                        error_category,
                        delay,
                    )
                    time.sleep(delay)

            # Should not reach here, but just in case
            raise last_exc

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None
            for attempt in range(policy.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    error_category = classify_error(exc)

                    if not policy.should_retry(exc, attempt):
                        logger.error(
                            "%s failed (attempt %d/%d): %s | Category: %s | Fatal: %s",
                            operation_name,
                            attempt + 1,
                            policy.max_retries + 1,
                            exc,
                            error_category,
                            is_fatal_error(exc),
                        )
                        raise

                    delay = policy.get_delay(attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s | Category: %s | Retrying in %.1fs",
                        operation_name,
                        attempt + 1,
                        policy.max_retries + 1,
                        exc,
                        error_category,
                        delay,
                    )
                    await asyncio.sleep(delay)

            raise last_exc

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class RetryContext:
    """Context manager for manual retry logic."""

    def __init__(
        self,
        policy: RetryPolicy,
        operation_name: str = "operation",
        logger: Optional[logging.Logger] = None,
    ):
        self.policy = policy
        self.operation_name = operation_name
        self.logger = logger or logging.getLogger(__name__)
        self.attempt = 0
        self.last_exc = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # Don't suppress exceptions

    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function with retry logic."""
        self.last_exc = None
        for self.attempt in range(self.policy.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                self.last_exc = exc
                error_category = classify_error(exc)

                if not self.policy.should_retry(exc, self.attempt):
                    self.logger.error(
                        "%s failed (attempt %d/%d): %s | Category: %s | Fatal: %s",
                        self.operation_name,
                        self.attempt + 1,
                        self.policy.max_retries + 1,
                        exc,
                        error_category,
                        is_fatal_error(exc),
                    )
                    raise

                delay = self.policy.get_delay(self.attempt)
                self.logger.warning(
                    "%s failed (attempt %d/%d): %s | Category: %s | Retrying in %.1fs",
                    self.operation_name,
                    self.attempt + 1,
                    self.policy.max_retries + 1,
                    exc,
                    error_category,
                    delay,
                )
                time.sleep(delay)

        raise self.last_exc

    async def execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an async function with retry logic."""
        self.last_exc = None
        for self.attempt in range(self.policy.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                self.last_exc = exc
                error_category = classify_error(exc)

                if not self.policy.should_retry(exc, self.attempt):
                    self.logger.error(
                        "%s failed (attempt %d/%d): %s | Category: %s | Fatal: %s",
                        self.operation_name,
                        self.attempt + 1,
                        self.policy.max_retries + 1,
                        exc,
                        error_category,
                        is_fatal_error(exc),
                    )
                    raise

                delay = self.policy.get_delay(self.attempt)
                self.logger.warning(
                    "%s failed (attempt %d/%d): %s | Category: %s | Retrying in %.1fs",
                    self.operation_name,
                    self.attempt + 1,
                    self.policy.max_retries + 1,
                    exc,
                    error_category,
                    delay,
                )
                await asyncio.sleep(delay)

        raise self.last_exc


def create_retry_context(
    operation_name: str,
    policy: Optional[RetryPolicy] = None,
    logger: Optional[logging.Logger] = None,
) -> RetryContext:
    """Create a RetryContext for manual retry control."""
    return RetryContext(
        policy=policy or DEFAULT_POLICY,
        operation_name=operation_name,
        logger=logger,
    )