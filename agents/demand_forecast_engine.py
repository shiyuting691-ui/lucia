"""
需求预测引擎 — 三层数据融合，生成 DemandForecastSignal

三层体系：
  Layer 1 — SchoolAcademicCalendar  （学校级学期日历）
  Layer 2 — CourseAssessmentV2      （课程级 Assessment 到期数据）
  Layer 3 — MajorDemandProfile      （历史订单/线索提炼的专业需求画像）
  Layer 4 — get_lead_stats          （当前线索热度实时信号）

用法（CLI）：
  python agents/demand_forecast_engine.py --migrate        # 建表
  python agents/demand_forecast_engine.py --seed           # 种子数据（日历 + 课程）
  python agents/demand_forecast_engine.py --build-profiles # 从 CRM 构建专业画像
  python agents/demand_forecast_engine.py --forecast       # 生成预测信号
  python agents/demand_forecast_engine.py --all            # 依次执行全部步骤
"""

import sys
import os
import logging
from datetime import date, timedelta, datetime
from collections import defaultdict

# ── 路径修正，确保能 import database ──────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.crud import (
    list_orders, get_lead_stats,
    upsert_school_academic_calendar, list_school_academic_calendars,
    save_course_assessment_v2, list_course_assessments_v2,
    save_major_demand_profile, list_major_demand_profiles,
    save_demand_forecast_signal, clear_expired_forecast_signals,
    upsert_data_source, migrate_demand_tables,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 常量映射
# ─────────────────────────────────────────────────────────────────────────────

EVENT_TO_PRODUCTS = {
    "teaching_start":  ["annual_package", "regular"],
    "reading_week":    ["regular", "annual_package"],
    "exam_period":     ["final_prediction", "guaranteed"],
    "resit_exam":      ["guaranteed", "final_prediction"],
    "dissertation":    ["dissertation", "dp_premium", "ai_compliance"],
    "teaching_end":    ["regular", "final_prediction"],
    "assignment":      ["regular", "ai_compliance"],
    "quiz":            ["final_prediction", "regular"],
    "exam":            ["final_prediction", "guaranteed"],
    "project":         ["regular"],
    "presentation":    ["regular"],
}

MAJOR_PRODUCTS = {
    "商科":  ["regular", "final_prediction", "annual_package"],
    "CS/IT": ["regular", "final_prediction"],
    "法律":  ["regular", "dp_premium"],
    "心理":  ["regular"],
    "工程":  ["regular", "final_prediction"],
    "传媒":  ["regular", "dissertation"],
}

# 产品名称 → 专业类别 启发式映射
PRODUCT_TO_MAJOR = {
    "essay": "商科",
    "作业":  "商科",
    "cs":    "CS/IT",
    "it":    "CS/IT",
    "计算机": "CS/IT",
    "代码":  "CS/IT",
    "法律":  "法律",
    "law":   "法律",
    "心理":  "心理",
    "工程":  "工程",
    "传媒":  "传媒",
    "media": "传媒",
}

SOURCE_CONFIDENCE = {
    "official": 0.9,
    "scraped":  0.7,
    "pattern":  0.5,
    "manual":   0.8,
}

def _conf_label(score: float) -> str:
    if score >= 0.7: return "高"
    if score >= 0.4: return "中"
    return "低"


def _date_in_window(date_str: str, window_start: date, window_end: date) -> bool:
    """检查 'YYYY-MM-DD' 字符串是否落在 [window_start, window_end] 内"""
    if not date_str:
        return False
    try:
        d = date.fromisoformat(date_str[:10])
        return window_start <= d <= window_end
    except Exception:
        return False


def _days_until(date_str: str) -> int:
    """返回距离某日期的天数（负数表示已过期）"""
    if not date_str:
        return 9999
    try:
        d = date.fromisoformat(date_str[:10])
        return (d - date.today()).days
    except Exception:
        return 9999


# ─────────────────────────────────────────────────────────────────────────────
# Step 4：种子数据 — 学校学术日历（第一层）
# ─────────────────────────────────────────────────────────────────────────────

AU_SCHOOLS = [
    "新南威尔士大学", "悉尼大学", "墨尔本大学", "莫纳什大学Monash", "昆士兰大学",
]
UK_SCHOOLS = [
    "伦敦大学学院UCL", "伯明翰大学", "伦敦国王学院KCL", "利兹大学", "谢菲尔德大学",
    "曼彻斯特大学", "布里斯托大学", "华威大学", "杜伦大学", "格拉斯哥大学",
    "南安普敦大学", "爱丁堡大学", "约克大学", "诺丁汉大学", "雷丁大学",
    "伦敦玛丽女王大学Queen Mary", "纽卡斯尔大学",
]
HK_SCHOOLS = [
    "香港教育大学", "香港理工大学", "香港城市大学", "香港大学",
]

# 每学期模板 — 字段值按学校在列表中的索引微调 teaching_start，其余共享
AU_SEM1_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Semester 1",
    "term_start":                "2025-02-17",
    "term_end":                  "2025-06-21",
    "teaching_start":            "2025-02-17",   # 各校在 17-24 之间，统一用17
    "teaching_end":              "2025-05-30",
    "reading_week_start":        "2025-04-14",
    "reading_week_end":          "2025-04-18",
    "exam_period_start":         "2025-06-02",
    "exam_period_end":           "2025-06-21",
    "resit_exam_start":          None,
    "resit_exam_end":            None,
    "dissertation_deadline_start": None,
    "dissertation_deadline_end": None,
    "source_type":               "pattern",
    "confidence_score":          0.6,
}

AU_SEM2_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Semester 2",
    "term_start":                "2025-07-14",
    "term_end":                  "2025-11-15",
    "teaching_start":            "2025-07-14",
    "teaching_end":              "2025-10-24",
    "reading_week_start":        "2025-09-08",
    "reading_week_end":          "2025-09-12",
    "exam_period_start":         "2025-10-27",
    "exam_period_end":           "2025-11-15",
    "resit_exam_start":          "2026-01-12",
    "resit_exam_end":            "2026-01-23",
    "dissertation_deadline_start": None,
    "dissertation_deadline_end": None,
    "source_type":               "pattern",
    "confidence_score":          0.6,
}

UK_AUTUMN_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Autumn Term",
    "term_start":                "2025-09-22",
    "term_end":                  "2026-01-23",
    "teaching_start":            "2025-09-22",
    "teaching_end":              "2025-12-12",
    "reading_week_start":        "2025-11-03",
    "reading_week_end":          "2025-11-07",
    "exam_period_start":         "2026-01-05",
    "exam_period_end":           "2026-01-23",
    "resit_exam_start":          None,
    "resit_exam_end":            None,
    "dissertation_deadline_start": "2026-09-01",
    "dissertation_deadline_end": "2026-09-30",
    "source_type":               "pattern",
    "confidence_score":          0.6,
}

UK_SPRING_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Spring Term",
    "term_start":                "2026-01-12",
    "term_end":                  "2026-06-19",
    "teaching_start":            "2026-01-12",
    "teaching_end":              "2026-03-20",
    "reading_week_start":        "2026-02-16",
    "reading_week_end":          "2026-02-20",
    "exam_period_start":         "2026-05-11",
    "exam_period_end":           "2026-06-19",
    "resit_exam_start":          "2026-08-17",
    "resit_exam_end":            "2026-08-28",
    "dissertation_deadline_start": "2026-09-01",
    "dissertation_deadline_end": "2026-09-30",
    "source_type":               "pattern",
    "confidence_score":          0.6,
}

HK_SEM1_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Semester 1",
    "term_start":                "2025-09-01",
    "term_end":                  "2025-12-31",
    "teaching_start":            "2025-09-01",
    "teaching_end":              "2025-12-05",
    "reading_week_start":        None,
    "reading_week_end":          None,
    "exam_period_start":         "2025-12-15",
    "exam_period_end":           "2025-12-31",
    "resit_exam_start":          None,
    "resit_exam_end":            None,
    "dissertation_deadline_start": None,
    "dissertation_deadline_end": None,
    "source_type":               "pattern",
    "confidence_score":          0.55,
}

HK_SEM2_TEMPLATE = {
    "academic_year":             "2025-2026",
    "semester":                  "Semester 2",
    "term_start":                "2026-01-12",
    "term_end":                  "2026-05-08",
    "teaching_start":            "2026-01-12",
    "teaching_end":              "2026-04-10",
    "reading_week_start":        None,
    "reading_week_end":          None,
    "exam_period_start":         "2026-04-20",
    "exam_period_end":           "2026-05-08",
    "resit_exam_start":          None,
    "resit_exam_end":            None,
    "dissertation_deadline_start": None,
    "dissertation_deadline_end": None,
    "source_type":               "pattern",
    "confidence_score":          0.55,
}


def seed_school_academic_calendars() -> int:
    """向 school_academic_calendars 表写入26所学校的2025-2026学期数据。返回总插入行数。"""
    count = 0
    school_groups = [
        (AU_SCHOOLS, "AU", [AU_SEM1_TEMPLATE, AU_SEM2_TEMPLATE]),
        (UK_SCHOOLS, "UK", [UK_AUTUMN_TEMPLATE, UK_SPRING_TEMPLATE]),
        (HK_SCHOOLS, "HK", [HK_SEM1_TEMPLATE, HK_SEM2_TEMPLATE]),
    ]
    for schools, country, templates in school_groups:
        for school in schools:
            for tmpl in templates:
                data = dict(tmpl)
                data["school"]  = school
                data["country"] = country
                upsert_school_academic_calendar(data)
                count += 1
                # 注册数据源
                upsert_data_source({
                    "source_name":    f"{school}_{data['semester']}_calendar",
                    "source_type":    "academic_calendar",
                    "school":         school,
                    "country":        country,
                    "scrape_success": True,
                    "record_count":   1,
                    "confidence_score": data["confidence_score"],
                    "scrape_method":  "pattern",
                    "last_scraped":   datetime.utcnow(),
                    "last_success":   datetime.utcnow(),
                })
    log.info(f"[seed_calendars] 写入 {count} 条学术日历记录")
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Step 5：种子数据 — 课程级 Assessment（第二层）
# ─────────────────────────────────────────────────────────────────────────────

# 每所学校 × 每个专业 生成典型 Assignment 模式
_ASSESSMENT_PATTERNS = [
    # (assessment_type, assessment_name, due_week, weight, suitable_products)
    ("assignment", "Assignment 1",    "Week 5",  25.0, ["regular"]),
    ("assignment", "Assignment 2",    "Week 9",  25.0, ["regular", "ai_compliance"]),
    ("exam",       "Mid-term Exam",   "Week 7",  20.0, ["final_prediction"]),
    ("exam",       "Final Exam",      "Week 13", 40.0, ["final_prediction", "guaranteed"]),
    ("quiz",       "Weekly Quiz",     "Week 4",  10.0, ["final_prediction", "regular"]),
    ("project",    "Group Project",   "Week 11", 30.0, ["regular"]),
]


def seed_course_assessments_v2() -> int:
    """向 course_assessments_v2 写入各学校×专业的 Assessment 模式数据。"""
    count = 0
    all_schools = (
        [(s, "AU") for s in AU_SCHOOLS] +
        [(s, "UK") for s in UK_SCHOOLS] +
        [(s, "HK") for s in HK_SCHOOLS]
    )
    semester_map = {
        "AU": "Semester 1",
        "UK": "Autumn Term",
        "HK": "Semester 1",
    }
    for school, country in all_schools:
        for major_cat, products in MAJOR_PRODUCTS.items():
            for (atype, aname, due_week, weight, suitable) in _ASSESSMENT_PATTERNS:
                # 过滤不适合该专业的考核类型
                if atype == "exam" and major_cat in ("传媒",):
                    continue
                data = {
                    "school":             school,
                    "country":            country,
                    "major_category":     major_cat,
                    "subject_code":       f"{major_cat[:2].upper()}001",
                    "subject_name":       f"{major_cat}核心课程",
                    "semester":           semester_map.get(country, "Semester 1"),
                    "academic_year":      "2025-2026",
                    "assessment_type":    atype,
                    "assessment_name":    aname,
                    "assessment_weight":  weight,
                    "due_week":           due_week,
                    "due_date_if_public": None,
                    "final_exam_yes_no":  atype == "exam" and "Final" in aname,
                    "presentation_yes_no": atype == "presentation",
                    "group_work_yes_no":  "Group" in aname,
                    "suitable_products":  suitable,
                    "source_type":        "pattern",
                    "confidence_score":   0.5,
                    "notes":              "模式推断，非官方数据",
                }
                save_course_assessment_v2(data)
                count += 1
    log.info(f"[seed_assessments_v2] 写入 {count} 条课程考核记录")
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Step 6：从 CRM 数据构建专业需求画像（第三层）
# ─────────────────────────────────────────────────────────────────────────────

def _infer_major(product_name: str, major_name: str = "") -> str:
    """从产品/专业名称推断 major_category"""
    text = (product_name + " " + major_name).lower()
    for kw, cat in PRODUCT_TO_MAJOR.items():
        if kw in text:
            return cat
    return "商科"   # 默认回退


def build_demand_profiles_from_crm() -> int:
    """从历史订单构建 MajorDemandProfile，返回写入条数。"""
    orders = list_orders(days=365, limit=5000)
    if not orders:
        log.warning("[build_profiles] 无历史订单数据，跳过")
        return 0

    # 聚合: (school, major_category, product_type) -> {月份计数, 金额, 渠道}
    agg: dict = {}   # key -> {"months": Counter, "amounts": [], "channels": Counter}

    for o in orders:
        school   = (o.get("school") or "").strip()
        product  = (o.get("product") or "").strip()
        major    = (o.get("major") or "").strip()
        amount   = float(o.get("amount") or 0)
        channel  = (o.get("sales_owner") or "顾问")

        if not school or not product:
            continue

        major_cat = _infer_major(product, major)
        key = (school, major_cat, product)

        if key not in agg:
            agg[key] = {
                "months": defaultdict(int),
                "amounts": [],
                "channels": defaultdict(int),
            }

        # 解析订单月份
        order_date_str = o.get("order_date") or ""
        if order_date_str:
            try:
                m = int(order_date_str[5:7])
                agg[key]["months"][m] += 1
            except Exception:
                pass
        agg[key]["amounts"].append(amount)
        agg[key]["channels"][channel] += 1

    count = 0
    for (school, major_cat, product_type), stats in agg.items():
        months = stats["months"]
        amounts = stats["amounts"]
        channels = stats["channels"]

        peak_month    = max(months, key=months.get) if months else None
        total_orders  = sum(months.values())
        avg_value     = round(sum(amounts) / len(amounts), 2) if amounts else 0
        primary_chan  = max(channels, key=channels.get) if channels else None
        avg_peak_orders = months.get(peak_month, 0) if peak_month else 0

        save_major_demand_profile({
            "school":           school,
            "major_category":   major_cat,
            "product_type":     product_type,
            "peak_month":       peak_month,
            "avg_orders_peak":  avg_peak_orders,
            "avg_order_value":  avg_value,
            "primary_channel":  primary_chan,
            "total_orders":     total_orders,
            "total_revenue":    sum(amounts),
            "data_period_start": (date.today() - timedelta(days=365)).isoformat(),
            "data_period_end":   date.today().isoformat(),
            "last_computed":     datetime.utcnow(),
        })
        count += 1

    log.info(f"[build_profiles] 构建 {count} 条专业需求画像")
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Step 2：生成预测信号
# ─────────────────────────────────────────────────────────────────────────────

def _compute_signal_strength(
    calendar_hit: bool,
    assessment_hit: bool,
    history_hit: bool,
    lead_heat_high: bool,
    base_confidence: float,
) -> tuple:
    """返回 (signal_strength, confidence_score)"""
    # calendar(0.4) + historical_demand(0.4) + lead_heat(0.2)
    cal_score  = 0.4 if calendar_hit  else 0.0
    hist_score = 0.4 if history_hit   else 0.0
    heat_score = 0.2 if lead_heat_high else 0.0
    signal = round(cal_score + hist_score + heat_score, 3)

    # confidence
    conf = base_confidence
    if history_hit:   conf = min(conf + 0.1, 1.0)
    if lead_heat_high: conf = min(conf + 0.1, 1.0)
    if assessment_hit: conf = min(conf + 0.05, 1.0)
    conf = round(conf, 3)
    return signal, conf


def _build_triggered_by(calendar_hit, assessment_hit, history_hit, lead_heat_high) -> str:
    parts = []
    if calendar_hit:    parts.append("calendar")
    if assessment_hit:  parts.append("assessment")
    if history_hit:     parts.append("history")
    if lead_heat_high:  parts.append("lead_heat")
    return "+".join(parts) if parts else "pattern"


def _make_promo_action(school: str, major_cat: str, product: str, event_label: str) -> str:
    return (f"小红书/社群发布{school}{major_cat}{event_label}攻略，"
            f"重点推{product}服务")


def _make_sales_action(school: str, major_cat: str, product: str, days: int) -> str:
    return (f"主动联系近{days}天咨询过{school}{major_cat}的线索，"
            f"话术重点：即将到来的考核/截止日期，推荐{product}")


def run_forecast(time_windows: list = None) -> int:
    """
    综合四层数据生成 DemandForecastSignal 记录。
    time_windows: 要生成的时间窗口列表（天数），默认 [7, 14, 30, 60]
    返回写入信号总数。
    """
    if time_windows is None:
        time_windows = [7, 14, 30, 60]

    today = date.today()

    # 清理过期信号
    clear_expired_forecast_signals()

    # ── 获取数据 ──────────────────────────────────────────────────────────────
    calendars  = list_school_academic_calendars(limit=1000)
    assessments = list_course_assessments_v2(limit=2000)
    profiles    = list_major_demand_profiles(limit=2000)
    lead_stats  = get_lead_stats(days=14)

    # 当前线索热度判断
    total_leads_14d    = lead_stats.get("total", 0)
    lead_heat_high     = total_leads_14d >= 20   # 近14天线索>=20视为高热度

    # 按学校索引线索热度（top学校）
    hot_schools = set()
    for sch, cnt in (lead_stats.get("by_school") or [])[:5]:
        if cnt >= 3:
            hot_schools.add(sch)

    # 按 school 索引历史画像
    profile_index: dict = {}   # (school, major_cat, product) -> profile
    for p in profiles:
        key = (p.get("school"), p.get("major_category"), p.get("product_type"))
        profile_index[key] = p

    signals_written = 0

    for window_days in time_windows:
        window_start = today
        window_end   = today + timedelta(days=window_days)
        ws = window_start.isoformat()
        we = window_end.isoformat()
        expires_at = we

        # ── Layer 1: 学术日历触发 ─────────────────────────────────────────────
        for cal in calendars:
            school  = cal.get("school", "")
            country = cal.get("country", "")
            sem     = cal.get("semester", "")
            src_type = cal.get("source_type", "pattern")
            base_conf = SOURCE_CONFIDENCE.get(src_type, 0.5)

            # 检查各关键节点是否落在窗口内
            event_hits = []
            if _date_in_window(cal.get("exam_period_start"), window_start, window_end):
                event_hits.append(("exam_period", "final_prediction", "期末考试季"))
            if _date_in_window(cal.get("reading_week_start"), window_start, window_end):
                event_hits.append(("reading_week", "regular", "Reading Week"))
            if _date_in_window(cal.get("resit_exam_start"), window_start, window_end):
                event_hits.append(("resit_exam", "guaranteed", "补考季"))
            if _date_in_window(cal.get("dissertation_deadline_start"), window_start, window_end):
                event_hits.append(("dissertation", "dissertation", "论文提交季"))
            if _date_in_window(cal.get("teaching_start"), window_start, window_end):
                event_hits.append(("teaching_start", "annual_package", "开学季"))

            for event_key, primary_product, event_label in event_hits:
                products = EVENT_TO_PRODUCTS.get(event_key, [primary_product])
                for product in products:
                    # 推断 major_category
                    major_cats = list(MAJOR_PRODUCTS.keys())
                    for major_cat in major_cats:
                        history_hit = (school, major_cat, product) in profile_index
                        sch_lead_hot = school in hot_schools
                        signal, conf = _compute_signal_strength(
                            calendar_hit=True,
                            assessment_hit=False,
                            history_hit=history_hit,
                            lead_heat_high=sch_lead_hot,
                            base_confidence=base_conf,
                        )
                        if signal < 0.3:
                            continue   # 信号太弱，跳过

                        profile = profile_index.get((school, major_cat, product))
                        reason_parts = [
                            f"{sem} {event_label}即将到来（{cal.get(event_key + '_start', '')}）",
                        ]
                        if profile:
                            reason_parts.append(
                                f"历史数据：{school}{major_cat}共{profile['total_orders']}笔订单，"
                                f"峰值月份为{profile['peak_month']}月"
                            )
                        data_sources = ["school_academic_calendars"]
                        if history_hit:
                            data_sources.append("major_demand_profiles")
                        if sch_lead_hot:
                            data_sources.append("lead_heat")

                        save_demand_forecast_signal({
                            "school":           school,
                            "major_category":   major_cat,
                            "product":          product,
                            "country":          country,
                            "time_window_days": window_days,
                            "window_start":     ws,
                            "window_end":       we,
                            "signal_strength":  signal,
                            "confidence_score": conf,
                            "confidence_label": _conf_label(conf),
                            "forecast_reason":  "；".join(reason_parts),
                            "data_sources":     data_sources,
                            "promo_action":     _make_promo_action(school, major_cat, product, event_label),
                            "sales_action":     _make_sales_action(school, major_cat, product, window_days),
                            "triggered_by":     _build_triggered_by(True, False, history_hit, sch_lead_hot),
                            "expires_at":       expires_at,
                        })
                        signals_written += 1

        # ── Layer 2: 课程考核到期触发 ─────────────────────────────────────────
        for assess in assessments:
            due_date = assess.get("due_date_if_public")
            if not due_date:
                continue
            if not _date_in_window(due_date, window_start, window_end):
                continue

            school      = assess.get("school", "")
            country     = assess.get("country", "")
            major_cat   = assess.get("major_category", "商科")
            atype       = assess.get("assessment_type", "assignment")
            aname       = assess.get("assessment_name", "")
            suitable    = assess.get("suitable_products") or EVENT_TO_PRODUCTS.get(atype, ["regular"])
            src_type    = assess.get("source_type", "pattern")
            base_conf   = SOURCE_CONFIDENCE.get(src_type, 0.5)

            for product in (suitable if isinstance(suitable, list) else [suitable]):
                history_hit  = (school, major_cat, product) in profile_index
                sch_lead_hot = school in hot_schools
                signal, conf = _compute_signal_strength(
                    calendar_hit=False,
                    assessment_hit=True,
                    history_hit=history_hit,
                    lead_heat_high=sch_lead_hot,
                    base_confidence=base_conf,
                )
                if signal < 0.2:
                    continue

                reason = f"课程考核 {aname} 截止日期：{due_date}，适合推广 {product}"
                data_sources = ["course_assessments_v2"]
                if history_hit:
                    data_sources.append("major_demand_profiles")

                save_demand_forecast_signal({
                    "school":           school,
                    "major_category":   major_cat,
                    "product":          product,
                    "country":          country,
                    "time_window_days": window_days,
                    "window_start":     ws,
                    "window_end":       we,
                    "signal_strength":  signal,
                    "confidence_score": conf,
                    "confidence_label": _conf_label(conf),
                    "forecast_reason":  reason,
                    "data_sources":     data_sources,
                    "promo_action":     _make_promo_action(school, major_cat, product, aname),
                    "sales_action":     _make_sales_action(school, major_cat, product, window_days),
                    "triggered_by":     _build_triggered_by(False, True, history_hit, sch_lead_hot),
                    "expires_at":       expires_at,
                })
                signals_written += 1

        # ── Layer 3: 历史峰值月份触发 ─────────────────────────────────────────
        current_month = today.month
        window_months = set()
        d = window_start
        while d <= window_end:
            window_months.add(d.month)
            d += timedelta(days=15)

        for profile in profiles:
            peak_month = profile.get("peak_month")
            if not peak_month or peak_month not in window_months:
                continue

            school     = profile.get("school", "")
            major_cat  = profile.get("major_category", "")
            product    = profile.get("product_type", "")
            country    = profile.get("country", "")
            if not school or not product:
                continue

            sch_lead_hot = school in hot_schools
            signal, conf = _compute_signal_strength(
                calendar_hit=False,
                assessment_hit=False,
                history_hit=True,
                lead_heat_high=sch_lead_hot,
                base_confidence=0.5,
            )

            reason = (
                f"历史数据：{school}{major_cat} {product} 在 {peak_month} 月为全年需求峰值，"
                f"共 {profile.get('total_orders', 0)} 笔历史订单"
            )
            save_demand_forecast_signal({
                "school":           school,
                "major_category":   major_cat,
                "product":          product,
                "country":          country,
                "time_window_days": window_days,
                "window_start":     ws,
                "window_end":       we,
                "signal_strength":  signal,
                "confidence_score": conf,
                "confidence_label": _conf_label(conf),
                "forecast_reason":  reason,
                "data_sources":     ["major_demand_profiles"],
                "promo_action":     _make_promo_action(school, major_cat, product, f"{peak_month}月高峰期"),
                "sales_action":     _make_sales_action(school, major_cat, product, window_days),
                "triggered_by":     _build_triggered_by(False, False, True, sch_lead_hot),
                "expires_at":       expires_at,
            })
            signals_written += 1

    log.info(f"[run_forecast] 生成 {signals_written} 条预测信号")
    return signals_written


# ─────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="需求预测引擎")
    parser.add_argument("--migrate",       action="store_true", help="创建新表（幂等）")
    parser.add_argument("--seed",          action="store_true", help="写入种子数据（日历 + 课程考核）")
    parser.add_argument("--build-profiles",action="store_true", help="从 CRM 构建专业需求画像")
    parser.add_argument("--forecast",      action="store_true", help="生成需求预测信号")
    parser.add_argument("--all",           action="store_true", help="依次执行全部步骤")
    parser.add_argument("--windows",       nargs="+", type=int, default=[7, 14, 30, 60],
                        help="预测窗口天数列表，默认 7 14 30 60")
    args = parser.parse_args()

    do_all = args.all

    if args.migrate or do_all:
        log.info("=== Step 1: migrate tables ===")
        migrate_demand_tables()
        log.info("表创建完成")

    if args.seed or do_all:
        log.info("=== Step 2: seed academic calendars (Tier 1) ===")
        n = seed_school_academic_calendars()
        log.info(f"学术日历：{n} 条")

        log.info("=== Step 3: seed course assessments v2 (Tier 2) ===")
        n = seed_course_assessments_v2()
        log.info(f"课程考核：{n} 条")

    if getattr(args, "build_profiles", False) or do_all:
        log.info("=== Step 4: build demand profiles from CRM (Tier 3) ===")
        n = build_demand_profiles_from_crm()
        log.info(f"专业需求画像：{n} 条")

    if args.forecast or do_all:
        log.info(f"=== Step 5: run forecast (windows={args.windows}) ===")
        n = run_forecast(time_windows=args.windows)
        log.info(f"预测信号：{n} 条")

    if not any([args.migrate, args.seed, getattr(args, "build_profiles", False),
                args.forecast, do_all]):
        parser.print_help()
