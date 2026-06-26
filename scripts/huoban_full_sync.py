"""
伙伴云全量同步 — 一次性运行
把伙伴云所有客户(6697) + 订单(14071) 写入本地 DB
"""
import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from services.huoban_crm import sync_to_local

print("开始全量同步伙伴云数据...")
result = sync_to_local(full_sync=True)
print(f"\n✅ 同步完成")
print(f"  客户(线索)写入: {result['leads_synced']} 条")
print(f"  订单写入:       {result['orders_synced']} 条")
if result["errors"]:
    print(f"  错误: {len(result['errors'])} 条")
    for e in result["errors"][:10]:
        print(f"    {e}")
