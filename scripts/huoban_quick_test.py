"""快速测试伙伴云解析 — 只拉10条，不分页"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests, os as _os

KEY  = _os.environ.get("HUOBAN_API_KEY", "")
H    = {"Open-Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE = "https://api.huoban.com"

def post(path, body):
    r = requests.post(BASE + path, headers=H, json=body, timeout=15)
    return r.json()

# 只拉3条客户
print("=== 客户信息（3条）===")
resp = post("/openapi/v1/item/list", {"table_id": "2100000052578962", "offset": 0, "limit": 3})
print(f"raw data type: {type(resp.get('data'))}  keys: {list(resp.get('data',{}).keys()) if isinstance(resp.get('data'),dict) else 'is list'}")
data = resp.get("data", {})
if isinstance(data, list):
    items = data
elif isinstance(data, dict):
    items = data.get("items") or []
else:
    items = []
print(f"返回: {len(items)} 条，总计: {resp.get('data',{}).get('total') if isinstance(data,dict) else len(items)}")

from services.huoban_crm import parse_customer, parse_order
for item in items:
    lead = parse_customer(item)
    print(f"  {lead['name']} | {lead['school']} | {lead['country']} | {lead['deal_status']} | 渠道:{lead['lead_source_channel']}")

# 只拉3条订单
print("\n=== 订单（3条）===")
resp2 = post("/openapi/v1/item/list", {"table_id": "2100000052585140", "offset": 0, "limit": 3})
data2 = resp2.get("data", {})
orders = (data2 if isinstance(data2, list) else data2.get("items") or [])
print(f"返回: {len(orders)} 条")
for item in orders:
    order = parse_order(item)
    print(f"  {order['order_no']} | {order['customer_name']} | {order['sales_owner']} | ¥{order['amount']} | {order['status']} | {order['product']}")

print("\n✅ 解析测试完成")
