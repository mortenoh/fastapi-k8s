# Kubernetes Guide

A hands-on introduction to Kubernetes using this project (`fastapi-k8s`) as the running example. Aimed at developers who are new to Kubernetes.

---

## Table of Contents

1. [What is Kubernetes?](#1-what-is-kubernetes)
2. [Core Concepts](#2-core-concepts)
3. [Your First Deployment (this project)](#3-your-first-deployment-this-project)
4. [Deploying & Verifying](#4-deploying--verifying)
5. [Scaling](#5-scaling)
6. [Self-Healing](#6-self-healing)
7. [Rolling Updates](#7-rolling-updates)
8. [Resource Management](#8-resource-management)
9. [Monitoring & Observability](#9-monitoring--observability)
10. [Networking Deep Dive](#10-networking-deep-dive)
11. [Configuration & Secrets](#11-configuration--secrets)
12. [Persistent Storage](#12-persistent-storage)
13. [Horizontal Pod Autoscaler (HPA)](#13-horizontal-pod-autoscaler-hpa)
14. [Common Troubleshooting](#14-common-troubleshooting)
15. [Where to Go Next](#15-where-to-go-next)

---

## 1. What is Kubernetes?

Kubernetes (often abbreviated **K8s**) is a container orchestration platform. It takes your containerized applications and manages where and how they run across a cluster of machines.

### Why does it exist?

Running a single container on your laptop is easy. Running dozens of containers across multiple servers — keeping them healthy, scaling them up under load, and deploying new versions without downtime — is hard. Kubernetes solves this by providing:

- **Declarative configuration** — You describe the *desired state* ("I want 5 copies of my app running") and Kubernetes makes it happen. You don't write scripts to start containers; you write YAML that describes what you want.
- **Self-healing** — If a container crashes or a node goes down, Kubernetes automatically restarts or reschedules your workloads.
- **Scaling** — Scale from 1 to 100 replicas with a single command (or automatically based on CPU/memory).
- **Rolling updates** — Deploy new versions with zero downtime. Kubernetes gradually replaces old pods with new ones.
- **Service discovery & load balancing** — Kubernetes gives your app a stable network address and distributes traffic across all healthy replicas.

### The big picture

```
                        ┌─────────────────────────────────┐
  You write YAML ──────►│         Kubernetes Cluster       │
  (desired state)        │                                 │
                        │  ┌─────┐  ┌─────┐  ┌─────┐     │
                        │  │ Pod │  │ Pod │  │ Pod │      │
                        │  │ :8000│  │ :8000│  │ :8000│     │
                        │  └──┬──┘  └──┬──┘  └──┬──┘     │
                        │     └────────┼────────┘         │
                        │           Service               │
                        │          (port 80)              │
                        └──────────┬──────────────────────┘
                                   │
  curl http://localhost ───────────┘
```

---

## 2. Core Concepts

### Cluster

A Kubernetes **cluster** is a set of machines (physical or virtual) that run your containerized applications. It consists of:

- **Control plane** — The brain. Makes decisions about the cluster (scheduling, detecting failures, responding to events). Includes the API server, scheduler, and etcd (a key-value store for all cluster data).
- **Worker nodes** — The muscles. Run your actual application containers.

With Docker Desktop, you get a single-node cluster where the control plane and worker run on the same machine.

### Node

A **node** is a single machine in the cluster. Each node runs:

- **kubelet** — An agent that ensures containers are running in pods
- **kube-proxy** — Handles networking rules so pods can communicate
- **Container runtime** — Docker (or containerd) that actually runs containers

```
┌──────────────── Node ──────────────────┐
│  kubelet    kube-proxy    containerd   │
│                                         │
│  ┌─────────┐  ┌─────────┐             │
│  │  Pod A  │  │  Pod B  │    ...       │
│  └─────────┘  └─────────┘             │
└─────────────────────────────────────────┘
```

### Pod

A **pod** is the smallest deployable unit in Kubernetes. It wraps one or more containers that share:

- The same network namespace (they can reach each other via `localhost`)
- The same storage volumes
- The same lifecycle (created and destroyed together)

In practice, most pods run a single container. Think of a pod as "one instance of your app."

```
┌───────── Pod ─────────┐
│                       │
│  ┌─────────────────┐  │
│  │   Container     │  │
│  │  fastapi-k8s    │  │
│  │  (port 8000)    │  │
│  └─────────────────┘  │
│                       │
│  IP: 10.1.0.15       │
└───────────────────────┘
```

You almost never create pods directly. Instead, you use a **Deployment**.

### Deployment

A **deployment** manages a set of identical pods (a **ReplicaSet**). It provides:

- **Desired replica count** — "I want 5 pods running"
- **Rolling updates** — Gradually replace old pods with new ones
- **Rollback** — Undo a bad deployment
- **Self-healing** — If a pod dies, the Deployment creates a new one

```
┌──────────── Deployment ────────────────┐
│  replicas: 5                           │
│                                         │
│  ┌─── ReplicaSet ───────────────────┐  │
│  │  Pod 1   Pod 2   Pod 3          │  │
│  │  Pod 4   Pod 5                   │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Service

Pods are ephemeral — they get new IP addresses every time they restart. A **service** provides a stable address and load-balances traffic across all matching pods.

```
                    ┌── Service ──┐
                    │  port: 80   │
                    │             │
curl ──────────────►│  ┌───────┐  │
                    │  │ Pod 1 │  │
                    │  │ Pod 2 │  │  (round-robin)
                    │  │ Pod 3 │  │
                    │  └───────┘  │
                    └─────────────┘
```

### Namespace

Namespaces are virtual clusters within a physical cluster. They provide isolation for teams or environments. The `default` namespace is used when you don't specify one (which is what we do in this project).

### Labels & Selectors

**Labels** are key-value pairs attached to objects (pods, services, deployments). **Selectors** are how objects find each other.

In our project, every object has the label `app: fastapi-k8s`. The Service uses the selector `app: fastapi-k8s` to find all matching pods:

```yaml
# Deployment adds this label to every pod it creates
template:
  metadata:
    labels:
      app: fastapi-k8s

# Service targets pods with this label
spec:
  selector:
    app: fastapi-k8s
```

This is how the Service knows which pods to send traffic to.

---

## 3. Your First Deployment (this project)

Our entire Kubernetes configuration lives in a single file: `k8s.yaml`. It contains two resources separated by `---`: a Deployment and a Service.

### The Deployment

```yaml
apiVersion: apps/v1          # API version for Deployment resources
kind: Deployment              # What type of resource this is
metadata:
  name: fastapi-k8s           # Name of the deployment
  labels:
    app: fastapi-k8s          # Label for the deployment itself
spec:
  replicas: 5                 # Number of pod copies to run
  selector:
    matchLabels:
      app: fastapi-k8s        # How the Deployment finds its pods
  template:                    # Pod template — blueprint for each pod
    metadata:
      labels:
        app: fastapi-k8s      # Label applied to each pod (must match selector)
    spec:
      containers:
        - name: fastapi-k8s           # Container name (for logs, exec)
          image: fastapi-k8s:latest    # Docker image to use
          imagePullPolicy: Never       # Use local image, don't pull from registry
          ports:
            - containerPort: 8000      # Port the app listens on inside the container
```

**Key points:**

- `replicas: 5` — Kubernetes will ensure exactly 5 pods are running at all times.
- `selector.matchLabels` must match `template.metadata.labels`. This is how the Deployment knows which pods belong to it.
- `imagePullPolicy: Never` — Critical for Docker Desktop. It tells Kubernetes to use the image from the local Docker daemon instead of trying to pull from Docker Hub or another registry.

### The Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
  labels:
    app: fastapi-k8s
spec:
  type: LoadBalancer           # Expose externally (on Docker Desktop: localhost)
  ports:
    - port: 80                 # Port the Service listens on
      targetPort: 8000         # Port to forward to on the pod
  selector:
    app: fastapi-k8s           # Send traffic to pods with this label
```

**Key points:**

- `type: LoadBalancer` — On cloud providers, this provisions a real load balancer with a public IP. On Docker Desktop, it maps directly to `localhost`.
- `port: 80` is the external port (what you `curl`). `targetPort: 8000` is the port your app listens on inside the container.
- `selector: app: fastapi-k8s` — The Service will distribute traffic across all pods that have this label.

---

## 4. Deploying & Verifying

### Step-by-step

```bash
# Build the Docker image (K8s will use the local image)
make docker-build

# Deploy to Kubernetes (applies k8s.yaml)
make deploy
# deployment.apps/fastapi-k8s created
# service/fastapi-k8s created

# Check status
make status
```

### Reading `kubectl get pods` output

```
NAME                          READY   STATUS    RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-5m9qr  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-8hjt2  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-kw4fn  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-xj2kl  1/1     Running   0          45s
```

| Column | Meaning |
|--------|---------|
| `NAME` | Pod name. Format: `<deployment>-<replicaset-hash>-<pod-hash>` |
| `READY` | `1/1` means 1 of 1 containers in the pod are ready |
| `STATUS` | `Running` = healthy. Other values: `Pending`, `CrashLoopBackOff`, `Error` |
| `RESTARTS` | How many times the container has restarted (0 is good) |
| `AGE` | Time since the pod was created |

### Reading `kubectl get svc` output

```
NAME          TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
fastapi-k8s   LoadBalancer   10.96.123.45   localhost     80:31234/TCP   2m
```

| Column | Meaning |
|--------|---------|
| `TYPE` | `LoadBalancer` — externally accessible |
| `CLUSTER-IP` | Internal cluster IP (used by other pods) |
| `EXTERNAL-IP` | `localhost` on Docker Desktop; a real IP on cloud |
| `PORT(S)` | `80:31234/TCP` — external port 80, NodePort 31234 |

### Debugging with kubectl

```bash
# Detailed info about a specific pod (events, conditions, volumes)
kubectl describe pod <pod-name>

# View logs from a specific pod
kubectl logs <pod-name>

# View logs from all pods with a label
kubectl logs -l app=fastapi-k8s

# Follow logs in real-time
kubectl logs -l app=fastapi-k8s -f

# Get a shell inside a running container
kubectl exec -it <pod-name> -- /bin/bash
```

---

## 5. Scaling

Scaling means changing the number of pod replicas running your application. More replicas = more capacity to handle requests.

### How the Service load-balances

When you have multiple replicas, the Service distributes incoming requests across all healthy pods. By default, `kube-proxy` uses **iptables rules** that provide roughly round-robin distribution.

```
                         Service (port 80)
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
         Pod 1             Pod 2             Pod 3
    "server":"..2nxkl"  "server":"..5m9qr"  "server":"..8hjt2"
```

### Scaling with kubectl

```bash
# Scale to 10 replicas
kubectl scale deployment fastapi-k8s --replicas=10

# Check the result
kubectl get pods -l app=fastapi-k8s
```

### Scaling with make

This project includes a convenience target:

```bash
# Scale to any number
make scale N=10

# Scale down
make scale N=2
```

### Scaling by editing the YAML

You can also change `replicas` in `k8s.yaml` and re-apply:

```yaml
spec:
  replicas: 10    # change this number
```

```bash
make deploy       # kubectl apply -f k8s.yaml
```

### Demonstrating round-robin

Our FastAPI app includes the pod hostname in the response. Curl multiple times to see different pods responding:

```bash
$ curl -s http://localhost | python -m json.tool
{
    "message": "Hello from fastapi-k8s!",
    "server": "fastapi-k8s-7f8b9c6d4-2nxkl"
}

$ curl -s http://localhost | python -m json.tool
{
    "message": "Hello from fastapi-k8s!",
    "server": "fastapi-k8s-7f8b9c6d4-xj2kl"
}

$ curl -s http://localhost | python -m json.tool
{
    "message": "Hello from fastapi-k8s!",
    "server": "fastapi-k8s-7f8b9c6d4-5m9qr"
}
```

A quick loop to see the distribution:

```bash
for i in $(seq 1 20); do
  curl -s http://localhost | python -m json.tool | grep server
done
```

### When to scale

- **CPU/memory pressure** — Pods are hitting resource limits
- **Request throughput** — Response times are increasing under load
- **Availability** — More replicas mean more resilience to individual pod failures
- **Scale down** when traffic drops to save resources

---

## 6. Self-Healing

Kubernetes continuously compares the **desired state** (what you declared in YAML) with the **actual state** (what's running). If they differ, Kubernetes acts to reconcile.

### Demonstration: kill a pod

```bash
# List pods
kubectl get pods -l app=fastapi-k8s

# Delete one
kubectl delete pod fastapi-k8s-7f8b9c6d4-2nxkl

# Immediately check again
kubectl get pods -l app=fastapi-k8s
```

You'll see 5 pods again almost immediately. The deleted pod is gone, but a new one has been created to maintain the desired replica count. The new pod will have a different name.

### How it works

```
Desired state:  replicas: 5
Actual state:   4 pods running (one was deleted)
                    │
                    ▼
Kubernetes:     "4 ≠ 5 — I need to create 1 more pod"
                    │
                    ▼
Actual state:   5 pods running ✓
```

This reconciliation loop runs continuously. It handles:
- Pod crashes (container exits with error)
- Node failures (node goes down, pods are rescheduled elsewhere)
- Manual deletions (as demonstrated above)

### Liveness and readiness probes

Kubernetes can check whether your app is actually healthy, not just "running":

- **Liveness probe** — "Is this container still alive?" If it fails, Kubernetes restarts the container.
- **Readiness probe** — "Is this container ready to accept traffic?" If it fails, the Service stops sending traffic to it (but doesn't restart it).

Example (not in our current config, but you can add it):

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    ports:
      - containerPort: 8000
    livenessProbe:
      httpGet:
        path: /
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /
        port: 8000
      initialDelaySeconds: 3
      periodSeconds: 5
```

This tells Kubernetes to `GET /` every 10 seconds (liveness) and every 5 seconds (readiness). If the endpoint returns a non-2xx status, the probe fails.

---

## 7. Rolling Updates

Rolling updates let you deploy a new version of your app with **zero downtime**. Kubernetes gradually replaces old pods with new ones.

### The update process

```
Step 1:  [v1] [v1] [v1] [v1] [v1]     ← all old version
Step 2:  [v1] [v1] [v1] [v1] [v2]     ← one new pod created
Step 3:  [v1] [v1] [v1] [v2] [v2]     ← another old pod replaced
Step 4:  [v1] [v1] [v2] [v2] [v2]
Step 5:  [v1] [v2] [v2] [v2] [v2]
Step 6:  [v2] [v2] [v2] [v2] [v2]     ← all new version
```

At every step, some pods are handling traffic. Users never see downtime.

### Deploying a new version

```bash
# 1. Make a code change (e.g., edit main.py)

# 2. Rebuild the Docker image
make docker-build

# 3. Restart the deployment (picks up the new image)
kubectl rollout restart deployment fastapi-k8s

# 4. Watch the rollout progress
kubectl rollout status deployment fastapi-k8s
# Waiting for deployment "fastapi-k8s" rollout to finish: 2 out of 5 new replicas have been updated...
# deployment "fastapi-k8s" successfully rolled out
```

### Rollback

If something goes wrong:

```bash
# Undo the last rollout
kubectl rollout undo deployment fastapi-k8s

# Check rollout history
kubectl rollout history deployment fastapi-k8s
```

### Update strategies

Kubernetes supports two strategies:

**RollingUpdate** (default):
```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1         # Max pods above desired count during update
      maxUnavailable: 0    # Max pods that can be unavailable during update
```

- `maxSurge: 1` — Create at most 1 extra pod during the update
- `maxUnavailable: 0` — Never let any pod be unavailable (safe but slower)

**Recreate:**
```yaml
spec:
  strategy:
    type: Recreate
```

Kills all old pods first, then creates new ones. Simple but causes downtime. Use only when your app can't have two versions running simultaneously (e.g., database migrations that break backward compatibility).

---

## 8. Resource Management

By default, a container can use as much CPU and memory as it wants. This is dangerous in a shared cluster — one runaway container can starve others.

### Requests and limits

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    resources:
      requests:
        cpu: "100m"        # 100 millicores = 0.1 CPU
        memory: "128Mi"    # 128 mebibytes
      limits:
        cpu: "500m"        # Max 0.5 CPU
        memory: "256Mi"    # Max 256 MiB
```

| Field | Meaning |
|-------|---------|
| `requests.cpu` | Guaranteed CPU. The scheduler uses this to decide which node to place the pod on. |
| `requests.memory` | Guaranteed memory. |
| `limits.cpu` | Maximum CPU. The container is throttled if it exceeds this. |
| `limits.memory` | Maximum memory. The container is **killed (OOMKilled)** if it exceeds this. |

### Why it matters

- **Scheduling** — Kubernetes uses `requests` to decide where to place pods. If no node has enough free resources, the pod stays in `Pending`.
- **OOM kills** — If a container exceeds its memory limit, Kubernetes kills it and restarts it. You'll see `OOMKilled` in pod status.
- **Fairness** — Without limits, one misbehaving app can consume all cluster resources.

### CPU units

- `1` = 1 full CPU core
- `500m` = 0.5 CPU (500 millicores)
- `100m` = 0.1 CPU

### Memory units

- `128Mi` = 128 mebibytes (MiB) — binary, 1 MiB = 1,048,576 bytes
- `128M` = 128 megabytes (MB) — decimal, 1 MB = 1,000,000 bytes

### Monitoring resource usage

```bash
# Requires metrics-server (see Monitoring section)
kubectl top pods -l app=fastapi-k8s
```

---

## 9. Monitoring & Observability

### Built-in tools

Kubernetes provides several built-in ways to observe your workloads:

```bash
# Resource usage per pod (requires metrics-server)
kubectl top pods

# Resource usage per node
kubectl top nodes

# Logs from a specific pod
kubectl logs <pod-name>

# Logs from all pods with a label
kubectl logs -l app=fastapi-k8s

# Follow logs in real-time
kubectl logs -l app=fastapi-k8s -f

# Detailed pod info (events, conditions, resource usage)
kubectl describe pod <pod-name>
```

### Metrics Server

`kubectl top` requires **metrics-server** to be installed. On Docker Desktop:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

You may need to add `--kubelet-insecure-tls` to the metrics-server deployment args for Docker Desktop:

```bash
kubectl patch deployment metrics-server -n kube-system --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
```

After a minute or two:

```bash
kubectl top pods -l app=fastapi-k8s
# NAME                          CPU(cores)   MEMORY(bytes)
# fastapi-k8s-7f8b9c6d4-2nxkl  1m           28Mi
# fastapi-k8s-7f8b9c6d4-5m9qr  1m           27Mi
# ...
```

### Prometheus + Grafana

For production monitoring, the standard stack is:

- **Prometheus** — Collects and stores metrics (CPU, memory, request count, latency)
- **Grafana** — Dashboards and visualization
- **Alertmanager** — Sends alerts based on rules

These are typically installed via Helm charts (e.g., `kube-prometheus-stack`). This is beyond the scope of a local Docker Desktop setup, but good to know about for production.

### Application-level health checks

A common pattern for FastAPI apps is a dedicated `/health` endpoint:

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

This can be used as the target for Kubernetes liveness and readiness probes.

### Log aggregation

In production, you want centralized logging. Common solutions:

- **EFK Stack** — Elasticsearch + Fluentd + Kibana
- **Loki + Grafana** — Lightweight alternative (Loki stores logs, Grafana visualizes)
- **Cloud-native** — CloudWatch (AWS), Cloud Logging (GCP), Azure Monitor

For local development, `kubectl logs` is sufficient.

---

## 10. Networking Deep Dive

### Service types

Kubernetes offers four Service types. Each builds on the previous:

| Type | Accessible from | Use case |
|------|----------------|----------|
| **ClusterIP** | Inside the cluster only | Internal services (databases, caches) |
| **NodePort** | `<NodeIP>:<NodePort>` | Development, simple external access |
| **LoadBalancer** | External IP/hostname | Production external access |
| **Ingress** | External via HTTP routing | Multiple services behind one IP |

#### ClusterIP (default)

```yaml
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8000
```

Only reachable from within the cluster. Other pods can access it via `http://fastapi-k8s:80` (Kubernetes DNS).

#### NodePort

```yaml
spec:
  type: NodePort
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30080    # optional, auto-assigned if omitted (30000-32767)
```

Exposes the service on a static port on every node's IP. Access via `http://<node-ip>:30080`.

#### LoadBalancer

```yaml
spec:
  type: LoadBalancer     # ← what we use
  ports:
    - port: 80
      targetPort: 8000
```

On cloud providers, this provisions an actual load balancer (e.g., AWS ELB, GCP load balancer). On Docker Desktop, it maps to `localhost`.

#### Ingress

Not a Service type, but a separate resource. Routes HTTP traffic based on hostname or path:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
spec:
  rules:
    - host: myapp.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fastapi-k8s
                port:
                  number: 80
```

Requires an Ingress Controller (e.g., NGINX Ingress Controller) to be installed in the cluster.

### Port mapping

Three different "port" fields can be confusing:

```
curl :80  ──►  Service (port: 80)  ──►  Pod (targetPort: 8000)  ──►  Container (containerPort: 8000)
```

| Field | Where | Meaning |
|-------|-------|---------|
| `port` | Service spec | Port the Service listens on |
| `targetPort` | Service spec | Port to forward to on the pod |
| `containerPort` | Pod spec | Port the container exposes (documentation only, not enforced) |

`targetPort` and `containerPort` should match (both 8000 in our case).

---

## 11. Configuration & Secrets

### ConfigMaps

A **ConfigMap** stores non-sensitive configuration as key-value pairs. You can inject them as environment variables or mount them as files.

#### Creating a ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastapi-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"
```

#### Using as environment variables

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    envFrom:
      - configMapRef:
          name: fastapi-config
```

Now your FastAPI app can read these:

```python
import os
app_env = os.getenv("APP_ENV", "development")
```

#### Using individual values

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    env:
      - name: APP_ENV
        valueFrom:
          configMapKeyRef:
            name: fastapi-config
            key: APP_ENV
```

### Secrets

**Secrets** are like ConfigMaps but for sensitive data (passwords, API keys, tokens). Values are base64-encoded (not encrypted by default — use external secret managers for real security).

#### Creating a Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fastapi-secrets
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXM6Ly91c2VyOnBhc3NAZGI6NTQzMi9teWRi    # base64 encoded
  API_KEY: c3VwZXItc2VjcmV0LWtleQ==                                # base64 encoded
```

To encode a value:

```bash
echo -n "my-secret-value" | base64
```

#### Using Secrets as environment variables

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    env:
      - name: DATABASE_URL
        valueFrom:
          secretKeyRef:
            name: fastapi-secrets
            key: DATABASE_URL
```

#### Mounting as files

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    volumeMounts:
      - name: secret-volume
        mountPath: /etc/secrets
        readOnly: true
volumes:
  - name: secret-volume
    secret:
      secretName: fastapi-secrets
```

This mounts each key as a file in `/etc/secrets/` (e.g., `/etc/secrets/DATABASE_URL`).

---

## 12. Persistent Storage

By default, all data inside a container is lost when the container restarts. For stateless apps like ours, this is fine. For databases or file uploads, you need persistent storage.

### Concepts

- **PersistentVolume (PV)** — A piece of storage provisioned by an admin or dynamically by the cluster (think: a physical disk).
- **PersistentVolumeClaim (PVC)** — A request for storage by a pod (think: "I need 10Gi of disk").

```
Pod  ──uses──►  PVC  ──binds to──►  PV  ──backed by──►  Actual disk
```

### Example

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
spec:
  accessModes:
    - ReadWriteOnce          # Can be mounted by a single node
  resources:
    requests:
      storage: 1Gi           # Request 1 GiB of storage
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
        - name: my-app
          volumeMounts:
            - name: data
              mountPath: /app/data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: data-pvc
```

### When you need it

- Databases (PostgreSQL, MySQL, MongoDB)
- File uploads
- Application state that must survive restarts
- Cache that should persist across pod restarts

### When you don't need it

- Stateless API servers (like this project)
- Apps that store state externally (e.g., in a cloud database)
- Apps that can rebuild their state on startup

---

## 13. Horizontal Pod Autoscaler (HPA)

Instead of manually running `make scale N=10`, you can let Kubernetes automatically adjust the replica count based on resource utilization.

### Prerequisites

HPA requires **metrics-server** (see [Monitoring section](#9-monitoring--observability)).

### Creating an HPA

```bash
kubectl autoscale deployment fastapi-k8s \
  --cpu-percent=50 \
  --min=2 \
  --max=20
```

This means:
- If average CPU across all pods exceeds 50% of their request, **scale up**
- If average CPU drops below 50%, **scale down**
- Never go below 2 replicas or above 20

### HPA as YAML

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fastapi-k8s-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fastapi-k8s
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
```

### Checking HPA status

```bash
kubectl get hpa
# NAME              REFERENCE                TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
# fastapi-k8s-hpa   Deployment/fastapi-k8s   12%/50%   2         20        5          3m

kubectl describe hpa fastapi-k8s-hpa
```

### Important notes

- HPA requires resource `requests` to be set on your containers (otherwise it has no baseline to calculate percentages)
- HPA overrides the `replicas` field in your Deployment
- Scale-up is faster than scale-down (Kubernetes is cautious about scaling down to avoid flapping)

---

## 14. Common Troubleshooting

### Debugging flowchart

```
Problem?
   │
   ▼
kubectl get pods
   │
   ├── Pending ────────► kubectl describe pod <name>
   │                      └── Check: resource constraints, node selectors, image pull
   │
   ├── CrashLoopBackOff ► kubectl logs <name>
   │                      └── Check: app crash, missing env vars, port conflict
   │
   ├── ImagePullBackOff ► kubectl describe pod <name>
   │                      └── Check: image name, tag, imagePullPolicy
   │
   ├── Running but ─────► kubectl logs <name>
   │   not working        kubectl describe svc <name>
   │                      └── Check: selector mismatch, wrong port
   │
   └── Running OK ──────► The issue is elsewhere (networking, client, DNS)
```

### Pod stuck in `Pending`

**Symptoms:** Pod stays in `Pending` state and never starts.

**Common causes:**
- **Insufficient resources** — The cluster doesn't have enough CPU/memory to schedule the pod.
  ```bash
  kubectl describe pod <name>
  # Look for: "Insufficient cpu" or "Insufficient memory" in Events
  ```
- **Image pull error** — Can't find the Docker image.
- **Node selector/affinity** — Pod requires a node that doesn't exist.

**Fix:**
- Reduce resource requests, or scale down other workloads
- Check image name and `imagePullPolicy`

### `CrashLoopBackOff`

**Symptoms:** Pod starts, crashes, restarts, crashes again. Kubernetes backs off on restart intervals.

**Common causes:**
- Application error (unhandled exception, missing dependency)
- Missing environment variable
- Wrong command or port

**Debugging:**
```bash
kubectl logs <pod-name>                    # See app output
kubectl logs <pod-name> --previous         # See logs from the PREVIOUS crashed container
kubectl describe pod <pod-name>            # See events and exit codes
```

### `ImagePullBackOff`

**Symptoms:** Pod can't pull the Docker image.

**Common causes:**
- Wrong image name or tag
- Missing `imagePullPolicy: Never` (for local Docker Desktop images)
- Private registry without proper credentials

**Fix for Docker Desktop:**
```yaml
imagePullPolicy: Never    # Must be set for local images
```

Make sure you've built the image locally:
```bash
make docker-build
```

### Service not reachable

**Symptoms:** `curl http://localhost` times out or refuses connection.

**Debugging:**
```bash
# Check the service exists and has endpoints
kubectl get svc fastapi-k8s
kubectl get endpoints fastapi-k8s

# If endpoints is empty, the selector doesn't match any pods
# Compare labels:
kubectl get pods --show-labels
kubectl describe svc fastapi-k8s    # Check "Selector" field
```

**Common causes:**
- **Selector mismatch** — The Service's `selector` doesn't match the pod labels
- **Wrong port** — `targetPort` in Service doesn't match `containerPort` in pod
- **Pods not running** — No healthy pods to route to

---

## 15. Where to Go Next

This guide covered the fundamentals using a local Docker Desktop cluster. Here's where to go from here:

### Helm

[Helm](https://helm.sh/) is the package manager for Kubernetes. Instead of managing raw YAML, you use **charts** — templated, versioned, reusable packages.

```bash
# Example: install PostgreSQL with one command
helm install my-postgres bitnami/postgresql
```

### Kustomize

[Kustomize](https://kustomize.io/) is built into `kubectl`. It lets you create overlays for different environments (dev, staging, prod) without duplicating YAML.

```bash
kubectl apply -k overlays/production/
```

### CI/CD integration

Automate your workflow:
1. Push code to Git
2. CI builds Docker image and pushes to registry
3. CD updates the Kubernetes deployment

Popular tools: GitHub Actions, GitLab CI, ArgoCD, Flux.

### Production clusters

Docker Desktop is great for learning, but production workloads need real clusters:

- **AWS** — EKS (Elastic Kubernetes Service)
- **GCP** — GKE (Google Kubernetes Engine)
- **Azure** — AKS (Azure Kubernetes Service)
- **Self-managed** — kubeadm, k3s, Rancher

### Official Kubernetes documentation

- [Kubernetes Docs](https://kubernetes.io/docs/home/) — The definitive reference
- [Kubernetes Basics Tutorial](https://kubernetes.io/docs/tutorials/kubernetes-basics/) — Interactive tutorial
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/) — Quick reference for common commands
