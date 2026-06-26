"""
teacher_capacity 初始数据录入脚本
运行方式: python scripts/seed_teacher_capacity.py

每行对应一类老师资源。团队填好后执行一次即可。
后续更新直接修改 ROWS 列表中的数值，重新运行会先清空再插入。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")

from datetime import datetime
from database import engine
from sqlalchemy import text

# ══════════════════════════════════════════════════════════════
#  请团队根据实际情况填写 available_slots / current_load / max_capacity
#  capacity_status: sufficient / tight / full
#  risk_level: low / medium / high
# ══════════════════════════════════════════════════════════════
ROWS = [
    # ── 课业辅导（regular）────────────────────────────────
    {
        "subject_area":     "regular",
        "course_type":      "coursework",
        "country":          "UK",
        "school_experience": "综合大学",
        "available_slots":  20,
        "current_load":     10,
        "max_capacity":     30,
        "capacity_status":  "sufficient",
        "risk_level":       "low",
        "notes":            "覆盖Essay/Report/Presentation，UK方向，请按实际修改",
    },
    {
        "subject_area":     "regular",
        "course_type":      "coursework",
        "country":          "AU",
        "school_experience": "综合大学",
        "available_slots":  15,
        "current_load":     8,
        "max_capacity":     25,
        "capacity_status":  "sufficient",
        "risk_level":       "low",
        "notes":            "覆盖Essay/Report，AU方向，请按实际修改",
    },
    # ── 毕业论文辅导（dissertation）───────────────────────
    {
        "subject_area":     "dissertation",
        "course_type":      "thesis",
        "country":          "UK",
        "school_experience": "Russell Group",
        "available_slots":  5,
        "current_load":     3,
        "max_capacity":     8,
        "capacity_status":  "sufficient",
        "risk_level":       "medium",
        "notes":            "毕业论文老师有限，旺季（5-6月/11-12月）需提前排期",
    },
    {
        "subject_area":     "dissertation",
        "course_type":      "thesis",
        "country":          "AU",
        "school_experience": "G8大学",
        "available_slots":  4,
        "current_load":     2,
        "max_capacity":     6,
        "capacity_status":  "sufficient",
        "risk_level":       "medium",
        "notes":            "AU毕业论文老师，请按实际修改",
    },
    # ── Final押题（final_prediction）─────────────────────
    {
        "subject_area":     "final_exam",
        "course_type":      "exam_prep",
        "country":          "UK",
        "school_experience": "综合大学",
        "available_slots":  10,
        "current_load":     2,
        "max_capacity":     15,
        "capacity_status":  "sufficient",
        "risk_level":       "low",
        "notes":            "考前押题，期末旺季（1月/6月/12月）需提前预排",
    },
    # ── 保过辅导（guaranteed）─────────────────────────────
    {
        "subject_area":     "guaranteed",
        "course_type":      "pass_guarantee",
        "country":          "UK",
        "school_experience": "综合大学",
        "available_slots":  6,
        "current_load":     2,
        "max_capacity":     8,
        "capacity_status":  "sufficient",
        "risk_level":       "medium",
        "notes":            "保过产品需提前评估老师资质，接单前须学管确认",
    },
    # ── 学年包（annual_package）───────────────────────────
    {
        "subject_area":     "annual",
        "course_type":      "package",
        "country":          "UK",
        "school_experience": "综合大学",
        "available_slots":  8,
        "current_load":     4,
        "max_capacity":     12,
        "capacity_status":  "sufficient",
        "risk_level":       "low",
        "notes":            "学年包长期服务，需固定老师绑定，请按实际修改",
    },
    # ── DP旗舰版（dp_premium）────────────────────────────
    {
        "subject_area":     "dp",
        "course_type":      "diploma",
        "country":          "UK",
        "school_experience": "TOP30大学",
        "available_slots":  4,
        "current_load":     2,
        "max_capacity":     6,
        "capacity_status":  "sufficient",
        "risk_level":       "low",
        "notes":            "DP专属顶级老师资源，稀缺，接单前必须确认",
    },
]


def run():
    now = datetime.now().isoformat()

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM teacher_capacity"))
        for row in ROWS:
            conn.execute(text("""
                INSERT INTO teacher_capacity
                    (subject_area, course_type, country, school_experience,
                     available_slots, current_load, max_capacity,
                     capacity_status, risk_level, notes, updated_at)
                VALUES
                    (:subject_area, :course_type, :country, :school_experience,
                     :available_slots, :current_load, :max_capacity,
                     :capacity_status, :risk_level, :notes, :updated_at)
            """), {**row, "updated_at": now})
        conn.commit()

    print(f"✅ 已写入 {len(ROWS)} 条 teacher_capacity 记录")
    print("   提示：请根据实际老师排期修改 available_slots / current_load / capacity_status")


if __name__ == "__main__":
    run()
