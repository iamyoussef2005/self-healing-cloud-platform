module "kind_cluster" {
  source = "./modules/kind-cluster"

  cluster_name = var.cluster_name
  node_image   = var.node_image
  worker_count = var.worker_count
}

module "namespaces" {
  source = "./modules/namespaces"

  namespaces = var.namespaces

  depends_on = [module.kind_cluster]
}

module "monitoring" {
  source = "./modules/monitoring"

  namespace     = "monitoring"
  chart_version = var.kube_prometheus_stack_version

  depends_on = [module.namespaces]
}

module "argocd" {
  source = "./modules/argocd"

  namespace     = "argocd"
  chart_version = var.argocd_chart_version

  depends_on = [module.namespaces]
}
