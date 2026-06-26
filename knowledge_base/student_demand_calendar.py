"""
极致教育 · 学生需求周历

核心逻辑：
  留学生的购买行为由"学校节点"驱动，不由机构营销驱动。
  所有推广建议必须先确定"这周学生在哪个阶段"，再决定推什么、说什么。

使用方式：
  from knowledge_base.student_demand_calendar import get_current_student_phase
  phase = get_current_student_phase()  # 返回当前需求快照
"""

from datetime import date, datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# 学生需求阶段定义（按月，主要面向英国/澳洲/美国留学生）
# ─────────────────────────────────────────────────────────────────────

# 格式：月份 → {国家 → 阶段描述}
MONTHLY_STUDENT_PHASES = {
    1: {
        "uk":  "春节前期末备考（部分学校1月考试），成绩焦虑期",
        "au":  "澳洲暑假结束，新学期准备期（2月开学）",
        "us":  "秋季学期期末刚结束，等成绩/新学期准备",
        "hot_products": ["final_prediction", "regular", "guaranteed"],
        "messaging_angle": "春节前最后冲刺，帮学生体面过年",
        "urgency": "中",
    },
    2: {
        "uk":  "春季学期开始，新模块启动，作业陆续布置",
        "au":  "Trimester 1开始，新学期首月高焦虑",
        "us":  "春季学期开始，选课完毕开始有作业",
        "hot_products": ["regular", "annual_package"],
        "messaging_angle": "新学期开局，提前锁定全年GPA托管",
        "urgency": "中",
    },
    3: {
        "uk":  "英国期中作业高峰（Essay/Report密集），部分学校春假前赶deadline",
        "au":  "澳洲第一轮Assignment高峰",
        "us":  "美国春季学期中期，Midterm备考",
        "hot_products": ["regular", "dissertation", "annual_package"],
        "messaging_angle": "Essay堆积，学生压力最大的一个月，即时需求高",
        "urgency": "高",
    },
    4: {
        "uk":  "英国期末考试倒计时（5月考试），Dissertation提交季开始",
        "au":  "澳洲T1期末备考开始（4-5月考试），Dissertation高峰",
        "us":  "美国Final前一个月，部分学校4月期末",
        "hot_products": ["final_prediction", "dissertation", "guaranteed"],
        "messaging_angle": "期末季来了，保分/保过需求爆发，转化最高的月份",
        "urgency": "极高",
    },
    5: {
        "uk":  "英国期末考试月（5月主考季），Dissertation最终提交",
        "au":  "澳洲T1期末考试+Dissertation提交",
        "us":  "美国Final月，5月毕业季",
        "hot_products": ["final_prediction", "guaranteed", "dissertation"],
        "messaging_angle": "全年最高转化月，Final押题/保过/毕业论文三箭齐发",
        "urgency": "极高",
    },
    6: {
        "uk":  "英国期末考试收尾，等成绩期，补考备考",
        "au":  "澳洲T1结束，T2开始（7月），暑假期",
        "us":  "暑假开始，部分学生申研/申请实习",
        "hot_products": ["final_prediction", "regular", "guaranteed"],
        "messaging_angle": "期末尾声 + 补考保底，同时高考结束→新客户（国内家长咨询）开始涌入",
        "urgency": "中高",
        "special_note": "6月高考结束，国内家长/高三学生开始了解留学，是新客户获取黄金期",
    },
    7: {
        "uk":  "暑假，等成绩期，补考（Resit）备考",
        "au":  "澳洲T2开始（7月），新学期首月",
        "us":  "暑假，暑期课选修",
        "hot_products": ["final_prediction", "annual_package", "regular"],
        "messaging_angle": "暑期备考 + 新学期学年包布局，双线并行",
        "urgency": "中",
        "special_note": "暑期是签新学年包的好时机，学生有时间规划，家长也有精力",
    },
    8: {
        "uk":  "英国成绩放榜（8月A-level/本科），9月开学倒计时",
        "au":  "澳洲T2中期，作业开始积压",
        "us":  "暑假尾声，秋季学期准备",
        "hot_products": ["annual_package", "regular", "final_prediction"],
        "messaging_angle": "开学前焦虑期，提前锁定学年包，强调'早规划早省心'",
        "urgency": "中高",
        "special_note": "英国8月成绩放榜，确认入学的学生马上要开学，是学年包成交黄金窗口",
    },
    9: {
        "uk":  "英国9月开学，新学期第一个月，作业开始布置",
        "au":  "澳洲T2期末备考开始（10-11月）",
        "us":  "秋季学期开始，选课完毕",
        "hot_products": ["annual_package", "regular"],
        "messaging_angle": "新学期开局，学年包转化率最高的窗口之一",
        "urgency": "高",
    },
    10: {
        "uk":  "英国第一个作业大月，Essay/Lab Report集中",
        "au":  "澳洲T2期末考试月（10-11月），Dissertation提交",
        "us":  "美国秋季学期中期，Midterm高峰",
        "hot_products": ["regular", "final_prediction", "dissertation"],
        "messaging_angle": "作业/考试双压力，即时单量高峰",
        "urgency": "高",
    },
    11: {
        "uk":  "英国第二波作业高峰，部分学校11月期末考",
        "au":  "澳洲T2期末考试+Dissertation最终提交，全年最忙",
        "us":  "美国期末备考开始，感恩节前冲刺",
        "hot_products": ["final_prediction", "guaranteed", "dissertation"],
        "messaging_angle": "全年第二高转化月，Final押题+保过+毕业论文齐爆发",
        "urgency": "极高",
    },
    12: {
        "uk":  "英国圣诞前作业冲刺，1月考试备考",
        "au":  "澳洲暑假开始，等成绩期",
        "us":  "美国期末考试+圣诞假期",
        "hot_products": ["regular", "final_prediction", "guaranteed"],
        "messaging_angle": "圣诞前最后冲刺，帮学生'年前交差'",
        "urgency": "中高",
    },
}

# ─────────────────────────────────────────────────────────────────────
# 按周细化（当月第几周）— 覆盖关键转折节点
# ─────────────────────────────────────────────────────────────────────

WEEKLY_TRIGGERS = {
    # (月, 周序1-4): 触发事件 + 优先建议
    (4, 3): {
        "trigger": "英国/澳洲期末考试进入倒计时30天",
        "action": "立即推Final押题，发'还有30天期末，你准备好了吗'内容",
        "target_student": "英国/澳洲在读，有期末考的学生",
    },
    (5, 1): {
        "trigger": "英国5月考试季开始，最高需求期",
        "action": "全力推Final押题+保过，顾问主动联系所有已询价未成交线索",
        "target_student": "英国在读，本科/研究生有期末考试",
    },
    (6, 2): {
        "trigger": "高考结束，国内新客户开始咨询留学",
        "action": "切换话题到'留学第一步怎么规划'，推广部布局小红书/垂直号内容",
        "target_student": "高三毕业生+家长，未来英澳美留学意向",
    },
    (8, 3): {
        "trigger": "英国A-level/本科成绩放榜",
        "action": "推'开学前规划'内容，主攻学年包成交，话术切入点：'成绩出来了，开学规划做了吗'",
        "target_student": "英国新生，即将9月入学",
    },
    (9, 1): {
        "trigger": "英国9月开学，学年包成交黄金窗口",
        "action": "顾问电话/微信主动跟进所有英国在读线索，学年包促单",
        "target_student": "英国在读，刚开学1-2周内",
    },
    (11, 2): {
        "trigger": "澳洲T2期末+英国11月考试，双高峰",
        "action": "双线推押题+保过，区分英国/澳洲话术",
        "target_student": "英国/澳洲在读，有期末考或论文",
    },
}

# ─────────────────────────────────────────────────────────────────────
# 渠道 × 学生阶段 最佳内容方向
# ─────────────────────────────────────────────────────────────────────

CHANNEL_CONTENT_GUIDE = {
    "xiaohongshu": {
        "best_content_types": ["亲历测评（押题效果）", "经验帖（这门课怎么过）", "避坑贴（留学常见失误）"],
        "tone": "真实、第一人称、带情绪共鸣，不像广告",
        "post_timing": "周二/周四/周日，18:00-22:00",
        "max_words": 500,
    },
    "moments": {
        "best_content_types": ["成绩截图+简短感谢", "节日问候+软植入", "限时优惠通知"],
        "tone": "简短、真实、朋友圈感，不超过150字",
        "post_timing": "周一/周三/周五，9:00 或 20:00",
        "max_words": 150,
    },
    "community": {
        "best_content_types": ["实用攻略（DDL临近怎么复习）", "活动通知（免费押题讲座）", "互动问答"],
        "tone": "实用、服务感、鼓励互动，用问句引发回复",
        "post_timing": "每天 20:00-22:00",
        "max_words": 300,
    },
    "vertical_account": {
        "best_content_types": ["深度攻略（某学校某专业期末完全指南）", "数据报告（往年押题命中率）"],
        "tone": "专业、数据支撑、干货感强",
        "post_timing": "周二/周四，10:00-12:00",
        "max_words": 1500,
    },
}


# ─────────────────────────────────────────────────────────────────────
# 主函数：获取当前学生需求快照
# ─────────────────────────────────────────────────────────────────────

def get_current_student_phase(target_date: Optional[date] = None) -> dict:
    """
    返回指定日期（默认今天）的学生需求快照，供 Agent 注入 prompt 使用。
    """
    if target_date is None:
        target_date = date.today()

    month = target_date.month
    # 月内第几周（1-4）
    week_of_month = (target_date.day - 1) // 7 + 1

    phase = MONTHLY_STUDENT_PHASES.get(month, {})
    weekly = WEEKLY_TRIGGERS.get((month, week_of_month), {})

    hot_products = phase.get("hot_products", [])
    urgency = phase.get("urgency", "中")

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "month": month,
        "week_of_month": week_of_month,
        # 各国学生当前阶段
        "uk_phase":   phase.get("uk", ""),
        "au_phase":   phase.get("au", ""),
        "us_phase":   phase.get("us", ""),
        # 核心推广建议
        "hot_products":     hot_products,
        "messaging_angle":  phase.get("messaging_angle", ""),
        "urgency":          urgency,
        "special_note":     phase.get("special_note", ""),
        # 本周特殊触发节点
        "weekly_trigger":   weekly.get("trigger", ""),
        "weekly_action":    weekly.get("action", ""),
        "target_student":   weekly.get("target_student", ""),
        # 渠道内容指南
        "channel_guide":    CHANNEL_CONTENT_GUIDE,
        # 格式化文本（直接注入 prompt）
        "prompt_block": _format_prompt_block(phase, weekly, target_date),
    }


def _format_prompt_block(phase: dict, weekly: dict, target_date: date) -> str:
    month = target_date.month
    week_of_month = (target_date.day - 1) // 7 + 1
    urgency = phase.get("urgency", "中")
    urgency_emoji = {"极高": "🔴", "高": "🟠", "中高": "🟡", "中": "⚪"}.get(urgency, "⚪")

    lines = [
        f"## 🎓 学生需求周历（{target_date.strftime('%Y年%m月')} 第{week_of_month}周）",
        f"**需求紧迫度：{urgency_emoji} {urgency}**",
        "",
        "### 各国学生当前处于什么阶段",
        f"- 🇬🇧 英国：{phase.get('uk', '暂无数据')}",
        f"- 🇦🇺 澳洲：{phase.get('au', '暂无数据')}",
        f"- 🇺🇸 美国：{phase.get('us', '暂无数据')}",
        "",
        f"### 本月核心推广角度",
        f"{phase.get('messaging_angle', '')}",
        "",
        f"### 本周重点热推产品",
    ]

    product_name_map = {
        "final_prediction": "Final精准押题",
        "regular": "课业辅导（单次）",
        "dissertation": "毕业论文辅导",
        "guaranteed": "保过辅导",
        "annual_package": "学年包",
        "dp_premium": "DP旗舰版",
    }
    for pid in phase.get("hot_products", []):
        lines.append(f"  - {product_name_map.get(pid, pid)}")

    if weekly:
        lines += [
            "",
            f"### ⚡ 本周触发节点",
            f"**触发事件**：{weekly.get('trigger', '')}",
            f"**立即行动**：{weekly.get('action', '')}",
            f"**目标学生**：{weekly.get('target_student', '')}",
        ]

    if phase.get("special_note"):
        lines += ["", f"### 💡 特别注意", phase["special_note"]]

    lines += [
        "",
        "### 各渠道内容方向",
        "- **小红书**：真实体验帖、经验分享、情绪共鸣，不像广告 | 最佳发布：周二/周四/周日 18-22点",
        "- **朋友圈**：简短+截图，150字内，不超过2条/周 | 最佳发布：9点或20点",
        "- **社群**：实用攻略+互动问句，每晚20-22点 | 触发回复比单向推送效果好3倍",
        "- **垂直号**：深度攻略+数据，1000字+，发周二/周四上午",
    ]

    return "\n".join(lines)
