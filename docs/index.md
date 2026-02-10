# fastapi-k8s

A simple FastAPI app deployed to Kubernetes using Docker Desktop.

**[Slide Deck](slides/)** -- Kubernetes learnings as a presentation

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

## Project Structure

```
src/fastapi_k8s/       Application package (FastAPI app, routes)
tests/                 Pytest unit tests
k8s/                   Extra K8s manifests (HPA, Redis, Secret)
k8s.yaml               Main deployment manifest (ConfigMap + Deployment + Service)
docs/                  MkDocs documentation source
Makefile               Build, deploy, test, and scale commands
Dockerfile             Multi-stage container build
pyproject.toml         Python project config and dependencies (uv)
mkdocs.yml             MkDocs site configuration
```

The application uses a `src` layout -- the FastAPI app lives in `src/fastapi_k8s/` and is installed as a package. This is the recommended Python project structure because it prevents accidental imports from the working directory. Tests live in `tests/` at the project root and run with `make test`.

Kubernetes manifests are split across two locations: `k8s.yaml` in the project root contains the core deployment (ConfigMap, Deployment, Service), while `k8s/` holds additional resources (HPA, Redis, Secret) that are deployed separately.

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

## Live Demo Walkthrough

A step-by-step script you can run against the cluster. Each step has the command and what to watch for.

### Part 1 -- Deploy, Load Balancing, Scaling, Self-Healing

**Step 1 -- Build and deploy**

```bash
make docker-build && make deploy
```

Observe: Kubernetes creates pods, service, and configmap.

**Step 2 -- Wait for pods**

```bash
make status
```

Observe: All pods show `STATUS: Running` and `READY: 1/1`.

**Step 3 -- Load balancing**

```bash
for i in $(seq 1 10); do curl -s http://localhost | jq -r .server; done
```

Observe: Different hostnames appear -- the Service round-robins across pods.

**Step 4 -- Scale up and self-healing**

```bash
make scale N=5
make status
curl -X POST http://localhost/crash
kubectl get pods -w
```

Observe: After the crash, Kubernetes restarts the pod automatically. The restart count increments by 1.

### Part 2 -- Readiness Probes

**Step 5 -- Remove a pod from traffic**

```bash
curl -X POST http://localhost/ready/disable
for i in $(seq 1 6); do curl -s http://localhost | jq -r .server; done
```

Observe: The disabled pod's hostname no longer appears in responses.

**Step 6 -- Re-enable the pod**

```bash
curl -X POST http://localhost/ready/enable
for i in $(seq 1 6); do curl -s http://localhost | jq -r .server; done
```

Observe: The pod's hostname starts appearing again.

### Part 3 -- Redis Shared State

**Step 7 -- Deploy Redis**

```bash
make redis-deploy
make redis-status
```

Observe: Redis pod is `Running`, PVC is `Bound`, ClusterIP service exists.

**Step 8 -- Shared visit counter**

```bash
for i in $(seq 1 5); do curl -s http://localhost/visits | jq; done
```

Observe: The visit count increments consistently regardless of which pod handles the request.

**Step 9 -- Key-value store**

```bash
curl -X POST http://localhost/kv/demo -d '{"value":"hello"}' | jq
curl -s http://localhost/kv/demo | jq
```

Observe: Any pod can read the value written by any other pod.

### Part 4 -- Autoscaling / HPA

**Step 10 -- Install metrics-server (if not already installed)**

```bash
make metrics-server
```

Observe: metrics-server pod starts in `kube-system` namespace.

**Step 11 -- Apply HPA**

```bash
make hpa
make hpa-status
```

Observe: HPA shows current CPU utilization and target of 50%.

**Step 12 -- Trigger autoscaling**

```bash
curl "http://localhost/stress?seconds=20"
watch make hpa-status
```

Observe: CPU spikes, replicas increase beyond the initial count. After load stops, replicas scale back down after the cooldown period.

**Step 13 -- Cleanup**

```bash
make hpa-delete
make scale N=3
make redis-undeploy
```

Observe: HPA removed, replicas set back to 3, Redis stack removed.

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
| `/kv/{key}` | GET | Retrieve a value by key from Redis (404 if missing) |
| `/kv/{key}` | POST | Store a value under a key in Redis |
| `/login` | POST | Login with username/password, sets session cookie (Redis) |
| `/logout` | POST | Clear session cookie and Redis session |
| `/me` | GET | Current user info and server hostname (requires session) |

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
| `make test` | `pytest` | Run unit tests with pytest |
| `make test-e2e` | build + deploy + curl all endpoints | Build, deploy, and test all endpoints |
| `make clean` | undeploy + `docker rmi` | Remove K8s resources and Docker image |
| `make metrics-server` | install + patch metrics-server | Install metrics-server for HPA and kubectl top |
| `make hpa` | `kubectl apply -f k8s/hpa.yaml` | Apply HPA for autoscaling |
| `make hpa-status` | `kubectl get hpa -l app=fastapi-k8s` | Check HPA status |
| `make hpa-delete` | `kubectl delete -f k8s/hpa.yaml` | Delete HPA |
| `make restart` | `kubectl rollout restart deployment/fastapi-k8s` | Trigger rolling restart of deployment |
| `make rollout-status` | `kubectl rollout status deployment/fastapi-k8s` | Watch rollout progress |
| `make redis-deploy` | `kubectl apply -f k8s/redis-secret.yaml,k8s/redis.yaml` | Deploy Redis (Secret + PVC + Deployment + Service) |
| `make redis-status` | `kubectl get pods,svc,pvc -l app=redis` | Check Redis pod, service, and PVC status |
| `make redis-logs` | `kubectl logs -l app=redis` | View Redis pod logs |
| `make redis-undeploy` | `kubectl delete -f k8s/redis.yaml` | Remove Redis Deployment and Service (keeps PVC/Secret) |
| `make redis-clean` | delete redis + PVC + Secret | Full Redis cleanup |
| `make test-redis` | curl Redis endpoints | Test Redis endpoints |
| `make docs` | `uv run mkdocs serve` | Serve documentation locally |
| `make docs-build` | `uv run mkdocs build` | Build documentation site |

## Cleanup

```bash
# Remove from Kubernetes
make undeploy

# Remove everything (K8s resources + Docker image)
make clean
```
