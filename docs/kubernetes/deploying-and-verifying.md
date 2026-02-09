# Deploying & Verifying

This page walks through deploying the fastapi-k8s application to your local Kubernetes cluster, understanding what happens behind the scenes, reading the output, verifying everything works, and debugging when it does not.

---

## Prerequisites

Before deploying, make sure you have:

1. **Docker Desktop** installed and running, with Kubernetes enabled (Settings > Kubernetes > Enable Kubernetes)
2. **kubectl** configured and pointing to your Docker Desktop cluster:
    ```bash
    kubectl config current-context
    # Expected: docker-desktop
    ```
3. **The Docker image built** -- Kubernetes needs the image to exist locally before it can create containers

!!! warning
    The most common first-deployment failure is forgetting to build the Docker image. Kubernetes cannot pull `fastapi-k8s:latest` from a remote registry because the Deployment uses `imagePullPolicy: Never`, which tells it to only use images already present in the local Docker daemon.

---

## Step-by-step deployment

### 1. Build the Docker image

```bash
make docker-build
```

This runs `docker build -t fastapi-k8s:latest .` which builds the image using the multi-stage `Dockerfile` and tags it as `fastapi-k8s:latest`. Since Docker Desktop shares its daemon with the Kubernetes node, the image is immediately available to the cluster.

### 2. Deploy to Kubernetes

```bash
make deploy
```

This runs `kubectl apply -f k8s.yaml`, which creates three resources. You should see:

```
configmap/fastapi-config created
deployment.apps/fastapi-k8s created
service/fastapi-k8s created
```

If the resources already exist (for example, you are redeploying after a code change), you will see `configured` instead of `created`:

```
configmap/fastapi-config unchanged
deployment.apps/fastapi-k8s configured
service/fastapi-k8s unchanged
```

### 3. Check status

```bash
make status
```

This runs `kubectl get pods,svc -l app=fastapi-k8s` to show all pods and services with the label `app=fastapi-k8s`. Wait a few seconds for pods to start -- they will transition from `ContainerCreating` to `Running`.

---

## What happens behind the scenes

When you run `kubectl apply -f k8s.yaml`, a precise sequence of events unfolds inside the cluster:

1. **kubectl sends the manifests to the API server.** The API server validates the YAML against the Kubernetes API schema and authenticates your request.

2. **The API server stores the desired state in etcd.** etcd is the cluster's key-value database -- the single source of truth for what should exist.

3. **The Deployment controller notices the new Deployment.** It creates a ReplicaSet, which in turn creates the requested number of Pod objects (5 by default in this project).

4. **The scheduler assigns each Pod to a node.** On Docker Desktop there is only one node, so all pods land on the same node. On a multi-node cluster, the scheduler considers resource requests, node capacity, and affinity rules.

5. **The kubelet on each assigned node pulls the image and starts the container.** With `imagePullPolicy: Never`, it skips the pull and uses the local image directly.

6. **The kubelet begins running health probes.** The liveness probe (`/health`) starts after 3 seconds, then runs every 10 seconds. The readiness probe (`/ready`) starts after 2 seconds, then runs every 5 seconds. The pod is not added to the Service's endpoint list until the readiness probe succeeds.

7. **The Service controller creates an Endpoints object.** As each pod passes its readiness probe, its IP is added to the Service's endpoint list. Traffic from the LoadBalancer is distributed across these ready pods.

!!! info
    The entire process typically takes 5-15 seconds on Docker Desktop. On cloud providers it can take longer due to image pulls from a remote registry.

---

## Reading `kubectl get pods` output

```
NAME                          READY   STATUS    RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-5m9qr  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-8hjt2  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-kw4fn  1/1     Running   0          45s
fastapi-k8s-7f8b9c6d4-xj2kl  1/1     Running   0          45s
```

### Column-by-column breakdown

| Column | Example | Meaning |
|--------|---------|---------|
| `NAME` | `fastapi-k8s-7f8b9c6d4-2nxkl` | The pod name. Format is `<deployment>-<replicaset-hash>-<pod-hash>`. The ReplicaSet hash (`7f8b9c6d4`) changes when you update the Deployment spec (for example, changing the image). The pod hash (`2nxkl`) is unique per pod. |
| `READY` | `1/1` | Containers ready vs. total containers in the pod. `1/1` means the single container has passed its readiness probe. `0/1` means it has not yet passed or is failing the readiness probe. |
| `STATUS` | `Running` | The current phase of the pod. See the status table below. |
| `RESTARTS` | `0` | How many times the container has been restarted by the kubelet. A non-zero value usually means the container crashed or a liveness probe failed. |
| `AGE` | `45s` | Time since the pod was created. Displayed as `s`, `m`, `h`, or `d` depending on duration. |

### Common pod statuses

| Status | Meaning |
|--------|---------|
| `Pending` | The pod has been accepted by the cluster but is not running yet. The scheduler may be finding a node, or an image is being pulled. |
| `ContainerCreating` | The node is pulling the image and setting up the container. |
| `Running` | The container is running. This does not necessarily mean it is ready -- check the `READY` column. |
| `Completed` | The container exited successfully (exit code 0). Common for Jobs, not expected for long-running apps. |
| `CrashLoopBackOff` | The container keeps crashing and Kubernetes is applying an exponential backoff before restarting it again. |
| `Error` | The container exited with a non-zero exit code. |
| `ImagePullBackOff` | Kubernetes cannot pull the container image. Wrong image name, missing registry credentials, or the image does not exist. |
| `ErrImagePull` | First failure to pull the image (before backoff kicks in). |
| `Terminating` | The pod is shutting down (after a delete or during a rolling update). |
| `Evicted` | The node ran out of resources (disk, memory) and evicted this pod. |

!!! tip
    Add `-o wide` to see additional columns including the node name and pod IP address:
    ```bash
    kubectl get pods -l app=fastapi-k8s -o wide
    ```

---

## Reading `kubectl get svc` output

```
NAME          TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
fastapi-k8s   LoadBalancer   10.96.123.45   localhost     80:31234/TCP   2m
```

### Column-by-column breakdown

| Column | Example | Meaning |
|--------|---------|---------|
| `NAME` | `fastapi-k8s` | The Service name, as defined in `metadata.name` in `k8s.yaml`. |
| `TYPE` | `LoadBalancer` | The Service type. `LoadBalancer` provisions an external access point. Other types: `ClusterIP` (internal only), `NodePort` (exposes on every node's IP at a static port). |
| `CLUSTER-IP` | `10.96.123.45` | The virtual IP assigned inside the cluster. Other pods can reach this Service at `10.96.123.45:80` or via DNS at `fastapi-k8s.default.svc.cluster.local`. |
| `EXTERNAL-IP` | `localhost` | The externally routable address. On Docker Desktop, LoadBalancer Services always get `localhost`. On cloud providers (EKS, GKE, AKS), this is a real public IP or DNS name provisioned by the cloud's load balancer controller. |
| `PORT(S)` | `80:31234/TCP` | The port mapping. `80` is the external port (what you curl). `31234` is the NodePort automatically assigned. Internally, the Service routes to `targetPort: 8000` on the pods. |
| `AGE` | `2m` | Time since the Service was created. |

!!! note
    On Docker Desktop, `EXTERNAL-IP` shows `localhost`, so you access the app at `http://localhost/`. On cloud providers, this field may show `<pending>` for a minute while the load balancer is being provisioned.

---

## Verifying the deployment

Once `make status` shows all pods as `1/1 Running`, test each endpoint:

### Root endpoint

```bash
curl http://localhost/
```

Expected output:

```json
{"message":"Hello from fastapi-k8s!","server":"fastapi-k8s-7f8b9c6d4-2nxkl"}
```

The `server` field shows the pod hostname. Run the command multiple times -- the load balancer distributes requests across pods, so you will see different hostnames.

### Health check

```bash
curl http://localhost/health
```

Expected output:

```json
{"status":"healthy"}
```

This is the liveness probe endpoint. It always returns 200 unless the process is completely down.

### Configuration

```bash
curl http://localhost/config
```

Expected output:

```json
{"app_name":"fastapi-k8s","log_level":"info","max_stress_seconds":30}
```

These values come from the ConfigMap defined in `k8s.yaml`, injected as environment variables via `envFrom`.

### Version

```bash
curl http://localhost/version
```

Expected output:

```json
{"version":"1.0.0","server":"fastapi-k8s-7f8b9c6d4-5m9qr"}
```

### Pod info (Downward API)

```bash
curl http://localhost/info
```

Expected output:

```json
{
  "pod_name":"fastapi-k8s-7f8b9c6d4-2nxkl",
  "pod_ip":"10.1.0.15",
  "node_name":"docker-desktop",
  "namespace":"default",
  "cpu_request":"1",
  "cpu_limit":"1",
  "memory_request":"67108864",
  "memory_limit":"134217728"
}
```

The metadata comes from the Kubernetes Downward API, which injects pod and resource information as environment variables.

---

## Using `make test`

The `make test` command automates the entire build-deploy-verify cycle:

```bash
make test
```

What it does, step by step:

1. **Builds the Docker image** (`docker build -t fastapi-k8s:latest .`)
2. **Deploys to Kubernetes** (`kubectl apply -f k8s.yaml`)
3. **Waits for rollout** (`kubectl rollout status deployment/fastapi-k8s --timeout=60s`) -- this blocks until all pods are ready or the timeout is reached
4. **Shows pod status** (`kubectl get pods -l app=fastapi-k8s`)
5. **Tests every endpoint** -- curls `/`, `/health`, `/ready`, `/info`, `/config`, `/version`, `/stress?seconds=1`, and toggles readiness with `/ready/disable` and `/ready/enable`

If all requests succeed (exit code 0 from `curl -sf`), you see `=== All tests passed ===` at the end.

!!! tip
    Run `make test` after every change to `main.py`, `Dockerfile`, or `k8s.yaml` to confirm nothing is broken. It is a quick integration test that catches most deployment issues.

---

## Debugging commands in depth

When things go wrong, these commands help you find the root cause.

### kubectl describe pod -- the full picture

```bash
kubectl describe pod <pod-name>
```

This produces a long output with several sections. Here is what to look at:

**Metadata section:**

```
Name:         fastapi-k8s-7f8b9c6d4-2nxkl
Namespace:    default
Node:         docker-desktop/192.168.65.4
Labels:       app=fastapi-k8s
              pod-template-hash=7f8b9c6d4
```

Shows the pod name, which node it is running on, and its labels.

**Conditions section:**

```
Conditions:
  Type              Status
  Initialized       True
  Ready             True
  ContainersReady   True
  PodScheduled      True
```

All four should be `True` for a healthy pod. `Ready: False` means the readiness probe is failing. `PodScheduled: False` means the scheduler could not place the pod on a node.

**Containers section:**

```
Containers:
  fastapi-k8s:
    Image:          fastapi-k8s:latest
    Port:           8000/TCP
    State:          Running
      Started:      Mon, 01 Jan 2025 12:00:00 +0000
    Ready:          True
    Restart Count:  0
    Limits:
      cpu:     200m
      memory:  128Mi
    Requests:
      cpu:     50m
      memory:  64Mi
    Liveness:   http-get http://:8000/health delay=3s timeout=1s period=10s
    Readiness:  http-get http://:8000/ready delay=2s timeout=1s period=5s
```

Shows the container image, current state, resource limits, and probe configuration.

**Events section (most important for debugging):**

```
Events:
  Type     Reason     Age   From               Message
  ----     ------     ----  ----               -------
  Normal   Scheduled  60s   default-scheduler  Successfully assigned default/fastapi-k8s-... to docker-desktop
  Normal   Pulled     59s   kubelet            Container image "fastapi-k8s:latest" already present on machine
  Normal   Created    59s   kubelet            Created container fastapi-k8s
  Normal   Started    58s   kubelet            Started container fastapi-k8s
```

Events are listed chronologically. Look here for errors like `Failed to pull image`, `Back-off restarting failed container`, or `Unhealthy` (probe failures).

### kubectl logs -- container output

```bash
# Logs from a specific pod
kubectl logs fastapi-k8s-7f8b9c6d4-2nxkl

# Logs from ALL pods with the app label
kubectl logs -l app=fastapi-k8s

# Follow logs in real-time (like tail -f)
kubectl logs -l app=fastapi-k8s -f

# Logs from the PREVIOUS container (useful after a crash)
kubectl logs <pod-name> --previous

# Only the last 50 lines
kubectl logs <pod-name> --tail=50

# Logs since a specific duration
kubectl logs <pod-name> --since=5m
```

!!! note
    `kubectl logs -l app=fastapi-k8s` aggregates output from all matching pods but does not prefix lines with the pod name. For multi-pod log tailing with pod labels, consider using `stern` (see [Where to Go Next](next-steps.md)).

### kubectl exec -- running commands inside a container

```bash
# Get an interactive shell
kubectl exec -it <pod-name> -- /bin/bash

# Run a single command without entering the shell
kubectl exec <pod-name> -- env

# Check network connectivity from inside the pod
kubectl exec <pod-name> -- curl -s http://localhost:8000/health

# Check the filesystem
kubectl exec <pod-name> -- ls /app
```

The `--` separates kubectl flags from the command to run inside the container. The `-it` flags allocate an interactive terminal.

!!! warning
    If the container does not have `/bin/bash`, try `/bin/sh` instead. Slim images may not include common utilities like `curl` or `wget`.

### kubectl port-forward -- direct pod access

Port-forward lets you bypass the Service and connect directly to a specific pod:

```bash
# Forward local port 9000 to pod port 8000
kubectl port-forward <pod-name> 9000:8000

# Then in another terminal:
curl http://localhost:9000/health
```

This is useful for:

- Testing a specific pod when the Service is load-balancing across multiple pods
- Debugging a pod that is not passing its readiness probe (and therefore not receiving Service traffic)
- Accessing a pod that has no Service defined at all

You can also port-forward to a Service instead of a pod:

```bash
kubectl port-forward svc/fastapi-k8s 9000:80
```

### kubectl get events -- cluster-wide event log

```bash
# All events in the default namespace, sorted by time
kubectl get events --sort-by='.lastTimestamp'

# Only warning events
kubectl get events --field-selector type=Warning

# Events for a specific pod
kubectl get events --field-selector involvedObject.name=<pod-name>
```

Events capture scheduling decisions, image pulls, probe results, scaling actions, and errors. They are the first place to look when pods are not behaving as expected.

!!! tip
    Events are only retained for about 1 hour by default. If you need longer retention, consider a logging stack like the EFK stack (Elasticsearch + Fluentd + Kibana) or Loki + Grafana.

---

## Common first-deployment issues

### ImagePullBackOff -- forgot to build the image

**Symptoms:**

```
NAME                          READY   STATUS             RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  0/1     ImagePullBackOff   0          30s
```

**Cause:** Kubernetes cannot find the `fastapi-k8s:latest` image. Since `imagePullPolicy: Never` is set, it only looks in the local Docker daemon. If you did not run `make docker-build`, the image does not exist.

**Fix:**

```bash
make docker-build
# The pods will automatically retry pulling the image
```

If they do not recover on their own, delete them and let the Deployment recreate them:

```bash
kubectl delete pods -l app=fastapi-k8s
```

### Pending -- insufficient resources

**Symptoms:**

```
NAME                          READY   STATUS    RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  0/1     Pending   0          2m
```

**Cause:** The scheduler cannot find a node with enough CPU or memory to satisfy the pod's resource requests. This can happen if you are running many other workloads on Docker Desktop or if the resource requests are too high for your machine.

**Diagnose:**

```bash
kubectl describe pod <pod-name>
# Look in Events for: "0/1 nodes are available: 1 Insufficient cpu"
```

**Fix:** Either free up resources by stopping other pods, or reduce the resource requests in `k8s.yaml`.

### CrashLoopBackOff -- application error

**Symptoms:**

```
NAME                          READY   STATUS             RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  0/1     CrashLoopBackOff   3          2m
```

**Cause:** The container starts but immediately crashes. Kubernetes restarts it, it crashes again, and Kubernetes starts backing off (waiting longer between restart attempts). Common causes: syntax error in `main.py`, missing dependency, bad environment variable.

**Diagnose:**

```bash
# Check the logs from the crashed container
kubectl logs <pod-name> --previous

# Check events for details
kubectl describe pod <pod-name>
```

**Fix:** Fix the application error, rebuild the image with `make docker-build`, then delete the broken pods:

```bash
kubectl delete pods -l app=fastapi-k8s
```

### CreateContainerConfigError -- bad ConfigMap reference

**Symptoms:**

```
NAME                          READY   STATUS                       RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-2nxkl  0/1     CreateContainerConfigError   0          15s
```

**Cause:** The Deployment references a ConfigMap (via `envFrom`) that does not exist. This happens if you deploy only the Deployment resource without the ConfigMap.

**Diagnose:**

```bash
kubectl describe pod <pod-name>
# Events will show: "configmap 'fastapi-config' not found"
```

**Fix:** Make sure you are deploying the full `k8s.yaml` (which includes the ConfigMap) with `make deploy`, not just a subset of it.

---

## Quick reference

| Task | Command |
|------|---------|
| Build image | `make docker-build` |
| Deploy everything | `make deploy` |
| Check status | `make status` |
| View logs | `make logs` |
| Full build + deploy + test | `make test` |
| Describe a pod | `kubectl describe pod <pod-name>` |
| Get a shell in a pod | `kubectl exec -it <pod-name> -- /bin/bash` |
| Port-forward to a pod | `kubectl port-forward <pod-name> 9000:8000` |
| View cluster events | `kubectl get events --sort-by='.lastTimestamp'` |
| Delete all pods (force restart) | `kubectl delete pods -l app=fastapi-k8s` |
| Remove everything | `make undeploy` |
