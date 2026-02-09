# Redis Integration

This page walks through adding Redis as a second service to the cluster. It builds on concepts covered earlier in the guide -- Secrets, PersistentVolumeClaims, ClusterIP Services, and DNS-based service discovery -- and ties them together into a real multi-service setup.

By the end, you will have:

- A Redis instance with password authentication (Secret), persistent data (PVC), and internal-only access (ClusterIP)
- Three new FastAPI endpoints that read and write data through Redis
- A demonstration of shared state across multiple stateless replicas

---

## Why add Redis?

Up to this point, the FastAPI app is entirely stateless. Every pod is interchangeable, and no data persists beyond a single request. That is great for demonstrating Deployments, scaling, and rolling updates, but it misses several Kubernetes concepts that matter in real applications:

| Concept | What Redis adds |
|---------|----------------|
| **Secrets** | The Redis password is stored in a Kubernetes Secret and injected into both the Redis and FastAPI pods |
| **PersistentVolumeClaims** | Redis data survives pod restarts and deletions via a PVC mounted at `/data` |
| **ClusterIP Services** | Redis is accessible only inside the cluster (no external exposure), contrasting with the FastAPI LoadBalancer |
| **DNS-based service discovery** | FastAPI finds Redis by its Service name (`redis`), not by IP address |
| **Multi-service architecture** | Two Deployments, two Services, communicating through Kubernetes networking |

---

## Architecture overview

```
                          Kubernetes cluster
     +---------------------------------------------------------+
     |                                                         |
     |   +-------------------+         +------------------+    |
     |   |  FastAPI Pods (5) |         |  Redis Pod (1)   |    |
     |   |                   |  DNS    |                  |    |
     |   |  GET /visits -----|-------->|  port 6379       |    |
     |   |  GET /kv/{key}    | "redis" |  --requirepass   |    |
     |   |  POST /kv/{key}   |         |  --appendonly    |    |
     |   +--------+----------+         +--------+---------+    |
     |            |                             |              |
     |   +--------+----------+         +--------+---------+    |
     |   | Service           |         | Service          |    |
     |   | fastapi-k8s       |         | redis            |    |
     |   | type: LoadBalancer |         | type: ClusterIP  |    |
     |   | port 80 -> 8000   |         | port 6379        |    |
     |   +-------------------+         +--------+---------+    |
     |                                          |              |
     |                                 +--------+---------+    |
     |                                 | PVC: redis-pvc   |    |
     |                                 | 100Mi, RWO       |    |
     |                                 +------------------+    |
     +---------------------------------------------------------+
              |
     curl http://localhost/visits
```

The FastAPI Service is type `LoadBalancer` (accessible from your machine). The Redis Service is type `ClusterIP` (accessible only inside the cluster). FastAPI pods connect to Redis using the DNS name `redis`, which Kubernetes CoreDNS resolves to the Redis Service's ClusterIP.

---

## New API endpoints

Three endpoints use Redis. All existing endpoints continue to work regardless of whether Redis is deployed.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/visits` | GET | Increment and return a shared visit counter. Shows `server` (FastAPI pod) and `redis_host` (DNS name). |
| `/kv/{key}` | GET | Retrieve a value by key. Returns 404 if not found. |
| `/kv/{key}` | POST | Store a value under a key. Body: `{"value": "..."}` |

All three return HTTP 503 with `{"error": "redis unavailable"}` if Redis is not reachable. This means the app degrades gracefully -- core endpoints like `/health`, `/ready`, and `/config` keep working even without Redis.

---

## Manifest walkthrough

### The Secret (`k8s/redis-secret.yaml`)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: redis-secret
  labels:
    app: redis
type: Opaque
stringData:
  REDIS_PASSWORD: "redis-learning-pwd-123"
```

This creates a Kubernetes Secret containing the Redis password. Key points:

- **`stringData`** accepts plain text -- Kubernetes base64-encodes it when storing. This is more readable than manually encoding values in the `data` field.
- **`type: Opaque`** is the generic Secret type for arbitrary key-value pairs.
- The password is intentionally simple -- this is a learning environment. See [Configuration & Secrets](configuration-and-secrets.md) for production secret management.

!!! warning "Secrets in version control"
    In a real project, you would not commit Secret manifests to Git (base64 is not encryption). Use `kubectl create secret`, Sealed Secrets, or an external secret manager instead. We include it here for easy setup.

### The PVC, Deployment, and Service (`k8s/redis.yaml`)

This file contains three resources separated by `---`.

**PersistentVolumeClaim:**

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

- **100Mi** is plenty for a learning environment.
- **ReadWriteOnce** (RWO) means one node can mount it at a time -- fine for a single Redis instance.
- Docker Desktop's default `hostpath` StorageClass dynamically provisions a PV.
- See [Persistent Storage](persistent-storage.md) for a deep dive on PVCs.

**Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  labels:
    app: redis
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          args:
            - redis-server
            - --requirepass
            - $(REDIS_PASSWORD)
            - --appendonly
            - "yes"
          env:
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: redis-secret
                  key: REDIS_PASSWORD
          ports:
            - containerPort: 6379
          volumeMounts:
            - name: redis-data
              mountPath: /data
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          livenessProbe:
            exec:
              command:
                - redis-cli
                - -a
                - $(REDIS_PASSWORD)
                - ping
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            exec:
              command:
                - redis-cli
                - -a
                - $(REDIS_PASSWORD)
                - ping
            initialDelaySeconds: 3
            periodSeconds: 5
      volumes:
        - name: redis-data
          persistentVolumeClaim:
            claimName: redis-pvc
```

Several things are worth noting:

- **`replicas: 1`** -- Redis is a single instance. See [Why Redis is not scaled](#why-redis-is-not-scaled) below for the reasoning.
- **`strategy: Recreate`** -- The old pod is terminated before the new one starts. This prevents two pods from mounting the same PVC simultaneously (RWO only allows one). Compare this with FastAPI's `RollingUpdate` strategy.
- **`--requirepass $(REDIS_PASSWORD)`** -- The password comes from the Secret via environment variable expansion in the container args.
- **`--appendonly yes`** -- Enables the Append Only File (AOF) persistence mode. Every write operation is logged to disk, so data survives pod restarts.
- **Volume mount** -- The PVC is mounted at `/data`, where Redis stores its AOF and RDB files.
- **Probes** -- Both liveness and readiness use `redis-cli ping`, which returns `PONG` if Redis is healthy. Unlike the FastAPI HTTP probes, these use `exec` (run a command inside the container).

**ClusterIP Service:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  labels:
    app: redis
spec:
  type: ClusterIP
  ports:
    - port: 6379
      targetPort: 6379
  selector:
    app: redis
```

- **`type: ClusterIP`** -- Only accessible inside the cluster. There is no reason to expose Redis to the outside world.
- **Service name `redis`** -- This becomes the DNS name that FastAPI uses to connect. When the app reads `REDIS_HOST=redis` from the ConfigMap, Kubernetes DNS resolves `redis` to this Service's ClusterIP.

!!! info "ClusterIP vs LoadBalancer"
    The FastAPI Service is `LoadBalancer` (accessible from `localhost`). The Redis Service is `ClusterIP` (internal only). This is a common pattern: expose the frontend/API to the outside world, keep backing services internal.

### FastAPI deployment changes (`k8s.yaml`)

Two changes connect the FastAPI pods to Redis.

**ConfigMap** -- Two new keys:

```yaml
data:
  APP_NAME: "fastapi-k8s"
  LOG_LEVEL: "info"
  MAX_STRESS_SECONDS: "30"
  REDIS_HOST: "redis"        # DNS name of the Redis Service
  REDIS_PORT: "6379"
```

Because the Deployment uses `envFrom: configMapRef`, these automatically become environment variables in every FastAPI pod. The Python code reads them:

```python
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
```

**Deployment env** -- The password comes from the Secret:

```yaml
env:
  # ... existing Downward API vars ...
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: redis-secret
        key: REDIS_PASSWORD
        optional: true
```

The `optional: true` is important -- it means the FastAPI pods can start even if the Redis Secret does not exist yet. Without it, pods would crash-loop if you deployed FastAPI before Redis.

!!! note "Why not use envFrom for the Secret?"
    We could use `envFrom: secretRef` to inject all Secret keys at once. We use `secretKeyRef` instead for two reasons: (1) it allows `optional: true` so pods start without the Secret, and (2) it makes explicit which Secret key the app depends on.

---

## Step-by-step deployment

### Prerequisites

Make sure the FastAPI app is already deployed with the Redis-aware image:

```bash
# Build the image with Redis support
make docker-build

# Deploy FastAPI (applies ConfigMap + Deployment + Service)
make deploy
make rollout-status
```

### Step 1: Deploy Redis

```bash
make redis-deploy
```

This applies both `k8s/redis-secret.yaml` and `k8s/redis.yaml`. You should see:

```
secret/redis-secret created
persistentvolumeclaim/redis-pvc created
deployment.apps/redis created
service/redis created
```

### Step 2: Verify Redis is running

```bash
make redis-status
```

```
NAME                        READY   STATUS    RESTARTS   AGE
pod/redis-7b44dc6dcf-j7lwq   1/1     Running   0          30s

NAME            TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
service/redis   ClusterIP   10.96.x.x      <none>        6379/TCP   30s

NAME                              STATUS   VOLUME          CAPACITY   ACCESS MODES   STORAGECLASS   AGE
persistentvolumeclaim/redis-pvc   Bound    pvc-xxxxxxxx    100Mi      RWO            hostpath       30s
```

Notice three things:

- The Redis pod is `1/1 Running` (both probes pass).
- The Service has no `EXTERNAL-IP` -- it is ClusterIP, internal only.
- The PVC is `Bound` -- Docker Desktop automatically provisioned a PersistentVolume.

### Step 3: Restart FastAPI pods to pick up the Secret

The FastAPI pods were started before the Redis Secret existed. Even though `optional: true` let them start, they do not have `REDIS_PASSWORD` set. Restart them to inject the Secret:

```bash
make restart
make rollout-status
```

!!! note "Why is a restart needed?"
    Environment variables are set when a container starts. If the Secret did not exist at pod creation time, `REDIS_PASSWORD` is empty. After the Secret is created, existing pods do not automatically pick it up -- you must restart them. This is the same behavior as ConfigMap changes (see [Configuration & Secrets](configuration-and-secrets.md)).

### Step 4: Test the Redis endpoints

```bash
make test-redis
```

This runs a comprehensive test suite:

1. **Visit counter** -- Two calls show the counter incrementing, plus the `redis_host` field showing DNS-based discovery
2. **Shared state** -- Five rapid calls show different `server` hostnames but the same incrementing counter (all pods share one Redis)
3. **Key-value store** -- POST a value, GET it back, overwrite it, verify the update
4. **Missing key** -- GET a nonexistent key returns 404
5. **Existing endpoints** -- `/health` and `/config` still work (Redis is optional)

---

## Exploring the integration

### Shared state across replicas

This is the key insight: five FastAPI pods, all sharing one Redis counter.

```bash
for i in {1..5}; do curl -s http://localhost/visits | python3 -m json.tool; done
```

```json
{
    "visits": 10,
    "server": "fastapi-k8s-5d45df96fb-w9vst",
    "redis_host": "redis"
}
{
    "visits": 11,
    "server": "fastapi-k8s-5d45df96fb-abc12",
    "redis_host": "redis"
}
{
    "visits": 12,
    "server": "fastapi-k8s-5d45df96fb-w9vst",
    "redis_host": "redis"
}
...
```

Each response shows:

- **`visits`** increments across all requests -- the counter is in Redis, not in any pod's memory
- **`server`** varies -- Kubernetes load-balances across FastAPI pods
- **`redis_host`** is always `redis` -- the DNS name from the ConfigMap, resolved by CoreDNS to the Redis Service ClusterIP

Without Redis (or any shared state), each pod would have its own counter that resets on every restart. Redis makes the counter truly shared and persistent.

### DNS-based service discovery

The `redis_host` field in the response shows `redis` -- that is the Kubernetes Service name. Under the hood, CoreDNS resolves it:

```
redis
  -> redis.default.svc.cluster.local
  -> 10.96.x.x (ClusterIP)
  -> 10.1.0.x:6379 (Pod IP)
```

You can verify this from inside the cluster:

```bash
kubectl run dns-test --rm -it --image=busybox --restart=Never -- nslookup redis
```

```
Name:      redis.default.svc.cluster.local
Address 1: 10.96.x.x
```

See [Networking Deep Dive](networking.md) for more on Kubernetes DNS.

### Testing data persistence

Data survives Redis pod restarts because of the PVC:

```bash
# Store a value
curl -X POST -H "Content-Type: application/json" \
  -d '{"value":"survives restart"}' \
  http://localhost/kv/persistence-test

# Delete the Redis pod (Kubernetes recreates it automatically)
kubectl delete pod -l app=redis

# Wait for the new pod to be ready
kubectl wait --for=condition=Ready pod -l app=redis --timeout=60s

# The value is still there
curl http://localhost/kv/persistence-test
# {"key":"persistence-test","value":"survives restart"}
```

This works because:

1. Redis writes data to `/data` (the PVC mount)
2. When the pod is deleted, the PVC is not deleted
3. The new pod mounts the same PVC and reads the existing data

### Verifying existing endpoints are unaffected

All original endpoints continue to work regardless of Redis state:

```bash
curl http://localhost/
curl http://localhost/health
curl http://localhost/config
curl http://localhost/version
curl http://localhost/info
```

The Redis endpoints return 503 if Redis is unavailable, but they do not affect the rest of the API.

---

## Why Redis is not scaled

The FastAPI app runs 5 replicas with a `RollingUpdate` strategy. Redis runs 1 replica with a `Recreate` strategy. This difference is fundamental to understanding stateful vs stateless workloads in Kubernetes.

### Stateless vs stateful

| Aspect | FastAPI (stateless) | Redis (stateful) |
|--------|--------------------|--------------------|
| Replicas | 5 (or more) | 1 |
| Update strategy | RollingUpdate (zero downtime) | Recreate (brief downtime) |
| Storage | None | PVC for data persistence |
| Identity | Interchangeable (any pod can handle any request) | Singular (one instance owns the data) |
| Scaling | Add replicas freely | Requires replication protocol |

### Why you cannot just set `replicas: 2` on Redis

If you set `replicas: 2` on the Redis Deployment, you would get two independent Redis instances, each with its own data. They would not share or replicate data between them. Writes to one instance would not appear on the other. The Kubernetes Service would round-robin requests between them, meaning reads would return inconsistent results.

This is not a Kubernetes limitation -- it is how databases work. A Deployment creates identical, independent replicas. It does not add replication logic between them.

### How Redis is scaled in production

Scaling Redis requires Redis-specific replication protocols:

**Redis Sentinel** -- Automatic failover for a master/replica setup. You run one master (handles writes) and one or more replicas (handle reads, promote to master if the master fails). Sentinel monitors the instances and orchestrates failover. This requires a StatefulSet and careful configuration.

**Redis Cluster** -- Automatic data sharding across multiple master nodes. Each master owns a subset of the key space. Provides both high availability and horizontal scaling for large datasets. More complex to operate than Sentinel.

**Managed Redis** -- Cloud providers offer managed Redis services (AWS ElastiCache, GCP Memorystore, Azure Cache for Redis). These handle replication, failover, and scaling for you.

**Redis Operators** -- Kubernetes operators like [Spotahome Redis Operator](https://github.com/spotahome/redis-operator) or the [OpsTree Redis Operator](https://github.com/OpsTree/redis-operator) automate Redis Sentinel and Cluster deployments in Kubernetes using Custom Resource Definitions.

!!! info "For this project"
    A single Redis instance with a PVC is the right choice for learning. It demonstrates Secrets, PVCs, ClusterIP Services, and service discovery without the complexity of replication. The brief downtime during Recreate updates is acceptable in a learning environment.

### The Recreate strategy explained

The FastAPI Deployment uses `RollingUpdate` -- new pods start before old ones stop, ensuring zero downtime. The Redis Deployment uses `Recreate` -- all old pods are terminated before new ones start.

Why `Recreate` for Redis?

1. **PVC access mode** -- The PVC is `ReadWriteOnce` (RWO), meaning only one node can mount it at a time. With `RollingUpdate`, the new pod would try to mount the PVC while the old pod still has it, causing a scheduling failure.
2. **Data integrity** -- Two Redis instances writing to the same data files would corrupt the data. `Recreate` ensures only one instance exists at any time.
3. **Single replica** -- With `replicas: 1`, there is no benefit to a rolling update -- you would have zero pods during the transition either way.

---

## Cleanup

### Remove Redis but keep data

```bash
make redis-undeploy
```

This deletes the Redis Deployment and Service but keeps the PVC and Secret. If you redeploy later, the data is still there.

### Full cleanup

```bash
make redis-clean
```

This deletes everything: Deployment, Service, PVC, and Secret. All Redis data is permanently deleted.

---

## Make targets reference

| Target | Description |
|--------|-------------|
| `make redis-deploy` | Apply Secret + PVC + Deployment + Service |
| `make redis-status` | Show Redis pods, service, and PVC |
| `make redis-logs` | View Redis pod logs |
| `make redis-undeploy` | Remove Deployment and Service (keeps PVC and Secret) |
| `make redis-clean` | Full cleanup (Deployment + PVC + Secret) |
| `make test-redis` | Test all Redis endpoints |

---

## Summary

| Concept | How it is used |
|---------|---------------|
| Secret | Redis password stored in `redis-secret`, injected into both Redis and FastAPI pods |
| PVC | 100Mi volume at `/data` for Redis AOF persistence |
| ClusterIP Service | Internal-only access to Redis on port 6379 |
| DNS discovery | FastAPI connects to Redis using the Service name `redis` |
| ConfigMap | `REDIS_HOST` and `REDIS_PORT` added to the FastAPI ConfigMap |
| `optional: true` | FastAPI starts even if the Redis Secret is not yet deployed |
| Recreate strategy | Ensures only one Redis instance accesses the PVC at a time |
| Shared state | Visit counter demonstrates all FastAPI replicas sharing one Redis |

This integration ties together Secrets, PersistentVolumeClaims, ClusterIP Services, and DNS-based service discovery into a practical multi-service deployment -- the foundation for any real Kubernetes application.
