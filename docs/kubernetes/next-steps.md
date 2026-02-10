# Where to Go Next

This guide covered the fundamentals of Kubernetes using a local Docker Desktop cluster and a FastAPI application. That foundation is solid, but production Kubernetes involves many more tools, patterns, and platforms. This page maps out the landscape so you know what to learn next and why.

---

## Helm -- the package manager for Kubernetes

[Helm](https://helm.sh/) is the most widely used tool for packaging, distributing, and installing Kubernetes applications. Think of it as `apt` or `brew` for your cluster.

### Core concepts

| Concept | Description |
|---------|-------------|
| **Chart** | A directory of templated YAML files that describe a set of Kubernetes resources |
| **Release** | A specific installation of a chart in a cluster (you can install the same chart multiple times) |
| **Repository** | A server that hosts packaged charts (like a package registry) |
| **values.yaml** | A file of configuration values that get injected into the templates at install time |

### How templating works

Instead of hardcoding values in your YAML, you use Go template syntax:

```yaml
# templates/deployment.yaml inside a Helm chart
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-{{ .Chart.Name }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          resources:
            limits:
              cpu: {{ .Values.resources.limits.cpu }}
              memory: {{ .Values.resources.limits.memory }}
```

Users override values at install time without ever editing templates:

```bash
helm install my-app ./my-chart --set replicaCount=3 --set image.tag=v2.0.0
```

### Example -- install PostgreSQL in one command

Helm repositories like [Bitnami](https://charts.bitnami.com/) provide production-ready charts for common software:

```bash
# Add the Bitnami chart repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install PostgreSQL with custom values
helm install my-postgres bitnami/postgresql \
  --set auth.postgresPassword=secretpassword \
  --set primary.persistence.size=10Gi

# Check what was deployed
helm list
helm status my-postgres
```

This single command creates a Deployment, Service, PersistentVolumeClaim, Secret, ConfigMap, and ServiceAccount -- all configured and wired together.

### Creating your own chart

```bash
# Scaffold a new chart
helm create fastapi-k8s-chart

# This creates:
# fastapi-k8s-chart/
#   Chart.yaml          -- metadata (name, version, description)
#   values.yaml         -- default configuration values
#   templates/          -- Kubernetes resource templates
#     deployment.yaml
#     service.yaml
#     ingress.yaml
#     _helpers.tpl      -- reusable template snippets
#   charts/             -- sub-chart dependencies
```

### Helm vs raw YAML

| Aspect | Raw YAML | Helm |
|--------|----------|------|
| Simplicity | Easier to read and debug | More complex, templating syntax |
| Reusability | Copy-paste between environments | One chart, multiple value files |
| Versioning | Manual tracking | Built-in chart versioning and rollback |
| Ecosystem | None | Thousands of community charts |
| Best for | Small projects, learning | Multi-environment, team projects |

!!! tip
    For this project, raw YAML in `k8s.yaml` is perfectly fine. Consider Helm when you need to deploy to multiple environments (dev, staging, prod) or want to share your app as a reusable package. For a complete deep-dive including creating a chart for this project, see [Helm Charts](helm.md).

---

## Kustomize -- built-in overlay system

[Kustomize](https://kustomize.io/) is built directly into `kubectl` (no separate install needed). It takes a different approach than Helm -- instead of templates, it uses a base-and-overlay model where you patch plain YAML.

### Bases and overlays

```
k8s/
  base/
    kustomization.yaml    # Lists resources to include
    deployment.yaml       # The base deployment (unchanged)
    service.yaml          # The base service (unchanged)
  overlays/
    dev/
      kustomization.yaml  # References base, applies dev patches
      replicas-patch.yaml
    prod/
      kustomization.yaml  # References base, applies prod patches
      replicas-patch.yaml
      resources-patch.yaml
```

**Base kustomization.yaml:**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
```

**Dev overlay kustomization.yaml:**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
namePrefix: dev-
patches:
  - path: replicas-patch.yaml
```

**Dev replicas-patch.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-k8s
spec:
  replicas: 2
```

**Prod overlay** might set 10 replicas, higher resource limits, and different ConfigMap values.

### Applying overlays

```bash
# Preview what will be generated
kubectl kustomize overlays/dev/

# Apply directly
kubectl apply -k overlays/prod/
```

### When to use Kustomize vs Helm

| Scenario | Kustomize | Helm |
|----------|-----------|------|
| Small per-environment differences | Great fit | Overkill |
| Complex applications with many options | Gets unwieldy | Better fit |
| Need to share charts publicly | Not designed for this | Built for this |
| Want to avoid templating | Yes, plain YAML | Requires Go templates |
| Already using `kubectl` | No extra tooling | Separate install |

!!! info
    Kustomize and Helm are not mutually exclusive. Many teams use Helm to install third-party charts and Kustomize to manage their own application manifests.

---

## CI/CD integration

### GitHub Actions workflow example

A typical pipeline builds a Docker image, pushes it to a container registry, and updates the Kubernetes deployment:

```yaml
# .github/workflows/deploy.yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:latest

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubeconfig
        run: echo "${{ secrets.KUBECONFIG }}" | base64 -d > $HOME/.kube/config

      - name: Update deployment image
        run: |
          kubectl set image deployment/fastapi-k8s \
            fastapi-k8s=ghcr.io/${{ github.repository }}:${{ github.sha }}

      - name: Wait for rollout
        run: kubectl rollout status deployment/fastapi-k8s --timeout=120s
```

### GitOps with ArgoCD or Flux

GitOps treats your Git repository as the single source of truth for what should be running in the cluster. Instead of CI pushing changes to the cluster, a controller inside the cluster watches the repo and syncs automatically.

**How it works:**

1. Developer pushes code -- CI builds and pushes a new image
2. Developer (or CI) updates the image tag in the Git repo's Kubernetes manifests
3. ArgoCD or Flux detects the change in Git
4. The controller applies the new manifests to the cluster
5. If someone manually changes something in the cluster, the controller reverts it to match Git

**ArgoCD** provides a web UI showing sync status, diff views, and rollback controls. **Flux** is lighter-weight and operates purely through Git and Kubernetes CRDs.

!!! tip
    GitOps is especially valuable for teams because every change is auditable in Git history. No one needs direct `kubectl` access to production.

### Image tagging strategies

| Strategy | Example | Pros | Cons |
|----------|---------|------|------|
| Git SHA | `fastapi-k8s:a1b2c3d` | Immutable, traceable to exact commit | Not human-readable |
| Semantic version | `fastapi-k8s:v1.2.3` | Clear meaning, supports rollback | Requires manual version bumps |
| Branch + SHA | `fastapi-k8s:main-a1b2c3d` | Shows branch and commit | Verbose |
| `latest` | `fastapi-k8s:latest` | Convenient | **Anti-pattern** -- not immutable, breaks rollback, unclear what's running |

!!! warning
    Avoid using the `latest` tag in production. Kubernetes may not pull a new image if the tag hasn't changed (depending on `imagePullPolicy`), and you lose the ability to know exactly which version is deployed. In this project we use `latest` only because Docker Desktop pulls from the local daemon with `imagePullPolicy: Never`.

---

## Production clusters

Docker Desktop is great for learning, but production workloads need real clusters with high availability, security, and managed infrastructure.

### Managed Kubernetes services

Managed services handle the control plane (API server, etcd, scheduler, controller manager) for you. You only manage worker nodes.

| Service | Provider | Key characteristics |
|---------|----------|-------------------|
| **EKS** | AWS | Deeply integrated with AWS (IAM, ALB, EBS). Most popular. Charges per-cluster fee (~$0.10/hr) plus node costs |
| **GKE** | GCP | Often considered the most polished. GKE Autopilot fully manages nodes too. One free zonal cluster, then per-cluster fee |
| **AKS** | Azure | Free control plane (you pay only for nodes). Tight Azure AD integration. Good for Microsoft-heavy shops |

All three support the same Kubernetes APIs -- your `k8s.yaml` manifests work across providers with minimal changes (mainly around storage classes, load balancers, and IAM).

### Self-managed options

| Tool | Description |
|------|-------------|
| **kubeadm** | Official Kubernetes bootstrapping tool. Full control, full responsibility |
| **k3s** | Lightweight Kubernetes by Rancher. Single binary, uses SQLite instead of etcd by default. Great for edge, IoT, and small environments |
| **RKE2** | Rancher's enterprise-grade distribution. Focused on security and compliance |
| **Rancher** | Management platform that can provision and manage clusters across providers from a single UI |

### Multi-cluster

As organizations grow, they often run multiple clusters -- per region, per team, or per environment. Tools for managing this:

- **Cluster Federation** -- run workloads across clusters with a single API
- **Service mesh** (Istio, Linkerd) -- can span clusters for cross-cluster service discovery
- **Rancher / OpenShift** -- provide multi-cluster management dashboards

---

## Container registries

When you move beyond Docker Desktop's local image store, you need a registry to push and pull images.

| Registry | Provider | Notes |
|----------|----------|-------|
| **Docker Hub** | Docker | Default public registry. Free for public images, paid for private |
| **ECR** | AWS | Fully managed, integrated with EKS and IAM. Pay per storage and transfer |
| **GCR / Artifact Registry** | GCP | Artifact Registry is the newer replacement for GCR. Integrated with GKE |
| **ACR** | Azure | Integrated with AKS. Supports geo-replication |
| **GitHub Container Registry** | GitHub | Free for public images. Tight integration with GitHub Actions |
| **Harbor** | CNCF | Open-source, self-hosted. Adds vulnerability scanning, signing, replication |

!!! note
    In this project, `imagePullPolicy: Never` tells Kubernetes to use the image from Docker's local daemon. In production, you would push to a registry and set `imagePullPolicy: IfNotPresent` or `Always`.

---

## Infrastructure as Code

Provisioning the cluster itself (not just what runs on it) should also be automated and version-controlled.

### Terraform

[Terraform](https://www.terraform.io/) by HashiCorp is the most widely used IaC tool for cloud infrastructure:

```hcl
# main.tf -- provision an EKS cluster
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  cluster_name    = "my-production-cluster"
  cluster_version = "1.29"
  subnet_ids      = module.vpc.private_subnets

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 10
      desired_size   = 3
    }
  }
}
```

```bash
terraform init    # Download providers and modules
terraform plan    # Preview what will be created
terraform apply   # Create the infrastructure
```

### Other IaC tools

| Tool | Approach |
|------|----------|
| **Pulumi** | Define infrastructure using real programming languages (Python, TypeScript, Go) instead of HCL |
| **Crossplane** | Runs inside Kubernetes itself. Define cloud resources as Kubernetes CRDs. Ideal for platform teams |
| **CDK for Terraform (CDKTF)** | Write Terraform configs in TypeScript, Python, etc. Compiles to HCL |

---

## Service mesh

A service mesh adds a sidecar proxy to every pod, giving you infrastructure-level networking features without changing application code.

### What a service mesh adds

| Feature | Description |
|---------|-------------|
| **Mutual TLS (mTLS)** | Automatic encryption between all services -- no code changes needed |
| **Traffic management** | Canary deployments, traffic splitting (send 5% to v2), retries, timeouts |
| **Observability** | Distributed tracing, request metrics, service dependency graphs -- all automatic |
| **Access control** | Fine-grained policies for which services can talk to which |

### Istio vs Linkerd

| Aspect | Istio | Linkerd |
|--------|-------|---------|
| Complexity | Feature-rich but complex to operate | Simpler, lighter, opinionated |
| Resource overhead | Higher (Envoy sidecar) | Lower (Rust-based micro-proxy) |
| Features | More configuration options, traffic management | Focused on core mesh features |
| Learning curve | Steep | Moderate |
| Best for | Large organizations needing fine-grained control | Teams wanting mesh benefits with less operational burden |

!!! info
    A service mesh is overkill for this project or most small deployments. Consider it when you have many services communicating with each other and need consistent security, observability, or traffic control across all of them.

---

## Useful tools

These tools make day-to-day Kubernetes work significantly easier.

### k9s -- terminal UI

[k9s](https://k9scli.io/) provides a full terminal-based dashboard for your cluster. Navigate pods, view logs, exec into containers, delete resources -- all with keyboard shortcuts.

```bash
# Install
brew install derailed/k9s/k9s

# Launch (uses your current kubeconfig context)
k9s
```

It replaces dozens of `kubectl` commands with an interactive, searchable interface.

### Lens -- desktop application

[Lens](https://k8slens.dev/) is a graphical desktop app that connects to your clusters. It provides a visual overview of resources, real-time logs, metrics dashboards, and Helm chart management.

### kubectx and kubens -- fast context switching

When working with multiple clusters or namespaces, switching context with raw `kubectl` commands is tedious:

```bash
# Install
brew install kubectx

# Switch cluster context
kubectx my-production-cluster

# Switch namespace
kubens my-team-namespace

# Interactive selection (with fzf installed)
kubectx    # presents a fuzzy-searchable list
```

### stern -- multi-pod log tailing

`kubectl logs` works for a single pod, but `stern` tails logs from multiple pods simultaneously with color-coded output:

```bash
# Install
brew install stern

# Tail all pods matching a regex
stern fastapi-k8s

# Tail with timestamp and namespace
stern fastapi-k8s --timestamps --namespace default

# Only show logs from the last 5 minutes
stern fastapi-k8s --since 5m
```

### Other notable tools

| Tool | Purpose |
|------|---------|
| **kustomize** | Standalone binary (also built into kubectl) for YAML overlays |
| **helm-diff** | Helm plugin that shows a diff before upgrading a release |
| **kube-score** | Static analysis of Kubernetes manifests for best practices |
| **Popeye** | Scans your cluster for potential issues and misconfigurations |
| **kubectl-neat** | Cleans up `kubectl get -o yaml` output by removing managed fields |

---

## Certifications

The Cloud Native Computing Foundation (CNCF) offers three Kubernetes certifications -- all are performance-based exams (you solve real tasks in a live cluster, not multiple choice).

### CKA -- Certified Kubernetes Administrator

- **Focus:** Cluster installation, configuration, networking, storage, troubleshooting
- **Who should take it:** Platform engineers, SREs, DevOps engineers who manage clusters
- **Format:** 2 hours, 15-20 hands-on tasks in a live cluster
- **Prerequisite knowledge:** Comfortable with Linux, networking, and `kubectl`

### CKAD -- Certified Kubernetes Application Developer

- **Focus:** Designing, building, and deploying applications on Kubernetes
- **Who should take it:** Developers who deploy to Kubernetes (this is the natural next step after this guide)
- **Format:** 2 hours, 15-20 hands-on tasks
- **Prerequisite knowledge:** Can write Deployments, Services, ConfigMaps, and debug pod issues

### CKS -- Certified Kubernetes Security Specialist

- **Focus:** Cluster hardening, system hardening, supply chain security, runtime security
- **Who should take it:** Security engineers, senior platform engineers
- **Prerequisite:** Must hold a valid CKA certification

!!! tip
    If you have worked through this entire guide and are comfortable with all the concepts, CKAD is a realistic next goal. Practice with tools like [killer.sh](https://killer.sh/) (included with exam registration) and focus on speed -- the exam is time-pressured.

---

## Official resources and learning paths

### Kubernetes documentation

- [Kubernetes Docs](https://kubernetes.io/docs/home/) -- The definitive reference for every resource, field, and concept
- [Kubernetes Basics Tutorial](https://kubernetes.io/docs/tutorials/kubernetes-basics/) -- Interactive browser-based tutorial
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/) -- Quick reference for common commands
- [Kubernetes API Reference](https://kubernetes.io/docs/reference/kubernetes-api/) -- Complete API specification

### Interactive learning

- [Play with Kubernetes](https://labs.play-with-k8s.com/) -- Free browser-based Kubernetes clusters for experimenting
- [Killercoda](https://killercoda.com/) -- Interactive Kubernetes scenarios and exam practice
- [Kubernetes the Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) -- Kelsey Hightower's guide to setting up Kubernetes from scratch (teaches how everything fits together)

### CNCF landscape

The [CNCF Landscape](https://landscape.cncf.io/) maps the entire cloud-native ecosystem -- hundreds of projects organized by category (orchestration, runtime, observability, security, etc.). It can be overwhelming, but it is the best way to discover tools for specific needs.

### Community

- [Kubernetes Slack](https://slack.k8s.io/) -- Active community with channels for every topic
- [r/kubernetes](https://www.reddit.com/r/kubernetes/) -- Discussion, questions, and news
- [KubeCon](https://events.linuxfoundation.org/kubecon-cloudnativecon-north-america/) -- The main Kubernetes conference (recordings are free on YouTube)

---

## Suggested learning order

If you have completed this guide, here is a practical sequence for going deeper:

1. **Kustomize** -- Low overhead, immediately useful for managing dev vs prod configs
2. **Helm** -- Learn to use existing charts, then create your own
3. **CI/CD** -- Set up a GitHub Actions pipeline that deploys to your Docker Desktop cluster
4. **k9s** -- Install it now, use it daily, never look back
5. **A managed cluster** -- Spin up a small GKE Autopilot or AKS cluster (both have free tiers or credits)
6. **Terraform** -- Provision that cluster with code instead of clicking in a console
7. **CKAD certification** -- Validate your knowledge with a hands-on exam
8. **Service mesh** -- Only when you actually need it (multiple services, security requirements)
