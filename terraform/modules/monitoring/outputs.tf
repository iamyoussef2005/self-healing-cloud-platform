output "release_name" {
  description = "Helm release name for kube-prometheus-stack."
  value       = helm_release.kube_prometheus_stack.name
}
