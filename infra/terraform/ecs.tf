data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "worker" {
  name        = "${var.project}-worker"
  description = "Egress-only ingestion worker"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project}-worker"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "main" {
  name = var.project
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.worker_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
    essential = true
    # Non-secret values mirror the Fly API deployment (fly.toml [env]);
    # EMBEDDING_MODEL_ID / EMBEDDING_DIMENSION must match the API or
    # worker-indexed collections will not match query-time search.
    environment = [
      { name = "APP_ENV", value = "prod" },
      { name = "INGEST_QUEUE_PROVIDER", value = "sqs" },
      { name = "INGEST_QUEUE_URL", value = aws_sqs_queue.ingest.url },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "INGEST_MINERU_BACKEND", value = "pipeline" },
      { name = "EMBEDDING_PROVIDER", value = "voyage" },
      { name = "EMBEDDING_MODEL", value = "voyage-4-lite" },
      { name = "EMBEDDING_MODEL_ID", value = "voyage-4-lite" },
      { name = "EMBEDDING_DIMENSION", value = "1024" },
      { name = "EMBEDDING_OUTPUT_DIMENSION", value = "1024" },
      { name = "OBJECT_STORAGE_PROVIDER", value = "s3" },
      { name = "OBJECT_STORAGE_BUCKET", value = var.object_storage_bucket },
      { name = "OBJECT_STORAGE_ENDPOINT_URL", value = var.object_storage_endpoint_url },
      { name = "OBJECT_STORAGE_REGION", value = "auto" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_ssm_parameter.database_url.arn },
      { name = "VOYAGE_API_KEY", valueFrom = aws_ssm_parameter.voyage_api_key.arn },
      { name = "OBJECT_STORAGE_ACCESS_KEY_ID", valueFrom = aws_ssm_parameter.r2_access_key_id.arn },
      { name = "OBJECT_STORAGE_SECRET_ACCESS_KEY", valueFrom = aws_ssm_parameter.r2_secret_access_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.worker.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = true # default VPC public subnets; egress to Neon/R2/Voyage
  }

  lifecycle {
    ignore_changes = [desired_count] # autoscaling owns it
  }
}
