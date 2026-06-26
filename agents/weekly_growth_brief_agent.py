"""
WeeklyGrowthBriefAgent — 本周增长作战单（需求驱动 v3）

新主链路（需求优先）：
  StudentNeedEngine          识别学生需求热度
  → ProductCatalogService    调用产品目录库
  → ProductNeedMatcher       需求 × 产品 × 红绿灯 匹配
  → ProductTrafficLight      判断产品能否推
  → TimeWindowForecastAgent  时间窗口节奏
  → 需求驱动渠道策略          不同渠道对应不同需求
  → 需求驱动顾问建议          客户级动作
  → 需求驱动学管建议          容量 + 风险
  → RiskGuard                内容安全
  → 输出 / dry-run

废弃逻辑：
  × 红绿灯优先（Final绿灯 → 所有人推Final）
  × 内容生成优先（先写小红书 → 再考虑销售）
  × 学校节点直接决定产品
"""
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WeeklyGrowthBriefAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}

    def run(self, dry_run: bool = False, use_llm: bool = None) -> dict:
        if use_llm is None:
            use_llm = not dry_run

        today      = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        week_end   = (today - timedelta(days=today.weekday()) + timedelta(days=6)).strftime("%Y-%m-%d")
        mode_tag   = "[DRY-RUN]" if dry_run else "[LIVE]"
        logger.info(f"[WeeklyGrowthBrief] {mode_tag} {week_start}~{week_end}")

        # ═══════════════════════════════════════════════════════════
        # Step 1  StudentNeedEngine — 识别学生需求热度
        # ═══════════════════════════════════════════════════════════
        try:
            from services.student_need_engine import StudentNeedEngine
            need_engine_result = StudentNeedEngine().run(days=30)
            need_summary       = need_engine_result["need_summary"]
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] StudentNeedEngine failed: {e}")
            need_engine_result = {"need_summary": [], "total_orders": 0, "total_leads": 0}
            need_summary       = []

        # ═══════════════════════════════════════════════════════════
        # Step 2  ProductTrafficLight — 产品能否推（限制，非起点）
        # ═══════════════════════════════════════════════════════════
        try:
            from agents.product_traffic_light import ProductTrafficLight
            traffic_lights = ProductTrafficLight().run()
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] TrafficLight failed: {e}")
            traffic_lights = {}

        # ═══════════════════════════════════════════════════════════
        # Step 3  ProductNeedMatcher — 需求 × 产品目录 × 红绿灯
        # ═══════════════════════════════════════════════════════════
        try:
            from agents.product_need_matcher import ProductNeedMatcher
            matched_needs = ProductNeedMatcher().run(need_summary, traffic_lights)
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] ProductNeedMatcher failed: {e}")
            matched_needs = []

        # ═══════════════════════════════════════════════════════════
        # Step 4  TimeWindowForecastAgent — 时间窗口节奏
        # ═══════════════════════════════════════════════════════════
        try:
            from agents.time_window_forecast_agent import TimeWindowForecastAgent
            forecasts = TimeWindowForecastAgent().run()
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] Forecast failed: {e}")
            forecasts = []

        # ═══════════════════════════════════════════════════════════
        # Step 5  DemandAnalyzer — CRM 聚合（国家/学校/热门组合）
        # ═══════════════════════════════════════════════════════════
        try:
            from services.demand_analyzer import build_push_data_basis
            demand_basis = build_push_data_basis(days=30)
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] DemandAnalyzer failed: {e}")
            demand_basis = {}

        # ═══════════════════════════════════════════════════════════
        # Step 6  渠道内容策略（需求驱动，非内容驱动）
        # ═══════════════════════════════════════════════════════════
        if not use_llm:
            channel_recs     = self._need_driven_channel_strategy(matched_needs, demand_basis)
            channel_provider = "RuleFallback"
        else:
            try:
                from agents.channel_content_strategy_agent import ChannelContentStrategyAgent
                channel_recs = ChannelContentStrategyAgent().run(
                    decision={}, traffic_lights=traffic_lights,
                    matched_needs=matched_needs,
                )
                channel_provider = "LLM"
            except Exception as e:
                logger.warning(f"[WeeklyGrowthBrief] ChannelStrategy failed: {e}")
                channel_recs     = self._need_driven_channel_strategy(matched_needs, demand_basis)
                channel_provider = "RuleFallback"

        # ═══════════════════════════════════════════════════════════
        # Step 7  顾问建议（客户级动作，需求驱动）
        # ═══════════════════════════════════════════════════════════
        if not use_llm:
            consultant_suggestions = self._need_driven_consultant_suggestions(matched_needs)
            consultant_provider    = "RuleFallback"
        else:
            try:
                from agents.weekly_sales_suggestion_agent import WeeklySalesSuggestionAgent
                sales_result = WeeklySalesSuggestionAgent().generate(
                    week_start=week_start,
                    traffic_lights=traffic_lights,
                    matched_needs=matched_needs,
                )
                consultant_suggestions = sales_result.get("consultant_suggestions", [])
                consultant_provider    = sales_result.get("consultant_provider", "unknown")
            except Exception as e:
                logger.warning(f"[WeeklyGrowthBrief] SalesSuggestion failed: {e}")
                consultant_suggestions = self._need_driven_consultant_suggestions(matched_needs)
                consultant_provider    = "RuleFallback"

        # ═══════════════════════════════════════════════════════════
        # Step 8  学管建议（容量 + 风险，需求驱动）
        # ═══════════════════════════════════════════════════════════
        xueguan_suggestions = self._need_driven_xueguan_suggestions(
            matched_needs, traffic_lights, demand_basis
        )
        xueguan_provider = "RuleFallback"

        # ═══════════════════════════════════════════════════════════
        # Step 9  RiskGuard
        # ═══════════════════════════════════════════════════════════
        try:
            from agents.risk_guard import RiskGuard
            risk_result = RiskGuard().assess(traffic_lights=traffic_lights)
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] RiskGuard failed: {e}")
            risk_result = {"alerts": [], "overall_risk": "unknown", "alert_count": 0}

        # ═══════════════════════════════════════════════════════════
        # Step 10  缺失数据报告
        # ═══════════════════════════════════════════════════════════
        missing_data_report = self._build_missing_data_report(
            demand_basis, traffic_lights, forecasts, need_engine_result
        )

        # ═══════════════════════════════════════════════════════════
        # 聚合
        # ═══════════════════════════════════════════════════════════
        time_windows_summary = self._summarize_forecasts(forecasts)
        channel_strategy     = self._summarize_channels(channel_recs)
        data_evidence        = self._build_data_evidence(traffic_lights, forecasts, risk_result)
        ai_source            = "RuleFallback" if dry_run else self._determine_ai_source(
            consultant_provider, xueguan_provider, channel_recs
        )
        confidence = self._calc_confidence(traffic_lights, forecasts, risk_result, matched_needs)
        wechat_preview = self._build_wechat_preview(
            week_start, week_end,
            traffic_lights=traffic_lights,
            risk_result=risk_result,
            matched_needs=matched_needs,
            time_windows=time_windows_summary,
            channel_strategy=channel_strategy,
            demand_basis=demand_basis,
            ai_source=ai_source,
            confidence=confidence,
            dry_run=dry_run,
        )

        brief = {
            "dry_run":                dry_run,
            "week_start":             week_start,
            "week_end":               week_end,
            "need_summary":           need_summary,        # 新增
            "matched_needs":          matched_needs,       # 新增
            "time_windows":           time_windows_summary,
            "channel_strategy":       channel_strategy,
            "consultant_suggestions": consultant_suggestions,
            "xueguan_suggestions":    xueguan_suggestions,
            "product_traffic_lights": traffic_lights,
            "risk_alerts":            risk_result.get("alerts", []),
            "data_evidence":          data_evidence,
            "missing_data_report":    missing_data_report,
            "ai_source":              ai_source,
            "confidence":             confidence,
            "wechat_push_preview":    wechat_preview,
            "overall_risk":           risk_result.get("overall_risk", "unknown"),
            "generated_at":           datetime.utcnow().isoformat(),
        }

        if dry_run:
            brief["brief_id"] = None
            return brief

        try:
            from database import save_weekly_growth_brief
            brief_id = save_weekly_growth_brief({
                "week_start":   week_start,
                "week_end":     week_end,
                "brief_json":   json.dumps(brief, ensure_ascii=False),
                "ai_source":    ai_source,
                "confidence":   confidence,
                "overall_risk": risk_result.get("overall_risk", "unknown"),
                "alert_count":  risk_result.get("alert_count", 0),
                "generated_at": datetime.utcnow().isoformat(),
            })
            brief["brief_id"] = brief_id
        except Exception as e:
            logger.warning(f"[WeeklyGrowthBrief] save failed: {e}")
            brief["brief_id"] = None

        return brief

    # ══════════════════════════════════════════════════════════════
    #  Step 6  需求驱动渠道策略（零LLM）
    # ══════════════════════════════════════════════════════════════

    def _need_driven_channel_strategy(self, matched_needs: list,
                                       demand_basis: dict) -> list:
        """
        渠道内容策略由学生需求决定，不由内容产出决定。
        必须覆盖5个渠道：小红书、垂直号、群推、朋友圈、社群。
        每个渠道的内容方向来自对应需求类型的渠道打法。
        """
        snap       = demand_basis.get("snapshot", {})
        by_country = snap.get("by_country", {})
        hot_combos = demand_basis.get("hot_combos", [])
        upcoming   = demand_basis.get("upcoming_events", [])

        COUNTRY_LABEL = {"UK": "英国", "AU": "澳洲", "US": "美国", "HK": "香港", "CA": "加拿大"}

        # 取热度最高的需求（有热度的优先）
        active_needs = [m for m in matched_needs if m.get("heat_score", 0) > 0]
        if not active_needs:
            active_needs = matched_needs[:3]

        top_need   = active_needs[0] if active_needs else {}
        sec_need   = active_needs[1] if len(active_needs) > 1 else {}
        near_event = next((e for e in upcoming if e.get("days_until", 99) <= 45), {})
        top_combo  = hot_combos[0] if hot_combos else {}
        countries  = list(by_country.keys())
        top_country = countries[0] if countries else ""
        top_school  = ""
        top_product = ""
        if top_country:
            cd = by_country[top_country]
            top_school  = (cd.get("top_schools") or [{}])[0].get("school", "")
            top_product = (cd.get("top_products") or [{}])[0].get("product", "")

        recs = []

        # ── 小红书 P0：最热需求的搜索痛点内容 ─────────────────────
        if top_need:
            tn_label     = top_need.get("label", "")
            tn_channels  = top_need.get("channel_plan", [])
            xhs_strategy = next((c["strategy"] for c in tn_channels
                                 if c["channel"] == "xiaohongshu"), tn_label + "避坑指南")
            recs_products = [r["product_name"] for r in top_need.get("recommended_products", [])
                             if r.get("push_level") in ("strong", "cautious")][:1]
            rec_p = recs_products[0] if recs_products else top_product

            hook = (f"{top_school or top_country or '留学生'}真实经验｜"
                    f"{rec_p or tn_label}避坑指南") if (top_school or top_country) else \
                   f"{tn_label}｜{xhs_strategy}"
            recs.append({
                "channel": "xiaohongshu", "priority": "P0",
                "hook_idea": hook,
                "cta": "私信「咨询」领取本周排期",
                "reason": f"需求热度最高：{tn_label}（{top_need.get('order_count',0)}单/{top_need.get('lead_count',0)}条）",
                "need_type": top_need.get("need_type", ""),
            })
        else:
            recs.append({
                "channel": "xiaohongshu", "priority": "P0",
                "hook_idea": "留学辅导经验分享（补录CRM数据后自动更新）",
                "cta": "私信「咨询」",
                "reason": "暂无热度数据",
                "need_type": "",
            })

        # ── 垂直号 P1：第二需求或长期信任内容 ────────────────────
        if sec_need:
            sn_label    = sec_need.get("label", "")
            va_strategy = next((c["strategy"] for c in sec_need.get("channel_plan", [])
                                if c["channel"] == "vertical_account"),
                               sn_label + "经验分享")
            flag2 = COUNTRY_LABEL.get(
                sec_need.get("top_countries", [None])[0] or "", "")
            hook2 = f"{flag2}{flag2 and '·'}{sn_label}｜{va_strategy[:30]}"
            recs.append({
                "channel": "vertical_account", "priority": "P1",
                "hook_idea": hook2,
                "cta": "点击阅读原文了解方案",
                "reason": f"第二需求热度：{sn_label}（{sec_need.get('order_count',0)}单）",
                "need_type": sec_need.get("need_type", ""),
            })
        else:
            recs.append({
                "channel": "vertical_account", "priority": "P1",
                "hook_idea": "海外留学辅导干货（补录数据后自动更新）",
                "cta": "点击阅读",
                "reason": "暂无第二需求数据",
                "need_type": "",
            })

        # ── 群推/微信群 P1：学校节点 + 紧急需求触达 ──────────────
        if near_event:
            ev    = near_event
            days  = ev.get("days_until", 0)
            flag3 = COUNTRY_LABEL.get(ev.get("country", ""), "")
            hook3 = (f"【{ev['school']}同学注意】"
                     f"{ev['event_name']}还有{days}天，辅导名额仅剩少量")
            r3    = f"{ev['school']} {ev['event_name']} {ev['start_date']}（{days}天后）"
        elif top_combo:
            flag3 = COUNTRY_LABEL.get(top_combo.get("country", ""), "")
            hook3 = (f"【{flag3 and flag3+'·'}{top_combo.get('school','')}在读同学】"
                     f"近30天{top_combo.get('count',0)}位同学在用「{top_combo.get('product','')}」辅导")
            r3    = f"热门组合近30天{top_combo.get('count',0)}单"
        else:
            hook3 = "本周辅导名额提醒（补录学校节点后自动更新）"
            r3    = "暂无学校节点数据"
        recs.append({
            "channel": "wechat_group", "priority": "P1",
            "hook_idea": hook3, "cta": "回复「预约」锁定名额",
            "reason": r3, "need_type": "",
        })

        # ── 朋友圈 P1：真实案例背书，来自热门组合 ─────────────────
        if top_combo:
            tc    = top_combo
            flag4 = COUNTRY_LABEL.get(tc.get("country", ""), "")
            hook4 = (f"又一位{flag4 and flag4+'·'}{tc.get('school','')}同学完成「{tc.get('product','')}」｜"
                     f"近30天{tc.get('count',0)}单在读")
            r4    = f"CRM真实成单：{tc.get('school','')}×{tc.get('product','')}，{tc.get('count',0)}单"
        elif top_need:
            tn_label = top_need.get("label", "")
            hook4 = (f"学员反馈｜{tn_label}服务过程·本周成单案例"
                     f"（{top_need.get('order_count',0)}单数据支撑）")
            r4    = f"近30天{tn_label}成单{top_need.get('order_count',0)}单"
        else:
            hook4 = "学员成绩反馈·本周成单案例（补录数据后自动更新）"
            r4    = "暂无热门组合数据"
        recs.append({
            "channel": "moments", "priority": "P1",
            "hook_idea": hook4, "cta": "评论「了解」私发方案",
            "reason": r4, "need_type": "",
        })

        # ── 社群 P2：互动 + 留存，基于最热需求 ────────────────────
        if near_event:
            ev    = near_event
            hook5 = (f"【{ev['school']}考试季互动】{ev['event_name']}前你准备好了吗？"
                     f"评论说说你的备考计划")
            r5    = f"{ev['school']} {ev['event_name']} {ev['start_date']}"
        elif top_need:
            tn_label = top_need.get("label", "")
            sc_strategy = next((c["strategy"] for c in top_need.get("channel_plan", [])
                                if c["channel"] == "community"), tn_label + "交流")
            hook5 = f"【{tn_label}专题互动】{sc_strategy[:30]}，评论分享你的经验"
            r5    = f"近30天{tn_label}热度最高"
        else:
            hook5 = "留学辅导经验交流（补录数据后自动更新）"
            r5    = "暂无数据"
        recs.append({
            "channel": "community", "priority": "P2",
            "hook_idea": hook5, "cta": "回复参与，置顶评论送辅导资料",
            "reason": r5, "need_type": "",
        })

        return recs

    # ══════════════════════════════════════════════════════════════
    #  Step 7  需求驱动顾问建议（客户级动作）
    # ══════════════════════════════════════════════════════════════

    def _need_driven_consultant_suggestions(self, matched_needs: list) -> list:
        """
        顾问建议必须是客户级动作，基于学生需求类型生成。
        输出格式兼容 main.py 的 {priority, action, success_metric, data_evidence, ...}。
        """
        suggestions = []
        priority    = 1

        for match in matched_needs:
            if match.get("action_level") not in ("push_now", "push_cautious"):
                continue
            if priority > 5:
                break

            nt       = match["need_type"]
            label    = match["label"]
            actions  = match.get("consultant_actions", [])
            evidence = ", ".join(match.get("evidence", []))
            qs       = match.get("next_questions", [])

            # 主动作
            main_action = actions[0] if actions else f"跟进{label}需求客户"

            # 不推荐产品提示
            not_rec     = match.get("not_recommended_products", [])
            not_rec_str = ("；禁推：" + "、".join(r["product_name"] for r in not_rec[:2])
                           ) if not_rec else ""

            # 推荐产品（只取绿/黄灯）
            rec_products = [r for r in match.get("recommended_products", [])
                            if r.get("push_level") in ("strong", "cautious")]
            rec_str      = ("；推荐：" + "、".join(r["product_name"] for r in rec_products[:2])
                            ) if rec_products else ""

            # 补问清单
            q_str = "；补问：" + qs[0] if qs else ""

            suggestions.append({
                "priority":        priority,
                "need_type":       nt,
                "action":          main_action + rec_str + not_rec_str,
                "target":          f"{label}需求学生",
                "script_hint":     q_str.lstrip("；") if q_str else "参考下方补问清单",
                "next_questions":  qs,
                "success_metric":  (
                    f"本周{label}方向新签≥{max(1, match.get('order_count',0)//20 or 1)}单"
                ),
                "risk_note":       "接单前确认学管有容量，不预先承诺交付时间",
                "data_evidence":   evidence or f"近30天{label}成单{match.get('order_count',0)}单",
                "not_recommended": [r["product_name"] for r in not_rec],
                "recommended":     [r["product_name"] for r in rec_products],
                "missing_info":    match.get("missing_info", []),
            })
            priority += 1

        if not suggestions:
            suggestions.append({
                "priority": 1,
                "action":   "补充CRM订单数据后系统自动生成精准建议",
                "target":   "全体顾问",
                "script_hint": "暂无需求数据依据",
                "success_metric": "完成数据录入",
                "risk_note": "",
                "data_evidence": "CRM暂无近30天需求数据",
                "not_recommended": [],
                "recommended":  [],
                "missing_info": ["CRM订单数据为空"],
            })

        return suggestions

    # ══════════════════════════════════════════════════════════════
    #  Step 8  需求驱动学管建议
    # ══════════════════════════════════════════════════════════════

    def _need_driven_xueguan_suggestions(self, matched_needs: list,
                                          traffic_lights: dict,
                                          demand_basis: dict) -> dict:
        """
        学管建议基于：本周需求 + 产品容量 + 风险等级。
        不直接输出"资源充足"，如果没有容量数据必须写"需学管判断"。
        """
        cap_check   = []
        forbidden   = []
        at_risk     = []

        for match in matched_needs:
            if match.get("action_level") not in ("push_now", "push_cautious"):
                continue
            label = match["label"]
            xueguan_actions = match.get("xueguan_actions", [])

            # 容量确认
            for r in match.get("recommended_products", []):
                if r.get("push_level") in ("strong", "cautious"):
                    pid = r["product_id"]
                    tl  = traffic_lights.get(pid, {})
                    cap = tl.get("teacher_capacity", "")
                    if not cap or "未录入" in cap:
                        cap_check.append(
                            f"[{r['product_name']}] 老师容量未确认 → 需学管判断后再放行报价"
                        )
                    else:
                        cap_check.append(f"[{r['product_name']}] 当前容量：{cap}")
                    forbidden.extend(r.get("forbidden_claims", []))
                elif r.get("push_level") == "blocked":
                    at_risk.append(
                        f"[{r['product_name']}] 红灯，{label}需求请推替代方案"
                    )

        if not cap_check:
            cap_check = ["所有产品：确认本周老师排期和可承接量"]

        # 开学/考试节点提醒（续费准备）
        upcoming    = demand_basis.get("upcoming_events", [])
        soon_starts = [e for e in upcoming
                       if e.get("event_type") in ("teaching_start", "exam_period")
                       and e.get("days_until", 99) <= 45]

        coordinator_actions = [
            "周一前完成所有产品老师排期核实，有容量才允许顾问接单",
            "黄灯/灰灯产品：有新询单时第一时间确认老师档期再告知顾问",
        ]
        if soon_starts:
            ev = soon_starts[0]
            coordinator_actions.append(
                f"{ev['school']} {ev['start_date']} 节点前，提前准备对应产品资源"
            )
        coordinator_actions.append("超额风险（预计超量≥20%）须提前72小时通知顾问并上报管理层")

        # 交付风险汇总
        grey_products = [tl.get("product_name", pid)
                         for pid, tl in traffic_lights.items()
                         if tl.get("status") == "grey"]
        delivery_risks = (
            f"以下产品因缺容量数据无法判断：{'、'.join(grey_products)}" if grey_products
            else "当前无高风险交付预警"
        )

        # 禁用表达汇总
        unique_forbidden = list(dict.fromkeys(forbidden))  # 去重保序
        if at_risk:
            coordinator_actions.extend(at_risk)

        return {
            "week_focus":          "基于本周学生需求核实容量，确保顾问接单前有资源保障",
            "capacity_check":      cap_check,
            "delivery_risks":      delivery_risks,
            "coordinator_actions": coordinator_actions,
            "forbidden_reminder":  unique_forbidden[:5],
            "escalation_triggers": "单周预计超量≥20%时上报管理层",
            "data_evidence":       "产品红绿灯：" + (
                ', '.join(pid + "=" + tl.get("status", "?")
                          for pid, tl in traffic_lights.items())
                or '暂无数据'
            ),
        }

    # ══════════════════════════════════════════════════════════════
    #  缺失数据报告
    # ══════════════════════════════════════════════════════════════

    def _build_missing_data_report(self, demand_basis: dict, traffic_lights: dict,
                                    forecasts: list, need_engine_result: dict) -> dict:
        try:
            from database.crud import get_session
            from database.models import Order, Lead, TeacherCapacity, SchoolCalendar
            from sqlalchemy import func
            with get_session() as s:
                order_cnt    = s.query(func.count(Order.id)).scalar() or 0
                lead_cnt     = s.query(func.count(Lead.id)).scalar() or 0
                capacity_cnt = s.query(func.count(TeacherCapacity.id)).scalar() or 0
                calendar_cnt = s.query(func.count(SchoolCalendar.id)).scalar() or 0
        except Exception:
            order_cnt = lead_cnt = capacity_cnt = calendar_cnt = -1

        snap      = demand_basis.get("snapshot", {})
        order_30d = snap.get("total_orders", 0)
        missing   = []
        warnings  = []

        if order_cnt == 0:
            missing.append("❌ orders表为空 — CRM未同步，需求分析不可用")
        elif order_30d == 0:
            warnings.append("⚠️ 近30天无订单数据 — 需求分析依据不足")

        if lead_cnt == 0:
            missing.append("❌ leads表为空 — 线索数据缺失，顾问建议无数据支撑")

        if capacity_cnt == 0:
            missing.append("❌ teacher_capacity表为空 — 产品容量无法判断，学管建议不可信")

        if calendar_cnt == 0:
            warnings.append("⚠️ school_calendar表为空 — 学校节点触达不可用")

        grey_count = sum(1 for tl in traffic_lights.values() if tl.get("status") == "grey")
        if grey_count >= 3:
            missing.append(f"❌ {grey_count}个产品因容量数据缺失变灰 — 红绿灯不可信")

        if not forecasts:
            warnings.append("⚠️ 时间窗口预测为空")

        # 未映射的 CRM 产品名
        unmapped = need_engine_result.get("unmapped_orders", [])
        if unmapped:
            unmapped_cnt = sum(c for _, c in unmapped)
            warnings.append(
                f"⚠️ CRM 中 {len(unmapped)} 种产品名未映射（共{unmapped_cnt}条），"
                f"建议补充别名：{', '.join(n for n, _ in unmapped[:3])}..."
            )

        return {
            "order_count_total":  order_cnt,
            "order_count_30d":    order_30d,
            "lead_count":         lead_cnt,
            "teacher_capacity":   capacity_cnt,
            "school_calendar":    calendar_cnt,
            "missing":            missing,
            "warnings":           warnings,
            "is_data_sufficient": len(missing) == 0,
        }

    # ══════════════════════════════════════════════════════════════
    #  通用工具方法（保持 main.py 接口兼容）
    # ══════════════════════════════════════════════════════════════

    def _summarize_forecasts(self, forecasts: list) -> dict:
        from collections import defaultdict
        by_window = defaultdict(list)
        for f in forecasts:
            by_window[f.get("window", "")].append(f)

        summary = {}
        for window in ["0-7天", "8-14天", "15-21天", "22-30天", "31-60天"]:
            rows = by_window.get(window, [])
            if not rows:
                summary[window] = {"urgency": "未知", "top_products": [], "total_leads": 0}
                continue
            top = sorted(rows, key=lambda x: x.get("demand_score", 0), reverse=True)[:3]
            summary[window] = {
                "urgency":     top[0].get("urgency", "低") if top else "低",
                "top_products": [
                    {"product": r.get("product_name", ""), "country": r.get("country", ""),
                     "leads": r.get("predicted_leads", 0)}
                    for r in top
                ],
                "total_leads":  sum(r.get("predicted_leads", 0) for r in rows),
                "key_events":   top[0].get("key_events", []) if top else [],
            }
        return summary

    def _summarize_channels(self, recs: list) -> list:
        return [
            {
                "channel":        r.get("channel", ""),
                "hook_idea":      r.get("hook_idea", ""),
                "priority":       r.get("priority", "P2"),
                "cta":            r.get("cta", ""),
                "reason":         r.get("reason", ""),
                "need_type":      r.get("need_type", ""),
            }
            for r in recs
        ]

    def _build_data_evidence(self, traffic_lights: dict, forecasts: list,
                              risk_result: dict) -> str:
        tl_summary = " | ".join(
            f"{tl.get('product_name', pid)}{tl.get('status_display', '')}"
            for pid, tl in list(traffic_lights.items())[:4]
        ) or "暂无红绿灯数据"
        total_leads = sum(f.get("predicted_leads", 0) for f in forecasts
                          if f.get("window") == "0-7天")
        return (
            f"产品红绿灯：{tl_summary}；"
            f"本周（0-7天）预估线索：{total_leads}条；"
            f"风控：{risk_result.get('overall_risk','unknown')}（{risk_result.get('alert_count',0)}条告警）"
        )

    def _determine_ai_source(self, consultant_provider: str, xueguan_provider: str,
                              channel_recs: list) -> str:
        providers = {consultant_provider, xueguan_provider}
        channel_providers = {r.get("provider", "") for r in channel_recs}
        providers |= channel_providers
        if "deepseek" in providers or "DeepSeek" in providers:
            return "DeepSeek"
        if "claude" in providers or "anthropic" in providers:
            return "Claude"
        return "RuleFallback"

    def _calc_confidence(self, traffic_lights: dict, forecasts: list,
                          risk_result: dict, matched_needs: list = None) -> str:
        if not traffic_lights and not forecasts:
            return "low"
        if risk_result.get("overall_risk") == "critical":
            return "low"
        grey_ct = sum(1 for tl in traffic_lights.values() if tl.get("status") == "grey")
        if grey_ct >= 3:
            return "low"
        if grey_ct >= 1 or risk_result.get("overall_risk") == "high":
            return "medium"
        # 有真实需求数据加成
        if matched_needs and any(m.get("heat_score", 0) > 20 for m in matched_needs):
            return "high"
        return "medium"

    # ══════════════════════════════════════════════════════════════
    #  企微推送预览（需求驱动重构版）
    # ══════════════════════════════════════════════════════════════

    def _build_wechat_preview(self, week_start: str, week_end: str,
                               traffic_lights: dict, risk_result: dict,
                               matched_needs: list,
                               time_windows: dict,
                               channel_strategy: list = None,
                               demand_basis: dict = None,
                               ai_source: str = "RuleFallback",
                               confidence: str = "medium",
                               dry_run: bool = False) -> str:

        channel_strategy = channel_strategy or []
        demand_basis     = demand_basis or {}

        PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚡", "P2": "📌"}
        COUNTRY_FLAG   = {"UK": "🇬🇧", "AU": "🇦🇺", "US": "🇺🇸", "HK": "🇭🇰", "CA": "🇨🇦"}
        CONF_MAP       = {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低"}
        SEV_EMOJI      = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "⚪"}

        dry_tag = "**[DRY-RUN · 不发送企业微信 · 零LLM调用]**\n\n" if dry_run else ""
        lines   = [f"{dry_tag}## 📊【本周增长作战单】{week_start} ~ {week_end}", ""]

        snap        = demand_basis.get("snapshot", {})
        by_country  = snap.get("by_country", {})
        total_ord   = snap.get("total_orders", 0)
        upcoming    = demand_basis.get("upcoming_events", [])
        hot_combos  = demand_basis.get("hot_combos", [])

        # ═══════════════════════════════════════════════════════
        # 板块 0：本周学生需求热图（全员参考，系统第一步）
        # ═══════════════════════════════════════════════════════
        lines += ["### 🎯 本周学生需求热图（全员参考）", ""]
        active_needs = [m for m in matched_needs if m.get("heat_score", 0) > 0]
        if active_needs:
            for m in active_needs[:5]:
                heat  = m["heat_score"]
                bar   = "█" * (heat // 10) + "░" * (10 - heat // 10)
                action_icon = {"push_now": "🟢", "push_cautious": "🟡",
                               "hold": "⚫"}.get(m.get("action_level", "hold"), "⚫")
                rec_names = [r["product_name"] for r in m.get("recommended_products", [])
                             if r["push_level"] in ("strong", "cautious")][:2]
                not_rec_names = [r["product_name"] for r in m.get("not_recommended_products", [])[:1]]
                lines.append(
                    f"{action_icon} **{m['label']}**  {bar} {heat}/100"
                    f"  成单{m['order_count']}+线索{m['lead_count']}"
                )
                if rec_names:
                    lines.append(f"   推荐：{'、'.join(rec_names)}"
                                 + (f"  ×不推：{'、'.join(not_rec_names)}" if not_rec_names else ""))
        else:
            lines.append("暂无热度数据，系统已切换至历史规律模式")

        lines.append("")
        if total_ord > 0:
            lines.append(f"**CRM近30天成单 {total_ord} 单**")
            for ctry, cdata in list(by_country.items())[:3]:
                flag  = COUNTRY_FLAG.get(ctry, "🌏")
                top_p = [p["product"] for p in cdata["top_products"][:2]]
                top_s = [s["school"] for s in cdata["top_schools"][:1]]
                lines.append(
                    f"{flag} {ctry} {cdata['total_orders']}单"
                    + (f" | {'、'.join(top_p)}" if top_p else "")
                    + (f" | {top_s[0]}" if top_s else "")
                )
            lines.append("")

        # ═══════════════════════════════════════════════════════
        # 板块 1：推广部 — 需求驱动渠道策略
        # ═══════════════════════════════════════════════════════
        CH_DISPLAY = {
            "xiaohongshu": "小红书", "vertical_account": "垂直号",
            "moments": "朋友圈", "community": "社群",
            "wechat_group": "微信群", "referral": "转介绍",
        }
        lines += ["---", "### 🎨 推广部 — 本周渠道内容策略", ""]
        for r in channel_strategy[:5]:
            ch  = CH_DISPLAY.get(r.get("channel", ""), r.get("channel", ""))
            pri = r.get("priority", "P1")
            lines.append(f"{PRIORITY_EMOJI.get(pri, '·')} **{ch}**")
            if r.get("hook_idea"):
                lines.append(f"> 🪝 {r['hook_idea'][:60]}")
            if r.get("reason"):
                lines.append(f"> 📊 依据：{r['reason'][:50]}")
        lines.append("")

        # ═══════════════════════════════════════════════════════
        # 板块 2：学管部 — 接待重点 + 产品容量
        # ═══════════════════════════════════════════════════════
        lines += ["---", "### 📚 学管部 — 本周接待重点", ""]

        # 接待准备（推广主打的需求方向）
        top_3 = [m for m in active_needs if m.get("action_level") in ("push_now", "push_cautious")][:3]
        if top_3:
            lines.append("**本周主要接待需求（推广打什么你就备什么）**")
            for m in top_3:
                countries_str = "/".join(m.get("top_countries", [])[:2]) or "全区域"
                lines.append(
                    f"- {m['label']}（{countries_str}） → "
                    f"{'、'.join(r['product_name'] for r in m.get('recommended_products',[])[:2] if r['push_level'] in ('strong','cautious'))}"
                )
            lines.append("")

        # 产品红绿灯接单参考
        if traffic_lights:
            lines.append("**产品接单参考（红绿灯）**")
            for pid, tl in traffic_lights.items():
                lines.append(
                    f"{tl.get('status_display','⚫')} {tl.get('product_name',pid)}"
                    f"：{tl.get('status_reason','')[:45]}"
                )
            lines.append("")

        # 老客续费节点
        renewal_events = [e for e in upcoming
                          if e.get("event_type") in ("teaching_start", "exam_period")
                          and e.get("days_until", 99) <= 45][:3]
        if renewal_events:
            lines.append("**老客主动触达节点**")
            for e in renewal_events:
                flag  = COUNTRY_FLAG.get(e.get("country", ""), "")
                etype = "开学前" if e.get("event_type") == "teaching_start" else "考试前"
                lines.append(
                    f"- {flag}{e['school']} {etype} {e['start_date']}（{e['days_until']}天后）"
                    f"→ 主动联系续课/升单"
                )
            lines.append("")

        # ═══════════════════════════════════════════════════════
        # 板块 3：顾问部 — 客户级动作 + 内容选题
        # ═══════════════════════════════════════════════════════
        lines += ["---", "### 📱 顾问部 — 本周客户动作 & 内容选题", ""]

        # 顾问客户动作（需求驱动）
        lines.append("**本周跟进重点（按需求优先级）**")
        for m in top_3:
            action_icon = "🔥" if m.get("action_level") == "push_now" else "⚡"
            ca = m.get("consultant_actions", [])
            lines.append(f"{action_icon} **{m['label']}**")
            for act in ca[:2]:
                lines.append(f"   → {act[:55]}")
            qs = m.get("next_questions", [])
            if qs:
                lines.append(f"   补问：{qs[0]}")
        if not top_3:
            lines.append("暂无明确需求方向，维持常规跟进")
        lines.append("")

        # 小红书/垂直号内容选题
        lines.append("**小红书/垂直号本周选题**")
        for m in active_needs[:3]:
            ch_plan = m.get("channel_plan", [])
            xhs = next((c["strategy"] for c in ch_plan if c["channel"] == "xiaohongshu"), "")
            if xhs:
                countries_str = "/".join(m.get("top_countries", [])[:1]) or ""
                flag = COUNTRY_FLAG.get(countries_str, "") if countries_str else ""
                lines.append(f"- {flag} {m['label']}：{xhs[:40]}")
        lines.append("")

        # ═══════════════════════════════════════════════════════
        # 板块 4：风险预警 & 系统评估
        # ═══════════════════════════════════════════════════════
        alerts = sorted(risk_result.get("alerts", []),
                        key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                            a.get("severity", "low"), 3))
        lines += ["---", "### ⚠️ 风险预警", ""]
        if alerts:
            for a in alerts[:3]:
                sev = a.get("severity", "low")
                lines.append(
                    f"{SEV_EMOJI.get(sev,'⚪')} **{a.get('rule_name','')}**：{a.get('blocked_content','')[:40]}"
                )
                lines.append(f"→ {a.get('suggested_fix','')[:55]}")
        else:
            lines.append("⚪ 本周暂无高风险预警")
        lines.append("")

        overall_risk   = risk_result.get("overall_risk", "unknown")
        risk_emoji_map = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢", "unknown": "⚪"}
        lines += [
            "### 🧭 系统评估",
            f"- 数据可信度：{CONF_MAP.get(confidence, confidence)}",
            f"- 整体风险等级：{risk_emoji_map.get(overall_risk,'')} {overall_risk.upper()}",
            "",
            f"<font color='comment'>🤖 极致增长系统 · {ai_source} · {datetime.now().strftime('%Y-%m-%d %H:%M')}</font>",
        ]

        return "\n".join(lines)
