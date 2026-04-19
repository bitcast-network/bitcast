# Bitcast Subnet Infrastructure
#
# Shared Terraform for YouTube miner and validator on ECS Fargate.
# Add X miner/validator by duplicating the module blocks with X_ prefix.

terraform {
  required_version = ">= 1.0"

  backend "s3" {
    # bucket = "bitcast-terraform-state"
    # key    = "subnet/terraform.tfstate"
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
  type    = string
  default = "us-east-1"
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

variable "tags" {
  type    = map(string)
  default = {}
}

# ─── YouTube Miner ──────────────────────────────────────────────────────────

module "youtube_miner" {
  source = "./modules/bittensor-neuron"

  name            = "bitcast-youtube-miner"
  ecs_cluster_id  = var.ecs_cluster_id
  vpc_id          = var.vpc_id
  subnet_ids      = var.subnet_ids
  tags            = var.tags

  cpu             = 1024
  memory          = 2048

  ecr_image       = "bitcast-youtube-miner"
  entrypoint      = ["python", "neurons/miner.py"]
  command         = [
    "--wallet.name",     var.youtube_miner_bt_wallet_name,
    "--wallet.hotkey",   var.youtube_miner_bt_hotkey_name,
    "--netuid",          "93",
    "--subtensor.network", "finney",
    "--neuron.disable_auto_update",
  ]

  environment = {
    TOKEN_SOURCE       = "api"
    BITCAST_API_URL    = var.youtube_miner_bitcast_api_url
    BITCAST_API_KEY    = var.youtube_miner_bitcast_api_key
    BT_WALLET_HOTKEY   = var.youtube_miner_bt_wallet_hotkey
    BT_WALLET_NAME     = var.youtube_miner_bt_wallet_name
    BT_WALLET_HOTKEY_NAME = var.youtube_miner_bt_hotkey_name
  }

  secrets = {
    BITCAST_API_KEY  = var.youtube_miner_bitcast_api_key
    BT_WALLET_HOTKEY = var.youtube_miner_bt_wallet_hotkey
  }
}

# ─── YouTube Validator ──────────────────────────────────────────────────────

module "youtube_validator" {
  source = "./modules/bittensor-neuron"

  name            = "bitcast-youtube-validator"
  ecs_cluster_id  = var.ecs_cluster_id
  vpc_id          = var.vpc_id
  subnet_ids      = var.subnet_ids
  tags            = var.tags

  cpu             = 2048
  memory          = 4096

  ecr_image       = "bitcast-youtube-validator"
  entrypoint      = ["python", "neurons/validator.py"]
  command         = [
    "--wallet.name",     var.youtube_validator_bt_wallet_name,
    "--wallet.hotkey",   var.youtube_validator_bt_hotkey_name,
    "--netuid",          "93",
    "--subtensor.network", "finney",
    "--neuron.disable_auto_update",
  ]

  environment = {
    BT_WALLET_HOTKEY       = var.youtube_validator_bt_wallet_hotkey
    BT_WALLET_NAME         = var.youtube_validator_bt_wallet_name
    BT_WALLET_HOTKEY_NAME  = var.youtube_validator_bt_hotkey_name
  }

  secrets = {
    BT_WALLET_HOTKEY = var.youtube_validator_bt_wallet_hotkey
  }
}

# ─── YouTube Miner Secrets ──────────────────────────────────────────────────

variable "youtube_miner_bitcast_api_url" {
  type    = string
  default = "https://api.bitcast.so"
}

variable "youtube_miner_bitcast_api_key" {
  type      = string
  sensitive = true
}

variable "youtube_miner_bt_wallet_hotkey" {
  type      = string
  sensitive = true
}

variable "youtube_miner_bt_wallet_name" {
  type    = string
  default = "default"
}

variable "youtube_miner_bt_hotkey_name" {
  type    = string
  default = "default"
}

# ─── YouTube Validator Secrets ──────────────────────────────────────────────

variable "youtube_validator_bt_wallet_hotkey" {
  type      = string
  sensitive = true
}

variable "youtube_validator_bt_wallet_name" {
  type    = string
  default = "default"
}

variable "youtube_validator_bt_hotkey_name" {
  type    = string
  default = "default"
}

# ─── Outputs ────────────────────────────────────────────────────────────────

output "youtube_miner_ecr_url"   { value = module.youtube_miner.ecr_repository_url }
output "youtube_miner_service"   { value = module.youtube_miner.service_name }
output "youtube_miner_log_group" { value = module.youtube_miner.log_group_name }

output "youtube_validator_ecr_url"   { value = module.youtube_validator.ecr_repository_url }
output "youtube_validator_service"   { value = module.youtube_validator.service_name }
output "youtube_validator_log_group" { value = module.youtube_validator.log_group_name }
