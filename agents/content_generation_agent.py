"""
ContentGenerationAgent — 基于内容日历批量生成小红书笔记
"""
import json
import asyncio
from anthropic import Anthropic

from agents.grounded_business_agent import GroundedBusinessAgent


SYSTEM_PROMPT = """你是一个专业的小红书内容创作者，专注留学辅导赛道。
你熟悉小红书的内容规则、爆款笔记结构和留学生的阅读习惯。

创作原则：
1. 标题：抓眼球，带数字/emoji/疑问句，15字以内
2. 开头：前两行就点出痛点或利益点（用户不展开就能看到）
3. 正文：干货为主，少废话，结构清晰（分点/分段）
4. 结尾：引导评论或私信（"有同款困惑的扣1"/"私信我领资料"）
5. 标签：精准+泛流量结合，10-15个
6. 禁止：过度承诺、夸大效果、违规宣传

语气：像学长学姐在分享经验，专业但不高冷"""


class ContentGenerationAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model = config["anthropic"]["model"]
        self._product_map = {p["id"]: p for p in config["products"]}

    def generate_posts_from_calendar(self, calendar: dict, max_posts: int = 10) -> list[dict]:
        """从日历节点批量生成小红书帖子"""
        nodes = calendar.get("key_nodes", [])[:max_posts]
        posts = []
        for node in nodes:
            post = self._generate_single_post(node, calendar.get("calendar_summary", ""))
            posts.append(post)
        return posts

    def generate_single_post(self, topic: str, product_id: str, school: str = None, country: str = None) -> dict:
        """按需生成单篇小红书笔记"""
        product = self._product_map.get(product_id, {})
        node = {
            "theme": topic,
            "recommended_product": product_id,
            "school_focus": [school] if school else [],
            "country": country or "通用",
            "xiaohongshu_angle": topic,
        }
        return self._generate_single_post(node, "")

    def _generate_single_post(self, node: dict, calendar_summary: str) -> dict:
        product_id = node.get("recommended_product", "regular")
        product = self._product_map.get(product_id, {})
        school_focus = "、".join(node.get("school_focus", [])) or "留学生通用"

        prompt = f"""
请为以下节点生成一篇完整的小红书笔记：

内容节点信息：
- 日期：{node.get('date', '近期')}
- 主题：{node.get('theme', '')}
- 目标受众：{school_focus}（{node.get('country', '通用')}）
- 内容方向：{node.get('content_direction', '')}
- 小红书切入角度：{node.get('xiaohongshu_angle', '')}
- 推广产品：{product.get('name', '')} — {product.get('description', '')}
- 产品卖点：{json.dumps(product.get('selling_points', []), ensure_ascii=False)}
- 紧迫程度：{node.get('urgency', '')}

请输出完整的小红书帖子内容（JSON格式）：
{{
  "title": "笔记标题（带emoji，15字内）",
  "cover_text": "封面文案（5-8字，大字报风格）",
  "body": "正文全文（含emoji、分段、干货内容，300-500字）",
  "hashtags": ["标签1", "标签2", ...],
  "call_to_action": "引导话术",
  "post_timing": "建议发布时间段（如：晚8-10点）",
  "estimated_engagement": "预计互动方向（评论/收藏/私信）"
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
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
            post_data = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            post_data = {"raw_output": raw, "parse_error": True}

        post_data["node_date"] = node.get("date", "")
        post_data["node_theme"] = node.get("theme", "")
        post_data["product_id"] = product_id
        post_data["school_focus"] = school_focus
        post_data["urgency"] = node.get("urgency", "")
        return post_data

    def generate_batch_by_product(self, product_id: str, count: int = 5) -> list[dict]:
        """针对特定产品批量生产推广素材"""
        product = self._product_map.get(product_id, {})
        angles = [
            f"{product['name']}的真实使用体验分享",
            f"为什么选{product['name']}而不是自己硬撑",
            f"用了{product['name']}之后成绩变化",
            f"{product['name']}适合哪类同学",
            f"学长学姐推荐：{product['name']}避坑指南",
        ]
        posts = []
        for i, angle in enumerate(angles[:count]):
            node = {
                "theme": angle,
                "recommended_product": product_id,
                "school_focus": [],
                "country": "通用",
                "xiaohongshu_angle": angle,
                "content_direction": f"从真实用户视角分享{product['name']}的价值",
                "urgency": "🟢铺垫",
            }
            posts.append(self._generate_single_post(node, ""))
        return posts
