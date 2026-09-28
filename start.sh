#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "========================================================"
echo "  Starting BestResponse Multi-LLM Web Aggregator"
echo "========================================================"

if [ ! -f ".venv/bin/python" ]; then
    echo "Virtual environment not found. Setting up .venv..."
    python3 -m venv .venv
    echo "Installing dependencies..."
    .venv/bin/pip install -r requirements.txt
    .venv/bin/playwright install chromium
fi

echo "Launching BestResponse Dashboard..."
.venv/bin/python run.py
