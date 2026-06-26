"""
HistoricalPatternAgent — 分析历史订单/咨询数据，识别季节性规律
把规律写入 yearly_patterns 表，供 SchoolMarketIntelligenceAgent 使用
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
import anthropic
from database import list_orders, list_leads, save_yearly_pattern, list_yearly_patterns

logger = logging.getLogger(__name__)


class HistoricalPatternAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model  = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    def _aggregate_data(self) -> dict:
        """汇总所有历史订单/咨询，按 (country, school, product, month) 分组"""
        orders = list_orders(days=730)  # 最近两年
        leads  = list_leads(days=730)

        # 按 (country, school, product, month) 统计
        order_groups: dict = defaultdict(list)
        for o in orders:
            if not o.get("order_date"):
                continue
            try:
                dt = datetime.fromisoformat(o["order_date"][:10])
                key = (o.get("country",""), o.get("school",""), o.get("product",""), dt.strftime("%m"))
                order_groups[key].append(o)
            except Exception:
                pass

        lead_groups: dict = defaultdict(list)
        for l in leads:
            if not l.get("inquiry_date"):
                continue
            try:
                dt = datetime.fromisoformat(l["inquiry_date"][:10])
                key = (l.get("country",""), l.get("school",""), l.get("product_interest",""), dt.strftime("%m"))
                lead_groups[key].append(l)
            except Exception:
                pass

        return {"orders": dict(order_groups), "leads": dict(lead_groups),
                "total_orders": len(orders), "total_leads": len(leads)}

    def run(self) -> dict:
        logger.info("HistoricalPatternAgent: 开始分析历史规律...")
        agg = self._aggregate_data()

        if agg["total_orders"] == 0 and agg["total_leads"] == 0:
            logger.info("HistoricalPatternAgent: 暂无历史数据，跳过")
            return {"patterns_saved": 0, "message": "暂无历史订单/咨询数据，请先导入数据"}

        # 构建分析摘要文本，送给 LLM
        summary_lines = []
        all_keys = set(list(agg["orders"].keys()) + list(agg["leads"].keys()))
        for key in sorted(all_keys)[:50]:  # 最多50个维度，避免 token 过多
            country, school, product, month = key
            orders_n = len(agg["orders"].get(key, []))
            leads_n  = len(agg["leads"].get(key, []))
            won  = sum(1 for l in agg["leads"].get(key, []) if l.get("deal_status") == "won")
            summary_lines.append(
                f"{country}|{school}|{product}|{month}月: 订单{orders_n}单, 咨询{leads_n}个, 成交{won}个"
            )

        data_text = "\n".join(summary_lines) if summary_lines else "数据维度不足"

        prompt = f"""你是留学辅导机构极致教育的数据分析师。
以下是按（国家|学校|产品|月份）聚合的历史订单和咨询数据：

{data_text}

请分析识别出季节性规律（高峰期、淡季），输出 JSON 数组（最多15条最有价值的规律）：
[
  {{
    "country": "UK",
    "school": "UCL",
    "product": "dissertation",
    "period_start": "04-01",
    "period_end": "06-30",
    "pattern_summary": "UCL学生4-6月dissertation高峰，订单量明显上升，需提前2周启动推广",
    "historical_volume": 8,
    "conversion_rate": 0.65,
    "recommended_lead_time_days": 14,
    "suggested_campaign": "UCL Dissertation 冲刺包 · 包过承诺限时优惠"
  }}
]

注意：period_start / period_end 用 MM-DD 格式，只写最有统计意义的规律。"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                system=[{
                    "type": "text",
                    "text": "你是数据驱动的留学辅导机构运营分析师。只输出 JSON 数组，不要其他说明。",
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
            patterns = json.loads(raw)

            saved = 0
            for p in patterns:
                try:
                    save_yearly_pattern(p)
                    saved += 1
                except Exception as e:
                    logger.warning(f"pattern save error: {e}")

            msg = f"历史规律分析完成：识别 {len(patterns)} 条规律，保存 {saved} 条"
            logger.info(msg)
            return {"patterns_saved": saved, "message": msg}

        except Exception as e:
            logger.error(f"HistoricalPatternAgent error: {e}")
            return {"patterns_saved": 0, "error": str(e)}
