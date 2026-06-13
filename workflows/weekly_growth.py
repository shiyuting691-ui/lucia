"""
WeeklyGrowthWorkflow — 每周增长管理主工作流（V9，8步）

触发：CLI run-weekly-growth [--week 2026-06-09]
步骤：
  1. 学校机会评分（规则）
  2. 产品供给分析 + 产品评分
  3. 线索机会评分（规则）
  4. 学校策略卡（LLM + GBA）
  5. 广告预测（规则 + Claude 写钩子）
  6. 周度销售建议
  7. 周度市场内容建议
  8. 企业微信推送（周策略格式）
"""
import logging
from datetime import datetime, timedelta
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class WeeklyGrowthWorkflow(BaseWorkflow):
    name = "weekly_growth"

    def __init__(self, config: dict, week_start: str = None):
        super().__init__(config)
        if week_start:
            self.week_start = week_start
        else:
            today = datetime.now()
            self.week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

    def _run_steps(self) -> dict:
        from services.agent_runner import AgentRunner
        from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
        from agents.product_supply_risk_agent import ProductSupplyRiskAgent
        from agents.lead_opportunity_scoring_agent import LeadOpportunityScoringAgent
        from agents.school_strategy_card_agent import SchoolStrategyCardAgent
        from agents.campaign_prediction_agent import CampaignPredictionAgent
        from agents.weekly_sales_suggestion_agent import WeeklySalesSuggestionAgent
        from agents.weekly_marketing_suggestion_agent import WeeklyMarketingSuggestionAgent

        runner = AgentRunner(workflow_name=self.name)
        scores = []
        supply_result = {}
        ok_cards = []

        # Step 1: 学校机会评分
        r = runner.run("SchoolOpportunityScoringAgent",
                       lambda: SchoolOpportunityScoringAgent(self.config).run(top_n=20),
                       input_summary=f"week={self.week_start}")
        scores = r["output"] if r["status"] == "success" else []
        self._add_step("school_opportunity_scoring", r["status"], records=len(scores),
                       note=r["error_message"] or f"S/A级={sum(1 for s in scores if s['priority_level'] in ('S','A'))}")

        # Step 2: 产品供给分析 + 产品评分
        r = runner.run("ProductSupplyRiskAgent",
                       lambda: ProductSupplyRiskAgent(self.config).analyze(period_days=14),
                       input_summary=f"week={self.week_start}")
        supply_result = r["output"] if r["status"] == "success" else {}
        self._add_step("product_supply_risk", r["status"], records=1,
                       note=r["error_message"] or f"orders={supply_result.get('order_count',0)}")

        # Step 3: 线索机会评分
        r = runner.run("LeadOpportunityScoringAgent",
                       lambda: LeadOpportunityScoringAgent(self.config).run(days_lookback=14),
                       input_summary=f"week={self.week_start}")
        lead_scores = r["output"] if r["status"] == "success" else []
        self._add_step("lead_opportunity_scoring", r["status"], records=len(lead_scores),
                       note=r["error_message"] or f"S/A级={sum(1 for l in lead_scores if l['level'] in ('S','A'))}")

        # Step 4: 学校策略卡
        r = runner.run("SchoolStrategyCardAgent",
                       lambda: SchoolStrategyCardAgent(self.config).run(),
                       input_summary=f"week={self.week_start}")
        ok_cards = [c for c in r["output"] if "error" not in c] if r["status"] == "success" else []
        self._add_step("school_strategy_cards", r["status"], records=len(ok_cards),
                       note=r["error_message"])

        # Step 5: 广告预测
        r = runner.run("CampaignPredictionAgent",
                       lambda: CampaignPredictionAgent(self.config).run(
                           week_start=self.week_start, top_schools=5, top_products=3),
                       input_summary=f"week={self.week_start}")
        predictions = r["output"] if r["status"] == "success" else []
        self._add_step("campaign_prediction", r["status"], records=len(predictions),
                       note=r["error_message"] or f"{len(predictions)} 条预测")

        # Step 5b: 归因分析（读最新快照，不强制重新跑）
        attribution_insights = []
        try:
            from database import get_latest_attribution
            _attr = get_latest_attribution()
            if _attr:
                attribution_insights = _attr.get("key_insights") or []
                self._add_step("attribution_insights", "success",
                               note=f"读取归因洞察 {len(attribution_insights)} 条")
        except Exception as _ae:
            self._add_step("attribution_insights", "skipped", note=str(_ae))

        # 构建 context 注入到后续建议（含归因洞察）
        _ctx = self._build_ctx(scores, supply_result, attribution_insights)

        # Step 6: 周度销售建议
        r = runner.run("WeeklySalesSuggestionAgent",
                       lambda: WeeklySalesSuggestionAgent(self.config).generate(
                           week_start=self.week_start, extra_context=_ctx),
                       input_summary=f"week={self.week_start}")
        sales_result = r["output"] if r["status"] == "success" else {}
        self._add_step("weekly_sales_suggestion", r["status"], records=1, note=r["error_message"])

        # Step 7: 周度市场内容建议
        r = runner.run("WeeklyMarketingSuggestionAgent",
                       lambda: WeeklyMarketingSuggestionAgent(self.config).generate(
                           week_start=self.week_start, extra_context=_ctx),
                       input_summary=f"week={self.week_start}")
        marketing_result = r["output"] if r["status"] == "success" else {}
        self._add_step("weekly_marketing_suggestion", r["status"], records=1, note=r["error_message"])

        # Step 8: 企业微信推送
        try:
            push_text = self._build_wecom_push(scores, ok_cards, supply_result, predictions,
                                               attribution_insights)
            sent = self._send_wecom(push_text)
            self._add_step("wecom_push", "success" if sent else "skipped",
                           note="已推送" if sent else "未配置 WECHAT_WORK_WEBHOOK")
        except Exception as e:
            self._add_step("wecom_push", "error", note=str(e))

        sa = [s for s in scores if s["priority_level"] in ("S","A")]
        return {
            "summary": (f"极致增长周度工作流完成：{self.week_start}，"
                        f"学校评分{len(scores)}所（S/A={len(sa)}），"
                        f"预测{len(predictions)}条，策略卡{len(ok_cards)}张"),
            "week_start": self.week_start,
            "school_count": len(scores),
            "prediction_count": len(predictions),
            "card_count": len(ok_cards),
        }

    # ── 推广边界摘要 ─────────────────────────────────────────────
    @staticmethod
    def _build_ctx(scores: list, supply_result: dict, attribution_insights: list = None) -> str:
        lines = []
        try:
            bd = supply_result.get("promotion_boundary", [])
            strong = [b["product"] for b in bd if b.get("push_level") == "strong"]
            cautious = [b["product"] for b in bd if b.get("push_level") in ("cautious","pause")]
            if strong: lines.append(f"本周强推产品：{'、'.join(strong)}")
            if cautious: lines.append(f"谨慎/暂停产品：{'、'.join(cautious)}")
        except Exception:
            pass
        try:
            sa = [s for s in scores if s["priority_level"] in ("S","A")]
            if sa:
                lines.append("重点学校：" + "、".join(s["school_name"] for s in sa[:5]))
        except Exception:
            pass
        if attribution_insights:
            lines.append("【归因洞察】" + "；".join(attribution_insights[:2]))
        return "\n".join(lines)

    # ── 企业微信推送 ─────────────────────────────────────────────
    _PRODUCT_ZH = {
        "regular": "常规课程辅导", "final_prediction": "Final考前预测",
        "guaranteed": "保过辅导", "dissertation": "毕业论文辅导",
        "annual_package": "年度套餐", "dp_premium": "DP高端服务",
        "ai_compliance": "AI合规学习",
    }

    def _pname(self, pid: str) -> str:
        return self._PRODUCT_ZH.get(pid, pid)

    def _build_wecom_push(self, scores, cards, supply_result, predictions,
                          attribution_insights=None) -> str:
        import os
        from datetime import datetime as _dt, timedelta as _td
        card_map = {c.get("school_name"): c for c in cards if "error" not in c}

        try:
            we = (_dt.strptime(self.week_start, "%Y-%m-%d") + _td(days=6))
            week_label = f"{self.week_start[5:7]}月{self.week_start[8:10]}日–{we.strftime('%m月%d日')}"
        except ValueError:
            week_label = self.week_start

        lines = [f"# 📅 极致教育 · 本周作战简报（{week_label}）"]

        if any("基于2025年同期" in str(r) for s in scores for r in s.get("score_reason",[])[:1]):
            lines.append("<font color='comment'>说明：以下判断基于2025年同期数据</font>")
        lines.append("")

        s_list = [s for s in scores if s["priority_level"] == "S"]
        a_list = [s for s in scores if s["priority_level"] == "A"]

        for icon, lv_list, lv in (("🔴", s_list, "S"), ("🟠", a_list, "A")):
            for s in lv_list:
                c = card_map.get(s["school_name"], {})
                p0 = c.get("main_product") or (self._pname(s["hot_products"][0]) if s["hot_products"] else "待定")
                lines.append(f"{icon} **{s['school_name']}**（{lv}级·{s['opportunity_score']}分）{s['current_stage']}｜主推：{p0}")
                # 预测提示
                preds_for_school = [p for p in predictions if p.get("school") == s["school_name"]]
                if preds_for_school:
                    p0pred = preds_for_school[0]
                    lines.append(f"预测咨询：{p0pred['predicted_leads_low']}–{p0pred['predicted_leads_high']}条（{p0pred['confidence']}置信）")
                    if p0pred.get("hook_theme"):
                        lines.append(f"推广钩子：{p0pred['hook_theme']}")
                mkt = (c.get("marketing_suggestions") or [])
                sl_s = (c.get("sales_suggestions") or [])
                if mkt: lines.append(f"→ 推广：{str(mkt[0])[:50]}")
                if sl_s: lines.append(f"→ 顾问：{str(sl_s[0])[:50]}")
                lines.append("")

        # 风险
        risks = list(dict.fromkeys(r for s in scores for r in s.get("risk_notes",[])))
        if risks:
            lines.append("⚠️ **风险提醒**")
            for i, r in enumerate(risks[:3], 1):
                lines.append(f"{i}. {r}")
            lines.append("")

        if attribution_insights:
            lines.append("📊 **本期归因洞察**")
            for _ins in attribution_insights[:2]:
                lines.append(f"· {_ins}")
            lines.append("")

        server = os.environ.get("PUBLIC_URL", "http://121.43.83.158")
        lines.append(f"完整策略卡：{server}")
        lines.append("<font color='comment'>🤖 极致增长系统自动生成</font>")
        return "\n".join(lines)[:2500]

    def _send_wecom(self, text: str) -> bool:
        import os, requests
        webhook = os.environ.get("WECHAT_WORK_WEBHOOK", "")
        if not webhook:
            return False
        resp = requests.post(webhook, json={"msgtype": "markdown",
                                            "markdown": {"content": text}}, timeout=10)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
