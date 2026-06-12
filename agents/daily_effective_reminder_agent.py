"""
DailyEffectiveReminderAgent — 每日有效提醒
输入：今日日期、线索状态、任务状态、市场信号
输出：销售/市场/学管 今日最重要的3-5条行动提醒
注意：轻量化调用，max_tokens=600，不使用 thinking
"""
import logging
from datetime import datetime, timedelta
import anthropic
from database import list_leads, list_tasks, list_market_signals, save_suggestion

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class DailyEffectiveReminderAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    def generate(self, target_date: str = None) -> dict:
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[DailyEffectiveReminderAgent] generating for {target_date}")

        # 轻量数据收集
        leads = list_leads(limit=30)
        tasks = list_tasks(limit=30)
        signals = list_market_signals(limit=5)

        # 今日到期/超期线索
        today = datetime.strptime(target_date, "%Y-%m-%d")
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        hot_leads = [l for l in leads if l.get("status") in ("new", "contacted", "negotiating")]
        overdue_tasks = [t for t in tasks
                         if t.get("status") == "pending"
                         and t.get("due_date") and str(t.get("due_date"))[:10] <= target_date]
        urgent_signals = [s for s in signals if s.get("urgency_level") in ("high", "critical")]

        hot_leads_str = "\n".join(
            f"  {l.get('name','')} {l.get('school','')} {l.get('product','')} "
            f"最近联系:{str(l.get('last_contact_at',''))[:10]}"
            for l in hot_leads[:8]
        ) or "  无"

        overdue_str = "\n".join(
            f"  [{t.get('task_type','')}] {t.get('title','')} 负责:{t.get('owner','')} 到期:{str(t.get('due_date',''))[:10]}"
            for t in overdue_tasks[:5]
        ) or "  无"

        urgent_signals_str = "\n".join(
            f"  {s.get('title','')} — {s.get('description','')[:60]}"
            for s in urgent_signals
        ) or "  无"

        prompt = f"""今天是{target_date}，请为留学机构团队生成今日最重要的行动提醒（简洁，5条以内）。

活跃线索（{len(hot_leads)}个）：
{hot_leads_str}

待处理/超期任务（{len(overdue_tasks)}个）：
{overdue_str}

紧急市场信号：
{urgent_signals_str}

请用以下格式输出（纯文本，不用Markdown标题）：

今日提醒 {target_date}

🔴 [紧急] xxx
🟡 [重要] xxx
🟢 [跟进] xxx

每条限20字内，直接告诉团队做什么，不要废话。"""

        result_text = ""
        # 轻量调用：不用 thinking，不用 streaming
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = resp.content[0].text
        except Exception as e:
            logger.error(f"[DailyEffectiveReminderAgent] error: {e}")
            result_text = f"生成失败：{e}"

        suggestion_id = save_suggestion(
            suggestion_type="daily_reminder",
            title=f"{target_date} 每日有效提醒",
            content=result_text,
            data_basis={
                "target_date": target_date,
                "hot_leads": len(hot_leads),
                "overdue_tasks": len(overdue_tasks),
                "urgent_signals": len(urgent_signals),
            },
            priority="medium",
        )

        return {
            "target_date": target_date,
            "reminder": result_text,
            "suggestion_id": suggestion_id,
            "hot_leads": len(hot_leads),
            "overdue_tasks": len(overdue_tasks),
        }
