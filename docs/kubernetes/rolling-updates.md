# Rolling Updates and Deployment Strategies

Rolling updates let you deploy a new version of your app with **zero downtime**. Kubernetes gradually replaces old pods with new ones, ensuring that your application remains available throughout the entire process.

## Why zero-downtime deployments matter

Every deployment is a risk. If your app goes offline during an update -- even for a few seconds -- the impact can be significant:

- **User experience** -- Users hitting a 502 or connection timeout will lose trust in your product. A shopping cart abandoned during a deploy is revenue lost.
- **SLAs and uptime commitments** -- If you have promised 99.9% uptime, that gives you roughly 8.7 hours of downtime per year. A 30-second deploy window, done daily, eats into that budget fast.
- **Business impact** -- Downstream services that depend on your API will fail. Webhook deliveries will be missed. Background jobs will error out.

Zero-downtime deployments remove the "deploy window" from your operational vocabulary. You can ship changes at any time -- during peak traffic, during business hours, multiple times a day -- without coordinating maintenance windows.

## How rolling updates work internally

When you update a Deployment (change the image, environment variables, or any field in the pod template), Kubernetes does not modify existing pods. Instead, it orchestrates a controlled transition:

1. **A new ReplicaSet is created.** Kubernetes creates a second ReplicaSet with the updated pod template. The old ReplicaSet still exists and manages the current pods.
2. **New pods are scheduled.** The new ReplicaSet begins creating pods according to `maxSurge`. These pods go through the usual lifecycle: Pending, ContainerCreating, Running.
3. **Readiness probes gate traffic.** A new pod does not receive traffic until its readiness probe passes. This is critical -- it prevents half-started pods from serving requests.
4. **Old pods are terminated.** Once a new pod is ready, Kubernetes terminates an old pod (respecting `maxUnavailable`). The old pod receives a SIGTERM, has a grace period to finish in-flight requests, and then is killed.
5. **Repeat until complete.** Steps 2-4 repeat until the new ReplicaSet has the desired number of replicas and the old ReplicaSet is scaled to zero.

```
Step 1:  [v1] [v1] [v1] [v1] [v1]        <- all old version (old ReplicaSet: 5)
Step 2:  [v1] [v1] [v1] [v1] [v1] [v2]   <- new pod created (surge: +1)
Step 3:  [v1] [v1] [v1] [v1] [v2]        <- old pod terminated after new is ready
Step 4:  [v1] [v1] [v1] [v1] [v2] [v2]   <- another new pod created
Step 5:  [v1] [v1] [v1] [v2] [v2]        <- another old pod terminated
  ...
Final:   [v2] [v2] [v2] [v2] [v2]        <- all new version (new ReplicaSet: 5)
```

At every step, some pods are handling traffic. Users never see downtime.

!!! info "Old ReplicaSets are kept around"
    Kubernetes does not delete the old ReplicaSet after a successful rollout. It scales it to zero replicas and keeps it in history. This is what makes rollbacks instant -- Kubernetes just scales the old ReplicaSet back up.

## RollingUpdate strategy parameters

The `RollingUpdate` strategy has two parameters that control the pace and safety of the rollout:

### maxSurge

**How many extra pods can exist above the desired replica count during an update.**

- Can be an absolute number (e.g., `1`) or a percentage (e.g., `25%`).
- Higher values mean faster rollouts because more new pods are created in parallel.
- Requires extra cluster resources during the update (CPU, memory).

### maxUnavailable

**How many pods can be unavailable (not ready) during an update.**

- Can be an absolute number or a percentage.
- Higher values mean faster rollouts but with reduced capacity.
- Setting this to `0` means every old pod must stay running until its replacement is ready.

### maxSurge and maxUnavailable combinations

The interplay between these two parameters determines the rollout behavior. Here is a comparison for a Deployment with 5 replicas:

| maxSurge | maxUnavailable | Max pods | Min available | Speed | Safety | Use case |
|----------|----------------|----------|---------------|-------|--------|----------|
| 1 | 0 | 6 | 5 | Slow | Highest | Production APIs (our config) |
| 0 | 1 | 5 | 4 | Slow | High | Resource-constrained clusters |
| 1 | 1 | 6 | 4 | Medium | Medium | General workloads |
| 2 | 0 | 7 | 5 | Fast | High | When you have spare capacity |
| 25% | 25% | 7 | 4 | Fast | Medium | Large Deployments (default) |
| 5 | 0 | 10 | 5 | Fastest | High | "Just get it done" with resources |

!!! warning "You cannot set both to zero"
    Setting both `maxSurge: 0` and `maxUnavailable: 0` is invalid. Kubernetes would have no way to make progress -- it cannot create new pods (surge is 0) and it cannot remove old pods (unavailable is 0).

### Trade-offs: fast vs safe

**Fast rollouts** (high `maxSurge`, high `maxUnavailable`):

- More new pods are created simultaneously.
- Old pods are removed sooner.
- The rollout completes quickly.
- Risk: if the new version is broken, more users are affected before you notice.

**Safe rollouts** (low `maxSurge`, zero `maxUnavailable`):

- One pod at a time is replaced.
- Full capacity is maintained throughout.
- The rollout takes longer.
- Benefit: if the new version is broken, only a fraction of traffic hits it, and the rollout stalls when the new pod fails readiness.

## Recreate strategy

The `Recreate` strategy is the simpler alternative: kill all old pods first, then create all new pods.

```yaml
spec:
  strategy:
    type: Recreate
```

This causes **downtime** between the old pods terminating and the new pods becoming ready. Use it only when:

- **Breaking schema changes** -- Your database migration is not backward-compatible, and having v1 and v2 running simultaneously would cause data corruption.
- **Single-instance apps** -- Some applications (certain databases, legacy apps with file locks) cannot have two instances running at once.
- **Dev/staging environments** -- Downtime does not matter, and you want the simplest possible deploy.
- **Volume constraints** -- If your pods use a `ReadWriteOnce` PersistentVolume, only one pod can mount it at a time.

!!! tip "Prefer RollingUpdate for stateless APIs"
    Our FastAPI app is completely stateless -- it does not write to a database or filesystem. RollingUpdate is always the right choice for stateless services like this.

## Our rolling update strategy

Our `k8s.yaml` Deployment has an explicit rolling update configuration:

```yaml
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

This is the **safest** configuration:

- `maxSurge: 1` -- During an update, Kubernetes creates at most one extra pod. With 5 replicas, there will be at most 6 pods running at any point during the rollout.
- `maxUnavailable: 0` -- No existing pod is terminated until its replacement is fully ready. The cluster always has at least 5 pods serving traffic.

### How readiness probes gate the rollout

Our Deployment also defines a readiness probe:

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 2
  periodSeconds: 5
```

This probe is what makes `maxUnavailable: 0` meaningful. When a new pod starts, Kubernetes will not route traffic to it -- and will not terminate an old pod -- until the readiness probe at `/ready` returns HTTP 200. If the new version has a bug that prevents startup, the rollout stalls and all traffic continues going to the healthy old pods.

## Walkthrough: deploy a new version

Our app exposes `GET /version` which returns the current `APP_VERSION` and the responding pod's hostname. This makes it easy to observe a rolling update in real time.

```bash
# 1. Check the current version
curl -s http://localhost/version
# {"version":"1.0.0","server":"fastapi-k8s-abc12"}

# 2. Edit main.py: change APP_VERSION = "1.0.0" to APP_VERSION = "2.0.0"

# 3. Rebuild the Docker image
make docker-build

# 4. Trigger a rolling restart (picks up the new image)
make restart

# 5. Immediately start curling /version in a loop to see the transition
for i in $(seq 1 20); do
  curl -s http://localhost/version
  echo
  sleep 1
done
# {"version":"1.0.0","server":"fastapi-k8s-old-abc12"}
# {"version":"1.0.0","server":"fastapi-k8s-old-def34"}
# {"version":"2.0.0","server":"fastapi-k8s-new-ghi56"}   <- new pod is ready!
# {"version":"1.0.0","server":"fastapi-k8s-old-abc12"}
# {"version":"2.0.0","server":"fastapi-k8s-new-ghi56"}
# ...responses gradually shift to 2.0.0...
# {"version":"2.0.0","server":"fastapi-k8s-new-jkl78"}
# {"version":"2.0.0","server":"fastapi-k8s-new-mno90"}   <- all new version

# 6. Watch the rollout in another terminal
make rollout-status
# Waiting for deployment "fastapi-k8s" rollout to finish: 2 out of 5 new replicas have been updated...
# Waiting for deployment "fastapi-k8s" rollout to finish: 3 out of 5 new replicas have been updated...
# deployment "fastapi-k8s" successfully rolled out
```

!!! note "Mixed versions during rollout"
    During the rollout, the Service load-balances across both old and new pods. Clients will see responses from both versions. This is normal and expected. Your application should be designed so that v1 and v2 can coexist -- this is sometimes called "backward-compatible deploys."

## Rollout history

Every time you change the pod template in a Deployment, Kubernetes creates a new **revision**. You can inspect the history:

```bash
# View rollout history
kubectl rollout history deployment fastapi-k8s
# REVISION  CHANGE-CAUSE
# 1         <none>
# 2         <none>
# 3         <none>

# View details of a specific revision
kubectl rollout history deployment fastapi-k8s --revision=2
```

A new revision is triggered by any change to `spec.template`, including:

- Changing the container image.
- Adding or modifying environment variables.
- Updating resource requests/limits.
- Modifying labels on the pod template.
- Running `kubectl rollout restart` (which adds a restart annotation).

!!! tip "Annotate your revisions"
    By default, the CHANGE-CAUSE column is empty. You can annotate a Deployment to record why a change was made:

    ```bash
    kubectl annotate deployment fastapi-k8s kubernetes.io/change-cause="Bumped to v2.0.0"
    ```

    This makes `kubectl rollout history` much more useful in practice.

Kubernetes keeps the last 10 revisions by default (controlled by `spec.revisionHistoryLimit`). Older ReplicaSets are garbage collected.

## Rollback

If a new version is broken, you can instantly roll back to the previous version.

### Undo the last rollout

```bash
kubectl rollout undo deployment fastapi-k8s
```

This scales up the previous ReplicaSet and scales down the current one. Because the old ReplicaSet already exists with the correct pod template, the rollback is fast -- Kubernetes does not need to pull images or rebuild anything.

### Rollback to a specific revision

```bash
# First, check the history to find the revision number
kubectl rollout history deployment fastapi-k8s

# Roll back to revision 2
kubectl rollout undo deployment fastapi-k8s --to-revision=2
```

### Automatic rollback (sort of)

Kubernetes does not have a built-in "automatic rollback" feature, but the combination of readiness probes and `maxUnavailable: 0` provides a safety net:

- If the new pods **crash on startup** (e.g., a syntax error, missing dependency), they will never become ready.
- The rollout will stall because Kubernetes will not terminate old pods until the new one is ready.
- The old pods continue serving traffic as if nothing happened.
- You will see the rollout stuck in a "waiting" state, giving you time to investigate and decide whether to fix forward or roll back.

```bash
# Check if a rollout is stuck
kubectl rollout status deployment fastapi-k8s --timeout=60s
# If it times out, something is wrong with the new version

# Check why new pods are not ready
kubectl get pods -l app=fastapi-k8s
kubectl describe pod <failing-pod-name>
kubectl logs <failing-pod-name>

# Roll back
kubectl rollout undo deployment fastapi-k8s
```

!!! warning "Readiness probes are your safety net"
    Without readiness probes, Kubernetes considers a pod "ready" as soon as its container starts. A broken version would be rolled out fully before you even notice. Always configure readiness probes for production workloads.

## Blue-green deployments

Blue-green is a deployment strategy where you run two identical environments -- "blue" (current) and "green" (new) -- and switch traffic between them instantly.

### How it works with Kubernetes

1. You have a Deployment called `fastapi-k8s-blue` running the current version with the label `version: blue`.
2. The Service selects pods with `app: fastapi-k8s, version: blue`.
3. You create a second Deployment called `fastapi-k8s-green` with the new version and label `version: green`.
4. Wait for all green pods to be ready and tested.
5. Update the Service selector to `version: green`. Traffic switches instantly.
6. If something goes wrong, switch the selector back to `version: blue`.

```yaml
# Service -- switch traffic by changing the version selector
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
spec:
  selector:
    app: fastapi-k8s
    version: blue      # Change to "green" to switch traffic
  ports:
    - port: 80
      targetPort: 8000
```

### Pros and cons

| Aspect | Blue-green |
|--------|-----------|
| Zero downtime | Yes -- traffic switches instantly |
| Rollback speed | Instant -- change the selector back |
| Resource cost | 2x -- both versions run simultaneously |
| Traffic splitting | All-or-nothing (no gradual shift) |
| Complexity | Higher -- two Deployments, manual selector management |
| Testing before switch | You can test the green environment before routing traffic |

!!! note "Blue-green is overkill for most apps"
    Kubernetes rolling updates with readiness probes achieve the same zero-downtime result with less complexity and half the resources. Blue-green is most useful when you need to test the new version in a production-like environment before any user traffic hits it.

## Canary deployments

A canary deployment sends a small percentage of traffic to the new version first. If it behaves well (low error rate, acceptable latency), you gradually increase the percentage until the new version handles all traffic.

### Basic canary with Kubernetes

The simplest approach uses two Deployments with the same label but different replica counts:

```yaml
# Stable -- 9 replicas of v1
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-k8s-stable
spec:
  replicas: 9
  template:
    metadata:
      labels:
        app: fastapi-k8s     # Same label -- Service selects both
    spec:
      containers:
        - image: fastapi-k8s:v1

# Canary -- 1 replica of v2 (roughly 10% of traffic)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-k8s-canary
spec:
  replicas: 1
  template:
    metadata:
      labels:
        app: fastapi-k8s     # Same label -- Service selects both
    spec:
      containers:
        - image: fastapi-k8s:v2
```

The Service selects `app: fastapi-k8s`, so it load-balances across all 10 pods. Roughly 10% of traffic goes to the canary. To increase the canary percentage, scale up the canary Deployment and scale down the stable one.

### Limitations of basic canary

- Traffic splitting is based on pod count, not true percentages. You cannot easily do "send 1% of traffic to the canary."
- No automatic analysis -- you manually decide whether the canary is healthy.
- No automatic rollback if the canary starts failing.

### Progressive delivery tools

For more sophisticated canary deployments, consider these tools:

- **Argo Rollouts** -- A Kubernetes controller that replaces Deployments with a `Rollout` resource. Supports canary with percentage-based traffic splitting, automated analysis (Prometheus metrics, web hooks), and automatic rollback. Works with service meshes like Istio, Linkerd, and AWS ALB.
- **Flagger** -- Another progressive delivery operator that works with Istio, Linkerd, App Mesh, and other service meshes. Automates canary analysis, A/B testing, and blue-green deployments.
- **Istio / Linkerd** -- Service meshes that provide fine-grained traffic splitting at the network level. You can route exactly 5% of traffic to the canary regardless of replica count.

!!! tip "Start simple"
    For a project like fastapi-k8s running on Docker Desktop, the built-in rolling update strategy is more than sufficient. Canary deployments and progressive delivery tools add value when you are running at scale with hundreds of pods and need fine-grained control over traffic shifting.

## Summary

| Strategy | Downtime | Rollback | Resource overhead | Complexity |
|----------|----------|----------|-------------------|------------|
| RollingUpdate | None | `kubectl rollout undo` | +maxSurge pods | Low (built-in) |
| Recreate | Yes | Redeploy old version | None | Lowest |
| Blue-green | None | Switch selector | 2x replicas | Medium |
| Canary | None | Scale down canary | +canary replicas | High |

For our fastapi-k8s project, the built-in `RollingUpdate` strategy with `maxSurge: 1` and `maxUnavailable: 0` gives us the safest zero-downtime deploys with minimal configuration. Combined with readiness probes, it ensures that broken versions never receive traffic and that rollouts stall safely if something goes wrong.
