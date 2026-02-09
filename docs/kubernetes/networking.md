# Networking Deep Dive

Networking is one of the most important -- and initially confusing -- parts of Kubernetes.
This page walks through the networking model from first principles, then covers every
Service type, Ingress, Network Policies, and CNI plugins, all grounded in our
**fastapi-k8s** project running on Docker Desktop.

---

## The Kubernetes Networking Model

Kubernetes imposes three fundamental rules on any conforming cluster implementation:

1. **Every pod gets its own IP address.** You never need to create links between pods or
   map container ports to host ports yourself.
2. **All pods can communicate with all other pods without NAT.** A pod on Node A can reach
   a pod on Node B using the pod's IP directly -- no network address translation in between.
3. **Agents on a node (e.g., kubelet) can communicate with all pods on that node.**

The result is a **flat network** -- from the perspective of any container, the network looks
like a single large ethernet segment. Every pod believes it lives on a "normal" network
where it can reach any other pod by IP.

!!! info "Why a flat network matters"
    Traditional Docker networking requires explicit port mappings (`-p 8080:80`) and link
    aliases. Kubernetes eliminates that complexity. Your FastAPI container listens on port
    8000, and every other pod in the cluster can reach it on `<pod-ip>:8000` without any
    extra configuration.

### Pod IPs in our project

When our `fastapi-k8s` Deployment creates pods, each one receives a unique cluster-internal
IP. You can see this yourself:

```bash
kubectl get pods -l app=fastapi-k8s -o wide
```

```
NAME                          READY   STATUS    IP           NODE
fastapi-k8s-7d4b8c6f5-abc12  1/1     Running   10.1.0.47    docker-desktop
fastapi-k8s-7d4b8c6f5-def34  1/1     Running   10.1.0.48    docker-desktop
fastapi-k8s-7d4b8c6f5-ghi56  1/1     Running   10.1.0.49    docker-desktop
```

Our `/info` endpoint returns this pod IP (via the Downward API `status.podIP` env var),
so you can verify it:

```bash
curl -s http://localhost/info | python3 -m json.tool
```

```json
{
    "pod_name": "fastapi-k8s-7d4b8c6f5-abc12",
    "pod_ip": "10.1.0.47",
    "node_name": "docker-desktop",
    "namespace": "default",
    ...
}
```

These IPs are **ephemeral** -- when a pod is deleted and recreated, it gets a new IP.
That is exactly why we need Services.

---

## DNS in Kubernetes

Kubernetes runs an internal DNS server (usually CoreDNS) that automatically creates DNS
records for Services. This means pods can reach Services **by name** instead of by IP.

### The fully qualified domain name (FQDN)

Every Service gets a DNS entry in the form:

```
<service-name>.<namespace>.svc.cluster.local
```

For our project, the Service is named `fastapi-k8s` in the `default` namespace, so the
full DNS name is:

```
fastapi-k8s.default.svc.cluster.local
```

### Short names work too

Pods have a `resolv.conf` that includes search domains, so you can use shorter forms:

| Form | Works from |
|------|-----------|
| `fastapi-k8s` | Same namespace |
| `fastapi-k8s.default` | Any namespace |
| `fastapi-k8s.default.svc` | Any namespace |
| `fastapi-k8s.default.svc.cluster.local` | Anywhere in the cluster |

!!! tip "Practical rule"
    If you are calling a Service in the **same namespace**, just use the Service name
    directly: `http://fastapi-k8s:80`. If you are calling across namespaces, use at least
    `<service-name>.<namespace>`.

### Verifying DNS resolution

You can spin up a debug pod to test DNS:

```bash
kubectl run dns-test --rm -it --image=busybox --restart=Never -- sh
```

Inside the pod:

```bash
nslookup fastapi-k8s
```

```
Server:    10.96.0.10
Address 1: 10.96.0.10 kube-dns.kube-system.svc.cluster.local

Name:      fastapi-k8s
Address 1: 10.96.0.100 fastapi-k8s.default.svc.cluster.local
```

```bash
nslookup fastapi-k8s.default.svc.cluster.local
```

```
Server:    10.96.0.10
Address 1: 10.96.0.10 kube-dns.kube-system.svc.cluster.local

Name:      fastapi-k8s.default.svc.cluster.local
Address 1: 10.96.0.100 fastapi-k8s.default.svc.cluster.local
```

The address `10.96.0.100` is the **ClusterIP** of the Service -- a virtual IP that
kube-proxy routes to the backing pods.

You can also call the API from inside the cluster:

```bash
wget -qO- http://fastapi-k8s:80/
```

```json
{"message": "Hello from fastapi-k8s!", "server": "fastapi-k8s-7d4b8c6f5-abc12"}
```

---

## Service Types in Depth

A Service is an abstraction that defines a logical set of pods and a policy for accessing
them. The set of pods is determined by a **label selector**. Our Service selects pods with
`app: fastapi-k8s`.

Each Service type builds on the previous one:

```
ClusterIP  -->  NodePort  -->  LoadBalancer
   ^                              |
   |______________________________|
        (each includes the one before)
```

### ClusterIP (default)

ClusterIP is the default Service type. It assigns a cluster-internal virtual IP that is
only reachable from within the cluster.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
spec:
  type: ClusterIP          # default, can be omitted
  selector:
    app: fastapi-k8s
  ports:
    - port: 80
      targetPort: 8000
```

**How kube-proxy implements it:**

kube-proxy runs on every node and watches the Kubernetes API for Service and Endpoints
changes. In the default `iptables` mode, it creates iptables rules that intercept traffic
destined for the ClusterIP and redirect it to one of the backing pod IPs using
probabilistic rules (roughly round-robin).

You can inspect these rules on the node:

```bash
# From a node (not typically accessible on Docker Desktop)
iptables -t nat -L KUBE-SERVICES -n | grep fastapi
```

The flow looks like this:

```
Pod A sends packet to 10.96.0.100:80 (ClusterIP)
  --> iptables DNAT rule on the node
  --> Packet destination rewritten to 10.1.0.47:8000 (a pod IP)
  --> Response returns directly
```

!!! note "kube-proxy modes"
    kube-proxy supports three modes: `userspace` (legacy), `iptables` (default), and
    `ipvs` (higher performance for clusters with many Services). Docker Desktop uses
    `iptables` mode.

**When to use ClusterIP:**

- Internal services that should not be exposed outside the cluster
- Databases, caches, message queues, internal microservice APIs
- Any service that another in-cluster service calls

### NodePort

NodePort builds on ClusterIP. It does everything ClusterIP does **plus** opens a static
port on every node in the cluster.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
spec:
  type: NodePort
  selector:
    app: fastapi-k8s
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30080      # optional, auto-assigned from 30000-32767 if omitted
```

With this config, the service is reachable at:

- **Inside the cluster:** `fastapi-k8s:80` (ClusterIP still works)
- **From outside:** `<any-node-ip>:30080`

On Docker Desktop (single node), that means `localhost:30080`.

```bash
curl http://localhost:30080/
```

**Port range:** NodePort values must be in the range **30000-32767**. This range is
configurable via the API server's `--service-node-port-range` flag, but the default range
is used in almost all clusters.

!!! warning "NodePort limitations"
    - Only one Service can use a given NodePort number
    - The high port numbers (30000+) are not user-friendly for end users
    - No built-in load balancing across nodes (you need an external LB or DNS round-robin)
    - Not recommended for production external access

**When to use NodePort:**

- Development and testing when you need quick external access
- When you have your own external load balancer that distributes to node IPs
- Simple setups where high port numbers are acceptable

### LoadBalancer

LoadBalancer builds on NodePort. It does everything NodePort does **plus** provisions an
external load balancer. This is the Service type we use in our project:

```yaml
# From our k8s.yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s
  labels:
    app: fastapi-k8s
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 8000
  selector:
    app: fastapi-k8s
```

**On cloud providers** (AWS, GCP, Azure), creating a LoadBalancer Service triggers the
cloud controller manager to provision an actual load balancer resource:

- **AWS:** An Elastic Load Balancer (ELB or NLB)
- **GCP:** A Google Cloud Load Balancer
- **Azure:** An Azure Load Balancer

The external IP or hostname is populated in the Service's `status.loadBalancer.ingress`
field. You can see it with:

```bash
kubectl get svc fastapi-k8s
```

```
NAME          TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
fastapi-k8s   LoadBalancer   10.96.0.100    localhost      80:31234/TCP   5m
```

**On Docker Desktop**, there is no cloud controller to provision a real load balancer.
Instead, Docker Desktop has built-in support that maps the Service's port directly to
`localhost`. This is why `curl http://localhost/` works:

```bash
curl http://localhost/
```

```json
{"message": "Hello from fastapi-k8s!", "server": "fastapi-k8s-7d4b8c6f5-abc12"}
```

!!! info "EXTERNAL-IP shows `localhost` on Docker Desktop"
    On cloud providers, the EXTERNAL-IP field shows the provisioned IP or hostname
    (e.g., `a1b2c3-1234567890.us-east-1.elb.amazonaws.com`). On Docker Desktop, it
    shows `localhost`. On bare-metal clusters without a cloud controller, it stays
    `<pending>` forever unless you install something like MetalLB.

**When to use LoadBalancer:**

- Production workloads on cloud providers that need external access
- When you want a dedicated IP/hostname for a single Service
- Simple external exposure without path-based routing needs

### ExternalName

ExternalName is different from the other types. It does not proxy traffic at all -- it
creates a **CNAME DNS record** that maps the Service name to an external DNS name.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: external-api
  namespace: default
spec:
  type: ExternalName
  externalName: api.example.com
```

Now any pod in the `default` namespace can call `http://external-api/` and DNS will
resolve it to `api.example.com`.

**When to use ExternalName:**

- Pointing to external services (third-party APIs, databases outside the cluster)
- Service migration -- redirect traffic to an external service while you migrate it into
  the cluster, then switch the Service type later
- Abstracting external dependencies behind a stable in-cluster name

!!! warning "ExternalName caveats"
    - No proxying or port remapping -- the port in the URL must match what the external
      service expects
    - HTTPS may fail if the external service's TLS certificate does not match the Service
      name you used
    - Only works with DNS, not with IP addresses (use Endpoints for that)

### Headless Services (clusterIP: None)

A headless Service is a ClusterIP Service with `clusterIP` explicitly set to `None`. It
does not get a virtual IP and kube-proxy does not handle it. Instead, DNS returns the
**individual pod IPs** directly.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: fastapi-k8s-headless
spec:
  clusterIP: None
  selector:
    app: fastapi-k8s
  ports:
    - port: 8000
      targetPort: 8000
```

A DNS lookup for `fastapi-k8s-headless` returns all pod IPs:

```bash
nslookup fastapi-k8s-headless
```

```
Name:      fastapi-k8s-headless.default.svc.cluster.local
Address 1: 10.1.0.47 fastapi-k8s-7d4b8c6f5-abc12
Address 2: 10.1.0.48 fastapi-k8s-7d4b8c6f5-def34
Address 3: 10.1.0.49 fastapi-k8s-7d4b8c6f5-ghi56
```

**When to use headless Services:**

- **StatefulSets:** Each pod in a StatefulSet gets a stable DNS name like
  `pod-0.my-headless-svc.default.svc.cluster.local`. This is essential for databases
  (e.g., each PostgreSQL replica has a unique, stable identity).
- **Client-side load balancing:** When your application wants to know all backend IPs
  and do its own load balancing or connection management.
- **Service discovery:** When you need to enumerate all pods behind a Service.

---

## Ingress and Ingress Controllers

### What is Ingress?

An Ingress is a Kubernetes resource that manages **external HTTP/HTTPS access** to
Services in the cluster. Unlike LoadBalancer Services (which give each Service its own
external IP), an Ingress lets you route traffic to **multiple Services behind a single
IP** based on the request's hostname or URL path.

### How Ingress differs from Services

| Feature | LoadBalancer Service | Ingress |
|---------|---------------------|---------|
| External IPs needed | One per Service | One for many Services |
| Layer | L4 (TCP/UDP) | L7 (HTTP/HTTPS) |
| Path-based routing | No | Yes |
| Host-based routing | No | Yes |
| TLS termination | No (needs app-level TLS) | Yes (via Secrets) |
| Cost (cloud) | One LB per Service ($$$) | One LB for all ($$) |

### When to use Ingress

- You have **multiple Services** that need external access and you want them behind a
  single IP/domain
- You need **path-based routing** (e.g., `/api` goes to one Service, `/web` goes to another)
- You need **TLS termination** at the edge rather than in each application
- You want to **reduce costs** on cloud providers by not provisioning one load balancer per
  Service

### Ingress Controllers

An Ingress resource on its own does nothing. You need an **Ingress Controller** -- a pod
that watches Ingress resources and configures a reverse proxy accordingly. Popular choices:

| Controller | Backed by | Notes |
|-----------|-----------|-------|
| **NGINX Ingress Controller** | NGINX | Most popular, community and F5 versions |
| **Traefik** | Traefik | Auto-discovery, built-in dashboard |
| **HAProxy Ingress** | HAProxy | High performance |
| **Contour** | Envoy | CNCF project |
| **Ambassador / Emissary** | Envoy | API gateway focus |

### NGINX Ingress Controller example

Install the NGINX Ingress Controller on Docker Desktop:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
```

Wait for it to be ready:

```bash
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

Now create an Ingress for our FastAPI app:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: fastapi.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fastapi-k8s
                port:
                  number: 80
```

Add `fastapi.local` to your `/etc/hosts`:

```bash
echo "127.0.0.1 fastapi.local" | sudo tee -a /etc/hosts
```

Now you can reach the app via the Ingress:

```bash
curl http://fastapi.local/
```

!!! tip "Ingress vs LoadBalancer for our project"
    For this single-service learning project, a LoadBalancer Service is simpler and
    perfectly adequate. Ingress becomes valuable when you have multiple services to
    expose -- for example, a frontend, an API, and an admin panel all behind one domain.

---

## Network Policies

### Default behavior: allow all

By default, Kubernetes allows **all traffic** between all pods in all namespaces. Any pod
can talk to any other pod. This is simple but not secure for production.

### What Network Policies do

A NetworkPolicy is a Kubernetes resource that controls traffic flow at the pod level. It
acts like a firewall for pod-to-pod communication. Network Policies use **label selectors**
to define which pods the rules apply to and which pods are allowed or denied as traffic
sources/destinations.

!!! warning "CNI support required"
    Network Policies only work if your cluster's CNI plugin supports them. Calico and
    Cilium support them fully. The default Docker Desktop networking has limited or no
    support for Network Policies. They are documented here because they are essential
    knowledge for production Kubernetes.

### Example: deny all ingress to our pods

This policy blocks **all incoming traffic** to pods labeled `app: fastapi-k8s`, then you
add explicit rules to allow only what you want:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-to-fastapi
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: fastapi-k8s
  policyTypes:
    - Ingress
  ingress: []               # empty = deny all ingress
```

### Example: allow traffic only from specific pods

Now allow traffic to our FastAPI pods only from pods labeled `role: frontend`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-fastapi
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: fastapi-k8s
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8000
```

This policy says: "For pods labeled `app: fastapi-k8s`, allow incoming TCP traffic on
port 8000 only from pods labeled `role: frontend` in the same namespace. Deny everything
else."

### Example: restrict egress

You can also control outbound traffic. This policy allows our pods to talk only to
DNS (port 53) and to other pods in the same namespace:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-fastapi-egress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: fastapi-k8s
  policyTypes:
    - Egress
  egress:
    - to:                     # allow DNS
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:                     # allow same-namespace pods
        - podSelector: {}
```

---

## Port Mapping Explained

The three port fields in Service and Deployment specs are a common source of confusion.
Here is exactly how they work in our project.

### The three port fields

| Field | Where it appears | What it means |
|-------|-----------------|---------------|
| `port` | Service spec | The port the **Service** listens on |
| `targetPort` | Service spec | The port to forward to on the **Pod** |
| `containerPort` | Pod/Deployment spec | The port the **container** listens on |

### Our project's configuration

From `k8s.yaml` -- the Service:

```yaml
spec:
  type: LoadBalancer
  ports:
    - port: 80              # Service listens on port 80
      targetPort: 8000      # forwards to pod port 8000
  selector:
    app: fastapi-k8s
```

From `k8s.yaml` -- the Deployment:

```yaml
containers:
  - name: fastapi-k8s
    image: fastapi-k8s:latest
    ports:
      - containerPort: 8000   # uvicorn listens on port 8000
```

### The full traffic flow

```
                    Kubernetes cluster
                    ==================

 curl localhost:80
       |
       v
 +-------------+         +------------------+         +-------------------+
 |   Service   |         |       Pod        |         |    Container      |
 |  port: 80   | ------> | targetPort: 8000 | ------> | containerPort:    |
 |             |         |                  |         | 8000 (uvicorn)    |
 +-------------+         +------------------+         +-------------------+
   10.96.0.100:80           10.1.0.47:8000              0.0.0.0:8000
```

Step by step:

1. **You run** `curl http://localhost:80/` -- on Docker Desktop, the LoadBalancer maps
   `localhost:80` to the Service's port 80.
2. **The Service** receives the request on port 80. It looks up the Endpoints (pods
   matching `app: fastapi-k8s` that pass the readiness probe) and picks one.
3. **kube-proxy** rewrites the destination from the Service's ClusterIP:80 to the
   selected pod's IP:8000 (the `targetPort`).
4. **The pod** receives the request on port 8000, where uvicorn is listening.
5. **FastAPI** processes the request and returns the response.

!!! note "containerPort is documentation only"
    The `containerPort` field in the pod spec does **not** enforce anything. Even if you
    omit it, traffic to port 8000 on the pod will still reach the container. It exists
    for documentation and for tools that inspect the spec. However, `targetPort` on the
    Service is what actually controls where traffic is forwarded -- and it **must** match
    the port your application listens on.

### Named ports

You can use named ports to decouple the Service from the specific port number:

```yaml
# In the Deployment
containers:
  - name: fastapi-k8s
    ports:
      - containerPort: 8000
        name: http            # give the port a name

# In the Service
spec:
  ports:
    - port: 80
      targetPort: http        # reference by name instead of number
```

This is useful when you want to change the application's port without updating the
Service definition.

---

## CNI Plugins

The networking model described above is an abstraction. The actual implementation is
provided by a **CNI (Container Network Interface) plugin**. The CNI plugin is responsible
for:

- Assigning IP addresses to pods
- Setting up network routes so pods on different nodes can communicate
- (Optionally) enforcing Network Policies

### Common CNI plugins

| Plugin | Key features |
|--------|-------------|
| **Calico** | Most popular, supports Network Policies, BGP routing, works on bare-metal and cloud |
| **Flannel** | Simple overlay network (VXLAN), no Network Policy support, good for getting started |
| **Cilium** | eBPF-based, advanced Network Policies, observability, identity-aware security |
| **Weave Net** | Mesh overlay, encrypted traffic by default, simple setup |
| **AWS VPC CNI** | AWS-native, pods get real VPC IPs, tight integration with security groups |
| **Azure CNI** | Azure-native, pods get Azure VNet IPs |

### Docker Desktop's networking

Docker Desktop uses its own built-in networking implementation rather than a traditional
CNI plugin. Since Docker Desktop runs a single-node cluster inside a lightweight VM, the
networking is simpler:

- All pods run on a single node, so cross-node networking is not needed
- The VM handles port forwarding from `localhost` to the cluster
- LoadBalancer Services automatically get `localhost` as their external IP
- Network Policy support is limited

!!! info "Production clusters use real CNI plugins"
    When you move beyond Docker Desktop to a production cluster (EKS, GKE, AKS, or
    self-managed), you will choose and install a CNI plugin. For most use cases, Calico
    or Cilium are strong defaults.

---

## Summary

| Concept | Key takeaway |
|---------|-------------|
| Flat network | Every pod gets an IP; pods talk directly without NAT |
| DNS | Services are reachable by name via CoreDNS |
| ClusterIP | Internal-only virtual IP, default Service type |
| NodePort | Opens a high port (30000-32767) on every node |
| LoadBalancer | Provisions an external LB (or maps to localhost on Docker Desktop) |
| ExternalName | CNAME alias to an external DNS name |
| Headless | Returns pod IPs directly, for StatefulSets and service discovery |
| Ingress | L7 routing (host/path) for multiple Services behind one IP |
| Network Policies | Firewall rules for pod-to-pod traffic |
| CNI plugins | The implementation layer that makes the networking model real |

For our **fastapi-k8s** project, the LoadBalancer Service maps `localhost:80` to our
pods' port 8000, and Kubernetes DNS lets any in-cluster pod reach the API at
`http://fastapi-k8s:80/`. That is Kubernetes networking doing its job.
