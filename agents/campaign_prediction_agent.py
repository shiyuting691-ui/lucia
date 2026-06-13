"""
CampaignPredictionAgent — 广告预测 Agent

规则引擎计算预测区间；Claude 仅写 hook_theme + rationale，不预测数字。
数据不足时明确标注"历史广告效果数据不足"，置信度 low，区间宽泛。

预测逻辑（每组合 school × product × channel 输出一条）：
  base = school_score × 0.3 + product_score × 0.2 + historical_leads × 0.5
  置信度判断：historical_leads > 5 → medium; > 10 → high
  区间：[max(0, base-delta), base+delta]，delta 由置信度决定
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
import anthropic

from database.db import engine
from database import save_campaign_prediction, list_opportunity_scores, list_school_scores

logger = logging.getLogger(__name__)

CHANNELS = ["小红书", "朋友圈", "社群", "转介绍"]

_PRODUCT_ZH = {
    "regular": "课业辅导",
    "final_prediction": "Final精准押题",
    "guaranteed": "保过辅导",
    "dissertation": "毕业论文辅导",
    "annual_package": "学年包",
    "dp_premium": "DP高端服务",
    "ai_compliance": "AI合规学习",
}


def _traffic_to_score(traffic: str) -> int:
    return {"green": 80, "yellow": 55, "red": 25, "gray": 10}.get(traffic, 40)


class CampaignPredictionAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6") if config else "claude-sonnet-4-6"

    def run(self, week_start: str = None, top_schools: int = 5,
            top_products: int = 3, channels: list = None) -> list[dict]:
        if not week_start:
            today = datetime.now()
            week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        channels = channels or CHANNELS[:2]

        # 加载学校分 & 产品分
        school_scores = {s["school_name"]: s for s in list_school_scores(limit=top_schools * 3)
                         if s["priority_level"] in ("S", "A", "B")}
        product_scores = {p["entity_name"]: p for p in list_opportunity_scores(score_type="product")}

        target_schools  = list(school_scores.keys())[:top_schools]
        target_products = list(product_scores.keys())[:top_products]

        predictions = []
        for school in target_schools:
            for product in target_products:
                for channel in channels:
                    pred = self._predict_one(
                        week_start, school, product, channel,
                        school_scores, product_scores)
                    predictions.append(pred)

        logger.info(f"[CampaignPredictionAgent] generated {len(predictions)} predictions for {week_start}")
        return predictions

    def _predict_one(self, week_start, school, product, channel,
                     school_scores, product_scores) -> dict:
        sc = school_scores.get(school, {})
        pc = product_scores.get(product, {})

        school_score  = sc.get("opportunity_score", 40)
        product_score = pc.get("score", 40)

        # 历史同期咨询量（该学校+产品）
        historical_leads = self._get_historical_leads(school, product, week_start)

        # 规则计算 base
        base = school_score * 0.30 + product_score * 0.20 + historical_leads * 1.5

        # 置信度 & 区间
        if historical_leads >= 10:
            confidence = "medium"
            delta = max(2, int(base * 0.3))
        elif historical_leads >= 3:
            confidence = "low"
            delta = max(3, int(base * 0.5))
        else:
            confidence = "low"
            delta = max(2, int(base * 0.7))
            base = max(1, base)

        low  = max(0, int(base - delta))
        high = max(low + 1, int(base + delta))

        insufficient = historical_leads < 3
        basis = "historical_data" if not insufficient else "rule_only"
        confidence_note = (
            "历史广告效果数据不足，区间仅供参考，实际效果可能有较大偏差"
            if insufficient else
            f"基于{historical_leads}条历史同期咨询数据推算，置信度中等"
        )

        # Claude 只写 hook_theme + rationale（不预测数字）
        hook_theme, rationale = self._gen_hook(
            school, product, channel, school_score, product_score,
            historical_leads, low, high, sc, pc)

        product_zh = _PRODUCT_ZH.get(product, product)
        data = {
            "prediction_week":       week_start,
            "school":                school,
            "product":               product_zh,
            "channel":               channel,
            "hook_theme":            hook_theme,
            "predicted_leads_low":   low,
            "predicted_leads_high":  high,
            "confidence":            confidence,
            "confidence_note":       confidence_note,
            "basis":                 basis,
            "school_score":          school_score,
            "product_score":         product_score,
            "historical_leads":      historical_leads,
            "rationale":             rationale,
        }
        save_campaign_prediction(data)
        return data

    def _get_historical_leads(self, school: str, product: str, week_start: str) -> int:
        """取2025年同期±14天的咨询量作为历史参考"""
        try:
            ws = datetime.strptime(week_start, "%Y-%m-%d")
            anchored = ws.replace(year=2025)
            d_from = (anchored - timedelta(days=14)).strftime("%Y-%m-%d")
            d_to   = (anchored + timedelta(days=14)).strftime("%Y-%m-%d")
            with engine.connect() as c:
                count = c.execute(text(
                    "SELECT COUNT(*) FROM leads WHERE school=:s "
                    "AND (product_interest=:p OR product_interest LIKE :pl) "
                    "AND inquiry_date BETWEEN :f AND :t"
                ), {"s": school, "p": product, "pl": f"%{product}%",
                    "f": d_from, "t": d_to}).scalar() or 0
            return int(count)
        except Exception:
            return 0

    def _gen_hook(self, school, product, channel, ss, ps, hist, low, high,
                  sc: dict, pc: dict) -> tuple[str, str]:
        """Claude 生成推广钩子 + 推理（轻量调用，max_tokens=300）"""
        product_zh = _PRODUCT_ZH.get(product, product)
        stage = sc.get("current_stage", "")
        risk_flags = pc.get("risk_flags", [])

        prompt = (
            f"学校：{school}（当前阶段：{stage or '未知'}）\n"
            f"产品：{product_zh}\n"
            f"推广渠道：{channel}\n"
            f"学校机会评分：{ss}/100，产品推广评分：{ps}/100\n"
            f"历史同期咨询：{hist}条，本周预测区间：{low}-{high}条\n"
            f"风险标记：{', '.join(risk_flags) or '无'}\n\n"
            "请输出两行，格式严格如下：\n"
            "钩子：<15字以内的推广主题/钩子，面向目标学生，不能出现承诺性用语>\n"
            "推理：<30字以内，说明为何此时推此产品最合适，基于数据不编造>\n"
        )
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text_out = resp.content[0].text.strip()
            hook = rationale = ""
            for line in text_out.splitlines():
                if line.startswith("钩子："):
                    hook = line[3:].strip()
                elif line.startswith("推理："):
                    rationale = line[3:].strip()
            return hook or f"{school} {product_zh}推广", rationale or "基于评分推断"
        except Exception as e:
            logger.warning(f"[CampaignPredictionAgent] hook gen failed: {e}")
            return f"{school} {product_zh}", "数据评分推断"
