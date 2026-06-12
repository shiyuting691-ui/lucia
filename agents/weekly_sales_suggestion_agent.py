"""
WeeklySalesSuggestionAgent — 周度销售话术建议
输入：本周日期范围、近期订单/线索、当前推广活动
输出：销售团队本周行动建议（跟进优先级/话术/场景应对）
"""
import json
import logging
import sys
import os
from datetime import datetime, timedelta
import anthropic
from database import list_orders, list_leads, list_campaigns, list_market_signals, save_suggestion

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import PRODUCT_NAME_MAP
    from company_context import get_company_context_for_prompt
except ImportError:
    PRODUCT_NAME_MAP = {}
    def get_company_context_for_prompt(): return ""

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class WeeklySalesSuggestionAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self._gba = GroundedBusinessAgent()

    def generate(self, week_start: str = None, extra_context: str = None) -> dict:
        """生成本周销售建议，week_start 格式 '2026-06-09'，extra_context 可传入推广边界摘要"""
        if not week_start:
            today = datetime.now()
            # 本周一
            week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        week_dt = datetime.strptime(week_start, "%Y-%m-%d")
        week_end = (week_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        logger.info(f"[WeeklySalesSuggestionAgent] week {week_start} ~ {week_end}")

        # 数据收集
        recent_orders = list_orders(limit=100, days=365)
        leads = list_leads(limit=50)
        campaigns = list_campaigns(limit=10)
        signals = list_market_signals(limit=10)

        # 统计本周前的数据情况
        hot_leads = [l for l in leads if l.get("status") in ("contacted", "negotiating", "new")]
        active_campaigns = [c for c in campaigns if c.get("status") == "active"]

        from collections import Counter
        product_counter = Counter(o.get("product", "") for o in recent_orders if o.get("status") == "completed")

        # 构建 prompt
        leads_str = "\n".join(
            f"  [{l.get('status','')}] {l.get('name','')} — {l.get('school','')} {l.get('product','')} "
            f"意向分:{l.get('intent_score','?')} 最后联系:{str(l.get('last_contact_at',''))[:10]}"
            for l in hot_leads[:15]
        ) or "  暂无活跃线索"

        campaigns_str = "\n".join(
            f"  {c.get('name','')} ({c.get('target_country','')}) 主题:{c.get('core_theme','')[:40]}"
            for c in active_campaigns[:5]
        ) or "  暂无进行中活动"

        signals_str = "\n".join(
            f"  [{s.get('signal_type','')}] {s.get('title','')} 紧急度:{s.get('urgency_level','')}"
            for s in signals[:8]
        ) or "  暂无市场信号"

        top_products = "\n".join(
            f"  {PRODUCT_NAME_MAP.get(p, p)}（{p}）: {n}单"
            for p, n in product_counter.most_common(5)
        ) or "  暂无"

        # ── GroundedBusinessAgent 读取已确认事实 ──
        gba_ctx = self._gba.get_context("weekly_sales")
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

        prompt = f"""你是极致教育顾问团队的销售策略顾问，请为顾问团队生成{week_start}这一周的销售跟进建议。

## 公司已确认事实（{gba_ctx['facts_count']}条来自上传资料）
{context_block}

## 业务词典约束
{terms_block}

---

## 本周背景

### 活跃线索（{len(hot_leads)}个）
{leads_str}

### 进行中推广活动
{campaigns_str}

### 市场信号
{signals_str}

### 近期热销产品
{top_products}

### 产品推广边界（老师资源约束）
{extra_context or "  暂无推广边界数据"}

---

请生成本周销售团队行动建议（Markdown格式）：

## 本周销售行动建议（{week_start} ~ {week_end}）

### 一、本周核心目标
（1-2条可量化目标）

### 二、优先跟进线索（TOP 5）
| 姓名/编号 | 学校 | 产品 | 跟进理由 | 推荐话术方向 |
|---------|-----|-----|---------|-----------|

### 三、本周话术重点
针对以下场景各提供1-2条话术：
1. 初次触达话术
2. 价格异议应对
3. 对比竞品应对
4. 促单/逼单时机

### 四、需重点推送的优惠/活动
结合本周推广活动，给销售一句话播报模板

### 五、注意事项
（合规提示/需规避的说法）

请确保建议简洁、可直接执行，避免空洞理论。"""

        result_text = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=1500,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                result_text = stream.get_final_message().content[-1].text
        except Exception:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = resp.content[0].text

        suggestion_id = save_suggestion(
            suggestion_type="weekly_sales_suggestion",
            title=f"{week_start} 周度销售建议",
            content=result_text,
            data_basis={
                "week_start": week_start,
                "week_end": week_end,
                "hot_leads": len(hot_leads),
                "active_campaigns": len(active_campaigns),
                "facts_count": gba_ctx["facts_count"],
                "data_source_note": gba_ctx["data_source_note"],
                "missing_info": gba_ctx["missing_information"],
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
