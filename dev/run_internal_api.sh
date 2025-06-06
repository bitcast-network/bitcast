#!/bin/bash

# Resolve project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Set PYTHONPATH to ensure modules can be found
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Stop the application if it's already running
pm2 delete internal_api 2>/dev/null || true

# Run the API with pm2
pm2 start --name internal_api --interpreter python3 "$PROJECT_ROOT/dev/internal_api_wrapper.py"

# Note: We're keeping the wrapper script for pm2 to use it