"""
DecisionEngine — 增长决策引擎

从 DB 数据中识别：
  - 本周 Top 机会（按预期价值排序）
  - 下周机会预警
  - 下月布局方向
  - 禁止行为（超卖 / 容量不足时）
  - 风险提示

输出结构：
{
  "top_opportunities": [{"school","product","reason","expected_leads","priority"}...],
  "next_week_opportunities": [...],
  "next_month_opportunities": [...],
  "forbidden_actions": [{"action","reason","risk_level"}...],
  "risks": [{"type","description","severity","affected_dept"}...],
  "resource_status": "green|yellow|red|blocked",
  "confidence": "high|medium|low",
  "generated_at": "ISO8601"
}
"""
import logging
import sys
import os
import json
from datetime import datetime, timedelta, date
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from student_demand_calendar import get_current_student_phase
    from product_catalog import PRODUCT_CATALOG, PRODUCT_NAME_MAP
except ImportError:
    def get_current_student_phase(**kw): return {"urgency": "中", "hot_products": [], "messaging_angle": "", "uk_phase": "", "au_phase": ""}
    PRODUCT_CATALOG = {}
    PRODUCT_NAME_MAP = {}

try:
    from services.business_constants import VALID_SCHOOLS
except ImportError:
    VALID_SCHOOLS = []


# ── 常量 ──────────────────────────────────────────────────────────────────────
PRODUCT_DISPLAY = {
    "final_prediction": "Final精准押题",
    "regular":          "课业辅导",
    "dissertation":     "毕业论文辅导",
    "guaranteed":       "保过辅导",
    "annual_package":   "学年包",
    "dp_premium":       "DP旗舰版",
}

# 容量阈值（可调）
OVERSELL_THRESHOLD = 0.85   # 老师使用率 > 85% → red
WARN_THRESHOLD     = 0.70   # > 70% → yellow


class DecisionEngine:
    """
    纯数据驱动（不调用 Claude API），速度快且无成本。
    复杂分析交给 ActionPlanner（用 Claude）。
    """

    def __init__(self):
        pass

    # ─────────────────────────────────────────────────────────────────────────
    def run(self, period_days: int = 14) -> dict:
        from database import (
            list_orders, list_leads, list_teacher_capacity,
            list_market_signals, list_order_risks,
        )

        today      = date.today()
        phase_now  = get_current_student_phase(target_date=today)
        phase_next = get_current_student_phase(target_date=today + timedelta(days=7))
        phase_month = get_current_student_phase(target_date=date(today.year, today.month % 12 + 1, 1) if today.month < 12 else date(today.year + 1, 1, 1))

        orders     = list_orders(days=period_days, limit=500)
        leads      = list_leads(limit=500)
        capacities = list_teacher_capacity()
        signals    = list_market_signals(limit=30)
        risks      = list_order_risks(limit=50)

        # ── 数据统计 ──────────────────────────────────────────────
        product_orders   = Counter(o.get("product") for o in orders)
        school_orders    = Counter(o.get("school") for o in orders)
        channel_leads    = Counter(l.get("lead_source_channel") or l.get("source_channel") for l in leads)
        active_leads     = [l for l in leads if l.get("deal_status") in ("new", "contacted", "quoted", "follow_up")]
        overdue_leads    = [l for l in leads if l.get("followup_status") == "overdue"]

        # 近7天 vs 前7天对比
        cutoff_7  = today - timedelta(days=7)
        cutoff_14 = today - timedelta(days=14)
        recent_orders  = [o for o in orders if _parse_date(o.get("order_date")) >= cutoff_7]
        earlier_orders = [o for o in orders if cutoff_14 <= _parse_date(o.get("order_date")) < cutoff_7]
        order_trend    = len(recent_orders) - len(earlier_orders)

        # 老师容量
        cap_status, cap_detail = self._check_capacity(capacities)

        # ── 机会识别 ──────────────────────────────────────────────
        hot_products  = phase_now.get("hot_products", [])
        next_products = phase_next.get("hot_products", [])

        top_opportunities = self._identify_opportunities(
            hot_products, active_leads, school_orders, channel_leads, "本周"
        )
        next_week_opps = self._identify_opportunities(
            next_products, active_leads, school_orders, channel_leads, "下周"
        )
        next_month_opps = self._identify_monthly_opportunities(phase_month)

        # ── 禁止行为 ──────────────────────────────────────────────
        forbidden = self._build_forbidden(cap_status, cap_detail, risks, phase_now)

        # ── 风险 ──────────────────────────────────────────────────
        risk_list = self._build_risks(
            cap_status, cap_detail, risks, signals,
            overdue_leads, order_trend, channel_leads, phase_now
        )

        # ── 数据依据摘要 ──────────────────────────────────────────
        data_summary = {
            "active_leads":       len(active_leads),
            "overdue_leads":      len(overdue_leads),
            "orders_last_7d":     len(recent_orders),
            "orders_prev_7d":     len(earlier_orders),
            "order_trend":        order_trend,
            "top_channel":        channel_leads.most_common(1)[0] if channel_leads else ("unknown", 0),
            "top_product":        product_orders.most_common(1)[0] if product_orders else ("unknown", 0),
            "capacity_status":    cap_status,
            "uk_phase":           phase_now.get("uk_phase", ""),
            "au_phase":           phase_now.get("au_phase", ""),
            "urgency":            phase_now.get("urgency", "中"),
        }

        confidence = self._calc_confidence(orders, leads, capacities)

        return {
            "top_opportunities":      top_opportunities,
            "next_week_opportunities": next_week_opps,
            "next_month_opportunities": next_month_opps,
            "forbidden_actions":      forbidden,
            "risks":                  risk_list,
            "resource_status":        cap_status,
            "data_summary":           data_summary,
            "phase_now":              phase_now,
            "phase_next":             phase_next,
            "confidence":             confidence,
            "generated_at":           datetime.utcnow().isoformat(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    def _check_capacity(self, capacities: list) -> tuple:
        """返回 (green|yellow|red|blocked, detail_list)"""
        if not capacities:
            return "yellow", [{"subject": "未知", "note": "无老师容量数据，建议人工确认"}]

        tight = []
        blocked_subjects = []
        for cap in capacities:
            avail   = cap.get("available_slots", 0) or 0
            total   = cap.get("total_slots", 1) or 1
            usage   = 1.0 - (avail / total) if total > 0 else 0.0
            subject = cap.get("subject_area", "")
            if avail <= 0:
                blocked_subjects.append(subject)
            elif usage >= OVERSELL_THRESHOLD:
                tight.append({"subject": subject, "usage": round(usage, 2), "avail": avail})

        if blocked_subjects:
            return "blocked", [{"subject": s, "note": "已满员，禁止推广"} for s in blocked_subjects]
        if tight and len(tight) >= 3:
            return "red", tight
        if tight:
            return "yellow", tight
        return "green", []

    def _identify_opportunities(self, hot_products, active_leads, school_orders, channel_leads, label) -> list:
        opps = []
        for pid in hot_products[:3]:
            pname    = PRODUCT_DISPLAY.get(pid, pid)
            cnt      = school_orders.get(pid, 0)
            leads_ct = sum(1 for l in active_leads if (l.get("product") or "") == pid)
            priority = "P0" if cnt > 5 else ("P1" if cnt > 2 else "P2")

            opps.append({
                "label":          label,
                "product":        pid,
                "product_name":   pname,
                "school":         "多校",
                "reason":         f"当前学生需求阶段主推产品，近{len(school_orders)}单中已有{cnt}单",
                "expected_leads": leads_ct,
                "priority":       priority,
            })

        # 高活跃渠道机会
        for ch, cnt in channel_leads.most_common(2):
            if ch and ch != "unknown" and cnt >= 5:
                opps.append({
                    "label":          label,
                    "product":        "all",
                    "product_name":   "全产品线",
                    "school":         "多校",
                    "reason":         f"渠道「{ch}」活跃线索{cnt}条，可加大跟进",
                    "expected_leads": cnt,
                    "priority":       "P1",
                })
                break  # 只取最高一个

        return opps[:4]

    def _identify_monthly_opportunities(self, phase_month) -> list:
        opps = []
        for pid in phase_month.get("hot_products", [])[:3]:
            pname = PRODUCT_DISPLAY.get(pid, pid)
            opps.append({
                "label":        "下月",
                "product":      pid,
                "product_name": pname,
                "school":       "多校",
                "reason":       phase_month.get("messaging_angle", ""),
                "priority":     "P2",
            })
        return opps

    def _build_forbidden(self, cap_status, cap_detail, risks, phase_now) -> list:
        forbidden = []
        if cap_status == "blocked":
            for d in cap_detail:
                forbidden.append({
                    "action":     f"推广{d['subject']}相关产品",
                    "reason":     f"老师已满员（{d['subject']}）",
                    "risk_level": "high",
                })
        if cap_status == "red":
            forbidden.append({
                "action":     "大量承接新订单（超过现有容量）",
                "reason":     f"老师容量紧张：{[d.get('subject') for d in cap_detail]}",
                "risk_level": "high",
            })
        # 高风险订单风险
        for r in risks[:5]:
            if r.get("risk_level") in ("high", "critical"):
                forbidden.append({
                    "action":     f"继续推广{r.get('product','')}（{r.get('school','')}）",
                    "reason":     r.get("risk_description", "存在订单风险"),
                    "risk_level": r.get("risk_level", "high"),
                })

        # 基于学生需求阶段的禁止项
        urgency = phase_now.get("urgency", "中")
        if urgency in ("极高", "高"):
            forbidden.append({
                "action":     "发布模糊定价内容或无明确截止日期的促销",
                "reason":     "高需求期学生决策快，模糊信息会直接流失客户",
                "risk_level": "medium",
            })

        return forbidden

    def _build_risks(self, cap_status, cap_detail, risks, signals,
                     overdue_leads, order_trend, channel_leads, phase_now) -> list:
        risk_list = []

        # 容量风险
        if cap_status in ("red", "blocked"):
            risk_list.append({
                "type":          "资源风险",
                "description":   f"老师容量{'已满' if cap_status == 'blocked' else '紧张'}：{[d.get('subject') for d in cap_detail[:3]]}",
                "severity":      "high" if cap_status == "blocked" else "medium",
                "affected_dept": "学管/后台",
            })

        # 超时线索风险
        if len(overdue_leads) >= 5:
            risk_list.append({
                "type":          "订单风险",
                "description":   f"{len(overdue_leads)} 条线索超时未跟进，存在流失风险",
                "severity":      "medium" if len(overdue_leads) < 10 else "high",
                "affected_dept": "顾问",
            })

        # 订单下滑风险
        if order_trend < -3:
            risk_list.append({
                "type":          "订单风险",
                "description":   f"近7天订单较前7天减少 {abs(order_trend)} 单，趋势下行",
                "severity":      "medium",
                "affected_dept": "推广部/顾问",
            })

        # 渠道异常
        for ch, cnt in channel_leads.most_common():
            if ch == "unknown" and cnt > 20:
                risk_list.append({
                    "type":          "渠道风险",
                    "description":   f"有 {cnt} 条线索来源渠道未知，归因数据不准确",
                    "severity":      "low",
                    "affected_dept": "后台",
                })
                break

        # 已有风险记录
        for r in risks[:3]:
            if r.get("risk_level") in ("high", "critical"):
                risk_list.append({
                    "type":          "学校节点风险",
                    "description":   r.get("risk_description", ""),
                    "severity":      r.get("risk_level", "medium"),
                    "affected_dept": "管理层",
                })

        return risk_list

    def _calc_confidence(self, orders, leads, capacities) -> str:
        score = 0
        if len(orders) >= 20:   score += 1
        if len(leads)  >= 30:   score += 1
        if capacities:           score += 1
        return "high" if score >= 3 else ("medium" if score >= 1 else "low")


def _parse_date(val) -> date:
    if not val:
        return date.min
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return date.min
