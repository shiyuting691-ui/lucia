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
        from services.agent_runner import AgentRunner

        runner = AgentRunner(workflow_name=self.name)
        r = runner.run("DailyEffectiveReminderAgent",
                       lambda: DailyEffectiveReminderAgent(self.config).generate(
                           target_date=self.target_date),
                       input_summary=f"date={self.target_date}")
        self._add_step("generate_daily_reminder", r["status"], records=1,
                       note=r["error_message"] or f"date={self.target_date}")
        if r["status"] != "success":
            raise RuntimeError(r["error_message"] or f"DailyEffectiveReminderAgent {r['status']}")

        result = r["output"]
        return {
            "summary": f"每日提醒生成完成：{self.target_date}，"
                       f"活跃线索{result.get('hot_leads',0)}个，"
                       f"超期任务{result.get('overdue_tasks',0)}个。",
            "target_date": self.target_date,
            "suggestion_id": result.get("suggestion_id"),
            "reminder_preview": result.get("reminder", "")[:200],
        }
