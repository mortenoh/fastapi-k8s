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
# {"message":"Hello from fastapi-k8s!"}
```

## Docker

```bash
# Build the image
make docker-build

# Run the container
make docker-run

# Test it
curl http://localhost:8000
# {"message":"Hello from fastapi-k8s!"}
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
| `make clean` | undeploy + `docker rmi` | Remove K8s resources and Docker image |

## Learning Kubernetes

New to Kubernetes? See **[KUBERNETES.md](KUBERNETES.md)** for a comprehensive guide using this project as the running example — covers core concepts, scaling, self-healing, rolling updates, and more.

## Cleanup

```bash
# Remove from Kubernetes
make undeploy

# Remove everything (K8s resources + Docker image)
make clean
```

## Useful kubectl Commands

```bash
# List all pods
kubectl get pods

# Describe a pod (shows events, useful for debugging)
kubectl describe pod -l app=fastapi-k8s

# Follow logs in real-time
kubectl logs -l app=fastapi-k8s -f

# Get a shell inside the running container
kubectl exec -it $(kubectl get pod -l app=fastapi-k8s -o jsonpath='{.items[0].metadata.name}') -- /bin/bash

# Check all services
kubectl get svc

# View the full deployment config
kubectl get deployment fastapi-k8s -o yaml
```
