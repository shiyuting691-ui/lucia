#!/bin/bash
# 伙伴云CRM同步脚本
# 每天8点和13点由crontab调用
set -a
source /opt/jizhi-growth-system/.env
set +a

cd /opt/jizhi-growth-system
LOG=/opt/jizhi-growth-system/logs/crm_sync.log

mkdir -p /opt/jizhi-growth-system/logs

echo "$(date '+%Y-%m-%d %H:%M:%S') [START] CRM sync" >> "$LOG"

.venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/jizhi-growth-system')
from services.huoban_sync import sync_all
result = sync_all(days_back=2)
print('leads:', result.get('leads', {}))
print('orders:', result.get('orders', {}))
" >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') [DONE] CRM sync" >> "$LOG"
