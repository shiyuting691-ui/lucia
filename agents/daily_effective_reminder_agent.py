"""
DailyEffectiveReminderAgent — 每日有效提醒 (V11)

按5个角色+渠道维度输出今日行动提醒：
  推广部：内容发布/渠道投放任务
  学管：推广/小红书/垂直号线索承接、订单风险反馈
  顾问：小红书/垂直号跟进、报价推进、老客户激活
  后台：资料补充、话术维护、风控规则
  管理层：待决策事项、资源倾斜确认

注意：轻量化调用，max_tokens=600，不使用 thinking
"""
import logging
import os
from datetime import datetime, timedelta
from services.llm import LLMRouter
from database import list_leads, list_tasks, list_market_signals, save_suggestion, list_feedbacks

logger = logging.getLogger(__name__)

# 角色对应的 department 字段值（兼容中英文）
_ROLE_DEPTS = {
    "推广部":  ("推广部", "promotion_team"),
    "学管":    ("学管", "xueguan"),
    "顾问":    ("顾问", "consultant"),
    "后台":    ("后台", "backend"),
    "管理层":  ("管理层", "management"),
}


class DailyEffectiveReminderAgent:
    def __init__(self, config: dict):
        self.config = config
        self._router = LLMRouter()

    def generate(self, target_date: str = None) -> dict:
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[DailyEffectiveReminderAgent] generating for {target_date}")

        leads   = list_leads(limit=100)
        tasks   = list_tasks(limit=100)
        signals = list_market_signals(limit=5)
        feedbacks = list_feedbacks(status="open")

        # ── 按角色分组任务 ───────────────────────────────────────────
        role_tasks = {}
        for role_zh, dept_vals in _ROLE_DEPTS.items():
            role_t = [t for t in tasks
                      if t.get("department") in dept_vals
                      and t.get("status") in ("todo", "in_progress", "delayed", "blocked")]
            role_tasks[role_zh] = role_t

        # ── 按渠道分组线索 ───────────────────────────────────────────
        ch_map = {
            "xiaohongshu":      "小红书",
            "vertical_account": "垂直号",
            "promotion":        "推广",
        }
        lead_by_ch = {}
        for ch_en, ch_zh in ch_map.items():
            lead_by_ch[ch_zh] = [
                l for l in leads
                if (l.get("lead_source_channel") or l.get("source_channel", "")) == ch_en
                and l.get("deal_status") in ("new", "contacted", "quoted", "follow_up")
            ]

        # ── 超时跟进线索 ─────────────────────────────────────────────
        overdue_leads = [l for l in leads if l.get("followup_status") == "overdue"]

        # ── 高危反馈 ─────────────────────────────────────────────────
        high_fbs = [f for f in feedbacks if f.get("urgency") in ("高", "紧急")]

        # ── 管理层待决策 ─────────────────────────────────────────────
        mgmt_tasks = [t for t in tasks
                      if t.get("department") in ("管理层", "management")
                      and t.get("status") in ("todo", "in_progress")]

        # ── 构建 prompt ──────────────────────────────────────────────
        def _fmt_tasks(ts):
            if not ts:
                return "  无"
            return "\n".join(
                f"  [{t.get('status','')}] {t.get('title','')[:30]} (负责:{t.get('owner','-')})"
                for t in ts[:4]
            )

        xhs_leads_str = f"小红书活跃线索{len(lead_by_ch.get('小红书',[]))}条"
        va_leads_str  = f"垂直号活跃线索{len(lead_by_ch.get('垂直号',[]))}条"
        overdue_str   = f"超时未跟进{len(overdue_leads)}条" if overdue_leads else "无超时线索"
        signal_str    = "、".join(s.get("signal_type","") for s in signals[:3]) or "无"

        prompt = f"""今天是{target_date}，请为留学机构各角色生成今日执行提醒。

数据摘要：
- {xhs_leads_str}，{va_leads_str}，{overdue_str}
- 高危反馈{len(high_fbs)}条，管理层待决策{len(mgmt_tasks)}项
- 市场信号：{signal_str}

各角色今日待办任务：
推广部（{len(role_tasks.get('推广部',[]))}个任务）：
{_fmt_tasks(role_tasks.get('推广部',[]))}

学管（{len(role_tasks.get('学管',[]))}个任务）：
{_fmt_tasks(role_tasks.get('学管',[]))}

顾问（{len(role_tasks.get('顾问',[]))}个任务）：
{_fmt_tasks(role_tasks.get('顾问',[]))}

后台（{len(role_tasks.get('后台',[]))}个任务）：
{_fmt_tasks(role_tasks.get('后台',[]))}

管理层（{len(mgmt_tasks)}项待决策）：
{_fmt_tasks(mgmt_tasks)}

请按以下格式输出（每个角色最多2条，每条20字内，没有待办就写"今日暂无"）：

【今日执行提醒】{target_date}

推广部：
- <任务或渠道动作>

学管：
- <推广/小红书/垂直号线索承接或风险反馈>

顾问：
- <小红书/垂直号跟进或报价推进>

后台：
- <资料或规则支持>

管理层：
- <待决策或待确认事项>"""

        result_text = ""
        try:
            resp = self._router.chat(prompt, max_tokens=800, task_type="daily_reminder")
            result_text = resp.text if resp.success else f"生成失败：{resp.error}"
            if not resp.success:
                logger.error(f"[DailyEffectiveReminderAgent] error: {resp.error}")
        except Exception as e:
            logger.error(f"[DailyEffectiveReminderAgent] error: {e}")
            result_text = f"生成失败：{e}"

        suggestion_id = save_suggestion(
            suggestion_type="daily_reminder",
            title=f"{target_date} 每日有效提醒",
            content=result_text,
            data_basis={
                "target_date": target_date,
                "xhs_leads": len(lead_by_ch.get("小红书", [])),
                "va_leads":  len(lead_by_ch.get("垂直号", [])),
                "overdue_leads": len(overdue_leads),
                "high_feedbacks": len(high_fbs),
                "mgmt_pending": len(mgmt_tasks),
            },
            priority="high",
        )

        return {
            "target_date":   target_date,
            "reminder":      result_text,
            "suggestion_id": suggestion_id,
            "role_task_counts": {k: len(v) for k, v in role_tasks.items()},
            "overdue_leads": len(overdue_leads),
            "high_feedbacks": len(high_fbs),
        }
