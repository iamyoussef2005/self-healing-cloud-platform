variable "namespace" {
  description = "Kubernetes namespace for Argo CD."
  type        = string
  default     = "argocd"
}

variable "chart_version" {
  description = "Helm chart version for argo-cd."
  type        = string
}
