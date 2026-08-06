"""Metrics service for TikTok Auto-Posting Machine.

Provides centralized metrics collection for operational visibility.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Counter:
    """Counter metric."""
    name: str
    value: int = 0
    labels: Dict[str, str] = field(default_factory=dict)

    def increment(self, amount: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
        self.value += amount
        if labels:
            self.labels.update(labels)


@dataclass
class Gauge:
    """Gauge metric (can go up and down)."""
    name: str
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.value = value
        if labels:
            self.labels.update(labels)

    def increment(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self.value += amount
        if labels:
            self.labels.update(labels)

    def decrement(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self.value -= amount
        if labels:
            self.labels.update(labels)


@dataclass
class Histogram:
    """Histogram metric for tracking distributions."""
    name: str
    buckets: List[float] = field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0])
    counts: List[int] = field(default_factory=lambda: [0] * 8)
    sum: float = 0.0
    count: int = 0
    labels: Dict[str, str] = field(default_factory=dict)

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.sum += value
        self.count += 1
        for i, bucket in enumerate(self.buckets):
            if value <= bucket:
                self.counts[i] += 1
                break
        if labels:
            self.labels.update(labels)


class MetricsService:
    """Centralized metrics collection service."""

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.RLock()
        self._start_time = datetime.utcnow()

    # Counter methods
    def counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> Counter:
        """Get or create a counter."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name=name, labels=labels or {})
            return self._counters[key]

    def increment_counter(
        self,
        name: str,
        amount: int = 1,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter."""
        self.counter(name, labels).increment(amount, labels)

    # Gauge methods
    def gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Gauge:
        """Get or create a gauge."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name=name, labels=labels or {})
            return self._gauges[key]

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge value."""
        self.gauge(name, labels).set(value, labels)

    def increment_gauge(
        self,
        name: str,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a gauge."""
        self.gauge(name, labels).increment(amount, labels)

    def decrement_gauge(
        self,
        name: str,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Decrement a gauge."""
        self.gauge(name, labels).decrement(amount, labels)

    # Histogram methods
    def histogram(
        self,
        name: str,
        buckets: Optional[List[float]] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Histogram:
        """Get or create a histogram."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name=name, labels=labels or {})
            return self._histograms[key]

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[List[float]] = None,
    ) -> None:
        """Observe a value in a histogram."""
        self.histogram(name, labels).observe(value, labels)

    @contextmanager
    def measure_time(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager to measure execution time."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.observe_histogram(f"{name}_duration_ms", duration_ms, labels)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a unique key for a metric."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    # Convenience methods for common metrics
    def record_upload_attempt(self, success: bool, product: str = "") -> None:
        """Record an upload attempt."""
        self.increment_counter("uploads_total", labels={"status": "success" if success else "failed", "product": product})
        if success:
            self.increment_counter("uploads_succeeded", labels={"product": product})
        else:
            self.increment_counter("uploads_failed", labels={"product": product})

    def record_retry(self, operation: str, reason: str = "") -> None:
        """Record a retry attempt."""
        self.increment_counter("retries_total", labels={"operation": operation, "reason": reason})

    def record_compliance_check(self, passed: bool, reason: str = "") -> None:
        """Record a compliance check result."""
        self.increment_counter("compliance_checks_total", labels={"result": "passed" if passed else "failed", "reason": reason})

    def record_processing_time(self, stage: str, duration_ms: float) -> None:
        """Record processing time for a pipeline stage."""
        self.observe_histogram(f"processing_time_ms", duration_ms, labels={"stage": stage})

    def record_upload_duration(self, duration_ms: float) -> None:
        """Record upload duration."""
        self.observe_histogram("upload_duration_ms", duration_ms)

    def record_queue_size(self, size: int) -> None:
        """Record current queue size."""
        self.set_gauge("queue_size", float(size))

    def record_storage_sync_duration(self, duration_ms: float, success: bool) -> None:
        """Record storage sync duration."""
        self.observe_histogram("storage_sync_duration_ms", duration_ms, labels={"status": "success" if success else "failed"})

    def record_ai_call(self, operation: str, success: bool, duration_ms: float) -> None:
        """Record an AI API call."""
        self.increment_counter("ai_calls_total", labels={"operation": operation, "status": "success" if success else "failed"})
        self.observe_histogram("ai_call_duration_ms", duration_ms, labels={"operation": operation})

    def record_proxy_check(self, success: bool, latency_ms: float) -> None:
        """Record proxy health check."""
        self.increment_counter("proxy_checks_total", labels={"status": "success" if success else "failed"})
        self.observe_histogram("proxy_check_latency_ms", latency_ms)

    def record_database_operation(self, operation: str, success: bool, duration_ms: float) -> None:
        """Record a database operation."""
        self.increment_counter("db_operations_total", labels={"operation": operation, "status": "success" if success else "failed"})
        self.observe_histogram("db_operation_duration_ms", duration_ms, labels={"operation": operation})

    # Export methods
    def get_counters(self) -> Dict[str, Dict[str, Any]]:
        """Get all counters as dict."""
        with self._lock:
            return {
                key: {"name": c.name, "value": c.value, "labels": c.labels}
                for key, c in self._counters.items()
            }

    def get_gauges(self) -> Dict[str, Dict[str, Any]]:
        """Get all gauges as dict."""
        with self._lock:
            return {
                key: {"name": g.name, "value": g.value, "labels": g.labels}
                for key, g in self._gauges.items()
            }

    def get_histograms(self) -> Dict[str, Dict[str, Any]]:
        """Get all histograms as dict."""
        with self._lock:
            result = {}
            for key, h in self._histograms.items():
                result[key] = {
                    "name": h.name,
                    "count": h.count,
                    "sum": h.sum,
                    "buckets": dict(zip([str(b) for b in h.buckets], h.counts)),
                    "labels": h.labels,
                }
            return result

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics as a single dict."""
        return {
            "uptime_seconds": (datetime.utcnow() - self._start_time).total_seconds(),
            "counters": self.get_counters(),
            "gauges": self.get_gauges(),
            "histograms": self.get_histograms(),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = datetime.utcnow()


# Global metrics instance
metrics = MetricsService()


# Convenience functions
def increment_counter(name: str, amount: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
    """Increment a counter."""
    metrics.increment_counter(name, amount, labels)


def set_gauge(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge value."""
    metrics.set_gauge(name, value, labels)


def observe_histogram(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
    """Observe a value in a histogram."""
    metrics.observe_histogram(name, value, labels)


def measure_time(name: str, labels: Optional[Dict[str, str]] = None):
    """Context manager to measure execution time."""
    return metrics.measure_time(name, labels)


def get_all_metrics() -> Dict[str, Any]:
    """Get all metrics."""
    return metrics.get_all_metrics()


def reset_metrics() -> None:
    """Reset all metrics."""
    metrics.reset()