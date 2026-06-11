resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 1
}

resource "aws_appautoscaling_policy" "scale_up" {
  name               = "${var.project}-worker-scale-up"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type = "ExactCapacity"
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "scale_down" {
  name               = "${var.project}-worker-scale-down"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type = "ExactCapacity"
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_has_messages" {
  alarm_name          = "${var.project}-ingest-queue-has-messages"
  alarm_description   = "Visible ingest jobs waiting; scale the worker to 1"
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.ingest.name }
  statistic           = "Maximum"
  period              = 60
  alarm_actions       = [aws_appautoscaling_policy.scale_up.arn]
}

# Scale-down watches visible + in-flight so a long-running conversion
# (message invisible while being processed) keeps the worker alive.
resource "aws_cloudwatch_metric_alarm" "queue_empty" {
  alarm_name          = "${var.project}-ingest-queue-empty"
  alarm_description   = "No queued or in-flight ingest jobs for 10 min; scale to 0"
  evaluation_periods  = 10
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  alarm_actions       = [aws_appautoscaling_policy.scale_down.arn]

  metric_query {
    id          = "total"
    expression  = "visible + inflight"
    label       = "queued plus in-flight messages"
    return_data = true
  }

  metric_query {
    id = "visible"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesVisible"
      dimensions  = { QueueName = aws_sqs_queue.ingest.name }
      stat        = "Maximum"
      period      = 60
    }
  }

  metric_query {
    id = "inflight"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      dimensions  = { QueueName = aws_sqs_queue.ingest.name }
      stat        = "Maximum"
      period      = 60
    }
  }
}
