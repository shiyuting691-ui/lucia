#!/usr/bin/env bash
set -e

cd /opt/jizhi-growth-system

if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

source .venv/bin/activate
python main.py run-daily-reminder
