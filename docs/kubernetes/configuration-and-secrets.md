# Configuration and Secrets

Kubernetes provides two core primitives for managing application configuration: **ConfigMaps** for non-sensitive data and **Secrets** for sensitive data. This guide covers both in depth, using our fastapi-k8s project as a running example.

## The twelve-factor app and configuration

The [twelve-factor app](https://12factor.net/) methodology states that configuration should be stored in the environment -- not in code. The reasoning is straightforward:

- **Hardcoded config is bad.** If your database URL is a string literal in `main.py`, you need to rebuild and redeploy every time it changes. Different environments (dev, staging, production) need different values, but your code should be identical across all of them.
- **Environment variables are universal.** Every language and framework can read them. They are easy to change between deploys without touching code.
- **Separation of concerns.** Developers write code; operators manage config. ConfigMaps and Secrets let each group work independently.

Our FastAPI app follows this pattern. Configuration values are read from environment variables with sensible defaults for local development:

```python
APP_NAME = os.getenv("APP_NAME", "fastapi-k8s")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
MAX_STRESS_SECONDS = int(os.getenv("MAX_STRESS_SECONDS", "30"))
```

When running locally with `make dev`, the defaults apply. When running in Kubernetes, the values come from a ConfigMap injected as environment variables.

## ConfigMaps in depth

A ConfigMap is a Kubernetes object that stores non-sensitive configuration as key-value pairs. It decouples configuration from container images, so you can change settings without rebuilding.

### Our fastapi-config ConfigMap

Our project defines a ConfigMap in `k8s.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastapi-config
  labels:
    app: fastapi-k8s
data:
  APP_NAME: "fastapi-k8s"
  LOG_LEVEL: "info"
  MAX_STRESS_SECONDS: "30"
```

!!! note "All values are strings"
    ConfigMap values are always strings. Even though `MAX_STRESS_SECONDS` is a number, it is stored as the string `"30"`. The application is responsible for parsing it to the correct type (e.g., `int(os.getenv("MAX_STRESS_SECONDS", "30"))`).

### Creating ConfigMaps

There are several ways to create a ConfigMap:

**From a YAML manifest** (what we use):

```bash
# Applied as part of k8s.yaml
kubectl apply -f k8s.yaml
```

**From literal values on the command line:**

```bash
kubectl create configmap fastapi-config \
  --from-literal=APP_NAME=fastapi-k8s \
  --from-literal=LOG_LEVEL=info \
  --from-literal=MAX_STRESS_SECONDS=30
```

**From an env file:**

```bash
# Create a file called config.env
# APP_NAME=fastapi-k8s
# LOG_LEVEL=info
# MAX_STRESS_SECONDS=30

kubectl create configmap fastapi-config --from-env-file=config.env
```

**From a regular file** (the entire file content becomes one value):

```bash
# Create a config file
echo '{"app_name": "fastapi-k8s", "log_level": "info"}' > app-config.json

kubectl create configmap fastapi-config --from-file=app-config.json
# This creates a key called "app-config.json" with the file contents as the value
```

!!! tip "Declarative vs imperative"
    Using a YAML manifest (`kubectl apply -f`) is the **declarative** approach -- you describe the desired state and Kubernetes makes it happen. Using `kubectl create` is **imperative** -- you tell Kubernetes exactly what to do. For production, always prefer the declarative approach because it is version-controlled, repeatable, and reviewable.

## Injecting ConfigMaps into pods

There are three ways to inject ConfigMap data into a container. Each has different trade-offs.

### envFrom -- inject all keys at once

This is what our project uses. Every key in the ConfigMap becomes an environment variable:

```yaml
containers:
  - name: fastapi-k8s
    envFrom:
      - configMapRef:
          name: fastapi-config
```

With our ConfigMap, the container gets three environment variables: `APP_NAME`, `LOG_LEVEL`, and `MAX_STRESS_SECONDS`.

**When to use:** When you want all keys from a ConfigMap as env vars and the key names match what your app expects. This is the simplest approach.

### configMapKeyRef -- inject individual keys

Pick specific keys and optionally rename them:

```yaml
containers:
  - name: fastapi-k8s
    env:
      - name: APP_NAME
        valueFrom:
          configMapKeyRef:
            name: fastapi-config
            key: APP_NAME
      - name: MY_LOG_LEVEL          # Renamed from LOG_LEVEL
        valueFrom:
          configMapKeyRef:
            name: fastapi-config
            key: LOG_LEVEL
```

**When to use:** When you need only a subset of keys, when you need to rename keys to match your app's expectations, or when you are pulling keys from multiple ConfigMaps.

### Volume mounts -- inject as files

Mount the ConfigMap as a directory where each key becomes a file:

```yaml
containers:
  - name: fastapi-k8s
    volumeMounts:
      - name: config-volume
        mountPath: /etc/config
        readOnly: true
volumes:
  - name: config-volume
    configMap:
      name: fastapi-config
```

This creates three files in the container:

- `/etc/config/APP_NAME` containing `fastapi-k8s`
- `/etc/config/LOG_LEVEL` containing `info`
- `/etc/config/MAX_STRESS_SECONDS` containing `30`

**When to use:** When your application reads config from files (e.g., `nginx.conf`, `application.yml`, `prometheus.yml`), or when you need config updates without pod restarts (see the updates section below).

### Comparison table

| Approach | Granularity | Rename keys | Auto-update | Simplicity |
|----------|-------------|-------------|-------------|------------|
| `envFrom` | All keys | No | No (requires restart) | Simplest |
| `configMapKeyRef` | Per key | Yes | No (requires restart) | Medium |
| Volume mount | All keys or subset | Via `items` | Yes (with delay) | More setup |

## Our walkthrough: changing configuration

Let's change the log level from `info` to `debug` and see it take effect.

```bash
# 1. Check the current config
curl -s http://localhost/config | python -m json.tool
# {
#     "app_name": "fastapi-k8s",
#     "log_level": "info",
#     "max_stress_seconds": 30
# }

# 2. Edit k8s.yaml -- change LOG_LEVEL from "info" to "debug"

# 3. Apply the change
make deploy
# configmap/fastapi-config configured
# deployment.apps/fastapi-k8s unchanged
# service/fastapi-k8s unchanged

# 4. Restart pods to pick up the new values
make restart

# 5. Wait for the rollout to complete
make rollout-status

# 6. Verify the change
curl -s http://localhost/config
# {"app_name":"fastapi-k8s","log_level":"debug","max_stress_seconds":30}
```

!!! warning "Why is the restart needed?"
    Environment variables are injected into a container when it starts. If you update a ConfigMap but do not restart the pods, the running containers still have the old values. This is a common source of confusion -- "I changed the ConfigMap, why is my app still using the old config?"

You can also inspect the ConfigMap directly with kubectl:

```bash
# View the ConfigMap
kubectl get configmap fastapi-config -o yaml

# View just the data section
kubectl describe configmap fastapi-config
```

## Immutable ConfigMaps

Starting with Kubernetes 1.21, you can mark a ConfigMap as immutable:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastapi-config-v1
immutable: true
data:
  APP_NAME: "fastapi-k8s"
  LOG_LEVEL: "info"
  MAX_STRESS_SECONDS: "30"
```

Once set, the `data` field cannot be modified. Any attempt to update it will be rejected by the API server.

### Why use immutable ConfigMaps?

- **Performance** -- Kubernetes watches all mutable ConfigMaps for changes. With immutable ConfigMaps, the kubelet does not need to watch them, significantly reducing load on the API server in clusters with many ConfigMaps.
- **Safety** -- Prevents accidental changes to config that could break running applications.
- **Versioning pattern** -- Use a naming convention like `fastapi-config-v1`, `fastapi-config-v2`, etc. Update the Deployment to reference the new name. This makes the config change part of the Deployment rollout, so rollbacks also revert the config.

!!! tip "Immutable ConfigMaps for production"
    The versioned naming pattern (`fastapi-config-v1`, `fastapi-config-v2`) combines well with rolling updates. When you update the Deployment to reference a new ConfigMap name, Kubernetes treats it as a pod template change and triggers a rolling update. If you roll back the Deployment, it automatically reverts to the old ConfigMap too.

## Secrets in depth

Secrets are the sibling of ConfigMaps, designed for sensitive data like passwords, API keys, TLS certificates, and tokens.

### base64 encoding is NOT encryption

This is the most important thing to understand about Kubernetes Secrets:

```bash
# Encoding a value
echo -n "super-secret-key" | base64
# c3VwZXItc2VjcmV0LWtleQ==

# Decoding it right back
echo "c3VwZXItc2VjcmV0LWtleQ==" | base64 --decode
# super-secret-key
```

Base64 is an encoding, not encryption. Anyone with access to the Secret object can decode it instantly. The encoding exists only so that binary data (like TLS certificates) can be stored in YAML/JSON. **Do not rely on base64 for security.**

!!! warning "Secrets are not secret by default"
    Out of the box, Kubernetes stores Secrets as plaintext in etcd (the cluster's key-value store). Anyone with API access or direct etcd access can read them. See the security best practices section below for how to actually protect your secrets.

### Creating Secrets

**From a YAML manifest:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fastapi-secrets
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXM6Ly91c2VyOnBhc3NAZGI6NTQzMi9teWRi
  API_KEY: c3VwZXItc2VjcmV0LWtleQ==
```

The values must be base64-encoded. You can also use `stringData` to provide plain-text values that Kubernetes will encode for you:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fastapi-secrets
type: Opaque
stringData:
  DATABASE_URL: "postgres://user:pass@db:5432/mydb"
  API_KEY: "super-secret-key"
```

!!! tip "Use stringData to avoid manual base64 encoding"
    The `stringData` field accepts plain-text values and is more readable. Kubernetes converts them to base64 when storing. Note that `kubectl get secret -o yaml` will always show the base64-encoded `data` field, even if you used `stringData` to create the Secret.

**From literal values:**

```bash
kubectl create secret generic fastapi-secrets \
  --from-literal=DATABASE_URL="postgres://user:pass@db:5432/mydb" \
  --from-literal=API_KEY="super-secret-key"
```

**From a file:**

```bash
kubectl create secret generic tls-cert \
  --from-file=cert.pem=/path/to/cert.pem \
  --from-file=key.pem=/path/to/key.pem
```

### Secret types

Kubernetes has several built-in Secret types:

| Type | Purpose |
|------|---------|
| `Opaque` | Generic key-value pairs (default) |
| `kubernetes.io/dockerconfigjson` | Docker registry credentials |
| `kubernetes.io/tls` | TLS certificate and private key |
| `kubernetes.io/basic-auth` | Username and password |
| `kubernetes.io/ssh-auth` | SSH private key |
| `kubernetes.io/service-account-token` | ServiceAccount token (auto-created) |

The type affects validation -- for example, a `kubernetes.io/tls` Secret must contain `tls.crt` and `tls.key` fields. For most application secrets, `Opaque` is the right choice.

## Using Secrets in pods

Secrets can be injected into pods in the same ways as ConfigMaps.

### As environment variables (secretKeyRef)

```yaml
containers:
  - name: fastapi-k8s
    env:
      - name: DATABASE_URL
        valueFrom:
          secretKeyRef:
            name: fastapi-secrets
            key: DATABASE_URL
      - name: API_KEY
        valueFrom:
          secretKeyRef:
            name: fastapi-secrets
            key: API_KEY
```

You can also use `envFrom` with a `secretRef` to inject all keys:

```yaml
envFrom:
  - secretRef:
      name: fastapi-secrets
```

### As volume mounts

```yaml
containers:
  - name: fastapi-k8s
    volumeMounts:
      - name: secret-volume
        mountPath: /etc/secrets
        readOnly: true
volumes:
  - name: secret-volume
    secret:
      secretName: fastapi-secrets
```

This mounts each key as a file in `/etc/secrets/` (e.g., `/etc/secrets/DATABASE_URL`, `/etc/secrets/API_KEY`). The files have `0644` permissions by default, but you can restrict them:

```yaml
volumes:
  - name: secret-volume
    secret:
      secretName: fastapi-secrets
      defaultMode: 0400    # Read-only for the file owner
```

### Comparing ConfigMaps and Secrets

| Aspect | ConfigMap | Secret |
|--------|-----------|--------|
| Purpose | Non-sensitive config | Sensitive data |
| Storage | Plaintext in etcd | Base64 in etcd (can be encrypted at rest) |
| Size limit | 1 MiB | 1 MiB |
| `kubectl get` output | Shows data | Hides data (shows base64) |
| Can be immutable | Yes | Yes |
| Injection methods | envFrom, env, volume | envFrom, env, volume |

In practice, the API is nearly identical. The main difference is that `kubectl` treats Secrets with slightly more care (not printing values in `describe` output) and that the cluster can be configured to encrypt Secrets at rest in etcd.

## envFrom vs individual refs

Choosing between `envFrom` (bulk injection) and individual `configMapKeyRef`/`secretKeyRef` depends on your needs:

| Criteria | envFrom | Individual refs |
|----------|---------|-----------------|
| Setup effort | One block per ConfigMap/Secret | One block per key |
| Key naming | Must match ConfigMap/Secret keys | Can rename with `name:` field |
| Subset selection | All or nothing | Pick exactly what you need |
| Multiple sources | Can combine multiple `envFrom` entries | Can mix ConfigMap and Secret keys |
| Conflict handling | Last `envFrom` entry wins on key collision | Explicit -- no collisions |
| Readability | Concise | Verbose but clear |

!!! info "When to use each"
    Use `envFrom` when the ConfigMap/Secret is purpose-built for your app and all keys should be injected (our case). Use individual refs when you need to pull specific keys from shared ConfigMaps, rename keys, or mix keys from multiple sources.

## ConfigMap and Secret updates

Understanding how updates propagate is critical to avoiding surprises in production.

### Environment variables do NOT update without restart

When you use `envFrom` or `configMapKeyRef` / `secretKeyRef` to inject values as environment variables, the values are set when the container starts. If you update the ConfigMap or Secret afterward:

- Running containers **keep the old values**.
- You must restart the pods to pick up changes.

```bash
# After updating a ConfigMap, restart the pods
make restart
# or
kubectl rollout restart deployment/fastapi-k8s
```

This is the behavior our project uses. It is predictable and safe -- you control exactly when pods pick up new config.

### Volume-mounted ConfigMaps DO update (with delay)

If you mount a ConfigMap as a volume, the kubelet periodically syncs the mounted files with the ConfigMap. The update delay depends on:

- The kubelet sync period (default: 60 seconds).
- The ConfigMap cache TTL (default: up to 60 seconds).

So after updating a ConfigMap, volume-mounted files can take up to **roughly 2 minutes** to reflect the change. The application must re-read the files to pick up the new values -- if it reads config once at startup and caches it in memory, it will not see updates.

!!! note "Volume-mounted Secrets also auto-update"
    The same auto-update behavior applies to Secrets mounted as volumes. This can be useful for rotating TLS certificates without restarting pods.

### How to force a restart after ConfigMap changes

If you want config changes to automatically trigger a pod restart, there is a common pattern: include the ConfigMap content hash in a pod annotation. When the ConfigMap changes, the annotation changes, which changes the pod template, which triggers a rolling update.

```yaml
spec:
  template:
    metadata:
      annotations:
        checksum/config: "sha256-of-configmap-data"
```

Tools like Helm automate this with `{{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}`. For our project, manually running `make restart` after `make deploy` is simple enough.

## Security best practices for Secrets

Since Kubernetes Secrets are not encrypted by default, follow these practices to protect sensitive data:

### Never commit Secrets to git

Secret YAML files with base64-encoded values should never be checked into version control. Base64 is trivially reversible -- committing a Secret to git is equivalent to committing the plaintext.

```bash
# Add to .gitignore
*-secret.yaml
*-secrets.yaml
```

### Enable encryption at rest

Configure the Kubernetes API server to encrypt Secrets in etcd. This uses an `EncryptionConfiguration` resource to encrypt Secret data before writing it to etcd. On managed Kubernetes services (EKS, GKE, AKS), this is often enabled by default.

### Use external secret managers

For production environments, store secrets in a dedicated secret management system and sync them into Kubernetes:

- **HashiCorp Vault** -- Full-featured secret management with dynamic secrets, leasing, and revocation. The Vault Agent Injector or Vault Secrets Operator syncs secrets into Kubernetes.
- **AWS Secrets Manager / SSM Parameter Store** -- Managed secret storage on AWS. Use the AWS Secrets and Configuration Provider (ASCP) with the Secrets Store CSI Driver.
- **Sealed Secrets (Bitnami)** -- Encrypts Secrets so they are safe to commit to git. A controller in the cluster decrypts them. Good for GitOps workflows.
- **External Secrets Operator** -- A Kubernetes operator that syncs secrets from external providers (AWS, GCP, Azure, Vault, etc.) into Kubernetes Secrets.

### Restrict access with RBAC

Use Kubernetes RBAC to limit who can read Secrets:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]            # Read only, no list or watch
    resourceNames: ["fastapi-secrets"]   # Only this specific Secret
```

By default, anyone with cluster-admin access can read all Secrets. In production, follow the principle of least privilege -- only grant Secret access to the specific ServiceAccounts that need it.

### Avoid logging Secret values

Make sure your application does not log environment variables or request headers that contain secrets. A common mistake is a startup log line like `Loaded config: {all_env_vars}` that accidentally prints database passwords.

## Summary

| Concept | Key takeaway |
|---------|-------------|
| ConfigMaps | Non-sensitive config as key-value pairs. Use `envFrom` for simplicity. |
| Secrets | Sensitive data. Base64-encoded, NOT encrypted by default. |
| envFrom | Injects all keys at once. Simple but no renaming. |
| configMapKeyRef / secretKeyRef | Inject individual keys. Can rename. More verbose. |
| Volume mounts | ConfigMap/Secret keys become files. Auto-updates (with delay). |
| Immutable ConfigMaps | Better performance, prevents accidental changes. |
| Updates | Env vars require pod restart. Volume mounts auto-update. |
| Security | Never commit Secrets to git. Use external secret managers in production. |

For our fastapi-k8s project, the combination of a ConfigMap with `envFrom` and sensible defaults in the Python code keeps things simple. The `GET /config` endpoint makes it easy to verify that configuration changes have taken effect after a restart.
