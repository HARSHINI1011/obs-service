"""
Production Observability demo service.

Endpoints:
  GET /work?n=K       -> does K units of "work", returns {"email":..., "done": K}
  GET /metrics        -> Prometheus text format, includes http_requests_total
  GET /healthz        -> {"status": "ok", "uptime_s": <float>}
  GET /logs/tail?limit=N -> last N structured JSON log entries
"""

import json
import time
import uuid
import logging
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# CHANGE THIS to your own email before you deploy!
# ---------------------------------------------------------------------------
YOUR_EMAIL = "24f2006358@ds.study.iitm.ac.in."

app = FastAPI()

# Record the moment the app started, so we can compute uptime later.
START_TIME = time.time()

# A simple in-memory "diary" of the last 1000 requests.
# deque = a list that automatically drops old items once it's full.
LOG_BUFFER = deque(maxlen=1000)

# A single Prometheus counter. Every single request to any endpoint
# will tick this counter up by 1. That's all "http_requests_total" needs to do.
REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Total number of HTTP requests received",
)

# Basic logging setup (prints JSON lines to the console, useful for real
# deployments where a hosting provider captures stdout as logs).
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("obs-service")


def record_log(level: str, path: str, request_id: str, **extra):
    """Build one structured log entry, store it, and print it."""
    entry = {
        "level": level,
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "request_id": request_id,
    }
    entry.update(extra)
    LOG_BUFFER.append(entry)
    logger.info(json.dumps(entry))
    return entry


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """
    This function runs on EVERY request, no matter which endpoint is hit.
    That's exactly what we need for the counter and the logs.
    """
    request_id = str(uuid.uuid4())
    path = request.url.path

    # 1. Bump the counter for this request.
    REQUEST_COUNTER.inc()

    # 2. Let the actual endpoint (e.g. /work) run and get its response.
    response = await call_next(request)

    # 3. Write a log entry describing what just happened.
    record_log(
        "INFO",
        path,
        request_id,
        method=request.method,
        status_code=response.status_code,
    )

    # Handy for debugging: return the request id in the response headers.
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/work")
async def work(n: int = 1):
    """Do K 'units of work' (just some harmless CPU busywork) and return a result."""
    total = 0
    for i in range(max(n, 0)):
        total += i * i  # meaningless math, just to simulate "work"
    return {"email": YOUR_EMAIL, "done": n}


@app.get("/metrics")
async def metrics():
    """Expose counters in the text format Prometheus expects."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz():
    """Tell the world the app is alive and how long it's been running."""
    uptime = time.time() - START_TIME
    return {"status": "ok", "uptime_s": uptime}


@app.get("/logs/tail")
async def logs_tail(limit: int = 20):
    """Return the most recent `limit` log entries as a JSON array."""
    limit = max(limit, 0)
    return list(LOG_BUFFER)[-limit:]
