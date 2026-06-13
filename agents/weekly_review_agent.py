"""
WeeklyReviewAgent — 周复盘生成

对比当周预测 vs 实际数据，分析部门任务执行完成情况，
由 Claude 撰写归因分析和下周重点，写入 weekly_reviews。
"""
import logging
from datetime import datetime, timedelta
import anthropic

from database import (
    list_campaign_predictions, list_orders, list_leads,
    get_task_execution_stats, save_weekly_review,
)

logger = logging.getLogger(__name__)


class WeeklyReviewAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6") if config else "claude-sonnet-4-6"

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

        # ── 4. Claude 生成复盘文字 ────────────────────────────────────
        review_summary, key_wins, key_misses, root_causes, next_focus = \
            self._gen_review(week_start, actual_leads, actual_orders,
                             pred_leads_mid, task_stats, school_breakdown)

        data = {
            "review_week":             week_start,
            "total_leads_predicted":   pred_leads_mid,
            "total_leads_actual":      len(actual_leads),
            "total_orders_predicted":  0,   # 暂不预测订单，下版本补充
            "total_orders_actual":     len(actual_orders),
            "school_breakdown":        school_breakdown,
            "product_breakdown":       [],
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
            "generated_by":            "WeeklyReviewAgent",
        }
        save_weekly_review(data)
        logger.info(f"[WeeklyReviewAgent] review saved for {week_start}")
        return data

    def _gen_review(self, week_start, leads, orders, pred_leads, task_stats, school_bd) -> tuple:
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

        prompt = f"""请对以下本周数据做简短复盘（全部基于数据，不编造，数据不足时直接说明）：

本周（{week_start}）数据：
- 实际咨询：{len(leads)}条，预测中位：{pred_leads}条
- 实际订单：{len(orders)}单
- 任务完成率：{int(completion_rate*100)}%（完成{task_stats.get('done',0)}/{task_stats.get('total',0)}，delayed={task_stats.get('delayed',0)}, blocked={task_stats.get('blocked',0)}）

部门完成情况：
{dept_lines}

学校咨询 Top3 实际 vs 预测：
{school_lines}

请输出以下格式（每项1-3条，每条不超过30字）：
亮点：
- <亮点1>
失落：
- <落差1>
归因：
- <原因1>
下周重点：
- <重点1>
总结：<一句话50字内总结>
"""
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text_out = resp.content[0].text.strip()
            return self._parse_review(text_out)
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
            elif line.startswith("归因："):
                current = "causes"
            elif line.startswith("下周重点："):
                current = "focus"
            elif line.startswith("总结："):
                summary = line[3:].strip()
                current = None
            elif line.startswith("- "):
                item = line[2:].strip()
                if current == "wins":    wins.append(item)
                elif current == "misses": misses.append(item)
                elif current == "causes": causes.append(item)
                elif current == "focus":  focus.append(item)
        return summary or text[:100], wins, misses, causes, focus
