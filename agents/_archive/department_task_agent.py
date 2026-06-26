"""
DepartmentTaskAgent — 根据月/周计划和内容池，自动生成各角色执行任务
输出写入 tasks 表

角色定义：
- 推广部：推广策略/内容主题/素材/小红书·朋友圈·社群·海报/推广节奏
- 顾问：小红书/垂直号获客、客户沟通、报价推进、成交转化、老客户维护、转介绍
- 学管：承接推广/小红书/垂直号线索、判断是否可接、确认老师资源、反馈订单风险和交付风险
- 后台：产品资料/销售话术/风控规则/系统配置/数据维护/业务规则整理
- 管理层：确认主推方向、资源倾斜、产品收紧/暂停、协调卡点、最终决策
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic

from agents.grounded_business_agent import GroundedBusinessAgent

SYSTEM_PROMPT = """你是极致教育的增长作战指挥官，把营销计划拆解成各角色可执行的具体任务。

你的输出必须是结构化的任务列表，每个任务要具体、可执行、有明确负责角色。
不要输出模糊的"做好推广"之类的任务，要具体到"今日下午3点前发布押题产品小红书"。

任务分配原则（严格按以下角色定义，禁止使用市场部/销售部/产品部/后端等错误叫法）：

推广部：
- 推广主题策划、内容方向确定
- 小红书/朋友圈/社群/海报素材制作
- 内容发布计划和节奏
- 放大有效内容、渠道节奏调整

顾问：
- 小红书/垂直号获客跟进
- 高机会客户沟通和报价推进
- 老客户激活和转介绍推进
- 客户异议收集和反馈

学管：
- 承接推广带来的线索/需求
- 判断需求是否可接（老师资源确认）
- 反馈订单风险和交付卡点
- 反馈哪些产品可以推/谨慎推

后台：
- 补充产品资料和销售话术
- 更新风控规则和边界说明
- 维护学校/产品/渠道基础数据
- 整理业务规则

管理层：
- 确认本周主推产品和重点学校
- 确认资源倾斜和优先级
- 处理产品收紧/暂停决策
- 协调跨部门卡点"""


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
        生成本周各角色任务列表
        返回 list[dict]，每条可直接写入 tasks 表
        """
        context = self._build_context(monthly_plan, weekly_plan, pending_contents, business_data)

        prompt = f"""
当前日期：{datetime.now().strftime('%Y-%m-%d')}（{['周一','周二','周三','周四','周五','周六','周日'][datetime.now().weekday()]}）

{context}

请生成本周各角色具体执行任务，输出 JSON 数组，每条任务包含：
{{
  "title": "任务标题（具体动作，不超过40字）",
  "description": "详细说明（做什么/怎么做/预期结果）",
  "task_type": "内容发布|顾问跟进|后台维护|学管反馈|风控审核|管理层决策|数据复盘|获客跟进",
  "department": "推广部|顾问|学管|后台|管理层",
  "owner": "负责人角色（如：推广同学/顾问/学管/后台同学/管理层）",
  "priority": "低|中|高|紧急",
  "related_product": "相关产品（如：Final押题/Dissertation/学年包）",
  "related_school": "相关学校（如：UCL/曼大，可为空）",
  "expected_output": "预期产出（如：3条小红书草稿/5条客户跟进记录）",
  "due_date_offset_days": 0
}}

要求：
- 每个角色至少2条任务，最多5条
- 任务要结合当前具体产品和学校，不要泛泛而谈
- 优先级要准确：本周必须完成的标"高"，可以推迟的标"中"
- 顾问任务要包含小红书/垂直号获客 + 高机会客户跟进
- 推广部任务要包含具体内容发布计划和素材方向
- 学管任务要包含线索承接判断 + 老师资源确认 + 交付风险反馈
- 后台任务要包含资料或话术补充
- 管理层任务要包含主推方向确认

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
            tasks_raw = self._fallback_tasks(monthly_plan, weekly_plan)

        tasks = []
        today = datetime.now()
        for t in tasks_raw:
            offset = t.pop("due_date_offset_days", 0) or 0
            due = today + timedelta(days=int(offset))
            t["due_date"]    = due
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
                parts.append(f"【推广方向】{tf.get('operation','')}")
                parts.append(f"【顾问方向】{tf.get('consultant','')}")
                parts.append(f"【学管方向】{tf.get('xueguan','')}")

        if pending_contents:
            types = {}
            for c in pending_contents[:20]:
                ct = c.get("content_type","")
                types[ct] = types.get(ct, 0) + 1
            parts.append(f"【待审核内容】{json.dumps(types, ensure_ascii=False)}")

        if business_data:
            parts.append(f"【业务数据】咨询量:{business_data.get('consultations','未知')} 营收:{business_data.get('revenue','未知')}")

        products = [p["name"] for p in self.config.get("products", [])]
        parts.append(f"【产品线】{' / '.join(products)}")

        return "\n".join(parts) if parts else "暂无具体计划，请基于英国/澳洲6月考试季背景生成通用任务"

    def _fallback_tasks(self, monthly_plan, weekly_plan):
        theme = (weekly_plan or {}).get("week_theme", "期末冲刺")
        return [
            {"title": f"发布{theme}主题小红书笔记", "task_type": "内容发布",
             "department": "推广部", "priority": "高", "owner": "推广同学",
             "related_product": "Final押题", "related_school": "UCL",
             "description": "围绕本周主题发布1条小红书，配合考季节点", "expected_output": "1条已发布的小红书",
             "due_date_offset_days": 1},
            {"title": "跟进小红书/垂直号未成交线索推送押题话术", "task_type": "顾问跟进",
             "department": "顾问", "priority": "高", "owner": "顾问",
             "related_product": "Final押题", "related_school": "",
             "description": "对过去7天咨询但未成交客户发送押题话术，重点跟进高机会客户", "expected_output": "5条客户跟进记录",
             "due_date_offset_days": 0},
            {"title": "确认本周老师资源和排课情况，反馈交付风险", "task_type": "学管反馈",
             "department": "学管", "priority": "中", "owner": "学管",
             "related_product": "", "related_school": "",
             "description": "统计本周可用老师名额，判断哪些需求可接，标记是否有交付风险", "expected_output": "资源确认和风险反馈",
             "due_date_offset_days": 1},
            {"title": "补充本周主推产品话术和卖点资料", "task_type": "后台维护",
             "department": "后台", "priority": "中", "owner": "后台同学",
             "related_product": "Final押题", "related_school": "",
             "description": "整理最新话术，更新到知识库供顾问使用", "expected_output": "话术文档更新",
             "due_date_offset_days": 2},
            {"title": "确认本周主推产品和重点学校资源倾斜", "task_type": "管理层决策",
             "department": "管理层", "priority": "高", "owner": "管理层",
             "related_product": "", "related_school": "",
             "description": "根据当前数据确认本周主推方向，协调推广/顾问/学管三方资源", "expected_output": "主推方向确认",
             "due_date_offset_days": 0},
        ]
