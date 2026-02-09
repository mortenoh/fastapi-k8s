# fastapi-k8s

A simple FastAPI app deployed to Kubernetes using Docker Desktop.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Kubernetes enabled

## Quick Start

```bash
# Install dependencies
uv sync

# Local dev server with hot-reload
make dev

# Build, deploy to K8s, and test all endpoints
make test
```

## Documentation

Full documentation (API reference, Kubernetes guide, walkthroughs) is available via MkDocs:

```bash
make docs
```

This serves the docs locally at `http://127.0.0.1:8000`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Hello message with pod hostname |
| `/health` | GET | Liveness probe (always 200) |
| `/ready` | GET | Readiness probe (200 or 503) |
| `/ready/enable` | POST | Mark pod as ready |
| `/ready/disable` | POST | Mark pod as not ready |
| `/crash` | POST | Kill the pod (demonstrates self-healing) |
| `/stress?seconds=10` | GET | Burn CPU (demonstrates HPA, capped by ConfigMap) |
| `/info` | GET | Pod metadata via Downward API |
| `/config` | GET | Current ConfigMap values |
| `/version` | GET | App version and server hostname |
| `/visits` | GET | Increment and return shared visit counter (Redis) |
| `/kv/{key}` | GET | Retrieve a value by key from Redis |
| `/kv/{key}` | POST | Store a value under a key in Redis |

## Key Make Targets

| Target | Description |
|--------|-------------|
| `make dev` | Local dev server with hot-reload |
| `make docker-build` | Build Docker image |
| `make deploy` | Deploy to Kubernetes |
| `make test` | Build, deploy, and test all endpoints |
| `make status` | Check pod and service status |
| `make scale N=3` | Scale deployment to N replicas |
| `make restart` | Trigger rolling restart |
| `make hpa` | Apply HPA for autoscaling |
| `make metrics-server` | Install metrics-server for HPA and kubectl top |
| `make docs` | Serve documentation locally |
| `make redis-deploy` | Deploy Redis to Kubernetes |
| `make redis-status` | Check Redis pod, service, and PVC status |
| `make test-redis` | Test Redis endpoints |
| `make redis-clean` | Full Redis cleanup |
| `make undeploy` | Remove from Kubernetes |

Run `make` with no arguments to see all available targets.
