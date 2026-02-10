# Helm Charts

Managing Kubernetes applications with raw YAML works well when you have a single environment and a handful of resources. But as projects grow, the pain becomes real: you copy-paste YAML between environments, hardcode values that should differ between dev and production, and have no built-in way to version or roll back a group of related resources as a unit.

Helm is the package manager for Kubernetes. It fills the same role that `apt` fills for Debian, `brew` for macOS, or `pip` for Python -- but instead of installing software on a single machine, Helm installs and manages applications on a Kubernetes cluster. A single Helm command can create a Deployment, Service, ConfigMap, Secret, and PVC all wired together and configured for your environment.

This page starts with what Helm solves, walks through using existing charts (the way most people start), and then builds a chart from scratch for our fastapi-k8s project.

!!! info "Project chart"
    This project includes a ready-to-use Helm chart at `helm/`. It packages the FastAPI app, ConfigMap, Service, optional Redis, and optional HPA into a single parameterized release. See [Using the project chart](#using-the-project-chart) for quick-start commands.

## Why Helm

Consider our current project. We have three separate YAML files with hardcoded values:

| File | Resources | Hardcoded values |
|------|-----------|-----------------|
| `k8s.yaml` | ConfigMap, Deployment, Service | Replica count, image name, resource limits, ConfigMap data, service type |
| `k8s/redis.yaml` | PVC, Deployment, Service | Storage size, image tag, resource limits, volume names |
| `k8s/redis-secret.yaml` | Secret | Redis password |

If you wanted to run a second environment (say, a staging cluster with fewer replicas and a different log level), you would need to copy all three files and change values by hand. Forget one file and your staging environment breaks. Change a value in production and forget to update staging, and they silently drift apart.

Helm solves these problems:

- **Parameterization** -- Values that differ between environments are extracted into a single `values.yaml` file. Templates reference these values, so one chart works for dev, staging, and production.
- **Versioning** -- Every chart has a version number. You know exactly which version is deployed, and you can pin dependencies to specific versions.
- **Atomic operations** -- Installing a chart creates all its resources together. Uninstalling removes them all. No orphaned ConfigMaps or forgotten Services.
- **Rollback** -- Helm tracks the history of every release. Rolling back is a single command that restores the previous set of resources and configuration.
- **Ecosystem** -- Thousands of community-maintained charts exist for databases, monitoring stacks, ingress controllers, and more. Installing PostgreSQL or Prometheus takes one command instead of hundreds of lines of YAML.

## Core Concepts

Helm introduces a small set of concepts that map to familiar ideas:

| Concept | Description |
|---------|-------------|
| **Chart** | A package of templated Kubernetes manifests, default values, and metadata. Similar to a Debian `.deb` or a Python wheel. |
| **Release** | A specific installation of a chart in a cluster. You can install the same chart multiple times with different names and values. |
| **Repository** | A server that hosts packaged charts. Similar to PyPI or a Homebrew tap. |
| **Values** | Configuration that customizes a chart installation. Provided via `values.yaml` files or `--set` flags. |
| **Template** | A Kubernetes manifest with Go template syntax (`{{ .Values.x }}`) that Helm renders into plain YAML before applying. |

!!! note "Chart vs Release"
    A chart is a package on disk or in a repository. A release is a running instance of that chart in your cluster. One chart can produce many releases -- for example, you might install the same Redis chart three times with release names `redis-cache`, `redis-sessions`, and `redis-queue`, each with different configuration.

## Installing Helm

Helm is a single binary that talks to your cluster through the same kubeconfig file that `kubectl` uses. If `kubectl` can reach your cluster, so can Helm.

```bash
# Install with Homebrew
brew install helm

# Verify the installation
helm version
```

No server-side component is needed. Helm 3 (the current version) communicates directly with the Kubernetes API server using your kubeconfig credentials.

## Using Existing Charts

The most common way to start with Helm is installing software that someone else has already packaged. Community chart repositories contain production-ready configurations for databases, monitoring tools, ingress controllers, and hundreds of other applications.

### Adding a repository

Chart repositories are remote servers that host packaged charts. You add them to your local Helm configuration and then search or install from them.

```bash
# Add the Bitnami repository (one of the largest chart collections)
helm repo add bitnami https://charts.bitnami.com/bitnami

# Update your local cache of available charts
helm repo update

# List all configured repositories
helm repo list
```

### Searching for charts

You can search your added repositories or the Artifact Hub (a centralized catalog of charts from many sources).

```bash
# Search your added repositories
helm search repo redis

# Search with version information
helm search repo redis --versions

# Search the Artifact Hub (public catalog)
helm search hub postgresql
```

### Installing a chart

The `helm install` command creates a release from a chart. You give it a release name and the chart reference.

```bash
# Basic install
helm install my-redis bitnami/redis

# Install with value overrides using --set
helm install my-redis bitnami/redis \
  --set auth.password=mysecretpass \
  --set replica.replicaCount=0

# Install with a values file
helm install my-redis bitnami/redis -f my-redis-values.yaml

# Install into a specific namespace (create it if it does not exist)
helm install my-redis bitnami/redis \
  --namespace redis-system \
  --create-namespace
```

!!! tip
    Use `-f values.yaml` for anything more than one or two overrides. A values file is easier to review, version-control, and share than a long chain of `--set` flags.

### Inspecting what was installed

After installing a chart, Helm provides several commands to see what is running.

```bash
# List all releases in the current namespace
helm list

# List releases across all namespaces
helm list --all-namespaces

# Show detailed status of a release
helm status my-redis

# Show the values that were used for a release
helm get values my-redis

# Show the rendered Kubernetes manifests that Helm applied
helm get manifest my-redis
```

### Upgrading a release

When you want to change configuration or update to a newer chart version, use `helm upgrade`.

```bash
# Change a value
helm upgrade my-redis bitnami/redis --set replica.replicaCount=3

# Upgrade using a values file
helm upgrade my-redis bitnami/redis -f my-redis-values.yaml

# Upgrade or install if the release does not exist yet
helm upgrade --install my-redis bitnami/redis -f my-redis-values.yaml
```

The `--install` flag makes `helm upgrade` idempotent -- it installs the release if it does not exist, or upgrades it if it does. This is useful in CI/CD pipelines where you do not want to check whether the release exists first.

### Rolling back

Helm keeps a history of every release revision. If an upgrade causes problems, you can roll back to any previous revision.

```bash
# View the history of a release
helm history my-redis

# Roll back to the previous revision
helm rollback my-redis

# Roll back to a specific revision number
helm rollback my-redis 2
```

### Uninstalling

Removing a release deletes all the Kubernetes resources it created.

```bash
# Uninstall a release
helm uninstall my-redis

# Uninstall and keep the release history (for auditing)
helm uninstall my-redis --keep-history
```

!!! warning
    `helm uninstall` deletes all resources created by the release, including PersistentVolumeClaims by default in some charts. Check the chart documentation before uninstalling if you have data you want to keep.

## Practical Example: Redis via Helm

Our project manually deploys Redis using three files: `k8s/redis-secret.yaml` (Secret), `k8s/redis.yaml` (PVC, Deployment, Service). With Helm, this entire setup can be replaced with a single command.

```bash
# Add the Bitnami repository (if not already added)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install Redis with settings that match our manual setup
helm install redis bitnami/redis \
  --set auth.password=redis-learning-pwd-123 \
  --set architecture=standalone \
  --set master.persistence.size=100Mi \
  --set master.resources.requests.cpu=50m \
  --set master.resources.requests.memory=64Mi \
  --set master.resources.limits.cpu=200m \
  --set master.resources.limits.memory=128Mi
```

Compare what each approach creates:

| Resource | Our manual YAML | Bitnami Helm chart |
|----------|----------------|-------------------|
| Secret | `redis-secret` with `REDIS_PASSWORD` | Auto-generated with password |
| PVC | `redis-pvc` (100Mi) | Managed by the chart with configurable size |
| Deployment | Single replica, `redis:7-alpine` | StatefulSet with configurable replicas |
| Service | `redis` ClusterIP on 6379 | Headless + ClusterIP services |
| ConfigMap | None | Redis configuration file |
| ServiceAccount | None | Dedicated service account |
| NetworkPolicy | None | Optional, configurable |

The Helm chart creates more resources because it follows production best practices (StatefulSet for stable identity, dedicated ServiceAccount, configurable networking). Our hand-rolled YAML is simpler and easier to understand, which is the right choice for a learning project.

!!! tip "When to use a chart vs hand-rolled YAML"
    Use Helm charts when you want production-ready defaults and do not need to understand every detail of the deployment. Write YAML by hand when you want full control, are learning Kubernetes, or have simple requirements that a full chart would overcomplicate.

## Chart Anatomy

Every Helm chart follows a standard directory structure. Running `helm create` scaffolds a new chart with all the required files.

```bash
helm create fastapi-k8s-chart
```

This produces:

```
fastapi-k8s-chart/
  Chart.yaml            # Chart metadata (name, version, description)
  values.yaml           # Default configuration values
  charts/               # Sub-chart dependencies
  templates/            # Kubernetes resource templates
    deployment.yaml
    service.yaml
    serviceaccount.yaml
    ingress.yaml
    hpa.yaml
    NOTES.txt           # Post-install instructions shown to the user
    _helpers.tpl         # Reusable template snippets
    tests/
      test-connection.yaml
```

### Chart.yaml

The `Chart.yaml` file contains metadata about the chart.

| Field | Description |
|-------|-------------|
| `apiVersion` | Chart API version. Use `v2` for Helm 3. |
| `name` | The chart name. |
| `version` | The chart version (SemVer). Increment this when the chart changes. |
| `appVersion` | The version of the application being deployed. Informational only. |
| `description` | A one-line description of the chart. |
| `type` | `application` (default, installs resources) or `library` (provides helpers only). |

```yaml
apiVersion: v2
name: fastapi-k8s-chart
description: A Helm chart for the fastapi-k8s application
type: application
version: 0.1.0
appVersion: "1.0.0"
```

### values.yaml

The `values.yaml` file defines the default configuration for the chart. Users override these values at install time without editing the templates.

Values are organized as a nested YAML structure. Templates access them through the `.Values` object (e.g., `.Values.replicaCount`, `.Values.image.repository`).

```yaml
# Default values for fastapi-k8s-chart
replicaCount: 5

image:
  repository: fastapi-k8s
  tag: latest
  pullPolicy: Never

service:
  type: LoadBalancer
  port: 80
  targetPort: 8000

resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

Overrides follow a precedence chain: chart defaults are overridden by `-f values.yaml` files, which are overridden by `--set` flags. This is covered in detail in [Values Files and Overrides](#values-files-and-overrides).

### templates/

The `templates/` directory contains Kubernetes manifests with Go template syntax. Helm renders these templates by injecting values from `values.yaml` (and any overrides) to produce plain YAML, which is then applied to the cluster.

Common template constructs:

| Syntax | Purpose | Example |
|--------|---------|---------|
| `{{ .Values.x }}` | Insert a value | `replicas: {{ .Values.replicaCount }}` |
| `{{ .Release.Name }}` | Insert the release name | `name: {{ .Release.Name }}-config` |
| `{{ .Chart.Name }}` | Insert the chart name | `app: {{ .Chart.Name }}` |
| `{{ include "name" . }}` | Include a named template | `{{ include "fastapi.fullname" . }}` |
| `{{ if .Values.x }}` | Conditional block | Render a section only if a value is set |
| `{{ range .Values.x }}` | Loop over a list or map | Generate multiple env vars from a map |
| `{{ toYaml .Values.x \| nindent N }}` | Render nested YAML with indentation | Inline resource limits |

### _helpers.tpl

The `_helpers.tpl` file defines reusable named templates (partials) that other templates can include. By convention, template names start with the chart name to avoid collisions with sub-charts.

```yaml
# templates/_helpers.tpl

# Chart fullname (release-name + chart-name, truncated to 63 chars)
{{- define "fastapi-k8s-chart.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

# Common labels applied to every resource
{{- define "fastapi-k8s-chart.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

# Selector labels (subset of common labels, used in matchLabels)
{{- define "fastapi-k8s-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

### charts/

The `charts/` directory holds sub-chart dependencies. If your application depends on another chart (e.g., a Redis chart), you declare it in `Chart.yaml` and Helm downloads it into `charts/`.

```yaml
# Chart.yaml dependency example
dependencies:
  - name: redis
    version: "18.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
```

```bash
# Download dependencies into charts/
helm dependency update
```

## Creating a Chart for fastapi-k8s

This section walks through converting our raw YAML into a Helm chart. The goal is to produce a single chart that replaces `k8s.yaml`, `k8s/redis.yaml`, `k8s/redis-secret.yaml`, and `k8s/hpa.yaml` with templatized versions where environment-specific values are configurable.

The project chart lives at `helm/` in the repository root. It contains:

```
helm/
  Chart.yaml            # Chart metadata (name, version, description)
  values.yaml           # Default configuration values
  templates/
    _helpers.tpl         # Reusable template snippets
    configmap.yaml       # App ConfigMap
    deployment.yaml      # App Deployment
    service.yaml         # App Service (LoadBalancer)
    hpa.yaml             # HPA (optional, off by default)
    redis-secret.yaml    # Redis Secret (optional, on by default)
    redis-pvc.yaml       # Redis PVC (optional)
    redis-deployment.yaml # Redis Deployment (optional)
    redis-service.yaml   # Redis ClusterIP Service (optional)
    NOTES.txt            # Post-install instructions
```

### Chart.yaml

The `Chart.yaml` contains our project metadata.

```yaml
apiVersion: v2
name: fastapi-k8s
description: FastAPI app deployed to Kubernetes
type: application
version: 0.1.0
appVersion: "1.0.0"
```

### values.yaml

Every configurable value is extracted into `values.yaml`. This is the file users edit to customize the deployment.

```yaml
replicaCount: 5

image:
  repository: fastapi-k8s
  tag: latest
  pullPolicy: Never

service:
  type: LoadBalancer
  port: 80
  targetPort: 8000

resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi

config:
  appName: "fastapi-k8s"
  logLevel: "info"
  maxStressSeconds: "30"

strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0

probes:
  liveness:
    path: /health
    initialDelaySeconds: 3
    periodSeconds: 10
  readiness:
    path: /ready
    initialDelaySeconds: 2
    periodSeconds: 5

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilization: 50

redis:
  enabled: true
  password: "redis-learning-pwd-123"
  image:
    repository: redis
    tag: 7-alpine
  port: 6379
  persistence:
    size: 100Mi
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 128Mi
```

Redis resources are controlled by `redis.enabled` (default `true`). The HPA is controlled by `autoscaling.enabled` (default `false`). When `autoscaling.enabled` is `true`, the `replicaCount` field is ignored since the HPA manages replica count.

### templates/configmap.yaml

Our ConfigMap template replaces hardcoded values with references to `.Values.config`. When Redis is enabled, `REDIS_HOST` is dynamically set to the Helm-named Redis service.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "fastapi-k8s.fullname" . }}-config
  labels:
    {{- include "fastapi-k8s.labels" . | nindent 4 }}
data:
  APP_NAME: {{ .Values.config.appName | quote }}
  LOG_LEVEL: {{ .Values.config.logLevel | quote }}
  MAX_STRESS_SECONDS: {{ .Values.config.maxStressSeconds | quote }}
  {{- if .Values.redis.enabled }}
  REDIS_HOST: {{ include "fastapi-k8s.redisFullname" . | quote }}
  REDIS_PORT: {{ .Values.redis.port | quote }}
  {{- end }}
```

### templates/deployment.yaml

The Deployment template is the most complex, covering replicas, image, resources, probes, and environment variables.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "fastapi-k8s.fullname" . }}
  labels:
    {{- include "fastapi-k8s.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  strategy:
    type: {{ .Values.strategy.type }}
    {{- if eq .Values.strategy.type "RollingUpdate" }}
    rollingUpdate:
      maxSurge: {{ .Values.strategy.rollingUpdate.maxSurge }}
      maxUnavailable: {{ .Values.strategy.rollingUpdate.maxUnavailable }}
    {{- end }}
  selector:
    matchLabels:
      {{- include "fastapi-k8s.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "fastapi-k8s.selectorLabels" . | nindent 8 }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.service.targetPort }}
          livenessProbe:
            httpGet:
              path: {{ .Values.probes.liveness.path }}
              port: {{ .Values.service.targetPort }}
            initialDelaySeconds: {{ .Values.probes.liveness.initialDelaySeconds }}
            periodSeconds: {{ .Values.probes.liveness.periodSeconds }}
          readinessProbe:
            httpGet:
              path: {{ .Values.probes.readiness.path }}
              port: {{ .Values.service.targetPort }}
            initialDelaySeconds: {{ .Values.probes.readiness.initialDelaySeconds }}
            periodSeconds: {{ .Values.probes.readiness.periodSeconds }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          envFrom:
            - configMapRef:
                name: {{ include "fastapi-k8s.fullname" . }}-config
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_IP
              valueFrom:
                fieldRef:
                  fieldPath: status.podIP
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            # ... resource field refs for CPU_REQUEST, CPU_LIMIT, etc.
            {{- if .Values.redis.enabled }}
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "fastapi-k8s.redisFullname" . }}-secret
                  key: REDIS_PASSWORD
            {{- end }}
```

Notice how `{{ .Values.replicaCount }}`, `{{ .Values.image.repository }}`, and `{{ toYaml .Values.resources }}` replace the hardcoded values from our original `k8s.yaml`. The Downward API environment variables remain static because they reference pod metadata, not configurable values. The `REDIS_PASSWORD` env var is conditionally included only when `redis.enabled` is `true`.

### templates/service.yaml

The Service template is straightforward.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "fastapi-k8s.fullname" . }}
  labels:
    {{- include "fastapi-k8s.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
  selector:
    {{- include "fastapi-k8s.selectorLabels" . | nindent 4 }}
```

### Conditional templates

The HPA and Redis templates are wrapped in conditionals so they only render when enabled:

```yaml
# templates/hpa.yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
# ...
{{- end }}
```

```yaml
# templates/redis-deployment.yaml (and redis-secret, redis-pvc, redis-service)
{{- if .Values.redis.enabled }}
apiVersion: apps/v1
kind: Deployment
# ...
{{- end }}
```

This keeps the chart flexible: `helm template fastapi-k8s ./helm --set redis.enabled=false` produces zero Redis resources, while `--set autoscaling.enabled=true` adds the HPA.

### Using the project chart

With the chart in place, deploy using Make targets or Helm directly.

```bash
# Install the chart with default values
make helm-install
# or: helm install fastapi-k8s ./helm

# Upgrade (or install if not present)
make helm-upgrade
# or: helm upgrade --install fastapi-k8s ./helm

# Verify the release
make helm-status

# Render templates locally without installing (dry-run)
make helm-template

# Uninstall
make helm-uninstall

# Check that all resources were created
kubectl get configmap,deployment,service -l app.kubernetes.io/instance=fastapi-k8s
```

### Overriding values

The power of Helm becomes clear when you need different configurations for different environments.

```bash
# Scale up from the command line
helm upgrade fastapi-k8s ./helm --set replicaCount=3

# Deploy without Redis
helm upgrade fastapi-k8s ./helm --set redis.enabled=false

# Enable HPA
helm upgrade fastapi-k8s ./helm --set autoscaling.enabled=true

# Use an environment-specific values file
helm upgrade fastapi-k8s ./helm -f values-dev.yaml
```

A `values-dev.yaml` for local development might look like:

```yaml
# values-dev.yaml -- overrides for local development
replicaCount: 2

resources:
  requests:
    cpu: 25m
    memory: 32Mi
  limits:
    cpu: 100m
    memory: 64Mi

config:
  logLevel: "debug"
```

Only the values that differ from the defaults need to be specified. Everything else falls through to `values.yaml`.

## Values Files and Overrides

Helm applies values in a specific precedence order. Later sources override earlier ones:

1. **Chart defaults** (`values.yaml` in the chart) -- lowest priority
2. **Parent chart values** (if this chart is a sub-chart)
3. **User values files** (`-f values.yaml` or `--values values.yaml`) -- applied in the order specified
4. **`--set` flags** -- highest priority

```bash
# This command applies three layers of values:
# 1. Chart defaults (values.yaml in the chart)
# 2. values-prod.yaml overrides
# 3. --set override (highest priority)
helm install fastapi-k8s ./helm \
  -f values-prod.yaml \
  --set replicaCount=10
```

A common pattern for managing multiple environments is to maintain a values file per environment:

```
fastapi-k8s-chart/
  values.yaml          # defaults (shared across all environments)
  values-dev.yaml      # local development overrides
  values-staging.yaml  # staging environment overrides
  values-prod.yaml     # production overrides
```

```yaml
# values-prod.yaml
replicaCount: 10

image:
  pullPolicy: Always

resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi

config:
  logLevel: "warning"
  maxStressSeconds: "10"
```

```bash
# Deploy to each environment
helm upgrade --install fastapi-k8s ./helm -f values-dev.yaml
helm upgrade --install fastapi-k8s ./helm -f values-staging.yaml
helm upgrade --install fastapi-k8s ./helm -f values-prod.yaml
```

## Helm Lifecycle Commands

This table summarizes all key Helm commands in one place.

| Command | Description |
|---------|-------------|
| `helm install <name> <chart>` | Create a new release |
| `helm upgrade <name> <chart>` | Upgrade an existing release |
| `helm upgrade --install <name> <chart>` | Install or upgrade (idempotent) |
| `helm rollback <name> [revision]` | Roll back to a previous revision |
| `helm uninstall <name>` | Delete a release and its resources |
| `helm list` | List all releases in the current namespace |
| `helm status <name>` | Show status of a release |
| `helm history <name>` | Show revision history of a release |
| `helm get values <name>` | Show the values used for a release |
| `helm get manifest <name>` | Show the rendered manifests for a release |
| `helm template <name> <chart>` | Render templates locally without installing |
| `helm lint <chart>` | Check a chart for errors and best practices |
| `helm package <chart>` | Package a chart into a `.tgz` archive |
| `helm repo add <name> <url>` | Add a chart repository |
| `helm repo update` | Update local cache of chart repositories |
| `helm search repo <keyword>` | Search added repositories |
| `helm dependency update <chart>` | Download chart dependencies |

## Debugging Charts

When templates produce unexpected output or installations fail, Helm provides several tools for diagnosing problems.

### Rendering templates locally

The `helm template` command renders templates without contacting the cluster. This is the fastest way to see what YAML Helm will produce.

```bash
# Render all templates with default values
helm template fastapi-k8s ./helm

# Render with specific value overrides
helm template fastapi-k8s ./helm --set replicaCount=3

# Render a single template file
helm template fastapi-k8s ./helm -s templates/deployment.yaml
```

### Linting

The `helm lint` command checks a chart for common issues: missing required fields, malformed templates, and best-practice violations.

```bash
helm lint ./helm
```

### Dry-run install

A dry-run sends the rendered templates to the cluster for server-side validation without actually creating resources.

```bash
helm install fastapi-k8s ./helm --dry-run
```

This catches errors that `helm template` alone cannot, such as invalid API versions, schema violations, and admission webhook rejections.

### Inspecting a deployed release

If a release is already installed and behaving unexpectedly, inspect the manifests that Helm applied.

```bash
# Show the actual manifests applied to the cluster
helm get manifest fastapi-k8s

# Show the values that were used
helm get values fastapi-k8s

# Show all information about the release
helm get all fastapi-k8s
```

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `template: ... unexpected "}" in operand` | Malformed Go template syntax | Check for missing or extra braces, unclosed `{{ if }}` blocks |
| `Error: YAML parse error` | Indentation or quoting issue in rendered output | Use `helm template` to inspect the rendered YAML |
| `nil pointer evaluating interface {}` | Referencing a `.Values` key that does not exist | Add a default or wrap in `{{ if }}` |
| `cannot re-use a name that is still in use` | Release name already exists | Choose a different name or `helm upgrade` the existing release |
| `field is immutable` | Trying to change an immutable field on upgrade | Uninstall and reinstall, or avoid changing immutable fields (like selectors) |

## Helm vs Raw YAML vs Kustomize

Helm is not the only way to manage Kubernetes manifests. The right tool depends on your project's complexity and team needs.

| Aspect | Raw YAML | Helm | Kustomize |
|--------|----------|------|-----------|
| **Learning curve** | None | Moderate (Go templates) | Low (plain YAML patches) |
| **Parameterization** | None (copy-paste) | Full templating | Patches and overlays |
| **Versioning** | Manual | Built-in chart versioning | Git-based |
| **Rollback** | `kubectl rollout undo` (per resource) | `helm rollback` (all resources) | No built-in rollback |
| **Ecosystem** | None | Thousands of community charts | None |
| **Multi-environment** | Duplicate files | Values files per environment | Overlay directories per environment |
| **Built into kubectl** | Yes | No (separate install) | Yes (`kubectl apply -k`) |
| **Best for** | Small projects, learning | Multi-environment apps, third-party software | Small per-environment differences |

Our project currently uses raw YAML, which is the right choice for learning and for a single-environment deployment. Consider moving to Helm when you need to deploy to multiple environments, want to package the application for others, or start adding third-party dependencies (like Redis) that have well-maintained Helm charts. Consider Kustomize when your customizations are small patches (changing replica counts, namespaces, or labels) and you want to stay close to plain YAML.

See [Where to Go Next](next-steps.md) for more on Kustomize and the broader packaging landscape.

## Best Practices

- **Pin chart versions** in CI/CD pipelines. Use `--version` to avoid surprises when a chart updates.
- **Use `helm upgrade --install`** for idempotent deployments. This works whether the release exists or not.
- **Keep `values.yaml` documented.** Add comments explaining what each value does and what valid options are.
- **Use the `helm-diff` plugin.** It shows a diff of what will change before an upgrade, similar to `terraform plan`.
- **Do not store secrets in `values.yaml`.** Use Kubernetes Secrets, external secret managers, or tools like `helm-secrets` to encrypt sensitive values. See [Configuration & Secrets](configuration-and-secrets.md) for more on managing secrets.
- **Lint and template before deploying.** Run `helm lint` and `helm template` in CI to catch errors before they reach the cluster.
- **Use semantic versioning** for your chart's `version` field. Increment the major version for breaking changes, minor for new features, and patch for fixes.

## Summary

Helm bridges the gap between simple YAML files and production-grade deployment management. It gives you parameterization, versioning, rollback, and access to a large ecosystem of community charts -- all without leaving the command line.

Our fastapi-k8s project includes both approaches: raw YAML for transparency and learning, and a Helm chart at `helm/` that packages everything (app, Redis, HPA) into a single parameterized release. Use `make helm-install` to deploy with Helm, or continue using `make deploy` with raw YAML. Either way, the path between the two is short.

See [Features Overview](features.md) for a broad map of Kubernetes capabilities, [Configuration & Secrets](configuration-and-secrets.md) for the configuration patterns that Helm builds on, or [Where to Go Next](next-steps.md) for the broader landscape of tools and platforms.
