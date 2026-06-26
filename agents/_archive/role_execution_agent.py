"""
RoleExecutionAgent — 角色执行情况分析
分析推广部、学管、顾问、后台、管理层的执行情况，
识别跟进不到位、资料缺失、决策卡点等问题。
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic
from database.db import get_session
from database.models import Lead, Task, DepartmentFeedback, Order
from services.channel_constants import role_zh, channel_zh, VALID_ROLES


class RoleExecutionAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.model  = config["anthropic"]["model"]

    def run(self, days_lookback: int = 30) -> dict:
        period_end   = datetime(2025, 12, 20)
        period_start = period_end - timedelta(days=days_lookback)

        with get_session() as s:
            leads   = s.query(Lead).filter(Lead.created_at >= period_start).all()
            tasks   = s.query(Task).filter(Task.created_at >= period_start).all()
            feedbacks = s.query(DepartmentFeedback).filter(
                DepartmentFeedback.created_at >= period_start).all()
            orders  = s.query(Order).filter(Order.order_date >= period_start).all()

        lead_rows  = [self._lead_row(l)  for l in leads]
        task_rows  = [self._task_row(t)  for t in tasks]
        fb_rows    = [self._fb_row(f)    for f in feedbacks]
        order_rows = [self._order_row(o) for o in orders]

        missing_data = self._detect_missing(lead_rows)
        role_exec    = self._compute_role_execution(lead_rows, task_rows, fb_rows, order_rows)
        coord_issues = self._detect_coordination_issues(lead_rows, task_rows, fb_rows)
        suggestions  = self._generate_suggestions(role_exec, coord_issues, missing_data)

        return {
            "period":                    f"{period_start.date()} ~ {period_end.date()}",
            "role_execution":            role_exec,
            "department_coordination_issues": coord_issues,
            "suggested_actions":         suggestions,
            "missing_data":              missing_data,
            "generated_at":              datetime.utcnow().isoformat(),
        }

    def _detect_missing(self, leads):
        missing = []
        if not any(l.get("assigned_role") for l in leads):
            missing.append({"field": "assigned_role", "table": "leads",
                            "impact": "无法判断哪个角色在承接哪条线索"})
        if not any(l.get("followup_status") for l in leads):
            missing.append({"field": "followup_status", "table": "leads",
                            "impact": "无法判断跟进是否及时或超时"})
        return missing

    def _compute_role_execution(self, leads, tasks, feedbacks, orders):
        from collections import defaultdict
        # key = (role, channel)
        stats = defaultdict(lambda: {
            "assigned": 0, "followed": 0, "overdue": 0,
            "quoted": 0, "won": 0, "amount": 0.0,
            "risk_feedback": 0, "useful_feedback": 0,
            "tasks_total": 0, "tasks_done": 0,
            "issues": [], "persons": set(),
        })

        for l in leads:
            role = l.get("assigned_role") or "unknown"
            ch   = l.get("lead_source_channel") or "unknown"
            key  = (role, ch)
            stats[key]["assigned"] += 1
            if l.get("followup_status") in ("in_progress", "done"):
                stats[key]["followed"] += 1
            if l.get("followup_status") == "overdue":
                stats[key]["overdue"] += 1
                stats[key]["issues"].append(f"超时未跟进线索ID={l['id']}")
            if l.get("deal_status") in ("quoted", "follow_up"):
                stats[key]["quoted"] += 1
            if l.get("deal_status") == "won":
                stats[key]["won"] += 1
                stats[key]["amount"] += float(l.get("deal_amount") or 0)
            if l.get("risk_flag"):
                stats[key]["risk_feedback"] += 1
            p = l.get("assigned_person")
            if p:
                stats[key]["persons"].add(p)

        for t in tasks:
            role = t.get("department_role") or t.get("department") or "unknown"
            from services.channel_constants import normalize_role
            role = normalize_role(role) or "unknown"
            ch   = t.get("channel") or "unknown"
            key  = (role, ch)
            stats[key]["tasks_total"] += 1
            if t.get("status") == "done":
                stats[key]["tasks_done"] += 1
            if t.get("status") == "blocked":
                stats[key]["issues"].append(f"任务被阻碍: {t.get('title','')[:30]}")

        for fb in feedbacks:
            role = fb.get("role") or fb.get("department") or "unknown"
            from services.channel_constants import normalize_role
            role = normalize_role(role) or "unknown"
            key  = (role, "unknown")
            stats[key]["risk_feedback"] += 1
            if fb.get("status") in ("resolved", "closed"):
                stats[key]["useful_feedback"] += 1

        result = []
        for (role, ch), st in stats.items():
            total = st["assigned"]
            cvr   = round(st["won"] / total, 3) if total else 0
            tc    = round(st["tasks_done"] / st["tasks_total"], 3) if st["tasks_total"] else 0
            result.append({
                "role":                    role,
                "role_zh":                 role_zh(role),
                "channel":                 ch,
                "channel_zh":              channel_zh(ch),
                "persons":                 list(st["persons"]),
                "assigned_leads_count":    total,
                "followed_leads_count":    st["followed"],
                "overdue_followups_count": st["overdue"],
                "quoted_count":            st["quoted"],
                "deal_count":              st["won"],
                "deal_amount":             round(st["amount"], 2),
                "conversion_rate":         cvr,
                "risk_feedback_count":     st["risk_feedback"],
                "useful_feedback_count":   st["useful_feedback"],
                "task_completion_rate":    tc,
                "issues":                  list(set(st["issues"]))[:5],
                "suggested_actions":       [],  # Claude 填充
            })
        result.sort(key=lambda x: x["assigned_leads_count"], reverse=True)
        return result

    def _detect_coordination_issues(self, leads, tasks, feedbacks):
        issues = []
        overdue = [l for l in leads if l.get("followup_status") == "overdue"]
        if overdue:
            issues.append(f"⚠️ {len(overdue)} 条线索跟进超时，涉及角色：" +
                          "、".join(set(l.get("assigned_role","?") for l in overdue)))
        blocked = [t for t in tasks if t.get("status") == "blocked"]
        if blocked:
            issues.append(f"🔴 {len(blocked)} 个任务被阻碍，需管理层或跨部门协调")
        pending_mgmt = [t for t in tasks
                        if t.get("department") in ("管理层","management")
                        and t.get("status") in ("todo","in_progress")]
        if pending_mgmt:
            issues.append(f"🔴 {len(pending_mgmt)} 个管理层待决策事项未完成，可能卡住执行")
        open_fb = [f for f in feedbacks if f.get("status") == "open"
                   and f.get("urgency") in ("高","紧急")]
        if open_fb:
            issues.append(f"⚠️ {len(open_fb)} 条高危反馈未处理")
        return issues

    def _generate_suggestions(self, role_exec, coord_issues, missing_data):
        summary = {
            "execution_overview": role_exec[:8],
            "coordination_issues": coord_issues,
            "missing_data": [m["field"] for m in missing_data],
        }
        prompt = f"""你是极致教育增长系统的角色执行分析师。
角色只有：推广部/学管/顾问/后台/管理层。

执行数据摘要：
{json.dumps(summary, ensure_ascii=False, default=str)}

请输出 JSON：
{{
  "role_actions": [
    {{"role": "角色中文", "channel": "渠道中文", "action": "具体建议（不超过30字）"}}
  ],
  "urgent_issues": ["紧急需处理的问题（角色+具体）"],
  "data_gaps": ["数据缺口及补录建议"]
}}

要求：
1. 不编造数字。
2. 每条建议必须具体到角色+渠道+行动。
3. 最多6条建议。
只输出 JSON。"""

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            return json.loads(raw[start:end])
        except Exception:
            return {"error": "建议生成失败"}

    def _lead_row(self, l):
        return {
            "id":                  l.id,
            "lead_source_channel": getattr(l, "lead_source_channel", None) or getattr(l, "source_channel", None),
            "assigned_role":       getattr(l, "assigned_role", None),
            "assigned_person":     getattr(l, "assigned_person", None) or l.sales_owner,
            "deal_status":         l.deal_status,
            "deal_amount":         getattr(l, "deal_amount", None),
            "followup_status":     getattr(l, "followup_status", None),
            "risk_flag":           getattr(l, "risk_flag", False),
        }

    def _task_row(self, t):
        return {
            "id":         t.id,
            "title":      t.title,
            "department": t.department,
            "status":     t.status,
            "channel":    getattr(t, "channel", None),
        }

    def _fb_row(self, f):
        return {
            "id":         f.id,
            "department": f.department,
            "urgency":    f.urgency,
            "status":     f.status,
        }

    def _order_row(self, o):
        return {
            "id":          o.id,
            "sales_owner": o.sales_owner,
            "amount":      o.amount,
        }
