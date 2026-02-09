# CLAUDE.md

## Project

FastAPI app deployed to Kubernetes on Docker Desktop.

## Conventions

- Use conventional commits (e.g., `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`)
- Never use emojis anywhere (commits, code, docs, PRs)
- Never add Co-Authored-By or any Claude attribution to commits, PRs, or any output
- Keep commit messages concise: type + short description on the first line

## Stack

- Python 3.13, FastAPI, uvicorn
- uv for dependency management
- Docker for containerization
- Kubernetes (Docker Desktop single-node cluster)

## Key Files

- `main.py` — FastAPI application
- `k8s.yaml` — ConfigMap + Kubernetes Deployment + Service
- `k8s/hpa.yaml` — HorizontalPodAutoscaler manifest
- `Makefile` — Build, run, deploy, and scale commands
- `Dockerfile` — Multi-stage Docker build
- `docs/` — MkDocs documentation source (Kubernetes guide, walkthroughs)
- `mkdocs.yml` — MkDocs configuration

## API Endpoints

- `GET /` -- Hello message with pod hostname (uses APP_NAME from ConfigMap)
- `GET /health` -- Liveness probe (always 200)
- `GET /ready` -- Readiness probe (200 or 503)
- `POST /ready/enable` -- Mark pod as ready
- `POST /ready/disable` -- Mark pod as not ready
- `POST /crash` -- Kill the pod (K8s restarts it)
- `GET /stress?seconds=N` -- Burn CPU for N seconds (capped by MAX_STRESS_SECONDS ConfigMap value, default 30)
- `GET /info` -- Pod metadata via Downward API env vars
- `GET /config` -- Current ConfigMap values (APP_NAME, LOG_LEVEL, MAX_STRESS_SECONDS)
- `GET /version` -- App version and server hostname

## Common Commands

- `make dev` — Local dev server with hot-reload
- `make docker-build` — Build Docker image
- `make deploy` — Deploy to Kubernetes
- `make status` — Check pod/service status
- `make scale N=5` — Scale to N replicas
- `make logs` — View pod logs
- `make test` — Build, deploy, and test all endpoints
- `make undeploy` — Remove from Kubernetes
- `make metrics-server` — Install metrics-server for HPA and kubectl top
- `make hpa` — Apply HPA for autoscaling
- `make hpa-status` — Check HPA status
- `make hpa-delete` — Delete HPA
- `make restart` — Trigger rolling restart of deployment
- `make rollout-status` — Watch rollout progress
- `make docs` — Serve documentation locally
- `make docs-build` — Build documentation site
