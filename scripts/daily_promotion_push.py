"""
每日14:00 推广行动提醒推送脚本 V2.0
增长决策 + 执行动作系统

数据流：
  数据 → DecisionEngine → ActionPlanner → ResourceChecker → RiskGuard → 推送 → ExecutionFeedback

推送格式：📊【增长决策卡】
  1. 本周TOP机会
  2. 各部门必须执行动作
  3. 禁止行为
  4. 风险预警
  5. 数据依据
  6. 可信度评分
"""
import os
import sys
import yaml
import uuid
import logging
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")

from agents.distribution_agent import DistributionAgent
from agents.decision_engine import DecisionEngine
from agents.action_planner import ActionPlanner
from agents.resource_checker import ResourceChecker
from agents.risk_guard import RiskGuard
from agents.channel_content_strategy_agent import ChannelContentStrategyAgent
from agents.time_window_forecast_agent import TimeWindowForecastAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PRODUCT_DISPLAY = {
    "final_prediction": "Final精准押题",
    "regular":          "课业辅导",
    "dissertation":     "毕业论文辅导",
    "guaranteed":       "保过辅导",
    "annual_package":   "学年包",
    "dp_premium":       "DP旗舰版",
    "all":              "全产品线",
}

DEPT_DISPLAY = {
    "promotion_team": "推广部",
    "consultant":     "顾问",
    "xueguan":        "学管",
    "backend":        "后台",
    "management":     "管理层",
}

STATUS_EMOJI = {
    "green":   "🟢",
    "yellow":  "🟡",
    "red":     "🔴",
    "blocked": "⛔",
}

PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚡", "P2": "📌"}


WECOM_MAX = 4000  # 企微 Markdown 上限 4096，留余量


def _split_for_wecom(text: str) -> list:
    """按行切割 Markdown，确保每段 UTF-8 字节数 ≤ WECOM_MAX（中文占3字节）"""
    def blen(s): return len(s.encode("utf-8"))
    if blen(text) <= WECOM_MAX:
        return [text]
    chunks, current, cur_bytes = [], [], 0
    for line in text.splitlines(keepends=True):
        lb = blen(line)
        if cur_bytes + lb > WECOM_MAX and current:
            chunks.append("".join(current))
            current, cur_bytes = [], 0
        current.append(line)
        cur_bytes += lb
    if current:
        chunks.append("".join(current))
    return chunks or [text.encode("utf-8")[:WECOM_MAX].decode("utf-8", errors="ignore")]


def _provider_label(provider: str) -> str:
    labels = {
        "claude":        "Claude",
        "deepseek":      "DeepSeek",
        "qwen":          "Qwen",
        "rule_fallback": "RuleFallback（AI不可用，已启用规则兜底）",
        "rule":          "RuleFallback（AI不可用，已启用规则兜底）",
    }
    name = labels.get(provider, provider or "未知")
    return f"<font color='comment'>🤖 AI生成：{name} · 极致增长系统V2 · 每日14:00</font>"


# ─────────────────────────────────────────────────────────────────────────────
def build_channel_card(today_str: str, channel_recs: list, forecasts: list) -> str:
    """组装渠道内容 + 时间窗口预测卡（第二条推送）"""
    lines = [f"## 📡【渠道作战 + 需求预测】{today_str}", ""]

    # ── 渠道内容策略 ──────────────────────────────────────────
    if channel_recs:
        lines += ["### 🎨 今日渠道内容策略（推广部执行）", ""]
        p0 = [r for r in channel_recs if r.get("priority") == "P0"]
        p1 = [r for r in channel_recs if r.get("priority") == "P1"]
        for r in (p0 + p1)[:4]:
            ch = DEPT_DISPLAY.get(r.get("channel"), r.get("channel", "?"))
            lines.append(f"**{ch}** · {r.get('content_type','')}")
            lines.append(f"> 🪝 {r.get('hook_idea','')}")
            lines.append(f"> 📢 {r.get('cta','')}")
        lines.append("")

    # ── 时间窗口预测（只显示高urgency）────────────────────────
    if forecasts:
        lines += ["### 📅 需求热度预测（推广/顾问提前布局）", ""]
        urgency_order = {"极高": 0, "高": 1, "中": 2, "低": 3}
        hot = sorted(
            [f for f in forecasts if f.get("urgency") in ("极高", "高")],
            key=lambda x: (x.get("window", ""), -x.get("demand_score", 0))
        )
        seen_windows = set()
        for f in hot[:6]:
            w = f.get("window", "")
            if w in seen_windows:
                continue
            seen_windows.add(w)
            label = f.get("window_label", w)
            country = {"UK": "🇬🇧", "AU": "🇦🇺"}.get(f.get("country", ""), "")
            lines.append(
                f"**{label}**（{w}天）{country} 需求分：{f.get('demand_score',0):.0f}/100"
                f" | 预计线索：{f.get('predicted_leads',0)}条 | {f.get('urgency','')}"
            )
            hint = f.get("action_hint", "")
            if hint:
                lines.append(f"> {hint[:80]}")
        lines.append("")

    lines.append("<font color='comment'>🤖 极致增长系统V2 · 数据截至今日</font>")
    return "\n".join(lines)


def build_decision_card(today_str: str, decision: dict, actions: dict,
                        resource: dict, risk: dict,
                        channel_recs: list = None, forecasts: list = None) -> str:
    """组装企微 Markdown 格式的增长决策卡"""

    summary  = decision.get("data_summary", {})
    conf     = decision.get("confidence", "medium")
    conf_map = {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低"}
    res_st   = resource.get("overall", "green")
    risk_lv  = risk.get("overall_risk", "low")
    risk_emoji = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢"}

    lines = [
        f"## 📊【增长决策卡】{today_str}",
        "",
    ]

    # ── 1. TOP 机会 ──────────────────────────────────────────────
    lines += ["### 🎯 本周TOP机会（按优先级排序）", ""]
    opps = decision.get("top_opportunities", [])
    if opps:
        for i, o in enumerate(opps[:3], 1):
            pname = PRODUCT_DISPLAY.get(o.get("product"), o.get("product_name", "?"))
            pri   = o.get("priority", "P1")
            lines.append(
                f"{PRIORITY_EMOJI.get(pri,'')} **机会{i}** [{pri}] {o.get('school','')} · {pname}"
            )
            lines.append(f"> {o.get('reason', '')} | 预期线索：{o.get('expected_leads', '?')}条")
    else:
        lines.append("> 暂无明确机会，维持常规推广节奏")
    lines.append("")

    # ── 2. 各部门必须执行动作 ────────────────────────────────────
    lines += ["### ⚡ 本周必须执行动作", ""]

    dept_order = ["promotion_team", "consultant", "xueguan", "backend", "management"]
    for dept in dept_order:
        dept_actions = actions.get(dept, [])
        if not dept_actions:
            continue
        lines.append(f"**{DEPT_DISPLAY.get(dept, dept)}**")
        for act in dept_actions[:3]:
            pri  = act.get("priority", "P1")
            emoji = PRIORITY_EMOJI.get(pri, "·")
            if dept == "promotion_team":
                text = f"{emoji} {act.get('action','')}（{act.get('quantity','')} / {act.get('deadline','')}）"
                if act.get("school") and act.get("school") != "多校":
                    text += f" [{act.get('school','')}]"
            elif dept == "consultant":
                text = f"{emoji} {act.get('action','')} | 目标：{act.get('deal_target','')}"
                if act.get("talk_track"):
                    text += f"\n> 话术方向：{act.get('talk_track','')}"
            elif dept == "xueguan":
                text = f"{emoji} {act.get('action','')} | 监控：{act.get('risk_monitor','')}"
            elif dept == "management":
                text = f"{emoji} 决策：{act.get('decision','')} | 选项：{' / '.join(act.get('options',[]))}"
            else:
                text = f"{emoji} {act.get('action','')}"
            lines.append(text)
        lines.append("")

    # ── 3. 禁止行为 ──────────────────────────────────────────────
    lines += ["### ⛔ 本周禁止行为（必须执行）", ""]
    forbidden = decision.get("forbidden_actions", [])
    promises  = risk.get("forbidden_promises", [])
    if forbidden:
        for f in forbidden[:4]:
            lines.append(f"- **禁止**：{f.get('action','')} ← {f.get('reason','')}")
    if promises[:3]:
        lines.append("- **不可承诺**：" + " / ".join(promises[:3]))
    if not forbidden and not promises:
        lines.append("- 无特殊禁止项，遵守常规话术边界")
    lines.append("")

    # ── 4. 风险预警 ──────────────────────────────────────────────
    lines += ["### ⚠️ 风险预警", ""]
    alerts = risk.get("alerts", []) + [
        {"type": r.get("type"), "description": r.get("description"),
         "severity": r.get("severity"), "dept": r.get("affected_dept")}
        for r in decision.get("risks", [])
    ]
    # 去重 + 按严重度排序
    seen = set()
    uniq_alerts = []
    for a in alerts:
        key = a.get("description", "")[:40]
        if key not in seen:
            seen.add(key)
            uniq_alerts.append(a)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    uniq_alerts.sort(key=lambda x: sev_order.get(x.get("severity","low"), 3))

    if uniq_alerts:
        for a in uniq_alerts[:5]:
            sev_e = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "⚪"}.get(a.get("severity","low"), "⚪")
            lines.append(f"{sev_e} **{a.get('type','')}**：{a.get('description','')} | 负责：{a.get('dept','')}")
    else:
        lines.append("⚪ 暂无高风险预警")
    lines.append("")

    # ── 5. 数据依据 ──────────────────────────────────────────────
    lines += ["### 📈 数据依据", ""]
    trend_sym = "↑" if (summary.get("order_trend", 0) or 0) > 0 else ("↓" if (summary.get("order_trend", 0) or 0) < 0 else "→")
    lines += [
        f"- 近7天订单：**{summary.get('orders_last_7d', 0)}单** （vs 前7天{summary.get('orders_prev_7d', 0)}单 {trend_sym}{abs(summary.get('order_trend',0))}）",
        f"- 活跃线索：**{summary.get('active_leads', 0)}条** | 超时未跟进：{summary.get('overdue_leads', 0)}条",
        f"- 学生需求：英国 {summary.get('uk_phase','')} | 澳洲 {summary.get('au_phase','')}",
        f"- 老师容量：{STATUS_EMOJI.get(res_st,'')} {res_st.upper()}",
        "",
    ]

    # ── 6. 可信度 + 整体风险 ────────────────────────────────────
    lines += [
        f"### 🧭 系统评估",
        f"- 数据可信度：{conf_map.get(conf, conf)}",
        f"- 整体风险等级：{risk_emoji.get(risk_lv,'')} {risk_lv.upper()}",
        f"- 资源状态：{STATUS_EMOJI.get(res_st,'')} {res_st.upper()}",
        "",
        _provider_label(actions.get("_provider", "unknown")),
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
def _save_actions_as_feedback(today_str: str, actions: dict):
    """将本次推送的动作存入 execution_feedback 表（初始状态 completed=None）"""
    try:
        from database import save_execution_feedback
        dept_order = ["promotion_team", "consultant", "xueguan", "backend", "management"]
        for dept in dept_order:
            for act in actions.get(dept, []):
                action_text = act.get("action") or act.get("decision", "")
                expected    = act.get("quantity") or act.get("deal_target", "")
                save_execution_feedback({
                    "action_id":       f"{today_str}-{dept}-{uuid.uuid4().hex[:8]}",
                    "push_date":       today_str,
                    "department":      dept,
                    "action_text":     action_text,
                    "priority":        act.get("priority", "P1"),
                    "expected_result": expected,
                })
        logger.info(f"[DailyPush] saved execution_feedback for {today_str}")
    except Exception as e:
        logger.warning(f"[DailyPush] save_execution_feedback failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"[DailyPromotionPush V2] starting for {today_str}")

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # ── 1. 决策引擎（无 API，纯数据）────────────────────────────
    try:
        decision = DecisionEngine().run(period_days=14)
        logger.info(f"[DailyPush] DecisionEngine: {len(decision.get('top_opportunities',[]))} opps, "
                    f"resource={decision.get('resource_status')}, confidence={decision.get('confidence')}")
    except Exception as e:
        logger.error(f"[DailyPush] DecisionEngine failed: {e}")
        decision = {
            "top_opportunities": [], "next_week_opportunities": [], "next_month_opportunities": [],
            "forbidden_actions": [], "risks": [], "resource_status": "yellow",
            "data_summary": {}, "phase_now": {}, "phase_next": {}, "confidence": "low",
            "generated_at": datetime.utcnow().isoformat(),
        }

    # ── 2. 资源校验 ──────────────────────────────────────────────
    try:
        resource = ResourceChecker().check()
        logger.info(f"[DailyPush] ResourceChecker: overall={resource.get('overall')}")
    except Exception as e:
        logger.error(f"[DailyPush] ResourceChecker failed: {e}")
        resource = {"overall": "yellow", "by_product": {}, "teacher_summary": [], "recommendations": []}

    # ── 3. 风控评估 ──────────────────────────────────────────────
    try:
        risk = RiskGuard().assess(decision, resource)
        logger.info(f"[DailyPush] RiskGuard: {len(risk.get('alerts',[]))} alerts, "
                    f"overall={risk.get('overall_risk')}")
    except Exception as e:
        logger.error(f"[DailyPush] RiskGuard failed: {e}")
        risk = {"alerts": [], "forbidden_promises": [], "channel_anomalies": [], "overall_risk": "low"}

    # ── 4. 动作拆解（调用 LLMRouter）──────────────────────────────
    try:
        actions = ActionPlanner(config).plan(decision)
        logger.info(f"[DailyPush] ActionPlanner: success")
    except Exception as e:
        logger.error(f"[DailyPush] ActionPlanner failed: {e}")
        actions = {}

    # ── 4b. 渠道内容策略（Phase 2）─────────────────────────────
    try:
        channel_recs = ChannelContentStrategyAgent(config).run(decision)
        logger.info(f"[DailyPush] ChannelContentStrategy: {len(channel_recs)} recs")
    except Exception as e:
        logger.warning(f"[DailyPush] ChannelContentStrategy failed: {e}")
        channel_recs = []

    # ── 4c. 时间窗口预测（Phase 2）─────────────────────────────
    try:
        forecasts = TimeWindowForecastAgent(config).run()
        logger.info(f"[DailyPush] TimeWindowForecast: {len(forecasts)} forecasts")
    except Exception as e:
        logger.warning(f"[DailyPush] TimeWindowForecast failed: {e}")
        forecasts = []

    # ── 5. 组装决策卡 ────────────────────────────────────────────
    markdown = build_decision_card(
        today_str    = today_str,
        decision     = decision,
        actions      = actions,
        resource     = resource,
        risk         = risk,
        channel_recs = channel_recs,
        forecasts    = forecasts,
    )

    # ── 6. 推送企微 ──────────────────────────────────────────────
    dist = DistributionAgent(config)
    # 第二条推送：渠道内容 + 时间窗口预测
    channel_card = build_channel_card(today_str, channel_recs, forecasts)
    all_markdowns = [markdown, channel_card]

    all_ok = True
    for card_idx, card_md in enumerate(all_markdowns):
        logger.info(f"[DailyPush] card {card_idx+1} length={len(card_md)} chars "
                    f"({len(card_md.encode('utf-8'))} bytes)")
        chunks = _split_for_wecom(card_md)
        logger.info(f"[DailyPush] card {card_idx+1}: sending {len(chunks)} chunk(s)")
        for i, chunk in enumerate(chunks):
            ok = dist.push_custom(chunk)
            if ok:
                logger.info(f"[DailyPush] ✅ card{card_idx+1} chunk{i+1}/{len(chunks)} pushed")
            else:
                logger.error(f"[DailyPush] ❌ card{card_idx+1} chunk{i+1}/{len(chunks)} failed")
                all_ok = False
    if not all_ok:
        sys.exit(1)

    # ── 7. 保存动作到 execution_feedback 表 ─────────────────────
    _save_actions_as_feedback(today_str, actions)


if __name__ == "__main__":
    main()
