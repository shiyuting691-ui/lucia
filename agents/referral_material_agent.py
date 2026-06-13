"""
ReferralMaterialAgent — 生成转介绍话术、朋友圈文案、群发消息
"""
import json
from anthropic import Anthropic
from agents.grounded_business_agent import GroundedBusinessAgent


SYSTEM_PROMPT = """你是一个专业的留学教育顾问和文案专家。
你深度理解中国留学生家长和学生的心理，能写出真实、有温度、不让人反感的转介绍话术。

写作风格：
- 转介绍话术：像朋友推荐，不像广告，真诚+利益点双驱动
- 朋友圈文案：有生活感，不硬广，让人想点赞
- 群发消息：简洁、有明确行动指引，不废话
- 所有文案禁止夸大，不能违规承诺（如"保证过"等绝对化表述改为"高通过率"）"""


class ReferralMaterialAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model = config["anthropic"]["model"]
        self._product_map = {p["id"]: p for p in config["products"]}
        self._gba = GroundedBusinessAgent()

    def generate_referral_kit(self, product_id: str, school: str = None, country: str = None) -> dict:
        _g = self._gba.get_context("content_generation")
        if not _g.get("can_generate"):
            return {"error": "公司事实库未确认，转介绍素材生成被阻止",
                    "can_generate": False,
                    "missing_info": _g.get("missing_information", [])}
        """生成一套完整的转介绍素材包"""
        product = self._product_map.get(product_id, {})
        context = self._build_context(product, school, country)

        prompt = f"""
请为以下场景生成完整的转介绍素材包：

{context}

请输出以下所有内容（JSON格式）：
{{
  "referral_scripts": {{
    "student_to_student": "学生推荐给学生的话术（微信私聊场景，100-150字）",
    "student_to_parent": "学生/家长推荐给其他家长的话术（150-200字）",
    "short_version": "30字内的简短推荐语（适合复制转发）"
  }},
  "wechat_moments": [
    {{
      "style": "晒成绩/结果型",
      "content": "朋友圈文案（带配图建议）"
    }},
    {{
      "style": "干货分享型",
      "content": "朋友圈文案（带配图建议）"
    }},
    {{
      "style": "限时活动型",
      "content": "朋友圈文案（带配图建议）"
    }}
  ],
  "group_messages": {{
    "xueguan_group": "学管群发消息（针对老客户，150字内）",
    "consultant_group": "顾问群发话术（获客/跟进使用，100字内）",
    "new_lead_first_msg": "新咨询客户第一条消息（引导付费，80字内）"
  }},
  "follow_up_sequence": [
    {{
      "timing": "未回复1天后",
      "message": "跟进消息"
    }},
    {{
      "timing": "未回复3天后",
      "message": "跟进消息"
    }}
  ],
  "referral_incentive_copy": "介绍有礼活动文案（如有激励机制）"
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            kit_data = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            kit_data = {"raw_output": raw, "parse_error": True}

        kit_data["product_id"] = product_id
        kit_data["product_name"] = product.get("name", "")
        kit_data["school"] = school or "通用"
        kit_data["country"] = country or "通用"
        return kit_data

    def generate_seasonal_campaign(self, season: str, target_country: str = None) -> dict:
        """生成季节性营销活动素材（开学季/考试季/毕业季）"""
        schools_info = ""
        if target_country == "英国":
            schools = self.config["schools"]["uk"]
        elif target_country == "澳洲":
            schools = self.config["schools"]["australia"]
        else:
            schools = self.config["schools"]["uk"] + self.config["schools"]["australia"]

        school_names = "、".join([s["name"] for s in schools[:6]])

        prompt = f"""
当前营销季节：{season}
目标国家：{target_country or '英国+澳洲'}
目标学校：{school_names}等

请生成一套{season}营销活动素材：
{{
  "campaign_name": "活动名称",
  "campaign_slogan": "活动口号（10字内）",
  "core_message": "核心传播信息",
  "xiaohongshu_series": [
    {{"day": 1, "title": "系列笔记1标题", "direction": "内容方向"}},
    {{"day": 3, "title": "系列笔记2标题", "direction": "内容方向"}},
    {{"day": 7, "title": "系列笔记3标题", "direction": "内容方向"}}
  ],
  "group_push_sequence": [
    {{"timing": "活动第1天", "message": "群推文案"}},
    {{"timing": "活动第3天", "message": "群推文案"}},
    {{"timing": "活动最后一天", "message": "收尾文案"}}
  ],
  "referral_hook": "转介绍钩子话术"
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            campaign_data = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            campaign_data = {"raw_output": raw, "parse_error": True}

        campaign_data["season"] = season
        campaign_data["country"] = target_country or "通用"
        return campaign_data

    def _build_context(self, product: dict, school: str, country: str) -> str:
        lines = [
            f"产品：{product.get('name', '')}",
            f"产品描述：{product.get('description', '')}",
            f"核心卖点：{json.dumps(product.get('selling_points', []), ensure_ascii=False)}",
            f"目标客群：{product.get('target', '')}",
            f"价格区间：{product.get('price_range', '')}",
        ]
        if school:
            lines.append(f"目标学校：{school}")
        if country:
            lines.append(f"目标国家：{country}")
        return "\n".join(lines)
