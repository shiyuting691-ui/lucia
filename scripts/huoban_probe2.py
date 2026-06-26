"""伙伴云 — 用 space_id 拉表格和字段"""
import requests, json, os

KEY      = os.environ.get("HUOBAN_API_KEY", "Hy8nQjpnPYmj9YOW3EHBs3PzjjGWY0IwPNFajDY6")
H        = {"Open-Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE     = "https://api.huoban.com"
SPACE_ID = "4000000007239337"

def get(path, params=None):
    r = requests.get(BASE + path, headers=H, params=params, timeout=10)
    return r.status_code, r.json()

def post(path, body):
    r = requests.post(BASE + path, headers=H, json=body, timeout=10)
    return r.status_code, r.json()

# 1. 拉所有 space
print("=== spaces ===")
code, data = get("/openapi/v1/space/list")
spaces = data.get("data", {}).get("spaces", [])
for s in spaces:
    print(f"  space_id={s['space_id']}  name={s['name']}")

# 2. 用 space_id 拉表格
print("\n=== tables in space ===")
code, data = post("/openapi/v1/table/list", {"space_id": SPACE_ID, "offset": 0, "limit": 50})
print(f"  status={code}")
tables = data.get("data", {}).get("tables") or data.get("data", [])
if not tables and isinstance(data.get("data"), list):
    tables = data["data"]
print(f"  返回表数量: {len(tables)}")
for t in tables:
    tid  = t.get("table_id") or t.get("id")
    name = t.get("name") or t.get("title")
    print(f"  table_id={tid}  name={name}")

# 3. 对每张表拉前2条记录
print("\n=== 各表前2条数据字段 ===")
for t in tables[:8]:
    tid  = t.get("table_id") or t.get("id")
    name = t.get("name") or t.get("title")
    print(f"\n【{name}】table_id={tid}")
    code2, resp2 = post("/openapi/v1/item/list", {
        "table_id": tid, "offset": 0, "limit": 2,
    })
    items = resp2.get("data", {}).get("items") or []
    if not items:
        print(f"  无数据  raw={json.dumps(resp2)[:120]}")
        continue
    for item in items:
        fields = item.get("fields", {})
        print(f"  item_id={item.get('item_id')} title={item.get('title','')[:30]}")
        for k, v in list(fields.items())[:12]:
            print(f"    {k} = {str(v)[:80]}")
