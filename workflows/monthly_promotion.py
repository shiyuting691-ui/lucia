"""
MonthlyPromotionWorkflow — 月度推广策略工作流
触发方式：CLI run-monthly-promotion [--month 2026-07]
"""
import logging
from datetime import datetime
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class MonthlyPromotionWorkflow(BaseWorkflow):
    name = "monthly_promotion"

    def __init__(self, config: dict, target_month: str = None):
        super().__init__(config)
        self.target_month = target_month or datetime.now().strftime("%Y-%m")

    def _run_steps(self) -> dict:
        from agents.promotion_strategy_agent import PromotionStrategyAgent

        # Step 1: 生成月度推广策略
        try:
            agent = PromotionStrategyAgent(self.config)
            result = agent.generate(target_month=self.target_month)
            self._add_step(
                "generate_monthly_strategy",
                "success",
                records=1,
                note=f"月份={self.target_month} campaign_id={result.get('campaign_id')} "
                     f"suggestion_id={result.get('suggestion_id')}",
            )
            return {
                "summary": f"月度推广策略生成完成：{self.target_month}，"
                           f"{'数据充足' if result.get('data_sufficient') else '数据有限（建议补充历史数据）'}，"
                           f"已保存策略报告。",
                "target_month": self.target_month,
                "campaign_id": result.get("campaign_id"),
                "suggestion_id": result.get("suggestion_id"),
                "strategy_preview": result.get("strategy", "")[:300],
            }
        except Exception as e:
            self._add_step("generate_monthly_strategy", "error", note=str(e))
            raise
