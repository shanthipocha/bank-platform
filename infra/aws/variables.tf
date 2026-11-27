variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "cluster_name" {
  type    = string
  default = "bank-eks"
}

# Check supported versions: aws eks describe-cluster-versions --region ap-south-1
variable "kubernetes_version" {
  type    = string
  default = "1.34"
}

variable "node_instance_type" {
  type    = string
  default = "m7i-flex.large"
}

variable "node_count" {
  type    = number
  default = 2
}

# IAM principal used in the AWS console (root or a user). Gives read-only view in the EKS console.
variable "console_principal_arn" {
  type    = string
  default = ""
}
