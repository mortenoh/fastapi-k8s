"""FastAPI app deployed to Kubernetes on Docker Desktop."""

from fastapi_k8s.main import app

__all__ = ["app"]
