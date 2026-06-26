#!/bin/bash
# 每天14:00 企业微信日报推送
set -e
LOG="/tmp/push_$(date +%Y%m%d).log"
cd /opt/jizhi-growth-system
set -a; source .env; set +a
export DATABASE_URL=sqlite:///data/marketing.db

echo "$(date '+%Y-%m-%d %H:%M:%S') [START] daily push" >> "$LOG"
.venv/bin/python3 scripts/run_daily_all.py --mode push >> "$LOG" 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') [DONE] daily push" >> "$LOG"
