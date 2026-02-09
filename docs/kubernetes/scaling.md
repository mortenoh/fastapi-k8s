# Scaling

Scaling is how you adjust the capacity of your application to match demand. When traffic increases, you add more instances to handle the load. When traffic drops, you remove instances to save resources. Kubernetes makes scaling straightforward -- you declare how many replicas you want, and Kubernetes does the rest.

## Why Scale?

There are four main reasons to scale your application:

**Latency** -- When a single pod is handling too many concurrent requests, response times increase. Adding replicas spreads the load so each pod handles fewer requests, keeping latency low.

**Throughput** -- A single pod has a finite number of requests it can process per second. More replicas means the system as a whole can serve more requests per second.

**Availability** -- If you run a single replica and it crashes, your application is completely down until the replacement starts. With multiple replicas, surviving pods continue serving traffic while the failed one recovers.

**Cost efficiency** -- Scaling down when traffic is low frees up cluster resources for other workloads. You do not need 10 replicas at 3 AM if 2 can handle the load.

!!! tip
    A good rule of thumb: run at least 2 replicas in production for any service that needs to stay available. This protects you against single-pod failures and allows rolling updates without downtime.

## Horizontal vs Vertical Scaling

There are two fundamentally different approaches to scaling:

### Horizontal Scaling (Scaling Out)

Horizontal scaling means adding more pod replicas. Each replica is identical -- same container image, same resource limits. The Service distributes traffic across all of them.

```
Before:   1 pod  handling 100 req/s
After:    4 pods handling  25 req/s each
```

Advantages:

- No upper limit (you can keep adding pods until the cluster runs out of resources)
- Zero-downtime scaling (existing pods keep running while new ones start)
- Better fault tolerance (losing one pod out of four is less impactful than losing one out of one)

Disadvantages:

- Your application must be stateless, or you need external state management (database, Redis, etc.)
- More pods consume more base memory (each pod has its own Python process, framework overhead, etc.)

### Vertical Scaling (Scaling Up)

Vertical scaling means giving each pod more CPU or memory by increasing its resource requests and limits.

```yaml
# Before
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"

# After (scaled up)
resources:
  requests:
    cpu: "200m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

Advantages:

- Works for stateful applications that cannot easily be replicated
- Simpler architecture -- no need for load balancing or session management

Disadvantages:

- Requires a pod restart to apply new resource limits (brief downtime for that pod)
- Hard upper limit based on node size (a pod cannot be bigger than the node it runs on)
- Does not improve fault tolerance (still a single point of failure if you only have one replica)

!!! info
    In practice, most Kubernetes workloads use **horizontal scaling** as the primary strategy. Vertical scaling is typically used to right-size individual pods so each one has the resources it needs to function efficiently, not as a scaling strategy by itself.

## Manual Scaling

There are three ways to manually change the replica count for our deployment.

### Method 1: kubectl scale

The most direct way. Changes take effect immediately:

```bash
# Scale to 10 replicas
kubectl scale deployment fastapi-k8s --replicas=10

# Verify the result
kubectl get pods -l app=fastapi-k8s

# Scale back down to 3
kubectl scale deployment fastapi-k8s --replicas=3
```

!!! note
    `kubectl scale` changes the live Deployment object in the cluster but does **not** update your `k8s.yaml` file. If you later run `kubectl apply -f k8s.yaml`, the replica count will revert to whatever is in the file.

### Method 2: make scale

This project includes a convenience Makefile target that wraps `kubectl scale`:

```bash
# Scale to 10 replicas
make scale N=10

# Scale to 2 replicas
make scale N=2

# Scale to 1 replica
make scale N=1
```

Under the hood, this runs `kubectl scale deployment fastapi-k8s --replicas=$(N)`.

### Method 3: Edit the YAML and re-apply

For changes you want to persist in version control, edit the `replicas` field in `k8s.yaml`:

```yaml
spec:
  replicas: 10    # change this value
```

Then apply the change:

```bash
make deploy       # runs: kubectl apply -f k8s.yaml
```

This method is preferred when you want the change to be permanent and tracked in Git.

## How Load Balancing Works

When multiple replicas are running, the Kubernetes Service distributes incoming requests across all healthy pods. Understanding how this works helps you reason about traffic distribution.

### The Role of kube-proxy

Every node in a Kubernetes cluster runs `kube-proxy`, which programs the networking rules that implement Services. kube-proxy operates in one of two modes:

**iptables mode** (default) -- kube-proxy creates iptables rules that randomly select a backend pod for each new connection. Despite the name "round-robin" being commonly used, iptables mode actually uses random selection with equal probability. For large numbers of requests, this approximates uniform distribution.

**IPVS mode** -- kube-proxy uses Linux IPVS (IP Virtual Server) for load balancing, which supports true round-robin along with other algorithms (least connections, shortest expected delay, etc.). IPVS is more efficient for clusters with many Services.

!!! info
    Docker Desktop uses iptables mode by default. For a learning environment, the difference between iptables and IPVS is negligible. Both distribute traffic across pods effectively.

### Session Affinity

By default, each request can land on any healthy pod. If you need requests from the same client to consistently reach the same pod, you can enable session affinity:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
spec:
  sessionAffinity: ClientIP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 10800   # 3 hours
  selector:
    app: fastapi-k8s
```

Our project does **not** use session affinity because the FastAPI app is stateless -- any pod can handle any request.

### Traffic Flow Diagram

```
        Client (curl http://localhost)
                    |
                    v
        +--------- Service ---------+
        |  fastapi-k8s (port 80)    |
        |                           |
        |  kube-proxy (iptables)    |
        |  randomly selects a pod   |
        +-----|---------|--------|--+
              |         |        |
              v         v        v
           +------+  +------+  +------+
           |Pod 1 |  |Pod 2 |  |Pod 3 |
           |:8000 |  |:8000 |  |:8000 |
           +------+  +------+  +------+
```

Only pods that pass their **readiness probe** receive traffic. If Pod 2 fails its readiness check, kube-proxy removes it from the pool and distributes traffic between Pod 1 and Pod 3 only.

## Demonstrating Round-Robin Distribution

Our FastAPI app includes the pod hostname in every response via the `server` field. This makes it easy to see which pod handled each request.

### Single requests

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
    "server": "fastapi-k8s-7f8b9c6d4-m8tnr"
}
```

### Loop to visualize distribution

Send 20 requests and extract just the server name:

```bash
for i in $(seq 1 20); do
  curl -s http://localhost | python -m json.tool | grep server
done
```

Example output with 3 replicas:

```
"server": "fastapi-k8s-7f8b9c6d4-2nxkl"
"server": "fastapi-k8s-7f8b9c6d4-xj2kl"
"server": "fastapi-k8s-7f8b9c6d4-m8tnr"
"server": "fastapi-k8s-7f8b9c6d4-2nxkl"
"server": "fastapi-k8s-7f8b9c6d4-m8tnr"
"server": "fastapi-k8s-7f8b9c6d4-xj2kl"
...
```

You will see all three pod names appearing in a roughly even distribution.

### Count requests per pod

For a clearer picture, count how many requests each pod handled:

```bash
for i in $(seq 1 60); do
  curl -s http://localhost
done | python -c "
import sys, json
from collections import Counter
lines = sys.stdin.read().strip().split('\n')
counts = Counter()
for line in lines:
    data = json.loads(line)
    # Use the last 5 chars of the hostname for readability
    counts[data['server'][-5:]] += 1
for server, count in sorted(counts.items()):
    print(f'{server}: {count} requests')
"
```

With 3 replicas handling 60 requests, you should see roughly 20 requests per pod.

## Scale-Up Behavior

When you increase the replica count, here is what happens step by step:

1. **API update** -- The Deployment object is updated with the new replica count
2. **Scheduler** -- The Kubernetes scheduler assigns each new pod to a node (on Docker Desktop, there is only one node)
3. **Image pull** -- If the container image is not already cached on the node, it gets pulled. With `imagePullPolicy: Never` (our setup), this step is skipped because we build images locally
4. **Container start** -- The container runtime starts the container process
5. **Readiness probe** -- After `initialDelaySeconds` (2 seconds in our config), Kubernetes begins probing the `/ready` endpoint every 5 seconds
6. **Traffic starts** -- Once the readiness probe succeeds, the pod is added to the Service endpoints and begins receiving traffic

For our FastAPI app on Docker Desktop, a new pod typically goes from "created" to "receiving traffic" in about 3-5 seconds. This is fast because:

- The image is already on the node (no pull needed)
- FastAPI/uvicorn starts quickly
- The readiness probe has a short initial delay

!!! tip
    You can watch pods come up in real time with:

    ```bash
    kubectl get pods -l app=fastapi-k8s -w
    ```

    The `-w` flag (watch) streams updates as pod states change.

## Scale-Down Behavior

When you decrease the replica count, Kubernetes must decide which pods to terminate and how to do so gracefully.

### Which pods get terminated?

The ReplicaSet controller selects pods for termination using the following priority order:

1. Pods in `Pending` or unscheduled state (not yet running)
2. Pods with a more recent `creationTimestamp` (newest first)
3. Pods with higher restart counts
4. Pods with a more recent ready timestamp

In practice, for a stable deployment, this means the **newest pods are terminated first**.

### Graceful shutdown sequence

When a pod is selected for termination:

1. **Removed from Service endpoints** -- The pod is immediately removed from the Service so it stops receiving new traffic
2. **preStop hook** (if configured) -- Kubernetes runs the preStop hook and waits for it to complete
3. **SIGTERM** -- Kubernetes sends SIGTERM to the main process in the container
4. **Grace period** -- The application has `terminationGracePeriodSeconds` (default: 30 seconds) to finish in-flight requests and shut down cleanly
5. **SIGKILL** -- If the process is still running after the grace period, Kubernetes sends SIGKILL to force-terminate it

```
Pod selected for termination
        |
        v
Remove from Service endpoints
        |
        v
Run preStop hook (if any)
        |
        v
Send SIGTERM to main process
        |
        v
Wait up to terminationGracePeriodSeconds (default 30s)
        |
        v
Send SIGKILL (if still running)
        |
        v
Pod is gone
```

!!! warning
    If your application does not handle SIGTERM, it will be force-killed after 30 seconds. For most web frameworks (including uvicorn), SIGTERM handling is built in -- the server stops accepting new connections and finishes processing in-flight requests before exiting.

## Scaling to Zero

Standard Kubernetes Deployments do **not** support scaling to zero replicas in a meaningful way. You can set `replicas: 0`, and Kubernetes will terminate all pods, but there is nothing to bring them back when a request arrives.

For true scale-to-zero with automatic wake-up, you need an external component:

- **KEDA** (Kubernetes Event-Driven Autoscaling) -- Scales based on event sources (message queues, HTTP requests, cron schedules). Can scale to zero and back up based on queue depth or other triggers.
- **Knative** -- A serverless platform for Kubernetes. Routes requests through an activator component that can wake up pods when traffic arrives.

These are advanced tools beyond the scope of this beginner guide.

## Automatic Scaling

Manual scaling works for predictable workloads, but for variable traffic, automatic scaling is essential.

### Horizontal Pod Autoscaler (HPA)

HPA adjusts the replica count based on observed metrics like CPU or memory utilization. This project includes a full HPA setup -- see the [HPA page](hpa.md) for a complete walkthrough.

The key idea:

```
Average CPU usage > target  -->  add replicas
Average CPU usage < target  -->  remove replicas (after stabilization)
```

### Vertical Pod Autoscaler (VPA)

VPA automatically adjusts the CPU and memory requests/limits for your pods based on observed usage. Instead of adding more replicas, it right-sizes the resources allocated to each pod.

VPA has three modes:

- **Off** -- Only recommends changes, does not apply them
- **Initial** -- Sets resources only when pods are first created
- **Auto** -- Evicts and recreates pods with updated resources

!!! note
    VPA and HPA should generally not be used together on the same metric (e.g., both targeting CPU). They can conflict, with HPA adding replicas while VPA changes the resource request that HPA uses for its calculations. If you use both, configure HPA to use custom metrics and VPA for CPU/memory.

## Summary

| Action | Command |
|---|---|
| Scale to N replicas | `make scale N=5` |
| Scale with kubectl | `kubectl scale deployment fastapi-k8s --replicas=5` |
| Scale via YAML | Edit `replicas:` in `k8s.yaml`, then `make deploy` |
| Check pod count | `kubectl get pods -l app=fastapi-k8s` |
| Watch pods in real time | `kubectl get pods -l app=fastapi-k8s -w` |
| View HPA status | `make hpa-status` |

Horizontal scaling is the primary mechanism for handling variable load in Kubernetes. Combined with readiness probes and the Service load balancer, it provides a robust way to keep your application responsive under varying traffic patterns.
