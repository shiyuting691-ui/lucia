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
import anthropic
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
except ImportError:
    def get_company_context_for_prompt(): return ""

# GroundedBusinessAgent — 事实检索门卫
from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class PromotionStrategyAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
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

---

请生成 {target_month} 月度推广策略报告，严格使用上方产品名称：

## {target_month} 月度推广策略

### 一、月度目标
- 收入目标：¥XXX（注明推算依据）
- 核心任务：（2-3条，聚焦本月最重要的事）

### 二、重点推广产品（按优先级排列）
| 优先级 | 产品名称 | 推广原因 | 目标单量 | 定价/话术要点 |
|:---:|--------|--------|:----:|----------|
（产品名称必须完全匹配上方产品线名称）

### 三、重点目标学校
| 学校 | 推广时机 | 推荐产品 | 渠道策略 |
|------|--------|---------|---------|

### 四、核心推广活动（3-5个）
每个活动：活动名 / 时间窗口 / 目标用户 / 主要渠道 / 预期产出

### 五、渠道分配建议
- 小红书：
- 朋友圈：
- 社群运营：
- 1v1 私信：

### 六、升单路径建议
说明本月哪些产品之间有升单机会，以及话术切入点

### 七、内容素材清单
列出3-5类本月需准备的素材（产品名+内容方向）

### 八、风险提示
- 主要风险
- 应对措施

### 九、产品推广边界（基于老师储备资源）
结合上方老师储备资源和订单风险信号，列出：
- **强推产品**（老师资源充足+需求旺盛）：
- **正常推广产品**：
- **谨慎推广产品**（老师资源紧张，先确认档期）：
- **暂停强推产品**（资源暂停接单）：

请确保所有产品名称与产品线完全一致，策略具体可执行。"""

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
            logger.warning("[PromotionStrategyAgent] insufficient data, generating with limited context")

        prompt = self._build_prompt(data)
        strategy_text = ""

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                strategy_text = stream.get_final_message().content[-1].text
        except Exception as e:
            # fallback without thinking
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            strategy_text = resp.content[0].text

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
