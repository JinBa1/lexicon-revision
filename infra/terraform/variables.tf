variable "aws_region" {
  description = "AWS region (Neon Postgres lives in eu-west-2; keep the worker beside it)"
  type        = string
  default     = "eu-west-2"
}

variable "project" {
  description = "Resource name prefix"
  type        = string
  default     = "lexicon"
}

variable "worker_image_tag" {
  description = "Worker image tag deployed by the ECS task definition"
  type        = string
  default     = "latest"
}

variable "worker_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Fargate task memory (MiB)"
  type        = number
  default     = 8192
}

variable "github_repository" {
  description = "GitHub repo allowed to push images via OIDC (owner/name)"
  type        = string
}

variable "database_url" {
  description = "Neon Postgres URL for the worker"
  type        = string
  sensitive   = true
}

variable "voyage_api_key" {
  description = "Voyage embeddings API key"
  type        = string
  sensitive   = true
}

variable "object_storage_bucket" {
  description = "R2 bucket name"
  type        = string
}

variable "object_storage_endpoint_url" {
  description = "R2 S3-compatible endpoint URL"
  type        = string
}

variable "object_storage_access_key_id" {
  description = "R2 access key id"
  type        = string
  sensitive   = true
}

variable "object_storage_secret_access_key" {
  description = "R2 secret access key"
  type        = string
  sensitive   = true
}
