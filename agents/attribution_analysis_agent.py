"""
AttributionAnalysisAgent — 纯规则归因引擎（V10）

四个维度：
  1. 渠道归因   — 哪个来源渠道带来最多线索/转化/营收
  2. 顾问归因   — 哪个顾问 GMV/单量/客单价最高
  3. 产品-学校  — 哪个产品在哪个学校成单最多
  4. 时效归因   — 线索到成单平均多少天（按渠道/顾问拆分）

Claude 仅生成 key_insights（3 条洞察）和 action_items（2 条建议）。
数字全部来自规则计算，不依赖 LLM 输出数值。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class AttributionAnalysisAgent:
    def __init__(self, config: dict):
        self.config = config

    def run(self, days_lookback: int = 90) -> dict:
        """
        分析最近 days_lookback 天的归因数据。
        返回 snapshot dict，同时写入 attribution_snapshots 表。
        """
        from database import get_session
        from database.models import Order, Lead, AttributionSnapshot

        period_end = datetime(2025, 12, 20)   # 数据锚点
        period_start = period_end - timedelta(days=days_lookback)

        with get_session() as session:
            orders = session.query(Order).filter(
                Order.order_date >= period_start,
                Order.order_date <= period_end,
            ).all()
            leads = session.query(Lead).filter(
                Lead.inquiry_date >= period_start,
                Lead.inquiry_date <= period_end,
            ).all()

            order_rows = [self._order_to_dict(o) for o in orders]
            lead_rows  = [self._lead_to_dict(l) for l in leads]

        channel_data      = self._calc_channel(lead_rows, order_rows)
        advisor_data      = self._calc_advisor(order_rows)
        product_school    = self._calc_product_school(order_rows)
        speed_data        = self._calc_speed(lead_rows, order_rows)

        total_revenue = sum(r["amount"] for r in order_rows if r["amount"])

        key_insights, action_items = self._gen_insights(
            channel_data, advisor_data, product_school, speed_data, total_revenue
        )

        snapshot = {
            "snapshot_date":     datetime.now().strftime("%Y-%m-%d"),
            "period_start":      period_start.strftime("%Y-%m-%d"),
            "period_end":        period_end.strftime("%Y-%m-%d"),
            "channel_data":      channel_data,
            "advisor_data":      advisor_data,
            "product_school_data": product_school,
            "speed_data":        speed_data,
            "key_insights":      key_insights,
            "action_items":      action_items,
            "order_count":       len(order_rows),
            "lead_count":        len(lead_rows),
            "total_revenue":     round(total_revenue, 2),
        }

        self._save(snapshot)
        logger.info("归因分析完成：%d 订单 / %d 线索", len(order_rows), len(lead_rows))
        return snapshot

    # ── 维度 1：渠道归因 ─────────────────────────────────────────────
    def _calc_channel(self, leads: list, orders: list) -> list:
        from collections import defaultdict

        ch_leads = defaultdict(int)
        for l in leads:
            ch = l["source_channel"] or "未知"
            ch_leads[ch] += 1

        # 尝试将线索匹配到订单（按 customer_name + school 模糊匹配）
        order_lookup = {}
        for o in orders:
            key = (o["customer_id"] or "", o["school"] or "")
            order_lookup[key] = o

        ch_orders   = defaultdict(int)
        ch_revenue  = defaultdict(float)
        ch_days     = defaultdict(list)

        for l in leads:
            ch = l["source_channel"] or "未知"
            key = (l["customer_name"] or "", l["school"] or "")
            if key in order_lookup:
                o = order_lookup[key]
                ch_orders[ch] += 1
                ch_revenue[ch] += o["amount"] or 0
                if l["inquiry_date"] and o["order_date"]:
                    diff = (o["order_date"] - l["inquiry_date"]).days
                    if 0 <= diff <= 180:
                        ch_days[ch].append(diff)

        all_channels = set(list(ch_leads.keys()) + list(ch_orders.keys()))
        result = []
        for ch in all_channels:
            lc = ch_leads[ch]
            oc = ch_orders[ch]
            rev = ch_revenue[ch]
            days_list = ch_days[ch]
            result.append({
                "channel":    ch,
                "lead_count": lc,
                "order_count": oc,
                "revenue":    round(rev, 2),
                "cvr":        round(oc / lc * 100, 1) if lc > 0 else 0,
                "avg_days_to_close": round(sum(days_list) / len(days_list), 1) if days_list else None,
            })

        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result

    # ── 维度 2：顾问归因 ─────────────────────────────────────────────
    def _calc_advisor(self, orders: list) -> list:
        from collections import defaultdict

        adv_count   = defaultdict(int)
        adv_revenue = defaultdict(float)
        adv_products = defaultdict(lambda: defaultdict(int))
        adv_schools  = defaultdict(lambda: defaultdict(int))

        for o in orders:
            adv = o["sales_owner"] or "未分配"
            adv_count[adv] += 1
            adv_revenue[adv] += o["amount"] or 0
            if o["product"]:
                adv_products[adv][o["product"]] += 1
            if o["school"]:
                adv_schools[adv][o["school"]] += 1

        result = []
        for adv in adv_count:
            cnt = adv_count[adv]
            rev = adv_revenue[adv]
            top_product = max(adv_products[adv], key=adv_products[adv].get) if adv_products[adv] else None
            top_school  = max(adv_schools[adv],  key=adv_schools[adv].get)  if adv_schools[adv]  else None
            result.append({
                "advisor":      adv,
                "order_count":  cnt,
                "gmv":          round(rev, 2),
                "avg_amount":   round(rev / cnt, 2) if cnt > 0 else 0,
                "top_product":  top_product,
                "top_school":   top_school,
            })

        result.sort(key=lambda x: x["gmv"], reverse=True)
        return result

    # ── 维度 3：产品 × 学校矩阵 ─────────────────────────────────────
    def _calc_product_school(self, orders: list) -> list:
        from collections import defaultdict

        matrix = defaultdict(lambda: {"count": 0, "revenue": 0.0})
        for o in orders:
            prod = o["product"] or "未知"
            school = o["school"] or "未知"
            key = (prod, school)
            matrix[key]["count"] += 1
            matrix[key]["revenue"] += o["amount"] or 0

        result = []
        for (prod, school), v in matrix.items():
            cnt = v["count"]
            rev = v["revenue"]
            result.append({
                "product":     prod,
                "school":      school,
                "order_count": cnt,
                "revenue":     round(rev, 2),
                "avg_amount":  round(rev / cnt, 2) if cnt > 0 else 0,
            })

        result.sort(key=lambda x: x["order_count"], reverse=True)
        return result[:30]   # 取前 30 条

    # ── 维度 4：时效归因（按顾问拆分） ──────────────────────────────
    def _calc_speed(self, leads: list, orders: list) -> list:
        from collections import defaultdict

        order_lookup = {}
        for o in orders:
            key = (o["customer_id"] or "", o["school"] or "")
            order_lookup[key] = o

        adv_days = defaultdict(list)
        for l in leads:
            key = (l["customer_name"] or "", l["school"] or "")
            if key in order_lookup:
                o = order_lookup[key]
                adv = o["sales_owner"] or "未分配"
                if l["inquiry_date"] and o["order_date"]:
                    diff = (o["order_date"] - l["inquiry_date"]).days
                    if 0 <= diff <= 365:
                        adv_days[adv].append(diff)

        result = []
        for adv, days in adv_days.items():
            if not days:
                continue
            days_sorted = sorted(days)
            n = len(days_sorted)
            result.append({
                "advisor":      adv,
                "sample_count": n,
                "avg_days":     round(sum(days) / n, 1),
                "median_days":  days_sorted[n // 2],
                "min_days":     min(days),
                "max_days":     max(days),
            })

        result.sort(key=lambda x: x["avg_days"])
        return result

    # ── Claude 生成洞察（少量文字，不预测数字） ──────────────────────
    def _gen_insights(self, channel_data, advisor_data, product_school, speed_data, total_revenue):
        try:
            import anthropic, os
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

            summary = self._build_summary_text(
                channel_data, advisor_data, product_school, speed_data, total_revenue
            )

            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": f"""你是极致教育的增长分析师。基于以下归因数据，给出：
1. 3条关键洞察（每条≤30字，要有具体数字，只讲规律）
2. 2条下周行动建议（每条≤25字，直接可执行）

格式：
INSIGHTS:
- 洞察1
- 洞察2
- 洞察3
ACTIONS:
- 建议1
- 建议2

数据摘要：
{summary}"""
                }]
            )
            return self._parse_insights(msg.content[0].text)
        except Exception as e:
            logger.warning("Claude 洞察生成失败：%s", e)
            return self._fallback_insights(channel_data, advisor_data, product_school)

    def _build_summary_text(self, channel_data, advisor_data, product_school, speed_data, total_revenue) -> str:
        lines = [f"总营收：{total_revenue:.0f}元"]

        if channel_data:
            top = channel_data[0]
            lines.append(f"最高营收渠道：{top['channel']}（{top['revenue']:.0f}元，{top['lead_count']}条线索）")
        if advisor_data:
            top = advisor_data[0]
            lines.append(f"最高GMV顾问：{top['advisor']}（{top['gmv']:.0f}元，{top['order_count']}单）")
        if product_school:
            top = product_school[0]
            lines.append(f"最热产品-学校：{top['product']}×{top['school']}（{top['order_count']}单）")
        if speed_data:
            fastest = speed_data[0]
            lines.append(f"最快成交顾问：{fastest['advisor']}（平均{fastest['avg_days']}天）")

        return "\n".join(lines)

    @staticmethod
    def _parse_insights(text: str):
        insights, actions = [], []
        section = None
        for line in text.strip().splitlines():
            line = line.strip()
            if line.startswith("INSIGHTS:"):
                section = "i"
            elif line.startswith("ACTIONS:"):
                section = "a"
            elif line.startswith("- ") and section == "i":
                insights.append(line[2:])
            elif line.startswith("- ") and section == "a":
                actions.append(line[2:])
        return insights[:3], actions[:2]

    @staticmethod
    def _fallback_insights(channel_data, advisor_data, product_school):
        insights = []
        if channel_data:
            top = channel_data[0]
            insights.append(f"{top['channel']}是最高营收渠道，占比最大，建议优先投入")
        if advisor_data:
            top = advisor_data[0]
            insights.append(f"{top['advisor']} GMV最高，客单价{top['avg_amount']:.0f}元，可作标杆")
        if product_school:
            top = product_school[0]
            insights.append(f"{top['product']}在{top['school']}成单{top['order_count']}次，是核心组合")
        return insights, []

    # ── 存储 ────────────────────────────────────────────────────────
    def _save(self, snapshot: dict):
        from database import get_session
        from database.models import AttributionSnapshot

        with get_session() as session:
            existing = session.query(AttributionSnapshot).filter_by(
                snapshot_date=snapshot["snapshot_date"]
            ).first()
            if existing:
                for k, v in snapshot.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                obj = AttributionSnapshot(**{k: v for k, v in snapshot.items()
                                             if hasattr(AttributionSnapshot, k)})
                session.add(obj)
            session.commit()

    # ── 辅助：ORM → dict ────────────────────────────────────────────
    @staticmethod
    def _order_to_dict(o) -> dict:
        return {
            "id":          o.id,
            "order_date":  o.order_date,
            "customer_id": o.customer_id,
            "school":      o.school,
            "product":     o.product,
            "amount":      o.amount or 0,
            "sales_owner": o.sales_owner,
        }

    @staticmethod
    def _lead_to_dict(l) -> dict:
        return {
            "id":             l.id,
            "inquiry_date":   l.inquiry_date,
            "customer_name":  l.customer_name,
            "school":         l.school,
            "source_channel": l.source_channel,
            "deal_status":    l.deal_status,
            "sales_owner":    l.sales_owner,
            "quoted_price":   l.quoted_price,
        }
