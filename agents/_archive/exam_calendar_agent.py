"""
ExamCalendarAgent — 基于学校考试节点生成30天内容日历
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic


SYSTEM_PROMPT = """你是一个专业的留学教育营销策划专家，熟悉英国和澳洲各大高校的学制、考试周期和学生痛点。
你的任务是基于当前日期和学校考试节点，生成精准的内容营销日历。

输出要求：
- 内容节点要贴合真实考试周期（英国：1月/5-6月；澳洲：6月/11-12月）
- 每个内容节点包含：日期、主题、内容方向、推荐产品、紧迫程度
- 紧迫程度：🔴紧急（距考试<2周）/ 🟡预热（2-4周）/ 🟢铺垫（>4周）
- 输出JSON格式"""


class ExamCalendarAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model = config["anthropic"]["model"]

    def generate_calendar(self, days: int = 30) -> dict:
        """生成未来N天的内容日历"""
        today = datetime.now()
        schools_info = self._build_schools_context()
        products_info = self._build_products_context()

        prompt = f"""
当前日期：{today.strftime('%Y年%m月%d日')}
需要规划的时间范围：未来{days}天（到{(today + timedelta(days=days)).strftime('%Y年%m月%d日')}）

目标学校信息：
{schools_info}

产品线：
{products_info}

请生成一个{days}天的内容日历，识别关键考试节点，为每个节点规划营销内容方向。

输出格式（JSON）：
{{
  "calendar_summary": "本月核心营销主题概述",
  "key_nodes": [
    {{
      "date": "YYYY-MM-DD",
      "urgency": "🔴紧急/🟡预热/🟢铺垫",
      "school_focus": ["学校名"],
      "country": "英国/澳洲/通用",
      "theme": "内容主题",
      "content_direction": "具体内容方向，2-3句",
      "recommended_product": "产品ID",
      "xiaohongshu_angle": "小红书切入角度",
      "referral_trigger": "转介绍话术触发点"
    }}
  ],
  "weekly_themes": {{
    "week1": "主题",
    "week2": "主题",
    "week3": "主题",
    "week4": "主题"
  }}
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
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
        # 提取JSON
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            calendar_data = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            calendar_data = {"raw_output": raw, "parse_error": True}

        calendar_data["generated_at"] = today.isoformat()
        calendar_data["days_covered"] = days
        return calendar_data

    def _build_schools_context(self) -> str:
        lines = []
        for country, schools in [
            ("英国", self.config["schools"]["uk"]),
            ("澳洲", self.config["schools"]["australia"]),
        ]:
            lines.append(f"\n【{country}院校】")
            for s in schools:
                lines.append(
                    f"- {s['name']}（{s['full_name']}）"
                    f"  热门专业：{', '.join(s['popular_majors'][:3])}"
                    f"  考试周期：{', '.join(s['exam_period'])}"
                )
        return "\n".join(lines)

    def _build_products_context(self) -> str:
        lines = []
        for p in self.config["products"]:
            lines.append(f"- {p['id']}: {p['name']} — {p['description']}")
        return "\n".join(lines)
