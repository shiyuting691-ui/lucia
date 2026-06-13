"""
V10 迁移：新增 attribution_snapshots 表
"""
from database.db import engine
from database.models import Base, AttributionSnapshot
from sqlalchemy import inspect, text


def run():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "attribution_snapshots" not in existing_tables:
        AttributionSnapshot.__table__.create(engine)
        print("✅ 创建 attribution_snapshots 表")
    else:
        print("⏭  attribution_snapshots 已存在，跳过")

    # 验证
    checks = {
        "attribution_snapshots 表存在": "attribution_snapshots" in inspector.get_table_names(),
    }
    with engine.connect() as conn:
        cols = [c["name"] for c in inspector.get_columns("attribution_snapshots")]
        for col in ["channel_data", "advisor_data", "product_school_data", "key_insights", "action_items"]:
            checks[f"列 {col} 存在"] = col in cols

    print("\n验证结果：")
    all_ok = True
    for name, ok in checks.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            all_ok = False

    return all_ok


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    run()
