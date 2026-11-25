output "cluster_name" {
  description = "Provisioned Kind cluster name."
  value       = module.kind_cluster.cluster_name
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint."
  value       = module.kind_cluster.endpoint
}

output "kubeconfig_path" {
  description = "Path to the generated kubeconfig file."
  value       = module.kind_cluster.kubeconfig_path
}

output "namespaces" {
  description = "Created Kubernetes namespaces."
  value       = module.namespaces.names
}

output "monitoring_release" {
  description = "Helm release name for kube-prometheus-stack."
  value       = module.monitoring.release_name
}

output "argocd_release" {
  description = "Helm release name for Argo CD."
  value       = module.argocd.release_name
}
