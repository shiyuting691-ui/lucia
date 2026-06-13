"""
V9 数据库迁移脚本
- tasks 表：新增 strategy_id / completion_result / blockers 三列
- 新增4张表：opportunity_scores / lead_scores / campaign_predictions / weekly_reviews
  （通过 create_all 自动创建，仅 tasks 扩展需要 ALTER TABLE）

运行方式：
  cd /opt/jizhi-growth-system
  python -m database.migrations.v9_growth_management
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database.db import engine, init_db
from sqlalchemy import text, inspect


def run():
    inspector = inspect(engine)

    # 1. 新增4张表（幂等，已存在则跳过）
    from database.models import Base
    Base.metadata.create_all(engine)
    print("[V9] create_all 完成（新表已创建，已有表不变）")

    # 2. tasks 表扩展（SQLite ALTER TABLE 每次只能加一列）
    existing_cols = {c["name"] for c in inspector.get_columns("tasks")}
    additions = [
        ("strategy_id",       "INTEGER"),
        ("completion_result", "TEXT"),
        ("blockers",          "TEXT"),
    ]
    with engine.connect() as conn:
        for col, col_type in additions:
            if col not in existing_cols:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}"))
                print(f"[V9] tasks.{col} 已添加")
            else:
                print(f"[V9] tasks.{col} 已存在，跳过")
        conn.commit()

    print("[V9] 迁移完成")


if __name__ == "__main__":
    run()
