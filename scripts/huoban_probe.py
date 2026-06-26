"""伙伴云 API 路径探测"""
import requests, os

KEY  = os.environ.get("HUOBAN_API_KEY", "Hy8nQjpnPYmj9YOW3EHBs3PzjjGWY0IwPNFajDY6")
H    = {"Open-Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE = "https://api.huoban.com"

tests = [
    ("GET",  "/openapi/v1/table/list",              None),
    ("POST", "/openapi/v1/table/list",              {}),
    ("GET",  "/openapi/v2/table/list",              None),
    ("GET",  "/openapi/v1/space/list",              None),
    ("POST", "/openapi/v1/space/list",              {}),
    ("POST", "/openapi/v1/application/table/list",  {}),
    ("GET",  "/openapi/v1/user/me",                 None),
    ("POST", "/openapi/v1/item/list",               {"table_id": "test", "limit": 1}),
]

for method, path, body in tests:
    try:
        if method == "GET":
            r = requests.get(BASE + path, headers=H, timeout=8)
        else:
            r = requests.post(BASE + path, headers=H, json=body, timeout=8)
        print(f"{method} {path} -> {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"{method} {path} -> ERR: {e}")
