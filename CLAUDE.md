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
- `k8s.yaml` — Kubernetes Deployment + Service
- `Makefile` — Build, run, deploy, and scale commands
- `Dockerfile` — Multi-stage Docker build
- `KUBERNETES.md` — Comprehensive K8s guide for beginners

## Common Commands

- `make dev` — Local dev server with hot-reload
- `make docker-build` — Build Docker image
- `make deploy` — Deploy to Kubernetes
- `make status` — Check pod/service status
- `make scale N=5` — Scale to N replicas
- `make logs` — View pod logs
- `make undeploy` — Remove from Kubernetes
