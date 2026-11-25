variable "cluster_name" {
  description = "Name of the Kind cluster."
  type        = string
}

variable "node_image" {
  description = "Kind node container image."
  type        = string
}

variable "worker_count" {
  description = "Number of worker nodes."
  type        = number
  default     = 2
}
