"""
SalesMaterialAgent — 生成每日销售素材包
根据业务背景和当前活动，生成当日可用的销售话术/推文/社群消息
"""
import json
import logging
from datetime import datetime
import anthropic
from database import list_campaigns, save_content

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class SalesMaterialAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self._gba = GroundedBusinessAgent()

    def run(self, context: dict) -> dict:
        """
        根据业务背景生成每日销售素材包（朋友圈/社群/私信话术各 1 条）
        返回 {"contents_saved": N, "items": [...]}
        """
        _g = self._gba.get_context("sales_material")
        if not _g.get("can_generate"):
            return {"contents_saved": 0, "items": [],
                    "error": "公司事实库未确认，销售素材生成被阻止",
                    "can_generate": False,
                    "missing_info": _g.get("missing_information", [])}
        today = context.get("today", datetime.utcnow().strftime("%Y-%m-%d"))
        active_campaigns = context.get("active_campaigns", [])
        campaign_summary = (
            "、".join([c["name"] for c in active_campaigns])
            if active_campaigns
            else "无当前活动，以日常推广为主"
        )
        hot_schools  = context.get("hot_schools", [])
        hot_products = context.get("hot_products", [])
        upcoming     = context.get("upcoming_nodes", [])
        patterns     = context.get("current_patterns", [])

        intel_hint = ""
        if hot_schools:
            intel_hint += f"\n当前热门学校：{'、'.join(hot_schools[:3])}"
        if hot_products:
            intel_hint += f"\n当前热门产品：{'、'.join(hot_products[:3])}"
        if upcoming:
            node = upcoming[0]
            intel_hint += f"\n即将到来的节点：{node.get('school','')} {node.get('event_type','')} ({node.get('start_date','')[:10]})"
        if patterns:
            p = patterns[0]
            intel_hint += f"\n往年同期规律：{p.get('pattern_summary','')[:60]}"

        prompt = f"""你是一名专业的海外留学辅导机构（极致教育）营销文案专家。
今天是 {today}（{context.get('weekday', '')}），当前活跃活动：{campaign_summary}。{intel_hint}

请生成今日销售素材包，包含以下 3 种内容（每种 1 条，输出 JSON 数组）：
1. moments（朋友圈）：150字以内，自然真实，结尾带行动号召
2. group_msg（社群消息）：80字以内，直接友好，适合群发
3. sales_script（销售私信话术）：针对"还在考虑中"的潜在客户，150字以内

输出格式（JSON 数组，不要包含其他内容）：
[
  {{
    "content_type": "moments",
    "title": "朋友圈文案 {today}",
    "body": "...",
    "channel": "wechat",
    "target_country": "All",
    "call_to_action": "私信了解详情",
    "hashtags": ["#留学辅导", "#极致教育"],
    "suggested_use": "今日朋友圈发布"
  }},
  {{
    "content_type": "group_msg",
    "title": "社群消息 {today}",
    "body": "...",
    "channel": "group",
    "target_country": "All",
    "call_to_action": "点击链接或私信",
    "hashtags": [],
    "suggested_use": "今日社群推送"
  }},
  {{
    "content_type": "sales_script",
    "title": "销售话术 {today}",
    "body": "...",
    "channel": "referral",
    "target_country": "All",
    "call_to_action": "预约免费咨询",
    "hashtags": [],
    "suggested_use": "针对犹豫中客户的跟进话术"
  }}
]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=[
                    {
                        "type": "text",
                        "text": "你是极致教育留学辅导机构的营销文案专家，专注英国和澳洲留学辅导市场。生成的内容需真实、合规、有吸引力。只输出 JSON，不要有其他说明。",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            # 清理 markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            items = json.loads(raw)

            saved = []
            for item in items:
                item["status"] = "draft"
                item["market_period"] = f"daily_{today}"
                cid = save_content(item)
                saved.append({"id": str(cid), **item})

            logger.info(f"SalesMaterialAgent: saved {len(saved)} contents")
            return {"contents_saved": len(saved), "items": saved}

        except Exception as e:
            logger.error(f"SalesMaterialAgent error: {e}")
            return {"contents_saved": 0, "items": [], "error": str(e)}
