resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${var.project}-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days to inspect failures
}

resource "aws_sqs_queue" "ingest" {
  name = "${var.project}-ingest"
  # MinerU CPU conversion is slow and the worker does not heartbeat
  # extend_visibility; one job must fit comfortably inside this window.
  visibility_timeout_seconds = 2700 # 45 min
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}
