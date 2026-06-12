"""
SchoolOpportunityScoringAgent — 学校机会评分（V7 第一阶段）

纯规则计算，不调用 Claude，不编造任何学校节点/DDL。
评分权重（共100分）：
  近7天咨询 20 / 近30天咨询 15 / 近30天订单 15 / 历史同期订单 15
  学校节点临近 10 / 产品利润潜力 10 / 老师资源匹配 10 / 风险可控 5

数据时效说明：orders/leads 数据若早于今天30天以上（CRM未接入期间），
自动锚定到数据年份的同期日期，并在 score_reason 中标注"基于2025年同期数据"。
"""
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import text
from database.db import engine
from database import list_dictionary_terms, save_school_score

logger = logging.getLogger(__name__)

MIN_DATA_THRESHOLD = 5  # 订单+咨询合计少于此数 → 资料不足 Unknown


def _priority(score: int, insufficient: bool) -> str:
    if insufficient:
        return "Unknown"
    if score >= 85: return "S"
    if score >= 70: return "A"
    if score >= 50: return "B"
    if score >= 30: return "C"
    return "低机会"


class SchoolOpportunityScoringAgent:

    def __init__(self, config: dict = None):
        self.config = config or {}
        # 学校别名映射：任意写法 → 标准简称（与 orders 表一致）
        self.alias_map = {}
        for t in list_dictionary_terms(term_type="学校名称"):
            std = t["standard_term"]
            self.alias_map[std.lower()] = std
            for a in t.get("aliases", []):
                self.alias_map[a.lower()] = std

    def normalize_school(self, name: str) -> str:
        return self.alias_map.get((name or "").strip().lower(), (name or "").strip())

    # ── 数据锚点：CRM 未接入时回退到数据年份同期 ──
    def _anchor_date(self) -> tuple[datetime, bool]:
        with engine.connect() as c:
            max_d = c.execute(text(
                "SELECT MAX(d) FROM (SELECT MAX(order_date) d FROM orders "
                "UNION SELECT MAX(inquiry_date) d FROM leads)")).scalar()
        today = datetime.now()
        if not max_d:
            return today, False
        max_dt = datetime.fromisoformat(str(max_d)[:10])
        if (today - max_dt).days <= 30:
            return today, False
        # 数据过旧 → 锚定到数据年份的今天同期
        anchored = today.replace(year=max_dt.year)
        if anchored > max_dt:
            anchored = max_dt
        return anchored, True

    def run(self, top_n: int = 20) -> list[dict]:
        anchor, is_historical = self._anchor_date()
        a = anchor.strftime("%Y-%m-%d")
        d7 = (anchor - timedelta(days=7)).strftime("%Y-%m-%d")
        d30 = (anchor - timedelta(days=30)).strftime("%Y-%m-%d")
        f30 = (anchor + timedelta(days=30)).strftime("%Y-%m-%d")
        hist_note = f"⚠️ 基于{anchor.year}年同期数据（CRM未接入，锚点 {a}）" if is_historical else None

        with engine.connect() as c:
            # 学校列表：按订单量 Top N（排除空/未知）
            schools = c.execute(text(
                "SELECT school, country, COUNT(*) n FROM orders "
                "WHERE school NOT IN ('', '未知', '/') GROUP BY school "
                "ORDER BY n DESC LIMIT :n"), {"n": top_n}).fetchall()

            results = []
            for school, country, total_orders in schools:
                results.append(self._score_one(
                    c, school, country, total_orders, a, d7, d30, f30, hist_note))
        return results

    def _score_one(self, c, school, country, total_orders, a, d7, d30, f30, hist_note):
        score_reason, evidence, risks, missing = [], [], [], []
        if hist_note:
            score_reason.append(hist_note)
        q = lambda sql, **kw: c.execute(text(sql), {"s": school, **kw}).scalar() or 0

        # 1. 近7天咨询（20分）：3条满分
        leads7 = q("SELECT COUNT(*) FROM leads WHERE school=:s AND inquiry_date BETWEEN :d7 AND :a", d7=d7, a=a)
        s1 = min(20, leads7 * 7)
        score_reason.append(f"近7天咨询 {leads7} 条 → {s1}/20")
        evidence.append(f"leads表 {d7}~{a} 咨询{leads7}条")

        # 2. 近30天咨询（15分）：8条满分
        leads30 = q("SELECT COUNT(*) FROM leads WHERE school=:s AND inquiry_date BETWEEN :d30 AND :a", d30=d30, a=a)
        s2 = min(15, leads30 * 2)
        score_reason.append(f"近30天咨询 {leads30} 条 → {s2}/15")

        # 3. 近30天订单（15分）：8单满分
        orders30 = q("SELECT COUNT(*) FROM orders WHERE school=:s AND order_date BETWEEN :d30 AND :a", d30=d30, a=a)
        s3 = min(15, orders30 * 2)
        score_reason.append(f"近30天订单 {orders30} 单 → {s3}/15")
        evidence.append(f"orders表 {d30}~{a} 成单{orders30}单")

        # 4. 历史同期订单（15分）：未来30天窗口的历史订单量，8单满分
        hist = q("SELECT COUNT(*) FROM orders WHERE school=:s AND order_date BETWEEN :a AND :f30", a=a, f30=f30)
        s4 = min(15, hist * 2)
        score_reason.append(f"历史同期(未来30天窗口)订单 {hist} 单 → {s4}/15")
        evidence.append(f"orders表 {a}~{f30} 历史同期{hist}单")

        # 5. 学校节点临近（10分）：±30天内有 calendar 事件
        events = c.execute(text(
            "SELECT event_name, start_date FROM school_calendar WHERE school=:s"), {"s": school}).fetchall()
        s5, near_events = 0, []
        anchor_dt = datetime.fromisoformat(a)
        for name, sd in events:
            try:
                ev = datetime.fromisoformat(str(sd)[:10]).replace(year=anchor_dt.year)
                if abs((ev - anchor_dt).days) <= 30:
                    near_events.append(f"{name}({str(sd)[5:10]})")
            except (ValueError, TypeError):
                continue
        if not events:
            missing.append("缺少学校节点资料（school_calendar 无该校记录），阶段判断可信度较低")
        elif near_events:
            s5 = 10
            evidence.append(f"30天内学校节点：{'、'.join(near_events[:3])}")
        score_reason.append(f"学校节点临近 → {s5}/10" + ("" if events else "（资料缺失计0分）"))

        # 6. 产品利润潜力（10分）：同期订单均价 ≥3000满分
        avg_amt = q("SELECT AVG(amount) FROM orders WHERE school=:s AND order_date BETWEEN :d30 AND :f30", d30=d30, f30=f30)
        s6 = min(10, int(avg_amt / 300)) if avg_amt else 0
        score_reason.append(f"同期订单均价 ¥{avg_amt:.0f} → {s6}/10" if avg_amt else "同期无订单金额数据 → 0/10")

        # 7. 老师资源匹配（10分）
        tc = c.execute(text("SELECT school_experience, capacity_status, subject_area FROM teacher_capacity")).fetchall()
        matched = [(st, sub) for exp, st, sub in tc
                   if school.lower() in (exp or "").lower()
                   or any(al.lower() in (exp or "").lower()
                          for al, std in self.alias_map.items() if std == school and len(al) > 2)]
        if not matched:
            s7 = 0
            missing.append("缺少老师储备数据（teacher_capacity 无该校匹配），无法判断是否适合强推")
        else:
            ok = sum(1 for st, _ in matched if st in ("充足", "正常"))
            s7 = round(10 * ok / len(matched))
            tight = [sub for st, sub in matched if st not in ("充足", "正常")]
            if tight:
                risks.append(f"老师资源紧张学科：{'、'.join(tight)}，谨慎强推")
            evidence.append(f"老师储备匹配{len(matched)}个学科，{ok}个状态充足/正常")
        score_reason.append(f"老师资源匹配 → {s7}/10")

        # 8. 风险可控（5分）
        high_risks = c.execute(text(
            "SELECT risk_type, evidence FROM order_risk_signals WHERE school=:s AND risk_level='high'"),
            {"s": school}).fetchall()
        s8 = 5 if not high_risks else max(0, 5 - 2 * len(high_risks))
        for rt, ev in high_risks:
            risks.append(f"高风险信号[{rt}]：{(ev or '')[:60]}")
        score_reason.append(f"风险可控 → {s8}/5（高风险信号{len(high_risks)}条）")

        total = s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8
        insufficient = (orders30 + leads30 + hist) < MIN_DATA_THRESHOLD
        if insufficient:
            missing.append("该学校内部数据不足，建议补充历史订单或咨询数据")

        # 当前阶段：只从已有 calendar / yearly_patterns 推断，缺失则"资料不足"
        stage = self._infer_stage(c, school, anchor_dt, near_events)
        heat = "high" if (leads7 >= 3 or orders30 >= 6) else \
               "medium" if (leads30 >= 3 or orders30 >= 2 or hist >= 4) else \
               "low" if not insufficient else "unknown"

        # 热门产品：同期订单 + 近期咨询意向
        prods = Counter(r[0] for r in c.execute(text(
            "SELECT product FROM orders WHERE school=:s AND order_date BETWEEN :d30 AND :f30 AND product != ''"),
            {"s": school, "d30": d30, "f30": f30}).fetchall())
        hot = [p for p, _ in prods.most_common(3)]

        data = {
            "school_name": school, "country": country or "",
            "opportunity_score": total,
            "priority_level": _priority(total, insufficient),
            "current_stage": stage, "demand_heat": heat,
            "hot_products": hot, "score_reason": score_reason,
            "internal_evidence": evidence, "risk_notes": risks,
            "missing_data": missing,
        }
        save_school_score(data)
        return data

    def _infer_stage(self, c, school, anchor_dt, near_events) -> str:
        for e in near_events:
            for kw, stage in (("Final", "Final冲刺期"), ("考试", "Final冲刺期"),
                              ("Dissertation", "Dissertation高峰期"), ("论文", "Dissertation高峰期"),
                              ("开学", "开学准备期"), ("Assessment", "Assessment高峰期"),
                              ("补考", "补考/挂科风险期")):
                if kw.lower() in e.lower():
                    return stage
        mmdd = anchor_dt.strftime("%m-%d")
        row = c.execute(text(
            "SELECT pattern_summary FROM yearly_patterns WHERE school=:s "
            "AND period_start<=:d AND period_end>=:d LIMIT 1"), {"s": school, "d": mmdd}).fetchone()
        if row:
            summary = row[0] or ""
            for kw, stage in (("Final", "Final冲刺期"), ("论文", "Dissertation高峰期"),
                              ("Dissertation", "Dissertation高峰期"), ("开学", "开学准备期"),
                              ("Assessment", "Assessment高峰期"), ("补考", "补考/挂科风险期")):
                if kw.lower() in summary.lower():
                    return stage
            return "低需求维护期"
        return "资料不足"
