"""
ProductTrafficLight — 产品红绿灯（Catalog-driven v3）

产品来源：ProductCatalogService（读取 knowledge_base/product_catalog.py）
不允许在本文件硬编码产品列表。

状态定义：
  green  🟢 全力推          需求↑ + 容量充足 + 无高风险告警
  yellow 🟡 控量推，确认后推  容量偏紧 或 需求持平 或 有中级告警
  red    🔴 先确认资源再接单  容量不足 或 有高级告警
  grey   ⚫ 补充资料后可推    数据不足，无法判断
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProductTrafficLight:
    def __init__(self, config: dict = None):
        self.config = config or {}

    def run(self) -> dict:
        """返回每个 active 产品的红绿灯状态 dict。产品列表来自 ProductCatalogService。"""
        # ── 从产品目录库加载 active 产品 ───────────────────────────
        try:
            from services.product_catalog_service import ProductCatalogService
            catalog_products = ProductCatalogService.load_active_products()
        except RuntimeError as e:
            logger.error(f"[TrafficLight] 产品目录库加载失败: {e}")
            raise  # 禁止 fallback，必须报错

        # ── 读取订单和容量数据 ──────────────────────────────────────
        try:
            from database import list_orders, list_teacher_capacity
            recent_orders_7  = list_orders(days=7,  limit=2000)
            recent_orders_14 = list_orders(days=14, limit=2000)
            capacities       = list_teacher_capacity()
        except Exception as e:
            logger.warning(f"[TrafficLight] DB read failed: {e}")
            recent_orders_7  = []
            recent_orders_14 = []
            capacities       = []

        result = {}
        for product in catalog_products:
            pid = product["canonical_product_id"]
            tl = self._evaluate(product, recent_orders_7, recent_orders_14, capacities)
            result[pid] = tl

        summary = ", ".join(f"{pid}={v['status']}" for pid, v in result.items())
        logger.info(f"[TrafficLight] evaluated {len(result)} products: {summary}")
        return result

    def _evaluate(self, product: dict,
                  orders_7: list, orders_14: list, capacities: list) -> dict:
        from services.product_catalog_service import ProductCatalogService

        pid          = product["canonical_product_id"]
        product_name = product["product_name"]

        # ── 1. 订单趋势（通过 ProductCatalogService alias 映射）────────
        def _order_matches(o: dict) -> bool:
            raw = str(o.get("product") or o.get("product_id") or "")
            result = ProductCatalogService.map_raw_product(raw)
            return result["canonical_product_id"] == pid

        cnt_7  = sum(1 for o in orders_7  if _order_matches(o))
        cnt_14 = sum(1 for o in orders_14 if _order_matches(o))
        prev_7 = cnt_14 - cnt_7
        trend_pct = ((cnt_7 - prev_7) / max(prev_7, 1)) * 100

        if cnt_7 + cnt_14 == 0:
            demand_level = "unknown"
        elif trend_pct > 20:
            demand_level = "rising"
        elif trend_pct < -20:
            demand_level = "falling"
        else:
            demand_level = "stable"

        # ── 2. 老师容量（通过产品目录库的 capacity_subject_keywords）────
        keywords = ProductCatalogService.get_capacity_keywords(pid)
        relevant = [c for c in capacities if any(
            kw in str(c.get("subject_area", "")).lower() or
            kw in str(c.get("course_type", "")).lower()
            for kw in keywords
        )]

        capacity_required = product.get("capacity_required", True)

        if not relevant:
            cap_status = "unknown"
            cap_slots  = None
            cap_note   = "老师容量数据未录入"
        else:
            total_slots = sum(c.get("available_slots", 0) or 0 for c in relevant)
            cap_slots   = total_slots
            if total_slots >= 5:
                cap_status = "sufficient"
                cap_note   = f"可承接约{total_slots}单/周"
            elif total_slots >= 2:
                cap_status = "tight"
                cap_note   = f"名额偏紧（约{total_slots}单），接单前须确认"
            else:
                cap_status = "full"
                cap_note   = f"名额极少（约{total_slots}单），接单前必须学管点头"

        # ── 3. 数据充足度 ──────────────────────────────────────────
        missing = []
        if capacity_required and cap_status == "unknown":
            missing.append("老师容量数据")
        if cnt_7 + cnt_14 == 0:
            missing.append("近期订单记录（可能正常，也可能是数据未录入）")

        # 必须有容量数据才能判断的产品
        data_ok = not (capacity_required and cap_status == "unknown")

        # ── 4. 综合判定 ────────────────────────────────────────────
        product_risk = product.get("risk_level", "medium")

        if not data_ok and "老师容量数据" in missing:
            status = "grey"
            status_reason = f"数据不足，无法判断：{' / '.join(missing)}"
        elif cap_status == "full":
            status = "red"
            status_reason = f"名额极少，接单前必须学管确认资源（{cap_note}）"
        elif product_risk == "high" and cap_status != "sufficient":
            status = "red"
            status_reason = f"高风险产品，容量未确认，接单前必须学管点头"
        elif cap_status == "tight" and demand_level == "rising":
            status = "yellow"
            status_reason = f"需求上升但容量偏紧，控量推广，确认资源后报价"
        elif cap_status in ("sufficient", "unknown") and demand_level in ("rising", "stable"):
            status = "green"
            status_reason = f"需求{_demand_cn(demand_level)}，{cap_note or '容量数据待补充但无告警'}"
        elif not capacity_required and demand_level in ("rising", "stable", "unknown"):
            # 不需要老师资源的产品（如 AI合规）
            status = "green"
            status_reason = f"无需老师资源，需求{_demand_cn(demand_level)}，可正常推广"
        elif demand_level == "falling":
            status = "yellow"
            status_reason = f"近期需求下降，谨慎推广，先了解原因"
        else:
            status = "yellow"
            status_reason = "数据有限，保守推广，接单前确认资源"

        # ── 5. 渠道建议（来自产品目录库）─────────────────────────────
        suitable_channels = product.get("suitable_channels", [])
        consultant_note   = product.get("consultant_note", "")
        xueguan_note      = product.get("xueguan_note", "")

        if status == "red":
            recommended_channels = ["old_customer"]
            avoid_channels       = [c for c in ["xiaohongshu", "vertical_account"]
                                     if c not in suitable_channels]
            consultant_note      = "接单前必须学管点头，不单独承诺。" + consultant_note
            xueguan_note         = (cap_note or "资源确认后方可放行接单") + "。" + xueguan_note
        elif status == "yellow":
            recommended_channels = [c for c in suitable_channels
                                     if c in ("old_customer", "moments", "referral", "wechat_group")]
            avoid_channels       = []
            consultant_note      = "报价前确认学管资源，不提前承诺交付时间。" + consultant_note
            xueguan_note         = (cap_note or "接单前确认老师排期") + "。" + xueguan_note
        elif status == "grey":
            recommended_channels = ["old_customer"]
            avoid_channels       = ["xiaohongshu", "vertical_account"]
            consultant_note      = "资料不足，接单前必须确认。" + consultant_note
            xueguan_note         = (cap_note or "补充数据后再开放接单") + "。" + xueguan_note
        else:  # green
            recommended_channels = suitable_channels
            avoid_channels       = []

        return {
            "product_id":            pid,
            "product_name":          product_name,
            "product_category":      product.get("product_category", ""),
            "status":                status,
            "status_display":        _status_display(status),
            "status_reason":         status_reason,
            "teacher_capacity":      cap_note or "数据不足",
            "demand_trend":          _demand_cn(demand_level),
            "demand_7d":             cnt_7,
            "demand_prev_7d":        prev_7,
            "demand_trend_pct":      round(trend_pct, 1),
            "risks":                 _risks(status, cap_status, demand_level, missing, product_risk),
            "recommended_channels":  recommended_channels,
            "avoid_channels":        avoid_channels,
            "consultant_note":       consultant_note,
            "xueguan_note":          xueguan_note,
            "forbidden_claims":      product.get("forbidden_claims", []),
            "suitable_time_windows": product.get("suitable_time_windows", []),
            "data_evidence":         (
                f"近7天订单{cnt_7}单 vs 前7天{prev_7}单（趋势{'+' if trend_pct>0 else ''}"
                f"{trend_pct:.0f}%）；老师容量：{cap_note or '未录入'}"
            ),
            "missing_data":          missing,
            "catalog_source":        product.get("source", "product_catalog"),
        }


def _demand_cn(level: str) -> str:
    return {"rising": "上升↑", "falling": "下降↓",
            "stable": "持平→", "unknown": "数据不足"}.get(level, level)


def _status_display(status: str) -> str:
    m = {
        "green":   "🟢 全力推",
        "yellow":  "🟡 控量推，确认后推",
        "red":     "🔴 先确认资源再接单",
        "grey":    "⚫ 补充资料后可推",
        "blocked": "🔴 先确认资源再接单",
    }
    return m.get(status, status)


def _risks(status, cap_status, demand, missing, product_risk="medium"):
    r = []
    if cap_status == "tight":
        r.append("老师容量偏紧，接单量超出后须提前通知顾问")
    if cap_status == "full":
        r.append("名额极少，接单前必须学管确认，不可提前承诺")
    if demand == "falling":
        r.append("近期需求下降，推广前了解原因")
    if product_risk == "high":
        r.append("高风险产品，严格执行接单流程，不得跳过任何确认步骤")
    if missing:
        r.append(f"数据缺失：{' / '.join(missing)}")
    return r
