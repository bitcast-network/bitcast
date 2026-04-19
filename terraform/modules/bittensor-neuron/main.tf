# Reusable module for any Bittensor neuron (miner or validator)

variable "name" {
  description = "Service name (e.g. bitcast-youtube-miner)"
  type        = string
}

variable "ecs_cluster_id" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "cpu" {
  description = "Fargate CPU units"
  type        = number
  default     = 1024
}

variable "memory" {
  description = "Fargate memory (MiB)"
  type        = number
  default     = 2048
}

variable "ecr_image" {
  description = "ECR repository name"
  type        = string
}

variable "entrypoint" {
  description = "Container entrypoint"
  type        = list(string)
}

variable "command" {
  description = "Container command (Bittensor args)"
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Non-sensitive env vars"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Sensitive env vars (stored in task def, visible in AWS console)"
  type        = map(string)
  default     = {}
}

locals {
  ecr_url    = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${var.ecr_image}"
  image      = "${local.ecr_url}:latest"
}

# ─── ECR ────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "this" {
  name                 = var.ecr_image
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ─── CloudWatch ──────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
  tags              = var.tags
}

# ─── Security Group ──────────────────────────────────────────────────────────

resource "aws_security_group" "this" {
  name_prefix = "${var.name}-task-"
  description = "Bittensor neuron task — outbound only"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-task" })

  lifecycle {
    create_before_destroy = true
  }
}

# ─── IAM ────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "execution" {
  name = "${var.name}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_base" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name = "${var.name}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = var.tags
}

# ─── Task Definition ────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = var.name
    image     = local.image
    essential = true

    entrypoint = var.entrypoint
    command    = var.command

    environment = [for k, v in merge(var.environment, var.secrets) : { name = k, value = v }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = var.tags
}

# ─── ECS Service ────────────────────────────────────────────────────────────

resource "aws_ecs_service" "this" {
  name            = var.name
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.this.id]
    assign_public_ip = true
  }

  health_check_grace_period_seconds = 120

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 0

  tags = var.tags
}

# ─── Data Sources ───────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ─── Outputs ────────────────────────────────────────────────────────────────

output "ecr_repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "service_name" {
  value = aws_ecs_service.this.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}

output "task_family" {
  value = var.name
}
