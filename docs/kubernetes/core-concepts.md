# Core Concepts

This page covers the fundamental building blocks of Kubernetes. Every concept here
is something you will encounter when deploying and operating applications -- including
our `fastapi-k8s` project running on Docker Desktop.

---

## Cluster

A Kubernetes **cluster** is the top-level construct: a set of machines that work
together to run containerized workloads. Every cluster has two distinct layers.

### Control Plane

The control plane is the brain of the cluster. It makes all scheduling decisions,
monitors cluster state, and responds to events (such as a pod crashing). Its key
components are:

| Component            | Role                                                                 |
|----------------------|----------------------------------------------------------------------|
| **kube-apiserver**   | Front door to the cluster. Every `kubectl` command talks to this.    |
| **etcd**             | Distributed key-value store holding all cluster state and config.    |
| **kube-scheduler**   | Decides which node a new pod should run on based on resource needs.  |
| **kube-controller-manager** | Runs controllers (Deployment, ReplicaSet, Node, etc.) that reconcile desired state with actual state. |
| **cloud-controller-manager** | Integrates with cloud provider APIs (not relevant for Docker Desktop). |

### Worker Nodes

Worker nodes are where your application pods actually run. Each worker node
communicates with the control plane, reports its health, and executes the workloads
that the scheduler assigns to it.

### Single-Node vs Multi-Node

In production, you typically have multiple worker nodes for redundancy and capacity.
With **Docker Desktop**, everything runs on a single node -- the control plane and
the worker are the same machine. This is perfect for learning and local development
but obviously not suitable for production.

```
Single-node cluster (Docker Desktop)            Multi-node cluster (production)
+-------------------------------+               +------------------+
|  Control Plane + Worker Node  |               |  Control Plane   |
|                               |               +------------------+
|  API Server, etcd, Scheduler  |                      |
|  kubelet, kube-proxy          |            +---------+---------+
|  Pods: fastapi-k8s-xxxxx     |            |         |         |
+-------------------------------+         Node 1   Node 2   Node 3
                                          (pods)   (pods)   (pods)
```

!!! info "Docker Desktop Kubernetes"
    When you enable Kubernetes in Docker Desktop settings, it provisions a
    single-node cluster using the same Docker engine already on your machine.
    Images built with `docker build` are immediately available to Kubernetes
    without pushing to a registry -- that is why our Deployment uses
    `imagePullPolicy: Never`.

---

## Node

A **node** is a single machine (physical server, VM, or -- in our case -- your
laptop via Docker Desktop) that is part of the cluster. Each node runs three
essential components.

### kubelet

The kubelet is an agent running on every node. It is responsible for:

- Receiving pod specifications (PodSpecs) from the API server
- Ensuring that the containers described in those PodSpecs are running and healthy
- Reporting the node's status and each pod's status back to the control plane
- Executing liveness and readiness probes (like the `/health` and `/ready`
  endpoints in our FastAPI app)

If the kubelet detects that a container has failed its liveness probe, it restarts
the container. This is how our `/crash` endpoint triggers a pod restart -- the
process exits, the kubelet notices, and it starts a new container.

### kube-proxy

kube-proxy runs on every node and maintains network rules that allow communication
to and from pods. It implements the Kubernetes **Service** abstraction by:

- Programming iptables or IPVS rules on the node
- Enabling ClusterIP, NodePort, and LoadBalancer service types
- Load-balancing traffic across the set of pods backing a Service

When you `curl http://localhost/` and it reaches one of our 5 FastAPI pods, that
routing is handled by kube-proxy rules on the node.

### Container Runtime

The container runtime is the software that actually pulls images, creates containers,
and manages their lifecycle. Kubernetes supports any runtime that implements the
**Container Runtime Interface (CRI)**. Common runtimes include:

- **containerd** -- the default in most Kubernetes distributions (including Docker Desktop)
- **CRI-O** -- lightweight runtime popular in OpenShift

Docker Desktop uses containerd under the hood. When our Deployment creates a pod, the
kubelet instructs containerd to start a container from the `fastapi-k8s:latest` image.

```
+-------------------------- Node (docker-desktop) --------------------------+
|                                                                           |
|   kubelet                kube-proxy              containerd               |
|   - watches API server   - manages iptables      - pulls images           |
|   - manages pod          - routes Service         - starts/stops           |
|     lifecycle              traffic                  containers             |
|                                                                           |
|   +------------+  +------------+  +------------+  +------------+          |
|   |   Pod 1    |  |   Pod 2    |  |   Pod 3    |  |   Pod 4    |   ...    |
|   | fastapi-k8s|  | fastapi-k8s|  | fastapi-k8s|  | fastapi-k8s|          |
|   +------------+  +------------+  +------------+  +------------+          |
+--------------------------------------------------------------------------+
```

---

## Pod

A **pod** is the smallest deployable unit in Kubernetes -- not a container, but a
wrapper around one or more containers. Understanding pods is essential to
understanding everything else in Kubernetes.

### Why Pods, Not Containers?

Kubernetes does not manage containers directly. Instead, it manages pods because:

1. **Shared context** -- Containers in a pod share a network namespace (same IP,
   same `localhost`), can share volumes, and are co-scheduled on the same node.
2. **Atomic scheduling** -- If two containers must always run together (e.g., an app
   and its log shipper), placing them in one pod guarantees they land on the same node.
3. **Abstraction layer** -- Pods decouple Kubernetes from specific container runtimes.

In our project, each pod runs a single container (`fastapi-k8s`), which is the most
common pattern.

### Pod Lifecycle

Every pod passes through a series of phases:

```
                  +---> Running ---> Succeeded
                  |         |
 Pending ---------+         +-----> Failed
                  |
                  +---> Failed (e.g., image pull error)
```

| Phase       | Description                                                                        |
|-------------|------------------------------------------------------------------------------------|
| **Pending** | The pod has been accepted by the cluster but one or more containers are not yet running. This includes time spent scheduling the pod to a node and pulling images. |
| **Running** | The pod has been bound to a node, all containers have been created, and at least one is running or starting/restarting. |
| **Succeeded** | All containers in the pod terminated successfully (exit code 0) and will not be restarted. Common for Jobs. |
| **Failed**  | All containers have terminated and at least one exited with a non-zero exit code.   |

When you call `POST /crash` on our FastAPI app, the container exits with code 1.
The pod phase briefly becomes Failed, but because the pod is managed by a Deployment
(with a default `restartPolicy: Always`), the kubelet restarts the container and the
pod returns to Running.

### Multi-Container Pods

While single-container pods are the norm, there are well-established patterns for
running multiple containers in one pod:

**Sidecar Pattern**

A sidecar container runs alongside your main application container and provides
supporting functionality -- log collection, metrics export, service mesh proxy, etc.

```
+------------------------ Pod -------------------------+
|                                                      |
|  +------------------+    +---------------------+     |
|  | Main Container   |    | Sidecar Container   |     |
|  | fastapi-k8s      |    | (e.g., log shipper) |     |
|  | port: 8000       |    |                     |     |
|  +------------------+    +---------------------+     |
|                                                      |
|  Shared: network (localhost), volumes, lifecycle     |
|  Pod IP: 10.1.0.15                                   |
+------------------------------------------------------+
```

The sidecar can read logs from a shared volume, or scrape the `/metrics` endpoint
via `localhost:8000` without any network hops.

**Init Containers**

Init containers run **before** the main containers start and must complete
successfully. They are used for setup tasks:

- Waiting for a database to become available
- Running database migrations
- Cloning configuration from a git repository
- Generating config files or certificates

Init containers run sequentially -- each one must finish before the next starts.
Only after all init containers succeed do the regular containers start.

```
Pod startup sequence:
  [init-container-1] ---> [init-container-2] ---> [main-container] + [sidecar]
        (done)                  (done)               (running)
```

### Shared Networking and Storage Within a Pod

All containers in a pod share:

- **Network namespace** -- They all have the same IP address. Container A can reach
  Container B on `localhost:<port>`. They must avoid port conflicts.
- **Volumes** -- Any volume mounted in the pod spec can be accessed by multiple
  containers, enabling file-based communication.
- **IPC namespace** -- Containers can communicate via shared memory if needed.

!!! note "Pod IP is ephemeral"
    Every pod gets its own IP address, but that address changes whenever the pod is
    recreated. This is why you never hardcode pod IPs -- you use a Service instead.

---

## ReplicaSet

A **ReplicaSet** ensures that a specified number of identical pod replicas are
running at any given time. If a pod goes down, the ReplicaSet controller creates a
replacement. If there are too many pods, it terminates the extras.

### How It Works

A ReplicaSet has three essential fields:

- **replicas** -- the desired number of pods
- **selector** -- labels used to identify the pods it manages
- **template** -- the pod specification for creating new pods

### ReplicaSet vs Deployment

In practice, you **almost never create ReplicaSets directly**. Instead, you create
a Deployment, which creates and manages ReplicaSets for you. The key difference:

| Aspect           | ReplicaSet                           | Deployment                              |
|------------------|--------------------------------------|-----------------------------------------|
| Rolling updates  | No                                   | Yes -- creates new ReplicaSet, scales old one down |
| Rollback         | No built-in mechanism                | Yes -- `kubectl rollout undo`           |
| Revision history | No                                   | Yes -- tracks revisions                 |
| Direct creation  | Possible but discouraged             | The standard approach                   |

Think of a ReplicaSet as the "engine" and a Deployment as the "car." You interact
with the car; the engine does its job under the hood.

!!! warning "Don't create ReplicaSets directly"
    If you see a tutorial telling you to create a ReplicaSet by hand, it is almost
    certainly teaching the concept rather than a real-world practice. Always use a
    Deployment.

---

## Deployment

A **Deployment** is the standard way to run stateless applications on Kubernetes.
It manages ReplicaSets, which in turn manage pods.

Our `fastapi-k8s` project uses a Deployment with 5 replicas:

```yaml
# From k8s.yaml
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
```

### How Deployments Manage ReplicaSets

When you create or update a Deployment, the Deployment controller creates a new
ReplicaSet. The ReplicaSet then creates the pods.

```
+--------------- Deployment: fastapi-k8s ----------------+
|  replicas: 5                                           |
|  strategy: RollingUpdate                               |
|                                                        |
|  +--- ReplicaSet (current, revision 3) -------------+  |
|  |  fastapi-k8s-7d9f8b6c4d                          |  |
|  |  Pod 1   Pod 2   Pod 3   Pod 4   Pod 5           |  |
|  +---------------------------------------------------+  |
|                                                        |
|  +--- ReplicaSet (previous, revision 2, 0 pods) ---+  |
|  |  fastapi-k8s-5a8e7c3b1f   (scaled to 0)         |  |
|  +---------------------------------------------------+  |
+--------------------------------------------------------+
```

### Rolling Updates

Our Deployment uses `RollingUpdate` with `maxSurge: 1` and `maxUnavailable: 0`.
This means:

- At most 1 extra pod can exist during the update (5 + 1 = 6 total)
- Zero pods can be unavailable (all 5 must be running before old ones are removed)
- The result is a zero-downtime deployment

When you rebuild the Docker image and run `make deploy`, Kubernetes will:

1. Create a new ReplicaSet with the updated pod template
2. Scale the new ReplicaSet up by 1 pod
3. Wait for that pod to pass its readiness probe (`GET /ready`)
4. Scale the old ReplicaSet down by 1 pod
5. Repeat until all 5 pods are running the new version

### Rollout History and Rollback

Kubernetes keeps a history of Deployment revisions. You can inspect and roll back:

```bash
# See rollout history
kubectl rollout history deployment/fastapi-k8s

# Roll back to the previous revision
kubectl rollout undo deployment/fastapi-k8s

# Roll back to a specific revision
kubectl rollout undo deployment/fastapi-k8s --to-revision=2
```

!!! tip "Trigger a rolling restart"
    If you just need to restart all pods without changing the image, use:
    `make restart` (which runs `kubectl rollout restart deployment/fastapi-k8s`).
    This creates a new ReplicaSet, effectively cycling all pods.

---

## StatefulSet

A **StatefulSet** is like a Deployment but for workloads that need **stable,
persistent identity**. Each pod in a StatefulSet gets:

- A **stable hostname** -- `pod-0`, `pod-1`, `pod-2` (ordinal index, not random hash)
- **Stable persistent storage** -- each pod gets its own PersistentVolumeClaim that
  survives pod restarts
- **Ordered deployment and scaling** -- pods are created sequentially (0, then 1, then 2)
  and terminated in reverse order

### When to Use StatefulSet vs Deployment

| Use Case                  | Resource     | Why                                             |
|---------------------------|--------------|-------------------------------------------------|
| Web app (FastAPI)         | Deployment   | Stateless, any pod can handle any request        |
| PostgreSQL / MySQL        | StatefulSet  | Needs stable identity for replication, persistent data |
| Redis Cluster             | StatefulSet  | Nodes need stable hostnames to form a cluster    |
| Kafka / ZooKeeper         | StatefulSet  | Ordered startup, stable network IDs              |
| Background worker         | Deployment   | Stateless, work is pulled from a queue           |

Our `fastapi-k8s` app is stateless -- it does not store data locally and any pod
can handle any request. A Deployment is the correct choice. If we added a PostgreSQL
database, we would use a StatefulSet for that.

```
StatefulSet: postgres
  postgres-0  -->  PVC: data-postgres-0  (10Gi)
  postgres-1  -->  PVC: data-postgres-1  (10Gi)
  postgres-2  -->  PVC: data-postgres-2  (10Gi)

Each pod keeps its storage even if rescheduled to a different node.
```

!!! note "StatefulSets require a Headless Service"
    A headless Service (with `clusterIP: None`) is required so each pod gets a
    stable DNS name like `postgres-0.postgres.default.svc.cluster.local`.

---

## DaemonSet

A **DaemonSet** ensures that **exactly one copy of a pod runs on every node** (or a
selected subset of nodes). When a new node joins the cluster, the DaemonSet
automatically schedules a pod on it. When a node is removed, the pod is garbage
collected.

### Common Use Cases

- **Log collectors** -- Fluentd or Filebeat running on every node to ship logs
- **Monitoring agents** -- Node Exporter or Datadog agent collecting node-level metrics
- **Network plugins** -- CNI plugins like Calico or Cilium
- **Storage daemons** -- Ceph or GlusterFS agents

```
3-node cluster with a logging DaemonSet:

  Node 1                Node 2                Node 3
  +-------------+       +-------------+       +-------------+
  | fluentd pod |       | fluentd pod |       | fluentd pod |
  | app pod     |       | app pod     |       | app pod     |
  | app pod     |       | app pod     |       |             |
  +-------------+       +-------------+       +-------------+

One fluentd per node, regardless of how many app pods exist.
```

On our Docker Desktop single-node cluster, a DaemonSet would run exactly one pod
(since there is only one node). Kubernetes system components like `kube-proxy` are
themselves deployed as a DaemonSet in the `kube-system` namespace.

---

## Job and CronJob

Not every workload is a long-running server. Kubernetes provides **Jobs** and
**CronJobs** for batch and scheduled work.

### Job

A Job creates one or more pods and ensures that a specified number of them
successfully terminate. Unlike a Deployment, a Job does not restart pods that
exit successfully -- the work is done.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
spec:
  template:
    spec:
      containers:
        - name: migrate
          image: myapp:latest
          command: ["python", "manage.py", "migrate"]
      restartPolicy: Never
  backoffLimit: 3    # retry up to 3 times on failure
```

Key behaviors:

- **Completions** -- how many pods must succeed (default: 1)
- **Parallelism** -- how many pods can run concurrently (default: 1)
- **backoffLimit** -- maximum retries before marking the Job as failed
- Pods from completed Jobs are not deleted automatically (so you can inspect logs),
  but the `ttlSecondsAfterFinished` field can auto-clean them

### CronJob

A CronJob creates Jobs on a schedule, using standard cron syntax:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-cleanup
spec:
  schedule: "0 2 * * *"    # Every day at 2:00 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: cleanup
              image: myapp:latest
              command: ["python", "cleanup.py"]
          restartPolicy: Never
```

Use cases include database backups, report generation, cache invalidation, and
cleanup scripts.

!!! tip "Job vs Deployment for one-off tasks"
    If you need to run a database migration before deploying your app, use a Job
    (or an init container). Do not use a Deployment for work that should run once
    and stop.

---

## Service

Pods are ephemeral -- they come and go, and their IP addresses change each time.
A **Service** provides a stable network endpoint that routes traffic to the right
set of pods, regardless of pod restarts or scaling events.

Our project defines a LoadBalancer Service:

```yaml
# From k8s.yaml
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

### Service Types at a Glance

| Type             | Accessible From        | How It Works                                              |
|------------------|------------------------|-----------------------------------------------------------|
| **ClusterIP**    | Inside the cluster only | Default type. Gets an internal IP. Other pods reach it via `fastapi-k8s.default.svc.cluster.local`. |
| **NodePort**     | Outside via node IP + port | Opens a static port (30000-32767) on every node. Traffic on that port is forwarded to the Service. |
| **LoadBalancer** | Outside via external IP | Provisions an external load balancer. On Docker Desktop, this maps to `localhost`. |
| **Headless**     | Inside the cluster     | No ClusterIP (`clusterIP: None`). DNS returns individual pod IPs. Used with StatefulSets. |

Our Service uses `LoadBalancer`, which is why `curl http://localhost/` works --
Docker Desktop maps the LoadBalancer's external IP to `localhost`. The Service
matches pods using the selector `app: fastapi-k8s` and distributes incoming
traffic on port 80 to container port 8000 across all 5 pods.

!!! info "Detailed networking coverage"
    Service types, DNS resolution, Ingress, and network policies are covered in
    depth on the [Networking](networking.md) page.

---

## Namespace

A **namespace** is a virtual cluster within your physical cluster. It provides a
scope for names -- two resources can have the same name as long as they live in
different namespaces.

### Default Namespaces

Every Kubernetes cluster comes with these namespaces out of the box:

| Namespace        | Purpose                                                          |
|------------------|------------------------------------------------------------------|
| **default**      | Where resources go when you do not specify a namespace. Our `fastapi-k8s` Deployment lives here. |
| **kube-system**  | Kubernetes system components -- API server, scheduler, CoreDNS, kube-proxy, etc. |
| **kube-public**  | Readable by all users (including unauthenticated). Rarely used in practice. |
| **kube-node-lease** | Holds Lease objects for node heartbeats. Improves performance of node health detection. |

### When to Use Namespaces

- **Team isolation** -- Give each team its own namespace (`team-backend`, `team-ml`)
- **Environment separation** -- `staging` and `production` in the same cluster
  (though separate clusters are often preferred for production)
- **Resource quotas** -- Apply CPU/memory limits per namespace
- **RBAC** -- Control who can access what on a per-namespace basis

For a local learning project like ours, the `default` namespace is fine. You can
verify where our resources live:

```bash
kubectl get all -n default -l app=fastapi-k8s
```

!!! warning "Namespaces are not a security boundary"
    Namespaces provide soft isolation -- they separate names and allow resource
    quotas, but pods in different namespaces can still communicate by default.
    For true network isolation, you need Network Policies.

---

## Labels and Selectors

**Labels** are key-value pairs attached to Kubernetes objects. **Selectors** are
queries that match objects by their labels. Together, they form the primary
mechanism for grouping, filtering, and connecting resources.

### How Labels Work

Every object in our `fastapi-k8s` project carries the label `app: fastapi-k8s`:

```yaml
metadata:
  labels:
    app: fastapi-k8s
```

This label appears on the Deployment, the pods, the Service, and the ConfigMap.
It is the glue that connects everything:

```
Deployment (app: fastapi-k8s)
  |
  +---> creates pods with label: app: fastapi-k8s
                                        ^
                                        |
Service (selector: app: fastapi-k8s) ---+
  Routes traffic to all pods matching this label
```

### Selector Types

**Equality-based selectors** match exact key-value pairs:

```yaml
selector:
  matchLabels:
    app: fastapi-k8s
```

**Set-based selectors** support more complex logic:

```yaml
selector:
  matchExpressions:
    - key: environment
      operator: In
      values: [production, staging]
    - key: tier
      operator: NotIn
      values: [frontend]
```

### Using Labels with kubectl

Labels are powerful for operational tasks:

```bash
# List only our project's pods
kubectl get pods -l app=fastapi-k8s

# List pods matching multiple labels
kubectl get pods -l app=fastapi-k8s,version=v2

# View logs from all our pods at once
kubectl logs -l app=fastapi-k8s

# Delete all resources with our label
kubectl delete all -l app=fastapi-k8s
```

Our `make status` command uses `-l app=fastapi-k8s` to filter results to just our
project's resources.

### Recommended Labels

Kubernetes defines a set of standard labels under the `app.kubernetes.io` prefix.
These are optional but improve interoperability with tooling (Helm, ArgoCD, etc.):

| Label                           | Example Value      | Purpose                        |
|---------------------------------|--------------------|--------------------------------|
| `app.kubernetes.io/name`        | `fastapi-k8s`      | The name of the application    |
| `app.kubernetes.io/version`     | `1.0.0`            | The version of the app         |
| `app.kubernetes.io/component`   | `api`              | The component within the arch  |
| `app.kubernetes.io/part-of`     | `fastapi-k8s`      | The higher-level application   |
| `app.kubernetes.io/managed-by`  | `kubectl`          | The tool managing the resource |

Our project uses the simpler `app: fastapi-k8s` label, which is perfectly valid for
a single-application project.

---

## Annotations

**Annotations** are key-value pairs attached to objects, similar to labels, but they
serve a fundamentally different purpose.

### Labels vs Annotations

| Aspect       | Labels                                | Annotations                             |
|--------------|---------------------------------------|-----------------------------------------|
| Purpose      | Identify and select objects           | Attach non-identifying metadata         |
| Queryable    | Yes -- used in selectors and filters  | No -- cannot be used in selectors       |
| Size limit   | 63 characters per value               | Much larger (256KB total per object)     |
| Used by      | Kubernetes internals, Services, etc.  | Tools, humans, automation               |

### Common Annotation Use Cases

**Build and deployment information:**

```yaml
metadata:
  annotations:
    app.example.com/git-commit: "a1b2c3d"
    app.example.com/build-timestamp: "2025-01-15T10:30:00Z"
    app.example.com/ci-pipeline: "https://ci.example.com/builds/1234"
```

**Tool-specific configuration:**

```yaml
metadata:
  annotations:
    # Prometheus scraping
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"

    # Ingress controller settings
    nginx.ingress.kubernetes.io/rewrite-target: /

    # Deployment change cause (auto-set by kubectl)
    kubernetes.io/change-cause: "image update to v1.1.0"
```

**Human-readable descriptions:**

```yaml
metadata:
  annotations:
    description: "FastAPI demo app for learning Kubernetes concepts"
    team: "platform-engineering"
    oncall: "https://pagerduty.example.com/schedules/ABC"
```

!!! tip "When to use labels vs annotations"
    If you need to **select** or **filter** objects by a value, use a label.
    If you need to **store metadata** that tools or humans will read, use an
    annotation. When in doubt, start with an annotation -- you can always promote
    it to a label later.

---

## Putting It All Together

Here is how all the core concepts connect in our `fastapi-k8s` project:

```
+------ Cluster (Docker Desktop, single node) ------+
|                                                    |
|  Namespace: default                                |
|                                                    |
|  ConfigMap: fastapi-config                         |
|    APP_NAME: "fastapi-k8s"                         |
|    LOG_LEVEL: "info"                               |
|    MAX_STRESS_SECONDS: "30"                        |
|                                                    |
|  Deployment: fastapi-k8s (replicas: 5)             |
|    |                                               |
|    +---> ReplicaSet: fastapi-k8s-xxxxxxxxx         |
|           |                                        |
|           +---> Pod 1 (app: fastapi-k8s)           |
|           +---> Pod 2 (app: fastapi-k8s)           |
|           +---> Pod 3 (app: fastapi-k8s)           |
|           +---> Pod 4 (app: fastapi-k8s)           |
|           +---> Pod 5 (app: fastapi-k8s)           |
|                   |                                |
|                   Each pod runs one container:     |
|                   fastapi-k8s:latest on port 8000  |
|                                                    |
|  Service: fastapi-k8s (LoadBalancer)               |
|    port 80 -> targetPort 8000                      |
|    selector: app: fastapi-k8s                      |
|    Matches all 5 pods, load-balances traffic       |
|                                                    |
+----------------------------------------------------+
```

The Deployment declares the desired state ("5 pods running this image"). Kubernetes
continuously reconciles actual state with desired state -- if a pod crashes, the
ReplicaSet creates a new one. The Service provides a stable entry point regardless
of which pods exist at any moment.

This declarative model -- where you describe *what* you want rather than *how* to
achieve it -- is the central philosophy of Kubernetes.
