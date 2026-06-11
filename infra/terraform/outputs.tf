output "ingest_queue_url" {
  value = aws_sqs_queue.ingest.url
}

output "ingest_dlq_url" {
  value = aws_sqs_queue.ingest_dlq.url
}

output "worker_ecr_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "github_image_push_role_arn" {
  value = aws_iam_role.github_image_push.arn
}
