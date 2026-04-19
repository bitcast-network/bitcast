terraform {
  required_version = ">= 1.0"

  backend "s3" {
    # bucket = "bitcast-terraform-state"
    # key    = "miner/terraform.tfstate"
    # region = "us-east-1"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ─── Variables ───────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "ecs_cluster_id" {
  description = "Existing ECS cluster ID from bitcast-infra"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID from bitcast-infra"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs from bitcast-infra"
  type        = list(string)
}

variable "bitcast_api_url" {
  description = "Bitcast API base URL"
  type        = string
  default     = "https://api.bitcast.so"
}

variable "token_source" {
  description = "Token source: local or api"
  type        = string
  default     = "api"
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

variable "tags" {
  description = "Additional tags"
  type        = map(string)
  default     = {}
}

locals {
  name     = "bitcast-miner"
  full_name = "${local.name}-${var.environment}"
}

# ─── ECR ────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "miner" {
  name                 = local.name
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "miner" {
  repository = aws_ecr_repository.miner.name

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

resource "aws_cloudwatch_log_group" "miner" {
  name              = "/ecs/${local.full_name}"
  retention_in_days = 30
  tags              = var.tags
}

# ─── Security Group ──────────────────────────────────────────────────────────
# Outbound only — the miner doesn't accept inbound connections.

resource "aws_security_group" "miner" {
  name_prefix = "${local.name}-task-"
  description = "Bitcast miner task — outbound only"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-task" })

  lifecycle {
    create_before_destroy = true
  }
}

# ─── IAM ────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "execution" {
  name = "${local.name}-execution"

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

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${local.name}-secrets"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = values(var.secrets)
    }]
  })
}

resource "aws_iam_role" "task" {
  name = "${local.name}-task"

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

variable "secrets" {
  description = "Map of env var name to Secrets Manager ARN"
  type        = map(string)
  default     = {}
}

# ─── Task Definition ────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "miner" {
  family                   = local.full_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = local.name
    image     = "${aws_ecr_repository.miner.repository_url}:latest"
    essential = true

    environment = [
      { name = "TOKEN_SOURCE", value = var.token_source },
      { name = "BITCAST_API_URL", value = var.bitcast_api_url },
    ]

    secrets = [for k, arn in var.secrets : { name = k, valueFrom = arn }]

    command = [
      "--wallet.name", "default",
      "--wallet.hotkey", "default",
      "--netuid", "93",
      "--subtensor.network", "finney",
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.miner.name
        "awslogs-region"        = var.aws_region
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

resource "aws_ecs_service" "miner" {
  name            = local.full_name
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.miner.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = [aws_security_group.miner.id]
    assign_public_ip = true
  }

  health_check_grace_period_seconds = 120

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 0

  tags = var.tags
}

# ─── Outputs ────────────────────────────────────────────────────────────────

output "ecr_repository_url" {
  value = aws_ecr_repository.miner.repository_url
}

output "ecs_service_name" {
  value = aws_ecs_service.miner.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.miner.name
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.miner.arn
}
