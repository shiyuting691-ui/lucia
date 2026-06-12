"""
SchoolStrategyCardAgent — 学校策略卡生成（V7 第一阶段）

基于 school_scores + 内部数据聚合，为每所学校生成一张短策略卡。
- 经过 GroundedBusinessAgent 闸门：只引用已确认事实和标准术语
- 每个关键判断必须带 data_evidence；资料不足时明确写 missing_data
- 不编造学校节点 / DDL / 外部信息
"""
import json
import logging
from datetime import datetime

import anthropic
from sqlalchemy import text
from database.db import engine
from database import list_school_scores, save_strategy_card
from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)

CARD_KEYS = (
    "main_product", "secondary_products", "cautious_products", "paused_products",
    "why_this_strategy", "marketing_suggestions", "sales_suggestions",
    "academic_support_notes", "backend_support_notes", "risk_notes",
    "suggested_materials", "next_7d_prediction", "next_14d_prediction",
    "next_30d_prediction", "data_evidence", "confidence",
)


class SchoolStrategyCardAgent:

    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self._gba = GroundedBusinessAgent()

    def run(self, priority_filter: tuple = ("S", "A", "B"), limit: int = 20) -> list[dict]:
        """为评分过的学校生成策略卡（默认跳过 Unknown/低机会，避免无依据强推）"""
        gba_ctx = self._gba.get_context("monthly_strategy")
        if not gba_ctx.get("can_generate"):
            return [{"error": "公司事实库未确认，无法生成策略卡", "can_generate": False}]

        scores = [s for s in list_school_scores(limit=limit)
                  if s["priority_level"] in priority_filter]
        cards = []
        for sc in scores:
            try:
                cards.append(self._generate_card(sc, gba_ctx))
            except Exception as e:
                logger.error(f"[StrategyCard] {sc['school_name']} 失败: {e}")
                cards.append({"school_name": sc["school_name"], "error": str(e)})
        return cards

    def _internal_snapshot(self, school: str) -> str:
        """聚合该校内部数据，作为唯一事实来源喂给模型"""
        with engine.connect() as c:
            rows = lambda sql: c.execute(text(sql), {"s": school}).fetchall()
            recent_leads = rows(
                "SELECT inquiry_date, product_interest, pain_point, deal_status, lost_reason "
                "FROM leads WHERE school=:s ORDER BY inquiry_date DESC LIMIT 10")
            prod_orders = rows(
                "SELECT product, COUNT(*), AVG(amount) FROM orders WHERE school=:s "
                "GROUP BY product ORDER BY 2 DESC LIMIT 6")
            risks = rows(
                "SELECT risk_type, risk_level, evidence, suggested_action "
                "FROM order_risk_signals WHERE school=:s")
            teachers = rows(
                "SELECT subject_area, capacity_status, risk_level, notes FROM teacher_capacity "
                "WHERE school_experience LIKE '%' || :s || '%'")
            cal = rows(
                "SELECT event_type, event_name, start_date, end_date, confidence "
                "FROM school_calendar WHERE school=:s")

        parts = [f"【{school} 内部数据快照】"]
        parts.append("历史产品订单分布：" + ("; ".join(
            f"{p}×{n}单(均价¥{avg:.0f})" for p, n, avg in prod_orders) or "无"))
        parts.append("近期咨询样本：" + ("; ".join(
            f"[{str(d)[:10]}]{pi or '?'}-{(pp or '')[:30]}({ds}{'/'+lr if lr else ''})"
            for d, pi, pp, ds, lr in recent_leads[:8]) or "无"))
        parts.append("订单风险信号：" + ("; ".join(
            f"[{lv}]{rt}:{(ev or '')[:50]}→{(sa or '')[:40]}" for rt, lv, ev, sa in risks) or "无"))
        parts.append("老师储备：" + ("; ".join(
            f"{sub}:{st}(风险{rl}{'/'+n[:30] if n else ''})" for sub, st, rl, n in teachers) or
            "⚠️ 无该校老师储备数据"))
        parts.append("学校节点（仅此为准，严禁编造其他日期）：" + ("; ".join(
            f"{et}-{en}:{str(sd)[:10]}~{str(ed)[:10]}(置信{cf})" for et, en, sd, ed, cf in cal) or
            "⚠️ 无学校节点资料"))
        return "\n".join(parts)

    def _generate_card(self, sc: dict, gba_ctx: dict) -> dict:
        snapshot = self._internal_snapshot(sc["school_name"])
        prompt = f"""你是教育辅导机构的学校推广策略顾问。基于以下内部真实数据，为一所学校生成一张简短的策略卡。

## 公司已确认事实（唯一可引用的公司信息）
{gba_ctx['facts_text']}

## 术语约束
{gba_ctx['terms_constraint_text']}

## 学校机会评分结果
学校：{sc['school_name']}（{sc['country']}）
机会分：{sc['opportunity_score']} | 优先级：{sc['priority_level']} | 阶段：{sc['current_stage']} | 热度：{sc['demand_heat']}
评分依据：{json.dumps(sc['score_reason'], ensure_ascii=False)}
热门产品：{sc['hot_products']}
风险：{sc['risk_notes']}
资料缺口：{sc['missing_data']}

{snapshot}

## 硬性规则
1. 严禁编造学校考试时间、DDL、学校节点——只能引用上面快照中明确给出的节点
2. 每个关键判断写进 data_evidence，注明依据哪条内部数据
3. 建议必须具体可执行，禁止空话；不要长报告，每条建议一句话
4. marketing_suggestions 必须含4条，分别以"小红书："朋友圈："社群："海报："开头
5. sales_suggestions 必须含4条，分别以"重点跟进："私聊方向："跟进节奏："异议处理："开头
6. academic_support_notes 必须覆盖：老师资源是否充足、是否需先评估、交付风险
7. backend_support_notes 必须覆盖：需补的资料、话术、风控边界
8. 资料缺口对应的方向不要给强推建议，写进 missing_data
9. 推广表达禁止"100%押中/保过承诺"类话术

只输出 JSON（不要 markdown 代码块）：
{{"main_product": "", "secondary_products": [], "cautious_products": [], "paused_products": [],
"why_this_strategy": [], "marketing_suggestions": [], "sales_suggestions": [],
"academic_support_notes": [], "backend_support_notes": [], "risk_notes": [],
"suggested_materials": [], "next_7d_prediction": "", "next_14d_prediction": "",
"next_30d_prediction": "", "data_evidence": [], "confidence": "high/medium/low", "missing_data": []}}"""

        parsed = None
        for attempt in range(2):
            resp = self.client.messages.create(
                model=self.model, max_tokens=3500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            try:
                parsed = json.loads(raw)
                break
            except json.JSONDecodeError as e:
                logger.warning(f"[StrategyCard] {sc['school_name']} JSON解析失败(第{attempt+1}次): {e}")
        if parsed is None:
            raise ValueError("两次生成均无法解析为JSON")

        # 数据过旧/资料缺口时压低可信度，不允许虚高
        if sc["missing_data"] and parsed.get("confidence") == "high":
            parsed["confidence"] = "medium"

        card = {
            "school_name": sc["school_name"], "country": sc["country"],
            "period": "weekly", "priority_level": sc["priority_level"],
            "current_stage": sc["current_stage"], "demand_heat": sc["demand_heat"],
        }
        for k in CARD_KEYS:
            if k in parsed:
                card[k] = parsed[k]
        save_strategy_card(card)
        card["missing_data"] = parsed.get("missing_data", [])
        return card
