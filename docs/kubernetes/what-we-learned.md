---
hide:
  - toc
enumerate_headings: false
---

# What We Learned

Fifteen things worth knowing before your next meeting -- each one distilled from the guide, with a link to the full walkthrough.

---

**1. Kubernetes is a declarative system**

You describe the desired state in YAML; Kubernetes continuously reconciles the actual state to match. You never say "start 5 pods" -- you say "there should be 5 pods" and the control plane figures out the rest.

:material-arrow-right: [What is Kubernetes?](what-is-kubernetes.md)

---

**2. Pods are the smallest deployable unit**

Not containers. A pod wraps one or more containers that share networking and storage. In practice, most pods run a single container.

:material-arrow-right: [Core Concepts](core-concepts.md)

---

**3. Deployments manage ReplicaSets, which manage Pods**

This three-layer hierarchy gives you rolling updates, rollbacks, and scaling through a single resource.

:material-arrow-right: [Core Concepts](core-concepts.md)

---

**4. Services provide stable networking**

Pods are ephemeral -- IPs change on restart. A Service gives a stable DNS name and IP that load-balances across healthy pods.

:material-arrow-right: [Networking Deep Dive](networking.md)

---

**5. ConfigMaps and Secrets separate config from code**

Twelve-factor app style. Change configuration without rebuilding images. Secrets are base64-encoded (not encrypted) -- treat them as sensitive.

:material-arrow-right: [Configuration & Secrets](configuration-and-secrets.md)

---

**6. Resource requests and limits control scheduling and stability**

Requests guarantee a minimum; limits enforce a ceiling. CPU is throttled, memory is OOMKilled. QoS classes (Guaranteed, Burstable, BestEffort) determine eviction order.

:material-arrow-right: [Resource Management](resource-management.md)

---

**7. Liveness and readiness probes drive self-healing**

Liveness failures restart the container. Readiness failures remove it from the Service. Together they keep unhealthy pods from receiving traffic.

:material-arrow-right: [Self-Healing](self-healing.md)

---

**8. Rolling updates give zero-downtime deployments**

New pods start before old ones stop. `maxSurge` and `maxUnavailable` control the rollout speed. Rollback is one command away.

:material-arrow-right: [Rolling Updates](rolling-updates.md)

---

**9. Horizontal Pod Autoscaler scales based on metrics**

HPA watches CPU (or custom metrics) and adjusts replica count automatically. The metrics-server provides the data.

:material-arrow-right: [Horizontal Pod Autoscaler](hpa.md)

---

**10. PersistentVolumeClaims decouple storage from pods**

Data survives pod restarts. The PVC requests storage; the cluster provisions it. Docker Desktop uses hostPath; production uses cloud volumes.

:material-arrow-right: [Persistent Storage](persistent-storage.md)

---

**11. ClusterIP vs LoadBalancer controls exposure**

ClusterIP is internal-only (backing services like Redis). LoadBalancer exposes to the outside world. Use the narrowest access possible.

:material-arrow-right: [Networking Deep Dive](networking.md)

---

**12. DNS-based service discovery replaces hardcoded IPs**

`redis` resolves to `redis.default.svc.cluster.local` via CoreDNS. Services find each other by name, not by IP.

:material-arrow-right: [Networking Deep Dive](networking.md)

---

**13. Stateless apps scale freely; stateful apps need special handling**

FastAPI runs 5 replicas with RollingUpdate. Redis runs 1 replica with Recreate. Scaling a database requires replication protocols, not just more replicas.

:material-arrow-right: [Redis Integration](redis.md)

---

**14. Shared state across pods requires an external store**

In-memory data dies with the pod. Redis (or any external store) lets all replicas share visit counters, sessions, and key-value data.

:material-arrow-right: [Redis Integration](redis.md)

---

**15. Docker layer caching makes builds fast**

Copy dependency files first, install, then copy code. Code changes only rebuild the last layers. A 30-second build becomes 2-3 seconds.

:material-arrow-right: [Dockerfile Walkthrough](dockerfile.md)
