"""
TimeWindowForecastAgent — 时间窗口需求预测 v2（Phase 2 v2）

5个时间窗口：0-7天 / 8-14天 / 15-21天 / 22-30天 / 31-60天
为每个窗口×国家×产品生成预测，并保存结构化 role_actions_json。
纯本地计算，不调 LLM。
"""
import json
import logging
from datetime import datetime, timedelta, date
from database import (
    list_orders, list_leads, list_school_calendar, list_yearly_patterns,
    list_teacher_capacity, save_time_window_forecast_v2,
)

logger = logging.getLogger(__name__)

WINDOWS = [
    ("0-7天",   "本周",   0,  7),
    ("8-14天",  "下周",   8, 14),
    ("15-21天", "半月后", 15, 21),
    ("22-30天", "月底",   22, 30),
    ("31-60天", "下月",   31, 60),
]

COUNTRY_PHASES = {
    "UK": {
        1:  ("寒假复习期", 0.6),
        2:  ("春季冲刺期", 0.9),
        3:  ("考试倒计时", 1.0),
        4:  ("暑期申请季", 0.7),
        5:  ("暑期申请季", 0.7),
        6:  ("开学准备期", 0.5),
        7:  ("秋季冲刺期", 0.8),
        8:  ("秋季冲刺期", 0.9),
        9:  ("秋季考试季", 1.0),
        10: ("考试后复盘", 0.6),
        11: ("来年预判期", 0.5),
        12: ("年底冲刺",   0.8),
    },
    "AU": {
        1:  ("暑假期间",       0.4),
        2:  ("开学季",         0.8),
        3:  ("秋季学期",       0.8),
        4:  ("期中考试",       0.9),
        5:  ("冲刺期",         1.0),
        6:  ("期末冲刺",       1.0),
        7:  ("寒假/下学期准备", 0.6),
        8:  ("春季学期",       0.8),
        9:  ("期中考试",       0.9),
        10: ("冲刺期",         1.0),
        11: ("期末冲刺",       1.0),
        12: ("暑假/毕业季",    0.5),
    },
}

PRODUCTS = [
    ("final_prediction", "Final考前冲刺规划"),
    ("dissertation",     "毕业论文辅导"),
    ("regular",          "课业辅导"),
    ("guaranteed",       "保过辅导"),
]

WINDOW_CONFIDENCE = {
    "0-7天": "high", "8-14天": "high",
    "15-21天": "medium", "22-30天": "medium", "31-60天": "low",
}

WINDOW_DECAY = {
    "0-7天": 1.0, "8-14天": 0.9, "15-21天": 0.8, "22-30天": 0.75, "31-60天": 0.6,
}

PRIORITY_MAP = {
    "0-7天": 1, "8-14天": 2, "15-21天": 3, "22-30天": 4, "31-60天": 5,
}


class TimeWindowForecastAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}

    def run(self) -> list:
        today = datetime.now().strftime("%Y-%m-%d")
        today_dt = datetime.now().date()

        logger.info(f"[TimeWindowForecast v2] generating forecasts for {today}")

        try:
            recent_leads  = list_leads(days=30, limit=2000)
            recent_orders = list_orders(days=30, limit=2000)
        except Exception as e:
            logger.warning(f"[TimeWindowForecast] DB read error: {e}")
            recent_leads, recent_orders = [], []

        daily_leads_base  = len(recent_leads) / 30
        daily_orders_base = len(recent_orders) / 30

        # 从真实订单中提取 country×product 有效组合及需求比例
        country_product_stats = {}
        for order in recent_orders:
            c = (order.get("country") or "").strip().upper()
            p = order.get("product") or ""
            if not c or not p:
                continue
            pid = self._map_product_id(p)
            if pid:
                key = (c, pid)
                country_product_stats[key] = country_product_stats.get(key, 0) + 1

        # 如果数据库还没有country数据，退回到学术日历驱动的默认组合
        if not country_product_stats:
            logger.warning("[TimeWindowForecast] no country data in orders, using calendar defaults")
            country_product_stats = {
                ("UK", "dissertation"): 10,
                ("UK", "final_prediction"): 15,
                ("UK", "regular"): 20,
                ("AU", "final_prediction"): 12,
                ("AU", "regular"): 15,
            }

        # 按国家汇总：每个国家的总订单数（用于计算各产品占比）
        country_totals = {}
        for (c, p), cnt in country_product_stats.items():
            country_totals[c] = country_totals.get(c, 0) + cnt

        try:
            patterns  = list_yearly_patterns()
        except Exception:
            patterns = []
        try:
            calendars = list_school_calendar(days_ahead=90)
        except Exception:
            calendars = []
        try:
            capacities = list_teacher_capacity()
        except Exception:
            capacities = []

        # teacher_capacity 没有 product_id 字段，按 subject_area 关键词反查 product_id
        from services.product_catalog_service import ProductCatalogService
        _subject_to_pid = {}
        for p in ProductCatalogService.load_active_products():
            for kw in p.get("capacity_subject_keywords", []):
                _subject_to_pid[kw] = p["canonical_product_id"]
        cap_map = {}
        for c in capacities:
            if c.get("available_slots") is None:
                continue
            sa = str(c.get("subject_area", "")).lower()
            ct = str(c.get("course_type", "")).lower()
            for kw, pid in _subject_to_pid.items():
                if kw in sa or kw in ct:
                    cap_map[pid] = cap_map.get(pid, 0) + (c.get("available_slots") or 0)
                    break

        results = []
        for window_key, window_label, days_from, days_to in WINDOWS:
            window_start = today_dt + timedelta(days=days_from)
            window_end   = today_dt + timedelta(days=days_to)
            month = window_start.month

            # 只生成有真实数据支撑的 country×product 组合
            for (country, product_id) in country_product_stats.keys():
                product_name = self._PRODUCT_NAMES.get(product_id, product_id)
                phase_name, demand_multiplier = self._get_phase(country, month)

                if True:  # 保持缩进层级一致
                    base_score = min(100, daily_leads_base * demand_multiplier * 10)
                    hist_boost = self._calc_hist_boost(patterns, country, product_id, month)
                    base_score = min(100, base_score * (1 + hist_boost))

                    cal_boost, key_events, cal_notes = self._calc_calendar_boost(
                        calendars, window_start, window_end, country
                    )
                    base_score = min(100, base_score * (1 + cal_boost))
                    base_score *= WINDOW_DECAY.get(window_key, 1.0)

                    urgency = "低"
                    if base_score >= 70:
                        urgency = "极高"
                    elif base_score >= 50:
                        urgency = "高"
                    elif base_score >= 30:
                        urgency = "中"

                    span_days = days_to - days_from + 1
                    predicted_leads  = max(0, int(daily_leads_base * demand_multiplier * span_days))
                    predicted_orders = max(0, int(daily_orders_base * demand_multiplier * span_days * 0.3))

                    avail = cap_map.get(product_id)
                    if avail is not None and avail < predicted_orders:
                        predicted_orders = avail

                    missing_data = []
                    if daily_leads_base == 0:
                        missing_data.append("近30天线索数据")
                    if daily_orders_base == 0:
                        missing_data.append("近30天订单数据")
                    if product_id not in cap_map:
                        missing_data.append(f"{product_name}老师容量")

                    role_actions = self._build_role_actions(
                        window_key, window_label, country, product_id, product_name,
                        phase_name, urgency, key_events, predicted_leads, predicted_orders,
                        today_dt, days_to
                    )

                    recommended_channels = self._recommend_channels(urgency, window_key)

                    data_evidence = (
                        f"近30天日均线索{daily_leads_base:.1f}条，日均订单{daily_orders_base:.1f}单；"
                        f"{country}当前学期阶段：{phase_name}（需求系数{demand_multiplier}）；"
                        f"历史同期boost={hist_boost:.2f}，日历boost={cal_boost:.2f}"
                    )

                    row = {
                        "forecast_date":       today,
                        "window":              window_key,
                        "window_label":        window_label,
                        "school_name":         "",
                        "product_id":          product_id,
                        "product_name":        product_name,
                        "country":             country,
                        "urgency":             urgency,
                        "demand_score":        round(base_score, 1),
                        "predicted_leads":     predicted_leads,
                        "predicted_orders":    predicted_orders,
                        "key_events":          key_events,
                        "confidence":          WINDOW_CONFIDENCE.get(window_key, "medium"),
                        "recommended_channels": recommended_channels,
                        "role_actions_json":   json.dumps(role_actions, ensure_ascii=False),
                        "calendar_note_json":  json.dumps(cal_notes, ensure_ascii=False),
                        "reason":              f"{country}{phase_name}，需求{urgency}，预估{predicted_leads}条线索",
                        "data_evidence":       data_evidence,
                        "risk_note":           "；".join(missing_data) if missing_data else "",
                        "missing_data":        json.dumps(missing_data, ensure_ascii=False),
                        "priority":            PRIORITY_MAP.get(window_key, 5),
                        "basis": {
                            "phase":             phase_name,
                            "demand_multiplier": demand_multiplier,
                            "hist_boost":        round(hist_boost, 2),
                            "cal_boost":         round(cal_boost, 2),
                            "daily_leads_base":  round(daily_leads_base, 1),
                        },
                    }

                    try:
                        save_time_window_forecast_v2(row)
                    except Exception as e:
                        logger.warning(f"[TimeWindowForecast] save failed: {e}")

                    results.append(row)

        logger.info(f"[TimeWindowForecast v2] generated {len(results)} forecasts")
        return results

    _PRODUCT_ID_MAP = {
        "dissertation": "dissertation",
        "论文": "dissertation",
        "毕业论文": "dissertation",
        "essay": "regular",
        "assignment": "regular",
        "作业": "regular",
        "课业": "regular",
        "exam": "final_prediction",
        "final": "final_prediction",
        "考试": "final_prediction",
        "冲刺": "final_prediction",
        "保分": "guaranteed",
        "guaranteed": "guaranteed",
        "保过": "guaranteed",
        "年包": "annual_package",
        "dp": "dp_premium",
        "ib": "dp_premium",
    }

    _PRODUCT_NAMES = {
        "dissertation":   "毕业论文辅导",
        "regular":        "课业辅导",
        "final_prediction":"Final考前冲刺规划",
        "guaranteed":     "保过辅导",
        "annual_package": "年包服务",
        "dp_premium":     "DP辅导",
    }

    def _map_product_id(self, product: str) -> str:
        p = (product or "").lower()
        for key, pid in self._PRODUCT_ID_MAP.items():
            if key in p:
                return pid
        return ""

    def _get_phase(self, country: str, month: int) -> tuple:
        return COUNTRY_PHASES.get(country, {}).get(month, ("常规学期", 0.6))

    def _calc_hist_boost(self, patterns: list, country: str, product_id: str, month: int) -> float:
        relevant = [
            p for p in patterns
            if (p.get("country", "").upper() == country or not p.get("country"))
            and str(month) in str(p.get("peak_months", ""))
        ]
        return min(0.5, len(relevant) * 0.1)

    def _calc_calendar_boost(self, calendars: list, start: date, end: date,
                              country: str) -> tuple:
        boost = 0.0
        events = []
        cal_notes = []
        for cal in calendars:
            cal_country = (cal.get("country") or "").upper()
            if cal_country and cal_country != country:
                continue
            # start_date 字段（非 event_date）
            raw_date = cal.get("start_date") or cal.get("event_date") or ""
            try:
                event_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
            except Exception:
                continue
            if start <= event_date <= end:
                event_name = cal.get("event_name", "")
                school_name = cal.get("school", "")
                events.append(f"{school_name}：{event_name}" if school_name else event_name)
                note = {
                    "event_name":          event_name,
                    "school":              school_name,
                    "event_date":          str(event_date),
                    "calendar_source_url": cal.get("source", ""),
                    "calendar_confidence": cal.get("confidence", "medium"),
                }
                cal_notes.append(note)
                etype = cal.get("event_type", "")
                ename_lower = event_name.lower()
                if etype in ("exam_period", "submission") or any(kw in ename_lower for kw in ["考试", "exam", "final", "deadline", "截止", "submission"]):
                    boost += 0.35
                elif etype == "reading_week" or any(kw in ename_lower for kw in ["reading week", "revision"]):
                    boost += 0.2
                elif etype in ("teaching_start", "teaching_end") or any(kw in ename_lower for kw in ["开学", "start", "orientation"]):
                    boost += 0.15
                else:
                    boost += 0.05
        return min(0.8, boost), events[:5], cal_notes[:5]

    def _recommend_channels(self, urgency: str, window_key: str) -> list:
        if urgency in ("极高", "高"):
            if window_key in ("0-7天", "8-14天"):
                return ["xiaohongshu", "wechat_group", "moments", "referral"]
            return ["moments", "community", "referral"]
        elif urgency == "中":
            return ["moments", "community", "old_customer"]
        return ["old_customer", "referral"]

    def _build_role_actions(self, window_key: str, window_label: str, country: str,
                             product_id: str, product_name: str, phase_name: str,
                             urgency: str, key_events: list, predicted_leads: int,
                             predicted_orders: int, today_dt: date, days_to: int) -> list:
        due = (today_dt + timedelta(days=min(days_to, 7))).strftime("%Y-%m-%d")
        country_name = {"UK": "英国", "AU": "澳洲"}.get(country, country)
        event_str = f"（{', '.join(key_events[:2])}）" if key_events else ""

        actions = []

        # 推广部动作
        if window_key in ("0-7天", "8-14天"):
            promo_action = f"立即发布{country_name}{phase_name}主题内容，覆盖小红书+朋友圈+社群"
        else:
            promo_action = f"提前备好{country_name}{phase_name}素材矩阵，计划下阶段投放节奏"

        actions.append({
            "role":           "推广部",
            "action":         promo_action,
            "owner":          "promotion_team",
            "due_date":       due,
            "success_metric": f"本窗口期内新增线索≥{max(predicted_leads, 3)}条",
            "risk_note":      f"若{urgency}需求期内未及时发布，错过{event_str}节点流量",
            "data_evidence":  f"预测需求紧迫度：{urgency}；{country_name}当前：{phase_name}",
        })

        # 顾问动作
        if urgency in ("极高", "高"):
            cons_action = f"今日优先跟进{country_name}{product_name}高意向线索，当天内回复，促本周成单"
        else:
            cons_action = f"预热{country_name}客户，了解{product_name}需求，记录到CRM"

        actions.append({
            "role":           "顾问",
            "action":         cons_action,
            "owner":          "consultant",
            "due_date":       due,
            "success_metric": f"跟进率100%，成单≥{max(predicted_orders, 1)}单",
            "risk_note":      "高意向客户48小时未跟进流失率高",
            "data_evidence":  f"预计本窗口成单量：{predicted_orders}单",
        })

        # 学管动作
        actions.append({
            "role":           "学管",
            "action":         f"预检{product_name}老师排期，确认{window_label}可承接量，超额前72小时告知顾问",
            "owner":          "xueguan",
            "due_date":       due,
            "success_metric": "排期确认率100%，无超期接单",
            "risk_note":      "容量未确认即接单，导致后续延期交付投诉",
            "data_evidence":  f"预计需求{predicted_orders}单，需提前锁定老师资源",
        })

        return actions
