"""迁移 v12：给 leads 和 orders 表添加 CRM 同步字段"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")
sys.path.insert(0, "/opt/jizhi-growth-system")

from database.db import engine
from sqlalchemy import text, inspect

insp = inspect(engine)

def add_cols(table, cols):
    existing = [c["name"] for c in insp.get_columns(table)]
    with engine.connect() as conn:
        for col, dtype in cols.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}"))
                print(f"  ✅ {table}.{col} 已新增")
            else:
                print(f"  — {table}.{col} 已存在")
        conn.commit()

add_cols("leads",  {"crm_id": "VARCHAR(50)", "crm_source": "VARCHAR(20)", "crm_updated_at": "VARCHAR(30)"})
add_cols("orders", {"crm_id": "VARCHAR(50)", "crm_source": "VARCHAR(20)", "crm_updated_at": "VARCHAR(30)"})
print("✅ v12 迁移完成")
