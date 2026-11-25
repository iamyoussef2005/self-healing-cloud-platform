output "names" {
  description = "Names of the created namespaces."
  value       = sort(keys(kubernetes_namespace.this))
}
