resource "aws_iam_user" "api_producer" {
  name = "${var.project}-api-producer"
}

resource "aws_iam_user_policy" "api_producer_send" {
  name = "sqs-send"
  user = aws_iam_user.api_producer.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = aws_sqs_queue.ingest.arn
    }]
  })
}

resource "aws_iam_access_key" "api_producer" {
  user = aws_iam_user.api_producer.name
}
