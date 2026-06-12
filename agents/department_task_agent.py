"""
DepartmentTaskAgent — 根据月/周计划和内容池，自动生成各部门执行任务
输出写入 tasks 表
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic

from agents.grounded_business_agent import GroundedBusinessAgent

SYSTEM_PROMPT = """你是一个营销作战指挥官，擅长把营销计划拆解成各部门可执行的具体任务。

你的输出必须是结构化的任务列表，每个任务要具体、可执行、有明确负责部门。
不要输出模糊的"做好营销"之类的任务，要具体到"今日下午3点前发布押题产品小红书"。

任务分配原则：
- 推广部：内容发布、小红书、朋友圈、社群推广
- 顾问：客户跟进、话术使用、转介绍激活、报价跟进
- 后台：产品资料更新、交付流程优化、卖点梳理
- 学管部：后端交付反馈、老师资源确认、教学风险提示
- 管理层：战略决策确认、优先级拍板、资源调配"""


class DepartmentTaskAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model  = config["anthropic"]["model"]

    def generate_tasks(
        self,
        monthly_plan: dict = None,
        weekly_plan: dict  = None,
        pending_contents: list = None,
        business_data: dict = None,
    ) -> list[dict]:
        """
        生成本周各部门任务列表
        返回 list[dict]，每条可直接写入 tasks 表
        """
        context = self._build_context(monthly_plan, weekly_plan, pending_contents, business_data)

        prompt = f"""
当前日期：{datetime.now().strftime('%Y-%m-%d')}（{['周一','周二','周三','周四','周五','周六','周日'][datetime.now().weekday()]}）

{context}

请生成本周各部门具体执行任务，输出 JSON 数组，每条任务包含：
{{
  "title": "任务标题（具体动作，不超过40字）",
  "description": "详细说明（做什么/怎么做/预期结果）",
  "task_type": "内容发布|销售跟进|产品优化|后端反馈|风控审核|管理层决策|数据复盘|客户跟进",
  "department": "推广部|顾问|后台|学管部|管理层",
  "owner": "负责人角色（如：运营同学/销售顾问/产品负责人）",
  "priority": "低|中|高|紧急",
  "related_product": "相关产品（如：Final押题/Dissertation/学年包）",
  "related_school": "相关学校（如：UCL/曼大，可为空）",
  "expected_output": "预期产出（如：3条小红书草稿/5条客户跟进记录）",
  "due_date_offset_days": 0
}}

要求：
- 每个部门至少2条任务，最多5条
- 任务要结合当前具体产品和学校，不要泛泛而谈
- 优先级要准确：本周必须完成的标"高"，可以推迟的标"中"
- 顾问任务要包含今日重点跟进动作
- 推广部任务要包含具体内容发布计划
- 学管部任务要包含交付风险确认

只输出 JSON 数组，不要其他文字。
"""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```json")[-1].split("```")[0] if "```json" in raw \
                  else raw.split("```")[1].split("```")[0]

        try:
            tasks_raw = json.loads(raw.strip())
        except Exception:
            # fallback：生成基础任务
            tasks_raw = self._fallback_tasks(monthly_plan, weekly_plan)

        # 处理 due_date
        tasks = []
        today = datetime.now()
        for t in tasks_raw:
            offset = t.pop("due_date_offset_days", 0) or 0
            due = today + timedelta(days=int(offset))
            t["due_date"]   = due
            t["task_source"] = "AI生成"
            tasks.append(t)

        return tasks

    def _build_context(self, monthly_plan, weekly_plan, pending_contents, business_data):
        parts = []
        if monthly_plan:
            parts.append(f"【月度主题】{monthly_plan.get('core_theme','')}")
            parts.append(f"【月度目标】{monthly_plan.get('core_goal','')}")
            priority = monthly_plan.get("product_priority", [])
            if priority:
                top = priority[0]
                parts.append(f"【本月主推产品】{top.get('product','')}（目标：{top.get('target','')}）")

        if weekly_plan:
            parts.append(f"【本周主题】{weekly_plan.get('week_theme','')}")
            parts.append(f"【本周目标】{weekly_plan.get('week_goal','')}")
            parts.append(f"【本周洞察】{weekly_plan.get('key_insight','')}")
            tf = weekly_plan.get("team_focus", {})
            if tf:
                parts.append(f"【市场方向】{tf.get('operation','')}")
                parts.append(f"【销售方向】{tf.get('consultant','')}")
                parts.append(f"【学管方向】{tf.get('xueguan','')}")

        if pending_contents:
            types = {}
            for c in pending_contents[:20]:
                ct = c.get("content_type","")
                types[ct] = types.get(ct, 0) + 1
            parts.append(f"【待审核内容】{json.dumps(types, ensure_ascii=False)}")

        if business_data:
            parts.append(f"【业务数据】咨询量:{business_data.get('consultations','未知')} 营收:{business_data.get('revenue','未知')}")

        # 产品信息
        products = [p["name"] for p in self.config.get("products", [])]
        parts.append(f"【产品线】{' / '.join(products)}")

        return "\n".join(parts) if parts else "暂无具体计划，请基于英国/澳洲6月考试季背景生成通用任务"

    def _fallback_tasks(self, monthly_plan, weekly_plan):
        theme = (weekly_plan or {}).get("week_theme", "期末冲刺")
        return [
            {"title": f"发布{theme}主题小红书笔记", "task_type": "内容发布",
             "department": "推广部", "priority": "高", "owner": "运营同学",
             "related_product": "Final押题", "related_school": "UCL",
             "description": "围绕本周主题发布1条小红书", "expected_output": "1条已发布的小红书",
             "due_date_offset_days": 1},
            {"title": "跟进未成交咨询客户推送押题话术", "task_type": "销售跟进",
             "department": "顾问", "priority": "高", "owner": "销售顾问",
             "related_product": "Final押题", "related_school": "",
             "description": "对过去7天咨询但未成交客户发送押题话术", "expected_output": "5条客户跟进记录",
             "due_date_offset_days": 0},
            {"title": "确认本周老师资源和排课情况", "task_type": "后端反馈",
             "department": "学管部", "priority": "中", "owner": "学管负责人",
             "related_product": "", "related_school": "",
             "description": "统计本周可用老师名额，标记是否有交付风险", "expected_output": "资源确认表",
             "due_date_offset_days": 1},
        ]
