"""Monitoring endpoints for external monitoring systems.

Provides HTTP endpoints for health checks and metrics exposition.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SERVICES_DIR))

# Enable testing mode
os.environ["TESTING"] = "1"

from fastapi import FastAPI, Response
from pydantic import BaseModel

from services.infrastructure.health import run_health_checks, get_health_status
from services.core.metrics_service import metrics
from services.infrastructure.logging import get_logger

logger = get_logger("monitoring")

app = FastAPI(title="TikTok Auto-Posting Machine - Monitoring", version="1.0.0")


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    checks: dict


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Kubernetes-style liveness/readiness probe."""
    result = run_health_checks()
    return HealthResponse(**result)


@app.get("/health/live")
async def liveness():
    """Simple liveness check - returns 200 if process is alive."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Readiness check - returns 200 if system is ready to serve traffic."""
    status = get_health_status()
    if status == "healthy":
        return {"status": "ready"}
    else:
        return Response(content=json.dumps({"status": "not_ready", "health": status}), 
                       status_code=503, media_type="application/json")


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    all_metrics = metrics.get_all_metrics()
    
    lines = []
    
    # Counters
    for name, data in all_metrics.get('counters', {}).items():
        labels_str = ""
        if data['labels']:
            labels_parts = [f'{k}="{v}"' for k, v in data['labels'].items()]
            labels_str = "{" + ",".join(labels_parts) + "}"
        lines.append(f'# TYPE {name} counter')
        lines.append(f'{name}{labels_str} {data["value"]}')
    
    # Gauges
    for name, data in all_metrics.get('gauges', {}).items():
        labels_str = ""
        if data['labels']:
            labels_parts = [f'{k}="{v}"' for k, v in data['labels'].items()]
            labels_str = "{" + ",".join(labels_parts) + "}"
        lines.append(f'# TYPE {name} gauge')
        lines.append(f'{name}{labels_str} {data["value"]}')
    
    # Histograms (simplified)
    for name, data in all_metrics.get('histograms', {}).items():
        labels_str = ""
        if data['labels']:
            labels_parts = [f'{k}="{v}"' for k, v in data['labels'].items()]
            labels_str = "{" + ",".join(labels_parts) + "}"
        lines.append(f'# TYPE {name} histogram')
        lines.append(f'{name}_count{labels_str} {data["count"]}')
        lines.append(f'{name}_sum{labels_str} {data["sum"]}')
        if data['count'] > 0:
            lines.append(f'{name}_avg{labels_str} {data["sum"] / data["count"]}')
    
    return Response(content="\n".join(lines), media_type="text/plain; version=0.0.4")


@app.get("/metrics/json")
async def json_metrics():
    """JSON format metrics for non-Prometheus consumers."""
    return metrics.get_all_metrics()


def create_monitoring_app(config_path: Optional[str] = None) -> FastAPI:
    """Create monitoring app with config."""
    if config_path:
        from services.infrastructure.config import Config
        Config.reset_instance()
        Config.get_instance(Path(config_path))
    return app


def run_monitoring_server(config_path: str, host: str = "0.0.0.0", port: int = 9090):
    """Run monitoring server."""
    import uvicorn
    
    if config_path:
        from services.infrastructure.config import Config
        Config.reset_instance()
        Config.get_instance(Path(config_path))
    
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monitoring server")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()
    
    from services.infrastructure.config import Config
    Config.reset_instance()
    Config.get_instance(Path(args.config))
    
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")