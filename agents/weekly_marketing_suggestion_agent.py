"""
WeeklyMarketingSuggestionAgent — 周度市场内容建议
输入：本周日期范围、市场信号、知识库内容、当前推广活动
输出：4个维度建议 A市场/B销售/C产品学管/D内容素材
"""
import logging
import sys
import os
from datetime import datetime, timedelta
import anthropic
from database import (
    list_market_signals, list_knowledge_docs, list_campaigns,
    list_orders, save_suggestion,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import PRODUCT_NAME_MAP
    from company_context import get_company_context_for_prompt
except ImportError:
    PRODUCT_NAME_MAP = {}
    def get_company_context_for_prompt(): return ""

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)


class WeeklyMarketingSuggestionAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
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

        from collections import Counter
        product_counter = Counter(
            o.get("product", "") for o in recent_orders if o.get("status") == "completed"
        )

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

        prompt = f"""你是极致教育推广部的策略顾问，请为推广部/顾问/学管/后台四个职能方向生成本周行动建议。

## 公司已确认事实（{gba_ctx['facts_count']}条来自上传资料）
{context_block}

## 业务词典约束
{terms_block}

---

## 本周背景（{week_start} ~ {week_end}）

### 市场信号
{signals_str}

### 进行中推广活动
{campaigns_str}

### 知识库核心文档
{docs_str}

### 近期热销产品
{top_products_str}

### 产品推广边界（老师资源约束，市场投放需遵守）
{extra_context or "  暂无推广边界数据"}

---

请按以下四个维度分别输出建议（Markdown格式）：

## 本周推广建议包（{week_start} ~ {week_end}）

### A. 推广部行动建议
（渠道投放/SEO/活动策划/竞品监控，3-4条可执行动作）

### B. 销售支持建议
（销售工具/素材需求/数据反馈/培训重点，3-4条）

### C. 产品&学管建议
（服务优化/学生满意度/产品迭代信号，2-3条）

### D. 本周内容素材清单
| 素材类型 | 主题 | 目标渠道 | 优先级 | 参考资料 |
|---------|-----|---------|-------|---------|
（列出4-6个本周应制作的内容素材，包含小红书/朋友圈/社群/海报等）

### E. 本周推荐发布节奏
周一/周三/周五/周末 各推荐发布什么类型内容

请确保所有建议与当前市场信号和推广活动高度相关，具体可执行。"""

        result_text = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=1800,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                result_text = stream.get_final_message().content[-1].text
        except Exception:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1800,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = resp.content[0].text

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
