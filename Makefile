TF_DIR := terraform
CLUSTER_NAME := self-healing-cluster

.PHONY: infra-up infra-down status gitops-apply

infra-up:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply -auto-approve

infra-down:
	terraform -chdir=$(TF_DIR) destroy -auto-approve

gitops-apply:
	kubectl apply -f gitops/app-project.yaml --context kind-$(CLUSTER_NAME)
	kubectl apply -f gitops/demo-app-application.yaml --context kind-$(CLUSTER_NAME)

status:
	@echo "=== Cluster Nodes ==="
	kubectl get nodes --context kind-$(CLUSTER_NAME)
	@echo "\n=== Namespaces ==="
	kubectl get namespaces --context kind-$(CLUSTER_NAME)
	@echo "\n=== Pods (All Namespaces) ==="
	kubectl get pods -A --context kind-$(CLUSTER_NAME)
	@echo "\n=== Helm Releases ==="
	helm list -A --kube-context kind-$(CLUSTER_NAME)
