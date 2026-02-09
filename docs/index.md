# fastapi-k8s

A simple FastAPI app deployed to Kubernetes using Docker Desktop.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Kubernetes enabled

### Enabling Kubernetes in Docker Desktop

1. Open Docker Desktop
2. Go to **Settings** > **Kubernetes**
3. Check **Enable Kubernetes**
4. Click **Apply & Restart**

This gives you a single-node Kubernetes cluster, `kubectl` CLI, local Docker images available to K8s (no registry needed), and a built-in LoadBalancer that maps to localhost.

## Quick Start (Local Development)

```bash
# Install dependencies
uv sync

# Run with hot-reload
make dev

# Test it
curl http://127.0.0.1:8000
# {"message":"Hello from fastapi-k8s!","server":"your-hostname"}
```

## Docker

```bash
# Build the image
make docker-build

# Run the container
make docker-run

# Test it
curl http://localhost:8000
# {"message":"Hello from fastapi-k8s!","server":"your-hostname"}
```

## Kubernetes Deployment

```bash
# 1. Build the Docker image (K8s uses the local image)
make docker-build

# 2. Deploy to Kubernetes
make deploy

# 3. Check status (wait for STATUS: Running)
make status

# 4. Test it (the LoadBalancer maps port 80 to localhost)
curl http://localhost
# {"message":"Hello from fastapi-k8s!","server":"fastapi-k8s-7f8b9c6d4-xj2kl"}
```

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

## Makefile Reference

| Target | Command | Description |
|--------|---------|-------------|
| `make dev` | `uv run fastapi dev main.py` | Local dev server with hot-reload |
| `make run` | `uv run main.py` | Run with uvicorn directly |
| `make docker-build` | `docker build -t fastapi-k8s:latest .` | Build Docker image |
| `make docker-run` | `docker run --rm -p 8000:8000 fastapi-k8s:latest` | Run Docker container |
| `make deploy` | `kubectl apply -f k8s.yaml` | Deploy to Kubernetes |
| `make status` | `kubectl get pods,svc -l app=fastapi-k8s` | Check pod and service status |
| `make logs` | `kubectl logs -l app=fastapi-k8s` | View pod logs |
| `make scale N=3` | `kubectl scale deployment ... --replicas=3` | Scale deployment to N replicas |
| `make undeploy` | `kubectl delete -f k8s.yaml` | Remove from Kubernetes |
| `make test` | build + deploy + curl all endpoints | Build, deploy, and test all endpoints |
| `make clean` | undeploy + `docker rmi` | Remove K8s resources and Docker image |
| `make metrics-server` | install + patch metrics-server | Install metrics-server for HPA and kubectl top |
| `make hpa` | `kubectl apply -f k8s/hpa.yaml` | Apply HPA for autoscaling |
| `make hpa-status` | `kubectl get hpa -l app=fastapi-k8s` | Check HPA status |
| `make hpa-delete` | `kubectl delete -f k8s/hpa.yaml` | Delete HPA |
| `make restart` | `kubectl rollout restart deployment/fastapi-k8s` | Trigger rolling restart of deployment |
| `make rollout-status` | `kubectl rollout status deployment/fastapi-k8s` | Watch rollout progress |
| `make docs` | `uv run mkdocs serve` | Serve documentation locally |
| `make docs-build` | `uv run mkdocs build` | Build documentation site |

## Cleanup

```bash
# Remove from Kubernetes
make undeploy

# Remove everything (K8s resources + Docker image)
make clean
```
