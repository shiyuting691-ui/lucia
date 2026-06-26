"""
ProductNeedMatcher — 学生需求 × 产品目录 × 红绿灯 匹配器

输入：
  - need_summary（来自 StudentNeedEngine）
  - traffic_lights（来自 ProductTrafficLight）
  - catalog_products（来自 ProductCatalogService）

输出：
  针对每种需求类型，给出：
  - 推荐产品（含原因 + 红绿灯状态）
  - 不推荐产品（含原因）
  - 渠道打法
  - 顾问动作
  - 学管动作
  - 时间窗口
  - 数据依据
  - 风险提醒
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# 红绿灯状态 → 推荐强度
_TL_PUSH_LEVEL = {
    "green":  "strong",   # 可以推
    "yellow": "cautious", # 谨慎推，需学管确认
    "red":    "blocked",  # 暂停推，给替代方案
    "grey":   "unknown",  # 资料不足，不能强推
}


class ProductNeedMatcher:
    """
    将 StudentNeedEngine 输出的 need_summary 与产品目录 + 红绿灯结合，
    输出每种需求的结构化推荐。
    """

    def run(self, need_summary: list, traffic_lights: dict) -> list[dict]:
        """
        返回 matched_needs 列表，每个元素对应一种 need_type 的完整推荐包。
        """
        from services.product_catalog_service import ProductCatalogService
        catalog_products = {p["canonical_product_id"]: p
                            for p in ProductCatalogService.load_active_products()}

        matched_needs = []
        for need in need_summary:
            match = self._match_one(need, traffic_lights, catalog_products)
            matched_needs.append(match)

        return matched_needs

    def _match_one(self, need: dict, traffic_lights: dict,
                   catalog_products: dict) -> dict:
        nt             = need["need_type"]
        label          = need["label"]
        heat           = need["heat_score"]
        evidence       = need["evidence"]
        rec_pids       = need["recommended_products"]
        not_rec        = need["not_recommended"]
        next_questions = need["next_questions"]
        channels       = need["channels"]
        time_windows   = need["time_windows"]
        urgency        = need["urgency"]

        # ── 推荐产品（过滤红绿灯）─────────────────────────────────
        recommended = []
        for pid in rec_pids:
            tl  = traffic_lights.get(pid, {})
            tl_status = tl.get("status", "grey")
            push_level = _TL_PUSH_LEVEL.get(tl_status, "unknown")
            p   = catalog_products.get(pid, {})

            if push_level == "blocked":
                # 红灯产品给替代方案
                alt = self._find_alternative(pid, rec_pids, traffic_lights)
                recommended.append({
                    "product_id":    pid,
                    "product_name":  p.get("product_name", pid),
                    "push_level":    "blocked",
                    "tl_status":     tl_status,
                    "tl_reason":     tl.get("status_reason", ""),
                    "match_reason":  f"需求匹配但红灯暂停，替代方案：{alt}",
                    "consultant_note": tl.get("consultant_note", ""),
                    "xueguan_note":    tl.get("xueguan_note", ""),
                    "forbidden_claims": p.get("forbidden_claims", []),
                    "alternative":   alt,
                })
            else:
                need_strength = "high" if heat >= 30 else ("medium" if heat >= 10 else "low")
                match_score   = self._calc_match_score(pid, nt, tl_status, heat)
                recommended.append({
                    "product_id":    pid,
                    "product_name":  p.get("product_name", pid),
                    "push_level":    push_level,
                    "tl_status":     tl_status,
                    "tl_reason":     tl.get("status_reason", ""),
                    "match_score":   round(match_score, 2),
                    "need_strength": need_strength,
                    "match_reason":  self._build_match_reason(pid, nt, tl_status, need),
                    "consultant_note": (
                        p.get("consultant_note", "") or tl.get("consultant_note", "")
                    ),
                    "xueguan_note": (
                        p.get("xueguan_note", "") or tl.get("xueguan_note", "")
                    ),
                    "forbidden_claims": p.get("forbidden_claims", []),
                    "suitable_channels": p.get("suitable_channels", []),
                    "alternative":   None,
                })

        # 推荐产品按 match_score 排序，blocked 排最后
        recommended.sort(key=lambda x: (
            0 if x["push_level"] == "blocked" else 1,
            -(x.get("match_score") or 0)
        ), reverse=False)
        # 重排：非blocked排前，blocked排后
        recommended = (
            [r for r in recommended if r["push_level"] != "blocked"] +
            [r for r in recommended if r["push_level"] == "blocked"]
        )

        # ── 不推荐产品 ─────────────────────────────────────────────
        not_recommended = []
        for pid, reason in not_rec.items():
            tl  = traffic_lights.get(pid, {})
            p   = catalog_products.get(pid, {})
            not_recommended.append({
                "product_id":   pid,
                "product_name": p.get("product_name", pid),
                "reason":       reason,
                "tl_status":    tl.get("status", "unknown"),
            })

        # ── 综合判断：需求匹配度 × 红绿灯 ──────────────────────────
        action_level = self._determine_action_level(heat, recommended)

        # ── 顾问动作 ───────────────────────────────────────────────
        consultant_actions = self._build_consultant_actions(
            nt, need, recommended, action_level
        )

        # ── 学管动作 ───────────────────────────────────────────────
        xueguan_actions = self._build_xueguan_actions(
            nt, need, recommended, traffic_lights
        )

        # ── 渠道打法（按需求类型 + 热度过滤）──────────────────────
        channel_plan = self._build_channel_plan(nt, channels, heat, recommended)

        return {
            "need_type":          nt,
            "label":              label,
            "heat_score":         heat,
            "urgency":            urgency,
            "order_count":        need.get("order_count", 0),
            "lead_count":         need.get("lead_count", 0),
            "evidence":           evidence,
            "top_countries":      need.get("top_countries", []),
            "top_schools":        need.get("top_schools", []),
            "recommended_products": recommended,
            "not_recommended_products": not_recommended,
            "next_questions":     next_questions,
            "channel_plan":       channel_plan,
            "consultant_actions": consultant_actions,
            "xueguan_actions":    xueguan_actions,
            "time_windows":       time_windows,
            "action_level":       action_level,
            "missing_info":       self._missing_info(need, recommended, traffic_lights),
        }

    # ── 内部工具方法 ───────────────────────────────────────────────

    def _calc_match_score(self, pid: str, need_type: str,
                          tl_status: str, heat: int) -> float:
        """0~1 综合匹配分 = 需求热度权重 × 红绿灯系数。"""
        heat_score = min(heat / 100.0, 1.0)
        tl_coeff   = {"green": 1.0, "yellow": 0.6, "grey": 0.3, "red": 0.0}.get(tl_status, 0.3)
        return heat_score * tl_coeff

    def _build_match_reason(self, pid: str, need_type: str,
                            tl_status: str, need: dict) -> str:
        heat = need.get("heat_score", 0)
        orders = need.get("order_count", 0)
        label = need.get("label", "")

        heat_desc = "热度高" if heat >= 50 else ("热度中等" if heat >= 20 else "热度低但有信号")
        tl_desc = {
            "green":  "产品绿灯，当前可全力推",
            "yellow": "产品黄灯，需学管确认再推",
            "grey":   "产品数据不足，慎重推",
            "red":    "产品红灯，暂停推广",
        }.get(tl_status, "")

        return f"学生{label}需求明确（{heat_desc}，近30天{orders}单），{tl_desc}"

    def _find_alternative(self, blocked_pid: str, rec_pids: list,
                          traffic_lights: dict) -> str:
        """找出同一需求下不是红灯的替代产品。"""
        alts = [pid for pid in rec_pids
                if pid != blocked_pid
                and traffic_lights.get(pid, {}).get("status") in ("green", "yellow")]
        if alts:
            from services.product_catalog_service import ProductCatalogService
            p = ProductCatalogService.get_product(alts[0])
            return p["product_name"] if p else alts[0]
        return "暂无替代方案，等待红灯解除"

    def _determine_action_level(self, heat: int, recommended: list) -> str:
        """
        综合判断本需求的执行强度：
          push_now / push_cautious / hold / no_push
        """
        strong = [r for r in recommended if r["push_level"] == "strong"]
        cautious = [r for r in recommended if r["push_level"] == "cautious"]

        if heat >= 20 and strong:
            return "push_now"
        if heat >= 10 and (strong or cautious):
            return "push_cautious"
        if heat > 0 and cautious:
            return "push_cautious"
        if heat == 0 and strong:
            return "hold"  # 有产品但无历史需求，等待
        return "hold"

    def _build_consultant_actions(self, nt: str, need: dict,
                                   recommended: list, action_level: str) -> list[str]:
        actions = []
        label = need["label"]
        questions = need["next_questions"]
        top_schools = need.get("top_schools", [])
        top_countries = need.get("top_countries", [])

        # 动作强度
        if action_level == "push_now":
            actions.append(f"本周主动联系有{label}需求的客户，优先处理")
        elif action_level == "push_cautious":
            actions.append(f"谨慎跟进{label}需求，确认学管资源后再报价")
        else:
            actions.append(f"{label}方向本周持续观察，暂不主动硬推")

        # 补问清单
        if questions:
            actions.append(f"补问要点：{'；'.join(questions[:2])}")

        # 推荐产品动作
        for r in recommended[:2]:
            if r["push_level"] == "strong":
                actions.append(
                    f"推荐产品：{r['product_name']}（{r['tl_reason'][:30]}）"
                )
            elif r["push_level"] == "cautious":
                actions.append(
                    f"谨慎推荐：{r['product_name']}，报价前先问学管是否有资源"
                )
            elif r["push_level"] == "blocked":
                alt = r.get("alternative", "")
                actions.append(
                    f"{r['product_name']}暂停推广，替代方案：{alt}"
                )

        # 地域/学校
        if top_countries:
            actions.append(f"重点跟进{'/'.join(top_countries)}在读学生池子")
        if top_schools:
            actions.append(f"优先触达：{'、'.join(top_schools[:2])}学生")

        return actions

    def _build_xueguan_actions(self, nt: str, need: dict,
                                recommended: list, traffic_lights: dict) -> list[str]:
        actions = []
        label = need["label"]

        # 容量确认
        for r in recommended:
            if r["push_level"] in ("strong", "cautious"):
                pid = r["product_id"]
                tl = traffic_lights.get(pid, {})
                cap = tl.get("teacher_capacity", "未知")
                actions.append(f"[{r['product_name']}] 当前容量：{cap}；{r['xueguan_note'][:50]}")

        # 高风险产品特别提示
        caution_pids = [r["product_id"] for r in recommended if r["push_level"] == "cautious"]
        if caution_pids:
            actions.append(
                f"黄灯产品（{'、'.join(caution_pids)}）：顾问必须先问学管再报价，不得提前承诺"
            )

        # 禁用表达汇总
        all_forbidden = []
        for r in recommended:
            all_forbidden.extend(r.get("forbidden_claims", []))
        if all_forbidden:
            actions.append(f"顾问禁用：{' / '.join(set(all_forbidden[:3]))}")

        if not actions:
            actions.append(f"{label}方向本周无紧急容量压力，正常接单")

        return actions

    def _build_channel_plan(self, nt: str, channels: dict,
                             heat: int, recommended: list) -> list[dict]:
        """生成该需求类型的渠道打法列表。"""
        plan = []
        # 热度低不建议大规模推广
        if heat < 5 and nt not in ("ai_compliance", "language_school"):
            channels_to_use = {k: v for k, v in channels.items()
                               if k in ("old_customer", "moments")}
        else:
            channels_to_use = channels

        # 优先渠道 = 产品目录推荐渠道 × 需求类型渠道的交集
        all_product_channels = set()
        for r in recommended:
            if r["push_level"] in ("strong", "cautious"):
                all_product_channels.update(r.get("suitable_channels", []))

        for channel, strategy in channels_to_use.items():
            priority = "P0" if channel in all_product_channels else "P1"
            plan.append({
                "channel":  channel,
                "strategy": strategy,
                "priority": priority,
            })
        return plan

    def _missing_info(self, need: dict, recommended: list,
                      traffic_lights: dict) -> list[str]:
        missing = []
        if need.get("order_count", 0) + need.get("lead_count", 0) == 0:
            missing.append("CRM 暂无该需求历史数据，建议补录")
        grey_products = [r["product_name"] for r in recommended
                        if r["push_level"] == "unknown"]
        if grey_products:
            missing.append(f"以下产品数据不足：{'、'.join(grey_products)}")
        return missing
