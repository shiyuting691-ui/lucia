"""
DailyWorkflow — 每日自动化工作流（V4 升级版）
完整流程：
  1. SchoolMarketIntelligenceAgent  — 生成动态市场信号
  2. BusinessContextAgent           — 收集今日业务背景（整合动态信号）
  3. SalesMaterialAgent             — 根据热门学校/产品生成销售素材草稿
  4. FeedbackCollectorAgent         — 汇总高优先级反馈，生成战略建议
  5. DistributionAgent              — 推送企业微信日报

控制原则：所有生成内容为 draft 状态，需人工审核后才能发布
"""
import logging
from .base import BaseWorkflow
from agents import (
    SchoolMarketIntelligenceAgent, BusinessContextAgent,
    SalesMaterialAgent, FeedbackCollectorAgent, DistributionAgent,
)

logger = logging.getLogger(__name__)


class DailyWorkflow(BaseWorkflow):
    name = "DailyWorkflow"

    def _run_steps(self) -> dict:
        config = self.config

        # ── Step 1: 生成市场信号 ─────────────────────────────────
        intel_result = {}
        try:
            intel_agent = SchoolMarketIntelligenceAgent(config)
            intel_result = intel_agent.run()
            n = intel_result.get("signals_saved", 0)
            self._add_step(
                "SchoolMarketIntelligenceAgent",
                "ok" if not intel_result.get("error") else "error",
                records=n,
                note=f"signals={n}, hot_schools={intel_result.get('hot_schools',[])}",
            )
        except Exception as e:
            self._add_step("SchoolMarketIntelligenceAgent", "error", note=str(e))

        # ── Step 2: 收集业务背景 ─────────────────────────────────
        try:
            context_agent = BusinessContextAgent(config)
            context = context_agent.run()
            self._add_step(
                "BusinessContextAgent", "ok", records=0,
                note=f"today={context.get('today')}, "
                     f"hot_schools={context.get('hot_schools',[][:3])}, "
                     f"signals={len(context.get('market_signals',[]))}",
            )
        except Exception as e:
            self._add_step("BusinessContextAgent", "error", note=str(e))
            context = {
                "today": "", "hot_schools": [], "hot_products": [],
                "active_campaigns": [], "open_tasks_count": 0,
                "open_feedbacks_count": 0, "urgent_feedbacks": [],
                "market_signals": [], "current_patterns": [],
            }

        # ── Step 3: 生成销售素材（带市场信号） ──────────────────
        try:
            sales_agent = SalesMaterialAgent(config)
            sales_result = sales_agent.run(context)
            n = sales_result.get("contents_saved", 0)
            self._add_step(
                "SalesMaterialAgent",
                "ok" if not sales_result.get("error") else "error",
                records=n, note=f"{n} drafts saved",
            )
        except Exception as e:
            self._add_step("SalesMaterialAgent", "error", note=str(e))
            sales_result = {"contents_saved": 0, "items": []}

        # ── Step 4: 汇总反馈 ─────────────────────────────────────
        try:
            feedback_agent = FeedbackCollectorAgent(config)
            feedback_result = feedback_agent.run(context)
            self._add_step(
                "FeedbackCollectorAgent",
                "ok" if not feedback_result.get("error") else "error",
                records=feedback_result.get("suggestions_saved", 0),
                note=f"reviewed={feedback_result.get('feedbacks_reviewed',0)}, "
                     f"suggestions={feedback_result.get('suggestions_saved',0)}",
            )
        except Exception as e:
            self._add_step("FeedbackCollectorAgent", "error", note=str(e))
            feedback_result = {"feedbacks_reviewed": 0, "suggestions_saved": 0}

        # ── Step 5: 推送企业微信 ─────────────────────────────────
        try:
            dist_agent = DistributionAgent(config)
            pushed = dist_agent.push_daily_summary_v4(context, sales_result, feedback_result, intel_result)
            self._add_step("DistributionAgent", "ok" if pushed else "error",
                           note="wecom push " + ("ok" if pushed else "failed"))
        except Exception as e:
            self._add_step("DistributionAgent", "error", note=str(e))

        # ── 汇总 ─────────────────────────────────────────────────
        total_contents    = sales_result.get("contents_saved", 0)
        total_suggestions = feedback_result.get("suggestions_saved", 0)
        total_signals     = intel_result.get("signals_saved", 0)
        hot_schools = context.get("hot_schools", [])
        summary = (
            f"每日工作流完成 · {context.get('today', '')}：\n"
            f"  · 市场信号 {total_signals} 条 | 热门学校: {', '.join(hot_schools[:3]) or '暂无'}\n"
            f"  · 新增内容草稿 {total_contents} 条\n"
            f"  · 新增战略建议 {total_suggestions} 条\n"
            f"  · 待处理任务 {context.get('open_tasks_count', 0)} 条\n"
            f"  · 待处理反馈 {context.get('open_feedbacks_count', 0)} 条"
        )

        return {
            "summary": summary,
            "context": context,
            "intel_result": intel_result,
            "sales_result": sales_result,
            "feedback_result": feedback_result,
        }
