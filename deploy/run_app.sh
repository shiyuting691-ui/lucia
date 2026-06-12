#!/usr/bin/env bash
set -e

cd /opt/jizhi-growth-system

if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

source .venv/bin/activate

streamlit run dashboard.py \
  --server.port ${STREAMLIT_SERVER_PORT:-8501} \
  --server.address ${STREAMLIT_SERVER_ADDRESS:-0.0.0.0} \
  --server.headless true
