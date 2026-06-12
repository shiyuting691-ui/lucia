"""
极致教育 · 增长作战系统控制台
启动：streamlit run dashboard.py
"""
import sys, json
try:
    import pyperclip
except ImportError:
    pyperclip = None
from pathlib import Path
from datetime import datetime, date

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import (
    init_db, list_contents, get_content, update_content_status,
    get_dashboard_stats, list_campaigns, list_knowledge_docs,
    save_feedback, list_feedbacks, update_feedback_status,
    save_suggestion, list_suggestions, update_suggestion_status,
    save_task, list_tasks, update_task_status, get_task_stats,
    save_content_usage, list_content_usages, get_usage_stats,
    list_workflow_runs,
    list_market_signals, list_yearly_patterns, get_current_patterns,
    list_school_calendar, get_order_stats, get_lead_stats,
    list_orders, list_leads,
    list_teacher_capacity, list_order_risks,
    # V6 知识库事实系统
    list_company_facts, update_fact_status, update_fact_content,
    count_facts_by_type, save_company_fact,
    list_dictionary_terms, save_dictionary_term,
    seed_default_dictionary,
    # V7 学校增长情报
    list_school_scores, get_strategy_card, list_strategy_cards,
    save_content,
)
from database.models import TASK_TYPES


# ══════════════════════════════════════════
# 企业微信推送模板函数（供 workflow 和 dashboard 共用）
# ══════════════════════════════════════════

def format_weekly_push(strategy_data: dict, supply_data: dict) -> str:
    """
    周度推送模板：推广策略摘要 + 推广边界分类，不超过2500字
    strategy_data: WeeklySalesSuggestionAgent/WeeklyMarketingSuggestionAgent 的返回结果
    supply_data: ProductSupplyRiskAgent.analyze() 的返回结果
    """
    _week  = strategy_data.get("week_start", "本周")
    _lines = [f"# 📅 极致教育 · {_week} 周度作战简报\n"]

    # 本周重点学校（来自 school_scores）
    try:
        _sch = list_school_scores(limit=50)
        _s_lv = [s for s in _sch if s["priority_level"] == "S"]
        _a_lv = [s for s in _sch if s["priority_level"] == "A"]
        if _s_lv or _a_lv:
            _lines.append("【本周重点学校】")
            for _s in _s_lv:
                _p0 = "、".join(_s["hot_products"][:1]) or "待定"
                _lines.append(f"  S级 {_s['school_name']}｜{_s['current_stage']}｜P0 {_p0}")
            if _a_lv:
                _lines.append("  A级覆盖：" + "、".join(_s["school_name"] for _s in _a_lv))
            _lines.append("")
    except Exception:
        pass

    # 推广边界摘要
    _boundaries = supply_data.get("promotion_boundary", [])
    _strong  = [b["product"] for b in _boundaries if b.get("push_level") == "strong"]
    _cautious= [b["product"] for b in _boundaries if b.get("push_level") in ("cautious","pause")]
    if _strong:
        _lines.append(f"✅ **本周强推**：{'、'.join(_strong)}")
    if _cautious:
        _lines.append(f"⚠️ **谨慎/暂停**：{'、'.join(_cautious)}")
    _lines.append("")

    # 部门动作摘要
    for _da in supply_data.get("department_actions", [])[:3]:
        _dept = _da.get("department", "")
        _acts = (_da.get("actions") or [])[:2]
        if _acts:
            _lines.append(f"**{_dept}**")
            for _a in _acts:
                _lines.append(f"  • {_a}")
            _lines.append("")

    # 订单风险提示
    _risks = supply_data.get("stage_order_risks", [])
    _high_risks = [r for r in _risks if r.get("risk_level") in ("high","critical")]
    if _high_risks:
        _lines.append("🔴 **高风险提示**：")
        for _r in _high_risks[:3]:
            _lines.append(f"  • [{_r.get('risk_level','')}] {_r.get('risk_type','')}（{_r.get('related_product','')}）")
        _lines.append("")

    _lines.append("<font color='comment'>🤖 极致增长系统自动生成</font>")
    return "\n".join(_lines)[:2500]


def format_monthly_push(strategy_text: str) -> str:
    """
    月度推送模板：方向摘要+管理层建议，截取前2000字
    strategy_text: PromotionStrategyAgent.generate() 返回的 strategy 文本
    """
    if not strategy_text:
        return "月度推广策略暂未生成。"
    # 取策略前2000字
    _summary = strategy_text[:2000]
    return (
        f"# 📊 极致教育 · 本月推广战略\n\n"
        f"{_summary}"
        f"\n\n<font color='comment'>🤖 极致增长系统自动生成</font>"
    )


def format_daily_reminder_push(reminders: list) -> str:
    """
    每日提醒推送模板：3-5条关键提醒
    reminders: list of str，每条提醒文本
    """
    import datetime as _dtr
    _today = _dtr.date.today().strftime("%Y年%m月%d日")
    _lines = [f"# 🔔 {_today} 今日有效提醒\n"]
    for _i, _r in enumerate(reminders[:5], 1):
        _lines.append(f"{_i}. {_r}")
    _lines.append("\n<font color='comment'>🤖 极致增长系统自动生成</font>")
    return "\n".join(_lines)


# ── 页面配置 ──────────────────────────────
st.set_page_config(
    page_title="极致教育 · 增长作战系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局 CSS ──────────────────────────────
st.markdown("""
<style>
/* ── 侧边栏 ── */
[data-testid="stSidebar"] { background: #0f172a; }
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stRadio label { font-size:14px; padding: 4px 0; }
[data-testid="stSidebar"] hr { border-color: #334155; }

/* ── 页面背景 ── */
[data-testid="stAppViewContainer"] > .main { background: #f8fafc; }
[data-testid="stAppViewContainer"] { background: #f8fafc; }

/* ── Hero 区 ── */
.hero-block {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    border-radius: 18px;
    padding: 28px 32px 24px 32px;
    margin-bottom: 24px;
    color: white;
}
.hero-title { font-size: 28px; font-weight: 800; color: #ffffff; margin: 0 0 6px 0; }
.hero-subtitle { font-size: 15px; color: #94a3b8; margin: 0 0 14px 0; }
.hero-status { font-size: 13px; color: #60a5fa; background: rgba(59,130,246,0.15);
               display:inline-block; padding: 4px 12px; border-radius: 999px; margin-bottom: 4px; }

/* ── 指标卡 ── */
.metric-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    border-top: 3px solid #3b82f6;
    height: 100%;
}
.metric-num { font-size: 2.2rem; font-weight: 800; color: #0f172a; line-height: 1.1; }
.metric-lbl { font-size: 13px; color: #6b7280; margin-top: 6px; }
.metric-sub { font-size: 11px; color: #9ca3af; margin-top: 3px; }

/* ── 内容区卡片 ── */
.section-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 22px 24px;
    margin-bottom: 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.section-title {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 12px 0; padding-bottom: 10px;
    border-bottom: 1px solid #f1f5f9;
}

/* ── 空状态引导卡 ── */
.empty-card {
    background: #fffbeb;
    border: 1.5px dashed #fbbf24;
    border-radius: 14px;
    padding: 28px 24px;
    text-align: center;
    margin: 16px 0;
}
.empty-card-title { font-size: 16px; font-weight: 700; color: #92400e; margin-bottom: 8px; }
.empty-card-desc  { font-size: 14px; color: #78350f; margin-bottom: 0; }

/* ── 内容列表行 ── */
.content-row {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: box-shadow 0.15s;
}
.content-row:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.content-title { font-size: 15px; font-weight: 600; color: #111827; margin: 0 0 4px 0; }
.content-meta  { font-size: 12px; color: #6b7280; }

/* ── 状态徽章 ── */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; line-height: 1.4;
}
.badge-draft    { background:#dbeafe; color:#1d4ed8; }
.badge-pending  { background:#fef3c7; color:#b45309; }
.badge-approved { background:#d1fae5; color:#065f46; }
.badge-used     { background:#ede9fe; color:#5b21b6; }
.badge-archived { background:#f1f5f9; color:#475569; }
.badge-rejected { background:#fee2e2; color:#b91c1c; }
.badge-risk     { background:#fee2e2; color:#b91c1c; }
.badge-ok       { background:#d1fae5; color:#065f46; }
.badge-warn     { background:#fef3c7; color:#92400e; }

/* ── 建议行 ── */
.suggestion-row {
    background: #f0f9ff;
    border-left: 4px solid #3b82f6;
    border-radius: 0 10px 10px 0;
    padding: 12px 16px;
    margin-bottom: 10px;
}
.suggestion-row.urgent {
    background: #fff7ed;
    border-left-color: #ef4444;
}

/* ── 步骤条 ── */
.step-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid #f1f5f9;
}
.step-num {
    background: #3b82f6; color: white; border-radius: 50%;
    width: 26px; height: 26px; display:inline-flex;
    align-items:center; justify-content:center;
    font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.step-text { font-size: 14px; color: #374151; }

/* ── 风险卡 ── */
.risk-card {
    background: #fff1f2; border: 1px solid #fecdd3;
    border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;
}
.risk-title { font-size: 14px; font-weight: 700; color: #be123c; margin: 0 0 4px 0; }
.risk-desc  { font-size: 13px; color: #9f1239; }

/* ── 话术卡 ── */
.script-card {
    background: #ffffff; border: 1px solid #e5e7eb;
    border-radius: 14px; padding: 18px 20px; margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.script-product { font-size: 12px; font-weight: 600; color: #3b82f6;
                  background: #eff6ff; padding: 2px 8px; border-radius: 999px; }
.script-title { font-size: 15px; font-weight: 700; color: #111827; margin: 8px 0 6px 0; }
.script-body  { font-size: 14px; color: #374151; line-height: 1.6;
                background: #f8fafc; border-radius: 8px; padding: 10px 12px; }

/* ── 上传区卡片 ── */
.upload-card {
    background: #ffffff; border: 1.5px dashed #cbd5e1;
    border-radius: 16px; padding: 22px 20px; text-align: center;
    transition: border-color 0.2s;
}
.upload-card:hover { border-color: #3b82f6; }
.upload-card-icon  { font-size: 32px; margin-bottom: 8px; }
.upload-card-title { font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
.upload-card-desc  { font-size: 13px; color: #6b7280; }

/* ── 通用 ── */
div[data-testid="column"] { padding: 4px 6px; }
.muted { color: #9ca3af; font-size: 13px; }
.section-divider { height: 1px; background: #f1f5f9; margin: 20px 0; }
h3 { color: #1e293b !important; }
</style>
""", unsafe_allow_html=True)

# ── 全局辅助组件 ──────────────────────────
def render_hero(title: str, subtitle: str, status: str = ""):
    status_html = f'<div class="hero-status">{status}</div>' if status else ""
    st.markdown(f"""
    <div class="hero-block">
      <div class="hero-title">{title}</div>
      <div class="hero-subtitle">{subtitle}</div>
      {status_html}
    </div>""", unsafe_allow_html=True)

def render_metric(col, num, label, sub="", color="#3b82f6"):
    col.markdown(f"""
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-num" style="color:{color}">{num}</div>
      <div class="metric-lbl">{label}</div>
      <div class="metric-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

def render_badge(status: str):
    cls = {"draft":"badge-draft","pending_review":"badge-pending","approved":"badge-approved",
           "used":"badge-used","archived":"badge-archived","rejected":"badge-rejected"}.get(status,"badge-draft")
    label = STATUS_ZH.get(status, status)
    return f'<span class="badge {cls}">{label}</span>'

def render_empty_state(title: str, desc: str, btn_label: str = "", btn_page: str = ""):
    st.markdown(f"""
    <div class="empty-card">
      <div class="empty-card-title">📭 {title}</div>
      <div class="empty-card-desc">{desc}</div>
    </div>""", unsafe_allow_html=True)
    if btn_label and btn_page:
        if st.button(btn_label, type="primary"):
            st.session_state["_goto"] = btn_page

# ── 数据库初始化 ──────────────────────────
@st.cache_resource
def _init():
    import yaml
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    init_db(cfg)

_init()

# ── 常量映射 ──────────────────────────────
STATUS_ZH = {
    "draft":"草稿", "pending_review":"待审核", "approved":"已通过",
    "rejected":"已退回", "used":"已使用", "reviewed":"已复盘", "archived":"已废弃",
}
TYPE_ZH = {
    "xiaohongshu":"📱小红书", "moments":"🌅朋友圈", "group_msg":"💬群消息",
    "referral_script":"🔄转介绍", "sales_script":"💼销售话术",
    "monthly_plan":"📅月度计划", "weekly_plan":"📋周计划", "poster":"🎨海报",
    "product_promotion":"📢产品推广", "risk_notice":"⚠️风控提醒",
    "strategy_suggestion":"🧭战略建议",
}
PRODUCT_ZH = {
    "regular":          "常规辅导",
    "annual_package":   "学年包",
    "guaranteed":       "包过辅导",
    "dissertation":     "DP论文辅导",
    "b2b":              "对公合作",
    "final_prediction": "Final精准押题",
    "dp_premium":       "DP高端服务",
    "ai_learning":      "AI合规学习",
    "ai_compliance":    "AI合规学习",
}
DEPT_OPTIONS = ["市场部","销售部","产品部","学管部","管理层"]
FEEDBACK_TYPES = ["产品问题","销售异议","客户需求变化","后端交付风险",
                  "老师资源紧张","学校课程难度变化","价格问题","售后问题","其他"]
SUGGESTION_TYPES = ["产品优化","市场机会","销售策略","推广策略",
                    "风控提醒","资源配置","新产品机会"]
URGENCY_OPTIONS = ["低","中","高","紧急"]
PRIORITY_OPTIONS = ["低","中","高","紧急"]
SG_STATUS_ZH = {"new":"新建","under_review":"审核中","adopted":"已采纳",
                "rejected":"已驳回","archived":"已归档"}
FB_STATUS_ZH = {"open":"待处理","in_progress":"处理中","resolved":"已解决","closed":"已关闭"}

def _kpi(col, num, label, color="#3b82f6"):
    col.markdown(f"""
    <div class="kpi-box" style="border-top-color:{color}">
      <div class="kpi-num" style="color:{color}">{num}</div>
      <div class="kpi-lbl">{label}</div>
    </div>""", unsafe_allow_html=True)

def _tag(status: str):
    cls = {"draft":"tag-draft","pending_review":"tag-pending","approved":"tag-approved",
           "used":"tag-used","rejected":"tag-high","archived":"tag-archived"}.get(status,"tag-draft")
    return f'<span class="{cls}">{STATUS_ZH.get(status,status)}</span>'

# ── 侧边栏 ────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:12px 0 4px 0">
      <div style="font-size:22px;font-weight:800;color:#f8fafc;letter-spacing:-0.5px">🎯 极致教育</div>
      <div style="font-size:13px;color:#64748b;margin-top:2px">增长作战系统</div>
    </div>""", unsafe_allow_html=True)
    st.caption(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
    st.divider()
    st.markdown('<div style="font-size:11px;color:#475569;font-weight:600;letter-spacing:1px;padding:4px 0 6px 2px">核心页面</div>', unsafe_allow_html=True)
    page = st.radio("", [
        "📊 公司增长看板",
        "🏫 学校增长情报台",
        "📈 产品推广策略台",
        "📝 内容池",
        "💼 销售作战台",
        "📁 资料上传中心",
    ], label_visibility="collapsed")
    with st.expander("🧰 更多工具"):
        _more = st.radio("", [
            "（收起）",
            "📚 公司资料学习中心",
            "📡 市场情报台",
            "📅 营销日历",
            "✅ 部门任务台",
            "🗣️ 产品反馈台",
            "🧭 战略建议台",
            "🤖 自动化工作流",
            "🛠 Agent管理中心",
        ], label_visibility="collapsed", key="more_tools")
    if _more != "（收起）":
        page = _more
    st.divider()
    st.caption("v4.0 · 增长作战系统")


# ══════════════════════════════════════════════
# 页面：市场情报台
# ══════════════════════════════════════════════
if page == "🏫 学校增长情报台":
    st.title("🏫 学校增长情报台")
    st.caption("基于内部真实数据的学校机会评分与策略卡 · 不含任何外部编造信息")

    _scores = list_school_scores(limit=100)
    if not _scores:
        st.warning("尚未评分。请先运行：`python main.py update-school-scores`")
        st.stop()

    # ── 筛选器 ──
    _fc = st.columns(7)
    _f_country  = _fc[0].selectbox("国家", ["全部"] + sorted({s["country"] for s in _scores if s["country"]}))
    _f_school   = _fc[1].selectbox("学校", ["全部"] + [s["school_name"] for s in _scores])
    _f_stage    = _fc[2].selectbox("当前阶段", ["全部"] + sorted({s["current_stage"] for s in _scores}))
    _f_heat     = _fc[3].selectbox("需求热度", ["全部", "high", "medium", "low", "unknown"])
    _f_priority = _fc[4].selectbox("优先级", ["全部", "S", "A", "B", "C", "低机会", "Unknown"])
    _f_product  = _fc[5].selectbox("主推产品", ["全部"] + sorted({p for s in _scores for p in s["hot_products"]}))
    _f_complete = _fc[6].selectbox("资料完整度", ["全部", "资料完整", "有缺口"])

    _filtered = [s for s in _scores
                 if (_f_country == "全部" or s["country"] == _f_country)
                 and (_f_school == "全部" or s["school_name"] == _f_school)
                 and (_f_stage == "全部" or s["current_stage"] == _f_stage)
                 and (_f_heat == "全部" or s["demand_heat"] == _f_heat)
                 and (_f_priority == "全部" or s["priority_level"] == _f_priority)
                 and (_f_product == "全部" or _f_product in s["hot_products"])
                 and (_f_complete == "全部"
                      or (_f_complete == "资料完整" and not s["missing_data"])
                      or (_f_complete == "有缺口" and s["missing_data"]))]

    # ── 排行榜 ──
    st.subheader("📊 学校机会排行榜")
    _sort_by = st.radio("排序", ["机会分最高", "风险最高", "资料缺口最多"],
                        horizontal=True, label_visibility="collapsed")
    if _sort_by == "风险最高":
        _filtered.sort(key=lambda s: len(s["risk_notes"]), reverse=True)
    elif _sort_by == "资料缺口最多":
        _filtered.sort(key=lambda s: len(s["missing_data"]), reverse=True)
    else:
        _filtered.sort(key=lambda s: s["opportunity_score"], reverse=True)

    _PRIO_ICON = {"S": "🔴 S", "A": "🟠 A", "B": "🟡 B", "C": "🟢 C",
                  "低机会": "⚪ 低机会", "Unknown": "❓ Unknown"}
    st.dataframe(pd.DataFrame([{
        "排名": i + 1, "学校": s["school_name"], "国家": s["country"],
        "机会分": s["opportunity_score"], "优先级": _PRIO_ICON.get(s["priority_level"], s["priority_level"]),
        "当前阶段": s["current_stage"], "需求热度": s["demand_heat"],
        "主推产品": "、".join(s["hot_products"][:2]) or "—",
        "风险提示": s["risk_notes"][0][:30] if s["risk_notes"] else "—",
        "资料缺口": f"{len(s['missing_data'])}项" if s["missing_data"] else "✓ 完整",
    } for i, s in enumerate(_filtered)]), use_container_width=True, hide_index=True)

    # ── 策略卡 ──
    st.subheader("🃏 学校策略卡")
    _sel = st.selectbox("选择学校查看策略卡", [s["school_name"] for s in _filtered])
    _sc = next((s for s in _filtered if s["school_name"] == _sel), None)
    _card = get_strategy_card(_sel) if _sel else None

    if _sc:
        with st.expander("📐 评分依据与内部证据", expanded=not _card):
            for r in _sc["score_reason"]:
                st.markdown(f"- {r}")
            if _sc["internal_evidence"]:
                st.markdown("**内部数据依据：**")
                for e in _sc["internal_evidence"]:
                    st.markdown(f"- 📌 {e}")
            for m in _sc["missing_data"]:
                st.warning(m)

    if not _card:
        st.info(f"「{_sel}」暂无策略卡。S/A/B 级学校运行 `python main.py generate-school-strategy-cards` 生成；"
                "Unknown 级学校请先补充数据。")
    else:
        _c1, _c2, _c3, _c4 = st.columns(4)
        _c1.metric("机会分", _sc["opportunity_score"] if _sc else "—")
        _c2.metric("优先级", _card["priority_level"])
        _c3.metric("当前阶段", _card["current_stage"])
        _c4.metric("可信度", {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低"}.get(_card["confidence"], _card["confidence"]))

        st.markdown("#### 🎯 本周主推")
        _p1, _p2 = st.columns(2)
        _p1.success(f"**P0 主推**：{_card['main_product'] or '—'}")
        _p2.info(f"**P1 次推**：{'、'.join(_card['secondary_products']) or '—'}")
        if _card["cautious_products"]:
            st.warning(f"⚠️ 谨慎推广：{'、'.join(_card['cautious_products'])}")
        if _card["paused_products"]:
            st.error(f"⏸️ 暂停强推：{'、'.join(_card['paused_products'])}")

        with st.expander("💡 为什么这么推", expanded=True):
            for w in _card["why_this_strategy"]:
                st.markdown(f"- {w}")
            if _card["data_evidence"]:
                st.caption("数据依据：" + "；".join(str(e) for e in _card["data_evidence"][:5]))

        _t1, _t2, _t3, _t4 = st.tabs(["📣 推广部建议", "💼 顾问建议", "🎓 学管提醒", "🛠 后台支持"])
        with _t1:
            for m in _card["marketing_suggestions"]:
                st.markdown(f"- {m}")
        with _t2:
            for m in _card["sales_suggestions"]:
                st.markdown(f"- {m}")
        with _t3:
            for m in _card["academic_support_notes"]:
                st.markdown(f"- {m}")
            for r in _card["risk_notes"]:
                st.warning(r)
        with _t4:
            for m in _card["backend_support_notes"]:
                st.markdown(f"- {m}")

        st.markdown("#### 🔮 未来预判")
        _f1, _f2, _f3 = st.columns(3)
        _f1.markdown(f"**未来7天**\n\n{_card['next_7d_prediction'] or '—'}")
        _f2.markdown(f"**未来14天**\n\n{_card['next_14d_prediction'] or '—'}")
        _f3.markdown(f"**未来30天**\n\n{_card['next_30d_prediction'] or '—'}")

        # ── 学校级素材生成 ──
        st.markdown("#### ✨ 基于策略卡生成素材（进入内容池待审核）")
        _GEN_TYPES = {
            "小红书选题": "xiaohongshu", "朋友圈文案": "moments", "社群话题": "community",
            "顾问私聊话术": "sales_script", "转介绍话术": "referral", "海报文案": "poster",
        }
        _gcols = st.columns(6)
        for _i, (_label, _ctype) in enumerate(_GEN_TYPES.items()):
            if _gcols[_i].button(_label, key=f"gen_school_{_ctype}", use_container_width=True):
                with st.spinner(f"基于 {_sel} 策略卡生成{_label}..."):
                    try:
                        import anthropic as _anthropic
                        _client = _anthropic.Anthropic()
                        _gp = (f"你是教育机构推广文案专家。基于以下学校策略卡，生成3条具体的{_label}。\n"
                               f"学校：{_sel}（{_card['country']}）阶段：{_card['current_stage']}\n"
                               f"P0主推：{_card['main_product']}；次推：{_card['secondary_products']}\n"
                               f"推广建议：{json.dumps(_card['marketing_suggestions'], ensure_ascii=False)}\n"
                               f"销售建议：{json.dumps(_card['sales_suggestions'], ensure_ascii=False)}\n"
                               f"风险约束：{json.dumps(_card['risk_notes'], ensure_ascii=False)}\n"
                               f"要求：紧扣该校当前阶段和主推产品，不泛泛而谈；禁止'100%押中/保过'类承诺；"
                               f"每条之间用'---'分隔。")
                        _resp = _client.messages.create(
                            model="claude-sonnet-4-6", max_tokens=1500,
                            messages=[{"role": "user", "content": _gp}])
                        _body = _resp.content[0].text.strip()
                        save_content({
                            "title": f"{_sel}·{_label}（策略卡生成）",
                            "content_type": _ctype, "school": _sel,
                            "target_country": _card["country"], "channel": _ctype,
                            "content": _body, "status": "pending_review",
                            "suggested_use": f"基于{_sel}周策略卡，阶段：{_card['current_stage']}",
                        })
                        st.success(f"✅ 已生成并存入内容池（待审核）")
                        st.markdown(_body)
                    except Exception as _e:
                        st.error(f"生成失败：{_e}")

elif page == "🛠 Agent管理中心":
    st.title("🛠 Agent 管理中心")
    st.caption("管理/技术专用 · Agent 分层、启停、运行日志与质量反馈 · 启停配置见 config/agents.yaml")

    from agents.agent_registry import load_registry, GROUNDING_REQUIRED, LAYERS
    from database import list_agent_runs, get_agent_last_runs, save_agent_feedback, list_agent_feedbacks

    _reg = load_registry()
    _last = get_agent_last_runs()

    _tab1, _tab2, _tab3, _tab4, _tab5 = st.tabs(
        ["📋 Agent总览", "🏗 分层视图", "📜 运行日志", "⭐ 质量反馈", "💡 启停建议"])

    with _tab1:
        _fc = st.columns(5)
        _f_layer  = _fc[0].selectbox("层级", ["全部"] + list(LAYERS))
        _f_status = _fc[1].selectbox("状态", ["全部", "active", "paused", "deprecated", "experimental"])
        _f_en     = _fc[2].selectbox("是否启用", ["全部", "启用", "停用"])
        _f_llm    = _fc[3].selectbox("是否调用LLM", ["全部", "是", "否"])
        _f_fail   = _fc[4].selectbox("最近失败", ["全部", "仅失败"])

        _rows = []
        for _name, _info in _reg.items():
            _lr = _last.get(_name, {})
            if _f_layer != "全部" and _info["layer"] != _f_layer: continue
            if _f_status != "全部" and _info["status"] != _f_status: continue
            if _f_en != "全部" and _info["enabled"] != (_f_en == "启用"): continue
            if _f_llm != "全部" and _info["uses_llm"] != (_f_llm == "是"): continue
            if _f_fail == "仅失败" and _lr.get("status") != "failed": continue
            _rows.append({
                "Agent": _name, "中文名": _info["display_name"], "层级": _info["layer"],
                "职责": _info["description"][:40],
                "状态": {"active":"🟢","paused":"⏸️","deprecated":"🚫","experimental":"🧪"}.get(_info["status"],"") + _info["status"],
                "启用": "✅" if _info["enabled"] else "❌",
                "LLM": "✅" if _info["uses_llm"] else "—",
                "需事实校验": "🔒" if _name in GROUNDING_REQUIRED else "—",
                "最近运行": _lr.get("at", "从未"),
                "最近结果": _lr.get("status", "—"),
                "最近错误": (_lr.get("error_message") or "")[:30] or "—",
            })
        st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)

    with _tab2:
        for _layer in LAYERS:
            _in_layer = {n: i for n, i in _reg.items() if i["layer"] == _layer}
            _on = sum(1 for i in _in_layer.values() if i["enabled"])
            st.markdown(f"#### {_layer}（{len(_in_layer)}个，启用{_on}个）")
            _cols = st.columns(min(4, max(1, len(_in_layer))))
            for _i, (_n, _info) in enumerate(_in_layer.items()):
                _icon = "🟢" if _info["enabled"] else ("🚫" if _info["status"] == "deprecated" else "⏸️")
                _cols[_i % 4].markdown(f"{_icon} **{_info['display_name']}**<br>"
                                       f"<small>{_n}<br>{_info['status']}</small>",
                                       unsafe_allow_html=True)
            st.divider()

    with _tab3:
        _lc = st.columns(3)
        _l_days  = _lc[0].selectbox("时间范围", ["最近24小时", "最近7天", "最近30天"], index=1)
        _l_agent = _lc[1].selectbox("Agent", ["全部"] + sorted(_reg.keys()), key="log_agent")
        _l_stat  = _lc[2].selectbox("状态", ["全部", "success", "failed", "skipped", "blocked"], key="log_stat")
        _days = {"最近24小时": 1, "最近7天": 7, "最近30天": 30}[_l_days]
        _logs = list_agent_runs(
            agent_name=None if _l_agent == "全部" else _l_agent,
            status=None if _l_stat == "全部" else _l_stat, days=_days)
        if not _logs:
            st.info("该时间范围内无运行记录")
        else:
            st.dataframe(pd.DataFrame([{
                "时间": l["started_at"], "Workflow": l["workflow_name"], "Agent": l["agent_name"],
                "状态": {"success":"✅","failed":"❌","skipped":"⏭️","blocked":"🚧"}.get(l["status"],"") + l["status"],
                "耗时(s)": l["duration_seconds"], "Tokens": l["tokens_used"],
                "Cost($)": l["cost_estimate"],
                "输入": (l["input_summary"] or "")[:40],
                "输出": (l["output_summary"] or "")[:40],
                "错误": (l["error_message"] or "")[:60],
            } for l in _logs]), use_container_width=True, hide_index=True)

    with _tab4:
        st.markdown("##### 对某次 Agent 运行打分（用于后续优化 prompt）")
        _recent = list_agent_runs(days=7, limit=50)
        if _recent:
            _run_opts = {f"#{l['id']} {l['agent_name']} {l['started_at']} [{l['status']}]": l for l in _recent}
            _sel_run = st.selectbox("选择运行记录", list(_run_opts.keys()))
            _r = _run_opts[_sel_run]
            with st.form("agent_feedback_form"):
                _s1 = st.slider("有用程度", 1, 5, 3)
                _s2 = st.slider("准确程度", 1, 5, 3)
                _s3 = st.slider("可执行程度", 1, 5, 3)
                _hf = st.checkbox("存在幻觉/编造内容")
                _ft = st.text_area("反馈备注", placeholder="例如：建议太泛、学校信息有误…")
                _fu = st.text_input("评价人", value="Lucia")
                if st.form_submit_button("提交评分", type="primary"):
                    save_agent_feedback({
                        "agent_run_id": _r["id"], "agent_name": _r["agent_name"],
                        "feedback_user": _fu, "usefulness_score": _s1,
                        "accuracy_score": _s2, "actionability_score": _s3,
                        "hallucination_flag": _hf, "feedback_text": _ft,
                    })
                    st.success("✅ 反馈已保存")
        else:
            st.info("最近7天无运行记录可评分")

        _fbs = list_agent_feedbacks(limit=30)
        if _fbs:
            st.markdown("##### 历史反馈")
            st.dataframe(pd.DataFrame([{
                "时间": f["created_at"], "Agent": f["agent_name"], "评价人": f["feedback_user"],
                "有用": f["usefulness_score"], "准确": f["accuracy_score"],
                "可执行": f["actionability_score"],
                "幻觉": "⚠️是" if f["hallucination_flag"] else "否",
                "备注": (f["feedback_text"] or "")[:50],
            } for f in _fbs]), use_container_width=True, hide_index=True)

    with _tab5:
        _SUGGEST = {
            "必须启用": [n for n, i in _reg.items() if i["enabled"] and i["status"] == "active"],
            "待确认（experimental）": [n for n, i in _reg.items() if i["status"] == "experimental"],
            "可暂时停用（已停用）": [n for n, i in _reg.items() if not i["enabled"] and i["status"] == "paused"],
            "建议废弃（deprecated）": [n for n, i in _reg.items() if i["status"] == "deprecated"],
        }
        for _k, _v in _SUGGEST.items():
            st.markdown(f"**{_k}（{len(_v)}）**：" + ("、".join(_v) or "无"))
        st.caption("调整方式：编辑 config/agents.yaml 中对应 agent 的 enabled / status，重启服务生效。"
                   "停用不删除代码，随时可恢复。")

elif page == "📡 市场情报台":
    st.title("📡 市场情报台")
    st.caption("基于实时订单、咨询数据和学校节点，动态追踪市场机会。")
    st.info("📌 当前订单/咨询数据为演示样本（14条），接入真实数据后指标将自动更新。", icon="ℹ️")

    # ── 一键刷新信号 ─────────────────────────────
    col_btn, col_tip = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 刷新市场信号", type="primary", use_container_width=True):
            import subprocess, os
            env = os.environ.copy()
            with st.spinner("正在分析市场数据..."):
                try:
                    r = subprocess.run(
                        ["uv","run","--with","sqlalchemy","--with","anthropic",
                         "--with","pyyaml","--with","requests","--with","schedule",
                         "python","main.py","update-market-signals"],
                        capture_output=True, text=True, timeout=90,
                        cwd=str(ROOT), env=env,
                    )
                    if r.returncode == 0:
                        st.success("✅ 市场信号已更新")
                    else:
                        st.error(f"更新失败：{r.stderr[:200]}")
                except Exception as e:
                    st.error(f"执行失败：{e}")
    with col_tip:
        st.info("每日运行工作流时会自动更新信号，也可手动点击刷新。")

    st.divider()

    # ── KPI 行 ────────────────────────────────
    os7  = get_order_stats(days=7)
    os30 = get_order_stats(days=30)
    ls7  = get_lead_stats(days=7)
    ls30 = get_lead_stats(days=30)

    kc = st.columns(6)
    _kpi(kc[0], os7["total"],    "近7天订单",     "#3b82f6")
    _kpi(kc[1], os30["total"],   "近30天订单",    "#6366f1")
    _kpi(kc[2], ls7["total"],    "近7天咨询",     "#10b981")
    _kpi(kc[3], ls30["total"],   "近30天咨询",    "#059669")
    _kpi(kc[4], f"¥{os7['total_amount']:,.0f}", "近7天成交额", "#f59e0b")
    _kpi(kc[5], f"{ls7['conversion_rate']:.1%}", "近7天转化率", "#ef4444")

    st.divider()

    left, right = st.columns(2)

    with left:
        # ── 热门学校 ───────────────────────────
        st.subheader("🔥 近7天热门学校")
        school_orders = os7.get("by_school", [])
        school_leads  = ls7.get("by_school", [])
        school_merged: dict = {}
        for s, n in school_orders: school_merged[s] = school_merged.get(s, 0) + n * 2
        for s, n in school_leads:  school_merged[s] = school_merged.get(s, 0) + n
        top_schools = sorted(school_merged, key=lambda k: -school_merged[k])[:6]
        if top_schools:
            cols = st.columns(3)
            for i, sch in enumerate(top_schools):
                score = school_merged[sch]
                cols[i % 3].metric(sch, f"热度 {score}")
        else:
            st.info("暂无订单/咨询数据。请先导入：`python main.py ingest-orders data/orders.csv`")

        # ── 近7天热门产品 ──────────────────────
        st.subheader("💼 近7天热门产品")
        prod_orders = dict(os7.get("by_product", []))
        prod_leads  = dict(ls7.get("by_product", []))
        PRODUCT_NAMES = {
            "regular":          "常规辅导",
            "annual_package":   "学年包",
            "guaranteed":       "包过辅导",
            "dissertation":     "DP论文辅导",
            "b2b":              "对公合作",
            "final_prediction": "Final精准押题",
            "dp_premium":       "DP高端服务",
            "ai_learning":      "AI合规学习",
            "ai_compliance":    "AI合规学习",
        }
        all_prods = set(list(prod_orders.keys()) + list(prod_leads.keys()))
        if all_prods:
            prod_data = [
                {"产品": PRODUCT_NAMES.get(p, p),
                 "订单量": prod_orders.get(p, 0),
                 "咨询量": prod_leads.get(p, 0)}
                for p in all_prods if p
            ]
            prod_data.sort(key=lambda x: -(x["订单量"] + x["咨询量"]))
            st.dataframe(pd.DataFrame(prod_data[:6]), use_container_width=True, hide_index=True)
        else:
            st.info("暂无产品数据")

        # ── 往年同期规律 ───────────────────────
        st.subheader("📅 往年同期规律")
        patterns = get_current_patterns(days_window=21)
        if patterns:
            for p in patterns[:5]:
                with st.expander(
                    f"📌 {p.get('school','')} · {p.get('product','')} · "
                    f"{p.get('period_start','')}~{p.get('period_end','')}",
                    expanded=False,
                ):
                    st.write(p.get("pattern_summary", ""))
                    mc = st.columns(3)
                    mc[0].metric("往年量", p.get("historical_volume", 0))
                    mc[1].metric("转化率", f"{(p.get('conversion_rate') or 0):.1%}")
                    mc[2].metric("建议提前", f"{p.get('recommended_lead_time_days',14)}天")
                    if p.get("suggested_campaign"):
                        st.caption(f"💡 建议活动：{p['suggested_campaign']}")
        else:
            st.info("暂无往年规律数据。运行 `python main.py analyze-history` 生成。")

    with right:
        # ── 未来2-4周节点 ─────────────────────
        st.subheader("⏰ 未来4周学校节点")
        upcoming = list_school_calendar(days_ahead=28)
        if upcoming:
            CONF_COLOR = {"high":"🟢","medium":"🟡","low":"⚪"}
            for node in upcoming[:10]:
                conf_icon = CONF_COLOR.get(node.get("confidence",""), "⚪")
                start = (node.get("start_date") or "")[:10]
                end   = (node.get("end_date") or "")[:10]
                st.markdown(
                    f"{conf_icon} **{node['school']}** · {node['event_type']} · "
                    f"_{start}_{' → ' + end if end != start else ''}"
                )
                if node.get("event_name"):
                    st.caption(f"   {node['event_name']}")
        else:
            st.info("暂无学校节点数据。运行 `python main.py ingest-calendar data/school_calendar.csv`")

        # ── 最新市场信号 ──────────────────────
        st.subheader("📊 最新市场信号")
        signals = list_market_signals(days=7, limit=15)
        if signals:
            PRIORITY_COLOR = {"紧急":"🔴","高":"🟠","中":"🟡","低":"⚪"}
            TREND_ICON = {"up":"📈","down":"📉","stable":"➡️"}
            for sig in signals[:8]:
                pri  = sig.get("priority","中")
                icon = PRIORITY_COLOR.get(pri,"⚪")
                trend = TREND_ICON.get(sig.get("trend",""),"")
                label = f"{icon} [{sig['signal_type']}] {sig.get('school','')} {sig.get('product','')}"
                with st.expander(label + f" {trend}", expanded=(pri in ("紧急","高") and sig == signals[0])):
                    st.write(sig.get("evidence",""))
                    if sig.get("suggested_action"):
                        st.success(f"💡 建议：{sig['suggested_action']}")
        else:
            st.info("暂无市场信号。点击「刷新市场信号」按钮生成。")

    st.divider()

    # ── 咨询成交来源渠道分析 ──────────────────
    st.subheader("📣 近30天咨询来源渠道")
    channel_data = ls30.get("by_channel", [])
    if channel_data:
        df_channel = pd.DataFrame(channel_data, columns=["渠道","咨询量"])
        st.dataframe(df_channel, use_container_width=True, hide_index=True)
    else:
        st.info("暂无渠道数据")

    # ── 推荐营销动作（来自最新 LLM 分析）────────
    st.subheader("🎯 AI 推荐营销动作")
    latest_signals = list_market_signals(days=7, limit=20)
    actions = [s.get("suggested_action","") for s in latest_signals if s.get("suggested_action")]
    if actions:
        for i, action in enumerate(actions[:5], 1):
            st.info(f"**{i}.** {action}")
    else:
        st.info("运行每日工作流或刷新市场信号以获取 AI 推荐动作")


# ══════════════════════════════════════════════
# 页面：产品推广策略台
# ══════════════════════════════════════════════
elif page == "📈 产品推广策略台":
    st.title("📈 产品推广策略台")
    st.caption("基于真实销售数据 + 老师储备资源 + 市场信号，AI 自动生成月度/周度推广策略，驱动销售、市场、产品协同作战。")

    # ── 资料状态横幅 ──────────────────────────────────────────────
    from agents.grounded_business_agent import GroundedBusinessAgent as _GBA_strat
    _gba_strat = _GBA_strat()
    _strat_ctx = _gba_strat.get_context("monthly_strategy")
    _gap_strat = _gba_strat.get_knowledge_gap_status()
    _confirmed_count = sum(g["confirmed"] for g in _gap_strat)
    _missing_critical = [g for g in _gap_strat if g["status"] == "未上传" and g["fact_type"] in ("产品事实","部门事实")]

    if _strat_ctx["facts_count"] == 0:
        st.error(
            "⚠️ **当前无已确认资料事实，策略建议基于临时参考生成，可靠性有限。**\n\n"
            "请到 [📚 公司资料学习中心](#) 上传并确认以下资料：\n"
            + "\n".join(f"- {g['label']}" for g in _gap_strat if g['status'] == '未上传')
        )
    elif _missing_critical:
        st.warning(
            f"⚠️ 已加载 **{_strat_ctx['facts_count']}** 条已确认事实，但部分关键资料仍缺失：\n"
            + "\n".join(f"- {g['label']}（{g['status']}）" for g in _missing_critical)
        )
    else:
        st.success(
            f"✅ 已加载 **{_strat_ctx['facts_count']}** 条已确认事实 | "
            f"{_strat_ctx['data_source_note'].split(chr(10))[0]}"
        )

    # ── 加载页面所需数据 ──────────────────────────────────────────
    _monthly_strategy  = list_suggestions(suggestion_type="monthly_promotion_strategy", limit=1)
    _supply_risk_sugg  = list_suggestions(suggestion_type="product_supply_risk", limit=1)
    _orders_30d        = list_orders(days=30, limit=500)
    _order_risks_all   = list_order_risks(limit=20)
    _capacities_all    = list_teacher_capacity()
    _has_data          = len(_orders_30d) >= 10

    # 解析 supply_risk JSON
    _supply_data = {}
    if _supply_risk_sugg:
        try:
            import json as _json
            _supply_data = _json.loads(_supply_risk_sugg[0].get("content", "{}"))
        except Exception:
            _supply_data = {}

    _promotion_boundary = _supply_data.get("promotion_boundary", [])

    # 四个主 Tab
    _tab_strategy, _tab_weekly_play, _tab_dept, _tab_materials = st.tabs([
        "📅 本月战略",
        "📆 本周打法",
        "🏢 部门动作",
        "📦 可用素材",
    ])

    # ══════════════════════════════════════════════
    # Tab 1：本月战略
    # ══════════════════════════════════════════════
    with _tab_strategy:
        st.subheader("📅 本月战略总览")

        # 顶部生成按钮区
        _sc1, _sc2, _sc3 = st.columns([2, 1, 1])
        with _sc1:
            import datetime as _dt
            _default_month = _dt.date.today().strftime("%Y-%m")
            _target_month_input = st.text_input("目标月份", value=_default_month, placeholder="2026-07", key="strategy_month")
        with _sc2:
            st.write(""); st.write("")
            _gen_monthly = st.button("🚀 生成本月推广策略", type="primary", use_container_width=True, key="gen_monthly_btn")
        with _sc3:
            st.write(""); st.write("")
            _gen_supply = st.button("🔄 更新产品供给分析", use_container_width=True, key="gen_supply_btn")

        if _gen_monthly:
            _month_v = _target_month_input.strip() or _default_month
            import yaml as _yaml
            with open(ROOT / "config.yaml") as _f:
                _cfg = _yaml.safe_load(_f)
            with st.spinner(f"AI 正在分析数据并生成 {_month_v} 月度推广策略（约30秒）..."):
                try:
                    from agents.promotion_strategy_agent import PromotionStrategyAgent
                    _agent = PromotionStrategyAgent(_cfg)
                    _result = _agent.generate(target_month=_month_v)
                    st.success(f"✅ {_month_v} 月度推广策略生成完成！建议ID: {_result.get('suggestion_id')}")
                    if not _result.get("data_sufficient"):
                        st.warning("⚠️ 历史订单数据较少（< 10单），策略参考价值有限，建议先导入更多真实数据。")
                    st.rerun()
                except Exception as _e:
                    st.error(f"生成失败：{_e}")

        if _gen_supply:
            import yaml as _yaml_s
            with open(ROOT / "config.yaml") as _fs:
                _cfg_s = _yaml_s.safe_load(_fs)
            with st.spinner("正在运行产品供给与订单风险分析..."):
                try:
                    from agents.product_supply_risk_agent import ProductSupplyRiskAgent
                    _sra = ProductSupplyRiskAgent(_cfg_s)
                    _sr  = _sra.analyze(period_days=14)
                    st.success(f"✅ 供给分析完成！订单样本：{_sr.get('order_count',0)}单")
                    st.rerun()
                except Exception as _se:
                    st.error(f"分析失败：{_se}")

        st.divider()

        # 顶部 Hero 卡：本月状态总览
        _hero_col1, _hero_col2, _hero_col3, _hero_col4 = st.columns(4)
        _hero_col1.metric("本月订单", len(_orders_30d), help="近30天订单数")
        _hero_col2.metric("老师储备学科", len(_capacities_all), help="teacher_capacity 表记录数")
        _hero_col3.metric("订单风险信号", len(_order_risks_all), help="当前活跃风险信号数")
        _hero_col4.metric("数据状态", "✅ 充足" if _has_data else "⚠️ 有限")

        # 产品优先级卡（基于 promotion_boundary）
        st.markdown("#### 产品推广优先级")
        if not _promotion_boundary:
            st.info("暂无推广边界数据。点击「更新产品供给分析」按钮生成。")
        else:
            # 定义优先级标签颜色
            _PUSH_BADGE = {
                "strong":   ("P0 强推", "🟢"),
                "normal":   ("P1 正常", "🔵"),
                "cautious": ("⚠️ 谨慎", "🟡"),
                "pause":    ("⛔ 暂停", "🔴"),
            }
            _pb_cols = st.columns(min(len(_promotion_boundary), 4))
            for _i, _pb in enumerate(_promotion_boundary):
                _col = _pb_cols[_i % 4]
                _badge_text, _badge_icon = _PUSH_BADGE.get(_pb.get("push_level","normal"), ("P1 正常", "🔵"))
                with _col:
                    with st.container(border=True):
                        st.markdown(f"**{_pb.get('product','')}**")
                        st.caption(f"{_badge_icon} {_badge_text}")
                        st.caption(_pb.get("reason","")[:60])
                        if _pb.get("tight_subjects"):
                            st.caption(f"⚠️ 资源紧张：{'/'.join(_pb['tight_subjects'][:2])}")

        st.divider()

        # 月度策略报告展示
        st.markdown("#### 已生成的月度策略报告")
        _monthly_suggestions = list_suggestions(suggestion_type="monthly_promotion_strategy", limit=6)
        if not _monthly_suggestions:
            st.info("暂无月度策略。点击上方「生成本月推广策略」按钮。")
        else:
            for _s in _monthly_suggestions:
                _created = str(_s.get("created_at", ""))[:16]
                with st.expander(f"📋 {_s.get('title', '')} — {_created}", expanded=(_s == _monthly_suggestions[0])):
                    _basis = _s.get("data_basis") or {}
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _mc1.metric("月份", _basis.get("target_month", "—"))
                    _mc2.metric("数据量", f"{_basis.get('order_count', 0)}单")
                    _mc3.metric("数据状态", "✅ 充足" if _basis.get("data_sufficient") else "⚠️ 有限")
                    # 依据来源展示
                    _facts_at_gen = _basis.get("facts_count", 0)
                    _src_note = _basis.get("data_source_note", "")
                    _missing_at_gen = _basis.get("missing_info", [])
                    with st.container():
                        if _facts_at_gen and _facts_at_gen > 0:
                            st.markdown(
                                f"""<div style="background:#0f2a1a;border:1px solid #166534;border-radius:6px;padding:8px 12px;margin:8px 0;font-size:12px;color:#86efac">
                                📎 <b>依据来源</b> | 生成时已确认事实：{_facts_at_gen} 条 | {_src_note.split(chr(10))[0] if _src_note else ''}
                                </div>""",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                """<div style="background:#2a1a0f;border:1px solid #92400e;border-radius:6px;padding:8px 12px;margin:8px 0;font-size:12px;color:#fcd34d">
                                ⚠️ <b>临时参考</b> | 生成时无已确认事实，建议可靠性有限。请到「公司资料学习中心」上传并确认资料。
                                </div>""",
                                unsafe_allow_html=True
                            )
                        if _missing_at_gen:
                            with st.expander(f"📋 生成时缺少 {len(_missing_at_gen)} 项资料（展开查看）"):
                                for _m in _missing_at_gen:
                                    st.caption(f"- {_m}")
                    st.markdown(_s.get("content", ""))

    # ══════════════════════════════════════════════
    # Tab 2：本周打法
    # ══════════════════════════════════════════════
    with _tab_weekly_play:
        st.subheader("📆 本周作战打法")

        # 生成控制区
        import datetime as _dt2
        _today2 = _dt2.date.today()
        _monday = _today2 - _dt2.timedelta(days=_today2.weekday())
        _default_week = _monday.strftime("%Y-%m-%d")

        _wc1, _wc2, _wc3 = st.columns([2, 1, 1])
        with _wc1:
            _week_input = st.text_input("周起始日期（周一）", value=_default_week, placeholder="2026-06-09", key="week_input")
        with _wc2:
            st.write(""); st.write("")
            _gen_sales = st.button("📊 生成销售建议", use_container_width=True, key="gen_sales")
        with _wc3:
            st.write(""); st.write("")
            _gen_mkt = st.button("📣 生成市场内容包", use_container_width=True, key="gen_mkt")
        _gen_both = st.button("🚀 生成本周推广建议（销售+市场+供给分析）", type="primary", use_container_width=True, key="gen_both")

        if _gen_both or _gen_sales or _gen_mkt:
            _wk = _week_input.strip() or _default_week
            import yaml as _yaml2
            with open(ROOT / "config.yaml") as _f2:
                _cfg2 = _yaml2.safe_load(_f2)
            if _gen_both:
                with st.spinner(f"AI 正在生成 {_wk} 周度推广建议（约45秒）..."):
                    try:
                        from workflows.weekly_promotion import WeeklyPromotionWorkflow
                        _wf = WeeklyPromotionWorkflow(_cfg2, week_start=_wk)
                        _wr = _wf.run(trigger="dashboard")
                        st.success(f"✅ {_wr.get('summary', '周度推广建议生成完成')}")
                        st.rerun()
                    except Exception as _e2:
                        st.error(f"生成失败：{_e2}")
            elif _gen_sales:
                with st.spinner(f"AI 正在生成 {_wk} 销售建议（约20秒）..."):
                    try:
                        from agents.weekly_sales_suggestion_agent import WeeklySalesSuggestionAgent
                        _sa = WeeklySalesSuggestionAgent(_cfg2)
                        _sr2 = _sa.generate(week_start=_wk)
                        st.success(f"✅ 销售建议生成完成！ID: {_sr2.get('suggestion_id')}")
                        st.rerun()
                    except Exception as _e3:
                        st.error(f"生成失败：{_e3}")
            elif _gen_mkt:
                with st.spinner(f"AI 正在生成 {_wk} 市场内容包（约25秒）..."):
                    try:
                        from agents.weekly_marketing_suggestion_agent import WeeklyMarketingSuggestionAgent
                        _ma = WeeklyMarketingSuggestionAgent(_cfg2)
                        _mr = _ma.generate(week_start=_wk)
                        st.success(f"✅ 市场内容包生成完成！ID: {_mr.get('suggestion_id')}")
                        st.rerun()
                    except Exception as _e4:
                        st.error(f"生成失败：{_e4}")

        st.divider()

        # 顶部作战总览：读取最新 supply_risk 数据
        if _supply_data:
            _dept_actions = _supply_data.get("department_actions", [])
            if _dept_actions:
                st.markdown("#### 本周作战总览（基于最新供给分析）")
                for _da in _dept_actions[:2]:
                    st.markdown(f"**{_da.get('department','')}**")
                    for _act in (_da.get("actions") or [])[:3]:
                        st.caption(f"• {_act}")
                st.divider()

        # 三栏布局
        _w_col1, _w_col2, _w_col3 = st.columns(3)

        with _w_col1:
            st.markdown("#### A. 市场本周怎么推")
            _mkt_sugg = list_suggestions(suggestion_type="weekly_marketing_suggestion", limit=3)
            if not _mkt_sugg:
                st.info("暂无市场建议，点击上方生成按钮。")
            for _ms in _mkt_sugg:
                _mc = str(_ms.get("created_at",""))[:10]
                with st.expander(f"{_ms.get('title','')} ({_mc})", expanded=(_ms == _mkt_sugg[0])):
                    _mb = _ms.get("data_basis") or {}
                    _mfc = _mb.get("facts_count", 0)
                    if _mfc:
                        st.caption(f"📎 生成时已确认事实：{_mfc} 条")
                    else:
                        st.caption("⚠️ 临时参考模式，无已确认事实")
                    st.markdown(_ms.get("content",""))

        with _w_col2:
            st.markdown("#### B. 销售本周怎么跟")
            _sales_sugg = list_suggestions(suggestion_type="weekly_sales_suggestion", limit=3)
            if not _sales_sugg:
                st.info("暂无销售建议，点击上方生成按钮。")
            for _ss in _sales_sugg:
                _sc = str(_ss.get("created_at",""))[:10]
                with st.expander(f"{_ss.get('title','')} ({_sc})", expanded=(_ss == _sales_sugg[0])):
                    _sb = _ss.get("data_basis") or {}
                    _sfc = _sb.get("facts_count", 0)
                    if _sfc:
                        st.caption(f"📎 生成时已确认事实：{_sfc} 条")
                    else:
                        st.caption("⚠️ 临时参考模式，无已确认事实")
                    st.markdown(_ss.get("content",""))

        with _w_col3:
            st.markdown("#### C. 产品/学管本周补什么")
            # 显示资源紧张学科和学管需补充方向
            _tight_caps = [c for c in _capacities_all if c.get("capacity_status") in ("紧张","暂停接单")]
            if _tight_caps:
                st.warning(f"⚠️ 以下学科资源紧张，需补充老师：")
                for _tc in _tight_caps[:5]:
                    st.caption(f"• {_tc.get('subject_area')} {_tc.get('course_type')}（{_tc.get('country','')}）— {_tc.get('capacity_status')}")
            else:
                st.success("✅ 当前各学科资源充足")

            st.markdown("**今日有效提醒**")
            _reminder_sugg = list_suggestions(suggestion_type="daily_reminder", limit=1)
            if _reminder_sugg:
                _latest_reminder = _reminder_sugg[0].get("content","")
                st.text(_latest_reminder[:400] + ("..." if len(_latest_reminder) > 400 else ""))
            else:
                st.caption("暂无今日提醒。前往「产品推广策略台」→「每日有效提醒」生成。")
                import datetime as _dt3
                _today3 = _dt3.date.today().strftime("%Y-%m-%d")
                import yaml as _yaml_r
                with open(ROOT / "config.yaml") as _f_r:
                    _cfg_r = _yaml_r.safe_load(_f_r)
                if st.button("🔔 生成今日提醒", key="gen_reminder_weekly"):
                    with st.spinner("生成今日提醒中..."):
                        try:
                            from agents.daily_effective_reminder_agent import DailyEffectiveReminderAgent
                            _da_agent = DailyEffectiveReminderAgent(_cfg_r)
                            _dr = _da_agent.generate(target_date=_today3)
                            st.success("✅ 提醒生成完成")
                            st.rerun()
                        except Exception as _re:
                            st.error(f"失败：{_re}")

    # ══════════════════════════════════════════════
    # Tab 3：部门动作
    # ══════════════════════════════════════════════
    with _tab_dept:
        st.subheader("🏢 本周各部门动作")

        _dept_names = ["市场部", "销售部", "产品部", "学管部", "管理层"]
        _dept_icons = {"市场部": "📣", "销售部": "💼", "产品部": "📦", "学管部": "👩‍🏫", "管理层": "🏆"}
        _dept_actions_map = {
            _da.get("department", ""): _da.get("actions", [])
            for _da in _supply_data.get("department_actions", [])
        }

        # 市场部 + 销售部 并排
        _dc1, _dc2 = st.columns(2)
        for _dept, _col in [("市场部", _dc1), ("销售部", _dc2)]:
            with _col:
                with st.container(border=True):
                    st.markdown(f"#### {_dept_icons.get(_dept,'')} {_dept}")
                    _actions = _dept_actions_map.get(_dept, [])
                    if _actions:
                        for _act in _actions:
                            st.markdown(f"- {_act}")
                    else:
                        st.caption("暂无动作建议，请先运行供给分析。")

        # 产品部（重点展示）
        with st.container(border=True):
            st.markdown("#### 📦 产品部（核心：推广边界 + 老师储备 + 订单风险）")
            _p_c1, _p_c2, _p_c3, _p_c4 = st.columns(4)

            # 订单分布
            with _p_c1:
                st.markdown("**订单分布**")
                _od = _supply_data.get("order_distribution", [])
                if _od:
                    for _item in _od[:4]:
                        st.caption(f"• {_item.get('product','')}：{_item.get('volume',0)}单")
                else:
                    st.caption("暂无数据")

            # 老师储备
            with _p_c2:
                st.markdown("**老师储备**")
                _cap_analysis = _supply_data.get("teacher_capacity_analysis", [])
                if _cap_analysis:
                    for _cap in _cap_analysis[:5]:
                        _status_icon = {"充足":"🟢","正常":"🔵","紧张":"🟡","暂停接单":"🔴"}.get(_cap.get("capacity_status",""), "⚪")
                        st.caption(f"{_status_icon} {_cap.get('subject_area','')} {_cap.get('course_type','')}")
                else:
                    st.caption("暂无老师储备数据")

            # 订单风险
            with _p_c3:
                st.markdown("**订单风险**")
                _stage_risks = _supply_data.get("stage_order_risks", [])
                if _stage_risks:
                    _RISK_ICON = {"critical":"🔴","high":"🟠","medium":"🟡","low":"🟢"}
                    for _r in _stage_risks[:4]:
                        _ri = _RISK_ICON.get(_r.get("risk_level",""), "⚪")
                        st.caption(f"{_ri} {_r.get('risk_type','')}（{_r.get('related_product','')}）")
                else:
                    st.caption("暂无风险信号")

            # 推广边界
            with _p_c4:
                st.markdown("**推广边界**")
                if _promotion_boundary:
                    for _pb in _promotion_boundary[:5]:
                        _pl = _pb.get("push_level","normal")
                        _pi = {"strong":"🟢","normal":"🔵","cautious":"🟡","pause":"🔴"}.get(_pl,"⚪")
                        st.caption(f"{_pi} {_pb.get('product','')[:10]}")
                else:
                    st.caption("暂无推广边界数据")

            # 产品部建议动作
            _pd_actions = _dept_actions_map.get("产品部", _dept_actions_map.get("管理层", []))
            if _pd_actions:
                st.markdown("**本周建议动作：**")
                for _act in _pd_actions:
                    st.markdown(f"- {_act}")

        # 学管部 + 管理层 并排
        _dc3, _dc4 = st.columns(2)
        for _dept2, _col2 in [("学管部", _dc3), ("管理层", _dc4)]:
            with _col2:
                with st.container(border=True):
                    st.markdown(f"#### {_dept_icons.get(_dept2,'')} {_dept2}")
                    _actions2 = _dept_actions_map.get(_dept2, [])
                    if _dept2 == "学管部" and not _actions2:
                        _actions2 = [
                            "反馈本周各学科老师可接单数量",
                            "标记高风险订单（DDL 48小时内、计算类复杂考试）",
                            "更新不可承诺话术清单",
                        ]
                    if _actions2:
                        for _act2 in _actions2:
                            st.markdown(f"- {_act2}")
                    else:
                        st.caption("暂无动作建议。")

    # ══════════════════════════════════════════════
    # Tab 4：可用素材
    # ══════════════════════════════════════════════
    with _tab_materials:
        st.subheader("📦 可用素材库")
        st.caption("展示已通过审核（approved）和待审核（pending_review）的内容素材，按渠道分类。")

        # 读取内容
        _approved_contents  = list_contents(status="approved",       limit=100)
        _pending_contents   = list_contents(status="pending_review", limit=50)
        _all_display        = _approved_contents + _pending_contents

        if not _all_display:
            st.info("暂无可用素材。请先生成推广内容，或审核通过现有草稿。")
        else:
            # 状态图标
            _STATUS_BADGE = {"approved":"🟢 已通过","pending_review":"🟡 待审核","draft":"🔵 草稿"}
            # 渠道分类
            _CHANNEL_TABS = {
                "xiaohongshu": "📕 小红书",
                "moments":     "🌟 朋友圈",
                "group_msg":   "💬 社群话术",
                "sales_script":"💼 销售私聊",
                "referral_script":"🤝 转介绍",
                "poster":      "🎨 海报",
                "monthly_plan":"📅 月度计划",
                "weekly_plan": "📆 周计划",
            }
            # 按 content_type 分组
            _grouped: dict = {}
            for _ct in _all_display:
                _ct_type = _ct.get("content_type", "other")
                _grouped.setdefault(_ct_type, []).append(_ct)

            _channel_keys = [k for k in _CHANNEL_TABS.keys() if k in _grouped]
            _other_keys   = [k for k in _grouped.keys() if k not in _CHANNEL_TABS]
            _tab_keys     = _channel_keys + _other_keys

            if _tab_keys:
                _material_tabs = st.tabs([_CHANNEL_TABS.get(k, k) for k in _tab_keys])
                for _ti, _tkey in enumerate(_tab_keys):
                    with _material_tabs[_ti]:
                        _items = _grouped.get(_tkey, [])
                        st.caption(f"共 {len(_items)} 条")
                        for _item in _items[:20]:
                            _st_badge = _STATUS_BADGE.get(_item.get("status",""), "⚪ 未知")
                            _risk_notes = _item.get("risk_notes") or []
                            _risk_hint  = "⚠️ " + " | ".join(_risk_notes[:2]) if _risk_notes else ""

                            with st.expander(
                                f"{_st_badge}  {_item.get('title','（无标题）')[:45]}",
                                expanded=False,
                            ):
                                _mc1_mat, _mc2_mat = st.columns([3, 1])
                                with _mc1_mat:
                                    _body = _item.get("body","")
                                    st.text(_body[:400] + ("..." if len(_body) > 400 else ""))
                                    if _risk_hint:
                                        st.warning(_risk_hint)
                                with _mc2_mat:
                                    st.caption(f"产品：{_item.get('product_id','') or '—'}")
                                    st.caption(f"学校：{_item.get('school_name','') or '全部'}")
                                    st.caption(f"创建：{str(_item.get('created_at',''))[:10]}")
                                    # 复制按钮
                                    if st.button("📋 复制", key=f"copy_mat_{_item['id']}"):
                                        st.code(_body[:800])
                                        st.caption("请手动选中上方文本复制")


# ══════════════════════════════════════════════
# 页面 1：公司增长看板
# ══════════════════════════════════════════════
elif page == "📊 公司增长看板":
    # ── 数据加载 ────────────────────────────
    _dash_stats   = get_dashboard_stats()
    _task_stats   = get_task_stats()
    _order_stats7 = get_order_stats(days=7)
    _order_stats30= get_order_stats(days=30)
    _lead_stats7  = get_lead_stats(days=7)
    _lead_stats30 = get_lead_stats(days=30)

    _has_real_orders = (_order_stats30.get("total", 0) > 0)
    _has_real_leads  = (_lead_stats30.get("total", 0) > 0)
    _data_status = (
        f"近30天真实订单 {_order_stats30.get('total', 0)} 单 · "
        f"咨询线索 {_lead_stats30.get('total', 0)} 条 · "
        f"待审核内容 {_dash_stats.get('pending', 0)} 条"
    ) if (_has_real_orders or _has_real_leads) else "⚠️ 当前为演示数据，上传真实订单和咨询后数据将自动更新"

    # ── Hero ────────────────────────────────
    render_hero(
        "📊 公司增长看板",
        "查看当前市场机会、主推产品、内容进展和部门执行情况，掌握全局。",
        _data_status,
    )

    # ── Hero 主操作按钮 ──────────────────────
    _hb1, _hb2, _hb3, _hb_spacer = st.columns([1, 1, 1, 3])
    if _hb1.button("📋 生成今日简报", use_container_width=True):
        st.session_state["_run_brief"] = True
    if _hb2.button("📡 更新市场信号", use_container_width=True):
        st.session_state["_run_signals"] = True
    if _hb3.button("📈 查看本周推广建议", use_container_width=True):
        st.session_state["page_override"] = "📈 产品推广策略台"

    if st.session_state.get("_run_brief"):
        del st.session_state["_run_brief"]
        with st.spinner("正在生成今日简报..."):
            import subprocess, os
            r = subprocess.run(
                ["uv", "run", "--with", "anthropic", "python", "main.py", "daily-brief"],
                cwd=str(ROOT), capture_output=True, text=True, env={**os.environ}
            )
        if r.returncode == 0:
            st.success("✅ 今日简报已生成，请查看推送")
        else:
            st.error(f"生成失败：{r.stderr[:200]}")

    if st.session_state.get("_run_signals"):
        del st.session_state["_run_signals"]
        with st.spinner("正在更新市场信号（约20秒）..."):
            import subprocess, os
            r = subprocess.run(
                ["uv", "run", "--with", "anthropic", "python", "main.py", "update-market-signals"],
                cwd=str(ROOT), capture_output=True, text=True, env={**os.environ}
            )
        if r.returncode == 0:
            st.success("✅ 市场信号已更新")
            st.rerun()
        else:
            st.error(f"更新失败：{r.stderr[:200]}")

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── 核心指标卡（5个）───────────────────────
    _mc = st.columns(5)
    render_metric(_mc[0], _lead_stats7.get("total", 0),   "近7天咨询",   "条新咨询",   "#3b82f6")
    render_metric(_mc[1], _order_stats7.get("total", 0),  "近7天成交",   "单订单",     "#10b981")
    render_metric(_mc[2], _dash_stats.get("pending", 0),   "待审核内容",   "条草稿待审","#f59e0b")
    render_metric(_mc[3], _task_stats.get("todo", 0),      "待执行任务",   "条任务",    "#6366f1")
    render_metric(_mc[4], _dash_stats.get("high_feedback",0), "高危反馈",  "需立即处理","#ef4444")

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    # ── 三栏主体 ─────────────────────────────
    _col_l, _col_m, _col_r = st.columns([5, 4, 3])

    with _col_l:
        # 本周重点
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🎯 本周重点关注</div>', unsafe_allow_html=True)

        _weekly_sg = list_suggestions(suggestion_type="weekly_sales_suggestion", limit=1)
        if _weekly_sg:
            _ws = _weekly_sg[0]
            _ws_preview = (_ws.get("content") or "")[:400]
            st.markdown(f"**{_ws.get('title','')}**")
            st.markdown(_ws_preview + ("..." if len(_ws.get("content","")) > 400 else ""))
            with st.expander("查看完整本周销售建议"):
                st.markdown(_ws.get("content",""))
        else:
            render_empty_state(
                "暂无本周销售建议",
                "前往「产品推广策略台」生成本周推广建议，系统将自动分析销售重点。",
            )

        st.markdown('</div>', unsafe_allow_html=True)

        # 待审核内容快速通道
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">⏳ 待审核内容（快速通过）</div>', unsafe_allow_html=True)
        _pending = list_contents(status="pending_review", limit=5)
        if not _pending:
            st.markdown('<div class="muted">暂无待审核内容 ✅</div>', unsafe_allow_html=True)
        for _item in _pending:
            _tl = TYPE_ZH.get(_item["content_type"], _item["content_type"])
            _pl = PRODUCT_ZH.get(_item.get("product_id",""), "-")
            _c1, _c2, _c3 = st.columns([4, 2, 1])
            _c1.markdown(f"**{(_item['title'] or '无标题')[:28]}**")
            _c1.caption(f"{_tl} · {_pl}")
            _c2.markdown(f'<span class="badge badge-pending">待审核</span>', unsafe_allow_html=True)
            if _c3.button("通过", key=f"qk_{_item['id']}"):
                update_content_status(_item["id"], "approved")
                st.rerun()
            st.divider()
        st.markdown('</div>', unsafe_allow_html=True)

    with _col_m:
        # 高优反馈
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔴 需要立即处理</div>', unsafe_allow_html=True)
        _fbs = list_feedbacks(status="open")
        _high_fbs = [f for f in _fbs if f.get("urgency") in ("高","紧急")]
        if not _high_fbs:
            st.markdown('<div style="color:#10b981;padding:8px 0">✅ 当前暂无高危反馈，运营状态良好</div>', unsafe_allow_html=True)
        for _fb in _high_fbs[:4]:
            _u_icon = "🔴" if _fb.get("urgency") == "紧急" else "🟠"
            st.markdown(f"""
            <div class="risk-card">
              <div class="risk-title">{_u_icon} {_fb.get('title','')}</div>
              <div class="risk-desc">{_fb.get('department','')} · {_fb.get('feedback_type','')} · {str(_fb.get('created_at',''))[:10]}</div>
              <div class="risk-desc" style="margin-top:4px">{(_fb.get('content') or '')[:80]}</div>
            </div>""", unsafe_allow_html=True)
            if st.button("标记处理中", key=f"fb_dash_{_fb['id']}", use_container_width=True):
                update_feedback_status(_fb["id"], "in_progress")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # 高优建议
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">💡 待采纳的高优建议</div>', unsafe_allow_html=True)
        _sgs = list_suggestions(status="new")
        _high_sgs = [s for s in _sgs if s.get("priority") in ("高","紧急")][:3]
        if not _high_sgs:
            st.markdown('<div class="muted">暂无高优建议</div>', unsafe_allow_html=True)
        for _sg in _high_sgs:
            _p_color = "#ef4444" if _sg.get("priority") == "紧急" else "#f97316"
            st.markdown(f"""
            <div class="suggestion-row" style="border-left-color:{_p_color}">
              <strong>{_sg.get('title','')}</strong><br>
              <span class="muted">{_sg.get('suggestion_type','')} · {_sg.get('source','')}</span><br>
              <span style="font-size:13px;color:#374151">{(_sg.get('recommendation') or '')[:80]}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with _col_r:
        # 下一步建议
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">✅ 今天你应该做</div>', unsafe_allow_html=True)

        _todo_actions = []
        if _dash_stats.get("pending", 0) > 0:
            _todo_actions.append(f"📝 审核 {_dash_stats['pending']} 条待审核内容")
        if _high_fbs:
            _todo_actions.append(f"🔴 处理 {len(_high_fbs)} 条高危反馈")
        if not _weekly_sg if '_weekly_sg' in dir() else True:
            _todo_actions.append("📈 生成本周推广建议")
        if _task_stats.get("todo", 0) > 0:
            _todo_actions.append(f"✅ 跟进 {_task_stats['todo']} 条待执行任务")
        if not _has_real_orders:
            _todo_actions.append("📂 上传真实订单数据")
        if not _todo_actions:
            _todo_actions = ["🎉 当前无紧急待办事项"]

        for _i, _act in enumerate(_todo_actions[:5], 1):
            st.markdown(f"""
            <div class="step-item">
              <div class="step-num">{_i}</div>
              <div class="step-text">{_act}</div>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 快速跳转
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔗 快速跳转</div>', unsafe_allow_html=True)
        st.caption("👉 前往【📈 产品推广策略台】生成本周建议")
        st.caption("👉 前往【📝 内容池】审核和管理素材")
        st.caption("👉 前往【✅ 部门任务台】查看执行任务")
        st.caption("👉 前往【📁 资料上传中心】导入数据")
        st.markdown('</div>', unsafe_allow_html=True)

        # 内容分布小图
        _by_type = _dash_stats.get("by_type", {})
        if _by_type:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">📊 内容类型分布</div>', unsafe_allow_html=True)
            _chart_data = {TYPE_ZH.get(k, k): v for k, v in _by_type.items() if v > 0}
            st.bar_chart(_chart_data, height=160)
            st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 页面 2：营销日历
# ══════════════════════════════════════════════
elif page == "📅 营销日历":
    st.title("📅 营销日历")

    # 筛选
    f1, f2, f3 = st.columns(3)
    filter_country = f1.selectbox("国家", ["全部", "UK", "Australia"])
    filter_status  = f2.selectbox("状态", ["全部", "active", "completed", "archived"])
    f3.write("")

    campaigns = list_campaigns(limit=50)
    if filter_country != "全部":
        campaigns = [c for c in campaigns if (c.get("target_country") or "") == filter_country]
    if filter_status != "全部":
        campaigns = [c for c in campaigns if c.get("status") == filter_status]

    if not campaigns:
        st.info("暂无营销活动。运行 `python main.py monthly` 生成月度计划。")
    else:
        for camp in campaigns:
            status_badge = {"active":"🟢 进行中","completed":"✅ 已完成","archived":"⚫ 已归档"}.get(camp.get("status",""), camp.get("status",""))
            with st.expander(f"**{camp['name']}** · {status_badge} · {(camp.get('created_at') or '')[:10]}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("核心主题", camp.get("core_theme") or "-")
                c2.metric("推广开始", (camp.get("period_start") or "")[:10] or "-")
                c3.metric("推广结束", (camp.get("period_end") or "")[:10] or "-")
                c4.metric("创建日期", (camp.get("created_at") or "")[:10])

                # 关联内容
                related = list_contents(limit=30)
                related = [c for c in related if c.get("campaign_id") == camp["id"]]
                if related:
                    st.caption(f"📎 关联内容 {len(related)} 条")
                    rows = []
                    for r in related:
                        rows.append({
                            "类型": TYPE_ZH.get(r["content_type"], r["content_type"]),
                            "标题": r["title"] or "-",
                            "状态": STATUS_ZH.get(r["status"], r["status"]),
                            "产品": PRODUCT_ZH.get(r.get("product_id",""), r.get("product_id","") or "-"),
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# 页面 3：内容池
# ══════════════════════════════════════════════
elif page == "📝 内容池":
    # ── 数据 ────────────────────────────────
    _all_contents = list_contents(limit=500)
    _cnt_draft    = sum(1 for c in _all_contents if c["status"] == "draft")
    _cnt_pending  = sum(1 for c in _all_contents if c["status"] == "pending_review")
    _cnt_approved = sum(1 for c in _all_contents if c["status"] == "approved")
    _cnt_used     = sum(1 for c in _all_contents if c["status"] == "used")

    # ── Hero ────────────────────────────────
    render_hero(
        "📝 内容池",
        "管理所有 AI 生成的小红书、朋友圈、社群话术、销售话术和海报文案。审核通过后销售可直接使用。",
        f"共 {len(_all_contents)} 条内容 · 待审核 {_cnt_pending} 条 · 已通过 {_cnt_approved} 条",
    )

    # ── Hero 操作 ───────────────────────────
    _cb1, _cb2, _cb3, _cb4, _cb_sp = st.columns([1.2, 1.2, 1.2, 1.2, 2])
    _filter_pending = _cb2.button("⏳ 查看待审核", use_container_width=True,
                                   type="primary" if _cnt_pending > 0 else "secondary")
    _filter_approved = _cb3.button("✅ 查看可用素材", use_container_width=True)
    _show_all = _cb1.button("📋 查看全部内容", use_container_width=True)
    if _cb4.button("🔄 刷新列表", use_container_width=True):
        st.rerun()

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── 状态指标卡 ──────────────────────────
    _sc = st.columns(5)
    render_metric(_sc[0], len(_all_contents), "内容总数",  "", "#3b82f6")
    render_metric(_sc[1], _cnt_draft,         "草稿",     "待提交审核", "#94a3b8")
    render_metric(_sc[2], _cnt_pending,       "待审核",   "需要你处理", "#f59e0b")
    render_metric(_sc[3], _cnt_approved,      "已通过",   "可发给销售", "#10b981")
    render_metric(_sc[4], _cnt_used,          "已使用",   "已发布/发出", "#8b5cf6")

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    # ── 筛选条件 ────────────────────────────
    _default_status = ("pending_review" if _filter_pending
                       else "approved" if _filter_approved
                       else "全部")
    _fc1, _fc2, _fc3 = st.columns(3)
    _fs = _fc1.selectbox("内容状态", ["全部"] + list(STATUS_ZH.keys()),
                         index=(["全部"] + list(STATUS_ZH.keys())).index(_default_status) if _default_status != "全部" else 0,
                         format_func=lambda x: "全部" if x=="全部" else STATUS_ZH.get(x,x))
    _ft = _fc2.selectbox("内容类型", ["全部"] + list(TYPE_ZH.keys()),
                         format_func=lambda x: "全部" if x=="全部" else TYPE_ZH.get(x,x))
    _fp = _fc3.selectbox("产品", ["全部"] + list(PRODUCT_ZH.keys()),
                         format_func=lambda x: "全部" if x=="全部" else PRODUCT_ZH.get(x,x))

    _contents = list_contents(
        status       = None if _fs == "全部" else _fs,
        content_type = None if _ft == "全部" else _ft,
        product_id   = None if _fp == "全部" else _fp,
        limit=300,
    )
    st.caption(f"筛选结果：**{len(_contents)}** 条内容")

    if not _contents:
        render_empty_state(
            "当前没有内容",
            "请先前往「产品推广策略台」生成本周推广建议，或使用「创建推广活动」功能生成素材包。内容生成后会出现在这里等待审核。",
            "去产品推广策略台",
            "📈 产品推广策略台",
        )
    else:
        for _item in _contents:
            _tl  = TYPE_ZH.get(_item["content_type"], _item["content_type"])
            _pl  = PRODUCT_ZH.get(_item.get("product_id",""), _item.get("product_id","") or "-")
            _st  = _item["status"]
            _stl = STATUS_ZH.get(_st, _st)
            _badge_cls = {"draft":"badge-draft","pending_review":"badge-pending",
                          "approved":"badge-approved","used":"badge-used",
                          "archived":"badge-archived","rejected":"badge-rejected"}.get(_st,"badge-draft")

            with st.expander(
                f"{_tl} · {(_item['title'] or '无标题')[:35]} · {_stl}",
                expanded=(_st == "pending_review"),
            ):
                # ── 元信息行 ──
                _mi = st.columns(5)
                _mi[0].markdown(f'<span class="badge {_badge_cls}">{_stl}</span>', unsafe_allow_html=True)
                _mi[1].caption(f"**产品** {_pl}")
                _mi[2].caption(f"**渠道** {_item.get('channel') or '-'}")
                _mi[3].caption(f"**学校** {_item.get('school_name') or '-'}")
                _mi[4].caption(f"**创建** {(_item.get('created_at') or '')[:10]}")

                # ── 封面文案 ──
                if _item.get("cover_text"):
                    st.info(f"📌 封面文案：{_item['cover_text']}")

                # ── 可复制正文 ──
                _body = _item.get("body","")
                _copy_parts = []
                if _item.get("title"):   _copy_parts.append(_item["title"])
                if _body:                _copy_parts.append(_body)
                if _item.get("hashtags"):
                    _copy_parts.append(" ".join([f"#{t}" for t in _item["hashtags"]]))
                if _item.get("call_to_action"):
                    _copy_parts.append(_item["call_to_action"])
                _copy_text = "\n\n".join(_copy_parts)
                st.code(_copy_text, language=None)
                st.caption("☝️ 点击右上角复制图标复制全文，可直接粘贴发送")

                if _item.get("hashtags"):
                    st.caption("🏷️ " + "  ".join([f"#{t}" for t in _item["hashtags"]]))

                # ── 风险/备注 ──
                if _item.get("risk_notes"):
                    st.warning("⚠️ 风险提示：" + " / ".join(_item["risk_notes"]))
                if _item.get("review_comment"):
                    st.error(f"💬 审核意见：{_item['review_comment']}")
                if _item.get("suggested_use"):
                    st.caption(f"💡 使用建议：{_item['suggested_use']}")

                st.divider()

                # ── 操作按钮 ──
                _ops = st.columns(6)
                if _st == "draft":
                    if _ops[0].button("📤 提交审核", key=f"sub_{_item['id']}", type="primary"):
                        update_content_status(_item["id"], "pending_review")
                        st.rerun()

                if _st == "pending_review":
                    if _ops[0].button("✅ 审核通过", key=f"app_{_item['id']}", type="primary"):
                        update_content_status(_item["id"], "approved")
                        st.rerun()
                    _rej_r = _ops[1].text_input("退回原因", key=f"rej_r_{_item['id']}", placeholder="输入原因")
                    if _ops[1].button("🔙 退回修改", key=f"rej_{_item['id']}"):
                        update_content_status(_item["id"], "rejected", comment=_rej_r or "退回修改")
                        st.rerun()

                if _st == "approved":
                    if _ops[0].button("🎯 标记已使用", key=f"use_{_item['id']}", type="primary"):
                        update_content_status(_item["id"], "used", used_by="销售/运营")
                        st.rerun()

                if _st == "used":
                    if _ops[0].button("📋 标记已复盘", key=f"rev_{_item['id']}"):
                        update_content_status(_item["id"], "reviewed")
                        st.rerun()

                if _st not in ("archived",):
                    if _ops[5].button("🗑️ 废弃", key=f"arc_{_item['id']}"):
                        update_content_status(_item["id"], "archived")
                        st.rerun()


# ══════════════════════════════════════════════
# 页面 4：销售作战台
# ══════════════════════════════════════════════
elif page == "💼 销售作战台":
    # ── 数据 ────────────────────────────────
    _approved_all = list_contents(status="approved", limit=200)
    _used_all     = list_contents(status="used", limit=100)
    _sales_sug    = list_suggestions(suggestion_type="weekly_sales_suggestion", limit=1)
    _daily_rem    = list_suggestions(suggestion_type="daily_reminder", limit=1)

    _total_usable = len(_approved_all) + len(_used_all)

    # ── Hero ────────────────────────────────
    render_hero(
        "💼 销售作战台",
        "查看本周主推产品、复制销售话术、记录客户反馈。所有内容均已审核，可直接发给客户使用。",
        f"可用素材 {len(_approved_all)} 条 · 已使用 {len(_used_all)} 条 · 本周销售建议{'已生成' if _sales_sug else '未生成'}",
    )

    _sb1, _sb2, _sb3, _sb_sp = st.columns([1.2, 1.2, 1.2, 3])
    if _sb1.button("📋 查看本周销售建议", type="primary", use_container_width=True):
        st.session_state["sales_show_weekly"] = True
    if _sb2.button("📊 提交客户反馈", use_container_width=True):
        st.session_state["sales_show_feedback"] = True
    if _sb3.button("🔄 刷新素材", use_container_width=True):
        st.rerun()

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── 本周销售重点 ─────────────────────────
    if _sales_sug or st.session_state.get("sales_show_weekly"):
        if st.session_state.get("sales_show_weekly"):
            del st.session_state["sales_show_weekly"]

        if _sales_sug:
            _ws = _sales_sug[0]
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🎯 本周销售重点</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="muted">{_ws.get("title","")} · 生成时间 {str(_ws.get("created_at",""))[:10]}</div>', unsafe_allow_html=True)
            with st.expander("展开查看完整本周销售建议", expanded=True):
                st.markdown(_ws.get("content",""))
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            render_empty_state(
                "本周销售建议尚未生成",
                "前往「产品推广策略台」→「周度推广建议」→ 点击「生成本周销售建议」，约20秒即可生成。",
                "去生成本周销售建议", "📈 产品推广策略台",
            )

    # ── 今日提醒 ────────────────────────────
    if _daily_rem:
        _dr = _daily_rem[0]
        st.info(f"🔔 **{_dr.get('title','')}**\n\n{_dr.get('content','')[:300]}")

    # ── 产品筛选 ─────────────────────────────
    st.markdown("---")
    _sa_col1, _sa_col2 = st.columns([2, 4])
    _sel_product = _sa_col1.selectbox(
        "按产品筛选",
        ["全部"] + list(PRODUCT_ZH.keys()),
        format_func=lambda x: "全部" if x=="全部" else PRODUCT_ZH.get(x,x),
        key="sa_product_filter",
    )

    if not _total_usable:
        render_empty_state(
            "当前暂无可用话术素材",
            "素材需要先生成再经过审核才会出现在这里。\n请前往「产品推广策略台」生成本周推广建议，或在「内容池」审核通过已有草稿。",
            "去内容池审核素材", "📝 内容池",
        )
    else:
        # ── 渠道 Tab ─────────────────────────
        _ch_tabs = st.tabs(["💼 销售话术", "📱 小红书", "🌅 朋友圈", "💬 社群话术", "🔄 转介绍", "📢 全部素材"])
        _CH_FILTERS = [
            ("sales_script",    "销售话术"),
            ("xiaohongshu",     "小红书"),
            ("moments",         "朋友圈"),
            ("group_msg",       "社群话术"),
            ("referral_script", "转介绍"),
            (None,              "全部素材"),
        ]

        for _tab, (_ctype, _tab_label) in zip(_ch_tabs, _CH_FILTERS):
            with _tab:
                _items = list_contents(
                    content_type=_ctype,
                    product_id=None if _sel_product=="全部" else _sel_product,
                    limit=200,
                )
                _items = [i for i in _items if i["status"] in ("approved","used")]

                if not _items:
                    st.markdown(f'<div class="empty-card"><div class="empty-card-title">📭 暂无{_tab_label}素材</div><div class="empty-card-desc">先在「内容池」生成并审核该类型内容。</div></div>', unsafe_allow_html=True)
                    continue

                for _item in _items:
                    _pl  = PRODUCT_ZH.get(_item.get("product_id",""), "-")
                    _tl  = TYPE_ZH.get(_item["content_type"], _item["content_type"])
                    _body = _item.get("body","")

                    # 构造可复制全文
                    _cp = []
                    if _item.get("title"):   _cp.append(_item["title"])
                    if _body:                _cp.append(_body)
                    if _item.get("hashtags"):
                        _cp.append(" ".join([f"#{t}" for t in _item["hashtags"]]))
                    if _item.get("call_to_action"): _cp.append(_item["call_to_action"])
                    _copy_full = "\n\n".join(_cp)

                    with st.expander(
                        f"{'✅' if _item['status']=='approved' else '🎯'} {_item['title'] or '无标题'}  ·  {_pl}",
                        expanded=False,
                    ):
                        if _item.get("cover_text"):
                            st.info(f"📌 封面：{_item['cover_text']}")
                        if _item.get("suggested_use"):
                            st.caption(f"💡 使用场景：{_item['suggested_use']}")

                        # 正文卡片样式
                        st.markdown(f"""
                        <div class="script-card">
                          <span class="script-product">{_pl}</span>
                          <div class="script-title">{_item.get('title','')}</div>
                          <div class="script-body">{_body[:500]}</div>
                        </div>""", unsafe_allow_html=True)

                        if _item.get("hashtags"):
                            st.caption("🏷️ " + "  ".join([f"#{t}" for t in _item["hashtags"]]))

                        # 复制区
                        st.code(_copy_full, language=None)
                        st.caption("☝️ 点击右上角复制图标，可直接粘贴发送")

                        _oa, _ob, _oc = st.columns(3)
                        if _item["status"] == "approved":
                            if _oa.button("🎯 标记已使用", key=f"suse_{_item['id']}", type="primary"):
                                update_content_status(_item["id"], "used", used_by="销售")
                                st.rerun()

                        # 简化使用记录
                        with st.expander("📊 记录使用效果（选填）"):
                            with st.form(key=f"sf_{_item['id']}"):
                                _sfc1, _sfc2 = st.columns(2)
                                _u_ch  = _sfc1.selectbox("使用渠道", ["私聊","朋友圈","小红书","社群","转介绍"], key=f"sch_{_item['id']}")
                                _u_res = _sfc2.selectbox("客户反应", ["已发送","客户回复","产生咨询","已报价","已成交","无效","需优化"], key=f"sres_{_item['id']}")
                                _u_nm  = st.text_input("你的名字（可选）", key=f"snm_{_item['id']}")
                                _u_fb  = st.text_input("反馈备注（可选）", key=f"sfb_{_item['id']}")
                                if st.form_submit_button("✅ 提交反馈", type="primary"):
                                    save_content_usage({
                                        "content_id":     _item["id"],
                                        "used_by":        _u_nm or "销售",
                                        "department":     "销售部",
                                        "channel":        _u_ch,
                                        "customer_stage": "跟进中",
                                        "result":         _u_res,
                                        "feedback":       _u_fb,
                                    })
                                    st.success("✅ 反馈已记录！")
                                    st.rerun()

                        _usages = list_content_usages(content_id=_item["id"])
                        if _usages:
                            st.caption(f"📈 已使用 {len(_usages)} 次")
                            for _u in _usages[:2]:
                                _ri = {"已成交":"🏆","产生咨询":"✅","客户回复":"💬","无效":"❌"}.get(_u.get("result",""),"📌")
                                st.caption(f"  {_ri} {_u.get('result','')} · {_u.get('channel','')} · {_u.get('used_by','')} · {str(_u.get('created_at',''))[:10]}")

    # ── 客户反馈提交表单 ─────────────────────
    st.markdown("---")
    with st.expander("📝 提交客户反馈（让 AI 更了解客户痛点）",
                     expanded=st.session_state.get("sales_show_feedback", False)):
        if st.session_state.get("sales_show_feedback"):
            del st.session_state["sales_show_feedback"]
        with st.form("sales_feedback_form"):
            _ff1, _ff2, _ff3 = st.columns(3)
            _fb_name    = _ff1.text_input("销售姓名", placeholder="你的名字")
            _fb_school  = _ff2.text_input("客户学校", placeholder="UCL / KCL / 墨大...")
            _fb_stage   = _ff3.selectbox("客户阶段", ["初次接触","已报价","已成交","流失","犹豫中"])
            _ff4, _ff5  = st.columns(2)
            _fb_product = _ff4.selectbox("咨询产品", list(PRODUCT_ZH.keys()),
                                          format_func=lambda x: PRODUCT_ZH.get(x,x))
            _fb_result  = _ff5.selectbox("结果", ["成交","未成交","仍在跟进"])
            _fb_content = st.text_area("客户反馈内容", placeholder="客户说了什么？主要异议是什么？哪些话术有效？",
                                       height=80)
            _fb_reason  = st.text_input("未成交主要原因（如未成交）", placeholder="价格/时间/产品不匹配...")
            if st.form_submit_button("📤 提交客户反馈", type="primary"):
                if _fb_content.strip():
                    save_feedback({
                        "title":         f"{_fb_name or '销售'} · {_fb_school or '未知学校'} · {_fb_product}",
                        "department":    "销售部",
                        "feedback_type": "销售异议",
                        "content":       _fb_content + (f"\n未成交原因：{_fb_reason}" if _fb_reason else ""),
                        "urgency":       "中",
                        "source":        _fb_name or "销售",
                        "related_product": _fb_product,
                        "related_school":  _fb_school,
                    })
                    st.success("✅ 反馈已提交！AI 将基于此优化销售建议。")
                    st.rerun()
                else:
                    st.error("请填写客户反馈内容")


# ══════════════════════════════════════════════
# 页面 5：产品反馈台
# ══════════════════════════════════════════════
elif page == "🗣️ 产品反馈台":
    st.title("🗣️ 产品反馈台")
    st.caption("产品部 / 学管部 / 销售部 提交业务反馈，驱动产品优化和战略调整")

    # ── 新增反馈表单 ──
    with st.expander("➕ 新增反馈", expanded=False):
        with st.form("feedback_form"):
            fc1, fc2 = st.columns(2)
            dept      = fc1.selectbox("所属部门", DEPT_OPTIONS)
            fb_type   = fc2.selectbox("反馈类型", FEEDBACK_TYPES)
            fc3, fc4  = st.columns(2)
            rel_prod  = fc3.selectbox("相关产品（可选）",
                                      ["不限"] + list(PRODUCT_ZH.values()),
                                      format_func=lambda x: x)
            rel_school= fc4.text_input("相关学校（可选）", placeholder="如：UCL, 墨大")
            fb_title  = st.text_input("反馈标题 *", placeholder="一句话说清楚问题")
            fb_content= st.text_area("详细内容", height=100,
                                     placeholder="描述具体情况，越具体越有价值")
            fc5, fc6  = st.columns(2)
            urgency   = fc5.selectbox("紧急程度", URGENCY_OPTIONS, index=1)
            created_by= fc6.text_input("提交人", placeholder="你的名字/岗位")
            submitted = st.form_submit_button("📩 提交反馈", type="primary")

            if submitted:
                if not fb_title.strip():
                    st.error("请填写反馈标题")
                else:
                    save_feedback({
                        "department":      dept,
                        "feedback_type":   fb_type,
                        "related_product": rel_prod if rel_prod != "不限" else "",
                        "related_school":  rel_school,
                        "title":           fb_title.strip(),
                        "content":         fb_content.strip(),
                        "urgency":         urgency,
                        "created_by":      created_by.strip(),
                    })
                    st.success("✅ 反馈已提交！")
                    st.rerun()

    st.divider()

    # ── 筛选 ──
    ff1, ff2, ff3 = st.columns(3)
    filt_dept = ff1.selectbox("部门", ["全部"] + DEPT_OPTIONS)
    filt_urg  = ff2.selectbox("紧急度", ["全部"] + URGENCY_OPTIONS)
    filt_fbs  = ff3.selectbox("状态", ["全部", "open", "in_progress", "resolved", "closed"],
                              format_func=lambda x: "全部" if x=="全部" else FB_STATUS_ZH.get(x,x))

    feedbacks = list_feedbacks(
        department = None if filt_dept=="全部" else filt_dept,
        urgency    = None if filt_urg=="全部" else filt_urg,
        status     = None if filt_fbs=="全部" else filt_fbs,
    )

    st.caption(f"共 **{len(feedbacks)}** 条反馈")

    if not feedbacks:
        st.info("暂无反馈。点击上方「新增反馈」提交。")
    else:
        URGENCY_ICON = {"低":"⚪","中":"🟡","高":"🟠","紧急":"🔴"}
        for fb in feedbacks:
            icon = URGENCY_ICON.get(fb["urgency"], "⚪")
            status_label = FB_STATUS_ZH.get(fb["status"], fb["status"])
            with st.expander(f"{icon} **{fb['title']}** · {fb['department']} · `{status_label}`"):
                mc = st.columns(4)
                mc[0].caption(f"**类型**\n{fb['feedback_type']}")
                mc[1].caption(f"**产品**\n{fb.get('related_product') or '-'}")
                mc[2].caption(f"**学校**\n{fb.get('related_school') or '-'}")
                mc[3].caption(f"**提交人**\n{fb.get('created_by') or '-'}")

                if fb.get("content"):
                    st.markdown(fb["content"])

                st.caption(f"提交时间：{(fb.get('created_at') or '')[:16]}")
                st.divider()

                ops = st.columns(4)
                if fb["status"] == "open":
                    if ops[0].button("🔧 标记处理中", key=f"fb_ip_{fb['id']}"):
                        update_feedback_status(fb["id"], "in_progress")
                        st.rerun()
                if fb["status"] == "in_progress":
                    if ops[0].button("✅ 标记已解决", key=f"fb_res_{fb['id']}"):
                        update_feedback_status(fb["id"], "resolved")
                        st.rerun()
                if fb["status"] in ("resolved",):
                    if ops[1].button("🔒 关闭", key=f"fb_cl_{fb['id']}"):
                        update_feedback_status(fb["id"], "closed")
                        st.rerun()


# ══════════════════════════════════════════════
# 页面 6：战略建议台
# ══════════════════════════════════════════════
elif page == "🧭 战略建议台":
    st.title("🧭 战略建议台")
    st.caption("AI 自动生成 + 管理层人工录入的战略洞察与行动建议")

    # ── 新增建议 ──
    with st.expander("➕ 手动录入战略建议", expanded=False):
        with st.form("suggestion_form"):
            sc1, sc2 = st.columns(2)
            sg_title = sc1.text_input("建议标题 *", placeholder="一句话概括核心建议")
            sg_type  = sc2.selectbox("建议类型", SUGGESTION_TYPES)
            sc3, sc4, sc5 = st.columns(3)
            sg_prod  = sc3.selectbox("相关产品",
                                     ["不限"] + list(PRODUCT_ZH.values()))
            sg_country = sc4.selectbox("相关国家", ["不限", "UK", "Australia", "全球"])
            sg_school  = sc5.text_input("相关学校", placeholder="如：UCL")
            sg_insight = st.text_area("洞察/背景", height=80, placeholder="为什么要提这个建议？数据/观察到什么？")
            sg_rec     = st.text_area("建议动作", height=80, placeholder="具体要做什么？谁来做？")
            sc6, sc7   = st.columns(2)
            sg_pri     = sc6.selectbox("优先级", PRIORITY_OPTIONS, index=1)
            sg_source  = sc7.selectbox("来源", ["管理层","AI生成","销售反馈","产品部","学管部","外部调研"])
            sg_submit  = st.form_submit_button("📩 提交建议", type="primary")

            if sg_submit:
                if not sg_title.strip():
                    st.error("请填写建议标题")
                else:
                    save_suggestion({
                        "title":           sg_title.strip(),
                        "suggestion_type": sg_type,
                        "related_product": sg_prod if sg_prod != "不限" else "",
                        "related_country": sg_country if sg_country != "不限" else "",
                        "related_school":  sg_school.strip(),
                        "insight":         sg_insight.strip(),
                        "recommendation":  sg_rec.strip(),
                        "priority":        sg_pri,
                        "source":          sg_source,
                    })
                    st.success("✅ 建议已录入！")
                    st.rerun()

    st.divider()

    # ── 筛选 ──
    sf1, sf2, sf3 = st.columns(3)
    filt_sg_type = sf1.selectbox("类型", ["全部"] + SUGGESTION_TYPES)
    filt_sg_pri  = sf2.selectbox("优先级", ["全部"] + PRIORITY_OPTIONS)
    filt_sg_status = sf3.selectbox("状态", ["全部"] + list(SG_STATUS_ZH.keys()),
                                   format_func=lambda x: "全部" if x=="全部" else SG_STATUS_ZH.get(x,x))

    suggestions = list_suggestions(
        status   = None if filt_sg_status=="全部" else filt_sg_status,
        priority = None if filt_sg_pri=="全部" else filt_sg_pri,
    )
    if filt_sg_type != "全部":
        suggestions = [s for s in suggestions if s["suggestion_type"] == filt_sg_type]

    st.caption(f"共 **{len(suggestions)}** 条建议")

    if not suggestions:
        st.info("暂无战略建议。点击上方「手动录入」，或运行 `python main.py monthly` 后由 AI 自动生成。")
    else:
        PRIORITY_ICON = {"低":"🔵","中":"🟡","高":"🟠","紧急":"🔴"}
        for sg in suggestions:
            icon = PRIORITY_ICON.get(sg["priority"], "⚪")
            status_label = SG_STATUS_ZH.get(sg["status"], sg["status"])
            sg_type_label = sg["suggestion_type"] or "-"

            with st.expander(f"{icon} **{sg['title']}** · {sg_type_label} · `{status_label}`"):
                mc = st.columns(4)
                mc[0].caption(f"**产品**\n{sg.get('related_product') or '-'}")
                mc[1].caption(f"**国家**\n{sg.get('related_country') or '-'}")
                mc[2].caption(f"**学校**\n{sg.get('related_school') or '-'}")
                mc[3].caption(f"**来源**\n{sg.get('source') or '-'}")

                if sg.get("insight"):
                    st.markdown(f"**🔍 洞察：** {sg['insight']}")
                if sg.get("recommendation"):
                    st.markdown(f"**💡 建议：** {sg['recommendation']}")

                st.caption(f"创建时间：{(sg.get('created_at') or '')[:16]}")
                st.divider()

                ops = st.columns(4)
                if sg["status"] == "new":
                    if ops[0].button("👀 进入审核", key=f"sg_rv_{sg['id']}"):
                        update_suggestion_status(sg["id"], "under_review")
                        st.rerun()
                if sg["status"] == "under_review":
                    if ops[0].button("✅ 采纳", key=f"sg_ad_{sg['id']}"):
                        update_suggestion_status(sg["id"], "adopted")
                        st.rerun()
                    if ops[1].button("❌ 驳回", key=f"sg_rj_{sg['id']}"):
                        update_suggestion_status(sg["id"], "rejected")
                        st.rerun()
                if sg["status"] not in ("archived",):
                    if ops[3].button("🗄️ 归档", key=f"sg_ar_{sg['id']}"):
                        update_suggestion_status(sg["id"], "archived")
                        st.rerun()


# ══════════════════════════════════════════════
# 页面：部门任务台
# ══════════════════════════════════════════════
elif page == "✅ 部门任务台":
    st.title("✅ 部门任务台")
    st.caption("各部门执行任务管理 — 由 AI 自动生成或手动录入")

    TASK_STATUS_ZH = {"todo":"待执行","doing":"执行中","done":"已完成","blocked":"阻塞","cancelled":"已取消"}
    PRIORITY_ICON  = {"低":"🔵","中":"🟡","高":"🟠","紧急":"🔴"}
    TASK_STATUS_ICON = {"todo":"⬜","doing":"🔄","done":"✅","blocked":"🚧","cancelled":"❌"}

    # ── 统计行 ──
    ts = get_task_stats()
    c1,c2,c3,c4,c5 = st.columns(5)
    _kpi(c1, ts.get("total",0),   "任务总数",  "#3b82f6")
    _kpi(c2, ts.get("todo",0),    "待执行",    "#f59e0b")
    _kpi(c3, ts.get("doing",0),   "执行中",    "#10b981")
    _kpi(c4, ts.get("done",0),    "已完成",    "#8b5cf6")
    _kpi(c5, ts.get("blocked",0), "🚧 阻塞",   "#ef4444")

    st.divider()

    # ── 新增任务 ──
    with st.expander("➕ 手动新增任务", expanded=False):
        with st.form("new_task_form"):
            tf1, tf2 = st.columns(2)
            t_title  = tf1.text_input("任务标题 *", placeholder="具体要做什么")
            t_dept   = tf2.selectbox("所属部门", DEPT_OPTIONS)
            tf3, tf4 = st.columns(2)
            t_type   = tf3.selectbox("任务类型", list(TASK_TYPES))
            t_pri    = tf4.selectbox("优先级", PRIORITY_OPTIONS, index=1)
            tf5, tf6 = st.columns(2)
            t_owner  = tf5.text_input("负责人", placeholder="谁来做")
            t_prod   = tf6.selectbox("相关产品", ["不限"]+list(PRODUCT_ZH.values()))
            t_desc   = st.text_area("任务描述", height=80, placeholder="具体说明怎么做")
            t_output = st.text_input("预期产出", placeholder="完成后产出什么")
            t_sub    = st.form_submit_button("📩 新增任务", type="primary")
            if t_sub:
                if not t_title.strip():
                    st.error("请填写任务标题")
                else:
                    save_task({
                        "title":           t_title.strip(),
                        "description":     t_desc.strip(),
                        "task_type":       t_type,
                        "department":      t_dept,
                        "owner":           t_owner.strip(),
                        "priority":        t_pri,
                        "related_product": t_prod if t_prod != "不限" else "",
                        "expected_output": t_output.strip(),
                        "task_source":     "手动",
                        "status":          "todo",
                    })
                    st.success("✅ 任务已新增！")
                    st.rerun()

    # ── 筛选 ──
    fc1,fc2,fc3,fc4 = st.columns(4)
    filt_dept   = fc1.selectbox("部门", ["全部"]+DEPT_OPTIONS)
    filt_tstatus= fc2.selectbox("状态", ["全部"]+list(TASK_STATUS_ZH.keys()),
                                format_func=lambda x: "全部" if x=="全部" else TASK_STATUS_ZH.get(x,x))
    filt_tpri   = fc3.selectbox("优先级", ["全部"]+PRIORITY_OPTIONS)
    filt_ttype  = fc4.selectbox("类型", ["全部"]+list(TASK_TYPES),)

    tasks_data = list_tasks(
        department = None if filt_dept=="全部" else filt_dept,
        status     = None if filt_tstatus=="全部" else filt_tstatus,
        priority   = None if filt_tpri=="全部" else filt_tpri,
        task_type  = None if filt_ttype=="全部" else filt_ttype,
        limit      = 200,
    )

    st.caption(f"共 **{len(tasks_data)}** 条任务")

    if not tasks_data:
        st.info("暂无任务。运行 `python main.py generate-tasks` 自动生成，或点击上方手动新增。")
    else:
        # 按部门分组展示
        by_dept: dict = {}
        for t in tasks_data:
            d = t.get("department","其他")
            by_dept.setdefault(d, []).append(t)

        for dept, dept_tasks in by_dept.items():
            st.subheader(f"{dept}  ({len(dept_tasks)}条)")
            for t in dept_tasks:
                s_icon  = TASK_STATUS_ICON.get(t["status"],"⬜")
                p_icon  = PRIORITY_ICON.get(t.get("priority","中"),"⚪")
                s_label = TASK_STATUS_ZH.get(t["status"],t["status"])
                with st.expander(f"{s_icon} {p_icon} **{t['title']}** · `{s_label}`"):
                    mc = st.columns(4)
                    mc[0].caption(f"**类型**\n{t.get('task_type') or '-'}")
                    mc[1].caption(f"**负责人**\n{t.get('owner') or '⚠️ 待分配'}")
                    mc[2].caption(f"**产品**\n{t.get('related_product') or '-'}")
                    mc[3].caption(f"**来源**\n{t.get('task_source') or '-'}")

                    if t.get("description"):
                        st.markdown(t["description"])
                    if t.get("expected_output"):
                        st.caption(f"📦 预期产出：{t['expected_output']}")
                    if t.get("notes"):
                        st.caption(f"💬 备注：{t['notes']}")

                    st.caption(f"创建：{(t.get('created_at') or '')[:10]}"
                               + (f"  完成：{t['completed_at'][:10]}" if t.get('completed_at') else ""))
                    st.divider()

                    # 操作按钮
                    bc = st.columns(5)
                    status = t["status"]
                    if status == "todo":
                        if bc[0].button("▶️ 开始", key=f"tk_start_{t['id']}"):
                            update_task_status(t["id"], "doing")
                            st.rerun()
                    if status == "doing":
                        if bc[0].button("✅ 完成", key=f"tk_done_{t['id']}"):
                            update_task_status(t["id"], "done")
                            st.rerun()
                        if bc[1].button("🚧 阻塞", key=f"tk_block_{t['id']}"):
                            update_task_status(t["id"], "blocked")
                            st.rerun()
                    if status == "blocked":
                        note_in = bc[2].text_input("解除原因", key=f"tk_note_{t['id']}")
                        if bc[0].button("🔓 解除阻塞", key=f"tk_unblock_{t['id']}"):
                            update_task_status(t["id"], "doing", notes=note_in or "阻塞已解除")
                            st.rerun()
                    if status not in ("done","cancelled"):
                        if bc[4].button("❌ 取消", key=f"tk_cancel_{t['id']}"):
                            update_task_status(t["id"], "cancelled")
                            st.rerun()
            st.divider()


# ══════════════════════════════════════════════
# 页面 8：自动化工作流
# ══════════════════════════════════════════════
elif page == "🤖 自动化工作流":
    st.title("🤖 自动化工作流")
    st.caption("运行 AI 工作流自动生成内容草稿、战略建议并推送企业微信。所有输出为草稿，需人工审核后发布。")

    # ── 触发按钮 ──────────────────────────────────
    st.subheader("▶️ 手动触发工作流")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🚀 运行每日工作流", use_container_width=True, type="primary"):
            import subprocess, os
            env = os.environ.copy()
            with st.spinner("每日工作流运行中，预计 30-60 秒..."):
                try:
                    result = subprocess.run(
                        ["uv", "run", "--with", "sqlalchemy",
                         "--with", "anthropic", "--with", "pyyaml",
                         "--with", "requests", "--with", "schedule",
                         "python", "main.py", "run-daily", "dashboard"],
                        capture_output=True, text=True, timeout=120,
                        cwd=str(ROOT), env=env,
                    )
                    if result.returncode == 0:
                        st.success("✅ 工作流运行完成！")
                        st.code(result.stdout[-800:] if len(result.stdout) > 800 else result.stdout)
                    else:
                        st.error("❌ 工作流运行出错")
                        st.code(result.stderr[-600:] if result.stderr else "无错误输出")
                except subprocess.TimeoutExpired:
                    st.error("⏱️ 工作流超时（>120秒），请查看日志")
                except Exception as e:
                    st.error(f"启动失败：{e}")
    with col2:
        st.info(
            "**每日工作流包含：**\n"
            "1. 收集今日业务背景（活动、任务、反馈）\n"
            "2. AI 生成今日销售素材草稿（朋友圈/社群/销售话术）\n"
            "3. 汇总高优先级反馈，生成战略建议\n"
            "4. 推送企业微信日报\n\n"
            "⚠️ 生成内容均为 draft 状态，请到【内容池】审核后再发布。"
        )

    st.divider()

    # ── 运行日志 ───────────────────────────────────
    st.subheader("📋 工作流运行日志")

    runs = list_workflow_runs(limit=20)
    if not runs:
        st.info("暂无运行记录，点击上方按钮运行第一次工作流。")
    else:
        STATUS_ICON = {
            "success": "✅",
            "partial_success": "⚠️",
            "failed": "❌",
            "running": "🔄",
        }
        for run in runs:
            status = run.get("status", "")
            icon = STATUS_ICON.get(status, "⚪")
            started = run.get("started_at", "")[:16] if run.get("started_at") else "—"
            duration = f"{run.get('duration_seconds', 0):.0f}s" if run.get("duration_seconds") else "—"
            records = run.get("created_records_count", 0)
            label = f"{icon} **#{run['id']}** · {run['workflow_name']} · {started} · {duration} · {records} 条记录"

            with st.expander(label, expanded=(status in ("failed", "partial_success") and run == runs[0])):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("状态", f"{icon} {status}")
                c2.metric("触发方式", run.get("trigger", "—"))
                c3.metric("耗时", duration)
                c4.metric("生成记录", records)

                if run.get("summary"):
                    st.info(run["summary"])

                steps = run.get("steps_run") or []
                if steps:
                    st.markdown("**步骤明细：**")
                    for step in steps:
                        step_icon = "✅" if step.get("status") == "ok" else "❌"
                        note = f" — {step.get('note','')}" if step.get("note") else ""
                        st.caption(f"{step_icon} {step.get('step','')} (records={step.get('records',0)}){note}")

                if run.get("error_message"):
                    st.error(f"错误：{run['error_message'][:300]}")


# ══════════════════════════════════════════════
# 页面：资料上传中心
# ══════════════════════════════════════════════
elif page == "📁 资料上传中心":
    import subprocess, os, shutil
    from database import (
        save_knowledge_doc, list_knowledge_docs, get_knowledge_stats,
        update_knowledge_doc_summary,
    )

    KB_ROOT  = ROOT / "knowledge_base"
    DATA_DIR = ROOT / "data"
    _env_up  = os.environ.copy()

    # ── 当前状态统计 ────────────────────────
    from database.db import get_session as _gs
    from database.models import Order as _Order, Lead as _Lead, MarketSignal as _MS, KnowledgeDoc as _KD
    from sqlalchemy import select as _sel, func as _func
    with _gs() as _s:
        _n_orders  = _s.execute(_sel(_func.count()).select_from(_Order)).scalar() or 0
        _n_leads   = _s.execute(_sel(_func.count()).select_from(_Lead)).scalar() or 0
        _n_signals = _s.execute(_sel(_func.count()).select_from(_MS)).scalar() or 0
        _n_docs    = _s.execute(_sel(_func.count()).select_from(_KD).where(_KD.is_enabled == True)).scalar() or 0
        _n_summary = _s.execute(_sel(_func.count()).select_from(_KD).where(_KD.summary != None)).scalar() or 0

    _prod_files = len(list((KB_ROOT / "01_产品知识库").glob("*.*")) if (KB_ROOT / "01_产品知识库").exists() else [])
    _talk_files = len(list((KB_ROOT / "02_销售话术库").glob("*.*")) if (KB_ROOT / "02_销售话术库").exists() else [])
    _risk_files = len(list((KB_ROOT / "06_风控表达库").glob("*.*")) if (KB_ROOT / "06_风控表达库").exists() else [])
    _orders_csv = DATA_DIR / "orders.csv"
    _leads_csv  = DATA_DIR / "leads.csv"
    _has_orders = _orders_csv.exists()
    _has_leads  = _leads_csv.exists()

    _status_line = (
        f"知识库 {_n_docs} 个文件 · 订单 {_n_orders} 条 · 咨询 {_n_leads} 条 · 市场信号 {_n_signals} 条"
        if (_n_orders + _n_leads + _n_docs) > 0
        else "⚠️ 尚无真实数据。完成以下步骤后，推广建议会更准确。"
    )

    # ── Hero ────────────────────────────────
    render_hero(
        "📁 资料上传中心",
        "上传产品资料、销售话术、风控规则、订单和咨询数据。让系统更懂业务，推广建议更精准。",
        _status_line,
    )

    if (_n_orders + _n_leads) == 0:
        st.warning("⚠️ **当前仍处于 Demo 数据阶段。** 上传真实订单（orders.csv）和咨询记录（leads.csv）后，推广策略建议会更准确、更有针对性。", icon="⚠️")

    # ── Hero 操作按钮 ────────────────────────
    _ub1, _ub2, _ub3, _ub_sp = st.columns([1, 1, 1, 3])
    _do_scan    = _ub1.button("🔍 扫描知识库", use_container_width=True, type="primary")
    _do_import  = _ub2.button("📥 导入数据", use_container_width=True)
    _do_signals = _ub3.button("📡 更新市场信号", use_container_width=True)

    _base_cmd = ["uv", "run", "--with", "sqlalchemy", "--with", "pyyaml",
                 "--with", "pandas", "python", "main.py"]

    def _run_cmd_up(label, args, spinner_text, timeout=60):
        with st.spinner(spinner_text):
            try:
                r = subprocess.run(args, capture_output=True, text=True,
                                   timeout=timeout, cwd=str(ROOT), env=_env_up)
                out = (r.stdout or "") + (r.stderr or "")
                if r.returncode == 0:
                    st.success(f"✅ {label} 完成")
                else:
                    st.error(f"❌ {label} 失败")
                if out.strip():
                    st.code(out[-800:])
            except subprocess.TimeoutExpired:
                st.error(f"⏱️ {label} 超时（>{timeout}s）")
            except Exception as _e:
                st.error(f"执行失败：{_e}")

    if _do_scan:
        _run_cmd_up("扫描知识库", _base_cmd + ["scan-knowledge-base"], "正在扫描 knowledge_base/ 目录...")
        st.rerun()

    if _do_import:
        if _has_orders:
            _run_cmd_up("导入订单", _base_cmd + ["ingest-orders", "data/orders.csv"], "正在导入订单...", timeout=30)
        if _has_leads:
            _run_cmd_up("导入咨询", _base_cmd + ["ingest-leads", "data/leads.csv"], "正在导入咨询...", timeout=30)
        if not _has_orders and not _has_leads:
            st.warning("请先上传 orders.csv 和 leads.csv")
        else:
            st.rerun()

    if _do_signals:
        _run_cmd_up("更新市场信号",
            ["uv", "run", "--with", "sqlalchemy", "--with", "anthropic",
             "--with", "pyyaml", "--with", "requests", "python", "main.py", "update-market-signals"],
            "正在分析市场数据并生成信号...", timeout=90)
        st.rerun()

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── 状态指标卡 ───────────────────────────
    _sc = st.columns(5)
    render_metric(_sc[0], _n_docs,    "已登记资料",   f"含{_n_summary}份有摘要", "#3b82f6")
    render_metric(_sc[1], _n_orders,  "订单记录",     "条", "#10b981")
    render_metric(_sc[2], _n_leads,   "咨询记录",     "条", "#6366f1")
    render_metric(_sc[3], _n_signals, "市场信号",     "条", "#f59e0b")
    render_metric(_sc[4], _prod_files + _talk_files + _risk_files, "本地文件数", "知识库目录", "#0ea5e9")

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    # ── 步骤引导 ─────────────────────────────
    with st.expander("📋 使用步骤引导（点击展开）", expanded=(_n_orders + _n_docs == 0)):
        _steps = [
            ("上传产品资料 / 销售话术 / 风控规则到下方上传区", _prod_files + _talk_files > 0),
            ("点击「🔍 扫描知识库」将文件登记到数据库",       _n_docs > 0),
            ("（可选）点击「生成资料摘要」让 AI 理解内容",    _n_summary > 0),
            ("上传 orders.csv 和 leads.csv 到数据上传区",     _has_orders or _has_leads),
            ("点击「📥 导入数据」写入数据库",                 _n_orders > 0 or _n_leads > 0),
            ("点击「📡 更新市场信号」生成市场情报",            _n_signals > 0),
            ("前往「产品推广策略台」生成本月/本周推广建议",    False),
        ]
        for _i, (_step, _done) in enumerate(_steps, 1):
            _icon = "✅" if _done else "⏳"
            _clr = "#059669" if _done else "#374151"
            st.markdown(f"""
            <div class="step-item">
              <div class="step-num" style="background:{'#059669' if _done else '#3b82f6'}">{_i}</div>
              <div class="step-text" style="color:{_clr}">{_icon} {_step}</div>
            </div>""", unsafe_allow_html=True)

    # ── Tab 布局 ────────────────────────────────
    tab_kb, tab_data, tab_actions = st.tabs(["📚 业务资料上传", "📊 订单/咨询数据上传", "⚡ 进阶操作"])

    # ══ Tab 1：知识库上传 ══════════════════════
    with tab_kb:
        st.subheader("📂 上传业务资料到知识库")
        st.caption("支持格式：.md  .txt  .docx  .pdf · 上传后点击上方「🔍 扫描知识库」按钮登记文件")

        UPLOAD_CATS = {
            "01_产品知识库": {
                "label": "产品资料",
                "subtypes": ["Final精准押题", "Dissertation论文辅导", "学年包", "DP高端服务", "AI合规学习", "保过辅导", "其他"],
                "name_suffix": "_产品说明_v1.md",
                "category": "产品知识库",
            },
            "02_销售话术库": {
                "label": "销售话术",
                "subtypes": ["价格异议", "押题异议", "质量异议", "AI率异议", "保过异议", "学年包异议", "DP高端客户", "转介绍", "其他"],
                "name_suffix": "_销售话术_v1.md",
                "category": "销售话术库",
            },
            "06_风控表达库": {
                "label": "风控规则",
                "subtypes": ["禁用词与高风险表达", "押题产品风控规则", "AI率表达风控规则", "保过辅导风控规则", "退款承诺表达规则", "小红书平台表达风险", "其他"],
                "name_suffix": "_v1.md",
                "category": "风控表达库",
            },
        }

        for dir_key, cfg_item in UPLOAD_CATS.items():
            with st.expander(f"📂 {cfg_item['label']}  →  knowledge_base/{dir_key}/", expanded=True):
                col_sel, col_up = st.columns([1, 2])
                subtype = col_sel.selectbox(
                    f"{cfg_item['label']}类型",
                    cfg_item["subtypes"],
                    key=f"sel_{dir_key}",
                )
                uploaded = col_up.file_uploader(
                    f"上传{cfg_item['label']}文件",
                    type=["md", "txt", "docx", "pdf"],
                    key=f"uploader_{dir_key}",
                )
                if uploaded is not None:
                    target_dir = KB_ROOT / dir_key
                    target_dir.mkdir(parents=True, exist_ok=True)
                    # 建议文件名
                    ext = Path(uploaded.name).suffix or ".md"
                    suggested = subtype + cfg_item["name_suffix"]
                    suggested = suggested.replace(".md", ext) if ext != ".md" else suggested
                    save_name = col_up.text_input(
                        "保存文件名（可修改）",
                        value=suggested,
                        key=f"fname_{dir_key}",
                    )
                    if col_up.button(f"💾 保存到 {dir_key}", key=f"save_{dir_key}", type="primary"):
                        dest = target_dir / save_name
                        dest.write_bytes(uploaded.getvalue())
                        st.success(f"✅ 已保存：knowledge_base/{dir_key}/{save_name}")
                        st.caption("文件已保存，请点击下方「⚡ 操作按钮」中的「扫描知识库资料」更新登记。")

    # ══ Tab 2：数据上传 ════════════════════════
    with tab_data:
        st.subheader("上传订单 / 咨询 CSV 数据")

        # 订单上传
        with st.expander("📦 订单数据（orders.csv）", expanded=True):
            st.caption("字段要求：order_date, school, country, product, course_code, deadline, amount, sales_owner, status")
            with st.columns([1, 2])[1]:
                pass
            orders_up = st.file_uploader("上传订单 CSV", type=["csv"], key="orders_csv_up")
            if orders_up is not None:
                if st.button("💾 保存为 data/orders.csv", key="save_orders", type="primary"):
                    DATA_DIR.mkdir(exist_ok=True)
                    (DATA_DIR / "orders.csv").write_bytes(orders_up.getvalue())
                    st.success("✅ orders.csv 已保存。请前往「⚡ 操作按钮」点击「导入订单数据」写入数据库。")

            # 预览现有文件
            orders_path = DATA_DIR / "orders.csv"
            if orders_path.exists():
                try:
                    df_o = pd.read_csv(orders_path, nrows=3)
                    st.caption(f"当前 orders.csv 预览（前3行）：")
                    st.dataframe(df_o, use_container_width=True, hide_index=True)
                except Exception:
                    pass

        # 咨询上传
        with st.expander("💬 咨询数据（leads.csv）", expanded=True):
            st.caption("字段要求：inquiry_date, school, country, product_interest, pain_point, deadline, deal_status, lost_reason, sales_owner, source_channel")
            leads_up = st.file_uploader("上传咨询 CSV", type=["csv"], key="leads_csv_up")
            if leads_up is not None:
                if st.button("💾 保存为 data/leads.csv", key="save_leads", type="primary"):
                    DATA_DIR.mkdir(exist_ok=True)
                    (DATA_DIR / "leads.csv").write_bytes(leads_up.getvalue())
                    st.success("✅ leads.csv 已保存。请前往「⚡ 操作按钮」点击「导入咨询数据」写入数据库。")

            leads_path = DATA_DIR / "leads.csv"
            if leads_path.exists():
                try:
                    df_l = pd.read_csv(leads_path, nrows=3)
                    st.caption("当前 leads.csv 预览（前3行）：")
                    st.dataframe(df_l, use_container_width=True, hide_index=True)
                except Exception:
                    pass

        # 老师储备数据上传（新增）
        with st.expander("📋 老师储备数据（teacher_capacity.csv）", expanded=True):
            st.caption(
                "字段说明：subject_area, course_type, country, school_experience, "
                "available_slots, current_load, max_capacity, capacity_status, risk_level, notes"
            )
            # 状态统计
            from database.models import TeacherCapacity as _TC, OrderRiskSignal as _ORS
            with _gs() as _s2:
                _n_tc  = _s2.execute(_sel(_func.count()).select_from(_TC)).scalar() or 0
                _n_ors = _s2.execute(_sel(_func.count()).select_from(_ORS)).scalar() or 0
            st.caption(f"teacher_capacity 表：{_n_tc} 条 | order_risk_signals 表：{_n_ors} 条")

            _tc_upload = st.file_uploader("上传 teacher_capacity.csv", type=["csv"], key="tc_csv_up")
            if _tc_upload is not None:
                _tc_save_col1, _tc_save_col2 = st.columns(2)
                if _tc_save_col1.button("💾 保存文件", key="save_tc_file", type="primary"):
                    DATA_DIR.mkdir(exist_ok=True)
                    (DATA_DIR / "teacher_capacity.csv").write_bytes(_tc_upload.getvalue())
                    st.success("✅ 文件已保存到 data/teacher_capacity.csv")

                if _tc_save_col2.button("📥 导入数据到数据库", key="ingest_tc", type="primary"):
                    _tc_path = DATA_DIR / "teacher_capacity.csv"
                    if _tc_path.exists():
                        _run_cmd_up(
                            "导入老师储备数据",
                            ["uv", "run", "--with", "sqlalchemy", "--with", "pyyaml",
                             "--with", "pandas", "python", "main.py",
                             "ingest-teacher-capacity", "data/teacher_capacity.csv"],
                            "正在导入老师储备数据...", timeout=30,
                        )
                    else:
                        # 直接处理上传内容
                        try:
                            import io as _io
                            import pandas as _pd_tc
                            _tc_df = _pd_tc.read_csv(_io.StringIO(_tc_upload.getvalue().decode("utf-8")))
                            from database import save_teacher_capacity as _save_tc
                            _saved_tc = 0
                            for _, _row in _tc_df.iterrows():
                                try:
                                    _save_tc(_row.to_dict())
                                    _saved_tc += 1
                                except Exception:
                                    pass
                            st.success(f"✅ 老师储备数据导入完成：{_saved_tc} 条")
                        except Exception as _tc_e:
                            st.error(f"导入失败：{_tc_e}")
                    st.rerun()

            # 更新订单风险按钮
            _update_risk_col, _ = st.columns([1, 2])
            if _update_risk_col.button("⚡ 更新订单风险信号", key="update_risks_btn"):
                _run_cmd_up(
                    "更新订单风险",
                    ["uv", "run", "--with", "sqlalchemy", "--with", "pyyaml",
                     "--with", "pandas", "python", "main.py", "update-order-risks"],
                    "正在分析订单风险...", timeout=30,
                )
                st.rerun()

            # 下载样本模板
            _tpl_dl_col1, _tpl_dl_col2 = st.columns(2)
            _tc_sample = DATA_DIR / "teacher_capacity_sample.csv"
            _tc_tpl    = DATA_DIR / "teacher_capacity_template.csv"
            if _tc_sample.exists():
                _tpl_dl_col1.download_button(
                    "⬇️ 下载样本数据（含示例）",
                    _tc_sample.read_bytes(),
                    file_name="teacher_capacity_sample.csv",
                    mime="text/csv",
                )
            if _tc_tpl.exists():
                _tpl_dl_col2.download_button(
                    "⬇️ 下载空白模板",
                    _tc_tpl.read_bytes(),
                    file_name="teacher_capacity_template.csv",
                    mime="text/csv",
                )

        # 下载模板
        st.divider()
        st.subheader("📥 下载 CSV 模板")
        tc1, tc2 = st.columns(2)
        orders_tpl = DATA_DIR / "orders_template.csv"
        leads_tpl  = DATA_DIR / "leads_template.csv"
        if orders_tpl.exists():
            tc1.download_button("⬇️ 下载 orders_template.csv", orders_tpl.read_bytes(),
                                file_name="orders_template.csv", mime="text/csv")
        if leads_tpl.exists():
            tc2.download_button("⬇️ 下载 leads_template.csv", leads_tpl.read_bytes(),
                                file_name="leads_template.csv", mime="text/csv")

    # ══ Tab 3：进阶操作 ════════════════════════
    with tab_actions:
        st.subheader("⚡ 进阶操作")
        st.caption("以下操作已通过上方按钮快速访问，这里提供更精细的控制选项。")

        _base = ["uv", "run", "--with", "sqlalchemy", "--with", "pyyaml",
                 "--with", "pandas", "python", "main.py"]

        # ── 按钮1：扫描知识库
        st.markdown("#### 1. 扫描知识库资料")
        st.caption("扫描 knowledge_base/ 目录，登记文件信息到数据库。不调用 Claude，速度很快。")
        if st.button("🔍 扫描知识库资料", key="btn_scan", type="primary", use_container_width=True):
            _run_cmd_up("扫描知识库", _base + ["scan-knowledge-base"], "正在扫描文件...")
            st.rerun()

        st.divider()

        # ── 按钮2：生成摘要（可选，调用Claude）
        st.markdown("#### 2. 生成/更新资料摘要（可选）")
        st.caption("对尚未生成摘要的文档，调用 Claude 生成 150-300 字短摘要 + 关键词。Agent 生成内容时优先读摘要。")
        st.warning("⚠️ 此操作会调用 Claude API，消耗 token。建议仅在需要时使用。", icon="⚠️")

        docs_no_summary = list_knowledge_docs(has_summary=False)
        st.caption(f"当前待生成摘要文档：{len(docs_no_summary)} 个")

        if st.button("🤖 生成/更新资料摘要", key="btn_summary", use_container_width=True):
            if not docs_no_summary:
                st.info("所有文档已有摘要，无需更新。")
            else:
                import yaml
                with open(ROOT / "config.yaml") as f:
                    _cfg = yaml.safe_load(f)
                import anthropic as _anthropic
                _client = _anthropic.Anthropic()
                _model = _cfg.get("anthropic", {}).get("model", "claude-sonnet-4-6")
                progress = st.progress(0)
                for i, doc in enumerate(docs_no_summary[:10]):  # 每次最多10个，控制token
                    fp = Path(doc["file_path"]) if doc.get("file_path") else None
                    if not fp or not fp.exists():
                        continue
                    try:
                        raw = fp.read_text(encoding="utf-8", errors="ignore")[:3000]  # 最多3000字符
                        resp = _client.messages.create(
                            model=_model,
                            max_tokens=600,
                            messages=[{
                                "role": "user",
                                "content": (
                                    f"请对以下知识库文档生成简短摘要，用于销售辅助系统。\n\n"
                                    f"文档类别：{doc['category']}\n文件名：{doc['file_name']}\n\n"
                                    f"文档内容（节选）：\n{raw}\n\n"
                                    "请用JSON格式回复，包含以下字段：\n"
                                    "summary（摘要，150-300字中文）\n"
                                    "keywords（关键词列表，5-10个）\n"
                                    "related_products（关联产品ID列表，从以下选择：final_prediction/guaranteed/dissertation/annual_package/dp_premium/ai_learning/regular）\n"
                                    "related_scenarios（适用销售场景列表，3-5个）\n"
                                    "只返回JSON，不要其他内容。"
                                ),
                            }],
                        )
                        import json as _json
                        raw_resp = resp.content[0].text.strip()
                        if raw_resp.startswith("```"):
                            raw_resp = raw_resp.split("```")[1]
                            if raw_resp.startswith("json"):
                                raw_resp = raw_resp[4:]
                        parsed = _json.loads(raw_resp)
                        update_knowledge_doc_summary(
                            doc["id"],
                            summary=parsed.get("summary", ""),
                            keywords=parsed.get("keywords", []),
                            related_products=parsed.get("related_products", []),
                            related_scenarios=parsed.get("related_scenarios", []),
                        )
                        st.caption(f"  ✅ [{doc['category']}] {doc['file_name']}")
                    except Exception as e:
                        st.caption(f"  ❌ {doc['file_name']}：{e}")
                    progress.progress((i + 1) / min(len(docs_no_summary), 10))
                st.success(f"✅ 摘要生成完成，已更新 {min(len(docs_no_summary), 10)} 个文档。")

        st.divider()

        # ── 按钮3：导入订单
        st.markdown("#### 3. 导入订单数据")
        orders_csv = DATA_DIR / "orders.csv"
        if not orders_csv.exists():
            st.warning("⚠️ data/orders.csv 不存在，请先在「数据上传」标签页上传文件。")
        else:
            st.caption(f"文件已就绪：{orders_csv}（{orders_csv.stat().st_size} 字节）")
        if st.button("📥 导入订单数据", key="btn_orders", type="primary", use_container_width=True,
                     disabled=not orders_csv.exists()):
            _run_cmd_up("导入订单", _base + ["ingest-orders", "data/orders.csv"], "正在导入订单数据...", timeout=30)

        st.divider()

        # ── 按钮4：导入咨询
        st.markdown("#### 4. 导入咨询数据")
        leads_csv = DATA_DIR / "leads.csv"
        if not leads_csv.exists():
            st.warning("⚠️ data/leads.csv 不存在，请先在「数据上传」标签页上传文件。")
        else:
            st.caption(f"文件已就绪：{leads_csv}（{leads_csv.stat().st_size} 字节）")
        if st.button("📥 导入咨询数据", key="btn_leads", type="primary", use_container_width=True,
                     disabled=not leads_csv.exists()):
            _run_cmd_up("导入咨询", _base + ["ingest-leads", "data/leads.csv"], "正在导入咨询数据...", timeout=30)

        st.divider()

        # ── 按钮5：更新市场信号
        st.markdown("#### 5. 更新市场信号")
        st.caption("基于 orders/leads 数据用 Python/SQL 统计，生成热门学校/产品/DDL提醒等信号。调用 Claude 仅用于生成建议动作（少量 token）。")
        if st.button("📡 更新市场信号", key="btn_signals", type="primary", use_container_width=True):
            _run_cmd_up(
                "更新市场信号",
                ["uv", "run", "--with", "sqlalchemy", "--with", "anthropic",
                 "--with", "pyyaml", "--with", "requests", "python", "main.py", "update-market-signals"],
                "正在分析市场数据并生成信号...",
                timeout=90,
            )

    # ══ 底部状态面板（已通过顶部指标卡展示，此处展示知识库详情）════
    st.divider()
    _ks = get_knowledge_stats()
    if _ks.get("by_category"):
        st.markdown("#### 📚 知识库文件分类详情")
        _kc = st.columns(min(len(_ks["by_category"]), 4))
        for _i, (_cat, _cnt) in enumerate(_ks["by_category"].items()):
            _kc[_i % 4].metric(_cat, f"{_cnt} 个文件")
    else:
        render_empty_state(
            "知识库尚未扫描",
            "点击上方「🔍 扫描知识库」按钮，系统会自动扫描 knowledge_base/ 目录中的所有文件并登记。",
        )

    from database.db import get_session as _gs
    from database.models import Order as _Order, Lead as _Lead, MarketSignal as _MS, KnowledgeDoc as _KD
    from sqlalchemy import select as _sel, func as _func

    with _gs() as _s:
        pass  # stats already loaded at top of page block


# ══════════════════════════════════════════════════════════════════
# 页面：📚 公司资料学习中心
# ══════════════════════════════════════════════════════════════════
elif page == "📚 公司资料学习中心":
    st.title("📚 公司资料学习中心")
    st.caption("系统只能基于上传并确认的资料生成建议。资料越完整，建议越准确。")

    # 初始化默认词典
    seed_default_dictionary()

    # ── 顶部缺口清单 ──────────────────────────────────────────────
    from agents.grounded_business_agent import GroundedBusinessAgent as _GBA
    _gba = _GBA()
    _gap_status = _gba.get_knowledge_gap_status()

    STATUS_COLOR = {
        "未上传": "🔴",
        "已解析待确认": "🟡",
        "部分确认": "🟠",
        "已确认可使用": "🟢",
    }

    st.markdown("### 📋 资料缺口清单")
    _gap_cols = st.columns(4)
    for _gi, _gap in enumerate(_gap_status):
        _icon = STATUS_COLOR.get(_gap["status"], "⚪")
        _col = _gap_cols[_gi % 4]
        _col.markdown(
            f"""<div style="background:#1e293b;border-radius:8px;padding:10px 12px;margin-bottom:8px;border-left:3px solid {'#22c55e' if _gap['status']=='已确认可使用' else '#f59e0b' if '确认' in _gap['status'] else '#ef4444'}">
            <div style="font-size:12px;color:#94a3b8">{_gap['category']}</div>
            <div style="font-size:13px;font-weight:600;color:#f1f5f9">{_gap['label']}</div>
            <div style="font-size:12px;color:#64748b;margin-top:2px">{_icon} {_gap['status']}</div>
            <div style="font-size:11px;color:#475569">已确认:{_gap['confirmed']} 待确认:{_gap['pending']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── 四个 Tab ──────────────────────────────────────────────────
    _tab_upload, _tab_review, _tab_dict, _tab_facts = st.tabs([
        "📤 上传资料 & 提取事实",
        "✅ 待确认事实",
        "📖 业务词典管理",
        "🔍 已确认事实库",
    ])

    # ─────────────────────────────────────────
    # Tab 1：上传资料 + 触发提取
    # ─────────────────────────────────────────
    with _tab_upload:
        st.markdown("#### 上传资料文件，系统将自动提取业务事实")
        st.info("支持格式：.md / .txt / .html / .docx / .pdf\n上传后点击「提取事实」，AI 会从文件中提取明确写到的事实，不会脑补。提取完成后需要**人工确认**才会生效。")

        _CATEGORIES = {
            "00_公司事实源 · 公司基础信息":    "00_公司事实源",
            "01_部门职责 · 部门职责说明":       "01_部门职责",
            "02_产品体系 · 产品说明资料":       "02_产品体系",
            "03_销售话术 · 销售话术手册":       "03_销售话术",
            "04_客户异议 · 客户异议处理":       "04_客户异议",
            "05_风控表达 · 风控规则":           "05_风控表达",
            "06_学管交付 · 交付 SOP":           "06_学管交付",
            "07_老师储备 · 老师资源说明":       "07_老师储备",
            "08_订单咨询数据说明 · 字段口径":   "08_订单咨询数据说明",
            "09_优秀内容样例 · 内容参考":       "09_优秀内容样例",
            "10_禁用表达 · 禁用词规则":         "10_禁用表达",
            "11_组织命名规则 · 命名标准":       "11_组织命名规则",
        }

        _up_cat_label = st.selectbox("选择资料分类", list(_CATEGORIES.keys()))
        _up_cat = _CATEGORIES[_up_cat_label]
        _up_file = st.file_uploader("上传文件", type=["md","txt","html","htm","docx","pdf"])

        if _up_file:
            _save_dir = ROOT / "knowledge_base" / _up_cat
            _save_dir.mkdir(parents=True, exist_ok=True)
            _save_path = _save_dir / _up_file.name
            _save_path.write_bytes(_up_file.read())
            st.success(f"✅ 文件已保存到 knowledge_base/{_up_cat}/{_up_file.name}")

            if st.button("🤖 提取事实（调用 AI）", type="primary"):
                import os as _os
                _api_key = _os.environ.get("ANTHROPIC_API_KEY", "")
                if not _api_key:
                    st.error("❌ 未检测到 ANTHROPIC_API_KEY 环境变量，请先配置 API Key。")
                else:
                    with st.spinner(f"正在从「{_up_file.name}」提取事实，请稍候..."):
                        try:
                            from agents.fact_extraction_agent import FactExtractionAgent as _FEA
                            _fea = _FEA()
                            _result = _fea.extract(str(_save_path), category=_up_cat)
                            if _result.get("error"):
                                st.error(f"❌ 提取失败：{_result['error']}")
                            else:
                                st.success(
                                    f"✅ 提取完成！\n"
                                    f"- 新增事实：{_result['facts_saved']} 条（待确认）\n"
                                    f"- 词典条目：{_result['terms_saved']} 条\n"
                                    f"- 缺少信息：{len(_result['missing'])} 项"
                                )
                                if _result.get("missing"):
                                    st.warning("⚠️ 资料中未提及的信息：\n" + "\n".join(f"- {m}" for m in _result["missing"]))
                                st.info("👆 请切换到「待确认事实」标签页，审核并确认提取结果。")
                        except Exception as _e:
                            st.error(f"❌ 提取异常：{_e}")

        st.divider()
        st.markdown("#### 已有资料文件（knowledge_base/ 目录）")
        _kb_root = ROOT / "knowledge_base"
        _file_rows = []
        for _d in sorted(_kb_root.iterdir()):
            if _d.is_dir() and not _d.name.startswith("_") and not _d.name.startswith("."):
                for _f in sorted(_d.iterdir()):
                    if _f.suffix.lower() in {".md",".txt",".html",".htm",".docx",".pdf",".py"}:
                        _file_rows.append({
                            "分类": _d.name,
                            "文件名": _f.name,
                            "大小": f"{_f.stat().st_size // 1024} KB",
                        })
        if _file_rows:
            st.dataframe(pd.DataFrame(_file_rows), use_container_width=True, hide_index=True)
        else:
            st.info("暂无文件，请上传。")

    # ─────────────────────────────────────────
    # Tab 2：待确认事实
    # ─────────────────────────────────────────
    with _tab_review:
        st.markdown("#### ✅ 待确认事实")
        st.caption("只有「确认启用」的事实才会被 Agent 使用。请仔细核对每条事实的准确性。")

        _pending_facts = list_company_facts(review_status="pending")
        _modified_facts = list_company_facts(review_status="modified", is_active=False)
        _all_pending = _pending_facts + _modified_facts

        if not _all_pending:
            st.success("✅ 暂无待确认事实。请先上传资料并提取。")
        else:
            st.info(f"共 **{len(_all_pending)}** 条待确认事实，逐条审核：")

            # 分类筛选
            _rev_types = list({f["fact_type"] for f in _all_pending})
            _rev_filter = st.selectbox("筛选分类", ["全部"] + sorted(_rev_types), key="rev_filter")
            _show_facts = _all_pending if _rev_filter == "全部" else [f for f in _all_pending if f["fact_type"] == _rev_filter]

            for _fact in _show_facts:
                _conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(_fact["confidence"], "⚪")
                with st.expander(f"{_conf_color} [{_fact['fact_type']}] {_fact['title']}", expanded=False):
                    st.markdown(f"**内容：**\n{_fact['content']}")
                    _src = _fact.get("source_file", "")
                    _sec = _fact.get("source_section", "")
                    st.caption(f"来源：{_src.split('/')[-1] if _src else '未知'} | 章节：{_sec} | 可信度：{_fact['confidence']}")

                    _edit_content = st.text_area(
                        "如需修改内容：",
                        value=_fact["content"],
                        height=100,
                        key=f"edit_{_fact['id']}",
                    )
                    _edit_note = st.text_input("备注（可选）", key=f"note_{_fact['id']}")

                    _c1, _c2, _c3, _c4 = st.columns(4)
                    if _c1.button("✅ 确认启用", key=f"confirm_{_fact['id']}", type="primary"):
                        update_fact_status(_fact["id"], "confirmed")
                        st.success("已确认！")
                        st.rerun()
                    if _c2.button("✏️ 修改后启用", key=f"modify_{_fact['id']}"):
                        update_fact_content(_fact["id"], _edit_content, _edit_note)
                        st.success("已修改并启用！")
                        st.rerun()
                    if _c3.button("❌ 删除", key=f"reject_{_fact['id']}"):
                        update_fact_status(_fact["id"], "rejected")
                        st.warning("已删除")
                        st.rerun()
                    if _c4.button("⚠️ 标记不准确", key=f"inaccurate_{_fact['id']}"):
                        update_fact_status(_fact["id"], "inaccurate", _edit_note, is_active=False)
                        st.warning("已标记为不准确")
                        st.rerun()

    # ─────────────────────────────────────────
    # Tab 3：业务词典管理
    # ─────────────────────────────────────────
    with _tab_dict:
        st.markdown("#### 📖 业务词典管理")
        st.caption("词典中的标准词和禁用词会自动注入所有 Agent 的 prompt 约束。")

        _dict_terms = list_dictionary_terms(is_active=None)
        _dt_types = ["全部"] + sorted(list({t["term_type"] for t in _dict_terms}))
        _dt_filter = st.selectbox("筛选类型", _dt_types, key="dt_filter")
        _show_terms = _dict_terms if _dt_filter == "全部" else [t for t in _dict_terms if t["term_type"] == _dt_filter]

        if _show_terms:
            for _term in _show_terms:
                _active_icon = "🟢" if _term["is_active"] else "🔴"
                with st.expander(f"{_active_icon} [{_term['term_type']}] **{_term['standard_term']}**"):
                    _dc1, _dc2 = st.columns(2)
                    _dc1.markdown(f"**别名（可接受）：** {', '.join(_term.get('aliases') or []) or '无'}")
                    _dc2.markdown(f"**禁用词：** {', '.join(_term.get('forbidden_terms') or []) or '无'}")
                    if _term.get("description"):
                        st.markdown(f"**描述：** {_term['description']}")
                    st.caption(f"来源：{_term.get('source_file','').split('/')[-1] or '手动录入'}")
        else:
            st.info("暂无词典条目")

        st.divider()
        st.markdown("#### ➕ 手动新增词典条目")
        with st.form("add_term_form"):
            _nt_type = st.selectbox("类型", ["部门名称","产品名称","服务类型","客户类型","风控词","渠道名称","学校名称"])
            _nt_std = st.text_input("标准词（唯一）")
            _nt_aliases = st.text_input("别名（逗号分隔）")
            _nt_forbidden = st.text_input("禁用词（逗号分隔）")
            _nt_desc = st.text_area("描述/定义", height=60)
            if st.form_submit_button("➕ 新增", type="primary"):
                if _nt_std:
                    save_dictionary_term({
                        "term_type":       _nt_type,
                        "standard_term":   _nt_std.strip(),
                        "aliases":         [x.strip() for x in _nt_aliases.split(",") if x.strip()],
                        "forbidden_terms": [x.strip() for x in _nt_forbidden.split(",") if x.strip()],
                        "description":     _nt_desc.strip(),
                        "source_file":     "手动录入",
                        "is_active":       True,
                    })
                    st.success(f"✅ 已新增词典条目：{_nt_std}")
                    st.rerun()
                else:
                    st.error("标准词不能为空")

    # ─────────────────────────────────────────
    # Tab 4：已确认事实库
    # ─────────────────────────────────────────
    with _tab_facts:
        st.markdown("#### 🔍 已确认事实库（Agent 可使用）")
        _active_facts = list_company_facts(is_active=True)
        _inactive_facts = list_company_facts(is_active=False, review_status="rejected")

        if not _active_facts:
            st.warning("⚠️ 当前无已确认事实。所有 Agent 处于「临时参考」模式，建议不保证可靠性。")
            st.markdown("""
**当前缺少以下资料：**
1. 部门职责说明（上传 knowledge_base/01_部门职责/ 下的文件）
2. 产品体系资料（knowledge_base/02_产品体系/）
3. 销售话术资料（knowledge_base/03_销售话术/）
4. 风控表达规则（knowledge_base/05_风控表达/）
5. 学管交付边界（knowledge_base/06_学管交付/）
6. 老师储备数据（knowledge_base/07_老师储备/）

请到「上传资料」标签页上传以上资料。
            """)
        else:
            st.success(f"✅ 已确认事实共 **{len(_active_facts)}** 条，Agent 将优先使用这些事实。")

            _af_types = list({f["fact_type"] for f in _active_facts})
            _af_filter = st.selectbox("筛选分类", ["全部"] + sorted(_af_types), key="af_filter")
            _show_af = _active_facts if _af_filter == "全部" else [f for f in _active_facts if f["fact_type"] == _af_filter]

            _af_df = pd.DataFrame([{
                "ID": f["id"],
                "分类": f["fact_type"],
                "标题": f["title"],
                "内容摘要": f["content"][:80] + "..." if len(f["content"]) > 80 else f["content"],
                "来源文件": (f.get("source_file") or "").split("/")[-1],
                "可信度": f["confidence"],
                "更新时间": (f.get("updated_at") or "")[:10],
            } for f in _show_af])
            st.dataframe(_af_df, use_container_width=True, hide_index=True)

            # 允许撤销确认
            st.markdown("---")
            _revoke_id = st.number_input("撤销某条事实（输入 ID）", min_value=0, value=0, step=1)
            if st.button("⚠️ 撤销确认（改为待确认）") and _revoke_id > 0:
                update_fact_status(int(_revoke_id), "pending", is_active=False)
                st.warning(f"已撤销事实 #{_revoke_id}")
                st.rerun()
