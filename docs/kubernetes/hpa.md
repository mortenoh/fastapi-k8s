# Horizontal Pod Autoscaler (HPA)

Instead of manually running `make scale N=10`, you can let Kubernetes automatically adjust the replica count based on observed metrics. The Horizontal Pod Autoscaler (HPA) watches CPU utilization (or other metrics) and scales your deployment up or down to match demand.

## What is autoscaling

Autoscaling means automatically adjusting the number or size of your workload resources based on current demand. Kubernetes offers three complementary approaches:

| Type | What it scales | How it works |
|------|---------------|--------------|
| **HPA** (Horizontal Pod Autoscaler) | Number of pod replicas | Adds or removes pods based on CPU, memory, or custom metrics |
| **VPA** (Vertical Pod Autoscaler) | Resource requests/limits per pod | Adjusts CPU and memory allocations for existing pods |
| **Cluster Autoscaler** | Number of nodes | Adds or removes nodes when pods cannot be scheduled or nodes are underutilized |

On Docker Desktop, we only have a single node, so the Cluster Autoscaler is not applicable. HPA is the most common and practical starting point -- it is built into Kubernetes and works out of the box with the metrics-server.

## How HPA works internally

The HPA controller runs as a control loop inside the kube-controller-manager. Here is what happens on each iteration:

1. **Metrics collection** (every 15 seconds by default) -- The HPA controller queries the metrics-server API for current CPU/memory usage of all pods matching the target deployment.

2. **Calculate desired replicas** -- The controller applies this formula:

    ```
    desiredReplicas = ceil(currentReplicas * (currentMetricValue / desiredMetricValue))
    ```

    For example, if you have 3 replicas averaging 80% CPU utilization with a target of 50%:

    ```
    desiredReplicas = ceil(3 * (80 / 50)) = ceil(4.8) = 5
    ```

    The HPA would scale from 3 to 5 replicas.

3. **Apply bounds** -- The result is clamped between `minReplicas` and `maxReplicas`.

4. **Apply stabilization** -- The controller considers recent scaling decisions within the stabilization window to prevent flapping (rapid scale-up/scale-down cycles).

5. **Update the deployment** -- If the desired replica count differs from the current count, the HPA patches the deployment's `replicas` field.

!!! info "Sync period"
    The default sync period is 15 seconds, controlled by the `--horizontal-pod-autoscaler-sync-period` flag on the kube-controller-manager. You rarely need to change this.

## Our HPA manifest

The HPA for this project is defined in `k8s/hpa.yaml`. Here is the manifest with a detailed explanation of each field:

```yaml
apiVersion: autoscaling/v2           # v2 API supports multiple metrics and custom metrics
kind: HorizontalPodAutoscaler
metadata:
  name: fastapi-k8s-hpa              # Name of the HPA resource
  labels:
    app: fastapi-k8s                  # Label for filtering with kubectl
spec:
  scaleTargetRef:                     # What this HPA controls
    apiVersion: apps/v1
    kind: Deployment
    name: fastapi-k8s                 # Must match our Deployment name
  minReplicas: 2                      # Never scale below 2 pods
  maxReplicas: 10                     # Never scale above 10 pods
  metrics:                            # What metrics drive scaling decisions
    - type: Resource                  # Built-in resource metrics (CPU/memory)
      resource:
        name: cpu                     # Scale based on CPU utilization
        target:
          type: Utilization           # Percentage of the CPU request
          averageUtilization: 50      # Target 50% average across all pods
```

**Key configuration choices:**

- **minReplicas: 2** -- We always keep at least 2 pods for availability. If one pod crashes or is being replaced during a rolling update, the other continues serving traffic.
- **maxReplicas: 10** -- A safety cap to prevent runaway scaling. With 10 pods at 50m CPU request each, the maximum guaranteed CPU is 500m (half a core) -- reasonable for Docker Desktop.
- **averageUtilization: 50** -- The target is 50% of the CPU request. Since our request is `50m`, the target average usage per pod is `25m`. If pods average more than 25m, the HPA scales up. If they average less, it scales down (after the cooldown period).

!!! note "Why 50% utilization?"
    Setting the target at 50% gives you headroom. When traffic spikes, existing pods have room to absorb the initial burst while new pods are starting up. If you set the target to 90%, pods would already be near capacity when the spike hits, and users would experience latency before new pods come online.

## Prerequisites

HPA needs a metrics source to function. The built-in option is the **metrics-server**, which collects CPU and memory usage from the kubelet on each node.

### Installing metrics-server on Docker Desktop

```bash
make metrics-server
```

This make target does three things:

1. Installs the metrics-server from the official release manifest
2. Patches the deployment to add `--kubelet-insecure-tls` (required for Docker Desktop because the kubelet uses self-signed certificates)
3. Waits up to 120 seconds for the metrics-server to become available

!!! warning "Docker Desktop TLS"
    The `--kubelet-insecure-tls` flag is necessary because Docker Desktop's kubelet uses a self-signed certificate that metrics-server does not trust by default. This flag is only appropriate for local development -- never use it in production.

### Verifying metrics-server

After installation, wait 60-90 seconds for the first metrics to be collected, then verify:

```bash
$ kubectl top pods -l app=fastapi-k8s
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-xj2kl  2m           45Mi
fastapi-k8s-7f8b9c6d4-ab1cd  1m           43Mi
```

If you see `error: Metrics API not available`, the metrics-server is not ready yet. Check its status:

```bash
kubectl get pods -n kube-system -l k8s-app=metrics-server
kubectl logs -n kube-system -l k8s-app=metrics-server
```

## End-to-end walkthrough

This walkthrough demonstrates the full HPA lifecycle -- from deploying the app through observing autoscaling under load.

### Step 1: Deploy the application

```bash
make deploy
kubectl rollout status deployment/fastapi-k8s --timeout=60s
```

### Step 2: Install metrics-server (skip if already installed)

```bash
make metrics-server
```

Wait about 60 seconds, then confirm metrics are flowing:

```bash
$ kubectl top pods -l app=fastapi-k8s
NAME                          CPU(cores)   MEMORY(bytes)
fastapi-k8s-7f8b9c6d4-xj2kl  2m           45Mi
fastapi-k8s-7f8b9c6d4-ab1cd  1m           44Mi
fastapi-k8s-7f8b9c6d4-ef2gh  3m           43Mi
fastapi-k8s-7f8b9c6d4-ij4kl  1m           45Mi
fastapi-k8s-7f8b9c6d4-mn5op  2m           44Mi
```

### Step 3: Apply the HPA

```bash
$ make hpa
horizontalpodautoscaler.autoscaling/fastapi-k8s-hpa created
```

### Step 4: Check initial HPA status

```bash
$ make hpa-status
NAME              REFERENCE                TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
fastapi-k8s-hpa   Deployment/fastapi-k8s   2%/50%    2         10        5          10s
```

The `TARGETS` column shows `2%/50%` -- current average CPU utilization (2%) against the target (50%). Since usage is well below the target, the HPA will eventually scale down to `minReplicas` (2).

### Step 5: Watch the HPA continuously

Open a separate terminal window:

```bash
kubectl get hpa -l app=fastapi-k8s -w
```

This will stream updates as the HPA makes scaling decisions.

### Step 6: Generate CPU load

In another terminal, send concurrent requests to the `/stress` endpoint:

```bash
# Send 20 concurrent requests, each burning CPU for 30 seconds
for i in $(seq 1 20); do
  curl -s "http://localhost/stress?seconds=30" &
done
```

### Step 7: Observe scale-up

After 30-60 seconds, check the HPA and pod count:

```bash
$ make hpa-status
NAME              REFERENCE                TARGETS    MINPODS   MAXPODS   REPLICAS   AGE
fastapi-k8s-hpa   Deployment/fastapi-k8s   120%/50%   2         10        6          5m

$ kubectl get pods -l app=fastapi-k8s
NAME                          READY   STATUS    RESTARTS   AGE
fastapi-k8s-7f8b9c6d4-xj2kl  1/1     Running   0          10m
fastapi-k8s-7f8b9c6d4-ab1cd  1/1     Running   0          10m
fastapi-k8s-7f8b9c6d4-qr6st  1/1     Running   0          30s
fastapi-k8s-7f8b9c6d4-uv7wx  1/1     Running   0          30s
fastapi-k8s-7f8b9c6d4-yz8ab  1/1     Running   0          30s
fastapi-k8s-7f8b9c6d4-cd9ef  1/1     Running   0          30s
```

The HPA detected CPU utilization above 50% and added pods to bring the average back down.

### Step 8: Observe scale-down

Once the `/stress` requests complete, CPU usage drops. The HPA waits for the stabilization window (5 minutes by default) before scaling down:

```bash
# After 5+ minutes of low CPU usage
$ make hpa-status
NAME              REFERENCE                TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
fastapi-k8s-hpa   Deployment/fastapi-k8s   3%/50%    2         10        2          15m
```

The replicas have dropped back to `minReplicas: 2`.

### Step 9: Clean up

```bash
make hpa-delete
```

## Custom metrics

The built-in HPA supports CPU and memory metrics out of the box. For more sophisticated scaling, you can use custom metrics:

| Metric type | Examples | Requires |
|-------------|----------|----------|
| Resource | CPU utilization, memory utilization | metrics-server (built-in) |
| Custom | Requests per second, queue depth, active connections | Prometheus Adapter |
| External | Cloud queue length, pub/sub message count | External metrics provider |

To scale on requests per second, for example, you would:

1. Instrument your app to expose metrics (e.g., via Prometheus)
2. Deploy the Prometheus Adapter to translate Prometheus metrics into the Kubernetes custom metrics API
3. Configure the HPA to use the custom metric:

```yaml
metrics:
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "100"
```

!!! tip "KEDA as an alternative"
    For custom metrics, KEDA (Kubernetes Event-Driven Autoscaling) is often simpler than the Prometheus Adapter. See the KEDA section below.

## Scaling behavior configuration

The `autoscaling/v2` API lets you fine-tune how quickly the HPA scales up and down using the `behavior` field:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fastapi-k8s-hpa
spec:
  # ... scaleTargetRef, min/maxReplicas, metrics ...
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0        # Scale up immediately
      policies:
        - type: Percent
          value: 100                       # Can double the replica count
          periodSeconds: 60                # Per 60-second window
        - type: Pods
          value: 4                         # Or add up to 4 pods
          periodSeconds: 60
      selectPolicy: Max                    # Use whichever policy allows more scaling
    scaleDown:
      stabilizationWindowSeconds: 300      # Wait 5 minutes before scaling down
      policies:
        - type: Percent
          value: 10                        # Remove at most 10% of pods
          periodSeconds: 60
      selectPolicy: Min                    # Use the most conservative policy
```

**Key concepts:**

- **stabilizationWindowSeconds** -- How long the HPA looks back at past recommendations before acting. For scale-down, the default is 300 seconds (5 minutes). For scale-up, the default is 0 (immediate). This prevents flapping.
- **policies** -- Rules that limit how much scaling can happen per time period. You can specify both `Percent` and `Pods` policies.
- **selectPolicy** -- When multiple policies apply, `Max` picks the one that allows the most change (aggressive), `Min` picks the most conservative, and `Disabled` prevents scaling in that direction entirely.

!!! info "Default behavior"
    If you do not specify a `behavior` field, the defaults are: scale-up immediately with no stabilization window, scale-down after a 5-minute stabilization window. This asymmetry is intentional -- it is better to scale up quickly (to handle traffic) and scale down cautiously (to avoid premature removal).

## Cooldown periods

The HPA deliberately scales down more slowly than it scales up:

| Direction | Default stabilization | Why |
|-----------|----------------------|-----|
| Scale up | 0 seconds | Traffic spikes need immediate response. Latency is worse than over-provisioning. |
| Scale down | 300 seconds (5 min) | Load patterns are often bursty. Removing pods too quickly leads to flapping -- scaling down and immediately back up, which wastes resources and causes disruption. |

To adjust the scale-down cooldown, modify `stabilizationWindowSeconds` in the `behavior.scaleDown` section. For example, to scale down after 2 minutes instead of 5:

```yaml
behavior:
  scaleDown:
    stabilizationWindowSeconds: 120
```

!!! warning "Do not set scale-down stabilization to 0"
    A stabilization window of 0 for scale-down means the HPA will remove pods the instant metrics drop below the threshold. This almost always leads to flapping in real-world workloads where traffic is variable.

## HPA and manual scaling conflict

When an HPA is active on a deployment, it takes ownership of the `replicas` field. This creates an important rule:

**Do not use `kubectl scale` or `make scale` while the HPA is active.** If you manually set replicas to 8 but the HPA sees low CPU usage, it will scale back down to `minReplicas` within minutes. Your manual change is effectively ignored.

If you need a specific replica count:

- **Temporarily:** Delete the HPA (`make hpa-delete`), set replicas manually, then re-apply the HPA later
- **Permanently:** Adjust `minReplicas` in `k8s/hpa.yaml` to enforce a higher floor

```bash
# Wrong -- HPA will override this
make scale N=8

# Right -- change the HPA minimum
# Edit k8s/hpa.yaml to set minReplicas: 8, then:
make hpa
```

## VPA (Vertical Pod Autoscaler)

While HPA scales horizontally (more pods), VPA scales vertically (bigger pods). It adjusts the CPU and memory requests/limits for individual containers based on observed usage.

### How VPA works

1. The VPA controller monitors actual resource consumption over time
2. It calculates recommended requests based on usage patterns
3. Depending on the update mode, it either reports recommendations or applies them by evicting and recreating pods with new resource values

### VPA update modes

| Mode | Behavior |
|------|----------|
| `Off` | VPA calculates recommendations but does not apply them. Useful for observation only. |
| `Initial` | VPA sets resources only when pods are first created. Running pods are not affected. |
| `Recreate` | VPA evicts pods and recreates them with updated resources. This causes brief downtime per pod. |
| `Auto` | Currently equivalent to `Recreate`. May support in-place updates in the future. |

### HPA vs VPA: when to use each

| Scenario | Use HPA | Use VPA |
|----------|---------|---------|
| Stateless web apps (like our FastAPI app) | Yes -- scale out with demand | Optional -- for right-sizing |
| Stateful workloads (databases) | Usually no | Yes -- increase resources without adding replicas |
| Unpredictable traffic patterns | Yes -- respond to demand | No -- VPA is too slow for spikes |
| Unknown resource requirements | No | Yes -- let VPA discover the right values |

!!! warning "HPA and VPA together"
    You should not use HPA and VPA on the same metric. If both are watching CPU, they will conflict -- HPA tries to add pods while VPA tries to resize them. However, you can use them together if HPA scales on a custom metric (like requests per second) and VPA manages CPU/memory requests. This combination is sometimes called "right-sized horizontal scaling."

### VPA is not built in

Unlike HPA, VPA is not part of the standard Kubernetes distribution. It must be installed separately from the [autoscaler repository](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler). On Docker Desktop, this is generally not worth the setup complexity -- it is more relevant for production clusters.

## KEDA (Kubernetes Event-Driven Autoscaling)

KEDA extends Kubernetes autoscaling beyond the built-in HPA metrics. It can scale based on events from external systems -- message queues, databases, cloud services, cron schedules, and more.

### Key features

- **Scale to zero** -- Unlike HPA (which has a minimum of 1 replica), KEDA can scale a deployment to 0 replicas when there is no work to do, and back up when events arrive.
- **60+ built-in scalers** -- Kafka, RabbitMQ, Redis, PostgreSQL, AWS SQS, Azure Queue, HTTP requests, cron, and many more.
- **ScaledObject CRD** -- You define scaling rules with a `ScaledObject` resource instead of an HPA. KEDA creates and manages the underlying HPA for you.

### Example: scaling on HTTP requests

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: fastapi-k8s-scaledobject
spec:
  scaleTargetRef:
    name: fastapi-k8s
  minReplicaCount: 0           # Scale to zero when idle
  maxReplicaCount: 10
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring:9090
        metricName: http_requests_total
        query: sum(rate(http_requests_total{app="fastapi-k8s"}[1m]))
        threshold: "100"
```

### When to use KEDA vs HPA

| Situation | Recommendation |
|-----------|---------------|
| Simple CPU/memory scaling | Use HPA -- simpler, built-in, no extra dependencies |
| Scale to zero | Use KEDA -- HPA cannot scale below 1 |
| Event-driven workloads (queue consumers) | Use KEDA -- it natively integrates with message queues |
| Custom metrics without Prometheus | Use KEDA -- it has built-in scalers for many data sources |

!!! note "KEDA on Docker Desktop"
    KEDA can be installed on Docker Desktop via Helm, but it is overkill for learning basic Kubernetes concepts. Start with the built-in HPA, and explore KEDA when you have event-driven scaling needs.

## Summary

| Topic | Key takeaway |
|-------|-------------|
| HPA formula | `desiredReplicas = ceil(currentReplicas * currentMetric / targetMetric)` |
| Our config | minReplicas=2, maxReplicas=10, target CPU=50% |
| Prerequisite | metrics-server (install with `make metrics-server`) |
| Scale-up | Immediate by default |
| Scale-down | 5-minute stabilization window by default |
| Manual scaling | Do not use while HPA is active |
| VPA | Vertical scaling -- complementary to HPA but not built-in |
| KEDA | Event-driven scaling with scale-to-zero -- for advanced use cases |
