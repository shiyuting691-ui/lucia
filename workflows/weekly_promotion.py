"""
WeeklyPromotionWorkflow — 周度推广建议工作流
触发方式：CLI run-weekly-promotion [--week 2026-06-09]
同时生成：销售建议 + 市场内容建议
"""
import logging
from datetime import datetime, timedelta
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class WeeklyPromotionWorkflow(BaseWorkflow):
    name = "weekly_promotion"

    def __init__(self, config: dict, week_start: str = None):
        super().__init__(config)
        if week_start:
            self.week_start = week_start
        else:
            today = datetime.now()
            self.week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

    def _run_steps(self) -> dict:
        from agents.weekly_sales_suggestion_agent import WeeklySalesSuggestionAgent
        from agents.weekly_marketing_suggestion_agent import WeeklyMarketingSuggestionAgent
        from agents.product_supply_risk_agent import ProductSupplyRiskAgent

        sales_result    = {}
        marketing_result= {}
        supply_result   = {}

        # Step 0: 产品供给与订单风险分析（为后续建议提供推广边界）
        try:
            supply_agent  = ProductSupplyRiskAgent(self.config)
            supply_result = supply_agent.analyze(period_days=14)
            self._add_step(
                "product_supply_risk_analysis",
                "success",
                records=1,
                note=f"week={self.week_start} orders={supply_result.get('order_count',0)}",
            )
            logger.info(f"[WeeklyPromotionWorkflow] supply risk analysis done")
        except Exception as e:
            self._add_step("product_supply_risk_analysis", "error", note=str(e))
            logger.error(f"[WeeklyPromotionWorkflow] supply risk step failed: {e}")

        # 从 supply_result 提取推广边界摘要（注入到下方建议的 extra_context）
        _boundary_summary = ""
        try:
            _boundaries = supply_result.get("promotion_boundary", [])
            _strong  = [b["product"] for b in _boundaries if b.get("push_level") == "strong"]
            _normal  = [b["product"] for b in _boundaries if b.get("push_level") == "normal"]
            _cautious= [b["product"] for b in _boundaries if b.get("push_level") == "cautious"]
            _pause   = [b["product"] for b in _boundaries if b.get("push_level") == "pause"]
            _boundary_summary = (
                f"本周推广边界（基于老师储备）：\n"
                f"  强推产品：{'、'.join(_strong) or '无'}\n"
                f"  正常推广：{'、'.join(_normal) or '无'}\n"
                f"  谨慎推广：{'、'.join(_cautious) or '无（需先确认老师档期）'}\n"
                f"  暂停强推：{'、'.join(_pause) or '无'}"
            )
        except Exception:
            pass

        # Step 1: 销售建议
        try:
            agent = WeeklySalesSuggestionAgent(self.config)
            sales_result = agent.generate(
                week_start=self.week_start,
                extra_context=_boundary_summary,
            )
            self._add_step(
                "generate_weekly_sales_suggestion",
                "success",
                records=1,
                note=f"week={self.week_start} suggestion_id={sales_result.get('suggestion_id')}",
            )
        except Exception as e:
            self._add_step("generate_weekly_sales_suggestion", "error", note=str(e))
            logger.error(f"[WeeklyPromotionWorkflow] sales step failed: {e}")

        # Step 2: 市场内容建议
        try:
            agent2 = WeeklyMarketingSuggestionAgent(self.config)
            marketing_result = agent2.generate(
                week_start=self.week_start,
                extra_context=_boundary_summary,
            )
            self._add_step(
                "generate_weekly_marketing_suggestion",
                "success",
                records=1,
                note=f"week={self.week_start} suggestion_id={marketing_result.get('suggestion_id')}",
            )
        except Exception as e:
            self._add_step("generate_weekly_marketing_suggestion", "error", note=str(e))
            logger.error(f"[WeeklyPromotionWorkflow] marketing step failed: {e}")

        return {
            "summary": f"周度推广建议生成完成：{self.week_start} ~ {sales_result.get('week_end', '')}，"
                       f"销售建议+市场内容建议各1份已保存。",
            "week_start": self.week_start,
            "sales_suggestion_id": sales_result.get("suggestion_id"),
            "marketing_suggestion_id": marketing_result.get("suggestion_id"),
        }
