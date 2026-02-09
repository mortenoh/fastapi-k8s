# Dockerfile Walkthrough

Every Kubernetes deployment starts with a container image. This page walks through the project's Dockerfile line by line, explaining the build strategy, layer caching, and how the image connects to the rest of the deployment pipeline.

---

## The complete Dockerfile

```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application code
COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "fastapi_k8s:app", "--host", "0.0.0.0", "--port", "8000"]
```

This is a single-stage build with a deliberate layer ordering that maximises Docker's build cache.

---

## Line-by-line breakdown

### Base image

```dockerfile
FROM python:3.13-slim
```

The `python:3.13-slim` image is a Debian-based image with Python 3.13 pre-installed. The `-slim` variant strips out build tools (gcc, make, etc.) and documentation, reducing the image size significantly compared to the full `python:3.13` image. Since this project has no compiled dependencies (no C extensions), the slim variant has everything needed.

### Install uv

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
```

This uses a multi-stage `COPY --from` to pull the `uv` and `uvx` binaries directly from the official uv container image. This avoids installing uv via pip or curl during the build, keeping the layer small and the build fast. The binaries are placed in `/bin/` so they are available on `PATH`.

[uv](https://docs.astral.sh/uv/) is a fast Python package manager written in Rust. It replaces pip, pip-tools, and virtualenv with a single tool that resolves and installs dependencies in seconds rather than minutes.

### Working directory

```dockerfile
WORKDIR /app
```

All subsequent commands run in `/app`. The directory is created automatically if it does not exist.

### Install dependencies (cached layer)

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
```

This is the most important optimisation in the Dockerfile. By copying only the dependency files first and installing dependencies before copying the application code, Docker can cache this layer. As long as `pyproject.toml` and `uv.lock` do not change, this `RUN` step is skipped entirely on subsequent builds.

- **`--frozen`** -- Uses the exact versions from `uv.lock` without updating the lock file. This ensures reproducible builds.
- **`--no-install-project`** -- Installs only the dependencies, not the project itself. The project code has not been copied yet at this point.

### Copy application code and install project

```dockerfile
COPY . .
RUN uv sync --frozen
```

Now the full application code is copied into the image. The second `uv sync --frozen` installs the project itself (the `fastapi_k8s` package) into the virtual environment. This is fast because all dependencies are already installed from the cached layer above -- only the project package is added.

### Start command

```dockerfile
CMD ["uv", "run", "uvicorn", "fastapi_k8s:app", "--host", "0.0.0.0", "--port", "8000"]
```

The container starts uvicorn through `uv run`, which activates the virtual environment and runs the command. The arguments:

- **`fastapi_k8s:app`** -- Import the `app` object from the `fastapi_k8s` package.
- **`--host 0.0.0.0`** -- Listen on all interfaces. Required inside a container so that traffic from outside the container (via Kubernetes port mappings) can reach the server.
- **`--port 8000`** -- The port uvicorn listens on. This matches the `containerPort` in `k8s.yaml` and the `targetPort` in the Service.

---

## Layer caching strategy

Docker builds images layer by layer, from top to bottom. Each instruction creates a layer. If a layer's inputs have not changed since the last build, Docker reuses the cached layer and skips the step.

The order of instructions matters:

```
Layer 1: FROM python:3.13-slim          (changes rarely)
Layer 2: COPY uv binaries               (changes rarely)
Layer 3: COPY pyproject.toml uv.lock    (changes when dependencies change)
Layer 4: RUN uv sync --no-install       (cached unless layer 3 changed)
Layer 5: COPY . .                       (changes on every code edit)
Layer 6: RUN uv sync                    (runs after layer 5 changes)
```

When you edit application code and rebuild, only layers 5 and 6 need to run. The dependency installation (layer 4) is cached because the lock file did not change. This turns a 30+ second build into a 2-3 second build.

If you reversed the order -- copying all files first, then installing dependencies -- every code change would invalidate the dependency layer and trigger a full reinstall.

---

## Building the image

```bash
make docker-build
```

This runs:

```bash
docker build -t fastapi-k8s:latest .
```

The image is tagged `fastapi-k8s:latest` and stored in Docker Desktop's local image registry. Because Kubernetes on Docker Desktop shares the same Docker daemon, the image is immediately available to Kubernetes without pushing to a remote registry.

This is specific to Docker Desktop. In a production environment, you would push the image to a container registry (Docker Hub, GitHub Container Registry, AWS ECR, etc.) and reference it in your Kubernetes manifests.

---

## Running the image directly

```bash
make docker-run
```

This runs:

```bash
docker run --rm -p 8000:8000 fastapi-k8s:latest
```

- **`--rm`** -- Remove the container when it stops (no leftover stopped containers).
- **`-p 8000:8000`** -- Map port 8000 on the host to port 8000 in the container.

This is useful for testing the image locally before deploying to Kubernetes. The app is available at `http://localhost:8000`.

---

## Connection to Kubernetes

The Kubernetes Deployment in `k8s.yaml` references this image:

```yaml
spec:
  containers:
    - name: fastapi-k8s
      image: fastapi-k8s:latest
      imagePullPolicy: Never
```

- **`image: fastapi-k8s:latest`** -- The same tag used in `make docker-build`.
- **`imagePullPolicy: Never`** -- Tells Kubernetes not to pull from a remote registry. It uses the local Docker image directly. Without this, Kubernetes would try to pull `fastapi-k8s:latest` from Docker Hub and fail.

When you change your application code, the workflow is:

1. `make docker-build` -- Build a new image with your changes
2. `make restart` -- Trigger a rolling restart so pods pick up the new image

See [Your First Deployment](first-deployment.md) for the full deployment walkthrough.
