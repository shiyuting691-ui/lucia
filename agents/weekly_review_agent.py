"""
WeeklyReviewAgent — 周复盘生成 (V12)

对比当周预测 vs 实际数据，区分以下6类问题：
  1. 渠道问题（哪个渠道效果下降/上升）
  2. 角色执行问题（学管/顾问/推广部执行是否到位）
  3. 产品问题（哪个产品咨询多但转化差）
  4. 话术问题（报价后跟进不足/话术弱）
  5. 供给风险（老师资源紧张/交付卡点）
  6. 管理决策卡点（待确认事项卡住执行）

V12 新增：
  7. 执行反馈复盘（execution_feedback 完成率 + 偏差分析）
  8. 预测准确度复盘（哪些判断对了 / 哪些错了 / 是数据还是执行问题）
"""
import logging
import json
from datetime import datetime, timedelta

from database import (
    list_campaign_predictions, list_orders, list_leads,
    get_task_execution_stats, save_weekly_review,
    list_feedbacks, list_tasks,
    list_execution_feedbacks, get_execution_feedback_stats,
)

logger = logging.getLogger(__name__)


class WeeklyReviewAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        from services.llm import LLMRouter
        self._router = LLMRouter()

    def run(self, week_start: str) -> dict:
        ws = datetime.strptime(week_start, "%Y-%m-%d")
        we = ws + timedelta(days=6)
        week_end = we.strftime("%Y-%m-%d")

        # ── 1. 实际数据（本周）────────────────────────────────────────
        actual_leads = list_leads(days=8, limit=500)
        actual_orders = list_orders(days=8, limit=500)
        # 筛选本周内
        actual_leads  = [l for l in actual_leads
                         if l.get("inquiry_date", "") >= week_start and
                            l.get("inquiry_date", "") <= week_end + "Z"]
        actual_orders = [o for o in actual_orders
                         if o.get("order_date", "") >= week_start and
                            o.get("order_date", "") <= week_end + "Z"]

        # ── 2. 预测数据（本周）───────────────────────────────────────
        predictions = list_campaign_predictions(week=week_start, limit=200)
        pred_leads_low  = sum(p.get("predicted_leads_low", 0) for p in predictions)
        pred_leads_high = sum(p.get("predicted_leads_high", 0) for p in predictions)
        pred_leads_mid  = (pred_leads_low + pred_leads_high) // 2

        # 按学校汇总实际 vs 预测
        school_actual: dict = {}
        for l in actual_leads:
            s = l.get("school", "未知")
            school_actual[s] = school_actual.get(s, 0) + 1
        school_pred: dict = {}
        for p in predictions:
            s = p.get("school", "")
            if s:
                school_pred[s] = school_pred.get(s, 0) + (
                    (p.get("predicted_leads_low", 0) + p.get("predicted_leads_high", 0)) // 2)
        all_schools = set(list(school_actual.keys()) + list(school_pred.keys()))
        school_breakdown = [{
            "school": s,
            "predicted": school_pred.get(s, 0),
            "actual": school_actual.get(s, 0),
            "diff": school_actual.get(s, 0) - school_pred.get(s, 0),
        } for s in sorted(all_schools)]

        # ── 3. 任务执行完成情况 ───────────────────────────────────────
        task_stats = get_task_execution_stats(week_start=week_start)

        # ── 4. V11 渠道/角色/供给数据 ────────────────────────────────
        channel_stats = self._compute_channel_stats(actual_leads)
        role_stats    = self._compute_role_stats(actual_leads, task_stats)
        supply_risks  = self._detect_supply_risks()
        mgmt_blocks   = self._detect_mgmt_blocks()

        # ── 4b. V12 执行反馈复盘 ─────────────────────────────────────
        exec_stats     = get_execution_feedback_stats(push_date=None)  # 本周全部
        exec_feedbacks = list_execution_feedbacks(limit=200)
        # 筛选本周
        exec_this_week = [
            f for f in exec_feedbacks
            if f.get("push_date", "") >= week_start and f.get("push_date", "") <= week_end + "Z"
        ]
        exec_completion = self._compute_exec_completion(exec_this_week)

        # ── 5. Claude 生成复盘文字 ────────────────────────────────────
        review_summary, key_wins, key_misses, root_causes, next_focus = \
            self._gen_review(week_start, actual_leads, actual_orders,
                             pred_leads_mid, task_stats, school_breakdown,
                             channel_stats, role_stats, supply_risks, mgmt_blocks,
                             exec_completion)

        data = {
            "review_week":             week_start,
            "total_leads_predicted":   pred_leads_mid,
            "total_leads_actual":      len(actual_leads),
            "total_orders_predicted":  0,
            "total_orders_actual":     len(actual_orders),
            "school_breakdown":        school_breakdown,
            "product_breakdown":       [],
            # V11 新增：6维归因
            "channel_issues":          channel_stats.get("issues", []),
            "role_execution_issues":   role_stats.get("issues", []),
            "supply_risks":            supply_risks,
            "mgmt_blocks":             mgmt_blocks,
            "tasks_total":             task_stats.get("total", 0),
            "tasks_done":              task_stats.get("done", 0),
            "tasks_delayed":           task_stats.get("delayed", 0),
            "tasks_blocked":           task_stats.get("blocked", 0),
            "dept_completion":         task_stats.get("by_dept", {}),
            "key_wins":                key_wins,
            "key_misses":              key_misses,
            "root_causes":             root_causes,
            "next_week_focus":         next_focus,
            "review_summary":          review_summary,
            "exec_feedback_stats":     exec_completion,
            "generated_by":            "WeeklyReviewAgent_V12",
        }
        save_weekly_review(data)
        logger.info(f"[WeeklyReviewAgent] review saved for {week_start}")
        return data

    # ── V11 辅助统计方法 ──────────────────────────────────────────
    def _compute_channel_stats(self, leads: list) -> dict:
        from collections import Counter
        channels = [l.get("lead_source_channel") or l.get("source_channel") or "unknown"
                    for l in leads]
        ch_count = Counter(channels)
        issues = []
        # 检测 unknown 占比
        total = len(leads)
        unknown_pct = ch_count.get("unknown", 0) / total if total else 0
        if unknown_pct > 0.5:
            issues.append(f"超过{int(unknown_pct*100)}%线索来源未记录，渠道归因数据不足")
        # 检测是否有小红书/垂直号数据
        if ch_count.get("xiaohongshu", 0) == 0:
            issues.append("本周无小红书线索记录，无法评估小红书渠道效果")
        return {"channel_counts": dict(ch_count), "issues": issues}

    def _compute_role_stats(self, leads: list, task_stats: dict) -> dict:
        from collections import Counter
        roles = [l.get("assigned_role") or "unknown" for l in leads]
        role_count = Counter(roles)
        issues = []
        if role_count.get("unknown", 0) == len(leads) and leads:
            issues.append("所有线索缺少 assigned_role 字段，无法判断学管/顾问各自承接效果")
        # 检测超时跟进
        overdue = [l for l in leads if l.get("followup_status") == "overdue"]
        if overdue:
            by_role = Counter(l.get("assigned_role", "unknown") for l in overdue)
            for role, cnt in by_role.items():
                issues.append(f"{role} 有 {cnt} 条线索跟进超时")
        # 管理层任务阻碍
        blocked = task_stats.get("blocked", 0)
        if blocked > 0:
            issues.append(f"{blocked} 个任务被阻碍，可能存在角色执行卡点")
        return {"role_counts": dict(role_count), "issues": issues}

    def _detect_supply_risks(self) -> list:
        risks = []
        try:
            fbs = list_feedbacks(status="open")
            supply_fbs = [f for f in fbs
                          if f.get("feedback_type") in ("老师资源紧张", "学管交付风险")
                          and f.get("urgency") in ("高", "紧急")]
            for fb in supply_fbs[:3]:
                risks.append(f"[{fb.get('urgency','')}] {fb.get('title','')} — {fb.get('department','')}")
        except Exception:
            pass
        return risks

    def _compute_exec_completion(self, feedbacks: list) -> dict:
        """统计执行反馈完成情况，区分部门 + 识别高频偏差"""
        if not feedbacks:
            return {"total": 0, "completed": 0, "rate": 0.0, "by_dept": {}, "top_deviations": []}
        total     = len(feedbacks)
        completed = sum(1 for f in feedbacks if f.get("completed") is True)
        by_dept: dict = {}
        deviations = []
        for f in feedbacks:
            dept = f.get("department", "unknown")
            by_dept.setdefault(dept, {"total": 0, "completed": 0})
            by_dept[dept]["total"] += 1
            if f.get("completed") is True:
                by_dept[dept]["completed"] += 1
            elif f.get("completed") is False and f.get("deviation"):
                deviations.append(f.get("deviation", ""))
        for dept in by_dept:
            t = by_dept[dept]["total"]
            c = by_dept[dept]["completed"]
            by_dept[dept]["rate"] = round(c / t * 100, 1) if t else 0.0
        return {
            "total":          total,
            "completed":      completed,
            "rate":           round(completed / total * 100, 1) if total else 0.0,
            "by_dept":        by_dept,
            "top_deviations": deviations[:5],
        }

    def _detect_mgmt_blocks(self) -> list:
        blocks = []
        try:
            tasks = list_tasks(limit=100)
            mgmt_pending = [t for t in tasks
                            if t.get("department") in ("管理层", "management")
                            and t.get("status") in ("todo", "in_progress")]
            for t in mgmt_pending[:3]:
                blocks.append(f"管理层待决策：{t.get('title','')[:40]}")
        except Exception:
            pass
        return blocks

    def _gen_review(self, week_start, leads, orders, pred_leads, task_stats, school_bd,
                    channel_stats=None, role_stats=None, supply_risks=None, mgmt_blocks=None,
                    exec_completion=None) -> tuple:
        completion_rate = task_stats.get("completion_rate", 0)
        dept_lines = "\n".join(
            f"  {d}: 完成{v['done']}/{v['total']}（{int(v['completion_rate']*100)}%）"
            for d, v in task_stats.get("by_dept", {}).items()
        ) or "  暂无任务数据"

        top_schools = sorted(school_bd, key=lambda x: -x["actual"])[:3]
        school_lines = "\n".join(
            f"  {s['school']}: 实际{s['actual']}条 vs 预测{s['predicted']}条"
            for s in top_schools
        ) or "  暂无数据"

        # V11 归因补充
        ch_issues  = "\n".join(f"  - {i}" for i in (channel_stats or {}).get("issues", [])) or "  无"
        role_issues= "\n".join(f"  - {i}" for i in (role_stats or {}).get("issues", [])) or "  无"
        supply_str = "\n".join(f"  - {r}" for r in (supply_risks or [])) or "  无"
        mgmt_str   = "\n".join(f"  - {b}" for b in (mgmt_blocks or [])) or "  无"

        prompt = f"""请对以下本周数据做结构化复盘（基于数据，不编造；数据不足时直接标注"数据缺失"）。

本周（{week_start}）基础数据：
- 实际咨询：{len(leads)}条，预测中位：{pred_leads}条
- 实际订单：{len(orders)}单
- 任务完成率：{int(completion_rate*100)}%（完成{task_stats.get('done',0)}/{task_stats.get('total',0)}）

各角色任务完成情况（推广部/学管/顾问/后台/管理层）：
{dept_lines}

学校咨询 Top3 实际 vs 预测：
{school_lines}

渠道问题（小红书/垂直号/推广/朋友圈/转介绍）：
{ch_issues}

角色执行问题（学管/顾问/推广部）：
{role_issues}

供给风险（老师资源/交付卡点）：
{supply_str}

管理决策卡点：
{mgmt_str}

执行反馈复盘（本周推送动作完成情况）：
- 总完成率：{(exec_completion or {}).get('rate', '未知')}%（{(exec_completion or {}).get('completed', '?')}/{(exec_completion or {}).get('total', '?')}）
- 各部门完成率：{json.dumps({k: v.get('rate') for k, v in (exec_completion or {}).get('by_dept',{}).items()}, ensure_ascii=False)}
- 主要偏差：{'; '.join((exec_completion or {}).get('top_deviations', [])) or '无记录'}

请按以下7个维度输出（每项1-2条，每条不超过35字，没有数据的维度写"本周无此类问题"）：

亮点：
- <本周做得好的1-2件事>
失落：
- <落差或遗漏>
归因（请区分是渠道问题/角色执行问题/产品问题/话术问题/供给风险/管理决策/执行未到位 哪类）：
- <[问题类型] 具体原因>
执行复盘（哪些预测正确/哪些预测错误/是数据问题还是执行问题）：
- <具体描述>
下周重点（角色+渠道+具体动作）：
- <角色｜渠道｜动作>
供给预警：
- <需要管理层注意的资源风险>
总结：<一句话60字内，指出本周最大问题和下周最需改变的一件事>
"""
        try:
            resp = self._router.generate_text(
                prompt, max_tokens=800, task_type="weekly_review"
            )
            if resp.success:
                return self._parse_review(resp.content.strip())
            logger.warning(f"[WeeklyReviewAgent] LLM failed: {resp.error}")
            return "复盘生成失败（AI不可用）", [], [], ["AI不可用，无法自动归因"], []
        except Exception as e:
            logger.warning(f"[WeeklyReviewAgent] gen failed: {e}")
            return "复盘生成失败", [], [], [], []

    @staticmethod
    def _parse_review(text: str) -> tuple:
        wins, misses, causes, focus, summary = [], [], [], [], ""
        current = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("亮点："):
                current = "wins"
            elif line.startswith("失落："):
                current = "misses"
            elif line.startswith("归因"):
                current = "causes"
            elif line.startswith("下周重点"):
                current = "focus"
            elif line.startswith("供给预警"):
                current = "supply"
            elif line.startswith("执行复盘"):
                current = "exec_review"
            elif line.startswith("总结："):
                summary = line[3:].strip()
                current = None
            elif line.startswith("- "):
                item = line[2:].strip()
                if current == "wins":    wins.append(item)
                elif current == "misses": misses.append(item)
                elif current in ("causes", "supply", "exec_review"): causes.append(item)
                elif current == "focus":  focus.append(item)
        return summary or text[:100], wins, misses, causes, focus
