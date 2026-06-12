"""
SchoolMarketIntelligenceAgent — 动态市场情报引擎
读取 orders/leads/school_calendar/yearly_patterns/department_feedback/content_usage
→ 生成动态市场信号和营销建议，写入 market_signals 表

每天运行一次（DailyWorkflow 中调用）
"""
import json
import logging
from collections import Counter
from datetime import datetime, timedelta
import anthropic
from database import (
    list_orders, list_leads, list_school_calendar,
    list_yearly_patterns, get_current_patterns,
    list_feedbacks, get_usage_stats,
    save_market_signal, list_market_signals,
    get_order_stats, get_lead_stats,
)

logger = logging.getLogger(__name__)


class SchoolMarketIntelligenceAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model  = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    def _gather_raw_data(self) -> dict:
        """收集所有原始数据"""
        today = datetime.utcnow()
        return {
            "today": today.strftime("%Y-%m-%d"),
            "order_stats_7d":   get_order_stats(days=7),
            "order_stats_30d":  get_order_stats(days=30),
            "lead_stats_7d":    get_lead_stats(days=7),
            "lead_stats_30d":   get_lead_stats(days=30),
            "upcoming_calendar": list_school_calendar(days_ahead=28),
            "current_patterns":  get_current_patterns(days_window=21),
            "open_feedbacks":    list_feedbacks(status="open"),
            "usage_stats":       get_usage_stats(),
            # 近7天具体订单/咨询（给 LLM 细粒度参考）
            "recent_orders_7d":  list_orders(days=7, limit=50),
            "recent_leads_7d":   list_leads(days=7, limit=50),
        }

    def _build_prompt(self, data: dict) -> str:
        today = data["today"]
        os7  = data["order_stats_7d"]
        os30 = data["order_stats_30d"]
        ls7  = data["lead_stats_7d"]
        ls30 = data["lead_stats_30d"]

        school_orders_7d  = os7.get("by_school", [])[:5]
        school_orders_30d = os30.get("by_school", [])[:5]
        product_7d  = os7.get("by_product", [])[:5]
        school_leads_7d = ls7.get("by_school", [])[:5]

        upcoming = data["upcoming_calendar"]
        patterns = data["current_patterns"]
        feedbacks = [f for f in data["open_feedbacks"] if f.get("urgency") in ("高","紧急")]

        cal_text = "\n".join([
            f"- {c['school']} {c['event_type']} 《{c['event_name']}》"
            f" {c.get('start_date','')[:10]}~{c.get('end_date','')[:10]}"
            f" (置信度:{c.get('confidence','')})"
            for c in upcoming[:10]
        ]) or "（无已录入节点数据）"

        pattern_text = "\n".join([
            f"- {p.get('country','')} {p.get('school','')} {p.get('product','')} "
            f"{p.get('period_start','')}~{p.get('period_end','')}: {p.get('pattern_summary','')}"
            for p in patterns[:8]
        ]) or "（无往年规律数据）"

        feedback_text = "\n".join([
            f"- [{f.get('urgency','')}] {f.get('department','')} {f.get('title','')}"
            for f in feedbacks[:5]
        ]) or "（无高优先级反馈）"

        return f"""你是极致教育留学辅导机构的市场情报分析师。今天是 {today}。

## 近7天数据摘要
- 订单量：{os7['total']}单，金额：¥{os7['total_amount']:.0f}
  热门学校：{school_orders_7d}
  热门产品：{product_7d}
- 咨询量：{ls7['total']}个，转化率：{ls7['conversion_rate']:.1%}
  咨询学校：{school_leads_7d}

## 近30天数据摘要
- 订单量：{os30['total']}单，金额：¥{os30['total_amount']:.0f}
  热门学校：{school_orders_30d}

## 未来28天学校节点
{cal_text}

## 当前往年同期规律
{pattern_text}

## 当前高优先级部门反馈
{feedback_text}

请基于以上数据，输出结构化市场情报分析（JSON，控制在3000字符以内）：
{{
  "date": "{today}",
  "hot_schools": ["最多5个"],
  "hot_products": ["最多4个"],
  "upcoming_nodes": [{{"school":"","event":"","date":"","action":""}}],
  "market_signals": [
    {{
      "country": "UK",
      "school": "UCL",
      "product": "dissertation",
      "signal_type": "咨询量上升",
      "signal_value": 5,
      "trend": "up",
      "evidence": "近7天UCL咨询5个",
      "priority": "高",
      "suggested_action": "立即推送UCL Dissertation专题内容"
    }}
  ],
  "marketing_actions": ["最多3条"],
  "risk_alerts": ["最多2条"]
}}

限制：market_signals 最多5条，marketing_actions 最多3条，risk_alerts 最多2条。
如数据量少，基于往年规律推断并标注。只输出 JSON。"""

    def run(self) -> dict:
        logger.info("SchoolMarketIntelligenceAgent: 开始生成市场信号...")
        data = self._gather_raw_data()

        # 即使没有LLM，也基于规则生成基础信号
        basic_signals = self._generate_rule_based_signals(data)

        try:
            prompt = self._build_prompt(data)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=[{
                    "type": "text",
                    "text": "你是极致教育留学辅导机构的市场情报分析师。基于数据输出JSON市场情报，不要其他说明。",
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
            intel = json.loads(raw)

            # 保存市场信号到 DB
            signals_saved = 0
            for sig in intel.get("market_signals", []):
                try:
                    save_market_signal(sig)
                    signals_saved += 1
                except Exception as e:
                    logger.warning(f"signal save error: {e}")

            # 也保存规则信号
            for sig in basic_signals:
                try:
                    save_market_signal(sig)
                    signals_saved += 1
                except Exception:
                    pass

            logger.info(f"SchoolMarketIntelligenceAgent: saved {signals_saved} signals")
            return {
                "signals_saved": signals_saved,
                "intelligence": intel,
                "hot_schools":  intel.get("hot_schools", []),
                "hot_products": intel.get("hot_products", []),
                "marketing_actions": intel.get("marketing_actions", []),
                "risk_alerts": intel.get("risk_alerts", []),
            }

        except Exception as e:
            logger.error(f"SchoolMarketIntelligenceAgent LLM error: {e}")
            # 降级：只保存规则信号
            for sig in basic_signals:
                try: save_market_signal(sig)
                except Exception: pass
            return {
                "signals_saved": len(basic_signals),
                "error": str(e),
                "hot_schools": [s for s, _ in data["order_stats_7d"].get("by_school", [])[:3]],
                "hot_products": [p for p, _ in data["order_stats_7d"].get("by_product", [])[:3]],
                "marketing_actions": [],
                "risk_alerts": [],
            }

    def _generate_rule_based_signals(self, data: dict) -> list:
        """纯规则信号（不依赖LLM），确保即使LLM失败也有基础信号"""
        signals = []
        today = datetime.utcnow()

        # 信号1：咨询量趋势（7d vs 前7d）
        os7  = data["order_stats_7d"]
        os30 = data["order_stats_30d"]
        if os7["total"] > 0:
            # 用30天总量推算7天基线
            baseline_7d = os30["total"] / 4  # 30天均摊4周
            if os7["total"] >= baseline_7d * 1.3:
                signals.append({
                    "country": "All",
                    "school": "",
                    "product": "",
                    "signal_type": "订单量上升",
                    "signal_value": os7["total"],
                    "trend": "up",
                    "evidence": f"近7天订单{os7['total']}单，高于30天周均基线({baseline_7d:.1f}单)",
                    "priority": "高",
                    "suggested_action": "加大推广力度，优先跟进活跃意向客户",
                })

        # 信号2：DDL集中（学校节点未来7天）
        upcoming_7d = [c for c in data["upcoming_calendar"]
                       if c.get("start_date") and c["start_date"][:10] <= (today + timedelta(days=7)).strftime("%Y-%m-%d")]
        if upcoming_7d:
            for node in upcoming_7d[:3]:
                signals.append({
                    "country": node.get("country", ""),
                    "school": node.get("school", ""),
                    "product": "",
                    "signal_type": "DDL集中",
                    "signal_value": 1,
                    "trend": "up",
                    "evidence": f"{node['school']} {node['event_type']} 将于 {node.get('start_date','')[:10]} 开始",
                    "priority": "紧急",
                    "suggested_action": f"立即针对 {node['school']} 发布紧急备考内容",
                })

        # 信号3：往年规律激活
        patterns = data["current_patterns"]
        for p in patterns[:3]:
            signals.append({
                "country": p.get("country", ""),
                "school": p.get("school", ""),
                "product": p.get("product", ""),
                "signal_type": "学校需求升温",
                "signal_value": p.get("historical_volume", 0),
                "trend": "up",
                "evidence": f"往年同期规律：{p.get('pattern_summary', '')}",
                "priority": "中",
                "suggested_action": p.get("suggested_campaign", "参考往年规律制定推广方案"),
            })

        return signals
