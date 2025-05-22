#!/bin/bash

# Set PYTHONPATH to ensure modules can be found
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Stop the application if it's already running
pm2 delete internal_api 2>/dev/null || true

# Create a wrapper script that imports the required modules
cd $(dirname "$0")
cat > internal_api_wrapper.py << EOF
import bt_logging_patch
import internal_api
internal_api.main()
EOF

# Run the API with pm2
pm2 start --name internal_api --interpreter python3 internal_api_wrapper.py

# Note: We're keeping the wrapper script for pm2 to use it