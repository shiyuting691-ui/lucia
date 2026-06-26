"""伙伴云 — 九宙SCRM 表格和字段探测"""
import requests, json, os

KEY      = os.environ.get("HUOBAN_API_KEY", "")
H        = {"Open-Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE     = "https://api.huoban.com"
SPACE_ID = "4000000007072757"  # 九宙SCRM

def post(path, body):
    r = requests.post(BASE + path, headers=H, json=body, timeout=10)
    return r.json()

# 1. 拉表格列表
data = post("/openapi/v1/table/list", {"space_id": SPACE_ID, "offset": 0, "limit": 50})
tables = data.get("data", {}).get("tables") or []
print(f"九宙SCRM 共 {len(tables)} 张表\n")
for t in tables:
    print(f"  table_id={t.get('table_id')}  name={t.get('name')}")

# 2. 每张表拉前3条数据
print("\n" + "="*60)
for t in tables[:10]:
    tid  = t.get("table_id")
    name = t.get("name", "")
    print(f"\n【{name}】table_id={tid}")
    resp = post("/openapi/v1/item/list", {"table_id": tid, "offset": 0, "limit": 3})
    items = resp.get("data", {}).get("items") or []
    total = resp.get("data", {}).get("total", 0)
    print(f"  总记录数: {total}")
    for item in items[:2]:
        fields = item.get("fields", {})
        print(f"  --- item_id={item.get('item_id')} title={str(item.get('title',''))[:30]}")
        for k, v in list(fields.items())[:15]:
            print(f"      {k} = {str(v)[:80]}")
