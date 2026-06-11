resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.project}-ingest-dlq-not-empty"
  alarm_description   = "Ingest jobs exhausted retries; inspect the DLQ"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.ingest_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
}

resource "aws_cloudwatch_metric_alarm" "oldest_message_age" {
  alarm_name          = "${var.project}-ingest-oldest-message-age"
  alarm_description   = "Jobs stuck: oldest queued message older than 2h"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = aws_sqs_queue.ingest.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 7200
  comparison_operator = "GreaterThanThreshold"
}
