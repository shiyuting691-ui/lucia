"""补全 tasks 表缺失的列"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")
sys.path.insert(0, "/opt/jizhi-growth-system")

from database.db import engine
from sqlalchemy import text, inspect

insp = inspect(engine)
existing = [c["name"] for c in insp.get_columns("tasks")]
print("现有列:", existing)

# tasks 表需要的所有列（来自 models.py Task 类）
needed = {
    "task_source":        "VARCHAR(50)",
    "related_product":    "VARCHAR(100)",
    "related_school":     "VARCHAR(100)",
    "related_content_id": "INTEGER",
    "related_campaign_id":"INTEGER",
    "strategy_id":        "INTEGER",
    "expected_output":    "TEXT",
    "completion_result":  "TEXT",
    "blockers":           "TEXT",
    "notes":              "TEXT",
    "updated_at":         "DATETIME",
    "completed_at":       "DATETIME",
}

with engine.connect() as conn:
    for col, dtype in needed.items():
        if col not in existing:
            conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {dtype}"))
            print(f"  ✅ tasks.{col} 已新增")
        else:
            print(f"  — tasks.{col} 已存在")
    conn.commit()

print("✅ tasks 表补全完成")
