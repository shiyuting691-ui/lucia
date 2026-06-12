"""
DailyReminderWorkflow — 每日有效提醒工作流
触发方式：CLI run-daily-reminder [--date 2026-06-12]
轻量调用，推荐每日早上自动触发
"""
import logging
from datetime import datetime
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class DailyReminderWorkflow(BaseWorkflow):
    name = "daily_reminder"

    def __init__(self, config: dict, target_date: str = None):
        super().__init__(config)
        self.target_date = target_date or datetime.now().strftime("%Y-%m-%d")

    def _run_steps(self) -> dict:
        from agents.daily_effective_reminder_agent import DailyEffectiveReminderAgent

        try:
            agent = DailyEffectiveReminderAgent(self.config)
            result = agent.generate(target_date=self.target_date)
            self._add_step(
                "generate_daily_reminder",
                "success",
                records=1,
                note=f"date={self.target_date} suggestion_id={result.get('suggestion_id')} "
                     f"hot_leads={result.get('hot_leads')} overdue_tasks={result.get('overdue_tasks')}",
            )
            return {
                "summary": f"每日提醒生成完成：{self.target_date}，"
                           f"活跃线索{result.get('hot_leads',0)}个，"
                           f"超期任务{result.get('overdue_tasks',0)}个。",
                "target_date": self.target_date,
                "suggestion_id": result.get("suggestion_id"),
                "reminder_preview": result.get("reminder", "")[:200],
            }
        except Exception as e:
            self._add_step("generate_daily_reminder", "error", note=str(e))
            raise
