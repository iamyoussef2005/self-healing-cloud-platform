import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

# Custom Prometheus gauge for simulated memory usage (in MB)
SIMULATED_MEMORY_GAUGE = Gauge(
    "app_simulated_memory_mb",
    "Simulated memory usage in megabytes for chaos testing",
)

# In-memory state for chaos simulation
_chaos_state: dict[str, Any] = {
    "simulated_memory_mb": 0,
    "memory_blocks": [],
}

SAMPLE_ITEMS = [
    {
        "id": 1,
        "name": "api-gateway",
        "status": "healthy",
        "region": "us-east-1",
        "latency_ms": 14,
    },
    {
        "id": 2,
        "name": "auth-service",
        "status": "healthy",
        "region": "us-east-1",
        "latency_ms": 22,
    },
    {
        "id": 3,
        "name": "payment-worker",
        "status": "healthy",
        "region": "us-west-2",
        "latency_ms": 38,
    },
    {
        "id": 4,
        "name": "telemetry-collector",
        "status": "healthy",
        "region": "eu-central-1",
        "latency_ms": 19,
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    SIMULATED_MEMORY_GAUGE.set(0)
    yield
    _chaos_state["memory_blocks"].clear()
    _chaos_state["simulated_memory_mb"] = 0
    SIMULATED_MEMORY_GAUGE.set(0)


app = FastAPI(
    title="Self-Healing Cloud Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health", tags=["probes"])
def health() -> dict[str, str]:
    """Kubernetes liveness probe endpoint."""
    return {"status": "healthy"}


@app.get("/ready", tags=["probes"])
def ready() -> dict[str, Any]:
    """Kubernetes readiness probe endpoint."""
    return {
        "status": "ready",
        "simulated_memory_mb": _chaos_state["simulated_memory_mb"],
    }


@app.get("/api/items", tags=["items"])
def get_items() -> dict[str, Any]:
    """Return sample platform service items."""
    return {
        "items": SAMPLE_ITEMS,
        "count": len(SAMPLE_ITEMS),
        "simulated_memory_mb": _chaos_state["simulated_memory_mb"],
    }


@app.post("/chaos/memory", tags=["chaos"])
def trigger_memory_chaos(
    mb: int = Query(default=128, ge=1, le=2048, description="Megabytes to simulate"),
    allocate: bool = Query(
        default=True,
        description="Whether to allocate real memory bytes in addition to updating the metric",
    ),
) -> dict[str, Any]:
    """Simulate high memory usage and update the app_simulated_memory_mb gauge."""
    if allocate:
        _chaos_state["memory_blocks"].append(bytearray(mb * 1024 * 1024))

    _chaos_state["simulated_memory_mb"] += mb
    SIMULATED_MEMORY_GAUGE.set(_chaos_state["simulated_memory_mb"])

    return {
        "status": "chaos_memory_triggered",
        "added_mb": mb,
        "total_simulated_memory_mb": _chaos_state["simulated_memory_mb"],
    }


@app.post("/chaos/reset", tags=["chaos"])
def reset_chaos() -> dict[str, Any]:
    """Release simulated memory blocks and reset the gauge to zero."""
    _chaos_state["memory_blocks"].clear()
    _chaos_state["simulated_memory_mb"] = 0
    SIMULATED_MEMORY_GAUGE.set(0)
    return {"status": "reset", "total_simulated_memory_mb": 0}


@app.api_route("/chaos/error", methods=["GET", "POST"], tags=["chaos"])
def trigger_error_chaos() -> None:
    """Simulate an HTTP 500 Internal Server Error on demand."""
    raise HTTPException(
        status_code=500,
        detail="Simulated HTTP 500 error triggered via /chaos/error",
    )
