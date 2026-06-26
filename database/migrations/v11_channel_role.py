"""V11 迁移：渠道-角色归因字段 + 两张新表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db import engine
from sqlalchemy import text, inspect
from database.models import ChannelPerformance, RoleExecutionMetrics, Base


def run():
    insp = inspect(engine)
    existing_tables = insp.get_table_names()

    with engine.connect() as conn:
        # 1. leads 表新增字段
        leads_cols = [c["name"] for c in insp.get_columns("leads")]
        new_cols = {
            "lead_source_channel": "VARCHAR(50)",
            "lead_source_detail":  "VARCHAR(200)",
            "content_id":          "INTEGER",
            "campaign_id":         "INTEGER",
            "source_owner_role":   "VARCHAR(50)",
            "source_owner_name":   "VARCHAR(100)",
            "assigned_role":       "VARCHAR(50)",
            "assigned_person":     "VARCHAR(100)",
            "customer_stage":      "VARCHAR(50)",
            "followup_status":     "VARCHAR(30)",
            "last_followup_time":  "DATETIME",
            "next_followup_time":  "DATETIME",
            "deal_amount":         "FLOAT",
            "risk_flag":           "BOOLEAN DEFAULT 0",
            "risk_reason":         "TEXT",
            "updated_at":          "DATETIME",
        }
        for col, dtype in new_cols.items():
            if col not in leads_cols:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {dtype}"))
                print(f"  ✅ leads.{col} 已新增")
            else:
                print(f"  — leads.{col} 已存在，跳过")

        # 2. 迁移旧 source_channel → lead_source_channel（normalize）
        conn.execute(text("""
            UPDATE leads SET lead_source_channel = CASE
                WHEN source_channel IN ('xiaohongshu','小红书') THEN 'xiaohongshu'
                WHEN source_channel IN ('moments','朋友圈') THEN 'moments'
                WHEN source_channel IN ('community','社群') THEN 'community'
                WHEN source_channel IN ('referral','转介绍') THEN 'referral'
                WHEN source_channel IN ('old_customer','老客户') THEN 'old_customer'
                WHEN source_channel IN ('promotion','推广') THEN 'promotion'
                WHEN source_channel IN ('vertical_account','垂直号') THEN 'vertical_account'
                WHEN source_channel IS NULL OR source_channel = '' THEN 'unknown'
                ELSE 'unknown'
            END
            WHERE lead_source_channel IS NULL
        """))

        # 3. 迁移 sales_owner → assigned_person（保留原字段）
        conn.execute(text("""
            UPDATE leads SET assigned_person = sales_owner
            WHERE assigned_person IS NULL AND sales_owner IS NOT NULL
        """))

        conn.commit()
        print("✅ leads 表迁移完成")

    # 4. 新建两张表
    ChannelPerformance.__table__.create(engine, checkfirst=True)
    RoleExecutionMetrics.__table__.create(engine, checkfirst=True)
    print("✅ channel_performance 表已创建")
    print("✅ role_execution_metrics 表已创建")

    print("\n🎉 V11 迁移完成")


if __name__ == "__main__":
    run()
