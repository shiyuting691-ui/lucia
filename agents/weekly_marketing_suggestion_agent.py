"""
WeeklyMarketingSuggestionAgent — 周度市场内容建议
输入：本周日期范围、市场信号、知识库内容、当前推广活动
输出：4个维度建议 A市场/B销售/C产品学管/D内容素材
"""
import logging
import sys
import os
from datetime import datetime, timedelta
from services.llm import LLMRouter
from database import (
    list_market_signals, list_knowledge_docs, list_campaigns,
    list_orders, save_suggestion,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import PRODUCT_NAME_MAP
    from company_context import get_company_context_for_prompt
    from student_demand_calendar import get_current_student_phase
except ImportError:
    PRODUCT_NAME_MAP = {}
    def get_company_context_for_prompt(): return ""
    def get_current_student_phase(**kw): return {"prompt_block": "（学生需求周历未加载）"}

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class WeeklyMarketingSuggestionAgent:
    def __init__(self, config: dict):
        self.config = config
        self._router = LLMRouter()
        self._gba = GroundedBusinessAgent()

    def generate(self, week_start: str = None, extra_context: str = None) -> dict:
        if not week_start:
            today = datetime.now()
            week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        week_dt = datetime.strptime(week_start, "%Y-%m-%d")
        week_end = (week_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        logger.info(f"[WeeklyMarketingSuggestionAgent] week {week_start} ~ {week_end}")

        signals = list_market_signals(limit=15)
        docs = list_knowledge_docs(has_summary=True)
        campaigns = [c for c in list_campaigns(limit=10) if c.get("status") == "active"]
        recent_orders = list_orders(limit=80, days=365)

        from datetime import date as _date
        # 三个时间层的学生需求阶段
        student_phase_now  = get_current_student_phase(
            target_date=_date(week_dt.year, week_dt.month, week_dt.day)
        )
        next_week_dt = week_dt + timedelta(days=7)
        student_phase_next = get_current_student_phase(
            target_date=_date(next_week_dt.year, next_week_dt.month, next_week_dt.day)
        )
        next_month_dt = week_dt + timedelta(days=30)
        student_phase_month = get_current_student_phase(
            target_date=_date(next_month_dt.year, next_month_dt.month, 1)
        )
        # 判断相邻两周是否跨月份（需求是否转变）
        phase_shift = student_phase_now.get("month") != student_phase_next.get("month")

        from collections import Counter
        product_counter = Counter(
            o.get("product", "") for o in recent_orders if o.get("status") == "completed"
        )
        if not signals and not docs and not campaigns and not recent_orders:
            no_data = {
                "week_start": week_start,
                "week_end": week_end,
                "suggestion": None,
                "suggestion_id": None,
                "can_generate": False,
                "no_data": True,
                "error": "no_data: 缺少市场信号、知识库、活动和订单数据",
                "missing_info": ["market_signals", "knowledge_docs", "campaigns", "orders"],
            }
            try:
                no_data["suggestion_id"] = save_suggestion(
                    suggestion_type="weekly_marketing_suggestion",
                    title=f"{week_start} 周度市场内容建议（no_data）",
                    content="no_data：缺少真实数据，不生成推广结论。",
                    data_basis={
                        "no_data": True,
                        "evidence": [],
                        "confidence": "no_data",
                        "responsible_role": "推广部",
                    },
                    priority="中",
                )
            except Exception:
                pass
            return no_data

        signals_str = "\n".join(
            f"  [{s.get('signal_type','')}] {s.get('title','')} — {s.get('description','')[:80]}"
            f" 紧急度:{s.get('urgency_level','')} 置信度:{s.get('confidence_score','')}"
            for s in signals[:12]
        ) or "  暂无市场信号"

        docs_str = "\n".join(
            f"  [{d.get('category','')}] {d.get('title','')} — {(d.get('summary') or '')[:60]}"
            for d in docs[:8]
        ) or "  暂无知识库文档"

        campaigns_str = "\n".join(
            f"  {c.get('name','')} 主题:{c.get('core_theme','')[:40]}"
            for c in campaigns[:5]
        ) or "  无进行中活动"

        top_products_str = "\n".join(
            f"  {PRODUCT_NAME_MAP.get(p, p)}（{p}）: {n}单"
            for p, n in product_counter.most_common(5)
        ) or "  暂无"

        # ── GroundedBusinessAgent 读取已确认事实 ──
        gba_ctx = self._gba.get_context("weekly_promotion")
        if not gba_ctx["can_generate"]:
            return {
                "week_start": week_start, "week_end": week_end,
                "suggestion": None, "suggestion_id": None,
                "error": gba_ctx["reason"],
                "missing_info": gba_ctx["missing_information"],
                "can_generate": False,
            }
        if gba_ctx["facts_count"] > 0:
            context_block = gba_ctx["facts_text"]
            terms_block = gba_ctx["terms_constraint_text"]
        else:
            context_block = "【⚠️ 临时参考，未经资料确认】\n" + get_company_context_for_prompt()
            terms_block = ""

        # 相位变化提示
        phase_shift_note = (
            f"⚠️ 本周末跨月，下周学生需求将从「{student_phase_now['messaging_angle']}」转变为「{student_phase_next['messaging_angle']}」，下周素材需提前本周准备好。"
            if phase_shift else ""
        )

        next_week_start = next_week_dt.strftime("%Y-%m-%d")
        next_week_end   = (next_week_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        next_month_label = next_month_dt.strftime("%Y年%m月")

        prompt = f"""你是极致教育推广部的策略顾问。请基于三个时间层的学生需求阶段，生成短中长周期联动的推广建议。

## 公司已确认事实（{gba_ctx['facts_count']}条来自上传资料）
{context_block}

## 业务词典约束
{terms_block}

---

## 三个时间层：学生需求预测

### 🟢 本周（{week_start} ~ {week_end}）— 现在执行
{student_phase_now['prompt_block']}

---

### 🟡 下周（{next_week_start} ~ {next_week_end}）— 提前准备
**英国**：{student_phase_next['uk_phase']}
**澳洲**：{student_phase_next['au_phase']}
**下周核心推广角度**：{student_phase_next['messaging_angle']}
**下周热推产品**：{', '.join(student_phase_next['hot_products'])}
**下周需求紧迫度**：{student_phase_next['urgency']}
{phase_shift_note}

---

### 🔵 下个月（{next_month_label}）— 战略布局
**英国**：{student_phase_month['uk_phase']}
**澳洲**：{student_phase_month['au_phase']}
**下月核心推广角度**：{student_phase_month['messaging_angle']}
**下月热推产品**：{', '.join(student_phase_month['hot_products'])}
**下月需求紧迫度**：{student_phase_month['urgency']}
{student_phase_month.get('special_note', '')}

---

## 其他背景数据（{week_start} ~ {week_end}）

### 市场信号
{signals_str}

### 进行中推广活动
{campaigns_str}

### 近期热销产品
{top_products_str}

### 产品推广边界（老师资源约束）
{extra_context or "  暂无推广边界数据"}

---

## 输出要求

请按三个时间层分别输出推广建议，每条建议必须写清：目标学生 + 触发节点 + 具体动作 + 渠道/方式 + 负责角色。
不写模糊建议（如"多发内容"、"加强跟进"），每条让团队看完就能直接执行。

---

# 推广建议包（{week_start} 生成）

## ⚡ 最优先动作（跨时间层，1-2条本周必做）
格式：[时间层] | [目标学生] | [触发原因] | [立即要做什么] | [负责角色]

---

## 🟢 本周执行（{week_start} ~ {week_end}）

### 推广部 — 本周内容任务
每条格式：【渠道】【发布日】主题：XXX｜目标学生：XXX｜核心一句话：XXX
（3-4条，精确到发布日）

### 顾问 — 本周促单重点
每条格式：【优先级高/中】跟进对象：XXX｜切入话题：XXX｜话术方向：XXX
（3条，有实际话术，不是"多跟进"）

### 学管 — 本周承接要点
（2条，关注什么信号、做什么动作）

### 本周发布日历
| 日期 | 渠道 | 内容主题 | 负责角色 |
|-----|-----|--------|--------|
（周一到周日，每天1-2条）

---

## 🟡 下周预备（{next_week_start} ~ {next_week_end}）

### 本周内需完成的下周准备工作
（基于下周学生阶段，本周就要提前做什么）

### 下周内容素材清单（本周制作）
| 优先级 | 素材类型 | 具体主题 | 目标渠道 | 目标学生 | 完成截止 |
|:---:|--------|--------|--------|--------|--------|
（4-5条，主题具体，如"英国下周进入考试周，这样最后冲刺"，不能写模糊主题）

### 下周顾问话术预备
本周需要准备哪些话术/素材，以便下周直接用？

---

## 🔵 下月布局（{next_month_label}）

### 需求转变预判
- 下月学生需求与本月相比有何变化？
- 哪些产品需求会上升/下降？原因是什么？

### 本月需要启动的下月布局动作
（基于下月学生阶段，本周/本月需要提前做什么准备，如内容储备、资源预留、活动策划）

### 下月内容方向预规划
列出下月应重点布局的3-4个内容主题方向（不是本月延续，而是针对下月学生阶段的新内容）

---

禁止：
- 不能写"多投放内容"、"加强跟进"等无法执行的建议
- 不能三个时间层输出一样的内容，每层必须基于各自的学生需求阶段
- 不能虚构产品名称"""

        result_text = ""
        try:
            resp = self._router.chat(prompt, max_tokens=3000, task_type="weekly_marketing_suggestion")
            result_text = resp.text if resp.success else f"生成失败：{resp.error}"
        except Exception as e:
            result_text = f"生成失败：{e}"

        suggestion_id = save_suggestion(
            suggestion_type="weekly_marketing_suggestion",
            title=f"{week_start} 周度市场内容建议",
            content=result_text,
            data_basis={
                "week_start": week_start,
                "week_end": week_end,
                "signals_count": len(signals),
                "active_campaigns": len(campaigns),
                "facts_count": gba_ctx["facts_count"],
                "data_source_note": gba_ctx["data_source_note"],
                "missing_info": gba_ctx["missing_information"],
                "evidence": [
                    f"market_signals={len(signals)}",
                    f"knowledge_docs={len(docs)}",
                    f"campaigns={len(campaigns)}",
                    f"orders={len(recent_orders)}",
                ],
                "confidence": "medium" if signals or campaigns or recent_orders else "low",
                "responsible_role": "推广部",
            },
            priority="high",
        )

        return {
            "week_start":       week_start,
            "week_end":         week_end,
            "suggestion":       result_text,
            "suggestion_id":    suggestion_id,
            "can_generate":     True,
            "facts_count":      gba_ctx["facts_count"],
            "data_source_note": gba_ctx["data_source_note"],
            "missing_info":     gba_ctx["missing_information"],
        }
