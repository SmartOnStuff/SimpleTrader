#!/bin/bash

# Load environment variables from .env
source .env

while true
do
    # Run the Python script
    python3 multipair.py
    sleep 30

    # Check if any `_trades.csv` file has been created or modified
    if git ls-files --modified | grep '_trades.csv$' || ls *_trades.csv 2>/dev/null | grep -q .
    then
        echo "Detected changes in trade files, force pushing to GitHub..."

        git add .
        git commit -m "Auto-push: Updated trade data"

        # Forced push to overwrite remote changes
        git push --force https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@${GITHUB_REPO} main
    fi
done
