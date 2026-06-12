"""
WeeklyPromotionWorkflow — 周度推广建议工作流
触发方式：CLI run-weekly-promotion [--week 2026-06-09]
同时生成：销售建议 + 市场内容建议
"""
import logging
from datetime import datetime, timedelta
from .base import BaseWorkflow

logger = logging.getLogger(__name__)


class WeeklyPromotionWorkflow(BaseWorkflow):
    name = "weekly_promotion"

    def __init__(self, config: dict, week_start: str = None):
        super().__init__(config)
        if week_start:
            self.week_start = week_start
        else:
            today = datetime.now()
            self.week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

    def _run_steps(self) -> dict:
        from agents.weekly_sales_suggestion_agent import WeeklySalesSuggestionAgent
        from agents.weekly_marketing_suggestion_agent import WeeklyMarketingSuggestionAgent
        from agents.product_supply_risk_agent import ProductSupplyRiskAgent

        from services.agent_runner import AgentRunner
        runner = AgentRunner(workflow_name=self.name)

        sales_result    = {}
        marketing_result= {}
        supply_result   = {}
        school_summary  = ""

        # Step -1: 学校机会评分（纯规则，不调用AI）
        from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
        r = runner.run("SchoolOpportunityScoringAgent",
                       lambda: SchoolOpportunityScoringAgent(self.config).run(top_n=20),
                       input_summary=f"week={self.week_start} top_n=20")
        scores = r["output"] if r["status"] == "success" else []
        self._add_step("update_school_scores", r["status"], records=len(scores),
                       note=r["error_message"] or
                       f"S/A级={sum(1 for s in scores if s['priority_level'] in ('S','A'))}")

        # Step -1b: 学校策略卡（仅 S/A/B 级）
        from agents.school_strategy_card_agent import SchoolStrategyCardAgent
        r = runner.run("SchoolStrategyCardAgent",
                       lambda: SchoolStrategyCardAgent(self.config).run(),
                       input_summary=f"week={self.week_start}")
        ok_cards = [c for c in r["output"] if "error" not in c] if r["status"] == "success" else []
        self._add_step("generate_school_strategy_cards", r["status"],
                       records=len(ok_cards), note=r["error_message"])

        # 学校维度摘要（注入到周度建议的 extra_context）
        try:
            _s_schools = [s for s in scores if s["priority_level"] == "S"]
            _a_schools = [s for s in scores if s["priority_level"] == "A"]
            _lines = ["本周重点学校（基于内部数据评分）："]
            for s in _s_schools:
                _lines.append(f"  S级 {s['school_name']}｜{s['current_stage']}｜主推:{'、'.join(s['hot_products'][:2])}")
            for s in _a_schools:
                _lines.append(f"  A级 {s['school_name']}｜{s['current_stage']}｜主推:{'、'.join(s['hot_products'][:2])}")
            for c in ok_cards:
                if c.get("priority_level") in ("S", "A") and c.get("main_product"):
                    _lines.append(f"  策略卡 {c['school_name']}: P0={c['main_product']}, 谨慎={c.get('cautious_products', [])}")
            _school_risks = [r for s in scores for r in s.get("risk_notes", [])][:3]
            if _school_risks:
                _lines.append("  学校维度风险：" + "；".join(_school_risks))
            school_summary = "\n".join(_lines) if len(_lines) > 1 else ""
        except Exception:
            pass

        # Step 0: 产品供给与订单风险分析（为后续建议提供推广边界）
        r = runner.run("ProductSupplyRiskAgent",
                       lambda: ProductSupplyRiskAgent(self.config).analyze(period_days=14),
                       input_summary=f"week={self.week_start} period_days=14")
        supply_result = r["output"] if r["status"] == "success" else {}
        self._add_step("product_supply_risk_analysis", r["status"], records=1,
                       note=r["error_message"] or
                       f"week={self.week_start} orders={supply_result.get('order_count',0)}")

        # 从 supply_result 提取推广边界摘要（注入到下方建议的 extra_context）
        _boundary_summary = ""
        try:
            _boundaries = supply_result.get("promotion_boundary", [])
            _strong  = [b["product"] for b in _boundaries if b.get("push_level") == "strong"]
            _normal  = [b["product"] for b in _boundaries if b.get("push_level") == "normal"]
            _cautious= [b["product"] for b in _boundaries if b.get("push_level") == "cautious"]
            _pause   = [b["product"] for b in _boundaries if b.get("push_level") == "pause"]
            _boundary_summary = (
                f"本周推广边界（基于老师储备）：\n"
                f"  强推产品：{'、'.join(_strong) or '无'}\n"
                f"  正常推广：{'、'.join(_normal) or '无'}\n"
                f"  谨慎推广：{'、'.join(_cautious) or '无（需先确认老师档期）'}\n"
                f"  暂停强推：{'、'.join(_pause) or '无'}"
            )
        except Exception:
            pass

        _ctx = "\n\n".join(x for x in (_boundary_summary, school_summary) if x)

        # Step 1: 销售建议
        r = runner.run("WeeklySalesSuggestionAgent",
                       lambda: WeeklySalesSuggestionAgent(self.config).generate(
                           week_start=self.week_start, extra_context=_ctx),
                       input_summary=f"week={self.week_start}")
        sales_result = r["output"] if r["status"] == "success" else {}
        self._add_step("generate_weekly_sales_suggestion", r["status"], records=1,
                       note=r["error_message"] or
                       f"week={self.week_start} suggestion_id={sales_result.get('suggestion_id')}")

        # Step 2: 市场内容建议
        r = runner.run("WeeklyMarketingSuggestionAgent",
                       lambda: WeeklyMarketingSuggestionAgent(self.config).generate(
                           week_start=self.week_start, extra_context=_ctx),
                       input_summary=f"week={self.week_start}")
        marketing_result = r["output"] if r["status"] == "success" else {}
        self._add_step("generate_weekly_marketing_suggestion", r["status"], records=1,
                       note=r["error_message"] or
                       f"week={self.week_start} suggestion_id={marketing_result.get('suggestion_id')}")

        # Step 3: 企业微信推送（摘要，不推长报告）
        try:
            push_text = self._build_wecom_summary(scores, ok_cards, supply_result)
            sent = self._send_wecom(push_text)
            self._add_step("wecom_push", "success" if sent else "skipped",
                           note="已推送" if sent else "未配置 WECHAT_WORK_WEBHOOK")
        except Exception as e:
            self._add_step("wecom_push", "error", note=str(e))
            logger.error(f"[WeeklyPromotionWorkflow] wecom push failed: {e}")

        return {
            "summary": f"周度推广建议生成完成：{self.week_start} ~ {sales_result.get('week_end', '')}，"
                       f"销售建议+市场内容建议各1份已保存，学校评分{len(scores)}所/策略卡{len(ok_cards)}张。",
            "week_start": self.week_start,
            "sales_suggestion_id": sales_result.get("suggestion_id"),
            "marketing_suggestion_id": marketing_result.get("suggestion_id"),
        }

    def _build_wecom_summary(self, scores: list, cards: list, supply_result: dict) -> str:
        """周度推送：重点学校 + 推广边界 + 风险，只推摘要"""
        import os
        card_map = {c.get("school_name"): c for c in cards if "error" not in c}
        lines = [f"# 📅 极致教育 · {self.week_start} 周度作战简报\n", "【本周重点学校】\n"]

        s_list = [s for s in scores if s["priority_level"] == "S"]
        a_list = [s for s in scores if s["priority_level"] == "A"]
        if s_list:
            lines.append("S级重点：")
            for i, s in enumerate(s_list, 1):
                c = card_map.get(s["school_name"], {})
                p0 = c.get("main_product") or "、".join(s["hot_products"][:1]) or "待定"
                lines.append(f"{i}. {s['school_name']}｜{s['current_stage']}｜P0 {p0}")
        if a_list:
            lines.append("\nA级覆盖：")
            for i, s in enumerate(a_list, 1):
                lines.append(f"{i}. {s['school_name']}")
        if not s_list and not a_list:
            lines.append("本周暂无 S/A 级学校（数据不足或为淡季）")

        risks = [r for s in scores for r in s.get("risk_notes", [])]
        boundaries = supply_result.get("promotion_boundary", [])
        risks += [f"{b['product']} 老师储备紧张，谨慎强推"
                  for b in boundaries if b.get("push_level") in ("cautious", "pause")]
        if risks:
            lines.append("\n风险提醒：")
            for i, r in enumerate(dict.fromkeys(risks), 1):   # 去重保序
                if i > 3: break
                lines.append(f"{i}. {r}")

        server = os.environ.get("PUBLIC_URL", "http://121.43.83.158")
        lines.append(f"\n查看学校增长情报台：\n{server}")
        lines.append("\n<font color='comment'>🤖 极致增长系统自动生成</font>")
        return "\n".join(lines)[:2500]

    def _send_wecom(self, text: str) -> bool:
        import os, requests
        webhook = os.environ.get("WECHAT_WORK_WEBHOOK", "")
        if not webhook:
            return False
        resp = requests.post(webhook, json={"msgtype": "markdown",
                                            "markdown": {"content": text}}, timeout=10)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
