"""
ChannelAttributionAgent — 渠道与角色归因分析
分析各渠道（推广/小红书/垂直号/朋友圈/社群/转介绍/老客户）的线索质量和转化效果，
区分推广部、学管、顾问的不同渠道贡献。
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic
from database.db import get_session
from database.models import Lead, Order
from services.channel_constants import (
    VALID_CHANNELS, VALID_ROLES, channel_zh, role_zh, CHANNEL_EN_TO_ZH
)


class ChannelAttributionAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.model  = config["anthropic"]["model"]

    def run(self, days_lookback: int = 30) -> dict:
        period_end   = datetime(2025, 12, 20)
        period_start = period_end - timedelta(days=days_lookback)

        with get_session() as s:
            leads  = s.query(Lead).filter(
                Lead.created_at >= period_start,
                Lead.created_at <= period_end,
            ).all()
            orders = s.query(Order).filter(
                Order.order_date >= period_start,
                Order.order_date <= period_end,
            ).all()
            lead_data  = [self._lead_row(l) for l in leads]
            order_data = [self._order_row(o) for o in orders]

        missing_data = []
        if not any(l.get("lead_source_channel") and l["lead_source_channel"] != "unknown"
                   for l in lead_data):
            missing_data.append({
                "field": "lead_source_channel",
                "table": "leads",
                "impact": "无法区分渠道来源，所有线索归为 unknown",
                "action": "在线索录入时填写 lead_source_channel 字段"
            })
        if not any(l.get("source_owner_role") for l in lead_data):
            missing_data.append({
                "field": "source_owner_role",
                "table": "leads",
                "impact": "无法区分学管/顾问的小红书/垂直号贡献",
                "action": "在线索录入时填写 source_owner_role 字段"
            })

        # 纯规则统计
        channel_stats = self._compute_channel_stats(lead_data, order_data)
        role_stats    = self._compute_role_stats(lead_data, order_data)

        # Claude 只生成洞察（不生成数字）
        insights = self._generate_insights(channel_stats, role_stats, missing_data)

        result = {
            "period":             f"{period_start.date()} ~ {period_end.date()}",
            "channel_performance": channel_stats,
            "role_contribution":   role_stats,
            "insights":           insights,
            "missing_data":       missing_data,
            "generated_at":       datetime.utcnow().isoformat(),
        }
        return result

    # ── 纯规则统计 ──────────────────────────────────────
    def _compute_channel_stats(self, leads, orders):
        from collections import defaultdict
        stats = defaultdict(lambda: {
            "leads_count": 0, "qualified": 0, "quoted": 0,
            "won": 0, "deal_amount": 0.0, "lost": 0,
            "lost_reasons": [], "risk_count": 0,
            "roles": set(),
        })

        for l in leads:
            ch = l.get("lead_source_channel") or "unknown"
            stats[ch]["leads_count"] += 1
            if l.get("deal_status") in ("quoted", "follow_up", "won"):
                stats[ch]["qualified"] += 1
            if l.get("deal_status") in ("quoted", "follow_up"):
                stats[ch]["quoted"] += 1
            if l.get("deal_status") == "won":
                stats[ch]["won"] += 1
                stats[ch]["deal_amount"] += float(l.get("deal_amount") or 0)
            if l.get("deal_status") == "lost":
                stats[ch]["lost"] += 1
                if l.get("lost_reason"):
                    stats[ch]["lost_reasons"].append(l["lost_reason"])
            if l.get("risk_flag"):
                stats[ch]["risk_count"] += 1
            role = l.get("source_owner_role") or l.get("assigned_role")
            if role:
                stats[ch]["roles"].add(role)

        result = []
        for ch, st in stats.items():
            total = st["leads_count"]
            cvr   = round(st["won"] / total, 3) if total else 0
            result.append({
                "channel":            ch,
                "channel_zh":         channel_zh(ch),
                "leads_count":        total,
                "qualified_leads_count": st["qualified"],
                "quoted_count":       st["quoted"],
                "deal_count":         st["won"],
                "deal_amount":        round(st["deal_amount"], 2),
                "conversion_rate":    cvr,
                "lost_count":         st["lost"],
                "main_lost_reasons":  list(set(st["lost_reasons"]))[:3],
                "risk_count":         st["risk_count"],
                "owner_roles":        [role_zh(r) for r in st["roles"]],
            })
        result.sort(key=lambda x: x["leads_count"], reverse=True)
        return result

    def _compute_role_stats(self, leads, orders):
        from collections import defaultdict
        # key = (role, channel)
        stats = defaultdict(lambda: {
            "assigned": 0, "followed": 0, "overdue": 0,
            "quoted": 0, "won": 0, "deal_amount": 0.0,
            "risk_feedback": 0, "persons": set(),
        })
        now = datetime(2025, 12, 20)

        for l in leads:
            role = l.get("assigned_role") or l.get("source_owner_role") or "unknown"
            ch   = l.get("lead_source_channel") or "unknown"
            key  = (role, ch)
            stats[key]["assigned"] += 1
            if l.get("followup_status") in ("in_progress", "done"):
                stats[key]["followed"] += 1
            if l.get("followup_status") == "overdue":
                stats[key]["overdue"] += 1
            if l.get("deal_status") in ("quoted", "follow_up"):
                stats[key]["quoted"] += 1
            if l.get("deal_status") == "won":
                stats[key]["won"] += 1
                stats[key]["deal_amount"] += float(l.get("deal_amount") or 0)
            if l.get("risk_flag"):
                stats[key]["risk_feedback"] += 1
            person = l.get("assigned_person") or l.get("source_owner_name")
            if person:
                stats[key]["persons"].add(person)

        result = []
        for (role, ch), st in stats.items():
            total = st["assigned"]
            cvr   = round(st["won"] / total, 3) if total else 0
            result.append({
                "role":                   role,
                "role_zh":                role_zh(role),
                "channel":                ch,
                "channel_zh":             channel_zh(ch),
                "persons":                list(st["persons"]),
                "assigned_leads_count":   total,
                "followed_leads_count":   st["followed"],
                "overdue_followups_count":st["overdue"],
                "quoted_count":           st["quoted"],
                "deal_count":             st["won"],
                "deal_amount":            round(st["deal_amount"], 2),
                "conversion_rate":        cvr,
                "risk_feedback_count":    st["risk_feedback"],
            })
        result.sort(key=lambda x: x["assigned_leads_count"], reverse=True)
        return result

    def _generate_insights(self, channel_stats, role_stats, missing_data):
        if not channel_stats and not role_stats:
            return ["当前无有效数据，无法生成渠道洞察。请先录入线索来源信息。"]

        summary = json.dumps({
            "channel_summary": channel_stats[:6],
            "role_summary":    role_stats[:8],
            "missing_fields":  [m["field"] for m in missing_data],
        }, ensure_ascii=False, default=str)

        prompt = f"""你是极致教育增长系统的渠道归因分析师。

以下是渠道与角色的统计数据（基于真实数据规则计算，不含预测）：
{summary}

请输出 JSON，格式如下：
{{
  "scale_up": ["值得加大投入的渠道或角色+具体原因"],
  "optimize": ["需要优化的渠道或角色+具体问题"],
  "pause": ["建议暂停或减少投入的渠道"],
  "execution_gaps": ["执行缺口：哪个角色在哪个渠道跟进不到位"],
  "next_week_actions": ["下周具体行动建议（角色+渠道+动作）"]
}}

要求：
1. 不要编造数字。
2. 如果 missing_data 有字段，必须在结论里标注"因缺少XXX字段，该结论为推断"。
3. 每条建议必须指向具体渠道+角色+动作，不要写泛泛结论。
4. 最多5条建议，精准胜于全面。
只输出 JSON，不要加其他文字。"""

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            return json.loads(raw[start:end])
        except Exception:
            return {"error": "洞察生成失败，请检查 API 连接"}

    def _lead_row(self, l: Lead) -> dict:
        return {
            "id":                  l.id,
            "lead_source_channel": getattr(l, "lead_source_channel", None) or getattr(l, "source_channel", None),
            "source_owner_role":   getattr(l, "source_owner_role", None),
            "source_owner_name":   getattr(l, "source_owner_name", None),
            "assigned_role":       getattr(l, "assigned_role", None),
            "assigned_person":     getattr(l, "assigned_person", None) or l.sales_owner,
            "deal_status":         l.deal_status,
            "deal_amount":         getattr(l, "deal_amount", None) or l.quoted_price,
            "lost_reason":         l.lost_reason,
            "followup_status":     getattr(l, "followup_status", None),
            "risk_flag":           getattr(l, "risk_flag", False),
            "customer_stage":      getattr(l, "customer_stage", None),
        }

    def _order_row(self, o: Order) -> dict:
        return {
            "id":          o.id,
            "sales_owner": o.sales_owner,
            "amount":      o.amount,
            "product":     o.product,
            "school":      o.school,
        }
