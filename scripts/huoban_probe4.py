"""伙伴云 — 客户信息 + 订单 + 客户跟进 字段详查"""
import requests, json, os

KEY  = os.environ.get("HUOBAN_API_KEY", "")
H    = {"Open-Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE = "https://api.huoban.com"

TARGET_TABLES = {
    "客户信息": "2100000052578962",
    "客户跟进": "2100000052581248",
    "订单":     "2100000052585140",
    "客户来源": "2100000052579004",
}

def post(path, body):
    r = requests.post(BASE + path, headers=H, json=body, timeout=10)
    return r.json()

for name, tid in TARGET_TABLES.items():
    print(f"\n{'='*60}")
    print(f"【{name}】table_id={tid}")

    # 拉字段定义
    resp = post("/openapi/v1/field/list", {"table_id": tid})
    fields = resp.get("data", {}).get("fields") or []
    print(f"  字段数: {len(fields)}")
    for f in fields:
        fid   = f.get("field_id")
        fname = f.get("name")
        ftype = f.get("type")
        print(f"  field_id={fid}  name={fname}  type={ftype}")

    # 拉前3条数据
    print("  --- 前3条数据 ---")
    resp2 = post("/openapi/v1/item/list", {"table_id": tid, "offset": 0, "limit": 3})
    items = resp2.get("data", {}).get("items") or []
    total = resp2.get("data", {}).get("total", 0)
    print(f"  总记录数: {total}")
    for item in items:
        print(f"  item_id={item.get('item_id')}  title={str(item.get('title',''))[:40]}")
        for k, v in list(item.get("fields", {}).items()):
            # 找到对应字段名
            fname = next((f["name"] for f in fields if f["field_id"] == k), k)
            print(f"    [{fname}] = {str(v)[:80]}")
        print()
