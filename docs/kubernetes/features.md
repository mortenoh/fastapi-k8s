# Kubernetes Features Overview

Kubernetes is a rich platform with many features beyond running containers. This page provides a broad map of what Kubernetes can do -- from workload management and networking to security, scaling, and extensibility. For features covered in detail elsewhere in this guide, you will find cross-references to those pages. For features not covered elsewhere, this page provides enough context to understand what they are and when you would use them.

---

## Workload Management

Kubernetes supports several workload types, each designed for a different pattern.

### Deployments

A **Deployment** is the most common way to run stateless applications. You declare the desired number of replicas, the container image, and the update strategy. Kubernetes creates a ReplicaSet under the hood, which in turn creates the pods. Deployments handle rolling updates, rollbacks, and scaling.

This is what our FastAPI project uses. When you run `make deploy`, Kubernetes applies a Deployment that manages five replicas of the app.

See [Your First Deployment](first-deployment.md) for a line-by-line walkthrough of the YAML, and [Rolling Updates](rolling-updates.md) for how Deployments handle version changes with zero downtime.

### ReplicaSets

A **ReplicaSet** ensures that a specified number of pod replicas are running at any given time. Deployments create and manage ReplicaSets automatically -- you almost never create one directly. During a rolling update, the Deployment creates a new ReplicaSet (with the new version) and scales down the old one.

You can see ReplicaSets in your cluster with:

```bash
kubectl get replicasets -l app=fastapi-k8s
```

!!! note
    If you find yourself writing a ReplicaSet manifest directly, you probably want a Deployment instead. Deployments add rolling update logic, rollback history, and update strategies on top of ReplicaSets.

### StatefulSets

A **StatefulSet** is for applications that need **stable identities** and **persistent storage** -- databases, message queues, distributed systems like ZooKeeper or Kafka. Unlike Deployment pods (which get random names like `fastapi-k8s-7f8b9c6d4-2nxkl`), StatefulSet pods get sequential, predictable names: `postgres-0`, `postgres-1`, `postgres-2`.

Each pod in a StatefulSet can have its own PersistentVolumeClaim, so data follows the pod identity even across restarts. Pods are created and deleted in order (0, 1, 2 on scale-up; 2, 1, 0 on scale-down).

Use StatefulSets when your application requires:

- Stable network hostnames (e.g., `postgres-0.postgres-headless.default.svc.cluster.local`)
- Persistent storage per pod
- Ordered startup and shutdown

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres-headless
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
```

### DaemonSets

A **DaemonSet** runs exactly **one pod on every node** in the cluster (or a subset of nodes). When a new node joins the cluster, the DaemonSet automatically schedules a pod on it. When a node is removed, the pod is garbage collected.

Use DaemonSets for node-level services:

- Log collectors (Fluentd, Fluent Bit)
- Monitoring agents (Prometheus Node Exporter, Datadog agent)
- Network plugins (Calico, Cilium)
- Storage daemons

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      containers:
        - name: node-exporter
          image: prom/node-exporter:v1.7.0
          ports:
            - containerPort: 9100
```

!!! info
    On a Docker Desktop single-node cluster, a DaemonSet behaves identically to a Deployment with `replicas: 1`. The difference becomes apparent in multi-node clusters where the DaemonSet guarantees one pod per node.

### Jobs

A **Job** creates one or more pods and ensures they run to completion. Unlike Deployments (which keep pods running indefinitely), a Job's pods exit after finishing their work. Kubernetes tracks how many completions have succeeded and retries on failure.

Use Jobs for:

- Database migrations
- Batch processing (image resizing, data import)
- One-off administrative tasks

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
spec:
  backoffLimit: 3          # retry up to 3 times on failure
  activeDeadlineSeconds: 300  # timeout after 5 minutes
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: myapp:latest
          command: ["python", "manage.py", "migrate"]
```

For parallel processing, set `parallelism` and `completions`:

```yaml
spec:
  completions: 10    # total tasks to complete
  parallelism: 3     # run 3 pods at a time
```

### CronJobs

A **CronJob** creates Jobs on a schedule, using standard cron syntax. Kubernetes creates a new Job object at each scheduled time, and the Job creates the pod(s) to do the work.

Use CronJobs for:

- Database backups
- Report generation
- Cache cleanup
- Certificate renewal checks

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
spec:
  schedule: "0 2 * * *"            # 2:00 AM every day
  concurrencyPolicy: Forbid         # don't start a new job if the previous is still running
  successfulJobsHistoryLimit: 3     # keep last 3 successful job records
  failedJobsHistoryLimit: 3         # keep last 3 failed job records
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: myapp:latest
              command: ["python", "backup.py"]
```

!!! tip
    Use `concurrencyPolicy: Forbid` for jobs that should not overlap (like database backups). Use `Replace` to cancel the running job and start a new one. The default `Allow` lets jobs run concurrently.

---

## Networking

Kubernetes provides a flat network model -- every pod gets its own IP address, and any pod can reach any other pod without NAT.

### Services

A **Service** provides a stable network endpoint for a set of pods. Pods are ephemeral (they come and go), but the Service IP and DNS name remain constant. Kubernetes offers four Service types:

| Type | Accessible from | Use case |
|------|----------------|----------|
| **ClusterIP** | Inside the cluster only | Internal communication (databases, caches) |
| **NodePort** | `<NodeIP>:<port>` | Development, simple external access |
| **LoadBalancer** | External IP/hostname | Production external access |
| **ExternalName** | DNS CNAME | Alias for external services |

Our project uses a LoadBalancer Service, which maps to `localhost` on Docker Desktop.

See [Networking Deep Dive](networking.md) for a detailed walkthrough of each Service type with examples.

### Ingress

An **Ingress** provides HTTP and HTTPS routing to Services within the cluster. Instead of exposing each Service individually with a LoadBalancer (which would require one external IP per service), an Ingress lets you route traffic based on hostname or URL path through a single entry point.

Use Ingress when you have multiple HTTP services and want:

- Path-based routing (`/api` goes to one service, `/web` goes to another)
- Host-based routing (`api.example.com` vs `app.example.com`)
- TLS termination (HTTPS at the edge)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - myapp.example.com
      secretName: myapp-tls
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

!!! note
    An Ingress resource by itself does nothing -- you need an **Ingress Controller** (like NGINX Ingress Controller, Traefik, or HAProxy) installed in the cluster to process the Ingress rules.

### Network Policies

**Network Policies** act as a pod-level firewall. By default, all pods in a Kubernetes cluster can communicate with all other pods. Network Policies let you restrict which pods can talk to which.

Use Network Policies to:

- Isolate sensitive workloads (databases should only accept connections from app pods)
- Implement a default-deny policy and explicitly allow required traffic
- Meet compliance requirements for network segmentation

```yaml
# Default deny all ingress traffic in a namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: production
spec:
  podSelector: {}       # applies to all pods in the namespace
  policyTypes:
    - Ingress

---
# Allow traffic only from app pods to the database
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-app-to-db
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: postgres
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: fastapi-k8s
      ports:
        - port: 5432
```

!!! info
    Network Policies require a CNI plugin that supports them (Calico, Cilium, Weave). The default Docker Desktop networking does not enforce Network Policies -- the resources will be created but not enforced. For local testing, consider installing Calico.

### DNS

Kubernetes runs **CoreDNS** as a cluster add-on, providing automatic DNS-based service discovery. Every Service gets a DNS name following the pattern `<service-name>.<namespace>.svc.cluster.local`. Pods can reach services using just the service name within the same namespace.

For example, our FastAPI app could reach a database service at:

```
postgres.default.svc.cluster.local   # fully qualified
postgres.default                      # with namespace
postgres                              # within the same namespace
```

This is how our Service works behind the scenes -- pods don't need to know IP addresses, they just use DNS names.

### Service Mesh

A **service mesh** adds a layer of infrastructure between your services to handle cross-cutting concerns: traffic management, security (mutual TLS), and observability. It works by injecting a sidecar proxy container into each pod that intercepts all network traffic.

Popular service meshes:

- **Istio** -- Full-featured, widely adopted, includes traffic management, security, and observability
- **Linkerd** -- Lightweight, simpler to operate, focuses on reliability and observability
- **Cilium Service Mesh** -- eBPF-based, no sidecar required, high performance

Use a service mesh when you need:

- Mutual TLS between all services without changing application code
- Advanced traffic routing (canary releases, traffic mirroring, fault injection)
- Distributed tracing and detailed metrics between services

!!! tip
    A service mesh adds significant complexity. For small deployments or single-service applications like this project, it is overkill. Consider it when you have many services communicating over the network and need consistent security and observability policies.

---

## Configuration and Storage

Kubernetes separates configuration from container images so you can run the same image in different environments.

### ConfigMaps

A **ConfigMap** stores non-sensitive configuration as key-value pairs. You can inject them as environment variables or mount them as files inside containers. This lets you change configuration without rebuilding your Docker image.

Our project uses a ConfigMap to set `APP_NAME`, `LOG_LEVEL`, and `MAX_STRESS_SECONDS`.

See [Configuration & Secrets](configuration-and-secrets.md) for a hands-on walkthrough including live config updates.

### Secrets

A **Secret** is similar to a ConfigMap but intended for sensitive data -- passwords, API keys, TLS certificates. Secrets are base64-encoded (not encrypted by default) and can be injected as environment variables or mounted as files.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque
data:
  username: cG9zdGdyZXM=        # echo -n "postgres" | base64
  password: c3VwZXJzZWNyZXQ=    # echo -n "supersecret" | base64
```

Reference in a pod:

```yaml
containers:
  - name: app
    env:
      - name: DB_USER
        valueFrom:
          secretKeyRef:
            name: db-credentials
            key: username
      - name: DB_PASS
        valueFrom:
          secretKeyRef:
            name: db-credentials
            key: password
```

See [Configuration & Secrets](configuration-and-secrets.md) for more detail on Secrets, including how to create them with `kubectl`.

!!! warning
    Base64 is encoding, not encryption. Anyone with access to the cluster can decode Secrets. For production, enable encryption at rest and consider external secret managers (see the Security section below).

### PersistentVolumes and PersistentVolumeClaims

**PersistentVolumes (PVs)** represent a piece of storage in the cluster. **PersistentVolumeClaims (PVCs)** are requests for storage by pods. This two-layer abstraction separates storage provisioning (admin concern) from storage consumption (developer concern).

A PVC requests a certain amount of storage with specific access modes. Kubernetes binds it to an available PV that meets the requirements.

See [Persistent Storage](persistent-storage.md) for a comprehensive walkthrough covering ephemeral vs persistent storage, volume types, and hands-on examples.

### StorageClasses

A **StorageClass** enables **dynamic provisioning** of PersistentVolumes. Instead of an administrator pre-creating PVs, the StorageClass tells Kubernetes how to create them on demand when a PVC is submitted.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/gce-pd
parameters:
  type: pd-ssd
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
```

Then a PVC can request this class:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  storageClassName: fast-ssd
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 50Gi
```

Docker Desktop includes a default StorageClass called `hostpath` that provisions storage from the local disk. In cloud environments, StorageClasses map to cloud provider disk types (AWS EBS, GCP Persistent Disk, Azure Disk).

### CSI Drivers

The **Container Storage Interface (CSI)** is a standard that allows third-party storage providers to integrate with Kubernetes without modifying core Kubernetes code. CSI drivers are deployed as pods in the cluster and handle volume creation, attachment, mounting, and deletion.

Use CSI drivers when you need storage beyond what Kubernetes natively supports:

- Cloud provider storage (AWS EBS CSI, GCP PD CSI)
- Network file systems (NFS, CephFS)
- Distributed storage (Rook/Ceph, Longhorn, OpenEBS)

---

## Scaling and Performance

Kubernetes supports multiple dimensions of scaling -- from individual pod resources to the entire cluster.

### Horizontal Pod Autoscaler (HPA)

The **HPA** automatically adjusts the number of pod replicas based on observed metrics (typically CPU or memory utilization). The HPA controller checks metrics every 15 seconds and calculates the desired replica count to bring utilization close to the target.

Our project includes a fully configured HPA in `k8s/hpa.yaml` with a CPU target of 50% and a range of 2-10 replicas.

See [Horizontal Pod Autoscaler](hpa.md) for a complete walkthrough including stress-testing to trigger autoscaling.

### Vertical Pod Autoscaler (VPA)

The **VPA** automatically adjusts the CPU and memory **requests and limits** for containers. Instead of adding more pods (horizontal), it makes existing pods bigger or smaller (vertical). The VPA monitors actual resource usage over time and recommends (or applies) new resource values.

Use VPA when:

- You do not know the right resource requests for a new application
- Your workload has variable resource needs that do not scale horizontally (e.g., a single-replica batch processor)
- You want to right-size pods to avoid wasting resources

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: fastapi-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fastapi-k8s
  updatePolicy:
    updateMode: "Auto"       # can also be "Off" (recommend only) or "Initial"
  resourcePolicy:
    containerPolicies:
      - containerName: fastapi-k8s
        minAllowed:
          cpu: 25m
          memory: 32Mi
        maxAllowed:
          cpu: 500m
          memory: 512Mi
```

!!! note
    VPA and HPA should not target the same metric (e.g., both scaling on CPU). If you use both, configure HPA for CPU and VPA for memory, or use VPA in recommendation-only mode (`updateMode: "Off"`) to inform your manual resource tuning.

### Cluster Autoscaler

The **Cluster Autoscaler** adds or removes **nodes** from the cluster based on demand. When pods cannot be scheduled because no node has enough resources, the Cluster Autoscaler provisions a new node. When nodes are underutilized, it drains and removes them.

This operates at the infrastructure level and requires integration with a cloud provider (AWS, GCP, Azure) or a cluster management platform. It does not apply to Docker Desktop.

Use Cluster Autoscaler when:

- Your workload varies significantly (e.g., batch processing spikes)
- You want to optimize cloud costs by running only the nodes you need

### KEDA

**KEDA** (Kubernetes Event-Driven Autoscaler) extends HPA with event-driven scaling. While HPA scales based on CPU/memory, KEDA can scale based on external metrics -- queue depth, HTTP request rate, database connections, custom Prometheus metrics, and many more.

KEDA's killer feature is **scale to zero**: when there are no events to process, KEDA scales the deployment to zero replicas, saving resources entirely. When an event arrives, KEDA spins up pods to handle it.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: queue-processor
spec:
  scaleTargetRef:
    name: queue-worker
  minReplicaCount: 0           # scale to zero when idle
  maxReplicaCount: 20
  triggers:
    - type: rabbitmq
      metadata:
        queueName: tasks
        queueLength: "5"       # 1 pod per 5 messages in queue
```

---

## Security

Kubernetes provides multiple layers of security, from API access control to pod-level isolation.

### RBAC (Role-Based Access Control)

**RBAC** controls who can do what in the cluster. It uses four resources:

- **Role** -- defines permissions within a single namespace
- **ClusterRole** -- defines permissions cluster-wide
- **RoleBinding** -- grants a Role to a user/group/service account in a namespace
- **ClusterRoleBinding** -- grants a ClusterRole cluster-wide

```yaml
# A Role that allows reading pods and their logs in the "production" namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]

---
# Bind the Role to a specific service account
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: production
subjects:
  - kind: ServiceAccount
    name: monitoring-sa
    namespace: production
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

Use RBAC to implement the **principle of least privilege** -- grant only the permissions each user, team, or service needs.

### Service Accounts

A **Service Account** provides an identity for processes running inside pods. Every namespace has a `default` service account, but you should create dedicated service accounts for applications that need to interact with the Kubernetes API.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-app-sa
  namespace: default
automountServiceAccountToken: false    # don't mount token unless needed
```

Reference in a pod:

```yaml
spec:
  serviceAccountName: my-app-sa
  containers:
    - name: app
      image: myapp:latest
```

!!! tip
    Set `automountServiceAccountToken: false` on service accounts (and on pod specs) unless the pod actually needs to call the Kubernetes API. This reduces the attack surface if a container is compromised.

### Pod Security Standards

**Pod Security Standards** define three security profiles that restrict what pods can do:

| Profile | Description |
|---------|-------------|
| **Privileged** | No restrictions. For system-level workloads that need full access. |
| **Baseline** | Prevents known privilege escalations. Allows most workloads without changes. |
| **Restricted** | Heavily restricted. Requires non-root, read-only root filesystem, no capabilities. |

These are enforced at the namespace level using labels:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

With the `restricted` profile enforced, Kubernetes will reject any pod that runs as root, uses host networking, or requests dangerous capabilities.

### Network Policies

Network Policies restrict pod-to-pod traffic at the network level. They are covered in the Networking section above -- see [Network Policies](#network-policies) for details and examples.

### Secrets Encryption

By default, Kubernetes Secrets are stored in etcd as base64-encoded plaintext. For production, you should enable **encryption at rest** so that Secrets are encrypted before being written to etcd.

Beyond built-in encryption, external secret managers provide stronger guarantees:

- **HashiCorp Vault** -- Full-featured secrets management with dynamic secrets, leasing, and audit logging
- **Sealed Secrets (Bitnami)** -- Encrypt secrets in Git, only the cluster can decrypt them
- **External Secrets Operator** -- Sync secrets from AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, or Vault into Kubernetes Secrets

```bash
# Example: using kubectl to create a secret (not recommended for production)
kubectl create secret generic db-creds \
  --from-literal=username=admin \
  --from-literal=password=changeme

# Example: using Sealed Secrets (safe to commit to Git)
kubeseal --format yaml < secret.yaml > sealed-secret.yaml
```

### Security Contexts

A **Security Context** defines privilege and access control settings for a pod or container. These settings run at the Linux kernel level and provide defense in depth.

```yaml
spec:
  securityContext:
    runAsNonRoot: true                # pod-level: all containers must run as non-root
    runAsUser: 1000
    fsGroup: 1000
  containers:
    - name: app
      image: myapp:latest
      securityContext:
        readOnlyRootFilesystem: true  # container can't write to its filesystem
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL                     # drop all Linux capabilities
```

Key settings:

- `runAsNonRoot` -- Kubernetes rejects the pod if the container tries to run as root
- `readOnlyRootFilesystem` -- Prevents writing to the container filesystem (use volumes for writable paths)
- `capabilities.drop: [ALL]` -- Removes all Linux capabilities, minimizing what the process can do

---

## Scheduling and Placement

Kubernetes gives you fine-grained control over which nodes pods run on and how pods are distributed.

### Node Selectors

The simplest way to constrain a pod to specific nodes. You label nodes and add a `nodeSelector` to the pod spec.

```bash
# Label a node
kubectl label nodes worker-1 disktype=ssd
```

```yaml
spec:
  nodeSelector:
    disktype: ssd
```

The pod will only be scheduled on nodes with the `disktype=ssd` label.

### Node Affinity and Anti-Affinity

**Node Affinity** is a more expressive version of `nodeSelector`. It supports `requiredDuringSchedulingIgnoredDuringExecution` (hard requirement) and `preferredDuringSchedulingIgnoredDuringExecution` (soft preference).

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: topology.kubernetes.io/zone
                operator: In
                values:
                  - us-east-1a
                  - us-east-1b
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 80
          preference:
            matchExpressions:
              - key: node-type
                operator: In
                values:
                  - compute-optimized
```

This example says: "This pod **must** run in zone us-east-1a or us-east-1b, and **preferably** on a compute-optimized node."

### Pod Affinity and Anti-Affinity

**Pod Affinity** schedules pods close to (or far from) other pods. This is useful for co-locating related services or spreading replicas across failure domains.

```yaml
spec:
  affinity:
    # Co-locate with cache pods for low latency
    podAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchLabels:
              app: redis-cache
          topologyKey: kubernetes.io/hostname
    # Spread API replicas across nodes
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchLabels:
                app: fastapi-k8s
            topologyKey: kubernetes.io/hostname
```

This says: "Schedule this pod on a node that already runs a redis-cache pod (affinity), and preferably not on a node that already runs another fastapi-k8s pod (anti-affinity)."

### Taints and Tolerations

**Taints** are applied to nodes to repel pods. **Tolerations** are applied to pods to allow them onto tainted nodes. This is the inverse of affinity -- instead of attracting pods to nodes, taints push them away.

```bash
# Taint a node -- no pods will be scheduled here unless they tolerate it
kubectl taint nodes gpu-node-1 gpu=true:NoSchedule
```

```yaml
# A pod that tolerates the GPU taint
spec:
  tolerations:
    - key: "gpu"
      operator: "Equal"
      value: "true"
      effect: "NoSchedule"
  containers:
    - name: ml-training
      image: pytorch:latest
      resources:
        limits:
          nvidia.com/gpu: 1
```

Common use cases:

- **Dedicated nodes** -- Taint GPU nodes so only ML workloads run on them
- **Node maintenance** -- Taint a node with `NoSchedule` before draining it
- **System components** -- Control plane nodes are tainted to prevent user workloads from running on them

!!! info
    Kubernetes automatically adds taints to nodes that become unhealthy (e.g., `node.kubernetes.io/not-ready`). The default tolerations on pods allow a grace period before eviction.

### Topology Spread Constraints

**Topology Spread Constraints** distribute pods evenly across topology domains (zones, nodes, racks). Unlike pod anti-affinity (which is binary -- schedule here or not), topology spread gives you control over the maximum allowed imbalance.

```yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1                              # max difference between zones
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule        # or ScheduleAnyway
      labelSelector:
        matchLabels:
          app: fastapi-k8s
```

This ensures that the replica count across zones differs by at most 1. If you have 6 replicas and 3 zones, you get 2 pods per zone.

### Priority and Preemption

**PriorityClasses** let you assign priority levels to pods. When the cluster is full, the scheduler can **preempt** (evict) lower-priority pods to make room for higher-priority ones.

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: critical
value: 1000000
globalDefault: false
description: "For critical production workloads"

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: batch
value: 100
globalDefault: false
description: "For batch processing jobs"
```

```yaml
# Use in a pod spec
spec:
  priorityClassName: critical
```

If the cluster is at capacity and a `critical` pod needs to be scheduled, Kubernetes will evict `batch` pods to free up resources. Use this to ensure production workloads always get resources, even when the cluster is under pressure.

---

## Reliability

Kubernetes has built-in mechanisms to keep your application running and protect against disruptions.

### Self-Healing

Kubernetes continuously compares the **desired state** (your YAML) with the **actual state** (what is running). If they differ, it reconciles: creating new pods to replace crashed ones, rescheduling pods from failed nodes, and restarting containers that exit with errors.

This reconciliation loop is the heart of Kubernetes reliability. It handles pod crashes, node failures, and manual deletions without any intervention.

See [Self-Healing](self-healing.md) for a hands-on demonstration of killing pods and watching Kubernetes bring them back.

### Health Probes

Kubernetes supports three types of health probes:

| Probe | Purpose | On failure |
|-------|---------|------------|
| **Liveness** | Is the container alive? | Restart the container |
| **Readiness** | Is the container ready for traffic? | Remove from Service endpoints |
| **Startup** | Has the container finished starting? | Keep checking (don't run liveness yet) |

Our project uses liveness (`GET /health`) and readiness (`GET /ready`) probes. The startup probe is useful for slow-starting applications -- it prevents the liveness probe from killing a container that is still initializing.

See [Self-Healing](self-healing.md) for probe configuration and experimentation.

### Pod Disruption Budgets (PDB)

A **PDB** limits how many pods can be voluntarily disrupted at the same time. Voluntary disruptions include node drains (for maintenance), cluster upgrades, and autoscaler scale-downs. PDBs do not protect against involuntary disruptions like node crashes.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-pdb
spec:
  minAvailable: 3        # at least 3 pods must always be running
  # OR: maxUnavailable: 1  # at most 1 pod can be down at a time
  selector:
    matchLabels:
      app: fastapi-k8s
```

Use PDBs when:

- You need to guarantee a minimum number of available replicas during maintenance
- You are running a cluster with regular node updates or autoscaling

```bash
# When you drain a node, Kubernetes respects PDBs
kubectl drain worker-2 --ignore-daemonsets --delete-emptydir-data
# If draining would violate the PDB, the drain command waits
```

!!! tip
    Always create a PDB for production Deployments. Without one, a node drain can take all your pods offline at once.

### Resource Quotas

A **ResourceQuota** sets aggregate resource limits for an entire namespace. This prevents any single team or application from consuming all cluster resources.

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "10"          # total CPU requests across all pods
    requests.memory: 20Gi       # total memory requests
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"                  # max 50 pods in this namespace
    persistentvolumeclaims: "10"
```

When a ResourceQuota is active, every pod in the namespace **must** specify resource requests and limits, or creation will be rejected.

See [Resource Management](resource-management.md) for how individual pod resource requests and limits work.

### Limit Ranges

A **LimitRange** sets default resource requests/limits and enforces min/max constraints for individual containers in a namespace. While ResourceQuota caps the namespace total, LimitRange caps each container.

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: container-limits
  namespace: team-alpha
spec:
  limits:
    - type: Container
      default:                 # applied if container has no limits
        cpu: 200m
        memory: 256Mi
      defaultRequest:          # applied if container has no requests
        cpu: 50m
        memory: 64Mi
      max:                     # no container can request more than this
        cpu: "2"
        memory: 2Gi
      min:                     # no container can request less than this
        cpu: 10m
        memory: 16Mi
```

Use LimitRange to:

- Ensure every container has resource requests (required when ResourceQuota is active)
- Prevent developers from requesting unreasonably large or small resource amounts
- Set sensible defaults so pods work without explicit resource specs

---

## Deployment Strategies

Kubernetes natively supports two deployment strategies, and additional strategies can be implemented with external tools.

### Rolling Updates

The default strategy. Kubernetes gradually replaces old pods with new ones, maintaining availability throughout the process. You control the pace with `maxSurge` (how many extra pods to create) and `maxUnavailable` (how many pods can be down).

See [Rolling Updates](rolling-updates.md) for a hands-on walkthrough with our FastAPI app.

### Recreate

The **Recreate** strategy terminates all existing pods before creating new ones. This means there is a period of downtime during the update.

```yaml
spec:
  strategy:
    type: Recreate
```

Use Recreate when:

- Your application cannot run two versions simultaneously (e.g., database schema conflicts)
- Downtime during deploys is acceptable
- You need a clean break between versions

### Blue-Green Deployments

In a **blue-green** deployment, you maintain two identical environments. "Blue" is the current production version, "green" is the new version. Once green is verified, you switch traffic from blue to green by updating the Service selector.

```yaml
# Deploy the new version with a different label
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-green
spec:
  replicas: 5
  selector:
    matchLabels:
      app: fastapi-k8s
      version: green
  template:
    metadata:
      labels:
        app: fastapi-k8s
        version: green
    spec:
      containers:
        - name: fastapi-k8s
          image: fastapi-k8s:2.0.0
```

```bash
# Switch traffic to green by patching the Service selector
kubectl patch service fastapi-k8s \
  -p '{"spec":{"selector":{"version":"green"}}}'

# Rollback by switching back to blue
kubectl patch service fastapi-k8s \
  -p '{"spec":{"selector":{"version":"blue"}}}'
```

Blue-green gives you instant rollback (just switch the selector back), but requires double the resources during the transition.

### Canary Deployments

A **canary** deployment gradually shifts traffic from the old version to the new version. You start by sending a small percentage of traffic (e.g., 5%) to the new version, monitor for errors, and gradually increase to 100%.

Native Kubernetes does not directly support percentage-based traffic splitting. You can approximate it with replica ratios (e.g., 9 old pods and 1 new pod for roughly 10% canary traffic), but for precise control, use dedicated tools:

- **Argo Rollouts** -- Adds canary and blue-green strategies as custom resources, with automated analysis and promotion
- **Flagger** -- Progressive delivery operator that works with Istio, Linkerd, NGINX, and other service meshes

```yaml
# Argo Rollouts example
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: fastapi-k8s
spec:
  replicas: 5
  strategy:
    canary:
      steps:
        - setWeight: 10       # send 10% of traffic to canary
        - pause: {duration: 5m}
        - setWeight: 30
        - pause: {duration: 5m}
        - setWeight: 60
        - pause: {duration: 5m}
        - setWeight: 100      # promote to 100%
```

---

## Observability

Monitoring, logging, and tracing let you understand what your cluster and applications are doing.

### Metrics Server

The **Metrics Server** collects resource usage metrics (CPU and memory) from kubelets on each node. It powers `kubectl top` and is required by the HPA to make scaling decisions. It provides a real-time snapshot, not historical data.

```bash
# Install metrics-server (our project provides a make target)
make metrics-server

# View pod resource usage
kubectl top pods -l app=fastapi-k8s

# View node resource usage
kubectl top nodes
```

See [Monitoring & Observability](monitoring.md) for more on built-in Kubernetes monitoring tools.

### Prometheus

**Prometheus** is the standard for metrics collection in Kubernetes. It scrapes metrics endpoints from pods, stores time-series data, and supports powerful querying with PromQL. Combined with **Grafana** for dashboards and **Alertmanager** for alerts, it forms the de facto Kubernetes monitoring stack.

```bash
# Install the full monitoring stack with Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack
```

This installs Prometheus, Grafana, Alertmanager, and pre-configured dashboards for Kubernetes cluster monitoring.

See [Monitoring & Observability](monitoring.md) for more on setting up Prometheus and Grafana.

### Logging

Kubernetes does not provide a built-in centralized logging solution, but it offers the building blocks:

- `kubectl logs <pod>` -- View logs from a specific pod
- `kubectl logs -l app=fastapi-k8s` -- View logs from all pods with a label
- `kubectl logs <pod> --previous` -- View logs from the previous container instance (useful for crash debugging)

For production, deploy a centralized logging stack:

- **EFK** (Elasticsearch + Fluentd + Kibana) -- The traditional Kubernetes logging stack
- **Loki + Grafana** -- Lightweight log aggregation by Grafana Labs, designed for Kubernetes
- **Fluent Bit** -- Lightweight log processor, often used instead of Fluentd

See [Monitoring & Observability](monitoring.md) for more on using `kubectl logs`.

### Tracing

**Distributed tracing** tracks requests as they flow through multiple services. Each request gets a unique trace ID, and each service adds a span showing how long it spent processing the request. This is essential for debugging latency and understanding service dependencies in microservice architectures.

Popular tools:

- **Jaeger** -- Open-source distributed tracing, originally from Uber
- **Zipkin** -- Distributed tracing system originally from Twitter
- **OpenTelemetry** -- Vendor-neutral standard for metrics, logs, and traces. Increasingly the recommended approach, as it consolidates previously separate tools

For a single-service app like this project, tracing adds little value. It becomes essential when you have multiple services calling each other.

### Events

Kubernetes records **events** for significant occurrences in the cluster: pod scheduling, image pulls, container starts, failures, and more. Events are short-lived (retained for about 1 hour by default) but provide valuable insight into what is happening.

```bash
# View all events in the default namespace, sorted by time
kubectl get events --sort-by=.metadata.creationTimestamp

# View events for a specific pod
kubectl describe pod <pod-name>
# Events are shown at the bottom of the describe output

# Watch events in real time
kubectl get events --watch
```

Events are the first place to check when debugging pod issues. They tell you why a pod is pending, why a container was restarted, or why an image pull failed.

---

## Extension Points

Kubernetes is designed to be extended. You can add new resource types, automate complex operations, and intercept resource creation.

### Custom Resource Definitions (CRDs)

A **CRD** extends the Kubernetes API with a new resource type. Once you create a CRD, users can create, read, update, and delete instances of the custom resource using `kubectl`, just like built-in resources.

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: backups.myapp.example.com
spec:
  group: myapp.example.com
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                schedule:
                  type: string
                destination:
                  type: string
  scope: Namespaced
  names:
    plural: backups
    singular: backup
    kind: Backup
```

After applying this CRD:

```bash
# Now you can create Backup resources
kubectl apply -f my-backup.yaml
kubectl get backups
```

CRDs are the foundation for Operators and most Kubernetes ecosystem tools (Cert-Manager, Argo, Istio, etc.).

### Operators

An **Operator** combines a CRD with a custom controller that watches for changes to the custom resource and takes action. Operators encode operational knowledge -- the kind of procedures a human operator would follow -- into software.

For example, a PostgreSQL Operator would:

1. Create a `PostgresCluster` CRD
2. Watch for new `PostgresCluster` resources
3. Automatically create StatefulSets, Services, PVCs, and ConfigMaps
4. Handle backups, failover, scaling, and version upgrades

Popular Operators:

- **CloudNativePG** -- PostgreSQL operator
- **Strimzi** -- Apache Kafka operator
- **Cert-Manager** -- Automated TLS certificate management
- **Prometheus Operator** -- Manages Prometheus instances

```bash
# Find operators on OperatorHub
# https://operatorhub.io

# Example: install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml
```

### Admission Controllers

**Admission Controllers** intercept requests to the Kubernetes API server after authentication and authorization but before the resource is persisted to etcd. They can **validate** (reject bad resources) or **mutate** (modify resources before creation).

Kubernetes includes many built-in admission controllers (e.g., `LimitRanger`, `ResourceQuota`, `PodSecurity`). You can add custom ones using webhooks.

### Webhooks

**Webhooks** let you write your own admission logic as an HTTP service running in the cluster:

- **ValidatingWebhookConfiguration** -- Reject resources that do not meet your policies (e.g., "all images must come from our private registry")
- **MutatingWebhookConfiguration** -- Modify resources before creation (e.g., "inject a sidecar container into every pod")

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: require-labels
webhooks:
  - name: require-labels.example.com
    rules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["deployments"]
    clientConfig:
      service:
        name: webhook-server
        namespace: default
        path: /validate
    admissionReviewVersions: ["v1"]
    sideEffects: None
```

This webhook would call your `webhook-server` service every time a Deployment is created or updated, giving you a chance to enforce custom policies.

!!! note
    Istio's sidecar injection and many policy engines (OPA Gatekeeper, Kyverno) work by registering mutating or validating webhooks.

---

## Package Management

Managing raw YAML at scale becomes unwieldy. Package management tools help you template, version, and share Kubernetes configurations.

### Helm

**Helm** is the most widely used package manager for Kubernetes. It uses **charts** -- packages of pre-configured Kubernetes resources with templating support. Charts can be versioned, shared through repositories, and installed with a single command.

Key concepts:

- **Chart** -- A package containing templated Kubernetes manifests, default values, and metadata
- **Release** -- A specific installation of a chart in a cluster
- **Repository** -- A collection of charts (like a package registry)
- **Values** -- Configuration that customizes a chart installation

```bash
# Add a chart repository
helm repo add bitnami https://charts.bitnami.com/bitnami

# Search for charts
helm search repo postgresql

# Install a chart with custom values
helm install my-db bitnami/postgresql \
  --set auth.postgresPassword=secretpass \
  --set primary.persistence.size=20Gi

# List installed releases
helm list

# Upgrade a release
helm upgrade my-db bitnami/postgresql --set primary.persistence.size=50Gi

# Rollback to a previous version
helm rollback my-db 1

# Uninstall
helm uninstall my-db
```

Use Helm when:

- You want to install third-party applications (databases, monitoring stacks, ingress controllers)
- You need templating to manage multiple environments (dev, staging, prod)
- You want versioned, repeatable deployments with rollback support

See [Where to Go Next](next-steps.md) for more on Helm.

### Kustomize

**Kustomize** uses an overlay-based approach to customize Kubernetes YAML without templates. It is built into `kubectl` -- no additional tools required. You start with a base configuration and apply patches (overlays) for different environments.

```
base/
  deployment.yaml
  service.yaml
  kustomization.yaml
overlays/
  dev/
    kustomization.yaml      # patches for dev
  production/
    kustomization.yaml      # patches for production
    increase-replicas.yaml
```

```yaml
# base/kustomization.yaml
resources:
  - deployment.yaml
  - service.yaml

# overlays/production/kustomization.yaml
resources:
  - ../../base
patches:
  - path: increase-replicas.yaml
namePrefix: prod-
namespace: production
```

```bash
# Apply the production overlay
kubectl apply -k overlays/production/

# Preview what will be applied
kubectl kustomize overlays/production/
```

Use Kustomize when:

- You prefer declarative configuration over templating
- Your customizations are mostly small patches (replica counts, namespaces, labels)
- You want to avoid a dependency on Helm

See [Where to Go Next](next-steps.md) for more on Kustomize.

---

## Summary

This page covered the major Kubernetes features at a high level. The table below maps each feature to where you are most likely to encounter it:

| Stage | Features |
|-------|----------|
| **Getting started** | Deployments, Services, ConfigMaps, Pods |
| **Running in production** | HPA, PDBs, Resource Quotas, RBAC, Health Probes, Secrets |
| **Scaling** | HPA, VPA, Cluster Autoscaler, KEDA |
| **Advanced networking** | Ingress, Network Policies, Service Mesh |
| **Stateful workloads** | StatefulSets, PersistentVolumes, StorageClasses |
| **Batch processing** | Jobs, CronJobs |
| **Platform engineering** | CRDs, Operators, Admission Webhooks, Helm |

For hands-on walkthroughs using our FastAPI project, start with [Your First Deployment](first-deployment.md) and work through the guide pages linked throughout this document.
