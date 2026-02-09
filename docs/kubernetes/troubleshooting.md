# Troubleshooting

When something goes wrong in Kubernetes, the error messages can be cryptic and the root cause is often several layers removed from the symptom. This guide provides a systematic methodology for diagnosing and fixing the most common problems you will encounter with our fastapi-k8s deployment.

## Debugging methodology

The most important thing is to have a systematic approach. Do not jump to conclusions -- follow the layers in order:

1. **Check pod status** -- Are pods running? Are they restarting? Are they stuck?
2. **Check events** -- What does Kubernetes say happened? Events tell you about scheduling, pulling images, starting containers, and failures.
3. **Check logs** -- What does the application say? Logs reveal crashes, exceptions, and configuration errors.
4. **Check the service** -- Is traffic reaching the pods? Are endpoints registered?
5. **Check networking** -- Can pods talk to each other? Is DNS working?

!!! tip "Start broad, narrow down"
    Always start with `kubectl get pods` to get the big picture. Then drill into the specific pod that is having trouble with `kubectl describe` and `kubectl logs`. Most problems are diagnosed within these three commands.

## Debugging flowchart

```
Problem reported
    |
    v
kubectl get pods -l app=fastapi-k8s
    |
    +-- Status: Pending
    |     |
    |     v
    |   kubectl describe pod <name>
    |     |
    |     +-- "Insufficient cpu/memory" --> Reduce requests or free up resources
    |     +-- "no nodes available"      --> Check node status (kubectl get nodes)
    |     +-- "FailedScheduling"        --> Check taints, tolerations, node selectors
    |     +-- "Unschedulable"           --> Node is cordoned (kubectl uncordon <node>)
    |
    +-- Status: ContainerCreating (stuck)
    |     |
    |     v
    |   kubectl describe pod <name>
    |     +-- "pulling image"           --> Slow or failed image pull
    |     +-- "MountVolume" error       --> PVC not bound, volume not found
    |
    +-- Status: ImagePullBackOff / ErrImagePull
    |     |
    |     v
    |   kubectl describe pod <name>
    |     +-- Wrong image name/tag      --> Fix image reference in k8s.yaml
    |     +-- imagePullPolicy issue     --> Set to "Never" for local images
    |     +-- Auth required             --> Create imagePullSecret
    |
    +-- Status: CrashLoopBackOff
    |     |
    |     v
    |   kubectl logs <name> --previous
    |     +-- Exception / traceback     --> Fix application code
    |     +-- Missing env var           --> Check ConfigMap / env section
    |     +-- Port already in use       --> Check containerPort
    |     +-- Module not found          --> Check Dockerfile / dependencies
    |
    +-- Status: OOMKilled
    |     |
    |     v
    |   kubectl describe pod <name>
    |     +-- Exit code 137             --> Increase memory limit
    |     +-- Repeated OOMKill          --> Check for memory leak
    |
    +-- Status: Running (but not working)
    |     |
    |     v
    |   kubectl logs <name>             --> Check for application errors
    |   kubectl get endpoints <svc>     --> Check if endpoints exist
    |   kubectl describe svc <name>     --> Check selector and ports
    |   kubectl port-forward <name> 8000:8000 --> Bypass service, test pod directly
    |
    +-- Status: Running (all healthy)
          |
          v
        Issue is external (DNS, client, firewall, ingress)
```

## Pod states in detail

Understanding what each pod status means helps you know where to look next.

### Pending

The pod has been accepted by the Kubernetes API server but has not been scheduled to a node yet. The scheduler is either still working on it or cannot find a suitable node.

**Common reasons:** insufficient resources on any node, unmet node selectors or affinity rules, taints without matching tolerations, unbound PersistentVolumeClaims.

### ContainerCreating

The pod has been scheduled to a node and Kubernetes is preparing the container -- pulling the image, setting up volumes, configuring the network. If a pod stays in this state for a long time, the image pull is probably slow or failing.

### Running

At least one container in the pod is running. This does not necessarily mean the application is healthy -- the container could be running but returning errors or not accepting connections. That is why readiness probes exist.

### Succeeded

All containers in the pod terminated with exit code 0. This is the normal final state for Jobs and batch workloads. You should not see this for our FastAPI deployment -- if you do, something is wrong.

### Failed

At least one container terminated with a non-zero exit code. Check logs and describe output for the specific error.

### Unknown

The state of the pod could not be determined, usually because communication with the node where the pod is running has been lost. On Docker Desktop, this can happen if the Docker engine is restarting.

### Terminating

The pod is being shut down. Kubernetes sends SIGTERM to the container, waits for the grace period (30 seconds by default), then sends SIGKILL if the container is still running.

!!! info "CrashLoopBackOff is not a pod state"
    `CrashLoopBackOff` appears in the STATUS column but it is technically a container state, not a pod phase. It means the container keeps crashing and Kubernetes is backing off on restarts (waiting longer between each attempt).

## CrashLoopBackOff in depth

This is the most common and frustrating issue you will encounter. The container starts, crashes, and Kubernetes restarts it -- but with increasing delay between restarts.

### Exponential backoff timing

| Restart | Delay before restart |
|---------|---------------------|
| 1st | 10 seconds |
| 2nd | 20 seconds |
| 3rd | 40 seconds |
| 4th | 80 seconds |
| 5th | 160 seconds |
| 6th+ | 300 seconds (5 min cap) |

The backoff resets after the container runs successfully for 10 minutes.

### Common causes

**Missing environment variables:**

```bash
$ kubectl logs fastapi-k8s-7f8b9c6d4-xj2kl --previous
Traceback (most recent call last):
  File "main.py", line 16, in <module>
    MAX_STRESS_SECONDS = int(os.environ["MAX_STRESS_SECONDS"])
KeyError: 'MAX_STRESS_SECONDS'
```

Fix: Ensure the ConfigMap exists and is referenced correctly in the deployment.

**Wrong port or command:**

The container starts but Kubernetes cannot reach the health check endpoint, causing the liveness probe to fail, which triggers a restart.

```bash
$ kubectl describe pod fastapi-k8s-7f8b9c6d4-xj2kl
# Events:
#   Warning  Unhealthy  Liveness probe failed: connection refused
```

Fix: Verify `containerPort` matches what uvicorn listens on (8000).

**Unhandled exceptions at startup:**

```bash
$ kubectl logs fastapi-k8s-7f8b9c6d4-xj2kl --previous
ModuleNotFoundError: No module named 'fastapi'
```

Fix: Check the Dockerfile -- make sure dependencies are installed in the final stage.

**Missing files or incorrect working directory:**

```bash
$ kubectl logs fastapi-k8s-7f8b9c6d4-xj2kl --previous
FileNotFoundError: [Errno 2] No such file or directory: 'main.py'
```

Fix: Check the Dockerfile's `WORKDIR` and `COPY` instructions.

### Debugging with --previous and exec

```bash
# See logs from the last crashed container instance
kubectl logs fastapi-k8s-7f8b9c6d4-xj2kl --previous

# If the container is currently running (between crashes), exec in to inspect
kubectl exec -it fastapi-k8s-7f8b9c6d4-xj2kl -- /bin/sh

# Check if the application files are present
kubectl exec -it fastapi-k8s-7f8b9c6d4-xj2kl -- ls -la /app

# Check environment variables
kubectl exec -it fastapi-k8s-7f8b9c6d4-xj2kl -- env | sort

# Try running the app manually to see the error
kubectl exec -it fastapi-k8s-7f8b9c6d4-xj2kl -- python main.py
```

!!! warning "exec timing"
    When a container is in CrashLoopBackOff, you only have a brief window to `exec` into it before it crashes again. If the backoff has reached 5 minutes, you might need to wait for the next restart attempt. Alternatively, you can temporarily change the container command to `sleep infinity` to keep it running while you debug.

## ImagePullBackOff

The kubelet cannot pull the container image. This is almost always a configuration issue.

### Wrong image name or tag

```bash
$ kubectl describe pod fastapi-k8s-7f8b9c6d4-xj2kl
# Events:
#   Warning  Failed   Failed to pull image "fastapi-k8s:v2":
#     rpc error: code = NotFound desc = failed to pull and unpack image
#     "docker.io/library/fastapi-k8s:v2": not found
```

Fix: Check the image name and tag in `k8s.yaml`. For our project, the image is `fastapi-k8s:latest`.

### imagePullPolicy for local images

On Docker Desktop, images built locally with `docker build` are available to Kubernetes without pushing to a registry. But you **must** set `imagePullPolicy: Never`:

```yaml
# Correct for Docker Desktop with local images
image: fastapi-k8s:latest
imagePullPolicy: Never

# Wrong -- Kubernetes will try to pull from Docker Hub
image: fastapi-k8s:latest
imagePullPolicy: Always
```

If `imagePullPolicy` is not set, Kubernetes defaults to `Always` for the `latest` tag and `IfNotPresent` for other tags. For local development, always set it explicitly to `Never`.

### Private registries

If you are pulling from a private container registry, you need an `imagePullSecret`:

```bash
# Create the secret
kubectl create secret docker-registry my-registry-secret \
  --docker-server=registry.example.com \
  --docker-username=myuser \
  --docker-password=mypass

# Reference it in the pod spec
# spec:
#   imagePullSecrets:
#     - name: my-registry-secret
```

!!! note "Not needed for Docker Desktop"
    Our project uses locally-built images with `imagePullPolicy: Never`, so image pull secrets are not relevant. You would only need this when deploying to a cloud cluster with a private registry.

### Quick fix checklist

1. Did you build the image? Run `make docker-build`
2. Is `imagePullPolicy: Never` set in `k8s.yaml`? (It is in our deployment.)
3. Is the image name and tag correct? Run `docker images | grep fastapi-k8s`
4. If using Docker Desktop, is the Kubernetes context pointing to Docker Desktop? Run `kubectl config current-context`

## Pending pods

A pod stays in Pending when the scheduler cannot find a node to place it on.

### Insufficient resources

This is the most common cause. The cluster does not have enough free CPU or memory to satisfy the pod's resource requests.

```bash
$ kubectl describe pod fastapi-k8s-7f8b9c6d4-xj2kl
# Events:
#   Warning  FailedScheduling  0/1 nodes are available:
#     1 Insufficient cpu, 1 Insufficient memory.
```

**How to fix:**

```bash
# Check what resources are available on the node
kubectl describe node docker-desktop | grep -A 5 "Allocated resources"

# Option 1: Reduce resource requests in k8s.yaml
# Option 2: Scale down other deployments to free up resources
kubectl get deployments --all-namespaces

# Option 3: Reduce the number of replicas
make scale N=3
```

### Node selectors and affinity

If the pod spec includes a `nodeSelector` or `nodeAffinity` that does not match any node:

```bash
$ kubectl describe pod <name>
# Events:
#   Warning  FailedScheduling  0/1 nodes are available:
#     1 node(s) didn't match Pod's node affinity/selector.
```

Our fastapi-k8s deployment does not use node selectors, but you might encounter this in other projects.

### Taints and tolerations

Nodes can be "tainted" to repel pods unless those pods have a matching "toleration." The Docker Desktop node typically does not have taints, but control-plane nodes in multi-node clusters do.

```bash
# Check node taints
kubectl describe node docker-desktop | grep Taints
```

### Unbound PersistentVolumeClaim

If a pod references a PVC that does not exist or is not bound to a PV:

```bash
$ kubectl describe pod <name>
# Events:
#   Warning  FailedScheduling  persistentvolumeclaim "my-pvc" not found
```

Our deployment does not use PVCs, but this is a common issue in stateful workloads.

## OOMKilled

The container tried to use more memory than its `resources.limits.memory` allows. The kernel kills the process with SIGKILL (exit code 137).

### How to identify OOMKilled

```bash
$ kubectl get pods -l app=fastapi-k8s
NAME                          READY   STATUS      RESTARTS      AGE
fastapi-k8s-7f8b9c6d4-xj2kl  0/1     OOMKilled   3 (15s ago)   5m

$ kubectl describe pod fastapi-k8s-7f8b9c6d4-xj2kl
# ...
# Containers:
#   fastapi-k8s:
#     Last State:     Terminated
#       Reason:       OOMKilled
#       Exit Code:    137
```

### Common causes

- **Memory limit is too low** -- The application legitimately needs more memory than the limit allows. Increase `resources.limits.memory` in `k8s.yaml`.
- **Memory leak** -- The application accumulates memory over time and eventually hits the limit. This requires code-level investigation.
- **Large request payloads** -- Processing a large request body or response can temporarily spike memory.

### How to fix

```bash
# Check actual memory usage of running pods
kubectl top pods -l app=fastapi-k8s

# If pods are using 120Mi and the limit is 128Mi, they are dangerously close
# Increase the limit with headroom:
# resources:
#   limits:
#     memory: "256Mi"
```

!!! warning "Exit code 137"
    Exit code 137 always means SIGKILL (128 + signal 9). In Kubernetes, this almost always means OOMKilled. Check `kubectl describe pod` to confirm -- the `Reason` field will say `OOMKilled`.

## Service not reachable

You have pods running but `curl http://localhost` times out or refuses connections.

### Step 1: Check the service exists

```bash
$ kubectl get svc fastapi-k8s
NAME          TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
fastapi-k8s   LoadBalancer   10.96.45.123   localhost      80:31234/TCP   5m
```

If the service does not exist, redeploy: `make deploy`.

### Step 2: Check endpoints

Endpoints connect the service to pods. If no endpoints exist, the service has no pods to route to.

```bash
$ kubectl get endpoints fastapi-k8s
NAME          ENDPOINTS                                   AGE
fastapi-k8s   10.1.0.15:8000,10.1.0.16:8000,...          5m
```

If the ENDPOINTS column is empty (shows `<none>`), the problem is a selector mismatch or no ready pods.

### Step 3: Verify selector match

The service selector must match the pod labels exactly.

```bash
# Check service selector
$ kubectl describe svc fastapi-k8s | grep Selector
Selector:          app=fastapi-k8s

# Check pod labels
$ kubectl get pods -l app=fastapi-k8s --show-labels
NAME                          READY   STATUS    LABELS
fastapi-k8s-7f8b9c6d4-xj2kl  1/1     Running   app=fastapi-k8s,pod-template-hash=7f8b9c6d4
```

The `app=fastapi-k8s` label must be present on both the service selector and the pod labels.

### Step 4: Check port configuration

The service's `targetPort` must match the container's `containerPort`:

```yaml
# In the Service
ports:
  - port: 80            # External port (what you curl)
    targetPort: 8000     # Must match containerPort

# In the Deployment
ports:
  - containerPort: 8000  # What uvicorn listens on
```

If these do not match, the service routes traffic to the wrong port and the connection is refused.

### Step 5: Check if pods are ready

Only pods that pass their readiness probe receive traffic from the service. If all pods are not ready, the service has no endpoints.

```bash
$ kubectl get pods -l app=fastapi-k8s
NAME                          READY   STATUS    RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-xj2kl  0/1     Running   0          5m
```

`READY 0/1` means the readiness probe is failing. Check if someone called `/ready/disable`:

```bash
# Bypass the service and test the pod directly
kubectl port-forward fastapi-k8s-7f8b9c6d4-xj2kl 8001:8000 &
curl http://localhost:8001/ready
# If it returns {"status": "not ready"}, re-enable it:
curl -X POST http://localhost:8001/ready/enable
```

## DNS issues

Pods communicate with services using DNS names like `fastapi-k8s.default.svc.cluster.local`. If DNS is broken, inter-service communication fails.

### Testing DNS from inside a pod

```bash
# Exec into a running pod
kubectl exec -it fastapi-k8s-7f8b9c6d4-xj2kl -- /bin/sh

# Test DNS resolution (if nslookup is available)
nslookup fastapi-k8s.default.svc.cluster.local

# Alternative: use wget or curl to test
wget -qO- http://fastapi-k8s.default.svc.cluster.local/health
```

### Checking CoreDNS

Kubernetes uses CoreDNS for cluster DNS. If it is down, all DNS resolution fails:

```bash
# Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns
```

### Common DNS problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `nslookup: can't resolve` | CoreDNS is down or misconfigured | Restart CoreDNS pods |
| Slow DNS resolution | CoreDNS is overloaded | Check CoreDNS resource usage with `kubectl top` |
| DNS works inside pods but not from host | Expected behavior | Use `kubectl port-forward` or LoadBalancer service from the host |

## Common kubectl debugging commands

### kubectl get -- overview of resources

```bash
# Pods with extra detail (node, IP)
kubectl get pods -l app=fastapi-k8s -o wide

# All resources for our app
kubectl get all -l app=fastapi-k8s

# Watch for changes in real-time
kubectl get pods -l app=fastapi-k8s -w

# Sort pods by restart count (find the unstable ones)
kubectl get pods -l app=fastapi-k8s --sort-by='.status.containerStatuses[0].restartCount'

# Filter by status
kubectl get pods --field-selector=status.phase=Failed
```

### kubectl describe -- detailed resource information

```bash
# Pod details including events, conditions, resource usage
kubectl describe pod <pod-name>

# Service details including endpoints and selector
kubectl describe svc fastapi-k8s

# Node details including capacity, allocatable resources, and running pods
kubectl describe node docker-desktop

# Deployment details including rollout strategy and conditions
kubectl describe deployment fastapi-k8s
```

### kubectl logs -- application output

```bash
# Current logs
kubectl logs <pod-name>

# Logs from the previous (crashed) container
kubectl logs <pod-name> --previous

# Follow logs in real-time
kubectl logs <pod-name> -f

# Logs from the last 5 minutes
kubectl logs <pod-name> --since=5m

# Logs from the last 100 lines
kubectl logs <pod-name> --tail=100

# Logs from all pods with a specific label
kubectl logs -l app=fastapi-k8s
```

### kubectl exec -- run commands inside a container

```bash
# Interactive shell
kubectl exec -it <pod-name> -- /bin/sh

# Run a single command
kubectl exec <pod-name> -- env

# Check network connectivity from inside the pod
kubectl exec <pod-name> -- wget -qO- http://fastapi-k8s/health

# Check what process is running
kubectl exec <pod-name> -- ps aux
```

### kubectl port-forward -- direct access to a pod

```bash
# Forward local port 8001 to pod port 8000
kubectl port-forward <pod-name> 8001:8000

# Then in another terminal:
curl http://localhost:8001/health
```

### kubectl top -- resource usage (requires metrics-server)

```bash
# Pod resource usage
kubectl top pods -l app=fastapi-k8s

# Node resource usage
kubectl top nodes

# Sort by CPU usage
kubectl top pods -l app=fastapi-k8s --sort-by=cpu

# Sort by memory usage
kubectl top pods -l app=fastapi-k8s --sort-by=memory
```

### kubectl events -- cluster events

```bash
# Recent events in default namespace, sorted by time
kubectl get events --sort-by='.lastTimestamp'

# Events for a specific pod
kubectl get events --field-selector involvedObject.name=<pod-name>

# Watch for new events
kubectl get events -w
```

## Useful flags

These flags work across many kubectl commands and are invaluable for debugging:

| Flag | Usage | Example |
|------|-------|---------|
| `--previous` | Show logs from the previous container instance (after a crash) | `kubectl logs <pod> --previous` |
| `--since=5m` | Show logs from the last N minutes/hours | `kubectl logs <pod> --since=1h` |
| `-o wide` | Show additional columns (node, IP, etc.) | `kubectl get pods -o wide` |
| `-o yaml` | Full resource definition in YAML (great for seeing defaults Kubernetes filled in) | `kubectl get pod <pod> -o yaml` |
| `-o json` | Full resource definition in JSON | `kubectl get pod <pod> -o json` |
| `--sort-by` | Sort output by a JSON path expression | `kubectl get pods --sort-by='.metadata.creationTimestamp'` |
| `--field-selector` | Filter resources by field values | `kubectl get pods --field-selector=status.phase=Running` |
| `-l` | Filter by label | `kubectl get pods -l app=fastapi-k8s` |
| `-w` | Watch for changes | `kubectl get pods -w` |
| `-f` | Follow logs | `kubectl logs <pod> -f` |
| `--all-namespaces` / `-A` | Show resources across all namespaces | `kubectl get pods -A` |

## When to use kubectl port-forward

The `kubectl port-forward` command creates a direct tunnel from your machine to a specific pod, bypassing the Service entirely. This is invaluable for debugging because it lets you isolate whether the problem is with the pod itself or with the Service/networking layer.

**Use port-forward when:**

- The Service is not reachable but pods are running -- test the pod directly to confirm it is healthy
- You need to debug a specific pod out of many replicas -- the Service load-balances, but port-forward hits one specific pod
- You want to access a pod that is not exposed via a Service (e.g., a database pod)
- You need to test with traffic that bypasses the readiness check -- the Service only routes to ready pods, but port-forward works regardless

```bash
# Forward to a specific pod
kubectl port-forward fastapi-k8s-7f8b9c6d4-xj2kl 8001:8000 &

# Now test the pod directly
curl http://localhost:8001/health
curl http://localhost:8001/ready
curl http://localhost:8001/info

# If these work but curl http://localhost/ does not, the problem is
# with the Service (selector, port, or readiness), not the application.
```

!!! tip "Debugging the Service vs the pod"
    If `port-forward` to the pod works but the Service does not, check: (1) service selector matches pod labels, (2) targetPort matches containerPort, (3) pods are passing readiness probes. If `port-forward` also fails, the problem is in the application itself -- check logs.
