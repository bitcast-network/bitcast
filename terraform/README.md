# Bitcast Miner — ECS Fargate Infrastructure

Runs the Bitcast miner on AWS ECS Fargate with auto-healing.

This is optional infrastructure — the miner works fine without Docker/ECS
using the standard `python neurons/miner.py` flow.

## Architecture

- **Terraform** (in bitcast-infra) creates ECR, ECS service, IAM, task definition with secrets
- **GitHub Actions** builds the image and swaps it into the existing task definition — secrets untouched
- Follows the same pattern as `payments` repo

## Setup

### 1. Create terraform.tfvars

```hcl
aws_region           = "us-east-1"
environment          = "prod"
ecs_cluster_id       = "arn:aws:ecs:us-east-1:<account>:cluster/bitcast"
vpc_id               = "vpc-xxxxxxxx"
subnet_ids           = ["subnet-xxx", "subnet-yyy"]

# Secrets (store in bitcast-infra GitHub secrets or tfvars)
bitcast_api_key      = "your-api-key"
bt_wallet_hotkey     = "hotkey-json-contents"
bt_wallet_name       = "default"
bt_wallet_hotkey_name = "default"
```

### 2. Apply Terraform

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

### 3. Add GitHub repo variable

| Variable | Description |
|----------|-------------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role for GHA (same as payments repo) |

### 4. Deploy

Merge to `main` — GitHub Actions handles the rest:
- Builds Docker image → pushes to ECR
- Updates task definition (image only, secrets stay)
- Forces ECS service redeployment

## Cost Estimate

- Fargate (1 vCPU, 2GB): ~$30-40/month
- ECR storage: ~$1/month
- CloudWatch logs: ~$1-5/month

## Notes

- No ALB — miner is outbound-only (Bittensor axon, no inbound HTTP)
- Auto-update disabled in Docker (`--neuron.disable_auto_update`) — image updates handle deploys
- Secrets live in Terraform state, same pattern as payments
- Infrastructure should move into `bitcast-infra` repo alongside other services
