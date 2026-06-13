"""
DailyExecutionWorkflow — 每日执行监督工作流（V9，5步）

触发：CLI run-daily-execution-check
步骤：
  1. 线索机会评分（更新 lead_scores）
  2. 检查 blocked/delayed 任务（写入风险提醒）
  3. 每日有效提醒生成
  4. 企业微信推送（执行提醒格式）
"""
import logging
from datetime import datetime, timedelta
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class DailyExecutionWorkflow(BaseWorkflow):
    name = "daily_execution"

    def _run_steps(self) -> dict:
        from services.agent_runner import AgentRunner
        from agents.lead_opportunity_scoring_agent import LeadOpportunityScoringAgent
        from agents.daily_effective_reminder_agent import DailyEffectiveReminderAgent

        runner = AgentRunner(workflow_name=self.name)

        # Step 1: 线索机会评分
        r = runner.run("LeadOpportunityScoringAgent",
                       lambda: LeadOpportunityScoringAgent(self.config).run(days_lookback=7),
                       input_summary="daily")
        lead_scores = r["output"] if r["status"] == "success" else []
        urgent_leads = [l for l in lead_scores if l.get("urgent_flags")]
        self._add_step("lead_scoring", r["status"], records=len(lead_scores),
                       note=r["error_message"] or f"紧急线索{len(urgent_leads)}条")

        # Step 2: 检查阻碍任务
        from database import list_tasks, get_task_execution_stats
        blocked_tasks = list_tasks(status="blocked", limit=20)
        delayed_tasks = list_tasks(status="delayed", limit=20)
        self._add_step("check_blockers", "success",
                       note=f"blocked={len(blocked_tasks)} delayed={len(delayed_tasks)}")

        # Step 3: 每日有效提醒
        r = runner.run("DailyEffectiveReminderAgent",
                       lambda: DailyEffectiveReminderAgent(self.config).generate(),
                       input_summary="daily")
        reminders = r["output"] if r["status"] == "success" else []
        self._add_step("daily_reminder", r["status"], records=len(reminders), note=r["error_message"])

        # Step 4: 企业微信推送（执行提醒）
        try:
            push_text = self._build_exec_push(urgent_leads, blocked_tasks, delayed_tasks, reminders)
            sent = self._send_wecom(push_text)
            self._add_step("wecom_push", "success" if sent else "skipped",
                           note="已推送" if sent else "未配置")
        except Exception as e:
            self._add_step("wecom_push", "error", note=str(e))

        return {
            "summary": (f"每日执行检查完成：紧急线索{len(urgent_leads)}条，"
                        f"blocked={len(blocked_tasks)}，delayed={len(delayed_tasks)}"),
            "urgent_lead_count": len(urgent_leads),
            "blocked_count": len(blocked_tasks),
            "delayed_count": len(delayed_tasks),
        }

    @staticmethod
    def _build_exec_push(urgent_leads, blocked_tasks, delayed_tasks, reminders) -> str:
        today = datetime.now().strftime("%m月%d日")
        lines = [f"# 🔔 极致教育 · {today} 每日执行提醒\n"]

        if urgent_leads:
            lines.append("**🚨 紧急线索（需今日跟进）**")
            for l in urgent_leads[:5]:
                flags = "、".join(l.get("urgent_flags", []))
                lines.append(f"• {l.get('customer_name','')} {l.get('school','')} {l.get('product_interest','')}（{flags}）")
            lines.append("")

        if blocked_tasks or delayed_tasks:
            lines.append("**⚠️ 待处理阻碍**")
            for t in (blocked_tasks + delayed_tasks)[:5]:
                status_label = "🔴阻碍" if t["status"] == "blocked" else "🟡延迟"
                lines.append(f"• [{status_label}] {t['title'][:40]} — {t.get('department','')}")
                if t.get("blockers"):
                    lines.append(f"  阻碍原因：{t['blockers'][:50]}")
            lines.append("")

        if reminders:
            lines.append("**📌 今日重点提醒**")
            for i, r in enumerate(reminders[:3], 1):
                lines.append(f"{i}. {str(r)[:60]}")
            lines.append("")

        lines.append("<font color='comment'>🤖 极致增长系统 · 每日执行监督</font>")
        return "\n".join(lines)[:2000]

    def _send_wecom(self, text: str) -> bool:
        import os, requests
        webhook = os.environ.get("WECHAT_WORK_WEBHOOK", "")
        if not webhook:
            return False
        resp = requests.post(webhook, json={"msgtype": "markdown",
                                            "markdown": {"content": text}}, timeout=10)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
