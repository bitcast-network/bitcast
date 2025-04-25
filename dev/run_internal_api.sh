#!/bin/bash

# Stop the application if it's already running
pm2 delete internal_api

# Run the application using pm2 with the process name "miner_dashboard"
pm2 start "$(dirname "${BASH_SOURCE[0]}")/internal_api.py" --name internal_api --interpreter python