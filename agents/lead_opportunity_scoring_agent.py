"""
LeadOpportunityScoringAgent — 线索机会评分（纯规则，不调用 LLM）

评分维度（共100分）：
  报价未成交且仍在跟进 (25) / 学校热度（S/A级） (20) /
  DDL 临近 7天内 (20) / 咨询时间新鲜度 (15) / 热门产品意向 (10) / 无流失标记 (10)

输出写入 lead_scores 表（upsert），同时同步一条 opportunity_scores。
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from database.db import engine
from database import save_lead_score, save_opportunity_score, list_school_scores

logger = logging.getLogger(__name__)

HOT_PRODUCTS = {"final_prediction", "guaranteed", "annual_package", "dp_premium", "dissertation"}
ACTIVE_STATUSES = {"new", "contacted", "quoted", "follow_up"}


def _traffic(score: int) -> str:
    if score >= 70: return "green"
    if score >= 45: return "yellow"
    if score >= 20: return "red"
    return "gray"


def _level(score: int, insufficient: bool) -> str:
    if insufficient: return "Unknown"
    if score >= 85: return "S"
    if score >= 70: return "A"
    if score >= 50: return "B"
    if score >= 30: return "C"
    return "低机会"


class LeadOpportunityScoringAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        # 预加载学校优先级映射
        self._school_levels: dict[str, str] = {}
        try:
            scores = list_school_scores(limit=50)
            self._school_levels = {s["school_name"]: s["priority_level"] for s in scores}
        except Exception:
            pass

    def run(self, days_lookback: int = 14, limit: int = 200) -> list[dict]:
        """对最近 days_lookback 天的 active 线索评分"""
        anchor = datetime.now()
        cutoff = (anchor - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
        a = anchor.strftime("%Y-%m-%d")

        with engine.connect() as c:
            leads = c.execute(text(
                "SELECT id, customer_name, school, product_interest, deal_status, "
                "deadline, inquiry_date, quoted_price "
                "FROM leads WHERE inquiry_date >= :cutoff "
                "AND deal_status NOT IN ('won','lost','inactive') "
                "ORDER BY inquiry_date DESC LIMIT :n"
            ), {"cutoff": cutoff, "n": limit}).fetchall()

        results = []
        for row in leads:
            results.append(self._score_one(row, anchor))
        logger.info(f"[LeadOpportunityScoringAgent] 评分 {len(results)} 条线索")
        return results

    def _score_one(self, row, anchor: datetime) -> dict:
        (lid, cname, school, product, deal_status, deadline, inquiry_date, quoted_price) = row
        reasons, flags = [], []
        score = 0

        # 1. 报价未成交且仍在跟进 (25分)
        if deal_status in ("quoted", "follow_up"):
            score += 25
            reasons.append(f"已报价/跟进中 → 25/25")
        elif deal_status == "contacted":
            score += 15
            reasons.append(f"已接触未报价 → 15/25")
        else:
            score += 5
            reasons.append(f"新线索 → 5/25")

        # 2. 学校热度 (20分)
        school_level = self._school_levels.get(school or "", "Unknown")
        if school_level == "S":
            score += 20; reasons.append("学校S级 → 20/20")
        elif school_level == "A":
            score += 15; reasons.append("学校A级 → 15/20")
        elif school_level == "B":
            score += 10; reasons.append("学校B级 → 10/20")
        elif school_level in ("C", "低机会"):
            score += 3; reasons.append(f"学校{school_level}级 → 3/20")
        else:
            reasons.append("学校未评分 → 0/20")

        # 3. DDL临近 (20分)
        s3 = 0
        if deadline:
            try:
                dl = datetime.fromisoformat(str(deadline)[:10])
                days_left = (dl - anchor).days
                if days_left <= 3:
                    s3 = 20; flags.append("DDL≤3天 🚨")
                elif days_left <= 7:
                    s3 = 15; flags.append("DDL≤7天")
                elif days_left <= 14:
                    s3 = 8
            except (ValueError, TypeError):
                pass
        score += s3
        reasons.append(f"DDL临近 → {s3}/20")

        # 4. 咨询新鲜度 (15分)：7天内满分
        s4 = 0
        if inquiry_date:
            try:
                iq = datetime.fromisoformat(str(inquiry_date)[:10])
                age = (anchor - iq).days
                s4 = max(0, 15 - age * 2)
            except (ValueError, TypeError):
                pass
        score += s4
        reasons.append(f"咨询新鲜度 → {s4}/15")

        # 5. 热门产品意向 (10分)
        if (product or "").lower() in HOT_PRODUCTS:
            score += 10; reasons.append(f"热门产品意向({product}) → 10/10")
        else:
            reasons.append("产品意向非热门 → 0/10")

        # 6. 无流失标记 (10分)
        if deal_status not in ("lost", "inactive"):
            score += 10; reasons.append("无流失标记 → 10/10")
        else:
            reasons.append("已流失 → 0/10")

        score = min(100, score)
        insufficient = (deal_status == "new" and not deadline and not quoted_price)
        level = _level(score, insufficient)
        traffic = _traffic(score)

        # 行动建议
        if flags or score >= 70:
            action = f"立即跟进 {school or ''} {product or ''} 线索（{', '.join(flags) or '高评分'}）"
        elif score >= 50:
            action = f"本周优先跟进，确认报价和DDL"
        else:
            action = "维持常规跟进节奏"

        data = {
            "lead_id": lid, "customer_name": cname or "",
            "school": school or "", "product_interest": product or "",
            "score": score, "level": level,
            "score_reason": reasons, "urgent_flags": flags,
            "suggested_action": action,
        }
        save_lead_score(data)

        # 同步写入 opportunity_scores（score_type=lead）
        save_opportunity_score({
            "score_type": "lead",
            "entity_name": f"lead_{lid}_{cname or ''}",
            "entity_id": str(lid),
            "score": score,
            "level": level,
            "traffic_light": traffic,
            "score_reason": reasons,
            "risk_flags": flags,
            "recommendation": action,
        })
        return data
