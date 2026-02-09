# Monitoring & Observability

Deploying an application is only half the battle. Once your pods are running, you need
to **see what they are doing**. This chapter covers everything from the built-in kubectl
commands you will use daily to the production-grade stacks you will encounter at work.

---

## The three pillars of observability

Production systems rely on three complementary signals to stay healthy:

| Pillar | What it tells you | Example |
|--------|-------------------|---------|
| **Metrics** | Numeric measurements over time (CPU, memory, request rate, error rate) | "Pod CPU usage hit 95% at 14:32" |
| **Logs** | Discrete text records of events inside a process | `[INFO] stress starting for 10s (max 30s)` |
| **Traces** | The path a single request takes across services | `GET /` -> API pod -> database -> response in 42 ms |

Metrics tell you **something is wrong**, logs tell you **what went wrong**, and traces
tell you **where it went wrong** in a multi-service system. For a single-service project
like fastapi-k8s, metrics and logs cover most debugging needs. Traces become essential
once you have multiple services calling each other.

---

## Built-in kubectl tools

Kubernetes ships with several commands that require nothing extra to install.

### kubectl logs

The most common debugging command. It reads the stdout/stderr stream of a container.

```bash
# Logs from a specific pod
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl

# Follow logs in real-time (like tail -f)
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl -f

# Logs from the previous container instance (useful after a crash/restart)
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl --previous

# Only show logs from the last 5 minutes
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl --since=5m

# Only show the last 50 lines
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl --tail=50

# Combine flags: follow, last 20 lines, from the last minute
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl -f --tail=20 --since=1m
```

**Selecting pods by label** -- instead of typing a specific pod name, use `-l` to match
all pods with a given label:

```bash
# Logs from every pod in our deployment
kubectl logs -l app=fastapi-k8s

# Follow all pods (adds a pod-name prefix to each line)
kubectl logs -l app=fastapi-k8s -f
```

**Multi-container pods** -- if a pod has more than one container (for example a sidecar
proxy), use `-c` to pick which container's logs to read:

```bash
kubectl logs <pod-name> -c fastapi-k8s
kubectl logs <pod-name> -c istio-proxy
```

!!! tip "Our Makefile shortcut"
    `make logs` runs `kubectl logs -l app=fastapi-k8s`, which fetches logs from all
    pods in the deployment at once.

### kubectl describe

`kubectl describe` prints a human-readable summary of a resource. For pods, this
includes far more than `kubectl get`:

```bash
kubectl describe pod fastapi-k8s-7f8b9c6d4-2nxkl
```

Key sections in the output:

| Section | What it shows |
|---------|---------------|
| **Name / Namespace / Node** | Which node the pod landed on, its IP address |
| **Labels & Annotations** | All metadata attached to the pod |
| **Status** | Running, Pending, CrashLoopBackOff, etc. |
| **Containers** | Image, ports, resource requests/limits, environment variables |
| **Conditions** | PodScheduled, Initialized, ContainersReady, Ready |
| **Volumes** | ConfigMap mounts, Secret mounts, emptyDir, PVCs |
| **Events** | Recent events like pull image, created container, started, probe failures |

The **Events** section at the bottom is usually the most useful for debugging. If a pod
is stuck in `Pending` or `CrashLoopBackOff`, the events will tell you why.

```bash
# Describe the deployment (shows replica counts, strategy, rollout events)
kubectl describe deployment fastapi-k8s

# Describe the service (shows endpoints, i.e., which pod IPs receive traffic)
kubectl describe service fastapi-k8s
```

### kubectl get -- output formats

The default `kubectl get` output is a compact table. You can ask for more detail:

```bash
# Default view
kubectl get pods -l app=fastapi-k8s

# Wide view -- adds node name and pod IP columns
kubectl get pods -l app=fastapi-k8s -o wide

# Full YAML -- the complete resource spec as Kubernetes sees it
kubectl get pod fastapi-k8s-7f8b9c6d4-2nxkl -o yaml

# Full JSON -- same data, JSON format (handy for piping to jq)
kubectl get pod fastapi-k8s-7f8b9c6d4-2nxkl -o json
```

**jsonpath** lets you extract specific fields without parsing the entire output:

```bash
# Get just the pod IP
kubectl get pod fastapi-k8s-7f8b9c6d4-2nxkl \
  -o jsonpath='{.status.podIP}'

# List all container images in a pod
kubectl get pod fastapi-k8s-7f8b9c6d4-2nxkl \
  -o jsonpath='{.spec.containers[*].image}'

# List pod names and their restart counts
kubectl get pods -l app=fastapi-k8s \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
```

!!! info "When to use which format"
    Use `-o wide` for a quick glance at node placement. Use `-o yaml` when you need to
    see the full spec (probe config, volume mounts, env vars). Use `-o jsonpath` when
    you need a specific value in a script.

### kubectl top

Shows real-time CPU and memory consumption -- the Kubernetes equivalent of `top` or
`htop`. This command **requires metrics-server** to be installed (see next section).

```bash
# CPU and memory per pod
kubectl top pods -l app=fastapi-k8s

# CPU and memory per node
kubectl top nodes

# Sort by CPU usage (highest first)
kubectl top pods -l app=fastapi-k8s --sort-by=cpu

# Sort by memory
kubectl top pods -l app=fastapi-k8s --sort-by=memory
```

Example output:

```
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-2nxkl  1m           28Mi
fastapi-k8s-7f8b9c6d4-5m9qr  1m           27Mi
fastapi-k8s-7f8b9c6d4-8kj4z  2m           29Mi
```

The `CPU(cores)` column uses **millicores** -- `1m` means one-thousandth of a CPU core.
Our pods request `50m` and are limited to `200m`, so at idle (`1m`) they are using about
2% of their request and 0.5% of their limit.

---

## Metrics Server

### What it does

Metrics Server is a lightweight, in-memory aggregator that collects resource usage data
(CPU and memory) from the **kubelet** running on each node. It exposes this data through
the Kubernetes Metrics API, which is consumed by:

- `kubectl top` -- the command-line resource viewer
- **HPA (Horizontal Pod Autoscaler)** -- scales pods based on CPU/memory thresholds

Metrics Server does **not** store historical data. It only holds the most recent snapshot.
For historical metrics, you need Prometheus or a similar time-series database.

### Installation on Docker Desktop

Docker Desktop does not ship with metrics-server pre-installed. This project provides a
Make target that handles the full setup:

```bash
make metrics-server
```

This command does three things:

1. **Installs metrics-server** from the official release manifest
2. **Patches the deployment** to add `--kubelet-insecure-tls`
3. **Waits** for the deployment to become available (up to 120 seconds)

### Why --kubelet-insecure-tls?

Metrics Server normally connects to each kubelet over HTTPS and validates its TLS
certificate. In production clusters, kubelets have certificates signed by the cluster CA.
Docker Desktop uses **self-signed certificates** that metrics-server does not trust by
default. The `--kubelet-insecure-tls` flag tells metrics-server to skip certificate
verification.

!!! note
    This flag is safe for local development. Never use it in a production cluster --
    instead, ensure your kubelets have properly signed certificates.

### Reading the output

After installing metrics-server, wait about 60 seconds for it to collect its first
round of data, then:

```bash
kubectl top pods -l app=fastapi-k8s
```

If you see `error: Metrics not available for pod`, the server has not collected data yet.
Wait another minute and try again. If the error persists, check that metrics-server is
running:

```bash
kubectl get pods -n kube-system -l k8s-app=metrics-server
```

---

## Application-level health checks

Our fastapi-k8s app exposes two health check endpoints, and `k8s.yaml` wires them to
Kubernetes probes.

### Liveness probe -- /health

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 10
```

- Kubernetes sends `GET /health` every 10 seconds (after an initial 3-second delay).
- Our endpoint always returns `{"status": "healthy"}` with a 200 status code.
- If the probe fails (non-2xx response or timeout) **three consecutive times** (the
  default `failureThreshold`), Kubernetes **kills and restarts** the container.
- Use case: detecting deadlocked or frozen processes that are still technically running
  but no longer serving requests.

### Readiness probe -- /ready

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 2
  periodSeconds: 5
```

- Kubernetes sends `GET /ready` every 5 seconds.
- Our endpoint returns 200 when `_ready` is `True`, or 503 when it has been toggled off
  via `POST /ready/disable`.
- If the probe fails, the pod is **removed from the Service's endpoint list** -- it stops
  receiving traffic but is **not** restarted.
- When the probe succeeds again, the pod is added back to the endpoint list.
- Use case: temporarily draining a pod during maintenance, or waiting for a cache to warm
  up before accepting traffic.

### Checking probe status

Use `kubectl describe` to see probe configuration and recent probe events:

```bash
kubectl describe pod fastapi-k8s-7f8b9c6d4-2nxkl | grep -A 5 "Liveness\|Readiness"
```

If a probe is failing, you will see events like:

```
Warning  Unhealthy  12s  kubelet  Readiness probe failed: HTTP probe failed with statuscode: 503
```

You can also watch readiness in real time:

```bash
# The READY column shows 1/1 when ready, 0/1 when not
kubectl get pods -l app=fastapi-k8s -w
```

Try it yourself:

```bash
# Disable readiness on one pod
curl -X POST http://localhost/ready/disable

# Watch the READY column change
kubectl get pods -l app=fastapi-k8s

# Re-enable
curl -X POST http://localhost/ready/enable
```

---

## Kubernetes Events

Events are first-class objects in Kubernetes that record things happening to your
resources -- image pulls, container starts, probe failures, scheduling decisions, scaling
actions, and more.

### Viewing events

```bash
# All events in the default namespace, sorted by time
kubectl get events --sort-by='.lastTimestamp'

# Events for a specific pod
kubectl get events --field-selector involvedObject.name=fastapi-k8s-7f8b9c6d4-2nxkl

# Events across all namespaces
kubectl get events -A

# Watch events in real-time
kubectl get events -w
```

### What events look like

```
LAST SEEN   TYPE      REASON    OBJECT                             MESSAGE
2m          Normal    Pulling   pod/fastapi-k8s-7f8b9c6d4-2nxkl   Pulling image "fastapi-k8s:latest"
2m          Normal    Pulled    pod/fastapi-k8s-7f8b9c6d4-2nxkl   Successfully pulled image
2m          Normal    Created   pod/fastapi-k8s-7f8b9c6d4-2nxkl   Created container fastapi-k8s
2m          Normal    Started   pod/fastapi-k8s-7f8b9c6d4-2nxkl   Started container fastapi-k8s
30s         Warning   Unhealthy pod/fastapi-k8s-7f8b9c6d4-2nxkl   Readiness probe failed: ...
```

### Event retention

By default, the Kubernetes API server retains events for **1 hour**. After that, they are
garbage collected. This means events are useful for recent debugging but not for
historical analysis. For long-term event storage, you need to export them to an external
system (many log aggregation tools can ingest Kubernetes events).

!!! tip "Events are your first stop for debugging"
    If a pod is stuck in `Pending`, `ImagePullBackOff`, or `CrashLoopBackOff`, run
    `kubectl get events --sort-by='.lastTimestamp'` before anything else. The events
    will almost always tell you what went wrong.

---

## Our app's _log() helper

The fastapi-k8s application uses a simple `_log()` function that respects the `LOG_LEVEL`
environment variable set via the ConfigMap in `k8s.yaml`:

```python
_LOG_LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3}

def _log(level: str, message: str):
    if _LOG_LEVELS.get(level, 1) >= _LOG_LEVELS.get(LOG_LEVEL, 1):
        print(f"[{level.upper()}] {message}", file=sys.stderr, flush=True)
```

The ConfigMap sets `LOG_LEVEL: "info"` by default. This means:

- `_log("debug", ...)` -- **suppressed** (debug=0 < info=1)
- `_log("info", ...)` -- **printed** (info=1 >= info=1)
- `_log("warning", ...)` -- **printed** (warning=2 >= info=1)
- `_log("error", ...)` -- **printed** (error=3 >= info=1)

Logs are written to **stderr** with `flush=True`, so they appear immediately in
`kubectl logs`. To change the log level, edit the ConfigMap:

```bash
# Edit the ConfigMap to enable debug logging
kubectl edit configmap fastapi-config

# Change LOG_LEVEL from "info" to "debug", save, then restart pods
kubectl rollout restart deployment/fastapi-k8s
```

!!! note
    Changing a ConfigMap does not automatically restart pods. You need to trigger a
    rollout restart (or delete the pods) for the new value to take effect, because the
    env vars are injected at pod creation time.

View the application logs:

```bash
# See all log output
kubectl logs -l app=fastapi-k8s

# Follow logs while hitting the stress endpoint
kubectl logs -l app=fastapi-k8s -f
```

When you hit `/stress?seconds=5`, you will see lines like:

```
[INFO] stress starting for 5s (max 30s)
[INFO] stress completed after 5s
```

---

## Resource monitoring walkthrough

This hands-on exercise shows how to observe CPU usage in real time using metrics-server
and the `/stress` endpoint.

### Step 1 -- Install metrics-server

```bash
make metrics-server
```

Wait about 60 seconds for metrics-server to start collecting data.

### Step 2 -- Check baseline resource usage

```bash
kubectl top pods -l app=fastapi-k8s
```

You should see all pods at roughly 1-2m CPU (idle):

```
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-2nxkl  1m           28Mi
fastapi-k8s-7f8b9c6d4-5m9qr  1m           27Mi
fastapi-k8s-7f8b9c6d4-8kj4z  1m           29Mi
```

### Step 3 -- Generate CPU load

In a separate terminal, hit the stress endpoint:

```bash
curl "http://localhost/stress?seconds=30"
```

### Step 4 -- Watch CPU spike

While the stress request is running, poll `kubectl top` in your first terminal:

```bash
kubectl top pods -l app=fastapi-k8s --sort-by=cpu
```

You will see one pod's CPU jump dramatically -- up towards its `200m` limit:

```
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-2nxkl  198m         30Mi    <-- handling the stress request
fastapi-k8s-7f8b9c6d4-5m9qr  1m           27Mi
fastapi-k8s-7f8b9c6d4-8kj4z  1m           29Mi
```

The pod hits `198m` because its CPU limit is `200m` -- Kubernetes throttles it at that
ceiling. After the stress request completes, CPU drops back to idle.

!!! tip "Combine with HPA"
    If you have the Horizontal Pod Autoscaler enabled (`make hpa`), this CPU spike can
    trigger automatic scale-out. See the [HPA chapter](hpa.md) for details.

---

## Prometheus + Grafana

For anything beyond basic `kubectl top` monitoring, the industry standard is the
Prometheus and Grafana combination.

### What each component does

- **Prometheus** -- A time-series database that **pulls** (scrapes) metrics from
  endpoints at regular intervals. It stores numeric data with timestamps and labels,
  such as `http_requests_total{method="GET", endpoint="/", status="200"} 1523`.
- **Grafana** -- A visualization platform that queries Prometheus (and other data
  sources) to render dashboards with graphs, tables, and alerts.
- **Alertmanager** -- Receives alerts from Prometheus and routes them to Slack, email,
  PagerDuty, or other notification channels.

### How Prometheus scrapes metrics

Prometheus works on a **pull model**:

1. Each application exposes a `/metrics` endpoint in a text format called OpenMetrics.
2. Prometheus is configured with **scrape targets** -- a list of endpoints to poll.
3. Every `scrape_interval` (typically 15-30 seconds), Prometheus sends an HTTP GET to
   each target and stores the returned metrics.
4. In Kubernetes, Prometheus discovers targets automatically using **ServiceMonitor**
   resources or pod annotations like `prometheus.io/scrape: "true"`.

### PromQL basics

Prometheus has its own query language called PromQL. A few examples:

```promql
# Current CPU usage across all fastapi-k8s pods
sum(rate(container_cpu_usage_seconds_total{pod=~"fastapi-k8s.*"}[5m]))

# Request rate per second (if your app exports http_requests_total)
rate(http_requests_total{app="fastapi-k8s"}[5m])

# 99th percentile request duration
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{app="fastapi-k8s"}[5m]))

# Memory usage in megabytes
container_memory_usage_bytes{pod=~"fastapi-k8s.*"} / 1024 / 1024
```

### Installing with Helm (kube-prometheus-stack)

The easiest way to get the full stack is the `kube-prometheus-stack` Helm chart. It
installs Prometheus, Grafana, Alertmanager, node-exporter, and kube-state-metrics in one
command:

```bash
# Add the Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install (creates a "monitoring" namespace)
helm install kube-prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace

# Access Grafana (default user: admin, password: prom-operator)
kubectl port-forward -n monitoring svc/kube-prometheus-grafana 3000:80
```

Then open `http://localhost:3000` in your browser. The chart ships with dozens of
pre-built dashboards for node health, pod resource usage, and Kubernetes internals.

!!! info
    The full Prometheus + Grafana stack is resource-heavy for a local Docker Desktop
    setup. It is included here so you understand the concepts. In practice, you would
    run this on a real cluster or use a managed solution.

---

## Log aggregation

`kubectl logs` works well for a handful of pods, but in production you may have hundreds
of pods across multiple namespaces. You need a centralized place to search, filter, and
alert on logs.

### EFK stack (Elasticsearch + Fluentd + Kibana)

- **Fluentd** runs as a DaemonSet (one pod per node) and tails container log files from
  each node's filesystem.
- **Elasticsearch** stores and indexes the logs for full-text search.
- **Kibana** provides a web UI for searching, filtering, and visualizing logs.

The EFK stack is powerful but heavyweight -- Elasticsearch alone needs significant memory
and storage.

### Loki + Grafana (lightweight alternative)

- **Loki** stores logs indexed only by labels (not full-text), making it much lighter
  than Elasticsearch.
- **Promtail** (or Grafana Agent) runs as a DaemonSet and ships logs to Loki.
- **Grafana** provides the query UI (using LogQL, similar to PromQL).

Loki + Grafana is a popular choice because if you already have Grafana for metrics, you
get logs in the same dashboard tool.

```bash
# Install with Helm
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install loki grafana/loki-stack --namespace monitoring --create-namespace
```

### Cloud-native solutions

Managed Kubernetes services offer built-in log aggregation:

| Cloud provider | Service | Notes |
|----------------|---------|-------|
| **AWS (EKS)** | CloudWatch Container Insights | Fluent Bit DaemonSet ships logs to CloudWatch |
| **GCP (GKE)** | Cloud Logging (Stackdriver) | Enabled by default -- no setup needed |
| **Azure (AKS)** | Azure Monitor / Container Insights | Integrates with Log Analytics workspace |

These remove the operational burden of running your own log infrastructure.

### Structured logging best practices

Regardless of which aggregation tool you use, **structured logs** (JSON format) make
searching and filtering far easier than plain text:

```python
# Plain text (hard to parse)
print("[INFO] request completed in 42ms")

# Structured JSON (easy to filter and aggregate)
import json
print(json.dumps({
    "level": "info",
    "message": "request completed",
    "duration_ms": 42,
    "endpoint": "/",
    "method": "GET"
}))
```

With structured logs, you can query things like "show me all requests slower than 100ms"
or "show me all errors from the /stress endpoint" without relying on fragile regex
patterns.

!!! tip "For this project"
    Our `_log()` helper uses a simple `[LEVEL] message` format, which is fine for
    learning. In a production app, consider switching to a structured logging library
    like `structlog` or Python's built-in `logging` module with a JSON formatter.

---

## Summary

| Tool / concept | What it gives you | When to use it |
|----------------|-------------------|----------------|
| `kubectl logs` | Container stdout/stderr | First thing to check when debugging |
| `kubectl describe` | Resource details + events | Pod stuck in Pending/CrashLoopBackOff |
| `kubectl get -o wide/yaml` | Extended resource info | Checking node placement, full spec |
| `kubectl top` | Real-time CPU/memory | Quick resource check (needs metrics-server) |
| `kubectl get events` | Cluster event stream | Understanding what happened and when |
| Metrics Server | Powers `kubectl top` and HPA | Install once on Docker Desktop |
| Liveness/readiness probes | Automatic health checking | Already configured in `k8s.yaml` |
| Prometheus + Grafana | Metrics storage + dashboards | Production monitoring |
| EFK / Loki | Centralized log aggregation | Production log management |
| Structured logging | Machine-parseable log entries | Any app beyond the prototype stage |
