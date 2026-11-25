output "release_name" {
  description = "Helm release name for Argo CD."
  value       = helm_release.argocd.name
}
