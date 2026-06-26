"""
真实需求分析服务
从订单DB提取真实需求分布，作为推送建议的数据依据
"""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from database.crud import get_session
from database.models import Order, SchoolCalendar
from sqlalchemy import select, func, text

logger = logging.getLogger(__name__)


def get_demand_snapshot(days: int = 30) -> dict:
    """
    提取近N天的真实需求快照
    返回: country/product/school 维度的订单量和金额
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as s:
        rows = s.execute(
            select(
                Order.country,
                Order.product,
                Order.school,
                Order.service_type,
                Order.amount,
                Order.order_date,
                Order.sales_owner,
            ).where(
                Order.order_date >= cutoff,
                Order.country.isnot(None),
                Order.country != "",
            )
        ).fetchall()

    if not rows:
        return {}

    # ── country×product 矩阵 ──────────────────────────────────────
    cp_matrix = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    cs_matrix = defaultdict(lambda: {"count": 0, "revenue": 0.0})  # country×school
    country_total = defaultdict(int)

    for row in rows:
        country, product, school, stype, amount, odate, owner = row
        c = (country or "").upper()
        p = product or ""
        sch = (school or "").strip()
        amt = float(amount or 0)

        if not c or not p:
            continue

        cp_matrix[(c, p)]["count"] += 1
        cp_matrix[(c, p)]["revenue"] += amt
        country_total[c] += 1

        if sch:
            cs_matrix[(c, sch)]["count"] += 1
            cs_matrix[(c, sch)]["revenue"] += amt

    # ── 按国家整理 top 产品 ──────────────────────────────────────────
    by_country = {}
    for country in sorted(country_total, key=lambda x: -country_total[x]):
        total = country_total[country]
        products = [
            {
                "product": p,
                "count": data["count"],
                "revenue": round(data["revenue"]),
                "share": round(data["count"] / total * 100, 1),
            }
            for (c, p), data in cp_matrix.items()
            if c == country
        ]
        products.sort(key=lambda x: -x["count"])

        schools = [
            {
                "school": sch,
                "count": data["count"],
                "revenue": round(data["revenue"]),
            }
            for (c, sch), data in cs_matrix.items()
            if c == country
        ]
        schools.sort(key=lambda x: -x["count"])

        by_country[country] = {
            "total_orders": total,
            "top_products": products[:8],
            "top_schools": schools[:10],
        }

    return {
        "period_days": days,
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "total_orders": sum(country_total.values()),
        "by_country": by_country,
    }


def get_upcoming_school_events(days_ahead: int = 60) -> list:
    """
    从 school_calendar 提取未来N天的关键事件
    包括各学校的考试期/提交截止/开学
    """
    now = datetime.utcnow()
    future = now + timedelta(days=days_ahead)
    with get_session() as s:
        raw_rows = s.execute(
            select(SchoolCalendar).where(
                SchoolCalendar.start_date >= now,
                SchoolCalendar.start_date <= future,
            ).order_by(SchoolCalendar.start_date)
        ).scalars().all()
        # 在 session 内转换，避免 DetachedInstanceError
        rows = [
            {
                "school": r.school, "country": r.country,
                "event_type": r.event_type, "event_name": r.event_name,
                "start_date": r.start_date, "confidence": r.confidence, "source": r.source,
            }
            for r in raw_rows
        ]

    events = []
    for r in rows:
        start_dt = r["start_date"]
        days_until = (start_dt.date() - datetime.now().date()).days if start_dt else 999
        if days_until <= 7:
            urgency = "极高"
        elif days_until <= 14:
            urgency = "高"
        elif days_until <= 30:
            urgency = "中"
        else:
            urgency = "低"

        events.append({
            "school": r["school"],
            "country": r["country"],
            "event_type": r["event_type"],
            "event_name": r["event_name"],
            "start_date": start_dt.strftime("%Y-%m-%d") if start_dt else "",
            "days_until": days_until,
            "urgency": urgency,
            "confidence": r["confidence"],
            "source": r["source"],
        })

    return events


def get_hot_school_product_combos(days: int = 30, top_n: int = 10) -> list:
    """
    找出最热门的 学校×产品 组合（当前在读量最大的）
    用于内容策略精准定向
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as s:
        rows = s.execute(
            select(
                Order.country,
                Order.school,
                Order.product,
                func.count().label("cnt"),
                func.sum(Order.amount).label("rev"),
            ).where(
                Order.order_date >= cutoff,
                Order.school.isnot(None),
                Order.school != "",
                Order.product.isnot(None),
                Order.product != "",
            ).group_by(Order.country, Order.school, Order.product)
            .order_by(text("cnt DESC"))
            .limit(top_n * 3)
        ).fetchall()

    combos = []
    for country, school, product, cnt, rev in rows:
        combos.append({
            "country": country,
            "school": school,
            "product": product,
            "count": cnt,
            "revenue": round(float(rev or 0)),
        })

    return combos[:top_n]


def build_push_data_basis(days: int = 30) -> dict:
    """
    为推送内容构建完整的数据基础
    整合: 近期需求快照 + 即将到来的学校事件 + 热门学校×产品组合
    """
    snapshot = get_demand_snapshot(days=days)
    events = get_upcoming_school_events(days_ahead=60)
    hot_combos = get_hot_school_product_combos(days=days)

    # 找出最近 14 天内的高优先级事件
    urgent_events = [e for e in events if e["days_until"] <= 14 and e["event_type"] in ("exam_period", "submission")]

    # 当前主力国家（按订单量）
    by_country = snapshot.get("by_country", {})
    main_countries = list(by_country.keys())[:4]

    summary_lines = []
    for country in main_countries:
        data = by_country[country]
        top3 = [p["product"] for p in data["top_products"][:3]]
        top2_school = [s["school"] for s in data["top_schools"][:2]]
        summary_lines.append(
            f"{country}({data['total_orders']}单): "
            f"热销={'+'.join(top3[:2])}, "
            f"主力学校={'/'.join(top2_school[:2])}"
        )

    return {
        "snapshot": snapshot,
        "upcoming_events": events[:20],
        "urgent_events": urgent_events,
        "hot_combos": hot_combos,
        "main_countries": main_countries,
        "summary": "; ".join(summary_lines),
        "generated_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import json, logging
    logging.basicConfig(level=logging.WARNING)
    result = build_push_data_basis(days=30)
    print(f"\n近30天需求快照:")
    print(f"总订单: {result['snapshot']['total_orders']}")
    print(f"摘要: {result['summary']}")
    print(f"\n未来60天关键事件: {len(result['upcoming_events'])} 个")
    for e in result['upcoming_events'][:10]:
        print(f"  [{e['urgency']}] {e['school']} {e['event_name']} ({e['start_date']}, {e['days_until']}天后)")
    print(f"\n热门学校×产品组合 Top10:")
    for c in result['hot_combos']:
        print(f"  {c['country']} {c['school']} × {c['product']}: {c['count']}单")
