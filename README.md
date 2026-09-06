# Bitcast V2 — Decentralized Creator Economy (SN93)

Reengineered Bitcast subnet: a clean, lean, async-first Python codebase on Bittensor 10.x.

## Overview

Bitcast connects brands with audiences through content creators. Creators (miners) publish
YouTube videos satisfying brand briefs; validators verify engagement via the YouTube
Analytics API, score videos in USD terms, and convert those scores into on-chain weights.

- **Miners** serve YouTube OAuth access tokens for the channels they operate.
- **Validators** fetch active briefs, evaluate every miner's channels/videos against them
  (LLM-assisted brief matching), and set weights so emissions track earned USD value.
- Unallocated emission is absorbed by the burn UID (0).

## Layout

```
bitcast/
├── protocol.py          # AccessTokenSynapse — the single wire message
├── config.py            # ALL configuration: consensus constants, env settings, CLI
├── neuron.py            # Shared wallet/subtensor/metagraph lifecycle
├── miner/               # Token management (OAuth refresh) + axon server
├── validator/
│   ├── base.py          # Score state, EMA updates, weight-setting cadence
│   ├── forward.py       # Main loop: briefs → query → evaluate → score → weights
│   ├── weights.py       # Weight processing and chain submission
│   ├── reward/          # Orchestrator, models, scaling math, pricing
│   ├── youtube/         # YouTube API client, vetting, scoring, brief matching
│   └── llm/             # OpenRouter/Chute client + verbatim prompts
└── utils/               # Briefs client, signed dashboard publisher, TTL cache
```

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in API keys
```

## Run

```bash
# Miner
python -m neurons.miner --netuid 93 --subtensor.network finney \
    --wallet.name miner --wallet.hotkey default

# Validator
python -m neurons.validator --netuid 93 --subtensor.network finney \
    --wallet.name validator --wallet.hotkey default
```

Miner credentials: put one JSON file per YouTube account in `~/.bitcast/secrets/`, each
containing `client_id`, `client_secret` and `refresh_token` (or set `TOKEN_SOURCE=api`).

## Development

```bash
pytest                 # offline test suite (chain/YouTube/LLM all mocked)
ruff check .           # lint
ruff format .          # format
```

## Observability: Loki score audit telemetry

Loki is enabled by default for the shared Bitcast dataset. Operators can set
`LOKI_URL`, `LOKI_USERNAME`, and `LOKI_TOKEN` together to use another Grafana
Cloud stack. Do not add credentials to labels or log lines. Logging is batched
and best-effort, so a telemetry failure cannot affect validation, EMA state,
weight calculation, or chain submission.

Each reward cycle emits one JSON `miner_score` line per miner. Its safe schema
is limited to `validator_uid`, `cycle_id`, `cycle_step`, `miner_uid`,
`raw_reward` (pre-EMA), `ema_before`, and `ema_after`. When a weight submission
succeeds in the following sync, that same line also contains
`submitted_weight` (the processed float submitted to the SDK) and
`onchain_weight_uint16` (the converted chain value). These are intentionally
different values: raw reward feeds EMA; EMA scores are normalized/processed into
the submitted weight; the uint16 is the final on-chain encoding.

Validator identity stays in bounded Loki labels (`uid`, `hotkey`, `netuid`,
`neuron`, `version`); miner UID is a JSON field, never a label. For example, to
compare miner UID 68 on owner UID 0 and canary UID 60:

```logql
{neuron="validator", netuid="93", uid=~"0|60"} | json | event="miner_score" | miner_uid="68"
```

Plot raw reward and EMA across both validators:

```logql
avg_over_time({neuron="validator", netuid="93", uid=~"0|60"} | json | event="miner_score" | miner_uid="68" | unwrap ema_after [6h]) by (uid)
```

Inspect only actual successful weight submissions (records without these fields
were score cycles where no weights were submitted):

```logql
{neuron="validator", netuid="93", uid=~"0|60"} | json | event="miner_score" | miner_uid="68" | onchain_weight_uint16!=""
```

## Docker

```bash
docker build -t bitcast .
docker run --env-file .env bitcast                       # validator
docker run --env-file .env bitcast python -m neurons.miner --netuid 93
```
