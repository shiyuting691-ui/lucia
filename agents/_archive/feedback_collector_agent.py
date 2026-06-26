"""
FeedbackCollectorAgent — 汇总当日反馈摘要
读取未处理反馈，用 LLM 生成摘要和优先处理建议
"""
import json
import logging
from datetime import datetime
import anthropic
from database import list_feedbacks, save_suggestion

logger = logging.getLogger(__name__)


class FeedbackCollectorAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    def run(self, context: dict) -> dict:
        """
        汇总开放反馈，生成摘要，高优先级反馈自动创建战略建议
        返回 {"feedbacks_reviewed": N, "suggestions_saved": N}
        """
        feedbacks = list_feedbacks(status="open")
        if not feedbacks:
            logger.info("FeedbackCollectorAgent: no open feedbacks")
            return {"feedbacks_reviewed": 0, "suggestions_saved": 0}

        # 只处理高/紧急反馈
        urgent = [f for f in feedbacks if f.get("urgency") in ("高", "紧急")]
        if not urgent:
            logger.info(f"FeedbackCollectorAgent: {len(feedbacks)} feedbacks, none urgent")
            return {"feedbacks_reviewed": len(feedbacks), "suggestions_saved": 0}

        feedback_text = "\n".join(
            [f"- [{f.get('urgency','')}] {f.get('department','')} | {f.get('title','')}：{f.get('content','')[:100]}"
             for f in urgent[:5]]
        )

        prompt = f"""以下是今日高优先级部门反馈（{context.get('today','')}）：

{feedback_text}

请针对这些反馈，生成 1-2 条战略建议，帮助管理层快速决策。
输出 JSON 数组：
[
  {{
    "title": "建议标题",
    "suggestion_type": "产品优化|销售策略|市场机会|风控提醒",
    "related_product": "相关产品（如有）",
    "related_country": "UK|Australia|All",
    "insight": "问题背景和洞察",
    "recommendation": "具体行动建议（2-3 条）",
    "priority": "高|紧急"
  }}
]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1200,
                system=[
                    {
                        "type": "text",
                        "text": "你是极致教育的运营战略顾问，帮助管理层快速处理部门反馈并给出可执行建议。只输出 JSON，不要其他说明。",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            suggestions = json.loads(raw)

            saved = 0
            for s in suggestions:
                s["source"] = "AI生成-反馈汇总"
                s["status"] = "new"
                save_suggestion(s)
                saved += 1

            logger.info(f"FeedbackCollectorAgent: {len(urgent)} urgent feedbacks → {saved} suggestions")
            return {"feedbacks_reviewed": len(feedbacks), "suggestions_saved": saved}

        except Exception as e:
            logger.error(f"FeedbackCollectorAgent error: {e}")
            return {"feedbacks_reviewed": len(feedbacks), "suggestions_saved": 0, "error": str(e)}
