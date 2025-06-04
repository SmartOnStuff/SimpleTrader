#!/bin/bash

# Load environment variables from .env
source .env

while true
do
    # Run the Python script
    python3 main.py
    sleep 59

    # Check if any `_trades.csv` file has been created or modified
    if git status --porcelain | grep -E 'logs/.*_trades.csv$'    
    then
        echo "Detected changes in trade files, force pushing to GitHub..."

        # Add only `_trades.csv` files
        git add $(git status --porcelain | awk '{print $2}' | grep -E 'logs/.*_trades.csv$')
        git commit -m "Auto-push: Updated trade data"

        # Forced push to overwrite remote changes
        git push --force https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@${GITHUB_REPO} main
    fi
done
