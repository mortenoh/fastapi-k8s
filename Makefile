.DEFAULT_GOAL := help
.PHONY: help dev run lint docker-build docker-run deploy status logs scale undeploy clean test metrics-server hpa hpa-status hpa-delete restart rollout-status docs docs-serve docs-build redis-deploy redis-status redis-logs redis-undeploy redis-clean test-redis

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev: ## Run local dev server with hot-reload
	uv run fastapi dev main.py

run: ## Run with uvicorn directly
	uv run main.py

lint: ## Run ruff linter and formatter check
	uv run ruff check .
	uv run ruff format --check .

docker-build: ## Build Docker image
	docker build -t fastapi-k8s:latest .

docker-run: ## Run Docker container
	docker run --rm -p 8000:8000 fastapi-k8s:latest

deploy: ## Deploy to Kubernetes
	kubectl apply -f k8s.yaml

status: ## Check pod and service status
	kubectl get pods,svc -l app=fastapi-k8s

logs: ## View pod logs
	kubectl logs -l app=fastapi-k8s

scale: ## Scale deployment (usage: make scale N=3)
	kubectl scale deployment fastapi-k8s --replicas=$(N)

undeploy: ## Remove from Kubernetes
	kubectl delete -f k8s.yaml

clean: undeploy ## Remove K8s resources and Docker image
	docker rmi fastapi-k8s:latest

metrics-server: ## Install metrics-server for HPA and kubectl top
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
	kubectl patch deployment metrics-server -n kube-system --type='json' \
	  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
	kubectl wait --for=condition=available deployment/metrics-server -n kube-system --timeout=120s

hpa: ## Apply HPA for autoscaling
	kubectl apply -f k8s/hpa.yaml

hpa-status: ## Check HPA status
	kubectl get hpa -l app=fastapi-k8s

hpa-delete: ## Delete HPA
	kubectl delete -f k8s/hpa.yaml

restart: ## Trigger rolling restart of deployment
	kubectl rollout restart deployment/fastapi-k8s

rollout-status: ## Watch rollout progress
	kubectl rollout status deployment/fastapi-k8s

docs-serve: ## Serve documentation locally
	uv run mkdocs serve

docs-build: ## Build documentation site
	uv run mkdocs build

docs: docs-serve ## Alias for docs-serve

redis-deploy: ## Deploy Redis (Secret + PVC + Deployment + Service)
	kubectl apply -f k8s/redis-secret.yaml -f k8s/redis.yaml

redis-status: ## Check Redis pod, service, and PVC status
	kubectl get pods,svc,pvc -l app=redis

redis-logs: ## View Redis pod logs
	kubectl logs -l app=redis

redis-undeploy: ## Remove Redis Deployment and Service (keeps PVC and Secret)
	kubectl delete -f k8s/redis.yaml

redis-clean: ## Full Redis cleanup (Deployment + PVC + Secret)
	-kubectl delete -f k8s/redis.yaml
	-kubectl delete -f k8s/redis-secret.yaml
	-kubectl delete pvc redis-pvc

test-redis: ## Test Redis endpoints (visits, kv store)
	@echo "=== Testing GET /visits (first) ==="
	curl -sf http://localhost/visits
	@echo ""
	@echo "=== Testing GET /visits (second) ==="
	curl -sf http://localhost/visits
	@echo ""
	@echo "=== Testing POST /kv/greeting ==="
	curl -sf -X POST -H "Content-Type: application/json" -d '{"value":"hello from k8s"}' http://localhost/kv/greeting
	@echo ""
	@echo "=== Testing GET /kv/greeting ==="
	curl -sf http://localhost/kv/greeting
	@echo ""
	@echo "=== Testing GET /kv/missing (expect 404) ==="
	curl -s -o /dev/null -w "%{http_code}" http://localhost/kv/missing | grep -q 404 && echo '{"status":"got expected 404"}'
	@echo ""
	@echo "=== All Redis tests passed ==="

test: ## Build, deploy, wait for pods, and test all endpoints
	@echo "=== Building Docker image ==="
	docker build -t fastapi-k8s:latest .
	@echo ""
	@echo "=== Deploying to Kubernetes ==="
	kubectl apply -f k8s.yaml
	@echo ""
	@echo "=== Waiting for rollout ==="
	kubectl rollout status deployment/fastapi-k8s --timeout=60s
	@echo ""
	@echo "=== Pod status ==="
	kubectl get pods -l app=fastapi-k8s
	@echo ""
	@echo "=== Testing GET / ==="
	curl -sf http://localhost/
	@echo ""
	@echo "=== Testing GET /health ==="
	curl -sf http://localhost/health
	@echo ""
	@echo "=== Testing GET /ready ==="
	curl -sf http://localhost/ready
	@echo ""
	@echo "=== Testing GET /info ==="
	curl -sf http://localhost/info
	@echo ""
	@echo "=== Testing GET /config ==="
	curl -sf http://localhost/config
	@echo ""
	@echo "=== Testing GET /version ==="
	curl -sf http://localhost/version
	@echo ""
	@echo "=== Testing GET /stress?seconds=1 ==="
	curl -sf "http://localhost/stress?seconds=1"
	@echo ""
	@echo "=== Testing POST /ready/disable ==="
	curl -sf -X POST http://localhost/ready/disable
	@echo ""
	@echo "=== Testing POST /ready/enable ==="
	curl -sf -X POST http://localhost/ready/enable
	@echo ""
	@echo "=== All tests passed ==="
