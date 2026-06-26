"""
ProductImprovementAgent — 基于销售反馈和客户异议，生成产品改进建议
输出写入 strategy_suggestions 表（suggestion_type = 产品优化）
"""
import json
from anthropic import Anthropic

SYSTEM_PROMPT = """你是一个教育产品经理，专注于留学辅导产品的持续优化。

你的任务：基于销售反馈、客户异议和交付问题，找到产品的薄弱环节，给出具体的改进方案。

重点关注：
- 客户为什么没买（价格/效果担忧/信任/对比竞品）
- 交付中出现了什么问题（老师匹配/进度/质量）
- 产品介绍是否清晰（客户常问什么问题）
- 保障机制是否足够强（退款/重学/效果承诺）
- 与竞争对手的差异化是否清晰

输出要具体、可执行，不要泛泛而谈。"""


class ProductImprovementAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model  = config["anthropic"]["model"]

    def generate_improvements(
        self,
        feedbacks: list  = None,
        usage_records: list = None,
        product_id: str  = None,
    ) -> list[dict]:
        """
        生成产品改进建议
        返回可写入 strategy_suggestions 的 list[dict]
        """
        context = self._build_context(feedbacks, usage_records, product_id)

        products = self.config.get("products", [])
        product_names = [p["name"] for p in products]
        if product_id:
            product_names = [p["name"] for p in products if p["id"] == product_id]

        prompt = f"""
{context}

请针对以下产品生成改进建议：{', '.join(product_names)}

输出 JSON 数组，每条建议包含：
{{
  "title": "改进建议标题（20字内）",
  "suggestion_type": "产品优化",
  "related_product": "具体产品名称",
  "related_country": "UK|Australia|通用",
  "related_school": "相关学校（可为空）",
  "insight": "发现的问题：基于反馈数据观察到什么（具体说明）",
  "recommendation": "改进方案：具体怎么做，谁负责，预期效果",
  "priority": "低|中|高|紧急",
  "source": "AI分析"
}}

生成2-5条高价值的改进建议，必须基于数据，不要凑数。
只输出 JSON 数组。
"""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```json")[-1].split("```")[0] if "```json" in raw \
                  else raw.split("```")[1].split("```")[0]
        try:
            improvements = json.loads(raw.strip())
        except Exception:
            improvements = self._fallback_improvements(product_id)

        for s in improvements:
            s.setdefault("suggestion_type", "产品优化")
            s.setdefault("source", "AI分析")
            s.setdefault("status", "new")

        return improvements

    def _build_context(self, feedbacks, usage_records, product_id):
        parts = ["## 产品反馈数据"]

        if feedbacks:
            # 按产品聚合反馈
            product_issues = {}
            for f in feedbacks:
                prod = f.get("related_product", "通用")
                if product_id and prod != product_id:
                    continue
                if prod not in product_issues:
                    product_issues[prod] = []
                product_issues[prod].append(f"{f.get('feedback_type','')}: {f.get('title','')}")

            for prod, issues in product_issues.items():
                parts.append(f"\n{prod} 相关反馈：")
                for issue in issues[:5]:
                    parts.append(f"  - {issue}")
        else:
            parts.append("暂无部门反馈数据，基于行业经验生成改进建议")

        if usage_records:
            need_optimize = [u for u in usage_records if u.get("result") in ("需优化", "无效")]
            if need_optimize:
                parts.append(f"\n内容使用中标记\"需优化\"的记录：{len(need_optimize)} 条")
                for u in need_optimize[:3]:
                    if u.get("feedback"):
                        parts.append(f"  - {u['feedback'][:100]}")

        # 加入产品信息
        for p in self.config.get("products", []):
            if not product_id or p["id"] == product_id:
                parts.append(f"\n{p['name']} 当前卖点：{', '.join(p.get('selling_points', [])[:3])}")
                parts.append(f"目标客群：{p.get('target','')}")

        return "\n".join(parts)

    def _fallback_improvements(self, product_id):
        return [
            {
                "title": "Final押题产品需补充效果保障说明",
                "suggestion_type": "产品优化",
                "related_product": "Final押题",
                "related_country": "通用",
                "related_school": "",
                "insight": "销售反馈客户最常问：押题押不中怎么办？当前产品说明缺乏清晰的保障机制描述，影响成交决策。",
                "recommendation": "1. 补充历史押题命中率数据\n2. 明确退款/重学保障条款\n3. 在销售手册中加入标准应对话术",
                "priority": "高",
                "source": "AI分析（fallback）",
            }
        ]
