#!/bin/bash
# 每天08:00 每日Agent全量运行（提醒 + 供给风险 + 巡检）
# 周一额外运行周度简报
# 每月1日额外运行月度策略
set -e
LOG="/tmp/daily_agents_$(date +%Y%m%d).log"
cd /opt/jizhi-growth-system
set -a; source .env; set +a
export DATABASE_URL=sqlite:///data/marketing.db

DAY_OF_WEEK=$(date +%u)   # 1=周一 7=周日
DAY_OF_MONTH=$(date +%d)  # 01-31

echo "$(date '+%Y-%m-%d %H:%M:%S') [START] daily agents (dow=$DAY_OF_WEEK dom=$DAY_OF_MONTH)" >> "$LOG"

if [ "$DAY_OF_MONTH" = "01" ]; then
    # 每月1日：每日+每周+月度全量
    MODE="monthly"
elif [ "$DAY_OF_WEEK" = "1" ]; then
    # 每周一：每日+每周
    MODE="weekly"
else
    # 其余天：只跑每日
    MODE="daily"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [MODE] $MODE" >> "$LOG"
.venv/bin/python3 scripts/run_daily_all.py --mode "$MODE" >> "$LOG" 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') [DONE] $MODE" >> "$LOG"
