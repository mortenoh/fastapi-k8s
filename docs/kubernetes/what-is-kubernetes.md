# What is Kubernetes?

Kubernetes (often abbreviated **K8s** -- the 8 stands for the eight letters between "K" and "s") is an open-source container orchestration platform. It takes your containerized applications and manages where and how they run across a cluster of machines, handling everything from scheduling and networking to scaling and self-healing.

In the context of this project, we use Kubernetes to deploy a FastAPI application on a single-node Docker Desktop cluster. But the same concepts apply whether you are running one node on your laptop or thousands of nodes in a cloud data center.

!!! info "Why K8s?"
    The abbreviation "K8s" follows the same pattern as "i18n" (internationalization) and "l10n" (localization). It is widely used in documentation, CLI tools, and conversation.

---

## A Brief History

Kubernetes did not appear out of thin air. It has roots in over a decade of production container management at Google.

**2003-2004 -- Google's Borg system**
Google built an internal cluster management system called **Borg** to run its massive workloads (Search, Gmail, Maps, and more). Borg scheduled and managed thousands of applications across millions of machines. Many of the ideas in Kubernetes -- declarative configuration, labels, pods -- come directly from lessons learned building Borg.

**2013 -- Docker changes everything**
Docker made Linux containers accessible to ordinary developers. Before Docker, containers existed but were painful to use. Docker provided a simple build-and-run workflow that spread like wildfire. Suddenly everyone had containers -- but no good way to run them at scale.

**2014 -- Kubernetes is born**
Google open-sourced a system inspired by Borg (and its successor, Omega) under the name "Kubernetes" (Greek for "helmsman" or "pilot"). The first commit landed on GitHub on June 6, 2014. Unlike Borg, Kubernetes was designed from scratch for the open-source ecosystem and Docker containers.

**2015 -- CNCF and v1.0**
Google donated Kubernetes to the newly formed **Cloud Native Computing Foundation (CNCF)**, a vendor-neutral home under the Linux Foundation. Kubernetes 1.0 was released in July 2015, marking it as production-ready. This move ensured that no single company controlled the project.

**2016-present -- Industry standard**
Kubernetes became the de facto standard for container orchestration. Every major cloud provider offers a managed Kubernetes service (GKE, EKS, AKS). A massive ecosystem of tools, extensions, and certifications has grown around it.

!!! note "Standing on the shoulders of Borg"
    If you want to understand the deep design decisions in Kubernetes, the 2015 paper [Large-scale cluster management at Google with Borg](https://research.google/pubs/pub43438/) is excellent background reading. Many patterns -- like separating desired state from current state, using labels for grouping, and treating pods as the atomic unit -- trace directly back to Borg.

---

## The Problems Kubernetes Solves

Running a single container on your laptop is easy. Running dozens or hundreds of containers in production is a different story. Here are the specific pain points Kubernetes addresses.

### Manual Deployment Pain

Without orchestration, deploying a new version of your app looks something like this:

1. SSH into each server
2. Pull the new image
3. Stop the old container
4. Start the new container
5. Verify it is healthy
6. Repeat for every server

This is slow, error-prone, and does not scale. If you have 50 servers, you need to do this 50 times (or write fragile shell scripts to automate it). Kubernetes replaces all of this with a single command:

```bash
kubectl set image deployment/fastapi-k8s fastapi-k8s=fastapi-k8s:v2
```

Kubernetes handles the rest -- rolling out the new version, verifying health checks, and rolling back if something goes wrong.

### Scaling

Traffic spikes happen. Maybe your API goes viral, or a batch job hits your service hard. Without Kubernetes, you would need to manually provision new servers, deploy your app, and configure the load balancer.

With Kubernetes, scaling is one command:

```bash
kubectl scale deployment/fastapi-k8s --replicas=20
```

Or you can configure the **Horizontal Pod Autoscaler** to scale automatically based on CPU or memory usage. See the [HPA guide](hpa.md) in this project for a hands-on example.

### Service Discovery and Load Balancing

In a dynamic environment, containers come and go. They get new IP addresses every time they restart. How does one service find another?

Kubernetes solves this with **Services** -- stable network endpoints that automatically track which pods are alive and route traffic to them. Your app never needs to know individual pod IPs. It just talks to the Service name, and Kubernetes handles the rest.

```
App A  --->  service-name:80  --->  [ Pod 1, Pod 2, Pod 3 ]
```

### Configuration Management

Applications need configuration -- database URLs, feature flags, API keys. Kubernetes provides **ConfigMaps** for non-sensitive configuration and **Secrets** for sensitive data. These are injected into containers as environment variables or mounted as files, keeping configuration separate from application code.

In this project, we use a ConfigMap to inject `APP_NAME`, `LOG_LEVEL`, and `MAX_STRESS_SECONDS` into each pod. Changing a configuration value does not require rebuilding the Docker image.

### Self-Healing

Containers crash. Servers fail. Disks fill up. In a traditional setup, someone (or some monitoring script) needs to detect the failure and restart the process.

Kubernetes does this automatically:

- **Container crash** -- Kubernetes restarts it immediately (with exponential backoff)
- **Failed health check** -- Kubernetes kills the container and starts a new one
- **Node failure** -- Kubernetes reschedules all pods from the dead node onto healthy nodes
- **Failed readiness check** -- Kubernetes stops sending traffic to the pod (but keeps it running so it can recover)

In this project, you can test self-healing by calling `POST /crash` to kill a pod and watching Kubernetes bring it back to life within seconds.

---

## Kubernetes vs Alternatives

Kubernetes is powerful, but it is not always the right tool. Here is how it compares to common alternatives.

| Feature | Docker Compose | Docker Swarm | HashiCorp Nomad | Kubernetes |
|---|---|---|---|---|
| **Complexity** | Very low | Low | Medium | High |
| **Multi-host** | No (single host) | Yes | Yes | Yes |
| **Auto-scaling** | No | Limited | Yes | Yes (HPA) |
| **Self-healing** | Restart policies only | Yes | Yes | Yes |
| **Service discovery** | DNS on single host | Built-in | Consul integration | Built-in |
| **Ecosystem** | Small | Small | Medium | Massive |
| **Learning curve** | Minimal | Low | Moderate | Steep |
| **Best for** | Local dev, small projects | Simple multi-host | Mixed workloads (containers + VMs + batch) | Production at any scale |

### When to use Docker Compose

Use Docker Compose when you are running everything on a single machine -- local development, CI pipelines, or small self-hosted projects. It is simple, fast, and requires no cluster setup. If your app fits on one server and you do not need auto-scaling or rolling updates, Compose is probably all you need.

### When to use Docker Swarm

Docker Swarm is Docker's built-in orchestrator. It is simpler than Kubernetes and works well for small teams that need basic multi-host deployments without the complexity of Kubernetes. However, its development has largely stalled and its ecosystem is limited.

### When to use Nomad

HashiCorp Nomad is a flexible orchestrator that can schedule containers, VMs, Java apps, and batch jobs. It integrates well with other HashiCorp tools (Consul, Vault). Choose Nomad when you need to orchestrate mixed workload types or when you prefer HashiCorp's ecosystem. It has a gentler learning curve than Kubernetes but a smaller community.

### When to use Kubernetes

Use Kubernetes when you need a production-grade orchestration platform with a vast ecosystem. If you need auto-scaling, advanced networking, extensive monitoring integrations, or plan to run on managed cloud services (GKE, EKS, AKS), Kubernetes is the standard choice. The investment in learning pays off with portability across every major cloud provider.

!!! tip "For this project"
    We use Kubernetes on Docker Desktop -- a single-node cluster that behaves like a real multi-node cluster. This lets you learn Kubernetes concepts locally before deploying to the cloud. The exact same `k8s.yaml` file would work on a production cluster with minor adjustments.

---

## Architecture Overview

A Kubernetes cluster consists of two layers: the **control plane** (the brain) and the **worker nodes** (the muscles). On Docker Desktop, both layers run on your single machine. In production, the control plane typically runs on dedicated machines separated from worker nodes.

### Control Plane Components

The control plane makes all scheduling decisions and manages the cluster state.

**API Server (`kube-apiserver`)**
The front door to the cluster. Every interaction -- from `kubectl` commands to internal component communication -- goes through the API server. It validates and processes RESTful requests, then stores the resulting state in etcd.

**etcd**
A distributed key-value store that holds all cluster state -- every Deployment, Pod, Service, ConfigMap, and Secret. It is the single source of truth. If etcd is lost and has no backup, the cluster state is gone. In production, etcd is typically run as a 3- or 5-node cluster for high availability.

**Scheduler (`kube-scheduler`)**
When a new pod needs to run, the scheduler decides which node to place it on. It considers resource requests, node capacity, affinity rules, taints, and tolerations. Think of it as a matchmaker between pods and nodes.

**Controller Manager (`kube-controller-manager`)**
Runs a collection of controllers -- background loops that watch the cluster state and make changes to move from the *current state* to the *desired state*. Examples:

- **ReplicaSet controller** -- Ensures the correct number of pod replicas are running
- **Deployment controller** -- Manages rolling updates and rollbacks
- **Node controller** -- Monitors node health and evicts pods from failed nodes
- **Service controller** -- Creates cloud load balancers for LoadBalancer-type services

### Node Components

Every worker node runs these components to execute workloads and maintain networking.

**kubelet**
The agent running on each node. It receives pod specifications from the API server and ensures the described containers are running and healthy. It also reports node status back to the control plane.

**kube-proxy**
Manages network rules on the node so that traffic to a Service's IP gets forwarded to the correct pod. It implements the Kubernetes Service abstraction using iptables rules or IPVS.

**Container Runtime**
The software that actually runs containers. Docker Desktop uses **containerd** under the hood. Other runtimes include CRI-O. Kubernetes talks to the runtime through the Container Runtime Interface (CRI).

### Architecture Diagram

```
+===========================================================================+
|                         Kubernetes Cluster                                |
|                                                                           |
|  +------------------------------- Control Plane -----------------------+  |
|  |                                                                     |  |
|  |  +----------------+   +---------+   +-------------+   +----------+ |  |
|  |  |   API Server   |   |  etcd   |   |  Scheduler  |   | Ctrl Mgr | |  |
|  |  | (kube-apiserver)|   | (state) |   |             |   |          | |  |
|  |  +-------+--------+   +----+----+   +------+------+   +-----+----+ |  |
|  |          |                  |               |                |      |  |
|  |          +------------------+---------------+----------------+      |  |
|  |                             |                                       |  |
|  +-----------------------------+---------------------------------------+  |
|                                |                                          |
|         kubectl / API          |  watches & reconciles                    |
|              |                 |                                          |
|  +-----------+----- Worker Node(s) -----------------------------------+  |
|  |           |                                                        |  |
|  |  +--------+-------+    +--------------+    +--------------------+  |  |
|  |  |    kubelet      |    |  kube-proxy  |    | Container Runtime  |  |  |
|  |  | (pod lifecycle) |    |  (networking)|    | (containerd)       |  |  |
|  |  +--------+--------+    +------+-------+    +---------+----------+  |  |
|  |           |                    |                      |             |  |
|  |           v                    v                      v             |  |
|  |  +-------------+  +-------------+  +-------------+                 |  |
|  |  |    Pod A    |  |    Pod B    |  |    Pod C    |    ...          |  |
|  |  | fastapi-k8s |  | fastapi-k8s |  | fastapi-k8s |                |  |
|  |  |   :8000     |  |   :8000     |  |   :8000     |                |  |
|  |  +-------------+  +-------------+  +-------------+                 |  |
|  |                                                                    |  |
|  +--------------------------------------------------------------------+  |
|                                                                           |
+===========================================================================+
```

!!! info "Docker Desktop is a single-node cluster"
    On Docker Desktop, the control plane and worker node run on the same machine inside a lightweight Linux VM. This is perfect for learning. In production, you would have multiple worker nodes (and often multiple control plane nodes for high availability).

---

## The Declarative Model

One of the most important concepts in Kubernetes is the **declarative model**. Understanding this is key to understanding everything else.

### Imperative vs Declarative

In an **imperative** approach, you tell the system *what to do* step by step:

```bash
# Imperative: step-by-step instructions
docker run -d --name app1 fastapi-k8s:latest
docker run -d --name app2 fastapi-k8s:latest
docker run -d --name app3 fastapi-k8s:latest
# Hope nothing crashes...
```

In a **declarative** approach, you tell the system *what you want* and let it figure out how to get there:

```yaml
# Declarative: desired state
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-k8s
spec:
  replicas: 3
```

When you apply this YAML, Kubernetes compares the desired state ("3 replicas") with the current state ("0 replicas") and takes action to reconcile them. This happens continuously -- not just when you run `kubectl apply`. A background control loop is always watching.

### The Reconciliation Loop

This is the core pattern that powers all of Kubernetes:

```
  +----------------+
  |  Desired State |  (your YAML in etcd)
  |  replicas: 3   |
  +-------+--------+
          |
          v
  +-------+--------+      +-----------------+
  |   Controller   | ---> | Compare desired  |
  | (control loop) |      | vs current state |
  +-------+--------+      +--------+--------+
          ^                         |
          |                         v
  +-------+--------+      +--------+--------+
  | Current State  | <--- | Take action:     |
  | replicas: 2    |      | create 1 more    |
  +----------------+      | pod              |
                          +-----------------+
```

This loop runs continuously. If a pod crashes and the current state drops to 2, the controller sees the mismatch and creates a new pod. If you update the YAML to say `replicas: 5`, the controller creates 3 more. If you scale down to `replicas: 1`, the controller terminates 4.

!!! tip "Why declarative matters"
    The declarative model means your YAML files are the **single source of truth** for your application's desired state. You can store them in Git, review changes in pull requests, and roll back by reverting a commit. This is the foundation of **GitOps** -- a practice where Git is the source of truth for infrastructure.

### Desired State in Practice

In this project, our `k8s.yaml` declares:

- **A ConfigMap** with application settings
- **A Deployment** with 5 replicas, resource limits, health probes, and environment variables
- **A Service** of type LoadBalancer on port 80

When you run `make deploy` (which calls `kubectl apply -f k8s.yaml`), Kubernetes reads this file, stores the desired state in etcd, and the various controllers get to work creating pods, setting up networking, and configuring the load balancer. From that point on, Kubernetes continuously ensures reality matches your YAML.

---

## The Big Picture

Putting it all together -- here is the complete flow from writing YAML to curling your API:

```
 You write k8s.yaml
        |
        v
 kubectl apply -f k8s.yaml
        |
        v
 +------+----------------------------------------------+
 |                  Kubernetes Cluster                  |
 |                                                      |
 |   API Server receives desired state                  |
 |        |                                             |
 |        v                                             |
 |   etcd stores: "5 replicas of fastapi-k8s"          |
 |        |                                             |
 |        v                                             |
 |   Deployment controller creates ReplicaSet           |
 |        |                                             |
 |        v                                             |
 |   Scheduler assigns pods to node(s)                  |
 |        |                                             |
 |        v                                             |
 |   kubelet starts containers via containerd           |
 |        |                                             |
 |        v                                             |
 |   +----------+  +----------+  +----------+          |
 |   |  Pod 1   |  |  Pod 2   |  |  Pod 3   |   ...   |
 |   | :8000    |  | :8000    |  | :8000    |          |
 |   +-----+----+  +-----+----+  +-----+----+          |
 |         |              |              |               |
 |         +--------------+--------------+               |
 |                        |                              |
 |               +--------+--------+                     |
 |               |     Service     |                     |
 |               |    (port 80)    |                     |
 |               | Load-balances   |                     |
 |               | across healthy  |                     |
 |               | pods            |                     |
 |               +--------+--------+                     |
 |                        |                              |
 +------------------------+------------------------------+
                          |
                          v
          curl http://localhost/
          --> { "hello": "from fastapi-k8s", "hostname": "fastapi-k8s-xyz" }
```

Each `curl` request hits the Service, which forwards it to one of the healthy pods. The response includes the pod's hostname so you can see load balancing in action -- each request may come from a different pod.

---

## What's Next?

Now that you understand what Kubernetes is, why it exists, and how it works at a high level, continue to the next section to learn about the core building blocks in detail.

[Core Concepts -- Pods, Deployments, Services, and more](core-concepts.md){ .md-button }
