"""
PlanningAgent — 生成月度营销战略 + 周计划，推送企业微信
"""
import json
from datetime import datetime, timedelta
from anthropic import Anthropic


SYSTEM_PROMPT = """你是一个专业的留学教育营销总监，拥有丰富的用户增长和内容策划经验。
你熟悉英国/澳洲留学生群体，了解教育机构的产品结构和销售周期。

你的任务是基于业务数据、考试节点、产品线，制定有执行落地性的营销计划。

计划要求：
- 目标明确：每个时间段有清晰的核心目标（获客/转化/复购/裂变）
- 产品聚焦：每周主推1-2个产品，避免平均用力
- 渠道协同：小红书/朋友圈/群推/转介绍各有分工
- 可执行：每个动作有明确的执行人方向（学管/顾问/运营）
- 数据驱动：基于已有数据判断优先级

语言简练，用数字和结论说话，不废话。"""


class PlanningAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model = config["anthropic"]["model"]

    # ─────────────────────────────────────────
    # 月度战略计划
    # ─────────────────────────────────────────
    def generate_monthly_plan(self, business_data: dict = None) -> dict:
        """生成月度营销战略"""
        now = datetime.now()
        month_str = now.strftime("%Y年%m月")
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)

        business_context = self._build_business_context(business_data)

        prompt = f"""
当前日期：{now.strftime('%Y年%m月%d日')}
规划月份：{month_str}

## 业务背景数据
{business_context}

## 产品线
{self._products_summary()}

## 考试节点参考
英国：5-6月考试季收尾，8-9月开学季
澳洲：6月期末考试周，7月下旬Semester 2开学

请生成{month_str}完整营销战略计划，输出JSON：
{{
  "month": "{month_str}",
  "core_theme": "本月核心主题（一句话）",
  "core_goal": "本月核心目标（数字化，如：新客+20人/学年包成交8单）",
  "situation_analysis": "3条核心判断（基于数据的机会点和风险点）",
  "product_priority": [
    {{"rank": 1, "product": "产品名", "reason": "为什么这月主推", "target": "目标成交数"}},
    {{"rank": 2, "product": "产品名", "reason": "...", "target": "..."}}
  ],
  "weekly_focus": [
    {{
      "week": "第1周（日期范围）",
      "theme": "本周主题",
      "core_action": "最重要的1件事",
      "product_focus": "主推产品",
      "channel_split": {{"xiaohongshu": "内容方向", "moments": "文案方向", "group_push": "群推策略", "referral": "转介绍触发点"}},
      "kpi": "本周目标",
      "owner": "执行方向（学管/顾问/运营）"
    }}
  ],
  "channel_strategy": {{
    "xiaohongshu": "本月小红书策略（账号定位/内容比例/发布频率）",
    "group_push": "群推策略（老客户激活/节奏）",
    "referral": "转介绍机制（本月如何放大）",
    "wechat_moments": "朋友圈策略"
  }},
  "risk_alerts": ["风险点1", "风险点2"],
  "success_metrics": ["核心指标1", "核心指标2", "核心指标3"]
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text, {"month": month_str})

    # ─────────────────────────────────────────
    # 周计划
    # ─────────────────────────────────────────
    def generate_weekly_plan(self, monthly_plan: dict = None, business_data: dict = None) -> dict:
        """生成本周7天详细执行计划"""
        now = datetime.now()
        # 找本周一
        monday = now - timedelta(days=now.weekday())
        sunday = monday + timedelta(days=6)
        week_str = f"{monday.strftime('%m/%d')}-{sunday.strftime('%m/%d')}"

        monthly_context = ""
        if monthly_plan and not monthly_plan.get("parse_error"):
            monthly_context = f"""
## 本月战略方向
- 核心主题：{monthly_plan.get('core_theme', '')}
- 本月目标：{monthly_plan.get('core_goal', '')}
- 主推产品：{json.dumps(monthly_plan.get('product_priority', [])[:2], ensure_ascii=False)}
"""

        business_context = self._build_business_context(business_data)

        prompt = f"""
当前日期：{now.strftime('%Y年%m月%d日')}（{['周一','周二','周三','周四','周五','周六','周日'][now.weekday()]}）
本周范围：{week_str}

{monthly_context}

## 业务背景
{business_context}

请生成本周（{week_str}）详细执行计划，输出JSON：
{{
  "week": "{week_str}",
  "week_theme": "本周主题",
  "week_goal": "本周核心目标（可量化）",
  "key_insight": "本周最重要的一个判断",
  "daily_plan": [
    {{
      "date": "MM-DD",
      "weekday": "周X",
      "focus": "今日重点",
      "xiaohongshu_topic": "小红书发帖主题（具体）",
      "group_action": "群推/朋友圈动作",
      "sales_action": "销售/跟进动作（学管或顾问执行）",
      "product": "今日主推产品",
      "priority": "高/中/低"
    }}
  ],
  "week_highlight_content": "本周最重要的1篇内容方向（详细描述，可直接给运营执行）",
  "referral_trigger_this_week": "本周转介绍触发话术或时机",
  "data_to_watch": ["需要关注的数据指标1", "指标2"],
  "team_focus": {{
    "xueguan": "学管部本周重点动作",
    "consultant": "顾问部本周重点动作",
    "operation": "运营本周重点动作"
  }}
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text, {"week": week_str})

    # ─────────────────────────────────────────
    # 企业微信推送格式化
    # ─────────────────────────────────────────
    def format_monthly_for_wecom(self, plan: dict) -> list[str]:
        """格式化月度计划为企业微信消息（分多条）"""
        messages = []
        month = plan.get("month", "本月")

        # 消息1：总览
        msg1 = f"━━━━━━━━━━━━━━━━━━\n"
        msg1 += f"📅 {month}营销战略计划\n"
        msg1 += f"━━━━━━━━━━━━━━━━━━\n\n"
        msg1 += f"🎯 核心主题：{plan.get('core_theme', '')}\n"
        msg1 += f"📊 核心目标：{plan.get('core_goal', '')}\n\n"
        msg1 += f"💡 核心判断：\n"
        for i, s in enumerate(plan.get('situation_analysis', '').split('。')[:3], 1):
            if s.strip():
                msg1 += f"  {i}. {s.strip()}\n"
        messages.append(msg1)

        # 消息2：产品优先级
        msg2 = f"🏆 {month}产品优先级\n\n"
        for p in plan.get('product_priority', []):
            msg2 += f"第{p.get('rank')}优先：{p.get('product')}\n"
            msg2 += f"  原因：{p.get('reason', '')}\n"
            msg2 += f"  目标：{p.get('target', '')}\n\n"
        messages.append(msg2)

        # 消息3：每周重点
        msg3 = f"📆 {month}每周重点\n\n"
        for w in plan.get('weekly_focus', []):
            msg3 += f"【{w.get('week', '')}】\n"
            msg3 += f"主题：{w.get('theme', '')}\n"
            msg3 += f"核心动作：{w.get('core_action', '')}\n"
            msg3 += f"主推产品：{w.get('product_focus', '')}\n"
            msg3 += f"本周KPI：{w.get('kpi', '')}\n"
            msg3 += f"执行方向：{w.get('owner', '')}\n\n"
        messages.append(msg3)

        # 消息4：渠道策略 + 风险提示
        msg4 = f"📣 渠道策略\n\n"
        cs = plan.get('channel_strategy', {})
        msg4 += f"小红书：{cs.get('xiaohongshu', '')}\n\n"
        msg4 += f"群推：{cs.get('group_push', '')}\n\n"
        msg4 += f"转介绍：{cs.get('referral', '')}\n\n"
        msg4 += f"⚠️ 风险提示：\n"
        for r in plan.get('risk_alerts', []):
            msg4 += f"  · {r}\n"
        msg4 += f"\n✅ 成功标准：\n"
        for m in plan.get('success_metrics', []):
            msg4 += f"  · {m}\n"
        messages.append(msg4)

        return messages

    def format_weekly_for_wecom(self, plan: dict) -> list[str]:
        """格式化周计划为企业微信消息"""
        messages = []
        week = plan.get("week", "本周")

        # 消息1：周总览
        msg1 = f"━━━━━━━━━━━━━━━━━━\n"
        msg1 += f"📋 本周推广执行计划 {week}\n"
        msg1 += f"━━━━━━━━━━━━━━━━━━\n\n"
        msg1 += f"🎯 本周主题：{plan.get('week_theme', '')}\n"
        msg1 += f"📊 本周目标：{plan.get('week_goal', '')}\n"
        msg1 += f"💡 关键判断：{plan.get('key_insight', '')}\n"
        messages.append(msg1)

        # 消息2：每日计划
        msg2 = "📅 每日执行计划\n\n"
        for d in plan.get('daily_plan', []):
            priority_emoji = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(d.get('priority', ''), "⚪")
            msg2 += f"{priority_emoji} {d.get('date','')} {d.get('weekday','')}\n"
            msg2 += f"  重点：{d.get('focus', '')}\n"
            msg2 += f"  小红书：{d.get('xiaohongshu_topic', '')}\n"
            msg2 += f"  群推：{d.get('group_action', '')}\n"
            msg2 += f"  销售动作：{d.get('sales_action', '')}\n\n"
        messages.append(msg2)

        # 消息3：分部门分工
        msg3 = "👥 本周分部门分工\n\n"
        tf = plan.get('team_focus', {})
        msg3 += f"📚 学管部：\n{tf.get('xueguan', '')}\n\n"
        msg3 += f"💼 顾问部：\n{tf.get('consultant', '')}\n\n"
        msg3 += f"📱 运营：\n{tf.get('operation', '')}\n\n"
        msg3 += f"🔄 本周转介绍触发点：\n{plan.get('referral_trigger_this_week', '')}\n\n"
        msg3 += f"📈 本周重点监控数据：\n"
        for d in plan.get('data_to_watch', []):
            msg3 += f"  · {d}\n"
        messages.append(msg3)

        # 消息4：本周重点内容方向
        msg4 = f"✍️ 本周重点内容方向\n（运营直接执行）\n\n"
        msg4 += plan.get('week_highlight_content', '')
        messages.append(msg4)

        return messages

    # ─────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────
    def _build_business_context(self, data: dict = None) -> str:
        """构建业务上下文（有数据用数据，没有用预设背景）"""
        if data:
            # 接入真实数据后走这里
            lines = ["## 真实业务数据"]
            if "revenue" in data:
                lines.append(f"- 实收业绩：{data['revenue']}")
            if "consultations" in data:
                lines.append(f"- 咨询量：{data['consultations']}")
            if "conversion_rate" in data:
                lines.append(f"- 转化率：{data['conversion_rate']}")
            if "new_clients" in data:
                lines.append(f"- 新客数：{data['new_clients']}")
            if "top_products" in data:
                lines.append(f"- 热销产品：{data['top_products']}")
            if "channel_data" in data:
                lines.append(f"- 渠道数据：{data['channel_data']}")
            if "orders" in data:
                lines.append(f"- 订单详情：{json.dumps(data['orders'][:10], ensure_ascii=False)}")
            return "\n".join(lines)
        else:
            # 使用已知背景数据
            return """
- 5月实收：¥109.1万（同比-15.18%）
- 5月咨询量：262（同比-31.77%）  ⚠️ 流量是最大问题
- 5月转化率：86.26%（接近天花板）
- 5月客单价：¥4,827
- 亮点渠道：群推+133%、小红书+120%
- 失血渠道：闲鱼停运-10单、垂直号量质双降
- 6月目标区间：¥70-88万（均值¥78.94万）
- 核心矛盾：效率到顶，流量失血，需靠内容开源
- 年度战略：机制六（小红书内容变现体系）是今年重点
"""

    def _products_summary(self) -> str:
        lines = []
        for p in self.config["products"]:
            lines.append(f"- {p['name']}：{p['description']} / 目标客群：{p.get('target', '')}")
        return "\n".join(lines)

    def _parse_response(self, raw: str, fallback: dict) -> dict:
        try:
            # 处理 ```json ... ``` 格式
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            start = raw.find("{")
            end = raw.rfind("}") + 1
            return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            fallback["raw_output"] = raw
            fallback["parse_error"] = True
            return fallback
