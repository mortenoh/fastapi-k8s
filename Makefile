.DEFAULT_GOAL := help
.PHONY: help dev run docker-build docker-run deploy status logs scale undeploy clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev: ## Run local dev server with hot-reload
	uv run fastapi dev main.py

run: ## Run with uvicorn directly
	uv run main.py

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
