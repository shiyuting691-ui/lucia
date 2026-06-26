"""
RiskReviewAgent — 对内容进行风险审查
输出：risk_level / risk_notes / safer_version / suggested_action
"""
import json
from anthropic import Anthropic

from agents.grounded_business_agent import GroundedBusinessAgent

SYSTEM_PROMPT = """你是一个教育行业内容合规审核员，专门审查留学辅导机构的营销内容。

审查维度（必须逐一检查）：
1. 过度承诺：是否承诺"100%通过""保证成绩"等无法兑现的结果
2. 平台风险：是否含有小红书/微信可能限流的词（最好/第一/最专业/保证等）
3. 交付风险：卖点承诺是否超过实际能力范围
4. 法律风险：是否涉及学历造假、代写等违规业务
5. 品牌调性：表达是否低端、用词是否准确、是否有语病
6. 价格风险：是否违反定价策略或透露不应公开的价格信息

风险等级：
- safe：无风险，可直接发布
- low：轻微风险，建议微调
- medium：中等风险，需要修改再发
- high：高风险，必须修改
- block：内容违规，不可发布"""


class RiskReviewAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model  = config["anthropic"]["model"]

    def review_content(self, content: dict) -> dict:
        """
        审查单条内容
        返回：{risk_level, risk_notes, safer_version, suggested_action}
        """
        body      = content.get("body", "") or content.get("content", "")
        title     = content.get("title", "")
        ctype     = content.get("content_type", "")
        product   = content.get("product_id") or content.get("product", "")

        if not body.strip():
            return {"risk_level": "safe", "risk_notes": [], "safer_version": "", "suggested_action": "内容为空，跳过审核"}

        prompt = f"""
请审查以下营销内容：

【标题】{title}
【类型】{ctype}
【产品】{product}
【正文】
{body[:1500]}

请输出 JSON：
{{
  "risk_level": "safe|low|medium|high|block",
  "risk_notes": ["风险点1（具体说明）", "风险点2"],
  "safer_version": "修改后的安全版本（只改有问题的部分，其余保持原文）",
  "suggested_action": "建议操作（如：直接通过/微调后可用/必须修改/不可发布）",
  "specific_changes": ["具体修改建议1", "具体修改建议2"]
}}

如果内容完全安全，risk_notes 返回空数组，safer_version 返回原文，suggested_action 返回"直接通过"。
只输出 JSON。
"""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```json")[-1].split("```")[0] if "```json" in raw \
                  else raw.split("```")[1].split("```")[0]
        try:
            return json.loads(raw.strip())
        except Exception:
            return {
                "risk_level": "low",
                "risk_notes": ["风险解析失败，请人工检查"],
                "safer_version": body,
                "suggested_action": "人工审核",
            }

    def batch_review(self, contents: list[dict]) -> list[dict]:
        """批量审查，返回每条内容的审查结果"""
        results = []
        for c in contents:
            result = self.review_content(c)
            result["content_id"] = c.get("id")
            result["content_title"] = c.get("title", "")
            results.append(result)
        return results
