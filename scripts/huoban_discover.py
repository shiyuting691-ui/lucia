"""
伙伴云表格探测脚本 — 一次性运行，找出线索/订单对应的 table_id 和字段名
运行：python scripts/huoban_discover.py
"""
import json
import requests

API_KEY  = "Hy8nQjpnPYmj9YOW3EHBs3PzjjGWY0IwPNFajDY6"
BASE_URL = "https://api.huoban.com"
HEADERS  = {
    "Open-Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def get(path, **kwargs):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15, **kwargs)
    r.raise_for_status()
    return r.json()


def post(path, body):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    # 1. 列出所有表格
    print("=" * 60)
    print("【所有表格】")
    try:
        resp = post("/openapi/v1/table/list", {"offset": 0, "limit": 50})
        tables = resp.get("data", {}).get("tables") or resp.get("data", [])
        for t in tables:
            tid  = t.get("table_id", t.get("id", "?"))
            name = t.get("name", t.get("title", "?"))
            print(f"  table_id={tid}  名称={name}")
        print()
    except Exception as e:
        print(f"  获取表格列表失败: {e}\n  尝试 /openapi/v1/space/table/list")
        try:
            resp2 = post("/openapi/v1/space/table/list", {"offset": 0, "limit": 50})
            print(json.dumps(resp2, ensure_ascii=False, indent=2)[:2000])
        except Exception as e2:
            print(f"  也失败了: {e2}")
        return

    if not tables:
        print("  没有返回表格，检查 API Key 或权限")
        return

    # 2. 对每张表列出前3条记录（看字段长什么样）
    for t in tables[:6]:  # 最多看6张表
        tid  = t.get("table_id", t.get("id", ""))
        name = t.get("name", t.get("title", ""))
        print(f"{'=' * 60}")
        print(f"【{name}】 table_id={tid}")
        try:
            items_resp = post("/openapi/v1/item/list", {
                "table_id": tid,
                "offset": 0,
                "limit": 3,
            })
            items = items_resp.get("data", {}).get("items") or []
            if not items:
                print("  （无数据）")
            for item in items[:2]:
                fields = item.get("fields", {})
                print(f"  item_id={item.get('item_id')}")
                for fid, fval in list(fields.items())[:10]:
                    print(f"    {fid} = {str(fval)[:60]}")
        except Exception as e:
            print(f"  获取条目失败: {e}")
        print()


if __name__ == "__main__":
    main()
