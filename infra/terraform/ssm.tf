resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project}/worker/database-url"
  type  = "SecureString"
  value = var.database_url
}

resource "aws_ssm_parameter" "voyage_api_key" {
  name  = "/${var.project}/worker/voyage-api-key"
  type  = "SecureString"
  value = var.voyage_api_key
}

resource "aws_ssm_parameter" "r2_access_key_id" {
  name  = "/${var.project}/worker/r2-access-key-id"
  type  = "SecureString"
  value = var.object_storage_access_key_id
}

resource "aws_ssm_parameter" "r2_secret_access_key" {
  name  = "/${var.project}/worker/r2-secret-access-key"
  type  = "SecureString"
  value = var.object_storage_secret_access_key
}
