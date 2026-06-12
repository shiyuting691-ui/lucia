"""
DistributionAgent — 企业微信推送
把工作流运行结果格式化后推送到企业微信群
"""
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class DistributionAgent:
    WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=6fb301ee-26ad-4dc7-bcfb-a97274c7d477"

    def __init__(self, config: dict):
        self.webhook_url = config.get("wecom_webhook", self.WECOM_WEBHOOK)

    def _send(self, markdown: str) -> bool:
        if not self.webhook_url:
            logger.warning("DistributionAgent: no wecom_webhook configured")
            return False
        try:
            resp = requests.post(
                self.webhook_url,
                json={"msgtype": "markdown", "markdown": {"content": markdown}},
                timeout=10,
            )
            ok = resp.json().get("errcode", -1) == 0
            if not ok:
                logger.error(f"DistributionAgent WeChat push failed: {resp.text}")
            return ok
        except Exception as e:
            logger.error(f"DistributionAgent send error: {e}")
            return False

    def push_daily_summary(self, context: dict, sales_result: dict, feedback_result: dict) -> bool:
        today = context.get("today", datetime.utcnow().strftime("%Y-%m-%d"))
        contents_saved = sales_result.get("contents_saved", 0)
        suggestions_saved = feedback_result.get("suggestions_saved", 0)
        open_tasks = context.get("open_tasks_count", 0)
        open_feedbacks = context.get("open_feedbacks_count", 0)

        lines = [
            f"## 📋 每日自动化简报 · {today}",
            "",
            f"> <font color='info'>今日工作流已运行完成</font>",
            "",
            "**📊 今日数据汇总**",
            f"- 新生成内容草稿：**{contents_saved}** 条（待审核后发布）",
            f"- 新增战略建议：**{suggestions_saved}** 条",
            f"- 待处理任务：**{open_tasks}** 条",
            f"- 待处理反馈：**{open_feedbacks}** 条",
            "",
        ]

        urgent_feedbacks = context.get("urgent_feedbacks", [])
        if urgent_feedbacks:
            lines.append("**⚠️ 紧急反馈（需关注）**")
            for f in urgent_feedbacks:
                lines.append(f"- [{f.get('urgency','')}] {f.get('department','')}：{f.get('title','')}")
            lines.append("")

        active_campaigns = context.get("active_campaigns", [])
        if active_campaigns:
            lines.append("**🎯 当前活跃活动**")
            for c in active_campaigns:
                lines.append(f"- {c['name']}（{c.get('target_country','')}）")
            lines.append("")

        lines.append("> 💡 所有生成内容均为草稿，请登录控制台审核后再发布。")

        markdown = "\n".join(lines)
        return self._send(markdown)

    def push_workflow_error(self, workflow_name: str, error: str) -> bool:
        markdown = (
            f"## ❌ 工作流异常通知\n\n"
            f"> <font color='warning'>**{workflow_name}** 运行出错，请检查日志</font>\n\n"
            f"错误信息：`{error[:200]}`\n\n"
            f"时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        )
        return self._send(markdown)

    def push_daily_summary_v4(self, context: dict, sales_result: dict,
                               feedback_result: dict, intel_result: dict = None) -> bool:
        """V4 版日报：包含热门学校、市场信号、往年规律"""
        today = context.get("today", datetime.utcnow().strftime("%Y-%m-%d"))
        contents_saved    = sales_result.get("contents_saved", 0)
        suggestions_saved = feedback_result.get("suggestions_saved", 0)
        open_tasks        = context.get("open_tasks_count", 0)
        open_feedbacks    = context.get("open_feedbacks_count", 0)
        hot_schools       = context.get("hot_schools", [])
        hot_products      = context.get("hot_products", [])
        signals_saved     = (intel_result or {}).get("signals_saved", 0)
        marketing_actions = (intel_result or {}).get("marketing_actions", [])

        lines = [
            f"## 📋 极致教育每日情报简报 · {today}",
            "",
            f"> <font color='info'>今日工作流已运行完成</font>",
            "",
            "**📊 今日数据汇总**",
            f"- 新市场信号：**{signals_saved}** 条",
            f"- 新生成内容草稿：**{contents_saved}** 条（待审核后发布）",
            f"- 新增战略建议：**{suggestions_saved}** 条",
            f"- 待处理任务：**{open_tasks}** 条",
            f"- 待处理反馈：**{open_feedbacks}** 条",
            "",
        ]

        if hot_schools:
            lines.append("**🔥 今日热门学校**")
            lines.append(f"> {' | '.join(hot_schools[:5])}")
            lines.append("")

        if hot_products:
            lines.append("**💼 热门产品**")
            lines.append(f"> {' | '.join(hot_products[:4])}")
            lines.append("")

        urgent_feedbacks = context.get("urgent_feedbacks", [])
        if urgent_feedbacks:
            lines.append("**⚠️ 紧急反馈（需关注）**")
            for f in urgent_feedbacks:
                lines.append(f"- [{f.get('urgency','')}] {f.get('department','')}：{f.get('title','')}")
            lines.append("")

        if marketing_actions:
            lines.append("**🎯 今日推荐营销动作**")
            for action in marketing_actions[:3]:
                lines.append(f"- {action}")
            lines.append("")

        # 往年规律提示
        patterns = context.get("current_patterns", [])
        if patterns:
            lines.append("**📅 往年同期规律参考**")
            for p in patterns[:2]:
                lines.append(f"- {p.get('school','')} {p.get('product','')}: {p.get('pattern_summary','')[:60]}")
            lines.append("")

        lines.append("> 💡 所有生成内容均为草稿，请登录控制台【市场情报台】查看详情后审核发布。")
        lines.append(f"\n<font color=\"comment\">🤖 极致增长系统 · {datetime.utcnow().strftime('%H:%M')} UTC</font>")

        return self._send("\n".join(lines))

    def push_custom(self, markdown: str) -> bool:
        return self._send(markdown)
