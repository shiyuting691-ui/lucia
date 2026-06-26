"""
PromotionStrategyAgent — 月度推广策略生成
输入：当前月份、历史销售数据、市场信号、学校日历
输出：月度推广策略（目标/重点产品/重点学校/核心活动/渠道分配/预算建议）
"""
import json
import logging
import sys
import os
from datetime import datetime, date
from services.llm import LLMRouter
from services.output_contracts import evidence_from_records, no_data_result
from database import (
    list_orders, list_market_signals, get_current_patterns,
    list_school_calendar, save_campaign, save_suggestion,
    list_teacher_capacity, list_order_risks,
)

# 加载知识库（临时参考，优先使用 GroundedBusinessAgent 的已确认事实）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import (
        PRODUCT_CATALOG, PRODUCT_NAME_MAP,
        get_product_info_for_prompt, get_seasonal_products,
    )
except ImportError:
    PRODUCT_CATALOG = {}
    PRODUCT_NAME_MAP = {}
    def get_product_info_for_prompt(top_products): return "（产品目录未加载）"
    def get_seasonal_products(month): return []

try:
    from company_context import get_company_context_for_prompt
    from student_demand_calendar import get_current_student_phase
except ImportError:
    def get_company_context_for_prompt(): return ""
    def get_current_student_phase(**kw): return {"prompt_block": "（学生需求周历未加载）"}

# GroundedBusinessAgent — 事实检索门卫
from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class PromotionStrategyAgent:
    def __init__(self, config: dict):
        self.config = config
        self._router = LLMRouter()
        self._gba = GroundedBusinessAgent()

    # ─────────────────── data gathering ───────────────────

    def _gather_data(self, target_month: str) -> dict:
        """收集生成策略所需的数据，target_month 格式 '2026-07'"""
        year, month = int(target_month[:4]), int(target_month[5:7])

        # 近12个月订单（days=365保证能覆盖历史数据）
        recent_orders = list_orders(limit=500, days=365)
        # 市场信号（近30条）
        signals = list_market_signals(limit=30)
        # 当前季节/周期模式
        patterns = get_current_patterns()
        # 学校日历（目标月相关）
        calendar = list_school_calendar(days_ahead=90)

        # 统计近3月各产品销售
        from collections import Counter
        product_counter = Counter()
        school_counter  = Counter()
        monthly_amounts: dict = {}
        for o in recent_orders:
            if o.get("status") == "completed":
                product_counter[o.get("product", "")] += 1
                school_counter[o.get("school", "")] += 1
                m = str(o.get("order_date", ""))[:7]
                monthly_amounts[m] = monthly_amounts.get(m, 0) + float(o.get("amount") or 0)

        # 老师资源和订单风险（供推广边界判断用）
        capacities  = list_teacher_capacity()
        order_risks = list_order_risks(limit=20)

        # 数据充足性检查
        data_ok = len(recent_orders) >= 10
        return {
            "target_month": target_month,
            "order_count": len(recent_orders),
            "orders": recent_orders[:20],
            "data_sufficient": data_ok,
            "top_products": product_counter.most_common(6),
            "top_schools": school_counter.most_common(8),
            "monthly_amounts": sorted(monthly_amounts.items())[-4:],
            "signals": signals[:10],
            "patterns": patterns,
            "teacher_capacity": capacities,
            "order_risks": order_risks,
            "calendar_events": [e for e in calendar
                                 if e.get("event_month") in (month, month - 1, month + 1)
                                 or e.get("event_year") == year][:15],
        }

    # ─────────────────── prompt & call ────────────────────

    def _build_prompt(self, data: dict) -> str:
        target_month = data["target_month"]
        month_num = int(target_month[5:7])

        # ── 产品销量（显示真实产品名）──
        products_lines = []
        for pid, count in data["top_products"]:
            pname = PRODUCT_NAME_MAP.get(pid, pid)
            products_lines.append(f"  {pname}（{pid}）: {count}单")
        products_str = "\n".join(products_lines) or "  暂无数据"

        # ── 学校 ──
        schools_str = "\n".join(f"  {s}: {n}单" for s, n in data["top_schools"]) or "  暂无数据"

        # ── 月度收入 ──
        amounts_str = "\n".join(f"  {m}: ¥{v:,.0f}" for m, v in data["monthly_amounts"]) or "  暂无数据"

        # ── 市场信号 ──
        signals_str = "\n".join(
            f"  [{s.get('signal_type','')}] {s.get('title','')} — {s.get('description','')[:80]}"
            for s in data["signals"]
        ) or "  暂无市场信号"

        # ── 历史规律 ──
        patterns_str = "\n".join(
            f"  [{p.get('month_num','')}/{p.get('year','')}] {p.get('pattern_type','')}: {p.get('description','')[:80]}"
            for p in (data["patterns"] or [])[:6]
        ) or "  暂无规律数据"

        # ── 学校日历 ──
        calendar_str = "\n".join(
            f"  {e.get('school','')} {e.get('event_type','')} {e.get('event_name','')} ({e.get('event_date','')[:10]})"
            for e in data["calendar_events"]
        ) or "  暂无日历信息"

        # ── 老师储备资源摘要 ──
        cap_str = "\n".join(
            f"  {c.get('subject_area')} {c.get('course_type')}（{c.get('country','')}）: "
            f"{c.get('capacity_status')} — {(c.get('notes') or '')[:40]}"
            for c in data.get("teacher_capacity", [])[:12]
        ) or "  暂无老师储备数据（上传 teacher_capacity.csv 后可获得精准推广边界）"

        # ── 订单风险信号摘要 ──
        risk_str = "\n".join(
            f"  [{r.get('risk_level','').upper()}] {r.get('risk_type','')}（{r.get('product','')}）: "
            f"{(r.get('evidence') or '')[:60]}"
            for r in data.get("order_risks", [])[:8]
        ) or "  暂无订单风险信号"

        # ── 完整产品目录（供模型使用，防止幻觉）──
        product_catalog_str = get_product_info_for_prompt(data["top_products"])

        # ── 本月季节性重点产品 ──
        seasonal_ids = get_seasonal_products(month_num)
        seasonal_names = [PRODUCT_NAME_MAP.get(pid, pid) for pid in seasonal_ids]
        seasonal_str = "、".join(seasonal_names)

        # ── 学生需求周历（当月 + 下月 + 后月）──
        from datetime import date as _date
        student_phase = get_current_student_phase(
            target_date=_date(year, month_num, 1)
        )
        next_m  = month_num % 12 + 1
        next_y  = year + (1 if month_num == 12 else 0)
        after_m = next_m % 12 + 1
        after_y = next_y + (1 if next_m == 12 else 0)
        student_phase_next  = get_current_student_phase(target_date=_date(next_y, next_m, 1))
        student_phase_after = get_current_student_phase(target_date=_date(after_y, after_m, 1))

        # ── 已知产品名清单（硬约束用）──
        all_known = list(PRODUCT_CATALOG.keys())
        all_known_names = "、".join(PRODUCT_NAME_MAP.get(pid, pid) for pid in all_known)

        # ── 从 GroundedBusinessAgent 读取已确认事实（优先）──
        gba_ctx = self._gba.get_context("monthly_strategy")
        if gba_ctx["facts_count"] > 0:
            company_context_block = gba_ctx["facts_text"]
            terms_block = gba_ctx["terms_constraint_text"]
        else:
            # 降级使用临时参考
            company_context_block = (
                "【⚠️ 临时参考，未经资料确认 — 请到公司资料学习中心上传并确认事实】\n"
                + get_company_context_for_prompt()
            )
            terms_block = ""

        return f"""你是极致教育的市场策略分析师，请基于以下真实数据为 {target_month} 生成月度推广策略。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏢 **公司已确认事实（来自上传资料，{gba_ctx['facts_count']}条）**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{company_context_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚫 **硬性约束（违反则策略无效）**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{terms_block}
1. **只能使用以下产品名称**，禁止虚构任何不在列表中的产品：
   {all_known_names}
2. 产品必须用**完整中文名称**（如"Final精准押题"，而非"押题服务"；"学年包"而非"年度套餐"）
3. 收入目标必须基于下方月度趋势数据推算，不得凭空估算
4. 如某产品在数据中销量为零，需在策略中注明"本月数据暂无，基于季节性判断"
5. **禁止使用以下词语**：{', '.join(gba_ctx['forbidden_terms']) if gba_ctx['forbidden_terms'] else '无'}
6. 每条关键建议后请标注依据（数据表名/文件名）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 **极致教育完整产品线**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{product_catalog_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **历史销售数据（共{data['order_count']}单）**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
各产品销量：
{products_str}

各学校分布：
{schools_str}

月度收入趋势：
{amounts_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 **市场信号**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{signals_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👩‍🏫 **老师储备资源**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{cap_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ **当前订单风险信号**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{risk_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 **学校日历（{target_month}前后）**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{calendar_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 **历史规律**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{patterns_str}
季节性重点产品（{month_num}月通常主推）：{seasonal_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 三个月学生需求预测

### 🟢 本月（{target_month}）— 执行期
{student_phase['prompt_block']}

### 🟡 下月（{next_y}-{next_m:02d}）— 预备期
英国：{student_phase_next['uk_phase']}
澳洲：{student_phase_next['au_phase']}
核心推广角度：{student_phase_next['messaging_angle']}
热推产品：{', '.join(student_phase_next['hot_products'])}
需求紧迫度：{student_phase_next['urgency']}
{student_phase_next.get('special_note', '')}

### 🔵 后月（{after_y}-{after_m:02d}）— 布局期
英国：{student_phase_after['uk_phase']}
澳洲：{student_phase_after['au_phase']}
核心推广角度：{student_phase_after['messaging_angle']}
热推产品：{', '.join(student_phase_after['hot_products'])}
需求紧迫度：{student_phase_after['urgency']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

请基于三个月学生需求预测，生成 {target_month} 月度推广策略报告。
**核心原则：本月执行 + 下月预备 + 后月布局，三层同时规划，不只看眼前。**

## {target_month} 月度推广策略

### 一、三个月需求预判（所有策略基础）
- 本月核心需求：XXX（引用本月学生阶段）
- 下月需求转变点：本月末需要做什么准备迎接下月需求变化？
- 后月需要本月开始布局的事：XXX（如内容储备/资源预留）

### 二、本月执行目标
- 收入目标：¥XXX（注明推算依据）
- 核心任务：（2-3条，每条必须对应"因为学生在XX阶段"的理由）

### 三、本月学生需求判断（先写这个，其他都基于这个）
- 本月英国学生处于：XXX 阶段，最迫切需求是：XXX
- 本月澳洲学生处于：XXX 阶段，最迫切需求是：XXX
- 本月美国学生处于：XXX 阶段，最迫切需求是：XXX
- 本月最高需求产品（原因）：XXX，因为XXX（引用上方学生阶段数据）

### 二、月度目标
- 收入目标：¥XXX（注明推算依据）
- 核心任务：（2-3条，每条必须对应一个"因为学生在XX阶段"的理由）

### 三、重点推广产品（按转化优先级排列）
| 优先级 | 产品名称 | 推广原因（引用学生阶段） | 目标学生群体 | 话术核心切入点 | 目标单量 |
|:---:|--------|-------------------|-----------|------------|:----:|
（产品名称必须完全匹配上方产品线名称；推广原因要写"因为英国学生现在在X阶段"这样的句子）

### 四、各渠道本月执行计划
每个渠道必须写：目标学生群体 + 本月主题方向 + 发布频率 + 内容具体主题示例
- **小红书**：（目标：XXX学生 | 主题：XXX | 频率：X次/周 | 示例主题：《XXX》）
- **朋友圈**：（目标：XXX学生 | 主题：XXX | 频率：X次/周）
- **社群**：（目标：XXX学生 | 运营方式：XXX | 本月活动：XXX）
- **垂直号**：（目标：XXX学生 | 核心内容：XXX）

### 五、本月关键活动节点（3-5个）
格式：活动名 | 时间 | 目标学生（具体到学校/学期阶段） | 主打产品 | 预期成交
（时间要具体到某周，目标学生要具体到"英国X大正在备考期末的学生"）

### 六、顾问话术重点
- 本月主要学生情绪/状态：XXX（基于学生阶段分析）
- 最有效切入话术方向：XXX
- 本月应避免的话术误区：XXX

### 七、升单路径建议
说明本月哪些产品之间有升单机会，以及对应学生阶段的话术切入点

### 八、内容素材清单（推广部本月制作）
| 优先级 | 素材类型 | 具体内容主题（必须写出来） | 目标渠道 | 目标学生 | 截止周 |
|:---:|--------|---------------------|--------|--------|------|
（主题必须具体，如"英国某某大学期末考试攻略：这3门课押中率最高"）

### 九、产品推广边界（基于老师储备资源）
结合上方老师储备资源和订单风险信号，列出：
- **强推产品**（老师资源充足+需求旺盛）：
- **正常推广产品**：
- **谨慎推广产品**（老师资源紧张，先确认档期）：
- **暂停强推产品**（资源暂停接单）：

---

## 🟡 下月预备（{next_y}-{next_m:02d}，本月需做的准备）

### 下月需求转变预判
- 下月学生需求与本月有什么核心变化？
- 哪个产品需求会上升最快？为什么？
- 本月末哪些线索/客户会进入下月的高需求状态？

### 本月需完成的下月准备
（不是策略，是具体要做的事）
| 类型 | 具体准备内容 | 负责角色 | 完成截止 |
|-----|-----------|--------|--------|
（如：下月小红书内容储备5篇、顾问话术更新、资源预留等）

### 下月内容方向预规划（本月开始制作）
列出3-4个下月核心内容主题方向，本月开始储备：
（主题要针对下月学生阶段，不是本月内容的延续）

---

## 🔵 后月布局（{after_y}-{after_m:02d}，本月开始卡位）

### 本月需启动的后月布局
- 后月学生需求是什么（简述）？
- 本月需要开始做哪些提前卡位动作？（内容方向、资源、渠道）
- 是否有重要节点/deadline需要本月提前准备？

---

请确保所有产品名称与产品线完全一致，三个时间层建议不重复，每层针对各自学生阶段。"""

    def generate(self, target_month: str = None) -> dict:
        if not target_month:
            target_month = datetime.now().strftime("%Y-%m")

        logger.info(f"[PromotionStrategyAgent] generating for {target_month}")

        # ── GroundedBusinessAgent 预检 ──
        gba_ctx = self._gba.get_context("monthly_strategy")
        if not gba_ctx["can_generate"]:
            return {
                "target_month":   target_month,
                "strategy":       None,
                "error":          gba_ctx["reason"],
                "missing_info":   gba_ctx["missing_information"],
                "can_generate":   False,
                "data_source_note": gba_ctx["data_source_note"],
            }

        data = self._gather_data(target_month)

        if not data["data_sufficient"]:
            logger.warning("[PromotionStrategyAgent] no_data: insufficient order data")
            return {
                **no_data_result("近12个月真实订单少于10单，不能生成月度推广策略"),
                "target_month": target_month,
                "can_generate": False,
                "order_count": data["order_count"],
            }

        prompt = self._build_prompt(data)
        strategy_text = ""

        try:
            resp = self._router.generate_text(prompt, max_tokens=3500, task_type="monthly_promotion_strategy")
            if not resp.success or resp.provider in ("rule", "rule_fallback"):
                logger.error(f"[PromotionStrategyAgent] no_data: LLM unavailable: {resp.error}")
                return {
                    **no_data_result("AI模型不可用，且月度推广策略不允许规则兜底生成"),
                    "target_month": target_month,
                    "can_generate": False,
                    "order_count": data["order_count"],
                }
            strategy_text = resp.content
        except Exception as e:
            logger.error(f"[PromotionStrategyAgent] error: {e}")
            return {
                **no_data_result(f"月度推广策略生成失败：{e}"),
                "target_month": target_month,
                "can_generate": False,
                "order_count": data["order_count"],
            }

        # 保存为 suggestion
        suggestion_id = save_suggestion(
            suggestion_type="monthly_promotion_strategy",
            title=f"{target_month} 月度推广策略",
            content=strategy_text,
            data_basis={
                "target_month":     target_month,
                "order_count":      data["order_count"],
                "top_products":     data["top_products"],
                "data_sufficient":  data["data_sufficient"],
                "facts_count":      gba_ctx["facts_count"],
                "data_source_note": gba_ctx["data_source_note"],
                "missing_info":     gba_ctx["missing_information"],
                "evidence": (
                    evidence_from_records("orders", data.get("orders", []), limit=8)
                    or [f"orders.count={data['order_count']}"]
                ),
                "confidence": "medium",
                "responsible_role": "推广/市场",
            },
            priority="high",
        )

        # 同时保存为推广活动记录
        campaign_id = save_campaign({
            "name": f"{target_month} 月度推广策略",
            "campaign_type": "monthly_plan",
            "target_country": "All",
            "core_goal": strategy_text[:500],
            "extra_data": {
                "strategy_full": strategy_text,
                "generated_at": datetime.utcnow().isoformat(),
                "target_month": target_month,
            },
        })

        logger.info(f"[PromotionStrategyAgent] saved suggestion_id={suggestion_id} campaign_id={campaign_id}")
        return {
            "target_month":     target_month,
            "strategy":         strategy_text,
            "suggestion_id":    suggestion_id,
            "campaign_id":      campaign_id,
            "data_sufficient":  data["data_sufficient"],
            "order_count":      data["order_count"],
            "can_generate":     True,
            "facts_count":      gba_ctx["facts_count"],
            "data_source_note": gba_ctx["data_source_note"],
            "missing_info":     gba_ctx["missing_information"],
        }
