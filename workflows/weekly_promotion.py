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

    # 产品ID → 中文名（推送中禁止出现英文代码）
    _PRODUCT_ZH = {
        "regular": "常规课程辅导", "final_prediction": "Final考前预测",
        "guaranteed": "保过辅导", "dissertation": "毕业论文辅导",
        "annual_package": "年度套餐", "dp_premium": "DP高端服务",
        "ai_learning": "AI合规学习", "ai_compliance": "AI合规学习",
    }

    def _pname(self, pid: str) -> str:
        return self._PRODUCT_ZH.get(pid, pid)

    @staticmethod
    def _pick(suggestions: list, prefix: str, max_len: int = 60) -> str:
        """从策略卡建议里取指定前缀的那条，去掉前缀和冗余动词，在句读处截断"""
        for s in suggestions or []:
            s = str(s)
            if not s.startswith(prefix):
                continue
            s = s[len(prefix):].strip()
            for verb in ("发布", "推送", "发"):  # 推送文案里已有动词，去掉重复的
                if s.startswith(verb):
                    s = s[len(verb):].lstrip("：:")
                    break
            for q in "「」『』":  # 引号截断后会不对称，统一去掉
                s = s.replace(q, "")
            if len(s) <= max_len:
                return s
            cut = s[:max_len]
            for sep in ("。", "；", "，", ")", "）"):  # 在最近的句读处收尾
                idx = cut.rfind(sep)
                if idx >= int(max_len * 0.5):
                    return cut[:idx + (0 if sep in "。；" else 1)].rstrip("，,") + "…"
            return cut + "…"
        return ""

    @staticmethod
    def _evidence_brief(score: dict) -> str:
        """从评分依据中提取咨询/订单数字，拼成一句话依据"""
        import re
        nums = {}
        for r in score.get("score_reason", []):
            m = re.match(r"近7天咨询 (\d+) 条", r)
            if m: nums["近7天咨询"] = m.group(1)
            m = re.match(r"近30天订单 (\d+) 单", r)
            if m: nums["近30天订单"] = m.group(1)
            m = re.match(r"历史同期\S* ?订单 (\d+) 单", r) or re.match(r"历史同期\(.*\)订单 (\d+) 单", r)
            if m: nums["未来30天同期订单"] = m.group(1)
        return "、".join(f"{k}{v}{'条' if '咨询' in k else '单'}" for k, v in nums.items() if v != "0")

    def _build_wecom_summary(self, scores: list, cards: list, supply_result: dict) -> str:
        """周度推送：每所重点学校 = 依据 + 主推 + 推广动作 + 顾问动作，只推能直接执行的内容"""
        import os
        card_map = {c.get("school_name"): c for c in cards if "error" not in c}
        week_end = ""
        try:
            from datetime import datetime as _dt, timedelta as _td
            week_end = (_dt.strptime(self.week_start, "%Y-%m-%d") + _td(days=6)).strftime("%m月%d日")
            week_label = f"{self.week_start[5:7]}月{self.week_start[8:10]}日–{week_end}"
        except ValueError:
            week_label = self.week_start

        lines = [f"# 📅 极致教育 · 本周作战简报（{week_label}）"]

        # 数据时效说明（评分基于2025年同期时必须告知）
        if any("基于2025年同期" in str(r) for s in scores for r in s.get("score_reason", [])[:1]):
            lines.append("<font color='comment'>说明：CRM未接入，以下判断基于2025年同期订单/咨询数据</font>")
        lines.append("")

        s_list = [s for s in scores if s["priority_level"] == "S"]
        a_list = [s for s in scores if s["priority_level"] == "A"]

        if not s_list and not a_list:
            lines.append("本周暂无 S/A 级重点学校（多数学校数据不足，请优先补充订单/咨询/学校日历数据）")
        for icon, lv_list, lv in (("🔴", s_list, "S"), ("🟠", a_list, "A")):
            for s in lv_list:
                c = card_map.get(s["school_name"], {})
                p0 = c.get("main_product") or self._pname(s["hot_products"][0]) if s["hot_products"] else "待定"
                lines.append(f"{icon} **{s['school_name']}**（{lv}级·{s['opportunity_score']}分）{s['current_stage']}｜主推：{p0}")
                ev = self._evidence_brief(s)
                if ev:
                    lines.append(f"依据：{ev}")
                mk = self._pick(c.get("marketing_suggestions"), "小红书：", max_len=48)
                sl = self._pick(c.get("sales_suggestions"), "重点跟进：", max_len=60)
                if mk:
                    lines.append(f"→ 推广（小红书）：{mk}")
                if sl:
                    lines.append(f"→ 顾问：{sl}")
                lines.append("")

        # 风险提醒（已含学校名，去重）
        risks = list(dict.fromkeys(r for s in scores for r in s.get("risk_notes", [])))
        boundaries = supply_result.get("promotion_boundary", [])
        risks += [f"{self._pname(b['product'])} 老师储备紧张，谨慎强推"
                  for b in boundaries if b.get("push_level") in ("cautious", "pause")]
        if risks:
            lines.append("⚠️ **风险提醒**")
            for i, r in enumerate(risks[:3], 1):
                lines.append(f"{i}. {r}")
            lines.append("")

        server = os.environ.get("PUBLIC_URL", "http://121.43.83.158")
        lines.append(f"完整策略卡（含话术/异议处理/学管提醒）：{server}")
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
