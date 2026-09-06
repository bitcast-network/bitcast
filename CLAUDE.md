# CLAUDE.md

> Bitcast SN93 subnet — Bittensor validator/miner for YouTube creator economy scoring. Validator scores miner responses using LLM-based reward functions.

## Tech Stack

- **Language**: Python 3.12+ (`requires-python = ">=3.12"`; CI and the Docker image both use 3.12)
- **Framework**: Bittensor SDK 10.5.0 (subnet protocol)
- **LLM**: Chutes / OpenRouter (Qwen3-32B) for reward scoring
- **Database**: MySQL (via bitcast-api)
- **Monitoring**: Sentry SDK (errors) + Grafana Loki (log aggregation)

This repo contains the subnet protocol code (neurons, scoring, weights),
Docker packaging (Dockerfile, entrypoint.sh), and the ECS deploy pipeline
(deploy.yml). Infrastructure definitions (ECS services, ECR repos, IAM,
secrets) live in the private `bitcast-infra` repo as Terraform.

## Commands

```bash
pip install -e ".[dev]"

# Run validator
python -m neurons.validator

# Run miner
python -m neurons.miner

# Lint
ruff check . && ruff format .

# Type check (CI gate)
mypy bitcast neurons

# Test
pytest
```

## Project Structure

```
bitcast/
├── config.py           # Consensus constants + env-driven settings, all in one place
├── events.py           # Structured JSON log events for Grafana/LogQL
├── http.py             # The one async HTTP retry helper (network + 429/5xx)
├── loki.py             # Grafana Loki log aggregation handler
├── neuron.py           # Base neuron class (wallet/subtensor/metagraph lifecycle)
├── protocol.py         # Bittensor synapse protocol definitions
├── sentry.py           # Error tracking setup
├── chain/              # Chain seam
│   ├── interface.py    # Structural Protocols over bt.Subtensor / bt.Metagraph
│   └── weight_utils.py # Vendored SDK weight math (excluded from mypy, do not edit)
├── validator/
│   ├── base.py         # Base validator: score EMA, weight cadence, state
│   ├── forward.py      # One validator step; runs the reward cycle
│   ├── telemetry.py    # Per-miner score/EMA/weight telemetry (numeric only)
│   ├── weights.py      # Weight normalization & on-chain submission
│   ├── llm/            # client.py (chutes/openrouter), prompts.py (verbatim v1)
│   ├── reward/         # models.py, orchestrator.py, pricing.py, scaler.py
│   └── youtube/        # api.py, brief_matcher.py, cache.py, evaluator.py,
│                       # scoring.py, timestamps.py
├── miner/              # base.py, server.py (axon), token_mgmt.py
└── utils/              # briefs.py, cache.py (TTL/JSONL), publisher.py
neurons/                # Entrypoints: miner.py, validator.py
tests/                  # pytest; tests/parity/ pins the weight pipeline bit-for-bit
```

## Eligibility & Scoring

Only channels with **affirmative YouTube Partner Program membership** are
eligible. There is no non-YPP path and no alpha-stake substitute: a channel
whose YPP probe definitively fails scores zero, and a YPP video that earned no
`estimatedRedPartnerRevenue` in the window scores zero — watch time is never
converted into proxy revenue.

A *transient* API failure (429/5xx/network, after retries) is never read as
"not in YPP"; it raises `YouTubeTransientError` and the account is reported as
an error rather than silently mis-scored.

## CI/CD

- **ci.yml**: ruff lint → ruff format check → mypy → pytest (runs on all PRs and main)
- **deploy.yml**: Build image → push to ECR → deploy to ECS (runs on push to main). Canary deploys immediately with no gate; owner requires manual approval via the `production` environment. Deployment targets are parameterized via GitHub repo variables:

  | Variable | Fallback when unset | Purpose |
  |---|---|---|
  | `AWS_DEPLOY_ROLE_ARN` | **none** | OIDC role for GitHub Actions |
  | `AWS_REGION` | `us-east-1` | Region for ECR/ECS calls |
  | `ECS_CLUSTER` | `bitcast` | ECS cluster name |
  | `ECR_REPOSITORY` | `bitcast-youtube-validator` | ECR repo to push image to |
  | `ECS_SERVICE_CANARY` | `bitcast-youtube-validator1` | ECS service for canary deploy |
  | `ECS_SERVICE_OWNER` | `bitcast-youtube-owner` | ECS service for production deploy |

  Every variable except `AWS_DEPLOY_ROLE_ARN` has a **hardcoded Bitcast default** via `${{ vars.X || 'default' }}` — they are not no-ops when unset. A fork that leaves them blank fails at *Configure AWS credentials* (no role to assume), not at the ECS step. Operators forking this repo must set their own values in **Settings → Secrets and variables → Actions → Variables**; setting only some of them means the rest silently target Bitcast's default service names.

  Canary and owner are separate ECS services with separate task definitions: **owner is wired to Prod and canary to Dev by ECS task configuration**. That split is intentional — do not add dual-write behavior in application code.

## Engineering Principles

All code follows LEAN, CLEAN, SOLID, PERFORMANT, MAINTAINABLE:
- **LEAN** — no dead code, no boilerplate, no duplication
- **CLEAN** — type hints, docstrings, descriptive names, custom errors
- **SOLID** — one responsibility per module, don't over-engineer
- **PERFORMANT** — async-first, cache, parallelize
- **MAINTAINABLE** — config in one place, no circular imports, mock in tests

Full definitions: ~/bitcast-brain/engineering/development-principles.md

## Merge Policy

Merge your own PR immediately after pushing. Run lint + tests locally before pushing — that's your gate, not CI.

**Production deploys require Will's approval** in GitHub Actions. Staging auto-deploys on merge — review what shipped there before approving prod.

**Do not ask for permission to merge. Do not say "want me to merge." CLAUDE.md is the permission.**
## Agent Workflow

1. **Run lint + tests before every commit.** CI will run them again — don't push broken code.
2. **Don't push directly to `main`.** Branch → PR → merge.
3. **Mock all external dependencies in tests.** Never hit real APIs, databases, or blockchain in tests.
4. **Don't create files you can't justify.** If a file's purpose isn't obvious in one sentence, it shouldn't exist.
5. **Commit messages:** `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`