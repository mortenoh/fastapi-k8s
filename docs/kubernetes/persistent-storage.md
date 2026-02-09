# Persistent Storage

## The ephemeral nature of containers

Every container starts with a fresh filesystem built from its image. Any files you create, modify, or download inside the container exist only in a **writable layer** that is tied to that specific container instance. When the container stops, that layer is gone.

This matters in Kubernetes because pods are disposable. Two distinct things can happen:

- **Pod restart** -- When a container inside a pod crashes (or is killed by a liveness probe), Kubernetes restarts the container within the same pod. The writable layer is lost, but `emptyDir` volumes survive because they belong to the pod, not the container.
- **Pod deletion** -- When the pod itself is deleted (scaling down, node failure, rolling update), everything is gone -- the writable layer, `emptyDir` volumes, all of it. A brand-new pod is created with a clean slate.

For stateless apps like our FastAPI project, this is exactly what we want. The app holds no local data -- every request is independent, and pod identity does not matter. But if you were running a database, a file upload service, or anything that writes to disk, you would lose all data every time a pod is replaced.

!!! warning
    Never store important data in the container filesystem or in `emptyDir` volumes if it must survive pod deletion. Use PersistentVolumes instead.

## Volumes vs PersistentVolumes

Kubernetes has two layers of storage abstraction, and beginners often confuse them.

**Volumes** are defined directly in the pod spec. They share the pod's lifecycle -- when the pod is deleted, the volume is cleaned up. Volume types include `emptyDir`, `hostPath`, `configMap`, `secret`, and others. Use these for temporary scratch space, config injection, or sharing files between containers in the same pod.

**PersistentVolumes (PVs)** exist independently of any pod. They are cluster-level resources with their own lifecycle. A PV can outlive hundreds of pods -- data written by one pod is still there when a completely different pod mounts the same volume later. Use these when data must survive pod deletion.

The key mental model:

```
Volumes        = tied to the pod lifecycle (temporary)
PersistentVolumes = independent of any pod (durable)
```

## Volume types

### emptyDir

An `emptyDir` volume is created when a pod is assigned to a node and exists as long as the pod runs on that node. It starts empty. All containers in the pod can read and write the same files. When the pod is removed from the node for any reason, the data is deleted permanently.

Common uses:

- Scratch space for sorting or processing
- Sharing files between containers in a multi-container pod (e.g., a sidecar that tails logs written by the main container)
- Checkpoint data for crash recovery within the same pod

```yaml
spec:
  containers:
    - name: app
      volumeMounts:
        - name: scratch
          mountPath: /tmp/work
  volumes:
    - name: scratch
      emptyDir: {}
```

You can also request an in-memory `emptyDir` backed by a `tmpfs`:

```yaml
volumes:
  - name: cache
    emptyDir:
      medium: Memory
      sizeLimit: 128Mi
```

### hostPath

A `hostPath` volume mounts a file or directory from the host node's filesystem into the pod. The data persists across pod restarts and even pod deletions, because it lives on the node itself -- not inside the pod.

```yaml
volumes:
  - name: host-data
    hostPath:
      path: /data/my-app
      type: DirectoryOrCreate
```

!!! warning
    `hostPath` is useful for single-node development clusters like Docker Desktop, but it is **not portable** to multi-node clusters. If your pod moves to a different node, it will see a completely different (or empty) directory. Avoid `hostPath` in production.

### configMap and secret volumes

You can mount ConfigMaps and Secrets as files inside a container. Each key in the ConfigMap or Secret becomes a file, with the value as its content.

```yaml
volumes:
  - name: config-files
    configMap:
      name: fastapi-config
  - name: secret-files
    secret:
      secretName: fastapi-secrets
```

These are covered in detail on the [Configuration & Secrets](configuration-and-secrets.md) page. The key point here is that these are volume types -- they follow the same `volumes` + `volumeMounts` pattern as every other volume.

### projected volumes

A `projected` volume lets you combine multiple sources into a single mount point. This is useful when a container needs files from a ConfigMap, a Secret, and the Downward API all in one directory.

```yaml
volumes:
  - name: all-config
    projected:
      sources:
        - configMap:
            name: app-config
        - secret:
            name: app-secrets
        - downwardAPI:
            items:
              - path: "pod-name"
                fieldRef:
                  fieldPath: metadata.name
```

## PersistentVolume (PV)

A **PersistentVolume** is a piece of storage in the cluster that has been provisioned by an administrator or dynamically by a StorageClass. Think of it as a virtual disk that exists independently of any pod.

### PV lifecycle

A PersistentVolume moves through these phases:

| Phase       | Meaning                                                       |
|-------------|---------------------------------------------------------------|
| Available   | The PV exists and is not yet bound to any claim               |
| Bound       | The PV is bound to a PersistentVolumeClaim                    |
| Released    | The claim was deleted, but the PV has not been reclaimed yet  |
| Failed      | Automatic reclamation failed                                  |

### Reclaim policies

When a PVC is deleted, the reclaim policy determines what happens to the underlying PV:

- **Retain** -- The PV is kept with its data intact. An admin must manually clean up the volume and decide what to do with the data. This is the safest option for important data.
- **Delete** -- The PV and its underlying storage are deleted automatically. This is the default for dynamically provisioned volumes.
- **Recycle** -- (Deprecated) The volume is scrubbed with `rm -rf /thevolume/*` and made available again.

!!! tip
    For learning on Docker Desktop, `Delete` is fine. For anything resembling production, default to `Retain` and handle cleanup manually.

### Example: manually creating a PV

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-local-pv
spec:
  capacity:
    storage: 5Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  hostPath:
    path: /data/my-local-pv
```

In practice, you rarely create PVs by hand. Dynamic provisioning via StorageClasses is far more common.

## PersistentVolumeClaim (PVC)

A **PersistentVolumeClaim** is how a pod requests storage. You specify how much storage you need and what access mode you require, and Kubernetes finds (or creates) a matching PV.

### Access modes

| Mode            | Short name | Meaning                                       |
|-----------------|------------|-----------------------------------------------|
| ReadWriteOnce   | RWO        | Mounted as read-write by a single node        |
| ReadOnlyMany    | ROX        | Mounted as read-only by many nodes            |
| ReadWriteMany   | RWX        | Mounted as read-write by many nodes           |

!!! note
    On Docker Desktop, only `ReadWriteOnce` is supported by the default `hostpath` provisioner. `ReadWriteMany` requires a shared filesystem like NFS, which is not available out of the box.

### How binding works

When you create a PVC, the Kubernetes control plane looks for an existing PV that satisfies the claim's requirements (size, access mode, StorageClass). If a match is found, the PVC is bound to that PV. If dynamic provisioning is enabled and no existing PV matches, the StorageClass creates a new PV automatically.

A PVC is bound to exactly one PV, and that PV is exclusively reserved for that PVC. No other claim can use it.

## StorageClasses

A **StorageClass** defines how storage is dynamically provisioned. Instead of pre-creating PVs and hoping they match PVCs, the StorageClass tells Kubernetes: "when someone asks for storage, create it automatically using this provisioner with these parameters."

### Docker Desktop default

Docker Desktop ships with a default StorageClass called `hostpath`:

```bash
kubectl get storageclass
# NAME                 PROVISIONER          RECLAIMPOLICY   VOLUMEBINDINGMODE
# hostpath (default)   docker.io/hostpath   Delete          Immediate
```

Because it is marked as the **default**, any PVC that does not specify a StorageClass will automatically use it. The provisioner creates a `hostPath`-backed PV on the Docker Desktop VM's filesystem.

### How dynamic provisioning works

1. You create a PVC (no PV exists yet)
2. Kubernetes sees the PVC references a StorageClass (or the default)
3. The StorageClass provisioner creates a PV that matches the PVC's requirements
4. The PVC is bound to the newly created PV
5. Your pod mounts the PVC and reads/writes data

This is the standard workflow in most clusters. You almost never need to create PVs manually.

## The full chain

Here is how all the pieces connect, from the pod down to the actual disk:

```
+--------------------------------------------------+
|  Pod                                             |
|                                                  |
|  containers:                                     |
|    - name: my-app                                |
|      volumeMounts:                               |
|        - name: data                              |
|          mountPath: /app/data   <--- mount point |
|                                                  |
|  volumes:                                        |
|    - name: data                                  |
|      persistentVolumeClaim:                      |
|        claimName: data-pvc      <--- reference   |
+--------------------------------------------------+
          |
          | (pod references PVC by name)
          v
+--------------------------------------------------+
|  PersistentVolumeClaim (data-pvc)                |
|    requests: 1Gi                                 |
|    accessModes: [ReadWriteOnce]                  |
|    storageClassName: hostpath                    |
+--------------------------------------------------+
          |
          | (PVC binds to a matching PV)
          v
+--------------------------------------------------+
|  StorageClass (hostpath)                         |
|    provisioner: docker.io/hostpath               |
|    reclaimPolicy: Delete                         |
|                                                  |
|    (dynamically creates PV if none exists)       |
+--------------------------------------------------+
          |
          v
+--------------------------------------------------+
|  PersistentVolume (pvc-a3b4c5...)                |
|    capacity: 1Gi                                 |
|    hostPath: /var/lib/k8s-pvs/pvc-a3b4c5...     |
+--------------------------------------------------+
          |
          | (backed by actual storage)
          v
+--------------------------------------------------+
|  Actual disk on the Docker Desktop VM            |
+--------------------------------------------------+
```

## Walkthrough: persistent data that survives pod deletion

This walkthrough creates a PVC, mounts it in a pod, writes data, deletes the pod, recreates it, and verifies the data is still there.

### Step 1: Create the PVC

Save this as `pvc-demo.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: demo-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Mi
```

Apply it:

```bash
kubectl apply -f pvc-demo.yaml

# Check that it was created and is bound
kubectl get pvc demo-pvc
# NAME       STATUS   VOLUME            CAPACITY   ACCESS MODES   STORAGECLASS
# demo-pvc   Bound    pvc-abc123...     100Mi      RWO            hostpath
```

Because Docker Desktop has a default StorageClass, the PVC is immediately bound to a dynamically provisioned PV.

### Step 2: Create a pod that uses the PVC

Save this as `pod-demo.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: storage-demo
spec:
  containers:
    - name: busybox
      image: busybox
      command: ["sleep", "3600"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: demo-pvc
```

Apply it:

```bash
kubectl apply -f pod-demo.yaml
kubectl wait --for=condition=Ready pod/storage-demo --timeout=30s
```

### Step 3: Write data inside the pod

```bash
kubectl exec storage-demo -- sh -c 'echo "written at $(date)" > /data/proof.txt'
kubectl exec storage-demo -- cat /data/proof.txt
# written at Mon Jan 20 14:32:01 UTC 2025
```

### Step 4: Delete the pod

```bash
kubectl delete pod storage-demo
```

The pod is gone, but the PVC and PV still exist:

```bash
kubectl get pvc demo-pvc
# STATUS: Bound  (still there)
```

### Step 5: Recreate the pod and verify

Apply the same pod manifest again:

```bash
kubectl apply -f pod-demo.yaml
kubectl wait --for=condition=Ready pod/storage-demo --timeout=30s

kubectl exec storage-demo -- cat /data/proof.txt
# written at Mon Jan 20 14:32:01 UTC 2025
```

The data survived pod deletion. This is the core value of persistent storage.

### Cleanup

```bash
kubectl delete pod storage-demo
kubectl delete pvc demo-pvc
```

Deleting the PVC also deletes the underlying PV (because the default reclaim policy is `Delete`).

## StatefulSets and storage

A **Deployment** treats all pods as interchangeable. If a pod dies, a new one takes its place with a random name. This is fine for stateless apps, but databases need **stable identity** and **stable storage**.

A **StatefulSet** provides both:

- Pods get predictable names: `db-0`, `db-1`, `db-2` (not random suffixes)
- Each pod gets its own PVC via `volumeClaimTemplates`
- If `db-1` is deleted, the replacement `db-1` is reattached to the same PVC

### volumeClaimTemplates

Instead of manually creating PVCs, a StatefulSet defines a template. Kubernetes creates one PVC per pod automatically.

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: db
  replicas: 3
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: postgres
          image: postgres:16
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: pgdata
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
```

This creates three PVCs: `pgdata-db-0`, `pgdata-db-1`, `pgdata-db-2`. Each pod always mounts its own dedicated PVC. If `db-1` is deleted and recreated, it gets `pgdata-db-1` again -- not a random volume.

!!! info
    Deleting a StatefulSet does **not** delete the PVCs. This is intentional -- it prevents accidental data loss. You must delete PVCs manually if you want to reclaim the storage.

## When you need persistent storage

- **Databases** -- PostgreSQL, MySQL, MongoDB, Redis with persistence
- **File uploads** -- User-uploaded files that must be served later
- **Application state** -- Session stores, caches that must survive restarts
- **Message queues** -- Kafka, RabbitMQ with durable messages
- **ML models** -- Large model files that are expensive to re-download

## When you do not need it

- **Stateless API servers** -- Like this FastAPI project. Every request is independent, there is no local data to persist.
- **Apps with external storage** -- If your app writes to a cloud database or object store (S3, GCS), the pod itself is stateless.
- **Apps that rebuild state on startup** -- Caches that can be repopulated, derived data that can be recomputed.
- **CI/CD runners** -- Ephemeral by nature, each job starts clean.

!!! note
    Our FastAPI project is fully stateless. It stores no data on disk, reads configuration from ConfigMaps and environment variables, and can be replaced at any time without data loss. This is the ideal design for Kubernetes -- it makes scaling, rolling updates, and self-healing trivial.
