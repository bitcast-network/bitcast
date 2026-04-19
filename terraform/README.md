# Bitcast Miner — ECS Fargate Infrastructure

Runs the Bitcast miner on AWS ECS Fargate with auto-healing.

This is optional infrastructure — the miner works fine without Docker/ECS
using the standard `python neurons/miner.py` flow.

## Prerequisites

- Terraform >= 1.0
- AWS CLI configured
- Docker (for building images)
- Access to the existing Bitcast ECS cluster (from bitcast-infra)

## Setup

### 1. Create secrets in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name bitcast-miner/bt-api-key \
  --secret-string "YOUR_BITCAST_API_KEY"

aws secretsmanager create-secret \
  --name bitcast-miner/wallet-hotkey \
  --secret-string "$(cat ~/.bittensor/wallets/<wallet-name>/hotkey)"
```

### 2. Create terraform.tfvars

```hcl
aws_region      = "us-east-1"
environment     = "prod"
ecs_cluster_id  = "arn:aws:ecs:us-east-1:<account>:cluster/bitcast-prod"  # from bitcast-infra
vpc_id          = "vpc-xxxxxxxx"    # from bitcast-infra
subnet_ids      = ["subnet-xxx", "subnet-yyy"]  # public subnets from bitcast-infra

secrets = {
  BITCAST_API_KEY  = "arn:aws:secretsmanager:us-east-1:<account>:secret:bitcast-miner/bt-api-key-??????"
  BT_WALLET_HOTKEY = "arn:aws:secretsmanager:us-east-1:<account>:secret:bitcast-miner/wallet-hotkey-??????"
}
```

### 3. Build and push Docker image

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker build -t bitcast-miner .
docker tag bitcast-miner:latest \
  <account>.dkr.ecr.us-east-1.amazonaws.com/bitcast-miner:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/bitcast-miner:latest
```

### 4. Deploy

```bash
cd terraform
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Cost Estimate

- Fargate (1 vCPU, 2GB): ~$30-40/month
- ECR storage: ~$1/month
- CloudWatch logs: ~$1-5/month

## Notes

- No ALB needed — the miner is outbound-only (connects to Bittensor, no inbound HTTP)
- Wallet hotkey is stored in Secrets Manager and injected at runtime
- Task definition includes default Bittensor args (netuid 93, finney network) — override in task definition as needed
- Infrastructure should eventually be moved into the `bitcast-infra` repo alongside other services
