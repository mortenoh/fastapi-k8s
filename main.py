import os
import socket
import sys
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

APP_VERSION = "1.0.0"

# --- Configuration from ConfigMap (env vars with defaults) ---
APP_NAME = os.getenv("APP_NAME", "fastapi-k8s")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
MAX_STRESS_SECONDS = int(os.getenv("MAX_STRESS_SECONDS", "30"))

_LOG_LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3}


def _log(level: str, message: str):
    if _LOG_LEVELS.get(level, 1) >= _LOG_LEVELS.get(LOG_LEVEL, 1):
        print(f"[{level.upper()}] {message}", file=sys.stderr, flush=True)


# --- Readiness toggle (app-level state) ---
_ready = True


@app.get("/")
async def root():
    return {"message": f"Hello from {APP_NAME}!", "server": socket.gethostname()}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    if _ready:
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "not ready"})


@app.post("/ready/enable")
async def ready_enable():
    global _ready
    _ready = True
    return {"status": "ready"}


@app.post("/ready/disable")
async def ready_disable():
    global _ready
    _ready = False
    return {"status": "not ready"}


@app.post("/crash")
async def crash():
    """Kill this pod. K8s will restart it."""
    os._exit(1)


@app.get("/stress")
def stress(seconds: int = 10):
    """Burn CPU for N seconds. Sync def so it runs in threadpool."""
    seconds = min(seconds, MAX_STRESS_SECONDS)
    _log("info", f"stress starting for {seconds}s (max {MAX_STRESS_SECONDS}s)")
    end = time.time() + seconds
    while time.time() < end:
        _ = sum(i * i for i in range(10_000))
    _log("info", f"stress completed after {seconds}s")
    return {"stressed_seconds": seconds, "server": socket.gethostname()}


@app.get("/config")
async def config():
    """Return current configuration values (from ConfigMap env vars)."""
    return {
        "app_name": APP_NAME,
        "log_level": LOG_LEVEL,
        "max_stress_seconds": MAX_STRESS_SECONDS,
    }


@app.get("/version")
async def version():
    """Return app version and server hostname."""
    return {"version": APP_VERSION, "server": socket.gethostname()}


@app.get("/info")
async def info():
    """Return pod metadata injected via Downward API env vars."""
    return {
        "pod_name": os.getenv("POD_NAME", socket.gethostname()),
        "pod_ip": os.getenv("POD_IP", "unknown"),
        "node_name": os.getenv("NODE_NAME", "unknown"),
        "namespace": os.getenv("POD_NAMESPACE", "unknown"),
        "cpu_request": os.getenv("CPU_REQUEST", "not set"),
        "cpu_limit": os.getenv("CPU_LIMIT", "not set"),
        "memory_request": os.getenv("MEMORY_REQUEST", "not set"),
        "memory_limit": os.getenv("MEMORY_LIMIT", "not set"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
