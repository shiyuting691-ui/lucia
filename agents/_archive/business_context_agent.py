"""
BusinessContextAgent — 收集当前业务背景（V4 升级版）
优先读取动态市场信号，再结合静态 config.yaml
返回结构化 context dict 供其他 Workflow Agent 使用
"""
import logging
from datetime import datetime, timedelta
from database import (
    list_campaigns, list_contents, list_tasks, list_feedbacks,
    list_market_signals, get_current_patterns,
    list_school_calendar, get_order_stats, get_lead_stats,
)

logger = logging.getLogger(__name__)


class BusinessContextAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}

    def run(self) -> dict:
        try:
            today = datetime.utcnow()
            context = {
                "today": today.strftime("%Y-%m-%d"),
                "weekday": today.strftime("%A"),
                "month": today.month,
                # ── 动态市场信号 ──
                "hot_schools": [],
                "hot_products": [],
                "market_signals": [],
                "upcoming_nodes": [],
                "current_patterns": [],
                "order_stats_7d": {},
                "lead_stats_7d": {},
                # ── 系统状态 ──
                "active_campaigns": [],
                "recent_contents": [],
                "open_tasks_count": 0,
                "open_feedbacks_count": 0,
                "urgent_feedbacks": [],
            }

            # ── 1. 最新市场信号（近7天高优先级）─────────────────────
            try:
                signals = list_market_signals(days=7, limit=20)
                context["market_signals"] = signals

                # 从信号中提取热门学校/产品
                school_set: dict = {}
                product_set: dict = {}
                for s in signals:
                    if s.get("school"):
                        school_set[s["school"]] = school_set.get(s["school"], 0) + 1
                    if s.get("product"):
                        product_set[s["product"]] = product_set.get(s["product"], 0) + 1
                context["hot_schools"]  = sorted(school_set, key=lambda k: -school_set[k])[:5]
                context["hot_products"] = sorted(product_set, key=lambda k: -product_set[k])[:5]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: signals error: {e}")

            # ── 2. 未来28天学校节点 ───────────────────────────────────
            try:
                context["upcoming_nodes"] = list_school_calendar(days_ahead=28)[:10]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: calendar error: {e}")

            # ── 3. 往年同期规律 ───────────────────────────────────────
            try:
                context["current_patterns"] = get_current_patterns(days_window=21)[:5]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: patterns error: {e}")

            # ── 4. 订单/咨询统计 ─────────────────────────────────────
            try:
                context["order_stats_7d"] = get_order_stats(days=7)
                context["lead_stats_7d"]  = get_lead_stats(days=7)

                # 如果动态信号无数据，降级用订单统计
                if not context["hot_schools"]:
                    context["hot_schools"] = [s for s, _ in context["order_stats_7d"].get("by_school", [])[:5]]
                if not context["hot_products"]:
                    context["hot_products"] = [p for p, _ in context["order_stats_7d"].get("by_product", [])[:5]]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: order/lead stats error: {e}")

            # ── 5. 如果仍无数据，fallback 到 config.yaml ─────────────
            if not context["hot_schools"]:
                uk_schools = [s["name"] for s in self.config.get("schools", {}).get("uk", [])[:3]]
                au_schools = [s["name"] for s in self.config.get("schools", {}).get("australia", [])[:2]]
                context["hot_schools"] = uk_schools + au_schools
                logger.info("BusinessContextAgent: fallback to config.yaml schools")

            if not context["hot_products"]:
                context["hot_products"] = [p["id"] for p in self.config.get("products", [])[:3]]
                logger.info("BusinessContextAgent: fallback to config.yaml products")

            # ── 6. 营销活动 ───────────────────────────────────────────
            try:
                campaigns = list_campaigns(limit=5)
                context["active_campaigns"] = [
                    {"id": c["id"], "name": c["name"],
                     "core_theme": c.get("core_theme", ""),
                     "target_country": c.get("target_country", "")}
                    for c in campaigns if c.get("status") == "active"
                ]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: campaigns error: {e}")

            # ── 7. 任务/反馈状态 ─────────────────────────────────────
            try:
                open_tasks  = list_tasks(limit=50, status="todo")
                doing_tasks = list_tasks(limit=50, status="doing")
                context["open_tasks_count"] = len(open_tasks) + len(doing_tasks)
            except Exception as e:
                logger.warning(f"BusinessContextAgent: tasks error: {e}")

            try:
                feedbacks = list_feedbacks(status="open")
                urgent = [f for f in feedbacks if f.get("urgency") in ("高", "紧急")]
                context["open_feedbacks_count"] = len(feedbacks)
                context["urgent_feedbacks"] = [
                    {"id": f["id"], "title": f.get("title",""),
                     "department": f.get("department",""), "urgency": f.get("urgency","")}
                    for f in urgent[:3]
                ]
            except Exception as e:
                logger.warning(f"BusinessContextAgent: feedbacks error: {e}")

            logger.info(
                f"BusinessContextAgent: date={context['today']}, "
                f"hot_schools={context['hot_schools']}, "
                f"signals={len(context['market_signals'])}, "
                f"patterns={len(context['current_patterns'])}"
            )
            return context

        except Exception as e:
            logger.error(f"BusinessContextAgent fatal error: {e}")
            return {
                "today": datetime.utcnow().strftime("%Y-%m-%d"),
                "weekday": datetime.utcnow().strftime("%A"),
                "month": datetime.utcnow().month,
                "hot_schools": [], "hot_products": [],
                "market_signals": [], "upcoming_nodes": [],
                "current_patterns": [], "order_stats_7d": {}, "lead_stats_7d": {},
                "active_campaigns": [], "recent_contents": [],
                "open_tasks_count": 0, "open_feedbacks_count": 0, "urgent_feedbacks": [],
                "error": str(e),
            }
