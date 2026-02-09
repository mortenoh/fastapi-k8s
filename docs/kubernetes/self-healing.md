# Self-Healing

One of the most powerful features of Kubernetes is its ability to automatically detect and recover from failures. You declare the desired state of your application, and Kubernetes continuously works to make reality match that declaration. If a container crashes, a node goes down, or a health check fails, Kubernetes takes corrective action without human intervention.

## The Reconciliation Loop

At the heart of Kubernetes self-healing is the **reconciliation loop** -- also called the **control loop** or **controller pattern**.

### How it works

Every Kubernetes controller follows the same pattern:

1. **Observe** -- Read the current (actual) state of the cluster
2. **Compare** -- Diff the actual state against the desired state (what you declared in YAML)
3. **Act** -- If they differ, take action to bring actual state closer to desired state
4. **Repeat** -- Go back to step 1

```
        +-----> Observe actual state
        |              |
        |              v
        |       Compare with desired state
        |              |
        |              v
        |       Different?
        |        /        \
        |      No          Yes
        |      |            |
        |      v            v
        +-- Sleep       Take corrective action
        |                   |
        +-------------------+
```

For a Deployment with `replicas: 5`, the ReplicaSet controller continuously checks: "Are there exactly 5 healthy pods matching my selector?" If the answer is no, it creates or deletes pods to reach the target.

### How often does it run?

The controller does not poll on a fixed timer. Instead, it uses a **watch** mechanism -- the Kubernetes API server pushes notifications whenever relevant objects change. This means the controller reacts to events (pod crashed, node failed, etc.) within seconds, not minutes.

Additionally, controllers perform a periodic **resync** (default: every few minutes) to catch any events that might have been missed. This ensures eventual consistency even if a watch notification is lost.

!!! info
    The reconciliation loop is not unique to Deployments. Every Kubernetes controller -- ReplicaSets, Services, Jobs, DaemonSets, StatefulSets -- follows this exact same observe-compare-act pattern. It is the fundamental design principle of Kubernetes.

## Types of Self-Healing

Kubernetes handles several categories of failure automatically:

### 1. Restart crashed containers

When a container process exits (whether due to an unhandled exception, out-of-memory kill, or an explicit `os._exit(1)` like our `/crash` endpoint), the kubelet restarts it. The pod stays on the same node, keeps the same name, and the `RESTARTS` counter increments.

### 2. Reschedule pods from failed nodes

If a node becomes unreachable (hardware failure, network partition), the control plane marks its pods as `Unknown` after a timeout period (default: 5 minutes). The Deployment controller then creates replacement pods on healthy nodes. On Docker Desktop with a single node, this scenario does not apply, but it is critical in multi-node clusters.

### 3. Replace pods that fail liveness checks

If a container's liveness probe fails repeatedly, the kubelet kills the container and restarts it. This catches situations where the process is running but hung or deadlocked -- alive at the OS level but not functioning.

### 4. Remove unready pods from traffic

If a container's readiness probe fails, Kubernetes removes the pod from Service endpoints so it stops receiving traffic. The pod is not restarted -- it stays running and is given a chance to recover. Once the readiness probe passes again, the pod is re-added to the Service.

## Restart Policies

The `restartPolicy` field on a pod spec controls what happens when a container exits. There are three options:

### Always (default for Deployments)

```yaml
spec:
  restartPolicy: Always
```

The kubelet restarts the container regardless of the exit code -- whether it exited successfully (code 0) or with an error (non-zero). This is the default for Deployment pods and is almost always what you want for long-running services.

### OnFailure (common for Jobs)

```yaml
spec:
  restartPolicy: OnFailure
```

The kubelet restarts the container only if it exited with a non-zero exit code. If it exits cleanly (code 0), the container stays terminated. This is the typical choice for batch Jobs that should run to completion.

### Never

```yaml
spec:
  restartPolicy: Never
```

The kubelet never restarts the container, regardless of exit code. The pod transitions to `Succeeded` or `Failed` and stays in that terminal state. This is used for one-shot tasks or debugging scenarios where you want to inspect the container's final state.

!!! note
    Our deployment uses the default `restartPolicy: Always`. This means when `/crash` calls `os._exit(1)`, the kubelet immediately restarts the container. The pod keeps its name and IP, but the process inside starts fresh.

## CrashLoopBackOff

When a container keeps crashing repeatedly, Kubernetes enters a state called **CrashLoopBackOff**. This is not an error in itself -- it is Kubernetes telling you "this container keeps failing, so I am waiting longer between restarts to avoid wasting resources."

### The backoff timing

The kubelet uses exponential backoff for restart delays:

| Crash # | Delay before restart |
|---------|---------------------|
| 1st | 0 seconds (immediate restart) |
| 2nd | 10 seconds |
| 3rd | 20 seconds |
| 4th | 40 seconds |
| 5th | 80 seconds |
| 6th | 160 seconds |
| 7th+ | 300 seconds (5 minutes, the cap) |

After a successful run of about 10 minutes, the backoff timer resets.

### What you see in kubectl

```bash
$ kubectl get pods -l app=fastapi-k8s
NAME                          READY   STATUS             RESTARTS      AGE
fastapi-k8s-7f8b9c6d4-2nxkl  0/1     CrashLoopBackOff   5 (40s ago)   3m
```

### How to debug CrashLoopBackOff

```bash
# 1. Check the container logs (including previous crash)
kubectl logs <pod-name> --previous

# 2. Look at pod events for clues
kubectl describe pod <pod-name>

# 3. Common causes:
#    - Application error on startup (missing env var, bad config)
#    - Port already in use
#    - Missing dependency (file, database, external service)
#    - OOMKilled (container exceeded memory limit)
```

!!! warning
    CrashLoopBackOff is one of the most common issues you will encounter. Always start debugging with `kubectl logs <pod-name> --previous` to see the output from the last crash. The `--previous` flag is critical because the current container may not have produced any logs yet.

## Liveness Probes in Depth

A liveness probe answers the question: "Is this container still functioning?" If the probe fails, the kubelet kills the container and restarts it according to the restart policy.

### Probe types

Kubernetes supports three types of liveness probes:

**HTTP GET** -- The kubelet sends an HTTP GET request to a specified path and port. Any status code between 200 and 399 is considered success.

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
```

**TCP Socket** -- The kubelet attempts to open a TCP connection to a specified port. If the connection succeeds, the probe passes. Useful for non-HTTP services (databases, message brokers).

```yaml
livenessProbe:
  tcpSocket:
    port: 8000
```

**Exec command** -- The kubelet runs a command inside the container. If the command exits with code 0, the probe passes.

```yaml
livenessProbe:
  exec:
    command:
      - cat
      - /tmp/healthy
```

### Timing parameters

Every probe type supports the same timing parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `initialDelaySeconds` | 0 | Seconds to wait after container start before first probe |
| `periodSeconds` | 10 | How often to perform the probe |
| `timeoutSeconds` | 1 | Seconds to wait for a probe response before considering it failed |
| `successThreshold` | 1 | Consecutive successes needed to mark the probe as passing |
| `failureThreshold` | 3 | Consecutive failures needed before taking action |

### Our liveness probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 10
```

This means:

- Wait 3 seconds after the container starts before the first check
- Every 10 seconds, send `GET /health` to port 8000
- If the probe fails 3 times in a row (the default `failureThreshold`), restart the container
- The `/health` endpoint always returns `200 OK` with `{"status": "healthy"}`

### What happens when a liveness probe fails

```
Probe fails (1/3)  -->  No action, just recorded
Probe fails (2/3)  -->  No action, just recorded
Probe fails (3/3)  -->  kubelet kills the container
                         Container restarts (restartPolicy: Always)
                         RESTARTS counter increments
```

!!! tip
    Keep your liveness probe endpoint simple and fast. It should not check external dependencies (database, cache, external APIs). If your `/health` endpoint times out because the database is down, Kubernetes will restart your container -- but that will not fix the database. Use readiness probes for dependency checks.

## Readiness Probes in Depth

A readiness probe answers the question: "Is this container ready to receive traffic?" If the probe fails, the pod is removed from Service endpoints. Critically, the container is **not** restarted -- it is given time to recover.

### Same probe types, different consequences

Readiness probes support the same three types (HTTP GET, TCP Socket, Exec) and the same timing parameters as liveness probes. The key difference is what happens on failure:

| | Liveness probe fails | Readiness probe fails |
|---|---|---|
| Container restarted? | Yes | No |
| Removed from Service? | (After restart) | Yes, immediately |
| Use case | Detect deadlocks, hangs | Detect temporary unavailability |

### Our readiness probe

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 2
  periodSeconds: 5
```

The `/ready` endpoint in our FastAPI app is special -- it has a toggleable state:

```python
_ready = True

@app.get("/ready")
async def ready():
    if _ready:
        return {"status": "ready"}           # 200 OK
    return JSONResponse(status_code=503,
                        content={"status": "not ready"})  # 503
```

By calling `POST /ready/disable`, you can make the readiness probe fail on demand, which removes the pod from the Service. `POST /ready/enable` makes it pass again, re-adding the pod.

### Startup probes

For applications that take a long time to start (large ML models, complex initialization), there is a third probe type: the **startup probe**. While the startup probe is running, liveness and readiness probes are disabled, preventing Kubernetes from killing a slow-starting container.

```yaml
startupProbe:
  httpGet:
    path: /health
    port: 8000
  failureThreshold: 30
  periodSeconds: 10
  # Allows up to 30 * 10 = 300 seconds (5 min) for startup
```

Our FastAPI app starts in under a second, so we do not need a startup probe.

## Why Liveness and Readiness Probes Are Separate

It is important to understand why our app has two different endpoints:

**`/health` (liveness)** -- Always returns 200. It tells Kubernetes "the process is alive and not deadlocked." If this fails, something is seriously wrong and a restart is warranted.

**`/ready` (readiness)** -- Returns 200 or 503 based on application state. It tells Kubernetes "I can serve traffic right now." Failing readiness should not trigger a restart, just remove the pod from the load balancer.

Real-world examples of why you would want readiness to fail without a restart:

- The application is warming up a cache
- A downstream dependency is temporarily unavailable
- The pod is draining connections before a graceful shutdown
- The application is performing a data migration

## Demonstration Walkthroughs

### 1. Kill a pod with kubectl delete

This demonstrates the ReplicaSet controller recreating a pod to maintain the desired count.

```bash
# Check current pods
kubectl get pods -l app=fastapi-k8s

# Delete one pod by name
kubectl delete pod fastapi-k8s-7f8b9c6d4-2nxkl

# Immediately check again -- a new pod is already being created
kubectl get pods -l app=fastapi-k8s
```

You will see the deleted pod is gone and a new pod (with a different name) has appeared. The total count returns to the desired number of replicas within seconds.

### 2. Crash a pod with POST /crash

This demonstrates the kubelet restarting a crashed container within the same pod.

```bash
# List pods, note the RESTARTS column (should be 0)
kubectl get pods -l app=fastapi-k8s

# Crash a pod via the API
curl -X POST http://localhost/crash

# Check again -- one pod will show RESTARTS: 1
kubectl get pods -l app=fastapi-k8s
```

!!! note
    The pod name stays the same after a restart -- only the container inside it is restarted. The `RESTARTS` counter increments, and the pod briefly shows a non-Ready state before the readiness probe passes again.

The difference between `kubectl delete` and `/crash`:

| | `kubectl delete pod` | `POST /crash` |
|---|---|---|
| Pod name | New name (new pod created) | Same name (container restarted) |
| Pod IP | New IP | Same IP |
| RESTARTS counter | 0 (new pod) | Incremented |
| Who acts | ReplicaSet controller | kubelet |

### 3. Toggle readiness with POST /ready/disable

This demonstrates a pod being removed from Service endpoints without being restarted.

```bash
# Get a specific pod name
POD=$(kubectl get pod -l app=fastapi-k8s -o jsonpath='{.items[0].metadata.name}')

# Check current endpoints (all pod IPs listed)
kubectl get endpoints fastapi-k8s

# Disable readiness on one pod
kubectl exec $POD -- curl -s -X POST http://localhost:8000/ready/disable

# Wait a few seconds for the probe to run, then check endpoints
# The pod's IP will be gone from the list
kubectl get endpoints fastapi-k8s

# The pod is still running -- it just is not receiving traffic
kubectl get pods -l app=fastapi-k8s
# Notice: the pod shows 0/1 READY

# Re-enable readiness
kubectl exec $POD -- curl -s -X POST http://localhost:8000/ready/enable

# The pod's IP reappears in endpoints
kubectl get endpoints fastapi-k8s
```

### 4. Watch events during self-healing

Kubernetes events give you a real-time view of what the system is doing.

```bash
# In one terminal, watch events
kubectl get events --watch --field-selector involvedObject.kind=Pod

# In another terminal, trigger some self-healing actions
curl -X POST http://localhost/crash
```

You will see events like:

```
LAST SEEN   TYPE      REASON      OBJECT                             MESSAGE
0s          Normal    Killing     pod/fastapi-k8s-7f8b9c6d4-2nxkl   Stopping container fastapi-k8s
0s          Normal    Pulled      pod/fastapi-k8s-7f8b9c6d4-2nxkl   Container image already present
0s          Normal    Created     pod/fastapi-k8s-7f8b9c6d4-2nxkl   Created container fastapi-k8s
0s          Normal    Started     pod/fastapi-k8s-7f8b9c6d4-2nxkl   Started container fastapi-k8s
```

!!! tip
    Events are invaluable for debugging. If a pod is not starting, not becoming ready, or behaving unexpectedly, `kubectl describe pod <name>` shows the events for that specific pod at the bottom of the output.

## Pod Disruption Budgets (PDB)

A Pod Disruption Budget limits how many pods can be simultaneously unavailable during **voluntary disruptions** -- operations like node drains, cluster upgrades, or manual pod deletions.

### Why PDBs matter

Without a PDB, a `kubectl drain` (used during node maintenance) could evict all your pods at once, causing an outage. A PDB tells Kubernetes: "You can disrupt my pods, but you must keep at least N of them running."

### Two configuration options

**minAvailable** -- The minimum number of pods that must remain available:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-k8s-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: fastapi-k8s
```

**maxUnavailable** -- The maximum number of pods that can be unavailable:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-k8s-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: fastapi-k8s
```

Both can be specified as an absolute number or a percentage (e.g., `maxUnavailable: "25%"`).

### Voluntary vs involuntary disruptions

PDBs only protect against **voluntary** disruptions:

| Voluntary (PDB protects) | Involuntary (PDB does not protect) |
|---|---|
| `kubectl drain node` | Node hardware failure |
| `kubectl delete pod` | Kernel panic |
| Cluster autoscaler removing a node | OOMKill |
| Rolling update evictions | Container crash |

!!! warning
    A PDB with `minAvailable` equal to the replica count (e.g., `minAvailable: 5` with 5 replicas) will block all voluntary disruptions -- including node drains and cluster upgrades. Always leave room for at least one pod to be unavailable.

## Graceful Shutdown

When Kubernetes terminates a pod (whether due to scaling down, rolling updates, or manual deletion), it follows a sequence designed to let the application finish its work.

### The termination sequence

```
1. Pod marked for termination
        |
        v
2. Pod removed from Service endpoints
   (no new traffic)
        |
        v
3. preStop hook runs (if configured)
        |
        v
4. SIGTERM sent to PID 1 in the container
        |
        v
5. Application handles SIGTERM:
   - Stops accepting new connections
   - Finishes in-flight requests
   - Cleans up resources
        |
        v
6. terminationGracePeriodSeconds timer
   (default: 30 seconds)
        |
        v
7. If still running: SIGKILL (force kill)
```

### preStop hooks

A preStop hook runs a command before SIGTERM is sent. This is useful for actions like deregistering from a service registry or waiting for load balancers to drain:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["sleep", "5"]
```

The `sleep 5` pattern is common -- it gives the Service endpoints time to propagate the removal across all nodes before the application starts shutting down. Without this, some requests might still be routed to the pod during the brief window between endpoint removal and the load balancer update.

### terminationGracePeriodSeconds

This sets the maximum time between SIGTERM and SIGKILL:

```yaml
spec:
  terminationGracePeriodSeconds: 60   # default is 30
```

If your application needs more than 30 seconds to finish in-flight work (long-running API calls, large file uploads), increase this value.

### How uvicorn handles SIGTERM

Our FastAPI app runs on uvicorn, which handles SIGTERM gracefully by default:

1. Stops accepting new connections
2. Waits for in-flight requests to complete
3. Exits cleanly

You do not need to write any special signal-handling code for our application. The default behavior is correct.

## Summary

| Failure scenario | What Kubernetes does | Who acts |
|---|---|---|
| Container crashes | Restarts the container (same pod) | kubelet |
| Liveness probe fails 3x | Kills and restarts the container | kubelet |
| Readiness probe fails | Removes pod from Service endpoints | endpoint controller |
| Pod deleted | Creates new pod to maintain replica count | ReplicaSet controller |
| Node failure | Reschedules pods to healthy nodes | Deployment controller |

Self-healing is not just a feature -- it is the fundamental operating principle of Kubernetes. By declaratively specifying what should be running and letting controllers handle the "how," you get a system that recovers from failures automatically and keeps your application available with minimal human intervention.
