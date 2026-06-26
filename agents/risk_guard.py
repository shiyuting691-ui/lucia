"""
RiskGuard v2 — 风控模块（Phase 2 v2）

16条业务规则 + 规则17（禁止"暂停推"语言）
结构化告警输出：rule_id / rule_name / severity / blocked_content / suggested_fix
"""
import logging
from datetime import datetime, timedelta, date
from collections import Counter

logger = logging.getLogger(__name__)

# ── 永久禁止话术 ──────────────────────────────────────────────────
FORBIDDEN_PROMISES = [
    "100%通过 / 保证通过（不可量化承诺）",
    "无条件退款（需对照合同条款）",
    "24小时内完成（除非学管已确认）",
    "老师专属陪伴（除非购买旗舰套餐）",
    "一定能过 / 稳过（质量承诺）",
]

# ── 禁止营销词（规则12）──────────────────────────────────────────
FORBIDDEN_MARKETING_TERMS = {
    "押题命中率": "考前重点范围判断",
    "保证押中":   "考前重点范围判断",
    "真题框架":   "题型方向整理",
    "覆盖率":     "复习重点梳理",
    "绝对保分":   "考前冲刺规划",
    "绝对AI率":   "往年考察方向分析",
}

# ── 禁止部门名称（规则13）───────────────────────────────────────
FORBIDDEN_DEPT_NAMES = {
    "市场部": "推广部",
    "销售部": "顾问",
    "产品部": "推广部",
    "后端":   "后台",
    "运营部": "学管",
    "教研部": "学管",
}

# ── 禁止"暂停推"相关词语（规则17）──────────────────────────────
FORBIDDEN_PAUSE_TERMS = ["暂停推", "停止推广", "暂时停推", "先暂停"]

# 渠道异常增长阈值
ANOMALY_THRESHOLD = 2.0


class RiskGuard:

    def assess(self, decision: dict = None, resource: dict = None,
               traffic_lights: dict = None, content_to_check: str = "") -> dict:
        """
        Args:
            decision: DecisionEngine.run() 输出
            resource: ResourceChecker.check() 输出（可选）
            traffic_lights: ProductTrafficLight.run() 输出
            content_to_check: 待检查文本（话术/推文内容等）
        """
        from database import list_leads, list_orders, list_order_risks

        alerts = []
        today  = date.today()

        try:
            leads  = list_leads(limit=500)
        except Exception:
            leads = []
        try:
            orders = list_orders(days=14, limit=500)
        except Exception:
            orders = []
        try:
            db_risks = list_order_risks(limit=50)
        except Exception:
            db_risks = []

        decision      = decision or {}
        resource      = resource or {}
        traffic_lights = traffic_lights or {}
        overall_res   = resource.get("overall", "green")

        # ── 规则1：超卖风险 ──────────────────────────────────────
        if overall_res == "blocked":
            alerts.append(self._alert(
                rule_id="R01", rule_name="超卖风险", severity="critical",
                blocked_content="容量满员后继续接单",
                suggested_fix="先确认资源再接单；学管通知顾问当前可承接量",
                dept="管理层/学管/顾问",
            ))
        elif overall_res == "red":
            alerts.append(self._alert(
                rule_id="R01", rule_name="超卖风险", severity="high",
                blocked_content="多学科容量>85%仍全量推广",
                suggested_fix="本周新单逐单经学管确认后方可承接",
                dept="学管",
            ))

        # ── 规则2：老师容量风险 ──────────────────────────────────
        for ts in resource.get("teacher_summary", []):
            if ts.get("status") == "blocked":
                alerts.append(self._alert(
                    rule_id="R02", rule_name="老师容量风险", severity="critical",
                    blocked_content=f"{ts.get('subject','')} 方向已无老师名额仍在接单",
                    suggested_fix="先确认该方向资源后再接单",
                    dept="学管/后台",
                ))
            elif ts.get("status") == "red":
                alerts.append(self._alert(
                    rule_id="R02", rule_name="老师容量风险", severity="high",
                    blocked_content=f"{ts.get('subject','')} 使用率 {ts.get('usage_pct',0)}%",
                    suggested_fix="控制新单，优先服务已有客户",
                    dept="学管",
                ))

        # ── 规则3：超时线索流失风险 ──────────────────────────────
        overdue_ct = sum(1 for l in leads if l.get("followup_status") == "overdue")
        if overdue_ct >= 10:
            alerts.append(self._alert(
                rule_id="R03", rule_name="超时线索流失风险", severity="high",
                blocked_content=f"{overdue_ct}条线索超时未跟进",
                suggested_fix="顾问今日优先电话/微信处理全部超时线索",
                dept="顾问",
            ))
        elif overdue_ct >= 5:
            alerts.append(self._alert(
                rule_id="R03", rule_name="超时线索流失风险", severity="medium",
                blocked_content=f"{overdue_ct}条线索超时未跟进",
                suggested_fix="本周内完成跟进，记录原因",
                dept="顾问",
            ))

        # ── 规则4：渠道异常增长 ──────────────────────────────────
        channel_anomalies = self._detect_channel_anomalies(leads, today)
        for anom in channel_anomalies:
            alerts.append(self._alert(
                rule_id="R04", rule_name="渠道异常增长", severity="medium",
                blocked_content=anom["description"],
                suggested_fix="后台核查渠道数据来源，确认是否真实增长",
                dept="后台/推广部",
            ))

        # ── 规则5：DB已知高风险订单 ──────────────────────────────
        for r in db_risks[:5]:
            if r.get("risk_level") in ("high", "critical"):
                alerts.append(self._alert(
                    rule_id="R05", rule_name="订单高风险", severity=r.get("risk_level", "high"),
                    blocked_content=r.get("risk_description", ""),
                    suggested_fix="管理层审查，决定是否继续推广",
                    dept="管理层",
                ))

        # ── 规则6：红灯产品推广控制 ──────────────────────────────
        red_products = [pid for pid, tl in traffic_lights.items() if tl.get("status") == "red"]
        if red_products:
            names = [traffic_lights[p].get("product_name", p) for p in red_products]
            alerts.append(self._alert(
                rule_id="R06", rule_name="红灯产品推广控制", severity="high",
                blocked_content=f"{'、'.join(names)} 在未确认资源前大量引流",
                suggested_fix="先确认资源再接单；仅通过老客渠道触达",
                dept="推广部/顾问",
            ))

        # ── 规则7：灰灯产品数据缺失 ──────────────────────────────
        grey_products = [pid for pid, tl in traffic_lights.items() if tl.get("status") == "grey"]
        if grey_products:
            names = [traffic_lights[p].get("product_name", p) for p in grey_products]
            alerts.append(self._alert(
                rule_id="R07", rule_name="产品数据缺失", severity="medium",
                blocked_content=f"{'、'.join(names)} 缺少老师容量/订单数据",
                suggested_fix="学管补录容量数据后方可按常规节奏推广",
                dept="学管/后台",
            ))

        # ── 规则8：预测数据空缺 ───────────────────────────────────
        if not traffic_lights and not resource:
            alerts.append(self._alert(
                rule_id="R08", rule_name="预测数据空缺", severity="medium",
                blocked_content="无任何产品红绿灯或资源数据",
                suggested_fix="优先补录容量数据，当前按最保守策略执行",
                dept="后台",
            ))

        # ── 规则9：高意向线索0跟进 ───────────────────────────────
        high_intent_no_follow = sum(
            1 for l in leads
            if l.get("deal_status") in ("new",) and not l.get("last_followup_time")
        )
        if high_intent_no_follow >= 5:
            alerts.append(self._alert(
                rule_id="R09", rule_name="高意向线索零跟进", severity="high",
                blocked_content=f"{high_intent_no_follow}条新线索从未被跟进",
                suggested_fix="顾问今日全部首次触达，优先电话",
                dept="顾问",
            ))

        # ── 规则10：订单量骤降 ────────────────────────────────────
        orders_7d  = [o for o in orders if self._within_days(o.get("order_date"), today, 7)]
        orders_14d = [o for o in orders if self._within_days(o.get("order_date"), today, 14)]
        prev_7d_ct = len(orders_14d) - len(orders_7d)
        if prev_7d_ct > 0 and len(orders_7d) < prev_7d_ct * 0.5:
            alerts.append(self._alert(
                rule_id="R10", rule_name="订单量骤降", severity="high",
                blocked_content=f"本周订单{len(orders_7d)}单 vs 上周{prev_7d_ct}单，降幅>50%",
                suggested_fix="管理层了解原因，顾问加强线索跟进",
                dept="管理层/顾问",
            ))

        # ── 规则11：话术边界（永久禁止承诺）────────────────────────
        for fp in FORBIDDEN_PROMISES:
            if content_to_check and any(kw in content_to_check for kw in fp.split("/")):
                alerts.append(self._alert(
                    rule_id="R11", rule_name="话术边界违规", severity="critical",
                    blocked_content=fp,
                    suggested_fix="删除承诺性表述，改为'可参考往年数据'等中性说法",
                    dept="顾问",
                ))

        # ── 规则12：禁止营销词 ────────────────────────────────────
        if content_to_check:
            for term, replacement in FORBIDDEN_MARKETING_TERMS.items():
                if term in content_to_check:
                    alerts.append(self._alert(
                        rule_id="R12", rule_name="禁止营销词", severity="high",
                        blocked_content=f"使用了禁止词「{term}」",
                        suggested_fix=f"替换为「{replacement}」",
                        dept="推广部/顾问",
                    ))

        # ── 规则13：错误部门名称 ──────────────────────────────────
        if content_to_check:
            for bad_dept, correct_dept in FORBIDDEN_DEPT_NAMES.items():
                if bad_dept in content_to_check:
                    alerts.append(self._alert(
                        rule_id="R13", rule_name="错误部门名称", severity="medium",
                        blocked_content=f"使用了非标准部门名「{bad_dept}」",
                        suggested_fix=f"统一使用「{correct_dept}」",
                        dept="全员",
                    ))

        # ── 规则14：产品名称准确性 ────────────────────────────────
        PRODUCT_NAMES_OK = {
            "Final考前冲刺规划", "课业辅导", "毕业论文辅导",
            "保过辅导", "学年包", "DP旗舰版",
        }
        if content_to_check and "Final精准押题" in content_to_check:
            alerts.append(self._alert(
                rule_id="R14", rule_name="产品名称错误", severity="medium",
                blocked_content="使用旧产品名「Final精准押题」",
                suggested_fix="统一使用「Final考前冲刺规划」",
                dept="推广部/顾问",
            ))

        # ── 规则15：顾问/学管职责混淆 ────────────────────────────
        xueguan_terms_in_consultant = ["排课", "老师资源", "交付安排", "老师档期"]
        consultant_terms_in_xueguan = ["报价", "成单话术", "逼单"]
        if content_to_check:
            found = [t for t in xueguan_terms_in_consultant if t in content_to_check]
            if found:
                alerts.append(self._alert(
                    rule_id="R15", rule_name="职责混淆", severity="medium",
                    blocked_content=f"顾问内容中出现学管职责词：{found}",
                    suggested_fix="顾问只负责销售，学管职责词移出顾问话术",
                    dept="顾问",
                ))

        # ── 规则16：容量未确认即推广 ──────────────────────────────
        yellow_no_cap = [
            pid for pid, tl in traffic_lights.items()
            if tl.get("status") == "yellow" and "数据不足" in tl.get("status_reason", "")
        ]
        if yellow_no_cap:
            names = [traffic_lights[p].get("product_name", p) for p in yellow_no_cap]
            alerts.append(self._alert(
                rule_id="R16", rule_name="容量未确认推广", severity="medium",
                blocked_content=f"{'、'.join(names)} 容量数据不足但仍在推广",
                suggested_fix="学管补录容量后再决定推广力度",
                dept="学管",
            ))

        # ── 规则17：禁止"暂停推"语言 ────────────────────────────
        if content_to_check:
            found_pause = [t for t in FORBIDDEN_PAUSE_TERMS if t in content_to_check]
            if found_pause:
                alerts.append(self._alert(
                    rule_id="R17", rule_name="禁用语：暂停推", severity="critical",
                    blocked_content=f"出现禁用词：{found_pause}",
                    suggested_fix="红灯产品使用「先确认资源再接单」，不得出现该类表述",
                    dept="全员",
                ))

        # ── 整体风险等级 ──────────────────────────────────────────
        severities = [a["severity"] for a in alerts]
        if "critical" in severities:
            overall_risk = "critical"
        elif "high" in severities:
            overall_risk = "high"
        elif "medium" in severities:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        # ── 本周禁止承诺 ──────────────────────────────────────────
        forbidden_promises = list(FORBIDDEN_PROMISES)
        if overall_res in ("red", "blocked"):
            forbidden_promises.insert(0, "本周可以立即开始（容量未确认前不可说）")

        return {
            "alerts":             alerts,
            "forbidden_promises": forbidden_promises,
            "channel_anomalies":  channel_anomalies,
            "overall_risk":       overall_risk,
            "alert_count":        len(alerts),
            "critical_count":     severities.count("critical"),
            "high_count":         severities.count("high"),
            "generated_at":       datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _alert(rule_id: str, rule_name: str, severity: str,
               blocked_content: str, suggested_fix: str, dept: str) -> dict:
        return {
            "rule_id":        rule_id,
            "rule_name":      rule_name,
            "severity":       severity,
            "blocked_content": blocked_content,
            "suggested_fix":  suggested_fix,
            "dept":           dept,
        }

    @staticmethod
    def _within_days(date_str, today: date, days: int) -> bool:
        if not date_str:
            return False
        try:
            d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
            return (today - timedelta(days=days)) <= d <= today
        except Exception:
            return False

    def _detect_channel_anomalies(self, leads: list, today: date) -> list:
        cutoff_7  = today - timedelta(days=7)
        cutoff_14 = today - timedelta(days=14)

        def _date(v):
            if not v:
                return date.min
            try:
                return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
            except Exception:
                return date.min

        recent  = Counter(l.get("lead_source_channel") or "unknown"
                          for l in leads if _date(l.get("inquiry_date")) >= cutoff_7)
        earlier = Counter(l.get("lead_source_channel") or "unknown"
                          for l in leads if cutoff_14 <= _date(l.get("inquiry_date")) < cutoff_7)

        anomalies = []
        for ch, cnt in recent.items():
            prev = earlier.get(ch, 0)
            if prev == 0 and cnt >= 5:
                anomalies.append({
                    "channel":     ch,
                    "recent_ct":   cnt,
                    "prev_ct":     prev,
                    "description": f"渠道「{ch}」本周突现 {cnt} 条线索（上周0条），需核查来源",
                })
            elif prev > 0 and cnt / prev >= ANOMALY_THRESHOLD and cnt >= 5:
                anomalies.append({
                    "channel":     ch,
                    "recent_ct":   cnt,
                    "prev_ct":     prev,
                    "description": f"渠道「{ch}」增长{round(cnt/prev*100-100)}%（{prev}→{cnt}），请确认是否真实",
                })
        return anomalies
