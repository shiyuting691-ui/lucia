"""
ActionPlanner — 动作拆解器（LLMRouter版）

将 DecisionEngine 的输出转化为各部门具体执行动作。
调用链：LLMRouter → DeepSeek/Claude/RuleFallback
"""
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一家留学辅导机构（极致教育）的增长运营决策助手。

职责：将市场机会和数据分析，转化为各部门今天/本周必须执行的具体动作。

核心原则（必须严守）：
1. 每条动作必须可执行（有量化目标、有截止时间）
2. 每条动作必须有责任部门
3. 每条动作必须有优先级（P0/P1/P2）
4. 不允许只说"加强跟进"——必须说"今天联系哪类客户、怎么说、要达到什么结果"
5. 禁止动作必须明确写出

部门定义：
- 推广部（promotion_team）：内容创作、小红书/朋友圈/垂直号投放、拉新引流
- 顾问（consultant）：客资跟进、报价转化、成交
- 学管（xueguan）：承接新单、老师匹配、交付质量、产品风险判断
- 后台（backend）：数据录入、风控、产品边界管理
- 管理层（management）：资源决策、产品上下架、强推/暂停决策

【顾问和学管必须严格分开，不能混用】

输出必须是合法 JSON：
{
  "promotion_team": [{"action":"","quantity":"","deadline":"","content_type":"","school":"","product":"","priority":"P0"}],
  "consultant":     [{"action":"","target_leads":"","talk_track":"","deal_target":"","priority":"P0"}],
  "xueguan":        [{"action":"","capacity_note":"","risk_monitor":"","priority":"P0"}],
  "backend":        [{"action":"","priority":"P1"}],
  "management":     [{"decision":"","options":["",""],"priority":"P0"}]
}
每个部门至少2条动作，P0必须今天执行，P1本周内，P2本周预备。"""


class ActionPlanner:
    def __init__(self, config: dict = None):
        self.config = config or {}
        from services.llm import LLMRouter
        self._router = LLMRouter()

    def plan(self, decision: dict) -> dict:
        prompt = self._build_prompt(decision)
        logger.info("[ActionPlanner] calling LLMRouter.generate_json")

        resp = self._router.generate_json(
            prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=3000,
            task_type="action_planner",
        )

        if resp.success and resp.json_data:
            plan = resp.json_data
        else:
            logger.warning(f"[ActionPlanner] LLM failed ({resp.error}), using rule fallback")
            plan = self._fallback_plan(decision)

        plan["_provider"]     = resp.provider
        plan["generated_at"]  = datetime.utcnow().isoformat()
        return plan

    def _build_prompt(self, decision: dict) -> str:
        summary = decision.get("data_summary", {})
        phase   = decision.get("phase_now", {})
        opps    = decision.get("top_opportunities", [])
        forb    = decision.get("forbidden_actions", [])
        risks   = decision.get("risks", [])
        cap     = decision.get("resource_status", "green")

        opp_text = "\n".join(
            f"  - [{o.get('priority')}] {o.get('product_name','')}：{o.get('reason','')} （预期线索:{o.get('expected_leads',0)}）"
            for o in opps
        ) or "  - 暂无明确机会"

        forb_text = "\n".join(
            f"  - ⛔ {f.get('action','')}: {f.get('reason','')}"
            for f in forb
        ) or "  - 无"

        risk_text = "\n".join(
            f"  - [{r.get('severity','?').upper()}] {r.get('type','')}：{r.get('description','')}"
            for r in risks
        ) or "  - 无"

        return f"""根据以下数据，为各部门生成本周具体执行动作：

【学生需求阶段】
- 英国留学生：{phase.get('uk_phase', '')}
- 澳洲留学生：{phase.get('au_phase', '')}
- 需求紧迫度：{phase.get('urgency', '中')}
- 本周主推产品：{phase.get('hot_products', [])}
- 营销角度：{phase.get('messaging_angle', '')}

【本周TOP机会】
{opp_text}

【资源状态】
老师容量：{cap}（green=充足/yellow=偏紧/red=紧张/blocked=满员）

【禁止行为】
{forb_text}

【风险预警】
{risk_text}

【核心数据】
- 活跃线索：{summary.get('active_leads', 0)} 条
- 超时线索：{summary.get('overdue_leads', 0)} 条（顾问今日必处理）
- 近7天订单：{summary.get('orders_last_7d', 0)} 单（vs 前7天 {summary.get('orders_prev_7d', 0)} 单，趋势：{'+' if (summary.get('order_trend',0) or 0) > 0 else ''}{summary.get('order_trend', 0)}）

请生成各部门今天/本周必须执行的具体动作（JSON格式）。动作必须量化，不允许写"加强"等模糊词。顾问和学管必须严格分开。"""

    def _fallback_plan(self, decision: dict) -> dict:
        from services.llm.rule_fallback_provider import RuleFallbackProvider
        resp = RuleFallbackProvider().generate_json("")
        return resp.json_data or {}
