variable "cluster_name" {
  description = "Name of the local Kind Kubernetes cluster."
  type        = string
  default     = "self-healing-cluster"
}

variable "node_image" {
  description = "Kind node container image."
  type        = string
  default     = "kindest/node:v1.31.2"
}

variable "worker_count" {
  description = "Number of worker nodes in the Kind cluster."
  type        = number
  default     = 2
}

variable "namespaces" {
  description = "Kubernetes namespaces to provision."
  type        = list(string)
  default     = ["app", "monitoring", "argocd", "self-healing"]
}

variable "kube_prometheus_stack_version" {
  description = "Helm chart version for kube-prometheus-stack."
  type        = string
  default     = "66.2.1"
}

variable "argocd_chart_version" {
  description = "Helm chart version for argo-cd."
  type        = string
  default     = "7.7.5"
}
