# Resource Management

By default, a container can use as much CPU and memory as the node has available. In a shared cluster, this is a recipe for disaster -- one runaway container can starve every other workload on the same node. Kubernetes resource management gives you the tools to prevent this.

## Why resource management matters

Without resource constraints, your cluster is vulnerable to several problems:

- **Noisy neighbors** -- A single misbehaving pod can consume all CPU or memory on a node, degrading performance for every other pod scheduled there. Even in our Docker Desktop single-node setup, running five replicas of fastapi-k8s means they compete for the same resources.
- **Scheduling efficiency** -- The Kubernetes scheduler uses resource requests to decide where to place pods. Without requests, the scheduler has no idea how much capacity a pod actually needs, leading to poor placement decisions and unbalanced nodes.
- **Cost optimization** -- In cloud environments, you pay for the resources you allocate. Over-requesting wastes money (nodes are underutilized). Under-requesting causes instability (pods get evicted or throttled). Getting the balance right is one of the most impactful things you can do for your Kubernetes bill.
- **Stability** -- Resource limits protect the node itself. A memory leak in one container cannot bring down the entire node because the kernel enforces the limit and kills the offending container before it can do broader damage.

## Requests vs limits

Every container in a pod can specify two resource values for CPU and memory:

| Field | Purpose | What happens when exceeded |
|-------|---------|---------------------------|
| `requests` | **Guaranteed minimum.** The scheduler reserves this amount on the node. | N/A -- this is what you are guaranteed to get. |
| `limits` | **Hard ceiling.** The maximum the container is allowed to use. | **CPU:** throttled (slowed down). **Memory:** OOMKilled (process terminated). |

The key distinction is that CPU and memory behave very differently when a limit is exceeded:

- **CPU is compressible.** If a container tries to use more CPU than its limit, the kernel throttles it -- the container runs slower but stays alive. No data is lost, no restarts occur.
- **Memory is incompressible.** If a container tries to allocate more memory than its limit, the kernel sends an OOM (Out of Memory) signal and kills the process. Kubernetes then restarts the container, and you see `OOMKilled` in the pod status.

!!! tip "Rule of thumb"
    Set requests to what your app needs under normal load. Set limits to what it might need under peak load. The gap between them is your burst headroom.

## QoS classes

Kubernetes assigns a Quality of Service (QoS) class to every pod based on how you configure requests and limits. This class determines eviction priority when the node runs low on resources.

### Guaranteed

Requests equal limits for every container in the pod, for both CPU and memory.

```yaml
resources:
  requests:
    cpu: "200m"
    memory: "128Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"
```

Guaranteed pods are the **last to be evicted**. Use this for critical workloads that must not be disrupted.

### Burstable

At least one container has a request set, but requests do not equal limits.

```yaml
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"
```

Burstable pods are evicted **after BestEffort pods** but before Guaranteed pods. **This is what our fastapi-k8s deployment uses** -- we want a guaranteed baseline but allow bursting during CPU-intensive operations like the `/stress` endpoint.

### BestEffort

No requests or limits are set on any container in the pod.

```yaml
resources: {}
```

BestEffort pods are the **first to be evicted** when the node is under memory pressure. They get whatever resources happen to be available but have no guarantees.

!!! warning "Eviction order"
    When a node runs low on memory, the kubelet evicts pods in this order: BestEffort first, then Burstable, then Guaranteed. Within the same QoS class, pods using the most resources relative to their requests are evicted first.

## Our resource configuration

In `k8s.yaml`, we configure our FastAPI containers with:

```yaml
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"
```

Why these specific values:

| Resource | Value | Reasoning |
|----------|-------|-----------|
| CPU request | 50m | A small FastAPI app at idle uses very little CPU. 50 millicores (5% of one core) is enough for normal request handling. |
| CPU limit | 200m | The `/stress` endpoint burns CPU on purpose. 200m gives 4x burst headroom above the request for these spikes. |
| Memory request | 64Mi | Python plus FastAPI plus uvicorn typically uses 40-60 MiB at baseline. 64Mi covers this with a small buffer. |
| Memory limit | 128Mi | 2x the request provides headroom for request processing, temporary data structures, and the occasional spike. |

With 5 replicas at 50m CPU request each, the total guaranteed CPU is 250m (a quarter of one core). On a Docker Desktop node with multiple cores, this leaves plenty of room for other workloads.

## CPU units in depth

Kubernetes measures CPU in **millicores** (also called millicpu):

| Value | Meaning |
|-------|---------|
| `1` | 1 full CPU core |
| `1000m` | Same as `1` -- 1000 millicores equals 1 core |
| `500m` | Half a core |
| `100m` | One-tenth of a core |
| `50m` | 5% of one core |

These are abstract units -- they map to one hyperthread on Intel/AMD, one vCPU on AWS, or one core on ARM. The important thing is that `1000m` always means the same amount of compute regardless of the underlying hardware.

**Throttling behavior:** When a container hits its CPU limit, the kernel CFS (Completely Fair Scheduler) quota kicks in. The container is paused for a portion of each 100ms scheduling period. For example, a container with a 200m limit gets 20ms of CPU time per 100ms period. If it uses its 20ms budget early in the period, it sits idle for the remaining 80ms. This shows up as increased latency in your application -- requests take longer because the CPU is being throttled.

!!! info "Fractional CPU"
    You cannot request less than `1m`. In practice, anything below `10m` is rarely useful because the overhead of running the container itself consumes a measurable fraction of that budget.

## Memory units in depth

Kubernetes supports both binary and decimal memory units:

| Unit | Type | Value |
|------|------|-------|
| `Ki` | Binary (kibibyte) | 1,024 bytes |
| `Mi` | Binary (mebibyte) | 1,048,576 bytes (1024 * 1024) |
| `Gi` | Binary (gibibyte) | 1,073,741,824 bytes |
| `K` | Decimal (kilobyte) | 1,000 bytes |
| `M` | Decimal (megabyte) | 1,000,000 bytes |
| `G` | Decimal (gigabyte) | 1,000,000,000 bytes |

!!! warning "Mi vs M"
    `128Mi` (mebibytes) and `128M` (megabytes) are different values. `128Mi` = 134,217,728 bytes while `128M` = 128,000,000 bytes. The difference is about 4.8%. Always use binary units (`Mi`, `Gi`) for consistency -- this is the convention in the Kubernetes ecosystem.

**What OOMKilled looks like:**

```bash
$ kubectl get pods -l app=fastapi-k8s
NAME                          READY   STATUS      RESTARTS      AGE
fastapi-k8s-7f8b9c6d4-xj2kl  0/1     OOMKilled   3 (20s ago)   5m

$ kubectl describe pod fastapi-k8s-7f8b9c6d4-xj2kl
# ...
# Last State:     Terminated
#   Reason:       OOMKilled
#   Exit Code:    137
#   Started:      Mon, 01 Jan 2026 12:00:00 +0000
#   Finished:     Mon, 01 Jan 2026 12:00:05 +0000
```

Exit code 137 means the process was killed by SIGKILL (128 + 9 = 137). This is the kernel enforcing the memory limit.

**How to debug OOMKilled:**

1. Check the exit code: `kubectl describe pod <name>` -- look for `Exit Code: 137`
2. Check previous logs: `kubectl logs <name> --previous` -- the app might log memory usage before crashing
3. Increase the memory limit if the app legitimately needs more
4. If it keeps happening, your app may have a memory leak -- profile it locally

## LimitRange

A **LimitRange** is a cluster-level resource that administrators use to set default and maximum resource values for containers within a namespace. This prevents users from deploying pods without any resource constraints.

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: default
spec:
  limits:
    - type: Container
      default:          # Applied if no limits are specified
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:   # Applied if no requests are specified
        cpu: "100m"
        memory: "64Mi"
      min:              # Minimum allowed values
        cpu: "10m"
        memory: "16Mi"
      max:              # Maximum allowed values
        cpu: "2"
        memory: "1Gi"
```

If you deploy a pod without resource specifications into a namespace with a LimitRange, Kubernetes automatically injects the `default` and `defaultRequest` values. If your specified values fall outside the `min`/`max` range, the pod is rejected.

!!! note "LimitRange on Docker Desktop"
    Docker Desktop does not set a LimitRange by default. You would only encounter this in managed clusters or environments where an administrator has configured one.

## ResourceQuota

While LimitRange controls individual containers, a **ResourceQuota** sets aggregate limits for an entire namespace -- total CPU, total memory, maximum number of pods, and more.

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: namespace-quota
  namespace: default
spec:
  hard:
    requests.cpu: "4"           # Total CPU requests across all pods
    requests.memory: "8Gi"      # Total memory requests across all pods
    limits.cpu: "8"             # Total CPU limits across all pods
    limits.memory: "16Gi"       # Total memory limits across all pods
    pods: "20"                  # Maximum number of pods
    services: "10"              # Maximum number of services
```

With this quota in place, our deployment's 5 replicas consume 250m of the 4-core CPU request budget and 320Mi of the 8Gi memory request budget -- well within the quota.

!!! info "Quota enforcement"
    When a ResourceQuota is active in a namespace, every pod **must** specify resource requests and limits. If you try to create a pod without them (and no LimitRange provides defaults), the request is rejected. This is why it is always good practice to specify resources explicitly.

## Downward API

The Kubernetes Downward API lets you expose pod and container metadata as environment variables or files inside the container. Our deployment uses this to make resource values available to the application at runtime.

From `k8s.yaml`:

```yaml
env:
  - name: CPU_REQUEST
    valueFrom:
      resourceFieldRef:
        resource: requests.cpu
  - name: CPU_LIMIT
    valueFrom:
      resourceFieldRef:
        resource: limits.cpu
  - name: MEMORY_REQUEST
    valueFrom:
      resourceFieldRef:
        resource: requests.memory
  - name: MEMORY_LIMIT
    valueFrom:
      resourceFieldRef:
        resource: limits.memory
```

The `/info` endpoint in `main.py` reads these environment variables and returns them:

```bash
$ curl -s http://localhost/info | python -m json.tool
{
    "pod_name": "fastapi-k8s-7f8b9c6d4-xj2kl",
    "pod_ip": "10.1.0.15",
    "node_name": "docker-desktop",
    "namespace": "default",
    "cpu_request": "1",
    "cpu_limit": "1",
    "memory_request": "67108864",
    "memory_limit": "134217728"
}
```

!!! note "CPU and memory values in the Downward API"
    The format depends on the `divisor` field in the `resourceFieldRef`. When no divisor is specified (as in our manifest), CPU defaults to a divisor of `1` (whole cores) and memory defaults to a divisor of `1` (bytes). With a divisor of `1` core, both `50m` and `200m` are rounded up to `1` because they are fractions of a single core. To see millicores instead, add `divisor: 1m` to the CPU resource field references. Memory values are exact in bytes: `64Mi` = 67,108,864 bytes, `128Mi` = 134,217,728 bytes.

## Monitoring resource usage

To see actual resource consumption, you need the metrics-server installed:

```bash
# Install metrics-server (Docker Desktop)
make metrics-server

# Wait a minute for metrics to populate, then check usage
kubectl top pods -l app=fastapi-k8s
```

Example output:

```
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-xj2kl  2m           45Mi
fastapi-k8s-7f8b9c6d4-ab1cd  1m           43Mi
fastapi-k8s-7f8b9c6d4-ef2gh  3m           44Mi
```

Compare these values against the requests and limits:

- CPU usage of 2m against a request of 50m means the pod is using only 4% of its guaranteed CPU -- lots of headroom.
- Memory usage of 45Mi against a limit of 128Mi means the pod is at 35% of its ceiling -- healthy.

You can also check node-level resource usage:

```bash
kubectl top nodes
```

```
NAME             CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
docker-desktop   250m         6%     1200Mi          15%
```

## Right-sizing

Getting resource values right is an iterative process. Here is a practical approach:

1. **Start generous.** Deploy with higher limits than you think you need. This prevents OOMKills and throttling while you gather data.
2. **Observe.** Run `kubectl top pods` over time -- during idle, normal load, and peak load. Note the actual usage patterns.
3. **Set requests to the P95 usage.** Your request should cover 95% of normal operating conditions. This is what the scheduler reserves.
4. **Set limits to the peak usage plus a buffer.** Your limit should cover the worst-case spike with 20-50% headroom.
5. **Iterate.** After a week of production data, adjust values based on what you observe.

For our FastAPI app, the idle CPU is ~2m and memory is ~45Mi. The `/stress` endpoint can push CPU to the 200m limit. Since `/stress` is deliberate and time-bounded, our current values are well-suited.

!!! tip "Vertical Pod Autoscaler (VPA)"
    In production clusters, the VPA can automatically recommend and even adjust resource requests based on observed usage. See the [HPA documentation](hpa.md) for a comparison of HPA and VPA.
