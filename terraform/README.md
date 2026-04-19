# Bitcast Miner — ECS Fargate Infrastructure

Runs the Bitcast miner on AWS ECS Fargate with auto-healing.

This is optional infrastructure — the miner works fine without Docker/ECS
using the standard `python neurons/miner.py` flow.

## Prerequisites

- Terraform >= 1.0
- AWS CLI configured
- Docker (for building images)
- Access to the existing Bitcast ECS cluster (from bitcast-infra)

## Architecture

- **Terraform** creates the infra: ECR, ECS service, IAM, CloudWatch, security group
- **GitHub Actions** builds the image and registers task definitions with secrets
- **All secrets live in GitHub repo secrets** — no AWS Secrets Manager needed

## Setup

### 1. Apply Terraform (one-time)

Create `terraform.tfvars`:
```hcl
aws_region      = "us-east-1"
environment     = "prod"
ecs_cluster_id  = "arn:aws:ecs:us-east-1:<account>:cluster/bitcast-prod"
vpc_id          = "vpc-xxxxxxxx"
subnet_ids      = ["subnet-xxx", "subnet-yyy"]
```

```bash
cd terraform
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

### 2. Add GitHub repo secrets

| Secret | Description |
|--------|-------------|
| `AWS_ASSUME_ROLE_ARN` | IAM role for GHA to push to ECR + update ECS |
| `BITCAST_API_KEY` | Bitcast API key for fetching access tokens |
| `BT_WALLET_HOTKEY` | Bittensor hotkey JSON contents |

| Variable | Description |
|----------|-------------|
| `BITCAST_API_URL` | API base URL (default: `https://api.bitcast.so`) |
| `BT_WALLET_NAME` | Wallet name (default: `default`) |
| `BT_WALLET_HOTKEY_NAME` | Hotkey name (default: `default`) |

### 3. Deploy

Merge to `main` — GitHub Actions handles the rest:
- Builds Docker image
- Pushes to ECR
- Registers new task definition with secrets
- Forces ECS service redeployment

## Cost Estimate

- Fargate (1 vCPU, 2GB): ~$30-40/month
- ECR storage: ~$1/month
- CloudWatch logs: ~$1-5/month

## Notes

- No ALB needed — miner is outbound-only (Bittensor axon, no inbound HTTP)
- Auto-update is disabled in Docker (`--neuron.disable_auto_update`) — image updates handle deploys
- Wallet hotkey is injected as env var from GitHub secrets at deploy time
- Infrastructure should eventually move into the `bitcast-infra` repo
