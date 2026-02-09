# Your First Deployment

Our Kubernetes configuration lives in a single file called `k8s.yaml`. It contains three resources separated by `---`: a **ConfigMap**, a **Deployment**, and a **Service**. Together, these three resources define everything Kubernetes needs to run and expose your FastAPI application.

This page walks through the complete YAML, field by field, so you understand exactly what each line does and how the three resources relate to each other.

---

## How the Three Resources Fit Together

Before diving into the YAML, it helps to understand the relationship between the three resources:

1. **ConfigMap** -- Stores application configuration (key-value pairs) outside of your container image. This keeps configuration separate from code.
2. **Deployment** -- Describes the desired state of your application: how many replicas to run, which container image to use, what environment variables to inject (pulling from the ConfigMap), and how to check if containers are healthy.
3. **Service** -- Provides a stable network endpoint that routes external traffic to whichever pods the Deployment is currently managing.

The data flows like this:

```
ConfigMap (config data)
    |
    v
Deployment (creates pods, injects ConfigMap as env vars)
    |
    v
Service (routes external traffic to the Deployment's pods)
```

The ConfigMap feeds environment variables into the Deployment's pods via `envFrom`. The Service finds the Deployment's pods using label selectors -- both the Deployment's pod template and the Service use the label `app: fastapi-k8s`, which is what ties them together.

---

## The Complete k8s.yaml

Below is the full file, split into its three resources with detailed annotations on every field.

### Resource 1: ConfigMap

```yaml
apiVersion: v1                    # Core API group -- ConfigMap has been in v1 since early K8s
kind: ConfigMap                   # Resource type: a key-value configuration store
metadata:
  name: fastapi-config            # Name used to reference this ConfigMap from other resources
  labels:
    app: fastapi-k8s              # Label for organizational purposes and filtering
data:                             # The actual key-value pairs stored in this ConfigMap
  APP_NAME: "fastapi-k8s"        # Application name -- used in logging and the /info endpoint
  LOG_LEVEL: "info"              # Uvicorn log level (debug, info, warning, error, critical)
  MAX_STRESS_SECONDS: "30"       # Maximum duration for the /stress endpoint (safety cap)
```

**What this does:** A ConfigMap is a Kubernetes-native way to store non-sensitive configuration data. Every key-value pair under `data:` becomes an environment variable when injected into a pod. All values must be strings -- that is why `"30"` is quoted even though it represents a number.

!!! tip "Why use a ConfigMap instead of hardcoding values?"
    ConfigMaps let you change application behavior without rebuilding your Docker image. You can update a ConfigMap and restart pods to pick up new values. This separates configuration from code, which is one of the [twelve-factor app](https://12factor.net/config) principles.

!!! note "ConfigMap values are always strings"
    Even numeric values like `MAX_STRESS_SECONDS` must be stored as strings in a ConfigMap. Your application code is responsible for parsing them into the appropriate type.

### Resource 2: Deployment

```yaml
apiVersion: apps/v1               # API group for Deployment resources (stable since K8s 1.9)
kind: Deployment                   # Resource type: manages a set of identical pods
metadata:
  name: fastapi-k8s                # Name of this Deployment (shown in kubectl get deployments)
  labels:
    app: fastapi-k8s               # Label on the Deployment itself (for filtering/selection)
spec:                              # The desired state of this Deployment
  replicas: 5                      # Number of identical pod copies to maintain at all times
  strategy:                        # How to handle updates when the Deployment changes
    type: RollingUpdate            # Replace pods gradually (not all at once)
    rollingUpdate:
      maxSurge: 1                  # Allow at most 1 extra pod above the desired 5 during updates
      maxUnavailable: 0            # Never take a pod down until its replacement is ready
  selector:
    matchLabels:
      app: fastapi-k8s             # The Deployment manages pods that have this label
  template:                        # Pod template -- the blueprint for every pod this Deployment creates
    metadata:
      labels:
        app: fastapi-k8s           # Label applied to each pod (MUST match selector.matchLabels)
    spec:
      containers:
        - name: fastapi-k8s               # Container name (used in logs, kubectl exec, etc.)
          image: fastapi-k8s:latest        # Docker image to run inside the container
          imagePullPolicy: Never           # Use the local Docker image -- do not pull from a registry
          ports:
            - containerPort: 8000          # The port your FastAPI app listens on inside the container
          livenessProbe:                   # Health check: is this container still alive?
            httpGet:
              path: /health                # Endpoint to probe (our /health always returns 200)
              port: 8000                   # Port to send the probe request to
            initialDelaySeconds: 3         # Wait 3 seconds after container starts before first probe
            periodSeconds: 10              # Run the probe every 10 seconds after that
          readinessProbe:                  # Readiness check: should this pod receive traffic?
            httpGet:
              path: /ready                 # Endpoint to probe (can be toggled via /ready/disable)
              port: 8000                   # Port to send the probe request to
            initialDelaySeconds: 2         # Wait 2 seconds before first readiness check
            periodSeconds: 5              # Check readiness every 5 seconds
          resources:
            requests:                      # Guaranteed minimum resources for scheduling
              cpu: "50m"                   # 50 millicores = 0.05 CPU cores (5% of one core)
              memory: "64Mi"               # 64 mebibytes of RAM guaranteed
            limits:                        # Hard ceiling -- container cannot exceed these
              cpu: "200m"                  # 200 millicores = 0.2 CPU cores (20% of one core)
              memory: "128Mi"              # 128 mebibytes max -- exceeding this triggers an OOMKill
          envFrom:                         # Inject ALL keys from a ConfigMap as environment variables
            - configMapRef:
                name: fastapi-config       # References the ConfigMap defined above
          env:                             # Individual environment variables (Downward API)
            - name: POD_NAME              # The unique name of this specific pod (e.g., fastapi-k8s-7d4b8c6f5-x2k9m)
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_IP                # The cluster-internal IP address assigned to this pod
              valueFrom:
                fieldRef:
                  fieldPath: status.podIP
            - name: NODE_NAME             # The name of the node (machine) this pod is running on
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: POD_NAMESPACE         # The namespace this pod belongs to (default: "default")
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: CPU_REQUEST           # The CPU request value (50m), exposed to the app at runtime
              valueFrom:
                resourceFieldRef:
                  resource: requests.cpu
            - name: CPU_LIMIT             # The CPU limit value (200m), exposed to the app at runtime
              valueFrom:
                resourceFieldRef:
                  resource: limits.cpu
            - name: MEMORY_REQUEST        # The memory request value (64Mi), exposed to the app
              valueFrom:
                resourceFieldRef:
                  resource: requests.memory
            - name: MEMORY_LIMIT          # The memory limit value (128Mi), exposed to the app
              valueFrom:
                resourceFieldRef:
                  resource: limits.memory
```

### Resource 3: Service

```yaml
apiVersion: v1                     # Core API group -- Services have been in v1 since early K8s
kind: Service                      # Resource type: a stable network endpoint for a set of pods
metadata:
  name: fastapi-k8s                # Name of this Service (also becomes a DNS name inside the cluster)
  labels:
    app: fastapi-k8s               # Label on the Service itself (for filtering)
spec:
  type: LoadBalancer               # Expose this Service externally (localhost on Docker Desktop)
  ports:
    - port: 80                     # The port the Service listens on (external-facing)
      targetPort: 8000             # The port traffic is forwarded to on each pod
  selector:
    app: fastapi-k8s               # Route traffic to all pods with this label
```

---

## Section-by-Section Breakdown

### ConfigMap: Externalizing Configuration

The ConfigMap is the simplest of the three resources. It is a flat key-value store that lives in the Kubernetes API server. It has no behavior on its own -- it only becomes useful when another resource references it.

In our case, the Deployment references it via `envFrom.configMapRef`. This tells Kubernetes to take every key in the ConfigMap and inject it as an environment variable into each container. So a pod created by this Deployment will have `APP_NAME=fastapi-k8s`, `LOG_LEVEL=info`, and `MAX_STRESS_SECONDS=30` available as environment variables alongside the Downward API variables.

!!! info "ConfigMap vs. Secrets"
    ConfigMaps are for non-sensitive data. For passwords, API keys, and tokens, use a **Secret** instead. Secrets are base64-encoded (not encrypted by default, but can be with additional configuration) and have tighter access controls. See [Configuration & Secrets](configuration-and-secrets.md) for more.

### Deployment: Declaring Desired State

The Deployment is the most complex resource in our file. It does not directly create containers -- instead, it manages a **ReplicaSet**, which in turn manages the individual pods. You rarely interact with ReplicaSets directly; the Deployment abstraction handles them for you.

**metadata.name and metadata.labels:**
The `name` is how you reference this Deployment in `kubectl` commands (e.g., `kubectl get deployment fastapi-k8s`). The `labels` are arbitrary key-value pairs used for filtering and selection. We use `app: fastapi-k8s` consistently across all three resources for easy `kubectl get all -l app=fastapi-k8s` queries.

**spec.replicas:**
This tells Kubernetes to maintain exactly 5 running copies of your pod at all times. If a pod crashes, Kubernetes automatically creates a replacement. If you manually delete a pod, a new one appears within seconds. This is the core of Kubernetes self-healing.

**spec.selector.matchLabels:**
This is how the Deployment identifies which pods it owns. It must match `template.metadata.labels` exactly. If they do not match, Kubernetes will reject the Deployment with a validation error.

**spec.template:**
Everything under `template` is the pod blueprint. Every pod created by this Deployment is identical -- same container image, same ports, same environment variables, same resource limits. The only things that differ are the pod name (auto-generated) and the Downward API values (POD_NAME, POD_IP, etc.).

### Service: Stable Networking

Pods are ephemeral -- they get created and destroyed constantly during updates, scaling, and self-healing. Each pod gets a new IP address every time it is created. The Service solves this by providing a single stable endpoint that automatically routes to whichever pods are currently running and ready.

The Service uses `selector: app: fastapi-k8s` to find its target pods. This is the same label that the Deployment's pod template applies to every pod. The Service continuously watches for pods matching this selector and updates its routing table accordingly.

**port vs. targetPort:**
The `port: 80` is what external clients connect to. The `targetPort: 8000` is where traffic actually arrives inside each pod. This mapping lets you expose a standard port (80) externally while your application listens on whatever port it prefers internally.

**type: LoadBalancer:**
On a cloud provider (AWS, GCP, Azure), this would provision an actual load balancer with a public IP. On Docker Desktop, it maps the Service port directly to `localhost`, so you can reach your app at `http://localhost`.

---

## Rolling Update Strategy

The `strategy` block controls how Kubernetes replaces old pods with new ones when you change the Deployment (e.g., deploying a new image version):

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

**type: RollingUpdate** means pods are replaced gradually rather than all at once. The alternative is `Recreate`, which kills all existing pods before starting new ones -- this causes downtime and is only needed for applications that cannot tolerate two versions running simultaneously.

**maxSurge: 1** controls how many extra pods Kubernetes can create above the desired replica count during an update. With `replicas: 5` and `maxSurge: 1`, Kubernetes may run up to 6 pods at once while transitioning. This extra pod ensures there is always capacity to handle traffic.

**maxUnavailable: 0** means Kubernetes will never take a pod down until its replacement is running and passing its readiness probe. Combined with `maxSurge: 1`, this gives you zero-downtime deployments: the new pod starts, passes readiness checks, and only then does Kubernetes terminate an old pod.

!!! tip "The update sequence with these settings"
    With 5 replicas, `maxSurge: 1`, and `maxUnavailable: 0`, an update proceeds like this:

    1. Kubernetes creates 1 new pod (6 total: 5 old + 1 new)
    2. New pod starts and passes readiness probe
    3. Kubernetes terminates 1 old pod (5 total: 4 old + 1 new)
    4. Kubernetes creates another new pod (6 total: 4 old + 2 new)
    5. This cycle repeats until all 5 pods are running the new version

    At no point is there less than 5 ready pods serving traffic.

See [Rolling Updates](rolling-updates.md) for a hands-on walkthrough.

---

## imagePullPolicy Explained

```yaml
imagePullPolicy: Never
```

The `imagePullPolicy` field tells Kubernetes where to get the container image. There are three options:

| Policy | Behavior | Use Case |
|---|---|---|
| `Always` | Always pull the image from a registry, even if a local copy exists. | Production clusters pulling from a private registry. Ensures you always get the latest image for a given tag. |
| `IfNotPresent` | Pull only if the image is not already present on the node. | Most production setups with properly versioned tags (e.g., `v1.2.3`). Avoids redundant pulls. |
| `Never` | Never pull from a registry. Only use images already present on the node. | **Local development with Docker Desktop.** The image must already exist in the local Docker daemon. |

We use `Never` because our workflow builds the image directly into Docker Desktop's local daemon with `docker build`. The image never gets pushed to a registry -- it only exists locally. If we used `Always` or `IfNotPresent`, Kubernetes would try to pull `fastapi-k8s:latest` from Docker Hub, fail to find it, and the pod would be stuck in an `ErrImagePull` or `ImagePullBackOff` state.

!!! warning "Common mistake: forgetting imagePullPolicy: Never"
    If your pods are stuck in `ImagePullBackOff` on Docker Desktop, the most likely cause is a missing or incorrect `imagePullPolicy`. Make sure it is set to `Never` and that you have built the image locally with `make docker-build` before deploying.

---

## Probe Timing Parameters

Both `livenessProbe` and `readinessProbe` support timing parameters that control how aggressively Kubernetes checks your containers:

### Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 10
```

| Parameter | Value | Meaning |
|---|---|---|
| `initialDelaySeconds` | 3 | Wait 3 seconds after the container starts before sending the first liveness probe. This gives your application time to boot up. |
| `periodSeconds` | 10 | After the initial delay, send a probe every 10 seconds. |
| `timeoutSeconds` | 1 (default) | If the probe does not get a response within 1 second, count it as a failure. |
| `failureThreshold` | 3 (default) | After 3 consecutive failures, Kubernetes kills the container and restarts it. |

With these settings, the worst-case detection time for a hung container is: 3 (initial delay) + 10 * 3 (three failed probes at 10-second intervals) = **33 seconds** from container start, or about **30 seconds** during normal operation (three probe periods).

### Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 2
  periodSeconds: 5
```

| Parameter | Value | Meaning |
|---|---|---|
| `initialDelaySeconds` | 2 | Wait 2 seconds before the first readiness check. Shorter than liveness because we want to start serving traffic quickly. |
| `periodSeconds` | 5 | Check readiness every 5 seconds. More frequent than liveness because readiness directly affects user traffic. |
| `timeoutSeconds` | 1 (default) | A probe that does not respond within 1 second is considered failed. |
| `failureThreshold` | 3 (default) | After 3 consecutive failures, the pod is removed from the Service's endpoint list and stops receiving traffic. |

!!! note "Liveness vs. readiness -- different consequences"
    A **failed liveness probe** causes Kubernetes to **restart** the container -- it assumes the process is hung or deadlocked and needs to be killed. A **failed readiness probe** only **removes the pod from the Service** -- the container keeps running, and if it starts passing the probe again, it is added back. This is why the readiness probe is checked more frequently: you want to quickly detect and route around unhealthy pods without killing them.

!!! tip "Default values you did not set"
    We did not explicitly set `timeoutSeconds` or `failureThreshold` in our YAML because the defaults (1 and 3 respectively) are reasonable for most applications. You can add them explicitly if you want to be more defensive about slow responses or transient failures.

---

## Downward API Environment Variables

The `env` block uses the Kubernetes Downward API to expose pod metadata and resource information as environment variables. Unlike `envFrom` (which pulls from ConfigMaps), these values are unique to each pod:

| Variable | Source | Example Value | Description |
|---|---|---|---|
| `POD_NAME` | `metadata.name` | `fastapi-k8s-7d4b8c6f5-x2k9m` | The unique name of this specific pod instance |
| `POD_IP` | `status.podIP` | `10.1.0.47` | The cluster-internal IP address assigned to this pod |
| `NODE_NAME` | `spec.nodeName` | `docker-desktop` | The node (machine) this pod is running on |
| `POD_NAMESPACE` | `metadata.namespace` | `default` | The Kubernetes namespace this pod belongs to |
| `CPU_REQUEST` | `requests.cpu` | `1` | The CPU request in Kubernetes canonical form |
| `CPU_LIMIT` | `limits.cpu` | `1` | The CPU limit in Kubernetes canonical form |
| `MEMORY_REQUEST` | `requests.memory` | `67108864` | The memory request in bytes |
| `MEMORY_LIMIT` | `limits.memory` | `134217728` | The memory limit in bytes |

The first four use `fieldRef` to read pod metadata fields. The last four use `resourceFieldRef` to read the container's resource requests and limits. Note that `resourceFieldRef` exposes values in canonical form -- CPU as integer cores and memory as bytes -- which may differ from what you specified in the YAML (`50m`, `64Mi`).

Our FastAPI app exposes all of these via the `GET /info` endpoint, which is useful for debugging and understanding which pod handled a given request.

---

## How Kubernetes Processes This File

When you run `kubectl apply -f k8s.yaml`, a precise sequence of events unfolds across multiple Kubernetes components:

### Step 1: API Server Receives and Validates

The `kubectl` client sends the YAML to the **API server** (the front door of the Kubernetes control plane). The API server:

- Parses the YAML and validates it against the schema for each resource kind
- Checks that required fields are present (e.g., a Deployment must have a `selector`)
- Validates relationships (e.g., `selector.matchLabels` must match `template.metadata.labels`)
- Runs any admission controllers (built-in policies that can reject or modify resources)
- If everything passes, stores the three resources in **etcd** -- the distributed key-value store that acts as Kubernetes' database

### Step 2: Controllers React to New State

Kubernetes is built on a "controller" pattern. Controllers are loops that watch for changes in etcd and take action to make reality match the desired state.

- The **Deployment controller** sees a new Deployment and creates a **ReplicaSet** resource
- The **ReplicaSet controller** sees the new ReplicaSet with `replicas: 5` and creates 5 **Pod** resources
- The **Endpoints controller** sees the new Service and starts watching for pods matching `app: fastapi-k8s`

### Step 3: Scheduler Assigns Pods to Nodes

The 5 newly created pods have no node assignment yet. The **scheduler** picks them up and decides which node to place each pod on. It considers:

- Resource availability (does the node have enough CPU and memory for the requests?)
- Affinity and anti-affinity rules (not configured in our case)
- Taints and tolerations (not configured in our case)

On Docker Desktop, there is only one node (`docker-desktop`), so all pods land on the same node. In a multi-node cluster, the scheduler would spread them across nodes.

### Step 4: Kubelet Starts Containers

The **kubelet** is an agent running on each node. When it sees new pods assigned to its node, it:

- Pulls the container image (skipped in our case because `imagePullPolicy: Never`)
- Creates the container using the container runtime (containerd on Docker Desktop)
- Injects environment variables from the ConfigMap and Downward API
- Starts the container process (`uvicorn main:app`)
- Begins running liveness and readiness probes on the configured schedule

### Step 5: Service Starts Routing Traffic

As each pod passes its readiness probe, the Endpoints controller adds that pod's IP to the Service's endpoint list. The **kube-proxy** component on each node updates iptables rules (or equivalent) so that traffic to the Service's cluster IP gets load-balanced across all ready pods.

At this point, hitting `http://localhost` (the LoadBalancer Service on Docker Desktop) routes your request to one of the 5 running pods.

!!! info "This all happens in seconds"
    On Docker Desktop, the entire process -- from `kubectl apply` to all 5 pods running and receiving traffic -- typically takes 5-15 seconds. The FastAPI app boots almost instantly, and the short `initialDelaySeconds` on the probes means pods are marked ready within a few seconds of starting.

---

## Verifying the Deployment

After running `kubectl apply -f k8s.yaml`, you can verify each resource was created correctly:

```bash
# See all three resources
kubectl get configmap,deployment,service -l app=fastapi-k8s

# Check that all 5 pods are running and ready
kubectl get pods -l app=fastapi-k8s

# View the ConfigMap contents
kubectl describe configmap fastapi-config

# Check the Service endpoints (should list 5 pod IPs)
kubectl get endpoints fastapi-k8s

# Test the app
curl http://localhost
```

See [Deploying and Verifying](deploying-and-verifying.md) for a complete walkthrough.

---

## Next Steps

Now that you understand the full configuration file, explore how Kubernetes uses it in practice:

- [Deploying and Verifying](deploying-and-verifying.md) -- Apply the YAML and confirm everything works
- [Scaling](scaling.md) -- Change the replica count and watch Kubernetes respond
- [Self-Healing](self-healing.md) -- Kill pods and see automatic recovery
- [Rolling Updates](rolling-updates.md) -- Deploy a new version with zero downtime
- [Resource Management](resource-management.md) -- Understand requests, limits, and what happens when you exceed them
- [Configuration & Secrets](configuration-and-secrets.md) -- Manage ConfigMaps and Secrets in more depth
