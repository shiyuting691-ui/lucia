"""RuleFallback Provider.

止血规则：LLM 不可用时只返回 no_data，不生成业务结论、行动建议或复盘判断。
"""
import json
import logging
from typing import Optional

from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

class RuleFallbackProvider(BaseLLMProvider):
    provider_name = "rule_fallback"

    def is_configured(self) -> bool:
        return True  # 永远可用

    def health_check(self) -> dict:
        return {"status": "success", "available": True, "provider": "rule_fallback"}

    def generate_text(self, prompt: str, system_prompt=None,
                      temperature: float = 0.2, max_tokens: int = 2000) -> LLMResponse:
        # 根据 prompt 关键词判断任务类型，生成对应文字兜底
        content = self._route_text(prompt)
        logger.info(f"[rule_fallback] generate_text (fallback)")
        return LLMResponse(success=True, content=content,
                           provider="rule_fallback", model="rule_based")

    def generate_json(self, prompt: str, system_prompt=None,
                      temperature: float = 0.1, max_tokens: int = 2000) -> LLMResponse:
        data = self._route_json(prompt)
        logger.info(f"[rule_fallback] generate_json (fallback)")
        return LLMResponse(success=True, content=json.dumps(data, ensure_ascii=False),
                           json_data=data, provider="rule_fallback", model="rule_based")

    # ── 路由 ─────────────────────────────────────────────────────────────────
    def _route_text(self, prompt: str) -> str:
        p = prompt.lower()
        if "今日执行提醒" in prompt or "今日有效提醒" in prompt or "daily_reminder" in p:
            return self._daily_reminder_text()
        if "周度" in prompt or "本周" in prompt or "weekly" in p:
            return self._weekly_suggestion_text()
        if "知识库文档" in prompt or "摘要" in prompt or "knowledge" in p:
            return self._knowledge_summary_text()
        return self._generic_text()

    def _route_json(self, prompt: str) -> dict:
        p = prompt.lower()
        if "promotion_team" in p or "推广部" in p or "动作" in p or "action" in p:
            return self._no_data_json("AI模型不可用，规则兜底不生成行动建议")
        if "复盘" in p or "review" in p:
            return self._no_data_json("AI模型不可用，规则兜底不生成复盘结论")
        return self._no_data_json("所有AI模型不可用，且无可验证数据")

    # ── 具体兜底内容 ──────────────────────────────────────────────────────────
    def _action_plan_json(self) -> dict:
        return self._no_data_json("AI模型不可用，规则兜底不生成行动建议")

    @staticmethod
    def _no_data_json(reason: str) -> dict:
        return {
            "no_data": True,
            "validation_status": "no_data",
            "reason": reason,
            "evidence": [],
            "confidence": "no_data",
            "responsible_role": "",
            "_meta": {"provider": "rule_fallback"},
        }

    def _weekly_review_json(self) -> dict:
        return self._no_data_json("AI模型不可用，规则兜底不生成复盘结论")

    def _weekly_review_text(self) -> str:
        return self._generic_text()

    def _daily_report_text(self) -> str:
        return self._generic_text()

    def _daily_reminder_text(self) -> str:
        return (
            "【今日执行提醒】\n\n"
            "推广部：\n- AI模型暂不可用，请先查看真实线索和订单数据。\n\n"
            "学管：\n- AI模型暂不可用，请优先检查交付风险和DDL订单。\n\n"
            "顾问：\n- AI模型暂不可用，请优先跟进超时线索和高意向客户。\n\n"
            "后台：\n- AI模型暂不可用，请检查资料库、产品边界和系统日志。\n\n"
            "管理层：\n- AI模型暂不可用，暂不生成经营判断或决策建议。"
        )

    def _weekly_suggestion_text(self) -> str:
        return (
            "AI模型暂不可用，系统已进入规则兜底模式。\n\n"
            "- 不生成未经验证的推广结论。\n"
            "- 请先查看订单、线索、产品红绿灯和老师容量等真实数据。\n"
            "- 恢复模型配置后，可重新生成周度建议。"
        )

    def _knowledge_summary_text(self) -> str:
        return (
            "{\"summary\":\"AI模型暂不可用，未生成自动摘要。\","
            "\"keywords\":[],\"related_products\":[],\"related_scenarios\":[]}"
        )

    def _generic_text(self) -> str:
        return "暂无真实数据，无法判断。"
