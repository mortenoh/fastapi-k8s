# Kubectl Cheatsheet

A quick-reference page for daily kubectl work with the fastapi-k8s project. Commands use actual resource names from this project. For deeper explanations, follow the cross-links to the relevant guide pages.

---

## Cluster and Context

| Command | Description |
|---------|-------------|
| `kubectl config current-context` | Show the active cluster context |
| `kubectl config get-contexts` | List all available contexts |
| `kubectl config use-context docker-desktop` | Switch to Docker Desktop cluster |
| `kubectl get nodes` | List cluster nodes |
| `kubectl cluster-info` | Show API server and CoreDNS addresses |
| `kubectl version` | Show client and server versions |

```bash
# Confirm you are targeting the right cluster before running anything
kubectl config current-context
# Expected output: docker-desktop
```

---

## Project Quick Reference

Makefile targets and their raw kubectl equivalents.

| Make target | kubectl equivalent |
|-------------|-------------------|
| `make deploy` | `kubectl apply -f k8s.yaml` |
| `make status` | `kubectl get pods,svc -l app=fastapi-k8s` |
| `make scale N=5` | `kubectl scale deployment fastapi-k8s --replicas=5` |
| `make logs` | `kubectl logs -l app=fastapi-k8s` |
| `make restart` | `kubectl rollout restart deployment/fastapi-k8s` |
| `make rollout-status` | `kubectl rollout status deployment/fastapi-k8s` |
| `make undeploy` | `kubectl delete -f k8s.yaml` |
| `make redis-deploy` | `kubectl apply -f k8s/redis-secret.yaml -f k8s/redis.yaml` |
| `make redis-status` | `kubectl get pods,svc,pvc -l app=redis` |
| `make redis-logs` | `kubectl logs -l app=redis` |
| `make redis-undeploy` | `kubectl delete -f k8s/redis.yaml` |
| `make redis-clean` | Delete redis deployment, secret, and PVC |
| `make hpa` | `kubectl apply -f k8s/hpa.yaml` |
| `make hpa-status` | `kubectl get hpa -l app=fastapi-k8s` |
| `make hpa-delete` | `kubectl delete -f k8s/hpa.yaml` |
| `make docker-build` | `docker build -t fastapi-k8s:latest .` |
| `make metrics-server` | Install and patch metrics-server |

*See [Your First Deployment](first-deployment.md) for the initial setup walkthrough.*

---

## Viewing Resources (kubectl get)

| Command | Description |
|---------|-------------|
| `kubectl get pods -l app=fastapi-k8s` | List app pods |
| `kubectl get pods -l app=fastapi-k8s -o wide` | Include node and IP columns |
| `kubectl get pods -l app=fastapi-k8s -w` | Watch for changes in real-time |
| `kubectl get pods -A` | Pods in all namespaces |
| `kubectl get all -l app=fastapi-k8s` | All resource types for the app |
| `kubectl get pods --field-selector=status.phase=Running` | Filter by pod phase |
| `kubectl get pods --sort-by='.metadata.creationTimestamp'` | Sort by creation time |
| `kubectl get pods --sort-by='.status.containerStatuses[0].restartCount'` | Sort by restart count |

```bash
# Extract a single field with jsonpath
kubectl get pods -l app=fastapi-k8s \
  -o jsonpath='{.items[*].metadata.name}'

# Custom columns
kubectl get pods -l app=fastapi-k8s \
  -o custom-columns='NAME:.metadata.name,STATUS:.status.phase,IP:.status.podIP'
```

*See [Deploying & Verifying](deploying-and-verifying.md) for a walkthrough of inspecting your deployment.*

---

## Inspecting Resources (kubectl describe)

| Command | Description |
|---------|-------------|
| `kubectl describe pod <pod-name>` | Pod details, events, conditions |
| `kubectl describe deployment fastapi-k8s` | Deployment strategy, replicas, conditions |
| `kubectl describe svc fastapi-k8s` | Service endpoints, selector, ports |
| `kubectl describe configmap fastapi-config` | ConfigMap keys and values |
| `kubectl describe hpa fastapi-k8s-hpa` | HPA targets, current metrics, events |
| `kubectl describe pvc redis-pvc` | PVC status, capacity, access modes |
| `kubectl describe node docker-desktop` | Node capacity, allocatable, running pods |
| `kubectl describe secret redis-secret` | Secret metadata (values are hidden) |

!!! tip
    `describe` is the single most useful debugging command. It shows events at the bottom, which tell you exactly why a pod is stuck, failing, or restarting.

*See [Common Troubleshooting](troubleshooting.md) for a systematic debugging methodology.*

---

## Logs

| Command | Description |
|---------|-------------|
| `kubectl logs <pod-name>` | Current container logs |
| `kubectl logs <pod-name> --previous` | Logs from the last crashed container |
| `kubectl logs <pod-name> -f` | Follow (stream) logs |
| `kubectl logs <pod-name> --since=5m` | Logs from the last 5 minutes |
| `kubectl logs <pod-name> --since=1h` | Logs from the last hour |
| `kubectl logs <pod-name> --tail=100` | Last 100 lines |
| `kubectl logs -l app=fastapi-k8s` | Logs from all pods matching a label |
| `kubectl logs -l app=fastapi-k8s --all-containers` | All containers across matching pods |

```bash
# Combine flags: follow the last 50 lines from all app pods
kubectl logs -l app=fastapi-k8s --tail=50 -f
```

!!! note
    `kubectl logs -l` has a default limit of 5 pods. For larger deployments, add `--max-log-requests=20` to increase the limit.

*See [Monitoring & Observability](monitoring.md) for more on log analysis.*

---

## Exec and Debug

```bash
# Interactive shell inside a running pod
kubectl exec -it <pod-name> -- /bin/sh

# Check environment variables
kubectl exec <pod-name> -- env | sort

# Test in-cluster DNS resolution
kubectl exec <pod-name> -- wget -qO- http://fastapi-k8s/health

# Test Redis connectivity from an app pod
kubectl exec <pod-name> -- wget -qO- http://localhost:8000/visits
```

```bash
# Run a temporary DNS test pod
kubectl run dnstest --rm -it --restart=Never \
  --image=busybox:1.36 -- nslookup redis.default.svc.cluster.local

# Run a temporary curl pod for testing services
kubectl run curltest --rm -it --restart=Never \
  --image=curlimages/curl -- curl -s http://fastapi-k8s/health
```

!!! warning
    Alpine-based images (including our FastAPI image) may not have `curl` or `nslookup`. Use `wget` instead, or spin up a dedicated debug pod as shown above.

*See [Networking Deep Dive](networking.md) for in-cluster connectivity testing.*

---

## Scaling

```bash
# Manual scale
kubectl scale deployment fastapi-k8s --replicas=5

# Watch pods come up
kubectl get pods -l app=fastapi-k8s -w

# Check HPA status (requires metrics-server)
kubectl get hpa fastapi-k8s-hpa

# Detailed HPA info including events
kubectl describe hpa fastapi-k8s-hpa

# Current CPU and memory usage per pod
kubectl top pods -l app=fastapi-k8s

# Node-level resource usage
kubectl top nodes
```

```bash
# Stress test to trigger HPA scale-up
curl "http://localhost/stress?seconds=10"
# Then watch:
kubectl get hpa fastapi-k8s-hpa -w
```

*See [Scaling](scaling.md) for a hands-on walkthrough and [Horizontal Pod Autoscaler](hpa.md) for HPA configuration.*

---

## Rollouts and Updates

| Command | Description |
|---------|-------------|
| `kubectl rollout status deployment/fastapi-k8s` | Watch current rollout progress |
| `kubectl rollout history deployment/fastapi-k8s` | View rollout revision history |
| `kubectl rollout undo deployment/fastapi-k8s` | Roll back to previous revision |
| `kubectl rollout undo deployment/fastapi-k8s --to-revision=2` | Roll back to a specific revision |
| `kubectl rollout restart deployment/fastapi-k8s` | Trigger a rolling restart |

```bash
# Full rebuild-and-deploy cycle
make docker-build && make deploy && make rollout-status
```

*See [Rolling Updates](rolling-updates.md) for a detailed walkthrough of zero-downtime deployments.*

---

## Configuration and Secrets

```bash
# View ConfigMap values
kubectl get configmap fastapi-config -o yaml

# View specific key
kubectl get configmap fastapi-config -o jsonpath='{.data.APP_NAME}'

# Describe ConfigMap (shows keys and values)
kubectl describe configmap fastapi-config

# View Secret metadata (values are base64-encoded)
kubectl get secret redis-secret -o yaml

# Decode a Secret value
kubectl get secret redis-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d

# Create a Secret from the command line (dry-run to preview)
kubectl create secret generic my-secret \
  --from-literal=KEY=value \
  --dry-run=client -o yaml
```

*See [Configuration & Secrets](configuration-and-secrets.md) for a full walkthrough including live config updates.*

---

## Networking and Services

### Service types

| Type | Accessible from | Project example |
|------|----------------|-----------------|
| **ClusterIP** | Inside the cluster only | `redis` service (port 6379) |
| **NodePort** | `<NodeIP>:<port>` | -- |
| **LoadBalancer** | External IP/hostname | `fastapi-k8s` service (port 80) |
| **ExternalName** | DNS CNAME | -- |

### Useful commands

```bash
# List services
kubectl get svc

# Check service endpoints (which pods receive traffic)
kubectl get endpoints fastapi-k8s

# Port-forward to a specific pod (bypasses the Service)
kubectl port-forward <pod-name> 8001:8000

# Port-forward to the service
kubectl port-forward svc/fastapi-k8s 8080:80
```

### In-cluster DNS names

| DNS name | Resolves to |
|----------|-------------|
| `fastapi-k8s` | fastapi-k8s ClusterIP (same namespace) |
| `fastapi-k8s.default.svc.cluster.local` | Fully qualified |
| `redis` | Redis ClusterIP (same namespace) |
| `redis.default.svc.cluster.local` | Fully qualified |

*See [Networking Deep Dive](networking.md) for a detailed walkthrough of each Service type.*

---

## Persistent Storage

```bash
# List PersistentVolumeClaims
kubectl get pvc

# List PersistentVolumes
kubectl get pv

# Describe PVC for details
kubectl describe pvc redis-pvc
```

### Access modes

| Mode | Abbreviation | Description |
|------|-------------|-------------|
| ReadWriteOnce | RWO | Mounted read-write by a single node |
| ReadOnlyMany | ROX | Mounted read-only by many nodes |
| ReadWriteMany | RWX | Mounted read-write by many nodes |

### PVC YAML snippet (from this project)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  labels:
    app: redis
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Mi
```

*See [Persistent Storage](persistent-storage.md) for a comprehensive walkthrough.*

---

## Resource Management

### Resource units

| Unit | Meaning | Example |
|------|---------|---------|
| `m` | Millicores (1 CPU = 1000m) | `cpu: "200m"` = 0.2 CPU |
| `Mi` | Mebibytes (1 Mi = 1,048,576 bytes) | `memory: "128Mi"` |
| `Gi` | Gibibytes (1 Gi = 1,073,741,824 bytes) | `memory: "2Gi"` |

### Requests vs limits

| Field | Purpose | If exceeded |
|-------|---------|-------------|
| `requests` | Guaranteed minimum; used for scheduling | Pod stays pending if node cannot satisfy |
| `limits` | Hard ceiling | CPU: throttled. Memory: OOMKilled (exit code 137) |

### Project resource settings

```yaml
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"
```

```bash
# Check current usage vs limits
kubectl top pods -l app=fastapi-k8s

# Check node allocatable resources
kubectl describe node docker-desktop | grep -A 5 "Allocated resources"
```

*See [Resource Management](resource-management.md) for a deep dive on requests, limits, and QoS classes.*

---

## Health Probes

### Probe configuration (from this project)

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 2
  periodSeconds: 5
```

### Probe types

| Probe | Purpose | On failure |
|-------|---------|------------|
| **Liveness** | Is the container alive? | Restart the container |
| **Readiness** | Can the container serve traffic? | Remove from Service endpoints |
| **Startup** | Has the container finished initializing? | Keep checking; liveness and readiness are paused |

### Test readiness toggle

```bash
# Disable readiness (pod stops receiving traffic)
curl -X POST http://localhost/ready/disable

# Check that the pod is removed from endpoints
kubectl get endpoints fastapi-k8s

# Re-enable readiness
curl -X POST http://localhost/ready/enable
```

*See [Self-Healing](self-healing.md) for a hands-on probe demonstration.*

---

## Events

```bash
# All events in default namespace, sorted by time
kubectl get events --sort-by='.lastTimestamp'

# Events for a specific pod
kubectl get events --field-selector involvedObject.name=<pod-name>

# Watch events in real-time
kubectl get events -w

# Events across all namespaces
kubectl get events -A --sort-by='.lastTimestamp'
```

!!! tip
    Events are retained for about 1 hour by default. If you need to investigate an issue that happened earlier, check `kubectl describe` output or your centralized logging system.

---

## Labels and Filtering

```bash
# List pods with a specific label
kubectl get pods -l app=fastapi-k8s

# Multiple selectors (AND)
kubectl get pods -l app=fastapi-k8s,version=v1

# Set-based selectors
kubectl get pods -l 'app in (fastapi-k8s, redis)'
kubectl get pods -l 'app notin (redis)'

# Show labels on output
kubectl get pods --show-labels

# Add a label to a pod
kubectl label pod <pod-name> env=debug

# Remove a label from a pod (trailing minus sign)
kubectl label pod <pod-name> env-
```

---

## Namespaces

```bash
# List namespaces
kubectl get namespaces

# Resources in a specific namespace
kubectl get pods -n kube-system

# Resources across all namespaces
kubectl get pods -A

# Set default namespace for kubectl
kubectl config set-context --current --namespace=my-namespace
```

### Default namespaces

| Namespace | Purpose |
|-----------|---------|
| `default` | Where your resources go if no namespace is specified |
| `kube-system` | Kubernetes system components (CoreDNS, metrics-server, etc.) |
| `kube-public` | Publicly readable resources (rarely used directly) |
| `kube-node-lease` | Node heartbeat leases for health detection |

```bash
# Query across namespaces for system pods
kubectl get pods -n kube-system
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

---

## YAML Snippets

Copy-paste blocks from this project. All snippets are from the actual manifests in the repository.

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastapi-config
  labels:
    app: fastapi-k8s
data:
  APP_NAME: "fastapi-k8s"
  LOG_LEVEL: "info"
  MAX_STRESS_SECONDS: "30"
  REDIS_HOST: "redis"
  REDIS_PORT: "6379"
```

### Deployment (key sections)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-k8s
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: fastapi-k8s
  template:
    metadata:
      labels:
        app: fastapi-k8s
    spec:
      containers:
        - name: fastapi-k8s
          image: fastapi-k8s:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
```

### LoadBalancer Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 8000
  selector:
    app: fastapi-k8s
```

### ClusterIP Service (Redis)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
spec:
  type: ClusterIP
  ports:
    - port: 6379
      targetPort: 6379
  selector:
    app: redis
```

### PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  labels:
    app: redis
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Mi
```

### Secret (stringData)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: redis-secret
type: Opaque
stringData:
  REDIS_PASSWORD: "your-password-here"
```

### HorizontalPodAutoscaler

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
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
```

### envFrom (inject entire ConfigMap)

```yaml
envFrom:
  - configMapRef:
      name: fastapi-config
```

### secretKeyRef (inject single Secret key)

```yaml
env:
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: redis-secret
        key: REDIS_PASSWORD
        optional: true
```

### Downward API (pod metadata as env vars)

```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_IP
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
  - name: NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: CPU_REQUEST
    valueFrom:
      resourceFieldRef:
        resource: requests.cpu
  - name: CPU_LIMIT
    valueFrom:
      resourceFieldRef:
        resource: limits.cpu
```

*See [Your First Deployment](first-deployment.md) for a line-by-line YAML walkthrough.*

---

## Debugging Quick Reference

### Pod status table

| Status | First command | Common fix |
|--------|--------------|------------|
| Pending | `kubectl describe pod <name>` | Reduce resource requests or free up node resources |
| ContainerCreating (stuck) | `kubectl describe pod <name>` | Check image pull status and volume mounts |
| ImagePullBackOff | `kubectl describe pod <name>` | Set `imagePullPolicy: Never` for local images, verify image name |
| CrashLoopBackOff | `kubectl logs <name> --previous` | Fix application error (missing env var, bad port, import error) |
| OOMKilled | `kubectl describe pod <name>` | Increase `resources.limits.memory` |
| Running (not working) | `kubectl logs <name>` | Check application errors, verify Service endpoints |
| Terminating (stuck) | `kubectl get pod <name> -o yaml` | Force delete: `kubectl delete pod <name> --grace-period=0 --force` |

### Three-command triage

```bash
# 1. What is the current state?
kubectl get pods -l app=fastapi-k8s -o wide

# 2. Why is the pod in this state?
kubectl describe pod <pod-name>

# 3. What does the application say?
kubectl logs <pod-name> --previous
```

!!! tip
    These three commands diagnose the vast majority of issues. Run them in order -- most problems are identified by step 2 or 3.

*See [Common Troubleshooting](troubleshooting.md) for a comprehensive debugging guide with flowcharts.*

---

## Useful Flags

| Flag | Works with | Description |
|------|-----------|-------------|
| `-o wide` | `get` | Show additional columns (node, IP) |
| `-o yaml` | `get` | Full resource definition in YAML |
| `-o jsonpath='{...}'` | `get` | Extract specific fields |
| `-l app=fastapi-k8s` | `get`, `logs`, `delete`, `top` | Filter by label selector |
| `-w` | `get` | Watch for real-time changes |
| `-f` | `logs` | Follow (stream) logs |
| `--previous` | `logs` | Logs from the previous container instance |
| `--since=5m` | `logs` | Logs from the last N minutes/hours |
| `--tail=100` | `logs` | Last N lines of logs |
| `--sort-by='.metadata.creationTimestamp'` | `get` | Sort output by a JSON path |
| `--field-selector=status.phase=Running` | `get` | Filter by resource field values |
| `-A` / `--all-namespaces` | `get` | Show resources across all namespaces |
| `--dry-run=client -o yaml` | `create`, `run` | Preview the YAML without creating the resource |

---

## Docker Desktop Gotchas

Things that work differently on Docker Desktop compared to cloud Kubernetes clusters.

### imagePullPolicy: Never

Local images built with `docker build` are available to Kubernetes without a registry, but only if you set `imagePullPolicy: Never`. Without this, Kubernetes tries to pull from Docker Hub and fails.

```yaml
# Correct for Docker Desktop
image: fastapi-k8s:latest
imagePullPolicy: Never
```

### metrics-server TLS

The default metrics-server installation fails on Docker Desktop because the kubelet uses a self-signed certificate. The fix is to add the `--kubelet-insecure-tls` flag:

```bash
# Our Makefile handles this automatically
make metrics-server
```

### LoadBalancer = localhost

On cloud providers, a LoadBalancer Service gets a real external IP. On Docker Desktop, it maps to `localhost`:

```bash
# This works on Docker Desktop
curl http://localhost/

# The EXTERNAL-IP column shows "localhost"
kubectl get svc fastapi-k8s
```

### Single node

Docker Desktop runs a single-node cluster. Features that depend on multiple nodes behave differently:

- Pod anti-affinity across nodes has no effect
- Node failure scenarios cannot be tested
- DaemonSets always run exactly one pod
- Topology spread constraints have a single domain

### Resource sharing

Docker Desktop shares CPU and memory with your host OS. Allocating too many resources to Kubernetes pods can slow down your entire machine.

!!! warning
    If your Mac becomes unresponsive after scaling up, reduce replicas: `make scale N=2`. Check Docker Desktop settings to adjust the resource limits allocated to the VM.

### hostpath PVC

PVCs on Docker Desktop use the `hostpath` provisioner, which stores data on the Docker Desktop VM's filesystem. Data persists across pod restarts but is lost if you reset the Kubernetes cluster from Docker Desktop settings.

### Network Policies

Docker Desktop's default networking does not enforce Network Policies. The resources will be created but traffic will not actually be blocked. For testing Network Policies locally, install Calico.

*See [Your First Deployment](first-deployment.md) and [Common Troubleshooting](troubleshooting.md) for more Docker Desktop specifics.*
