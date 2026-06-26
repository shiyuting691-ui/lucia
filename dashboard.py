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
    # V9 增长管理
    list_opportunity_scores, list_lead_scores, list_campaign_predictions,
    list_weekly_reviews, get_weekly_review,
    update_task_extended, get_task_execution_stats,
    save_agent_run, list_agent_runs, get_agent_last_runs,
    save_agent_feedback, list_agent_feedbacks,
    # V10 三层需求预测
    list_demand_forecast_signals, list_school_academic_calendars,
    list_course_assessments_v2, list_major_demand_profiles,
)
from database.models import TASK_TYPES
from services.guardrails import (
    NO_DATA_MESSAGE,
    catalog_product_options,
    normalize_role,
    validate_ai_output,
    validate_product,
)


# ══════════════════════════════════════════
# Helper：过滤无效学校名
# ══════════════════════════════════════════

def _is_valid_school(s):
    """过滤掉无效学校名"""
    return bool(s) and s not in ('未知', '未知学校', '未知（学生不愿意说）', 'None', '—', '未填写')


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
.status-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 16px 18px;
    min-height: 132px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.05);
}
.status-card-title { font-size: 14px; font-weight: 700; color: #111827; margin-bottom: 8px; }
.status-card-body { font-size: 13px; color: #4b5563; line-height: 1.55; }
.status-card-foot { font-size: 12px; color: #64748b; margin-top: 10px; }

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
        if st.button(btn_label, type="primary", key=f"goto_{btn_page}_{btn_label}"):
            st.session_state["_goto"] = btn_page
            st.rerun()

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
_CATALOG_PRODUCTS = catalog_product_options()
PRODUCT_ZH = {p["id"]: p["name"] for p in _CATALOG_PRODUCTS}
PRODUCT_BY_NAME = {p["name"]: p["id"] for p in _CATALOG_PRODUCTS}

# ── 产品目录（按客户问题分类）──────────────────────────────
PRODUCT_CATALOG = {
    "语言班/雅思不够": [
        {
            "name": "语言班辅导",
            "fit": "语言班在读、雅思成绩不达标需要补救",
            "not_fit": "已经通过语言要求的学生",
            "problem": "语言班课程跟不上，成绩不达标，无法升入正式课程",
            "price_logic": "按课程数量/学时定价，通常1-3k/月",
            "service_boundary": "辅导语言班课程，不包含雅思备考",
            "sales_script": "语言班跟不上很正常，很多同学第一年都有这个问题，我们有专门的老师一对一帮你跟课，让你顺利过关升入正式课程",
            "objection": {"价格高": "语言班不过关要重读费用更高，投入产出比反而更合算", "不确定效果": "我们有历史通过率数据，可以给你看"},
            "related": ["PSE跟课", "HWEPT冲刺", "开学前预习课"],
            "delivery_risk": "学生学习态度、出勤率影响效果",
        },
        {
            "name": "PSE跟课",
            "fit": "澳洲大学PSE课程在读学生",
            "not_fit": "非PSE课程学生",
            "problem": "PSE课程难度超预期，无法独立完成任务",
            "price_logic": "按学期定价，通常2-5k/学期",
            "service_boundary": "全程跟课辅导，不保证成绩",
            "sales_script": "PSE是很多中国学生的第一道坎，我们有专门做PSE的老师，可以全程陪你一起过",
            "objection": {"已有家教": "家教和我们不一样，我们有系统的PSE经验和资料"},
            "related": ["语言班辅导", "开学前预习课"],
            "delivery_risk": "课程变化、老师资源紧张",
        },
        {
            "name": "HWEPT冲刺",
            "fit": "需要通过HWEPT考试的学生",
            "not_fit": "不需要HWEPT的学校/专业",
            "problem": "HWEPT考试没把握，需要针对性备考",
            "price_logic": "按考试批次定价，1-3k/次",
            "service_boundary": "针对HWEPT考试的专项备考，不包含语言班辅导",
            "sales_script": "HWEPT是一次性的机会，备考要有系统方法，我们有专门的真题和备考方案",
            "objection": {"自己能准备": "HWEPT有特定考察维度，需要有人指导才效率高"},
            "related": ["语言班辅导", "PSE跟课"],
            "delivery_risk": "考试日期临近时供给紧张",
        },
    ],
    "开学前预习": [
        {
            "name": "开学前预习课",
            "fit": "即将入学、想提前熟悉课程内容的学生",
            "not_fit": "已经在读、课程已开始的学生",
            "problem": "担心开学跟不上、第一学期表现差",
            "price_logic": "按科目/课程数量定价，500-2k/科",
            "service_boundary": "开学前1-3个月预习，不包含正式辅导",
            "sales_script": "提前预习的学生开学后成绩通常比没预习的高10-15分，给自己一个好开头",
            "objection": {"没必要": "第一学期成绩影响GPA基础，值得投资"},
            "related": ["作业委托", "安心包"],
            "delivery_risk": "课程内容变化、老师没有对应学校资料",
        },
    ],
    "作业": [
        {
            "name": "作业委托",
            "fit": "有作业完成需求、时间紧张的学生",
            "not_fit": "只需要辅导不需要代做的学生",
            "problem": "作业deadline临近，没时间或没能力完成",
            "price_logic": "按作业类型/字数/难度定价，几百到几千不等",
            "service_boundary": "代写完成，质量保障，不保证成绩",
            "sales_script": "我们有各专业的资深老师，可以在deadline前高质量完成",
            "objection": {"担心查重": "我们有专业的降重处理，通过率高"},
            "related": ["70+质检", "降AI率", "Essay写作"],
            "delivery_risk": "时间太紧、专业匹配度",
        },
        {
            "name": "Essay写作",
            "fit": "需要Essay类作业的学生",
            "not_fit": "理工科计算题类作业",
            "problem": "Essay写作能力不足、逻辑不清晰、引用格式不规范",
            "price_logic": "按字数定价，通常200-400元/千字",
            "service_boundary": "提供完整Essay，包含格式规范",
            "sales_script": "Essay是留学生最常见的作业形式，我们有专门做各类Essay的写手团队",
            "objection": {"太贵": "和挂科补考的代价比，这个投入很合理"},
            "related": ["70+质检", "降AI率", "作业委托"],
            "delivery_risk": "主题太偏、资料不足",
        },
        {
            "name": "70+质检",
            "fit": "对成绩有要求、想确保质量的学生",
            "not_fit": "只要能交就行、不在乎分数的",
            "problem": "担心作业质量不达标，分数不理想",
            "price_logic": "在原服务基础上加价20-30%",
            "service_boundary": "提供成绩保障，不达70分可部分退款或免费修改",
            "sales_script": "多一点点投入，换来的是确定性的结果，很多同学都选这个",
            "objection": {"多花了钱": "70+质检相当于给作业买了保险，很值"},
            "related": ["作业委托", "Essay写作"],
            "delivery_risk": "成绩评定主观性强、老师评分标准不同",
        },
        {
            "name": "降AI率",
            "fit": "使用AI辅助创作、担心被查出的学生",
            "not_fit": "完全不用AI的学生",
            "problem": "AI率过高，担心被学校处分",
            "price_logic": "按字数定价，通常100-300元/千字",
            "service_boundary": "降低AI检测率，不保证100%通过",
            "sales_script": "现在很多学校开始检测AI率，风险很大，我们可以帮你处理到安全范围",
            "objection": {"没问题的": "现在AI检测工具越来越厉害，不值得冒这个险"},
            "related": ["作业委托", "Essay写作"],
            "delivery_risk": "检测工具持续更新、学校政策变化",
        },
    ],
    "考试": [
        {
            "name": "考试助力",
            "fit": "有考试临近、需要针对性复习的学生",
            "not_fit": "考试还早、不需要针对复习的",
            "problem": "考试临近没把握，需要快速提分",
            "price_logic": "按课程/考试定价，通常500-2k/门",
            "service_boundary": "考前辅导和复习资料，不包含代考",
            "sales_script": "考试最后两周的针对性复习效果最好，我们有历年真题和解题思路",
            "objection": {"时间不够": "我们可以根据你剩余的时间制定最优复习方案"},
            "related": ["押题", "包过辅导"],
            "delivery_risk": "时间太短、学生基础太差",
        },
        {
            "name": "Final精准押题",
            "fit": "Final考试前1-2周的学生",
            "not_fit": "平时作业，非Final时期",
            "problem": "Final范围太广，不知道重点在哪",
            "price_logic": "按课程定价，通常300-1k/门",
            "service_boundary": "提供高概率考点预测，不保证押中",
            "sales_script": "我们分析了大量历年真题，命中率很高，很多同学都靠这个过关",
            "objection": {"押不中怎么办": "命中率有数据，同时押题也帮你系统复习了"},
            "related": ["考试助力", "包过辅导"],
            "delivery_risk": "出题老师变化、考题随机性",
        },
        {
            "name": "包过辅导",
            "fit": "有明确过线要求、愿意投入的学生",
            "not_fit": "追求高分、不是只求过线的",
            "problem": "害怕挂科补考或被退学",
            "price_logic": "按课程收费，通常比普通辅导贵50-100%",
            "service_boundary": "辅导+质保，不过退部分款",
            "sales_script": "包过套餐最大的价值是给你确定性，不用担心补考的麻烦和额外费用",
            "objection": {"太贵了": "算上可能的补考费用和重读代价，包过其实很划算"},
            "related": ["考试助力", "Final精准押题"],
            "delivery_risk": "学生不配合复习、基础太差",
        },
    ],
    "论文": [
        {
            "name": "Dissertation全流程",
            "fit": "本科毕业论文、硕士学位论文需要全程支持的学生",
            "not_fit": "只需要局部帮助的学生",
            "problem": "Dissertation体量大、周期长、不知道如何规划和推进",
            "price_logic": "按章节/总字数定价，通常1-3万",
            "service_boundary": "从开题到定稿，全程辅导和代写支持",
            "sales_script": "Dissertation是留学生最大的挑战，从选题到答辩，我们陪你走完全程",
            "objection": {"太贵": "Dissertation决定你的学位，这是最值得投资的地方"},
            "related": ["70+质检", "降AI率", "毕业无忧"],
            "delivery_risk": "导师要求变化、中途换题、时间紧张",
        },
        {
            "name": "毕业无忧",
            "fit": "面临毕业风险、学分不足或Dissertation受阻的学生",
            "not_fit": "学业正常、没有毕业风险的",
            "problem": "面临无法按时毕业的风险",
            "price_logic": "综合服务包，定制报价，通常2-5万",
            "service_boundary": "全面评估+针对性解决方案，不保证100%毕业",
            "sales_script": "毕业是最重要的事，一旦出现风险要尽快应对，我们帮你全面评估和制定方案",
            "objection": {"已经没救了": "只要还有时间，就有可能解决，我们见过更难的情况"},
            "related": ["Dissertation全流程", "包过辅导"],
            "delivery_risk": "学校政策、时间窗口极短",
        },
    ],
    "挂科/毕业风险": [
        {
            "name": "安心包",
            "fit": "有多门课程、担心学业风险的学生",
            "not_fit": "只有单门需求的学生",
            "problem": "多门课程同时有压力，担心顾此失彼",
            "price_logic": "按学期整体套餐定价，通常5-15k/学期",
            "service_boundary": "多课程协同辅导，优先级排序，不保证每门成绩",
            "sales_script": "安心包的好处是你不用每次都来谈，我们帮你统筹安排，一个价搞定整个学期",
            "objection": {"不需要这么多": "很多同学觉得只需要一两门，但学期中途总会突然有新需求"},
            "related": ["DP卓越安心包", "学年包", "毕业无忧"],
            "delivery_risk": "课程超出覆盖范围、老师资源不足",
        },
        {
            "name": "DP卓越安心包",
            "fit": "DP项目学生，有高分和稳定性双重需求",
            "not_fit": "非DP项目",
            "problem": "DP课程要求高，需要全方位支持",
            "price_logic": "专属DP定价，通常高于普通安心包20-30%",
            "service_boundary": "覆盖DP全部课程，重点科目重点保障",
            "sales_script": "DP项目是极致专长，我们有专门做DP的团队，口碑很好",
            "objection": {"普通安心包也能做": "DP有特殊要求，专业团队更有保障"},
            "related": ["安心包", "学年包"],
            "delivery_risk": "DP难度高、老师资源有限",
        },
    ],
    "高分需求": [
        {
            "name": "Assignment辅导",
            "fit": "想提升作业质量、追求高分的学生",
            "not_fit": "只求通过、不在意分数的",
            "problem": "自己写的作业不够好，想有人辅导提升",
            "price_logic": "按次/按学时定价，通常200-500元/小时",
            "service_boundary": "辅导指导，不代写",
            "sales_script": "我们的辅导不是帮你写，是帮你理解怎么写好，这样每次都能进步",
            "objection": {"只要完成就行": "现在的习惯决定你以后的GPA，值得投入"},
            "related": ["Essay写作", "70+质检"],
            "delivery_risk": "学生积极性、时间配合度",
        },
    ],
    "长期托管": [
        {
            "name": "学年包",
            "fit": "想整个学年都有保障的学生或家长",
            "not_fit": "只有短期单次需求的学生",
            "problem": "每次临时找人麻烦，想要稳定的全年支持",
            "price_logic": "按学年整体定价，打折幅度大，通常20-50k/学年",
            "service_boundary": "全学年覆盖，固定老师团队，优先响应",
            "sales_script": "学年包是最省心的选择，整个学年一个固定团队跟着你，不用每次重新找人",
            "objection": {"太贵了": "摊到每次的成本其实比单次买更便宜，而且有固定的人服务质量更好"},
            "related": ["安心包", "包课"],
            "delivery_risk": "学生转学、休学、专业变化",
        },
        {
            "name": "包课",
            "fit": "按课程批量购买服务的学生",
            "not_fit": "按次购买更合适的学生",
            "price_logic": "按课程数量折扣，5-10门课有优惠",
            "service_boundary": "固定课程范围内的全部支持",
            "sales_script": "包课比单买便宜，而且你这学期的课都定好了，可以一次性解决",
            "objection": {"不确定用多少": "可以先包核心几门，其他按需补充"},
            "related": ["学年包", "安心包"],
            "delivery_risk": "课程实际内容与预期不符",
        },
    ],
    "AI学习提升": [
        {
            "name": "AI学霸成长包",
            "fit": "想用AI工具提升学习效率、同时规避风险的学生",
            "not_fit": "完全排斥AI、或已被处分的学生",
            "problem": "不知道如何合规地使用AI工具辅助学习",
            "price_logic": "按套餐定价，通常1-3k",
            "service_boundary": "AI工具使用培训+合规写作技巧，不代写",
            "sales_script": "AI是未来的方向，关键是要用对方式，我们教你怎么合规用AI让学习更高效",
            "objection": {"自己会用": "合规使用AI有很多技巧，我们的方法可以让你事半功倍"},
            "related": ["降AI率", "Assignment辅导"],
            "delivery_risk": "学校政策变化、学生自律性",
        },
    ],
}

# 渠道清单
CHANNELS = ["小红书", "垂直号", "朋友圈", "社群", "老客户转介绍", "代理渠道"]

# 统一角色
ROLES = {
    "🎯 管理层": "管理层",
    "📢 推广/市场": "推广/市场",
    "💼 销售/顾问/学管": "销售/顾问/学管",
    "📦 产品/后台": "产品/后台",
    "⚙️ 系统管理": "系统",
}

DEPT_OPTIONS = ["管理层", "推广/市场", "销售/顾问/学管", "产品/后台", "交付/老师"]
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

ROLE_PAGES = {
    "🎯 管理层": [
        "📊 老板驾驶舱",
        "🔮 增长预测台",
        "🚀 新产品上线台",
        "🚦 产品红绿灯",
        "📈 归因分析台",
        "✅ 部门任务台",
        "🔁 每周复盘台",
    ],
    "📢 推广/市场": [
        "📡 渠道作战台",
        "📡 市场情报台",
        "🏫 学校增长情报台",
        "📈 产品推广策略台",
        "🎯 广告预测台",
        "📅 营销日历",
        "📝 内容池",
    ],
    "💼 销售/顾问/学管": [
        "💼 销售顾问作战台",
        "📦 产品目录与推荐台",
        "🗣️ 产品反馈台",
        "✅ 部门任务台",
    ],
    "📦 产品/后台": [
        "🚀 新产品上线台",
        "📦 产品目录与推荐台",
        "🧭 战略建议台",
        "📚 公司资料学习中心",
        "📈 归因分析台",
    ],
    "⚙️ 系统管理": [
        "🛠 Agent管理中心",
        "🤖 自动化工作流",
        "📁 数据资料中心",
        "🔧 系统诊断台",
        "✅ 执行监督台",
    ],
}

ROLE_SECTION_LABELS = {
    "🎯 管理层": "决策中心",
    "📢 推广/市场": "推广作战",
    "💼 销售/顾问/学管": "销售转化",
    "📦 产品/后台": "产品管理",
    "⚙️ 系统管理": "系统配置",
}

_requested_page = st.session_state.pop("_goto", None) or st.session_state.pop("page_jump", None)
if _requested_page:
    for _role_name, _role_pages in ROLE_PAGES.items():
        if _requested_page in _role_pages:
            st.session_state["active_role"] = _role_name
            st.session_state[f"nav_{_role_name}"] = _requested_page
            break

# ── 侧边栏 ────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:12px 0 4px 0">
      <div style="font-size:22px;font-weight:800;color:#f8fafc;letter-spacing:-0.5px">🎯 极致教育</div>
      <div style="font-size:13px;color:#64748b;margin-top:2px">增长作战系统 v11.0</div>
    </div>""", unsafe_allow_html=True)
    st.caption(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 角色选择（学管=顾问=销售，是同一个岗位）
    role = st.selectbox("👤 当前视角", list(ROLE_PAGES.keys()), label_visibility="visible", key="active_role")
    st.divider()

    st.markdown(
        f'<div style="font-size:11px;color:#94a3b8;font-weight:600;padding:2px 0 4px">{ROLE_SECTION_LABELS[role]}</div>',
        unsafe_allow_html=True,
    )
    page = st.radio("页面导航", ROLE_PAGES[role], label_visibility="collapsed", key=f"nav_{role}")

    st.divider()
    try:
        _sb_s30 = get_order_stats(days=30)
        _sb_s7  = get_order_stats(days=7)
        st.markdown("**📊 本月快讯**")
        st.caption(f"订单 {_sb_s30['total']}单 · 营收 元{int(_sb_s30['total_amount']/10000)}万")
        st.caption(f"近7天 {_sb_s7['total']}单")
    except:
        pass

    st.markdown("**⚡ 常用入口**")
    _q1, _q2 = st.columns(2)
    if _q1.button("上传数据", key="quick_data", width="stretch"):
        st.session_state["_goto"] = "📁 数据资料中心"
        st.rerun()
    if _q2.button("内容池", key="quick_content", width="stretch"):
        st.session_state["_goto"] = "📝 内容池"
        st.rerun()
    _q3, _q4 = st.columns(2)
    if _q3.button("上线台", key="quick_launch", width="stretch"):
        st.session_state["_goto"] = "🚀 新产品上线台"
        st.rerun()
    if _q4.button("Agent", key="quick_agent", width="stretch"):
        st.session_state["_goto"] = "🛠 Agent管理中心"
        st.rerun()


PAUSED_PAGE_ACTIONS = {
    "📡 渠道作战台": [
        ("补齐渠道来源", "到数据资料中心导入 leads.source_channel 或同步 CRM 渠道字段。", "📁 数据资料中心"),
        ("查看销售承接", "渠道数据未完整前，先让销售作战台跟进已有线索。", "💼 销售顾问作战台"),
        ("检查执行任务", "已有渠道任务可先在部门任务台继续推进。", "✅ 部门任务台"),
    ],
    "🔮 增长预测台": [
        ("导入订单数据", "补齐 orders.order_date、amount、product、sales_owner。", "📁 数据资料中心"),
        ("查看老板驾驶舱", "先使用真实订单聚合的经营快照。", "📊 老板驾驶舱"),
        ("检查产品状态", "用新产品上线台确认在途产品和阻断。", "🚀 新产品上线台"),
    ],
    "📡 市场情报台": [
        ("补齐市场信号", "先导入学校节点、考试周、需求反馈等 evidence。", "📁 数据资料中心"),
        ("查看渠道作战", "渠道页会提示当前缺哪些线索来源字段。", "📡 渠道作战台"),
        ("沉淀资料事实", "把市场资料先放入公司资料学习中心确认。", "📚 公司资料学习中心"),
    ],
    "🏫 学校增长情报台": [
        ("补齐学校字段", "订单和线索需要 school、country、product 等字段。", "📁 数据资料中心"),
        ("查看产品目录", "先确认不同学校适用的正式产品名称。", "📦 产品目录与推荐台"),
        ("上传学校资料", "学校节点、课程考核和历史案例需要先确认来源。", "📚 公司资料学习中心"),
    ],
    "🚦 产品红绿灯": [
        ("维护产品上线卡", "先补齐产品阶段、交付风险和销售边界。", "🚀 新产品上线台"),
        ("查看产品目录", "确认产品口径、适用场景和价格边界。", "📦 产品目录与推荐台"),
        ("导入订单证据", "红绿灯需结合订单、老师容量和客户反馈。", "📁 数据资料中心"),
    ],
    "🎯 广告预测台": [
        ("补齐投放数据", "需要渠道、线索、成交和历史活动数据。", "📁 数据资料中心"),
        ("先生成内容", "广告素材可先从内容池审核通过后复用。", "📝 内容池"),
        ("查看销售反馈", "用产品反馈台确认客户异议和投放风险。", "🗣️ 产品反馈台"),
    ],
    "🧭 战略建议台": [
        ("上传战略依据", "战略建议必须基于已确认资料、订单和风险证据。", "📚 公司资料学习中心"),
        ("看老板驾驶舱", "先从真实经营数据判断是否需要战略动作。", "📊 老板驾驶舱"),
        ("拆成执行任务", "已有战略方向可以先落到部门任务台。", "✅ 部门任务台"),
    ],
    "📈 归因分析台": [
        ("补齐来源字段", "线索和订单需要能按客户、学校或渠道匹配。", "📁 数据资料中心"),
        ("查看销售作战", "先处理当前可跟进线索和已成交客户。", "💼 销售顾问作战台"),
        ("沉淀复盘口径", "归因口径确定后再进入每周复盘。", "🔁 每周复盘台"),
    ],
    "📈 产品推广策略台": [
        ("补齐事实资料", "上传产品边界、销售话术、部门职责和风控表达。", "📚 公司资料学习中心"),
        ("准备销售素材", "先审核已有内容，再进入销售作战台使用。", "📝 内容池"),
        ("查看产品目录", "确认产品名称、适用场景和禁用承诺。", "📦 产品目录与推荐台"),
    ],
    "📅 营销日历": [
        ("导入学校节点", "营销日历需要官方校历、考试周和DDL节点。", "📁 数据资料中心"),
        ("查看市场情报", "市场情报台会展示资料缺口和校验状态。", "📡 市场情报台"),
        ("先建推广任务", "确定节点后可直接在部门任务台跟执行。", "✅ 部门任务台"),
    ],
    "📝 内容池": [
        ("生成推广素材", "先在推广策略台生成内容，再回到这里审核。", "📈 产品推广策略台"),
        ("上传事实资料", "素材必须基于已确认公司资料和产品边界。", "📚 公司资料学习中心"),
        ("销售先用现有素材", "已审核素材可在销售作战台直接复制使用。", "💼 销售顾问作战台"),
    ],
    "🔁 每周复盘台": [
        ("补齐本周订单", "复盘必须先有本周 orders 和 leads 数据。", "📁 数据资料中心"),
        ("处理未完成任务", "先看部门任务台的逾期、阻断和执行状态。", "✅ 部门任务台"),
        ("看实时经营快照", "老板驾驶舱提供不含 AI 推断的实时情况。", "📊 老板驾驶舱"),
    ],
}


def _show_no_data_page(page_name: str, reason: str = ""):
    st.title(page_name)
    st.markdown(
        f"""
        <div class="empty-card">
          <div class="empty-card-title">当前页面已进入安全暂停状态</div>
          <div class="empty-card-desc">{NO_DATA_MESSAGE} {reason or ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### 现在可以做什么")
    actions = PAUSED_PAGE_ACTIONS.get(page_name, [
        ("补齐真实数据", "导入订单、线索、产品资料或部门事实后再生成结论。", "📁 数据资料中心"),
        ("查看经营快照", "先使用老板驾驶舱里基于真实数据的只读指标。", "📊 老板驾驶舱"),
        ("处理执行事项", "可先推进已有任务和产品上线卡。", "✅ 部门任务台"),
    ])
    cols = st.columns(len(actions))
    for idx, (title, body, target_page) in enumerate(actions):
        with cols[idx]:
            st.markdown(
                f"""
                <div class="status-card">
                  <div class="status-card-title">{title}</div>
                  <div class="status-card-body">{body}</div>
                  <div class="status-card-foot">跳转到：{target_page}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("前往", key=f"paused_goto_{page_name}_{idx}", width="stretch"):
                st.session_state["_goto"] = target_page
                st.rerun()


PAUSED_UNTRUSTED_PAGES = {
    "📡 渠道作战台": "渠道频次、主题和推广任务未接入真实渠道数据契约，暂停输出推广建议。",
    "🔮 增长预测台": "预测页面数据契约未重建，暂停输出增长结论。",
    "📡 市场情报台": "市场情报来源未完成 evidence 校验，暂停输出市场判断。",
    "🏫 学校增长情报台": "学校策略卡和内容建议未完成 evidence 校验，暂停输出学校推广结论。",
    "🚦 产品红绿灯": "产品红绿灯需重新接入产品目录、订单、老师容量和风险证据，暂停输出推广边界。",
    "🎯 广告预测台": "广告预测依赖评分模型和历史数据校验，暂停输出预测区间。",
    "🧭 战略建议台": "战略建议必须含 evidence/confidence/responsible_role，旧数据未完成校验。",
    "📈 归因分析台": "归因字段和角色来源未完成校验，暂停输出归因结论。",
    "📈 产品推广策略台": "旧策略页含 AI/fallback 输出，暂停正式展示。",
    "📅 营销日历": "营销日历含推广节奏建议，未完成真实节点 evidence 校验，暂停正式展示。",
    "📝 内容池": "内容池含创作优先级和素材建议，未完成 guardrails 校验，暂停正式展示。",
    "🔁 每周复盘台": "每周复盘含 AI 结论，未完成统一输出契约校验，暂停正式展示。",
}

if page in PAUSED_UNTRUSTED_PAGES:
    _show_no_data_page(page, PAUSED_UNTRUSTED_PAGES[page])
    page = "__paused_no_data__"


# ══════════════════════════════════════════════════════════════════════════════
# 通用工具：AI建议→任务（所有页面共用，必须在 if/elif 链之前定义）
# ══════════════════════════════════════════════════════════════════════════════
def _create_task_from_suggestion(title, desc, dept, owner="", deadline_days=7,
                                  source_agent="", product="", channel="",
                                  priority="高", success_criteria="", review_metric=""):
    """统一任务创建函数 - 11个字段写入 tasks 表"""
    from datetime import datetime as _cdt, timedelta as _ctd
    if product:
        _products = [p.strip() for p in str(product).replace("/", "、").split("、") if p.strip()]
        _bad_products = [p for p in _products if not validate_product(p).get("valid")]
        if _bad_products:
            st.error("产品目录校验失败，无法创建任务。")
            return None
    deadline = (_cdt.now() + _ctd(days=deadline_days)).strftime("%Y-%m-%d")
    full_desc = (
        f"{desc}\n\n"
        f"━━ 任务详情 ━━\n"
        f"来源Agent：{source_agent or 'AI建议'}\n"
        f"关联产品：{product or '待确认'}\n"
        f"关联渠道：{channel or '待确认'}\n"
        f"完成标准：{success_criteria or '按计划完成'}\n"
        f"复盘指标：{review_metric or '完成率、结果数据'}"
    )
    tid = save_task({
        "title": title,
        "description": full_desc,
        "department": dept,
        "assignee": owner,
        "due_date": deadline,
        "priority": priority,
        "status": "todo",
        "source": source_agent or "AI建议",
        "tags": f"{product},{channel}".strip(","),
    })
    return tid


# ══════════════════════════════════════════════
# 页面：市场情报台
# ══════════════════════════════════════════════
if page == "📡 渠道作战台":
    import pandas as _pd_ch
    import datetime as _ch_dt

    st.markdown("## 📡 渠道作战台")
    st.caption("6大渠道本周运营状态 · 推广任务和建议必须来自真实订单/线索 evidence")

    try:
        _ch_s7  = get_order_stats(days=7)
        _ch_s30 = get_order_stats(days=30)
        _ch_orders7 = list_orders(days=7, limit=500)
        _ch_leads7 = list_leads(days=7, limit=500)
        _ch_now = _ch_dt.datetime.now()
        _ch_week_start = (_ch_now - _ch_dt.timedelta(days=_ch_now.weekday())).strftime('%Y-%m-%d')

        # 产品建议（取本周热门前3）
        _ch_prod7 = []
        for _p, _cnt in sorted(_ch_s7['by_product'], key=lambda x: -x[1])[:10]:
            _vp = validate_product(_p)
            if _vp.get("valid"):
                _ch_prod7.append((_vp["product_name"], _cnt))
            if len(_ch_prod7) >= 3:
                break
        _ch_hot_prods = "、".join([p for p, _ in _ch_prod7])
    except Exception as _e_ch:
        st.error(f"数据加载：{_e_ch}")
        st.stop()

    if not _ch_orders7 and not _ch_leads7:
        st.info(NO_DATA_MESSAGE)
        st.stop()

    _ch_config = {
        "小红书": {
            "icon": "📕",
            "desc": "主要线索来源渠道，重点目标人群：准留学生、在读留学生",
            "content_theme": "需根据真实线索/订单确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
        "垂直号": {
            "icon": "📱",
            "desc": "专业留学辅导公众号，深度内容，建立信任",
            "content_theme": "需根据真实线索/订单确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
        "朋友圈": {
            "icon": "👥",
            "desc": "顾问/学管个人朋友圈，转化率高",
            "content_theme": "需根据真实线索/订单确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
        "社群": {
            "icon": "💬",
            "desc": "学生社群运营，维护老客户，激活转介绍",
            "content_theme": "需根据真实线索/订单确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
        "老客户转介绍": {
            "icon": "🤝",
            "desc": "老客户口碑传播，成本低、信任度高",
            "content_theme": "需根据老客真实订单确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
        "代理渠道": {
            "icon": "🏢",
            "desc": "B端代理商合作，批量获客",
            "content_theme": "需根据代理渠道真实数据确定",
            "push_freq": "需根据真实运营计划确定",
            "主推产品": _ch_hot_prods or NO_DATA_MESSAGE,
        },
    }

    for _ch_name, _ch_info in _ch_config.items():
        with st.expander(f"{_ch_info['icon']} **{_ch_name}** — {_ch_info['desc']}", expanded=True):
            _ccc1, _ccc2, _ccc3 = st.columns([2, 2, 1])

            with _ccc1:
                st.markdown("**本周任务**")
                st.markdown(f"• 主题：{_ch_info['content_theme']}")
                st.markdown(f"• 频次：{_ch_info['push_freq']}")
                st.markdown(f"• 主推产品：{_ch_info['主推产品']}")
                st.caption("evidence: orders/leads 近7天真实记录")

            with _ccc2:
                st.markdown("**本周数据**")
                _ch_leads = st.number_input(f"线索数", 0, 10000, 0, key=f"ch_lead_{_ch_name}", label_visibility="visible")
                _ch_deals = st.number_input(f"成交数", 0, 1000, 0, key=f"ch_deal_{_ch_name}", label_visibility="visible")
                if _ch_leads > 0:
                    st.caption(f"转化率：{_ch_deals/_ch_leads:.0%}")

            with _ccc3:
                st.markdown("**操作**")
                if st.button(f"📋 创建任务", key=f"ch_task_{_ch_name}"):
                    if not _ch_hot_prods:
                        st.info(NO_DATA_MESSAGE)
                        st.stop()
                    _create_task_from_suggestion(
                        title=f"{_ch_name}本周推广任务",
                        desc=f"渠道：{_ch_name}\n主题：{_ch_info['content_theme']}\n频次：{_ch_info['push_freq']}\n主推产品：{_ch_info['主推产品']}",
                        dept="推广/市场", deadline_days=7,
                        source_agent="渠道作战台", channel=_ch_name,
                        product=_ch_info['主推产品'], priority="高",
                        success_criteria=f"完成{_ch_info['push_freq']}的内容发布",
                        review_metric="线索数、成交数、转化率"
                    )
                    st.success("已创建！")
                if st.button(f"💡 优化建议", key=f"ch_opt_{_ch_name}"):
                    st.info(NO_DATA_MESSAGE)

            st.divider()

    # 渠道横向对比
    st.markdown("### 📊 渠道横向对比（本周）")
    _ch_summary_rows = []
    for _ch_name in _ch_config:
        _ch_summary_rows.append({"渠道": _ch_name, "主推产品": _ch_config[_ch_name]["主推产品"][:20], "发布频次": _ch_config[_ch_name]["push_freq"], "内容方向": _ch_config[_ch_name]["content_theme"][:20]})
    st.dataframe(_pd_ch.DataFrame(_ch_summary_rows), width='stretch', hide_index=True)

    # 生成本周渠道总任务
    if st.button("📋 一键生成本周所有渠道任务", type="primary"):
        if not _ch_hot_prods:
            st.info(NO_DATA_MESSAGE)
            st.stop()
        for _ch_n, _ch_i in _ch_config.items():
            _create_task_from_suggestion(
                title=f"{_ch_n}本周推广任务",
                desc=f"渠道：{_ch_n}\n主题：{_ch_i['content_theme']}\n主推：{_ch_i['主推产品']}",
                dept="推广/市场", deadline_days=7, source_agent="渠道作战台",
                channel=_ch_n, product=_ch_i['主推产品'], priority="高",
            )
        st.success(f"✅ 已创建6个渠道本周任务！前往「部门任务台」查看")

elif page == "💼 销售顾问作战台":
    import pandas as _pd_sales
    import datetime as _sales_dt

    st.markdown("## 💼 销售顾问作战台")
    st.caption("学管/顾问/销售 — 统一入口。今日应该跟谁、推什么、怎么说。")

    try:
        _sl_s7  = get_order_stats(days=7)
        _sl_s30 = get_order_stats(days=30)
        _sl_ls30 = get_lead_stats(days=30)

        # 近7天成交数据
        _sl_orders7 = list_orders(days=7, limit=200)
        _sl_leads30 = list_leads(days=30, limit=500) if 'list_leads' in dir() else []

        # 顾问本周排行
        _sl_owner = {}
        for _o in _sl_orders7:
            _own = (_o.get('sales_owner') or '未分配').split()[0]
            _sl_owner.setdefault(_own, {'cnt':0,'amt':0})
            _sl_owner[_own]['cnt'] += 1
            _sl_owner[_own]['amt'] += _o.get('amount') or 0

    except Exception as _e_sl:
        st.error(f"数据加载：{_e_sl}")
        st.stop()

    # ── 今日战情 ──
    _sl_c1, _sl_c2, _sl_c3, _sl_c4 = st.columns(4)
    _sl_c1.metric("本周成交", f"{_sl_s7['total']}单")
    _sl_c2.metric("本周营收", f"元{int(_sl_s7['total_amount']/10000)}万")
    _sl_c3.metric("本月线索", f"{_sl_ls30.get('total',0)}条")
    _sl_c4.metric("转化率", f"{_sl_ls30.get('conversion_rate',0):.0%}")

    st.divider()

    # ── 顾问排行 ──
    st.markdown("### 👥 本周顾问排行（谁在做，谁需要支持）")
    if _sl_owner:
        _sl_rank_rows = []
        for _rank, (_own, _d) in enumerate(sorted(_sl_owner.items(), key=lambda x: -x[1]['amt']), 1):
            _sl_avg = int(_d['amt'] / max(_d['cnt'], 1))
            _sl_rank_rows.append({
                '排名': f"{'🥇' if _rank==1 else '🥈' if _rank==2 else '🥉' if _rank==3 else str(_rank)}",
                '顾问': _own,
                '本周单量': _d['cnt'],
                '本周营收': f"元{int(_d['amt']):,}",
                '客单价': f"元{_sl_avg:,}",
                '状态': '🔥 超额' if _d['cnt'] >= 5 else ('⚠️ 需关注' if _d['cnt'] <= 1 else '✅ 正常'),
            })
        st.dataframe(_pd_sales.DataFrame(_sl_rank_rows), width='stretch', hide_index=True)

    st.divider()

    # ── 今日产品推荐 ──
    st.markdown("### 🎯 今日产品线索（只显示真实成交产品）")

    # 取本周最热产品
    _sl_prod7 = []
    for _raw_prod, _cnt in sorted(_sl_s7['by_product'], key=lambda x: -x[1])[:10]:
        _vp = validate_product(_raw_prod)
        if _vp.get("valid"):
            _sl_prod7.append((_vp["product_name"], _cnt, _vp["canonical_product_id"]))
        if len(_sl_prod7) >= 5:
            break
    if not _sl_prod7:
        st.info(NO_DATA_MESSAGE)

    for _sl_prod_name, _sl_cnt, _sl_pid in _sl_prod7:
        with st.expander(f"**{_sl_prod_name}** — 本周 {_sl_cnt} 单", expanded=(_sl_prod7.index((_sl_prod_name, _sl_cnt, _sl_pid)) == 0)):
            st.markdown(f"真实成交：**{_sl_cnt}** 单")
            st.caption(f"evidence: orders.product={_sl_pid};count={_sl_cnt}")
            st.info("销售话术需来自已审核知识库或经过 evidence 校验的 AI 建议；当前不展示未校验话术。")

    st.divider()

    # ── AI销售建议 ──
    st.markdown("### 💡 今日销售行动建议")
    try:
        _sl_suggs = list_suggestions(suggestion_type="weekly_sales_suggestion_v2", limit=3)
        if _sl_suggs:
            for _i, _sg in enumerate(_sl_suggs[:3]):
                _sg_text = (_sg.get('recommendation') or _sg.get('content') or '')[:500]
                _sg_date = (_sg.get('created_at') or '')[:10]
                with st.expander(f"建议{_i+1} — {_sg_date}", expanded=(_i==0)):
                    st.markdown(_sg_text)
                    st.markdown("---")
                    _sg_c1, _sg_c2, _sg_c3 = st.columns(3)
                    _sg_owner = _sg_c1.text_input("负责人", "", key=f"sl_sg_own_{_i}")
                    _sg_prod  = _sg_c2.selectbox("关联产品", [""] + list(PRODUCT_ZH.values()), key=f"sl_sg_prod_{_i}")
                    _sg_ch    = _sg_c3.selectbox("关联渠道", [""] + CHANNELS, key=f"sl_sg_ch_{_i}")
                    if st.button(f"📋 转任务", key=f"sl_sg_task_{_i}", type="secondary"):
                        _create_task_from_suggestion(
                            title=_sg_text[:50],
                            desc=_sg_text,
                            dept="销售部",
                            owner=_sg_owner,
                            deadline_days=7,
                            source_agent="weekly_sales_suggestion_v2",
                            product=_sg_prod,
                            channel=_sg_ch,
                            priority="高",
                            success_criteria="本周完成相关跟进",
                            review_metric="成交数、成交额"
                        )
                        st.success("✅ 任务已写入部门任务台！")
        else:
            st.info("销售建议每周一自动生成，暂无数据")
    except Exception as _e_sl_sg:
        st.caption(f"建议加载：{_e_sl_sg}")

    st.divider()

    # ── 产品目录快查 ──
    st.markdown("### 📦 快速查产品（按客户问题推荐）")
    _sl_cat = st.selectbox("客户的问题是：", list(PRODUCT_CATALOG.keys()), key="sl_cat")
    if _sl_cat:
        for _sl_p in PRODUCT_CATALOG.get(_sl_cat, []):
            st.markdown(f"**✅ 推荐：{_sl_p['name']}**")
            st.markdown(f"• 适合：{_sl_p.get('fit','')}")
            st.markdown(f"• 话术：{_sl_p.get('sales_script','')}")
            st.markdown("---")

elif page == "📦 产品目录与推荐台":
    import pandas as _pd_pcat

    st.markdown("## 📦 产品目录与推荐台")
    st.caption("正式页面只展示 PRODUCT_CATALOG 中锁定产品；推荐必须来自真实线索/订单 evidence。")

    _pcat_tab1, _pcat_tab2 = st.tabs(["锁定产品目录", "真实数据推荐"])

    with _pcat_tab1:
        _pcat_rows = []
        for _p in _CATALOG_PRODUCTS:
            _pcat_rows.append({
                "产品ID": _p.get("id", ""),
                "产品名称": _p.get("name", ""),
                "产品说明": _p.get("desc", ""),
                "价格口径": _p.get("price_range", ""),
                "别名": "、".join(_p.get("aliases", [])[:5]),
            })
        if _pcat_rows:
            st.dataframe(_pd_pcat.DataFrame(_pcat_rows), width="stretch", hide_index=True)
        else:
            st.info(NO_DATA_MESSAGE)

    with _pcat_tab2:
        _real_leads = list_leads(days=90, limit=1000)
        _real_orders = list_orders(days=90, limit=1000)
        if not _real_leads and not _real_orders:
            st.info(NO_DATA_MESSAGE)
        else:
            _rec_rows = {}
            for _lead in _real_leads:
                _raw = _lead.get("product_interest")
                _v = validate_product(_raw)
                if not _v.get("valid"):
                    continue
                _pid = _v.get("product_id")
                _rec_rows.setdefault(_pid, {"产品": _v.get("product_name"), "线索数": 0, "订单数": 0, "成交额": 0.0, "evidence": []})
                _rec_rows[_pid]["线索数"] += 1
                _rec_rows[_pid]["evidence"].append(f"lead_id={_lead.get('id')}")
            for _order in _real_orders:
                _raw = _order.get("product")
                _v = validate_product(_raw)
                if not _v.get("valid"):
                    continue
                _pid = _v.get("product_id")
                _rec_rows.setdefault(_pid, {"产品": _v.get("product_name"), "线索数": 0, "订单数": 0, "成交额": 0.0, "evidence": []})
                _rec_rows[_pid]["订单数"] += 1
                _rec_rows[_pid]["成交额"] += float(_order.get("amount") or 0)
                _rec_rows[_pid]["evidence"].append(f"order_id={_order.get('id')}")

            if not _rec_rows:
                st.info(NO_DATA_MESSAGE)
            else:
                _out_rows = []
                for _pid, _r in sorted(_rec_rows.items(), key=lambda x: (x[1]["订单数"], x[1]["线索数"]), reverse=True):
                    _confidence = "high" if _r["订单数"] >= 3 else "medium" if _r["订单数"] or _r["线索数"] >= 3 else "low"
                    _out_rows.append({
                        "产品": _r["产品"],
                        "线索数": _r["线索数"],
                        "订单数": _r["订单数"],
                        "成交额": round(_r["成交额"], 2),
                        "evidence": "、".join(_r["evidence"][:8]),
                        "confidence": _confidence,
                        "responsible_role": "销售/顾问/学管",
                    })
                st.dataframe(_pd_pcat.DataFrame(_out_rows), width="stretch", hide_index=True)
    st.stop()

elif page == "🏫 学校增长情报台":
    st.title("🏫 学校增长情报台")
    st.caption("基于内部真实数据的学校机会评分与策略卡 · 不含任何外部编造信息")

    # ══ Section 0：学校热度总览（实时订单数据）══════════════════════════════
    try:
        _s_all = get_order_stats(days=0)
        _s_30  = get_order_stats(days=30)
        _s_90  = get_order_stats(days=90)
        _sch_all = dict(_s_all['by_school'])
        _sch_30  = dict(_s_30['by_school'])
        _sch_90  = dict(_s_90['by_school'])
        _sch_rev = dict(_s_all.get('revenue_by_school', []))
        _valid_schools = [s for s, _ in _s_all['by_school'] if _is_valid_school(s)][:20]

        st.markdown("### 📊 学校热度总览（全量数据）")
        cols = st.columns(4)
        for i, sch in enumerate(_valid_schools[:4]):
            cols[i].metric(sch[:8], f"{_sch_all[sch]}单", delta=f"近30天{_sch_30.get(sch,0)}单")

        st.markdown("#### Top20学校完整排行")
        import pandas as _pd_sch_inf
        _sch_rows = []
        for i, sch in enumerate(_valid_schools[:20], 1):
            cnt_all = _sch_all.get(sch, 0)
            cnt_30  = _sch_30.get(sch, 0)
            cnt_90  = _sch_90.get(sch, 0)
            rev     = _sch_rev.get(sch, 0)
            trend   = "↑热门" if cnt_30 >= cnt_90/3 else "→稳定"
            _sch_rows.append({'排名': i, '学校': sch, '总单量': cnt_all, '近30天': cnt_30, '近90天': cnt_90, '总营收': f"元{int(rev):,}", '趋势': trend})
        if _sch_rows:
            st.dataframe(_pd_sch_inf.DataFrame(_sch_rows), width='stretch', hide_index=True)

        # Section 3：各学校主力产品
        st.markdown("#### 📦 各学校主力产品分析")
        try:
            _sch_orders = list_orders(days=365, limit=5000)
            _sch_prod_cnt: dict = {}
            for _so in _sch_orders:
                _ss = _so.get('school') or ''
                _sp = _so.get('product') or '未知'
                if not _is_valid_school(_ss): continue
                _sch_prod_cnt.setdefault(_ss, {})
                _sch_prod_cnt[_ss][_sp] = _sch_prod_cnt[_ss].get(_sp, 0) + 1
            for sch in _valid_schools[:10]:
                _prods = _sch_prod_cnt.get(sch, {})
                if not _prods: continue
                _top_prods = sorted(_prods.items(), key=lambda x: -x[1])[:5]
                with st.expander(f"**{sch}** — 近1年主力产品"):
                    for _pn, _pc in _top_prods:
                        st.markdown(f"- {_pn}：**{_pc}** 单")
        except Exception as _e_sp:
            st.info(f"产品分析加载中：{_e_sp}")

        # ── Section：课程作业/考试DDL情报 ──────────────────────────────
        st.markdown("---")
        st.markdown("### 📝 热门专业作业/考试 DDL 情报")
        st.caption("覆盖澳洲+英国热门专业（商科/CS/法律/心理），数据来源：课程大纲+模式推断")

        try:
            from database.crud import list_course_assessments
            _ca_filter_cols = st.columns(4)
            _ca_school  = _ca_filter_cols[0].selectbox("学校", ["全部"] + [
                "新南威尔士大学", "悉尼大学", "墨尔本大学", "莫纳什大学Monash", "昆士兰大学",
                "伦敦大学学院UCL", "曼彻斯特大学", "利兹大学", "谢菲尔德大学", "伦敦国王学院KCL",
                "伯明翰大学",
            ], key="ca_school")
            _ca_major   = _ca_filter_cols[1].selectbox("专业类别", ["全部", "商科", "CS/IT", "法律", "心理", "工程"], key="ca_major")
            _ca_atype   = _ca_filter_cols[2].selectbox("考核类型", ["全部", "assignment", "exam", "quiz", "project"], key="ca_atype")
            _ca_days    = _ca_filter_cols[3].selectbox("时间范围", ["全部", "60天内", "90天内", "180天内"], key="ca_days")

            _ca_days_val = None
            if _ca_days == "60天内": _ca_days_val = 60
            elif _ca_days == "90天内": _ca_days_val = 90
            elif _ca_days == "180天内": _ca_days_val = 180

            _ca_data = list_course_assessments(
                school=None if _ca_school == "全部" else _ca_school,
                major_category=None if _ca_major == "全部" else _ca_major,
                assessment_type=None if _ca_atype == "全部" else _ca_atype,
                days_ahead=_ca_days_val,
                limit=300,
            )

            if _ca_data:
                import pandas as _pd_ca
                _ca_rows = []
                _today_str = date.today().isoformat()
                for _ca in _ca_data:
                    _due = _ca.get("due_date") or ""
                    _days_left = ""
                    if _due:
                        try:
                            _d = (datetime.strptime(_due, "%Y-%m-%d").date() - date.today()).days
                            _days_left = f"{_d}天后" if _d >= 0 else f"已过{-_d}天"
                        except Exception:
                            pass
                    _type_label = {"exam": "🎯期末考", "assignment": "📄作业", "quiz": "📝测验", "project": "🔧项目", "presentation": "🎤展示"}.get(_ca.get("assessment_type",""), _ca.get("assessment_type",""))
                    _ca_rows.append({
                        "学校": _ca.get("school",""),
                        "课程代码": _ca.get("subject_code",""),
                        "课程名": (_ca.get("subject_name","") or "")[:25],
                        "专业": _ca.get("major_category",""),
                        "学期": _ca.get("semester",""),
                        "考核": _type_label,
                        "任务名": (_ca.get("assessment_name","") or "")[:30],
                        "截止日期": _due,
                        "距今": _days_left,
                        "周次": _ca.get("due_week",""),
                        "权重": f"{int(_ca.get('weight_pct') or 0)}%" if _ca.get("weight_pct") else "",
                        "来源": _ca.get("source",""),
                    })
                _ca_df = _pd_ca.DataFrame(_ca_rows)
                st.dataframe(_ca_df, width='stretch', hide_index=True,
                             column_config={
                                 "截止日期": st.column_config.DateColumn("截止日期", format="YYYY-MM-DD"),
                                 "权重": st.column_config.TextColumn("权重"),
                             })
                st.caption(f"共 {len(_ca_rows)} 条记录 · 覆盖 {len(set(r['学校'] for r in _ca_rows))} 所学校 {len(set(r['课程代码'] for r in _ca_rows))} 门课程")

                # 快速洞察：未来30天高压节点
                _upcoming_exams = [r for r in _ca_rows if "期末考" in r["考核"] and "天后" in r["距今"]
                                    and int(r["距今"].replace("天后","")) <= 30]
                _upcoming_ass   = [r for r in _ca_rows if "作业" in r["考核"] and "天后" in r["距今"]
                                    and int(r["距今"].replace("天后","")) <= 30]
                if _upcoming_exams or _upcoming_ass:
                    st.warning(f"⚠️ 未来30天高压节点：**{len(_upcoming_exams)} 场期末考** · **{len(_upcoming_ass)} 个作业截止** — 这是最佳触达时机！")
            else:
                st.info("暂无课程考核数据。运行 `python agents/course_assessment_scraper.py --seed` 填充基础数据。")

        except Exception as _e_ca:
            st.info(f"课程考核数据加载中：{_e_ca}")

        st.divider()
    except Exception as _e_sch_inf:
        st.warning(f"学校情报数据加载中：{_e_sch_inf}")

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
    } for i, s in enumerate(_filtered)]), width='stretch', hide_index=True)

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
            if _gcols[_i].button(_label, key=f"gen_school_{_ctype}", width='stretch'):
                with st.spinner(f"基于 {_sel} 策略卡生成{_label}..."):
                    try:
                        from services.llm import LLMRouter as _LLMRouter2
                        _llm2 = _LLMRouter2()
                        _gp = (f"你是教育机构推广文案专家。基于以下学校策略卡，生成3条具体的{_label}。\n"
                               f"学校：{_sel}（{_card['country']}）阶段：{_card['current_stage']}\n"
                               f"P0主推：{_card['main_product']}；次推：{_card['secondary_products']}\n"
                               f"推广建议：{json.dumps(_card['marketing_suggestions'], ensure_ascii=False)}\n"
                               f"销售建议：{json.dumps(_card['sales_suggestions'], ensure_ascii=False)}\n"
                               f"风险约束：{json.dumps(_card['risk_notes'], ensure_ascii=False)}\n"
                               f"要求：紧扣该校当前阶段和主推产品，不泛泛而谈；禁止'100%押中/保过'类承诺；"
                               f"每条之间用'---'分隔。")
                        _resp2 = _llm2.chat(_gp, max_tokens=1500, task_type="content_generation")
                        _body = (_resp2.text or "生成失败，请重试").strip()
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

        # 运行统计（调用次数、平均耗时、质量评分）
        _all_runs = list_agent_runs(days=30, limit=500)
        _run_stats = {}
        for _r in _all_runs:
            _an = _r.get("agent_name","")
            if _an not in _run_stats:
                _run_stats[_an] = {"count":0,"total_dur":0,"success":0,"failed":0}
            _run_stats[_an]["count"] += 1
            _run_stats[_an]["total_dur"] += float(_r.get("duration_seconds") or 0)
            if _r.get("status") == "success": _run_stats[_an]["success"] += 1
            if _r.get("status") == "failed":  _run_stats[_an]["failed"] += 1

        _all_fbs2 = list_agent_feedbacks(limit=200)
        _fb_scores = {}
        for _fb in _all_fbs2:
            _an = _fb.get("agent_name","")
            if _an not in _fb_scores:
                _fb_scores[_an] = {"usefulness":[],"accuracy":[],"actionability":[]}
            if _fb.get("usefulness_score"): _fb_scores[_an]["usefulness"].append(_fb["usefulness_score"])
            if _fb.get("accuracy_score"):   _fb_scores[_an]["accuracy"].append(_fb["accuracy_score"])
            if _fb.get("actionability_score"): _fb_scores[_an]["actionability"].append(_fb["actionability_score"])

        _rows = []
        for _name, _info in _reg.items():
            _lr = _last.get(_name, {})
            if _f_layer != "全部" and _info["layer"] != _f_layer: continue
            if _f_status != "全部" and _info["status"] != _f_status: continue
            if _f_en != "全部" and _info["enabled"] != (_f_en == "启用"): continue
            if _f_llm != "全部" and _info["uses_llm"] != (_f_llm == "是"): continue
            if _f_fail == "仅失败" and _lr.get("status") != "failed": continue
            _rs = _run_stats.get(_name, {})
            _fbs2 = _fb_scores.get(_name, {})
            _avg_dur = _rs["total_dur"] / max(_rs["count"],1) if _rs.get("count") else 0
            _avg_score = (
                sum(_fbs2.get("usefulness",[0]) + _fbs2.get("accuracy",[]) + _fbs2.get("actionability",[])) /
                max(len(_fbs2.get("usefulness",[])) + len(_fbs2.get("accuracy",[])) + len(_fbs2.get("actionability",[])), 1)
            ) if _fbs2 else 0
            _rows.append({
                "Agent": _name, "中文名": _info["display_name"], "层级": _info["layer"],
                "职责": _info["description"][:35],
                "状态": {"active":"🟢 active","paused":"⏸️ paused","deprecated":"🚫 deprecated","experimental":"🧪 exp"}.get(_info["status"],_info["status"]),
                "启用": "✅" if _info["enabled"] else "❌",
                "LLM": "✅" if _info["uses_llm"] else "—",
                "30天调用": _rs.get("count", 0),
                "成功率": f"{int(_rs['success']/_rs['count']*100)}%" if _rs.get("count") else "—",
                "均耗时(s)": f"{_avg_dur:.1f}" if _avg_dur else "—",
                "质量评分": f"{_avg_score:.1f}/5" if _avg_score else "—",
                "最近运行": str(_lr.get("at", "从未"))[:16],
                "最近结果": {"success":"✅","failed":"❌","skipped":"⏭️"}.get(_lr.get("status",""),"—") + (_lr.get("status","") or ""),
            })
        st.dataframe(pd.DataFrame(_rows), width='stretch', hide_index=True)

        if not _all_runs:
            st.info("Agent运行记录将在自动化任务执行后显示。计划时间：每日08:30（每日任务）、周一09:00（周度任务）、月初09:00（月度任务）。")
            st.markdown("### ⏰ 自动化任务时间表")
            import pandas as _pd_ag
            _schedule_rows = [
                {'任务': '每日有效提醒', '运行时间': '每天 08:30', '功能': '生成今日销售提醒和风险预警'},
                {'任务': '产品供给风险', '运行时间': '每天 08:30', '功能': '分析产品库存和交付风险'},
                {'任务': '风险巡检', '运行时间': '每天 08:30', '功能': '扫描异常订单和逾期风险'},
                {'任务': '周度增长简报', '运行时间': '每周一 09:00', '功能': '汇总上周数据生成增长报告'},
                {'任务': '市场推广建议', '运行时间': '每周一 09:00', '功能': '基于数据生成下周推广策略'},
                {'任务': '销售行动建议', '运行时间': '每周一 09:00', '功能': '针对每位顾问生成行动清单'},
                {'任务': '归因分析', '运行时间': '每周一 09:00', '功能': '分析渠道、产品、学校转化归因'},
                {'任务': '增长预测', '运行时间': '每周一 09:00', '功能': '预测下周各学校×产品咨询量'},
                {'任务': '月度推广策略', '运行时间': '每月1日 09:00', '功能': '生成当月完整推广方案'},
                {'任务': '企业微信日报', '运行时间': '每天 14:00', '功能': '推送当日数据摘要至微信群'},
            ]
            st.dataframe(_pd_ag.DataFrame(_schedule_rows), width='stretch', hide_index=True)

        # 快速统计
        _act_count = sum(1 for r in _rows if "✅" in r["启用"])
        _tot_calls  = sum(r["30天调用"] for r in _rows)
        _mc1,_mc2,_mc3 = st.columns(3)
        _mc1.metric("启用Agent数", _act_count)
        _mc2.metric("30天总调用", _tot_calls)
        _mc3.metric("有质量评分", sum(1 for r in _rows if r["质量评分"] != "—"))

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
            } for l in _logs]), width='stretch', hide_index=True)

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
            } for f in _fbs]), width='stretch', hide_index=True)

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
    # ── 一键刷新信号 ─────────────────────────────
    col_btn, col_tip = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 刷新市场信号", type="primary", width='stretch'):
            with st.spinner("正在分析市场数据（约20秒）..."):
                try:
                    import yaml as _yaml_mkt
                    with open(ROOT / "config.yaml") as _f_mkt:
                        _cfg_mkt = _yaml_mkt.safe_load(_f_mkt)
                    from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
                    _r_mkt = SchoolOpportunityScoringAgent(_cfg_mkt).run()
                    st.success(f"✅ 市场信号已更新，评分学校数：{len(_r_mkt) if isinstance(_r_mkt, list) else '—'}")
                    st.rerun()
                except Exception as e:
                    st.error(f"更新失败：{e}")
    with col_tip:
        st.info("系统每天08:30自动更新市场信号，也可手动点击刷新。")

    st.divider()

    # ── KPI 行 ────────────────────────────────
    os7  = get_order_stats(days=7)
    os30 = get_order_stats(days=30)
    ls7  = get_lead_stats(days=7)
    ls30 = get_lead_stats(days=30)

    _os_all = get_order_stats(days=0)
    _ls_all = get_lead_stats(days=0)
    kc = st.columns(6)
    _kpi(kc[0], f"{_os_all['total']:,}", "历史总订单",  "#3b82f6")
    _kpi(kc[1], os30["total"],           "近30天订单",  "#6366f1")
    _kpi(kc[2], f"元{_os_all['total_amount']:,.0f}", "历史总营收", "#10b981")
    _kpi(kc[3], f"元{os30['total_amount']:,.0f}",   "近30天营收", "#059669")
    _kpi(kc[4], ls30["total"],  "近30天咨询",  "#f59e0b")
    _kpi(kc[5], f"{ls7['conversion_rate']:.1%}", "近7天转化率", "#ef4444")

    st.divider()

    left, right = st.columns(2)

    with left:
        # ── 全量TOP10热门学校 ──────────────────
        st.subheader("🔥 全量 Top10 学校")
        try:
            _mkt_all_stats  = get_order_stats(days=0)
            _mkt_sch30_dict = dict(get_order_stats(days=30).get('by_school', []))
            _mkt_sch90_dict = dict(get_order_stats(days=90).get('by_school', []))
            _mkt_all_sch_dict = dict(_mkt_all_stats.get('by_school', []))
            _mkt_top_schools = [s for s, _ in _mkt_all_stats.get('by_school', []) if _is_valid_school(s)][:10]
            if _mkt_top_schools:
                _mkt_sch_rows = []
                for _ms in _mkt_top_schools:
                    _ms_all = _mkt_all_sch_dict.get(_ms, 0)
                    _ms_30  = _mkt_sch30_dict.get(_ms, 0)
                    _ms_90  = _mkt_sch90_dict.get(_ms, 0)
                    _ms_hist_avg = (_ms_90 / 3) if _ms_90 else 0
                    _ms_trend = "📈" if _ms_30 > _ms_hist_avg * 1.1 else "📉" if _ms_30 < _ms_hist_avg * 0.9 else "➡️"
                    _mkt_sch_rows.append({
                        '学校': _ms,
                        '全量单量': _ms_all,
                        '近30天': _ms_30,
                        '趋势': _ms_trend,
                    })
                import pandas as _pd_mkt
                st.dataframe(_pd_mkt.DataFrame(_mkt_sch_rows), width='stretch', hide_index=True)
            else:
                st.info("暂无订单/咨询数据。请先导入：`python main.py ingest-orders data/orders.csv`")
        except Exception as _e_mkt_sch:
            st.info(f"学校数据加载中：{_e_mkt_sch}")

        # ── 产品完整分析 ───────────────────────
        st.subheader("💼 产品全量分析")
        try:
            _mkt_os_all  = get_order_stats(days=0)
            _mkt_os30    = get_order_stats(days=30)
            _mkt_os60    = get_order_stats(days=60)
            _mkt_prod_all_cnt = dict(_mkt_os_all.get('by_product', []))
            _mkt_prod_all_rev = dict(_mkt_os_all.get('revenue_by_product', []))
            _mkt_prod30_cnt   = dict(_mkt_os30.get('by_product', []))
            _mkt_prod60_cnt   = dict(_mkt_os60.get('by_product', []))
            _mkt_total_rev = sum(_mkt_prod_all_rev.values()) or 1
            _mkt_prod_names = sorted(_mkt_prod_all_cnt.keys(), key=lambda p: -_mkt_prod_all_rev.get(p, 0))
            if _mkt_prod_names:
                _mkt_prod_rows = []
                for _mp in _mkt_prod_names:
                    _mp_cnt  = _mkt_prod_all_cnt.get(_mp, 0)
                    _mp_rev  = _mkt_prod_all_rev.get(_mp, 0)
                    _mp_30   = _mkt_prod30_cnt.get(_mp, 0)
                    _mp_avg  = int(_mp_rev / max(_mp_cnt, 1))
                    _mp_pct  = round(_mp_rev / _mkt_total_rev * 100, 1)
                    _mp_60h  = _mkt_prod60_cnt.get(_mp, 0) / 2
                    _mp_trend = "📈" if _mp_30 > _mp_60h * 1.1 else "📉" if _mp_30 < _mp_60h * 0.9 else "➡️"
                    _mkt_prod_rows.append({
                        '产品': _mp,
                        '总单量': _mp_cnt,
                        '总营收': f"元{int(_mp_rev):,}",
                        '近30天': _mp_30,
                        '均价': f"元{_mp_avg:,}",
                        '占营收%': f"{_mp_pct}%",
                        '趋势': _mp_trend,
                    })
                import pandas as _pd_mkt2
                st.dataframe(_pd_mkt2.DataFrame(_mkt_prod_rows), width='stretch', hide_index=True)
            else:
                st.info("暂无产品数据")
        except Exception as _e_mkt_prod:
            st.info(f"产品数据加载中：{_e_mkt_prod}")

        # ── 产品营收构成 ───────────────────────
        st.subheader("🥧 产品营收占比")
        try:
            _pie_data = {p: v for p, v in _mkt_prod_all_rev.items() if v > 0}
            if _pie_data:
                _pie_total = sum(_pie_data.values())
                _pie_sorted = sorted(_pie_data.items(), key=lambda x: -x[1])[:6]
                _pie_cols = st.columns(min(3, len(_pie_sorted)))
                for _pii, (_pname, _prev) in enumerate(_pie_sorted):
                    _pct = round(_prev / _pie_total * 100, 1)
                    _pie_cols[_pii % 3].metric(_pname[:8], f"{_pct}%", f"元{int(_prev/10000):.0f}万")
            else:
                st.info("暂无营收数据")
        except Exception:
            pass

    with right:
        # ── 近30天学校-产品热力分析 ─────────────
        st.subheader("🔥 近30天学校-产品热力分析")
        try:
            _mkt_orders30 = list_orders(days=30, limit=2000)
            _sch_prod_heat: dict = {}
            for _ho in _mkt_orders30:
                _hsch = _ho.get('school') or '未知'
                _hprd = _ho.get('product') or '未知'
                _sch_prod_heat.setdefault(_hsch, {})
                _sch_prod_heat[_hsch][_hprd] = _sch_prod_heat[_hsch].get(_hprd, 0) + 1
            if _sch_prod_heat:
                # 取top5学校
                _top5sch = sorted(_sch_prod_heat.keys(), key=lambda s: -sum(_sch_prod_heat[s].values()))[:5]
                for _hsch in _top5sch:
                    _hsch_total = sum(_sch_prod_heat[_hsch].values())
                    _top_prod = max(_sch_prod_heat[_hsch], key=lambda p: _sch_prod_heat[_hsch][p])
                    _top_cnt  = _sch_prod_heat[_hsch][_top_prod]
                    st.markdown(
                        f"**{_hsch}** — {_hsch_total}单 | "
                        f"主力产品：{_top_prod}（{_top_cnt}单）"
                    )
                    _heat_items = sorted(_sch_prod_heat[_hsch].items(), key=lambda x: -x[1])[:4]
                    st.caption("  " + "  |  ".join([f"{p}:{n}单" for p, n in _heat_items]))
                st.divider()
            else:
                st.info("近30天暂无数据")
        except Exception as _e_heat:
            st.info(f"热力数据加载中：{_e_heat}")

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
            try:
                _opp_data = list_opportunity_scores()  # 27条
                if _opp_data:
                    st.markdown("### 🎯 学校机会评分（AI自动计算）")
                    import pandas as _pd_opp
                    _opp_rows = [{'学校/产品': o['entity_name'], '评分': o['score'], '类型': o['score_type'],
                                   '更新时间': (o.get('updated_at') or '')[:10],
                                   '投放建议': '🔴重点' if (o.get('score') or 0) >= 80 else ('🟡培育' if (o.get('score') or 0) >= 60 else '🟢观察')}
                                for o in sorted(_opp_data, key=lambda x: -(x.get('score') or 0))
                                if o.get('entity_name') and _is_valid_school(o.get('entity_name', ''))][:15]
                    if _opp_rows:
                        st.dataframe(_pd_opp.DataFrame(_opp_rows), width='stretch', hide_index=True)
            except Exception as _e_opp:
                st.caption(f"机会评分加载中：{_e_opp}")

    st.divider()

    # ── 咨询成交来源渠道分析 ──────────────────
    st.subheader("📣 近30天咨询来源渠道")
    channel_data = ls30.get("by_channel", [])
    if channel_data:
        df_channel = pd.DataFrame(channel_data, columns=["渠道","咨询量"])
        st.dataframe(df_channel, width='stretch', hide_index=True)
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
        try:
            _daily_suggs = list_suggestions(suggestion_type="daily_reminder", limit=5)
            if _daily_suggs:
                st.markdown("**💡 最新每日提醒（来自AI）**")
                for _i_ds, _ds in enumerate(_daily_suggs[:5], 1):
                    _ds_txt = ((_ds.get('recommendation') or _ds.get('content') or ''))[:300]
                    if _ds_txt:
                        st.info(f"**{_i_ds}.** {_ds_txt}")
        except Exception as _e_ds:
            st.caption(f"建议加载中：{_e_ds}")


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
        _sc1, _sc2, _sc3, _sc4 = st.columns([2, 1, 1, 1])
        with _sc1:
            import datetime as _dt
            _default_month = _dt.date.today().strftime("%Y-%m")
            _target_month_input = st.text_input("目标月份", value=_default_month, placeholder="2026-07", key="strategy_month")
        with _sc2:
            st.write(""); st.write("")
            _gen_all = st.button("⚡ 一键全量生成", type="primary", width='stretch', key="gen_all_btn",
                                  help="先运行产品供给分析，再生成AI月度推广策略")
        with _sc3:
            st.write(""); st.write("")
            _gen_monthly = st.button("🤖 生成月度策略", width='stretch', key="gen_monthly_btn")
        with _sc4:
            st.write(""); st.write("")
            _gen_supply = st.button("🔄 更新供给分析", width='stretch', key="gen_supply_btn")

        if _gen_all:
            _month_v = _target_month_input.strip() or _default_month
            import yaml as _yaml
            with open(ROOT / "config.yaml") as _f:
                _cfg = _yaml.safe_load(_f)
            _prog = st.progress(0, text="第1步：运行产品供给分析...")
            try:
                from agents.product_supply_risk_agent import ProductSupplyRiskAgent
                _sra = ProductSupplyRiskAgent(_cfg)
                _sr = _sra.analyze(period_days=30)
                _prog.progress(50, text=f"✅ 供给分析完成（{_sr.get('order_count',0)}单）。第2步：生成AI月度策略...")
            except Exception as _se:
                st.warning(f"供给分析步骤出错（跳过）：{_se}")
                _prog.progress(50, text="供给分析跳过，继续生成月度策略...")
            try:
                from agents.promotion_strategy_agent import PromotionStrategyAgent
                _agent = PromotionStrategyAgent(_cfg)
                _result = _agent.generate(target_month=_month_v)
                _prog.progress(100, text="✅ 全量生成完成！")
                st.success(f"✅ {_month_v} 月度推广策略已生成！建议ID: {_result.get('suggestion_id')}")
                if not _result.get("data_sufficient"):
                    st.warning("⚠️ 订单数据较少，AI建议仅供参考。")
                st.rerun()
            except Exception as _e:
                st.error(f"月度策略生成失败：{_e}")

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
        _orders_all = list_orders(days=90, limit=1000)
        _orders_30d_amt = sum(o.get("amount") or 0 for o in _orders_30d)
        _orders_60d = list_orders(days=60, limit=1000)
        _hero_col1, _hero_col2, _hero_col3, _hero_col4 = st.columns(4)
        _hero_col1.metric("近30天订单", len(_orders_30d), delta=f"vs 前30天 {len(_orders_60d)-len(_orders_30d):+d}单")
        _hero_col2.metric("近30天营收", f"元{_orders_30d_amt:,.0f}", help="近30天订单金额汇总")
        _hero_col3.metric("老师储备学科", len(_capacities_all), help="teacher_capacity 表记录数")
        _hero_col4.metric("数据状态", "✅ 充足" if _has_data else "⚠️ 不足")

        # ── 数据驱动产品分析（无需AI，实时计算）──────────────────────
        st.markdown("#### 📊 产品实战数据（近30天 vs 前30天）")

        # 计算各产品30天 vs 前30天数据
        import datetime as _dtx
        _cutoff30 = _dtx.datetime.utcnow() - _dtx.timedelta(days=30)
        _cutoff60 = _dtx.datetime.utcnow() - _dtx.timedelta(days=60)

        _prod_30: dict = {}
        _prod_60_prev: dict = {}  # 31-60天
        for _o in _orders_60d:
            _p = _o.get("product") or "未知"
            _amt = _o.get("amount") or 0
            _odate = _o.get("order_date", "")
            try:
                _od = _dtx.datetime.fromisoformat(_odate[:19])
                if _od >= _cutoff30:
                    _prod_30[_p] = _prod_30.get(_p, {"cnt": 0, "amt": 0})
                    _prod_30[_p]["cnt"] += 1
                    _prod_30[_p]["amt"] += _amt
                else:
                    _prod_60_prev[_p] = _prod_60_prev.get(_p, {"cnt": 0, "amt": 0})
                    _prod_60_prev[_p]["cnt"] += 1
                    _prod_60_prev[_p]["amt"] += _amt
            except Exception:
                pass

        _all_prods = sorted(set(list(_prod_30.keys()) + list(_prod_60_prev.keys())),
                            key=lambda x: -_prod_30.get(x, {}).get("cnt", 0))

        if _all_prods:
            _pcols = st.columns(min(len(_all_prods), 4))
            for _i, _prod in enumerate(_all_prods[:8]):
                _p30 = _prod_30.get(_prod, {"cnt": 0, "amt": 0})
                _p60 = _prod_60_prev.get(_prod, {"cnt": 0, "amt": 0})
                _delta_cnt = _p30["cnt"] - _p60["cnt"]
                _avg_price = (_p30["amt"] / _p30["cnt"]) if _p30["cnt"] > 0 else 0
                # 推广建议标签
                if _p30["cnt"] >= 10 and _delta_cnt > 0:
                    _badge = "🟢 强推"
                elif _p30["cnt"] >= 5:
                    _badge = "🔵 维持"
                elif _p30["cnt"] < 3 and _p60["cnt"] > 5:
                    _badge = "🔴 下滑"
                else:
                    _badge = "🟡 观察"
                with _pcols[_i % 4]:
                    with st.container(border=True):
                        st.markdown(f"**{_prod}**")
                        st.caption(_badge)
                        st.metric("近30天单量", _p30["cnt"], delta=f"{_delta_cnt:+d}" if _delta_cnt else None)
                        st.caption(f"均价 元{_avg_price:,.0f} | 营收 元{_p30['amt']:,.0f}")
        else:
            st.info("暂无订单数据，请先导入 orders.csv")

        st.divider()

        # ── 产品趋势深度分析 ────────────────────────────────────────
        st.markdown("#### 📈 产品趋势与渠道分析")
        _trend_c1, _trend_c2 = st.columns(2)

        with _trend_c1:
            st.markdown("**按产品：近30天单量排名**")
            if _prod_30:
                _prod_sorted = sorted(_prod_30.items(), key=lambda x: -x[1]["cnt"])
                for _rank, (_pn, _pd) in enumerate(_prod_sorted[:6], 1):
                    _prev_cnt = _prod_60_prev.get(_pn, {}).get("cnt", 0)
                    _trend_icon = "▲" if _pd["cnt"] > _prev_cnt else ("▼" if _pd["cnt"] < _prev_cnt else "→")
                    _bar_w = int(_pd["cnt"] / max(v["cnt"] for v in _prod_30.values()) * 100)
                    st.markdown(
                        f"`#{_rank}` **{_pn}** {_trend_icon}  \n"
                        f"{'█' * (_bar_w // 10)}{'░' * (10 - _bar_w // 10)} "
                        f"{_pd['cnt']}单 | 元{_pd['amt']:,.0f}"
                    )
            else:
                st.caption("暂无数据")

        with _trend_c2:
            st.markdown("**按销售负责人：近30天成交**")
            _owner_30: dict = {}
            for _o in _orders_30d:
                _ow = _o.get("sales_owner") or "未分配"
                _owner_30[_ow] = _owner_30.get(_ow, {"cnt": 0, "amt": 0})
                _owner_30[_ow]["cnt"] += 1
                _owner_30[_ow]["amt"] += _o.get("amount") or 0
            if _owner_30:
                for _ow, _od in sorted(_owner_30.items(), key=lambda x: -x[1]["cnt"])[:6]:
                    st.markdown(f"**{_ow}** — {_od['cnt']}单 | 元{_od['amt']:,.0f}")
            else:
                st.caption("暂无数据")

        st.divider()

        # ── AI供给分析产品推广优先级 ──────────────────────────────────
        if _promotion_boundary:
            st.markdown("#### 🤖 AI产品供给分析（推广边界）")
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
                        st.caption(_pb.get("reason","")[:80])
                        if _pb.get("tight_subjects"):
                            st.caption(f"⚠️ 资源紧张：{'/'.join(_pb['tight_subjects'][:2])}")
            st.divider()

        # ── 月度AI策略报告 ─────────────────────────────────────────
        st.markdown("#### 🤖 AI月度推广策略报告")
        _monthly_suggestions = list_suggestions(suggestion_type="monthly_promotion_strategy", limit=6)
        if not _monthly_suggestions:
            st.info("暂无AI月度策略。点击上方「🚀 生成本月推广策略」按钮（约30秒），AI将基于以上真实数据生成详细策略。")
        else:
            for _s in _monthly_suggestions:
                _created = str(_s.get("created_at", ""))[:16]
                with st.expander(f"📋 {_s.get('title', '')} — {_created}", expanded=(_s == _monthly_suggestions[0])):
                    _basis = _s.get("data_basis") or {}
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _mc1.metric("月份", _basis.get("target_month", "—"))
                    _mc2.metric("数据量", f"{_basis.get('order_count', 0)}单")
                    _mc3.metric("数据状态", "✅ 充足" if _basis.get("data_sufficient") else "⚠️ 有限")
                    _facts_at_gen = _basis.get("facts_count", 0)
                    _src_note = _basis.get("data_source_note", "")
                    _missing_at_gen = _basis.get("missing_info", [])
                    if _facts_at_gen and _facts_at_gen > 0:
                        st.caption(f"📎 依据来源 | 已确认事实：{_facts_at_gen} 条 | {_src_note.split(chr(10))[0] if _src_note else ''}")
                    else:
                        st.warning("⚠️ 临时参考 | 生成时无已确认事实，建议可靠性有限。")
                    if _missing_at_gen:
                        with st.expander(f"📋 生成时缺少 {len(_missing_at_gen)} 项资料"):
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
            _gen_sales = st.button("📊 生成销售建议", width='stretch', key="gen_sales")
        with _wc3:
            st.write(""); st.write("")
            _gen_mkt = st.button("📣 生成市场内容包", width='stretch', key="gen_mkt")
        _gen_both = st.button("🚀 生成本周推广建议（销售+市场+供给分析）", type="primary", width='stretch', key="gen_both")

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
# 页面 1：老板驾驶舱
# ══════════════════════════════════════════════
elif page in ("📊 老板驾驶舱", "📊 公司增长看板"):
    import datetime as _bdt

    st.markdown("## 📊 老板驾驶舱")
    st.caption(f"基础版 · 只展示真实任务/审批/逾期/上线状态/风险记录 · {datetime.now().strftime('%Y-%m-%d %H:%M')} 更新")

    try:
        from database.crud import list_product_launches as _boss_list_launches
    except Exception:
        _boss_list_launches = lambda: []

    _boss_tasks = list_tasks(limit=500)
    _boss_launches = _boss_list_launches()
    _boss_risks = list_order_risks(limit=100)
    _boss_feedbacks = list_feedbacks(status="open")
    _today_boss = datetime.now().date().isoformat()
    _active_tasks = [t for t in _boss_tasks if t.get("status") in ("todo", "doing", "blocked")]
    _overdue_tasks = [
        t for t in _active_tasks
        if (t.get("due_date") or "")[:10] and (t.get("due_date") or "")[:10] < _today_boss
    ]
    _pending_approvals = [p for p in _boss_launches if (p.get("mgmt_approval") or "pending") == "pending"]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("真实待办", len(_active_tasks))
    k2.metric("真实逾期", len(_overdue_tasks))
    k3.metric("待审批上线卡", len(_pending_approvals))
    k4.metric("产品上线卡", len(_boss_launches))
    k5.metric("开放风险/反馈", len(_boss_risks) + len(_boss_feedbacks))

    st.divider()

    c_task, c_approval = st.columns(2)
    with c_task:
        st.markdown("### 真实逾期任务")
        if _overdue_tasks:
            st.dataframe(pd.DataFrame(_overdue_tasks)[["id", "title", "department", "priority", "status", "due_date"]], width="stretch", hide_index=True)
        else:
            st.info("暂无真实数据，无法判断。")

    with c_approval:
        st.markdown("### 真实审批")
        if _pending_approvals:
            _approval_rows = [{
                "id": p.get("id"),
                "产品": p.get("product_name"),
                "阶段": p.get("stage"),
                "审批": p.get("mgmt_approval") or "pending",
                "意见": p.get("mgmt_approval_note") or "",
            } for p in _pending_approvals]
            st.dataframe(pd.DataFrame(_approval_rows), width="stretch", hide_index=True)
        else:
            st.info("暂无真实数据，无法判断。")

    st.divider()
    st.markdown("### 真实产品上线状态")
    if _boss_launches:
        _launch_rows = [{
            "id": p.get("id"),
            "产品": p.get("product_name"),
            "目录ID": p.get("catalog_id"),
            "阶段": p.get("stage"),
            "顾问": p.get("advisor_owner") or "",
            "学管": p.get("xueguan_owner") or "",
            "后台": p.get("backend_owner") or "",
            "下一步": p.get("next_action") or "",
        } for p in _boss_launches]
        st.dataframe(pd.DataFrame(_launch_rows), width="stretch", hide_index=True)
    else:
        st.info("暂无真实数据，无法判断。")

    st.divider()
    c_risk, c_feedback = st.columns(2)
    with c_risk:
        st.markdown("### 真实风险记录")
        if _boss_risks:
            st.dataframe(pd.DataFrame(_boss_risks), width="stretch", hide_index=True)
        else:
            st.info("暂无真实数据，无法判断。")
    with c_feedback:
        st.markdown("### 真实开放反馈")
        if _boss_feedbacks:
            st.dataframe(pd.DataFrame(_boss_feedbacks), width="stretch", hide_index=True)
        else:
            st.info("暂无真实数据，无法判断。")

    st.stop()

    # ══ 数据加载 ══════════════════════════════════════════════
    try:
        _now = _bdt.datetime.now()
        _today = _now.strftime('%Y-%m-%d')
        _this_month_s = _now.replace(day=1).strftime('%Y-%m-%d')
        _last_m_end = _now.replace(day=1) - _bdt.timedelta(days=1)
        _last_month_s = _last_m_end.replace(day=1).strftime('%Y-%m-%d')
        _last_month_e = _last_m_end.strftime('%Y-%m-%d')

        _s0   = get_order_stats(days=0)
        _s30  = get_order_stats(days=30)
        _s60  = get_order_stats(days=60)
        _s7   = get_order_stats(days=7)
        _s90  = get_order_stats(days=90)
        _ls0  = get_lead_stats(days=0)
        _ls30 = get_lead_stats(days=30)

        _orders_60 = list_orders(days=60, limit=3000)
        _has_order_data = bool(_orders_60)
        _orders_this_month = [o for o in _orders_60 if (o.get('order_date') or '')[:10] >= _this_month_s]
        _orders_last_month = [o for o in _orders_60 if _last_month_s <= (o.get('order_date') or '')[:10] <= _last_month_e]

        _rev_this  = sum(o.get('amount') or 0 for o in _orders_this_month)
        _rev_last  = sum(o.get('amount') or 0 for o in _orders_last_month)
        _cnt_this  = len(_orders_this_month)
        _cnt_last  = len(_orders_last_month)

        # 月度目标（按上月实际×1.1为默认目标）
        _monthly_target_orders = max(int(_cnt_last * 1.1), 200)
        _monthly_target_rev = max(int(_rev_last * 1.1), 1000000)

        # 今天是本月第几天，推算完成率
        _day_of_month = _now.day
        _days_in_month = (_now.replace(month=_now.month % 12 + 1, day=1) - _bdt.timedelta(days=1)).day if _now.month < 12 else 31
        _progress_pct = _day_of_month / _days_in_month
        _projected_rev = _rev_this / max(_progress_pct, 0.01)
        _projected_cnt = _cnt_this / max(_progress_pct, 0.01)
        _target_pct_rev = _rev_this / max(_monthly_target_rev, 1)
        _on_track = _projected_rev >= _monthly_target_rev * 0.9

    except Exception as _e_boss:
        st.error(f"数据加载异常：{_e_boss}")
        st.stop()

    if not _has_order_data:
        st.info("no_data：orders 表暂无真实订单，老板驾驶舱不生成机会、风险或目标预测结论。")
        st.stop()

    # ══ Section 1：目标完成战况 ══════════════════════════════
    _track_color = "#10b981" if _on_track else "#ef4444"
    _track_label = "✅ 按当前趋势可完成月度目标" if _on_track else "⚠️ 按当前趋势无法完成月度目标，需要干预"
    st.markdown(f"<div style='background:{_track_color}20;border-left:4px solid {_track_color};padding:10px 16px;border-radius:4px;margin-bottom:12px'><b style='color:{_track_color}'>{_track_label}</b><br><span style='color:#64748b;font-size:12px'>今日 {_today} · 本月已过 {_day_of_month}/{_days_in_month} 天 · 完成率 {_target_pct_rev:.0%}</span></div>", unsafe_allow_html=True)

    _c1, _c2, _c3, _c4 = st.columns(4)
    _c1.metric("本月订单", f"{_cnt_this}单", delta=f"预计全月{int(_projected_cnt)}单", delta_color="normal")
    _c2.metric("本月营收", f"元{int(_rev_this/10000)}万", delta=f"预计元{int(_projected_rev/10000)}万", delta_color="normal")
    _c3.metric("vs上月", f"{_cnt_last}单/{int(_rev_last/10000)}万", delta=f"环比{int((_cnt_this/_progress_pct-_cnt_last)/max(_cnt_last,1)*100):+d}%", delta_color="normal")
    _c4.metric("目标进度", f"{_target_pct_rev:.0%}", delta=f"日均{int(_rev_this/max(_day_of_month,1)/10000*10)/10}万")

    # 进度条
    import pandas as _pd_boss
    st.progress(min(_target_pct_rev, 1.0), text=f"营收目标：元{int(_rev_this):,} / 元{_monthly_target_rev:,}")

    st.divider()

    # ══ Section 2：最大机会 & 最大风险 ══════════════════════
    _opp_col, _risk_col = st.columns(2)

    with _opp_col:
        st.markdown("### 🚀 当前最大增长机会")
        try:
            # 找增长最快的产品（近30天 vs 近60天日均）
            _prod30 = dict(_s30['by_product'])
            _prod60 = dict(_s60['by_product'])
            _prod_growth = {}
            for p, c30 in _prod30.items():
                if not p or p == '未知': continue
                c60_avg = _prod60.get(p, 0) / 2
                if c60_avg > 0:
                    _prod_growth[p] = (c30 - c60_avg) / c60_avg

            if _prod_growth:
                _hot_prod = max(_prod_growth, key=_prod_growth.get)
                _hot_rate = _prod_growth[_hot_prod]
                st.success(f"**产品机会：{PRODUCT_ZH.get(_hot_prod, _hot_prod)}**")
                st.markdown(f"近30天环比增长 **{_hot_rate:+.0%}**，是当前最快增长产品。")

            # 找需求上升最快的学校
            _sch30 = dict(_s30['by_school'])
            _sch90 = dict(_s90['by_school'])
            _sch_growth = {}
            for s, c30 in _sch30.items():
                if not _is_valid_school(s): continue
                c90_avg = _sch90.get(s, 0) / 3
                if c90_avg > 0:
                    _sch_growth[s] = (c30 - c90_avg) / c90_avg

            if _sch_growth:
                _hot_sch = max(_sch_growth, key=_sch_growth.get)
                _hot_sch_rate = _sch_growth[_hot_sch]
                st.info(f"**学校机会：{_hot_sch}**\n近30天环比增长 **{_hot_sch_rate:+.0%}**，建议加大该校推广投入。")

        except Exception as _e_opp:
            st.caption(f"机会分析：{_e_opp}")

    with _risk_col:
        st.markdown("### ⚠️ 当前最大风险")
        try:
            # 找下滑最快的产品
            _risk_items = []
            for p, c30 in _prod30.items():
                if not p or p == '未知': continue
                c60_avg = _prod60.get(p, 0) / 2
                if c60_avg > 5 and c30 < c60_avg * 0.8:
                    _risk_items.append((p, (c30 - c60_avg) / c60_avg))

            if _risk_items:
                _risk_items.sort(key=lambda x: x[1])
                _worst_prod, _worst_rate = _risk_items[0]
                st.error(f"**产品风险：{PRODUCT_ZH.get(_worst_prod, _worst_prod)}**")
                st.markdown(f"近30天下滑 **{_worst_rate:.0%}**，需要排查原因。")

            # 本月营收是否落后
            if not _on_track:
                _gap = _monthly_target_rev - _projected_rev
                _days_left = _days_in_month - _day_of_month
                _daily_needed = _gap / max(_days_left, 1)
                st.warning(f"**完成风险：** 预计月末差 元{int(_gap/10000)}万\n剩余{_days_left}天需每天新增 元{int(_daily_needed/10000)}万")
            else:
                st.success("营收目标按当前趋势可完成 ✅")

        except Exception as _e_risk:
            st.caption(f"风险分析：{_e_risk}")

    st.divider()

    # ══ Section 3：本周作战焦点 ══════════════════════════════
    st.markdown("### 🎯 本周作战焦点")
    _fw1, _fw2, _fw3, _fw4 = st.columns(4)

    try:
        # 本周主推产品（近7天最高营收产品）
        _prod_rev7 = dict(_s7.get('revenue_by_product', []))
        _top_prod_week = max(_prod_rev7, key=_prod_rev7.get) if _prod_rev7 else None
        _fw1.markdown("**📦 本周主推产品**")
        if _top_prod_week:
            _fw1.metric(PRODUCT_ZH.get(_top_prod_week, _top_prod_week),
                       f"元{int(_prod_rev7[_top_prod_week]/10000)}万",
                       delta="本周营收最高")
        else:
            _fw1.caption("数据计算中")
        if _fw1.button("→ 推广策略", key="boss_to_strategy"):
            st.session_state["page_jump"] = "📈 产品推广策略台"

        # 本周重点学校
        _sch7 = [(s, n) for s, n in _s7['by_school'] if _is_valid_school(s)]
        _fw2.markdown("**🏫 本周重点学校**")
        if _sch7:
            _fw2.metric(_sch7[0][0][:8], f"{_sch7[0][1]}单", delta="本周最多")
            if len(_sch7) > 1:
                _fw2.caption(f"2位：{_sch7[1][0][:6]}({_sch7[1][1]}单)")
        if _fw2.button("→ 学校情报", key="boss_to_school"):
            st.session_state["page_jump"] = "🏫 学校增长情报台"

        # 本周销售冠军
        _orders_7d = list_orders(days=7, limit=500)
        _owner_7d = {}
        for _o7 in _orders_7d:
            _own7 = ((_o7.get('sales_owner') or '未分配') + ' ').split()[0]
            _owner_7d.setdefault(_own7, {'cnt':0,'amt':0})
            _owner_7d[_own7]['cnt'] += 1
            _owner_7d[_own7]['amt'] += _o7.get('amount') or 0
        _fw3.markdown("**👑 本周销售冠军**")
        if _owner_7d:
            _top_owner = max(_owner_7d, key=lambda x: _owner_7d[x]['amt'])
            _fw3.metric(_top_owner, f"{_owner_7d[_top_owner]['cnt']}单",
                       delta=f"元{int(_owner_7d[_top_owner]['amt']/10000)}万")
        if _fw3.button("→ 销售排行", key="boss_to_sales"):
            st.session_state["page_jump"] = "💼 销售顾问作战台"

        # 本周重点渠道：仅在 CRM 线索有 source_channel 时展示
        _fw4.markdown("**📡 本周重点渠道**")
        _ls7 = get_lead_stats(days=7)
        _ch7 = [(c, n) for c, n in _ls7.get("by_channel", []) if c and c not in ("未知", "None", "")]
        if _ch7:
            _fw4.metric("重点推进", _ch7[0][0], delta=f"{_ch7[0][1]}条线索")
            if len(_ch7) > 1:
                _fw4.caption(f"2位：{_ch7[1][0]}({_ch7[1][1]}条)")
        else:
            _fw4.caption("no_data：leads.source_channel 暂无可用数据")
        if _fw4.button("→ 渠道作战台", key="boss_to_channel"):
            st.session_state["page_jump"] = "📡 渠道作战台"

    except Exception as _e_focus:
        st.caption(f"焦点数据：{_e_focus}")

    st.divider()

    # ══ Section 3.5：新产品上线状态 ══════════════════════════
    st.markdown("### 🚀 新产品上线状态")
    try:
        from database.crud import list_product_launches as _list_product_launches_boss
        _new_products = _list_product_launches_boss()[:5]
        if _new_products:
            _np_cols = st.columns(min(len(_new_products), 3))
            for _npi, _np in enumerate(_new_products[:3]):
                _np_col = _np_cols[_npi]
                _np_status = _np.get('stage', '需求判断')
                _np_status_label = _np_status
                _np_col.markdown(f"**{_np.get('product_name','未知产品')[:12]}**")
                _np_col.caption(_np_status_label)
                _owners = [x for x in [_np.get('advisor_owner'), _np.get('xueguan_owner'), _np.get('backend_owner')] if x]
                _np_col.caption(f"负责：{' / '.join(_owners) if _owners else '待分配'}")
        else:
            st.info("暂无新产品上线记录。[→ 新产品上线台](#)")
        if st.button("→ 查看新产品上线台", key="boss_to_newprod"):
            st.session_state["page_jump"] = "🚀 新产品上线台"
    except Exception as _e_np:
        st.caption(f"产品上线状态：{_e_np}")

    st.divider()

    # ══ Section 3.6：部门卡点分析 ══════════════════════════
    st.markdown("### 🚧 当前哪个环节卡住了")
    try:
        _block_items = []

        # 分析任务积压
        from database.crud import list_tasks as _list_tasks_boss
        _all_tasks_boss = _list_tasks_boss(status="todo", limit=200)
        _today_str_boss = _now.strftime('%Y-%m-%d')
        _overdue_tasks = [t for t in _all_tasks_boss if (t.get('due_date') or '9999') < _today_str_boss]
        _dept_overdue = {}
        for _ot in _overdue_tasks:
            _dept_overdue[_ot.get('department','未分配')] = _dept_overdue.get(_ot.get('department','未分配'), 0) + 1

        if _dept_overdue:
            _worst_dept = max(_dept_overdue, key=_dept_overdue.get)
            _block_items.append(f"**{_worst_dept}** 有 {_dept_overdue[_worst_dept]} 个任务逾期未完成")

        # 分析月度目标偏差
        if not _on_track:
            _block_items.append(f"**营收目标** 当前完成率 {_target_pct_rev:.0%}，预计缺口 元{int((_monthly_target_rev - _projected_rev)/10000)}万")

        # 分析产品下滑
        if _risk_items:
            _block_items.append(f"**产品交付/市场** — {PRODUCT_ZH.get(_risk_items[0][0], _risk_items[0][0])} 连续下滑")

        if _block_items:
            for _bi in _block_items:
                st.warning(f"⚠️ {_bi}")
        else:
            st.success("✅ 各部门运转正常，无明显卡点。")

        if st.button("→ 查看所有任务", key="boss_to_tasks"):
            st.session_state["page_jump"] = "✅ 部门任务台"
    except Exception as _e_block:
        st.caption(f"卡点分析：{_e_block}")

    st.divider()

    # ══ Section 4：今天需要管理层决策的事项 ══════════════════
    st.markdown("### 🔔 今天需要关注 & 决策")

    try:
        _decisions = []

        # 决策1：如果本月目标有风险
        if not _on_track:
            _gap_orders = int(_monthly_target_orders - _projected_cnt)
            _decisions.append({
                "紧急度": "🔴 紧急",
                "事项": f"本月订单预计缺口 **{_gap_orders}单**，需要决定：是否加大推广投入、是否启动促销活动",
                "建议动作": "本周内拍板推广预算追加方案",
                "责任部门": "管理层 + 市场部"
            })

        # 决策2：产品风险
        if _risk_items:
            _decisions.append({
                "紧急度": "🟠 重要",
                "事项": f"**{PRODUCT_ZH.get(_risk_items[0][0], _risk_items[0][0])}** 连续下滑，需排查是交付问题还是市场问题",
                "建议动作": "召集产品+学管+销售三方对齐",
                "责任部门": "产品部"
            })

        # 决策3：机会把握
        if _prod_growth:
            _decisions.append({
                "紧急度": "🟡 机会",
                "事项": f"**{PRODUCT_ZH.get(_hot_prod, _hot_prod)}** 正在爆发式增长，需要决定是否加仓资源",
                "建议动作": "确认老师产能是否足够支撑增长",
                "责任部门": "学管部 + 产品部"
            })

        if _decisions:
            for _d in _decisions:
                with st.expander(f"{_d['紧急度']} {_d['事项'][:60]}...", expanded=True):
                    st.markdown(f"**完整描述：** {_d['事项']}")
                    st.markdown(f"**建议动作：** {_d['建议动作']}")
                    st.markdown(f"**责任部门：** {_d['责任部门']}")
                    if st.button("📋 写入任务台", key=f"dec_task_{_decisions.index(_d)}"):
                        _create_task_from_suggestion(
                            title=_d['建议动作'],
                            desc=_d['事项'],
                            dept=_d['责任部门'],
                            deadline_days=3,
                            source_agent="老板驾驶舱自动生成",
                            priority="紧急" if "紧急" in _d['紧急度'] else "高"
                        )
                        st.success("已写入任务台！")
        else:
            st.success("✅ 当前没有紧急决策事项，业务运转正常。")
    except Exception as _e_dec:
        st.caption(f"决策分析：{_e_dec}")

    st.divider()

    # ══ Section 5：AI行动建议（前3条）══════════════════════
    st.markdown("### 💡 AI行动建议（今日）")

    try:
        _suggs_boss = list_suggestions(limit=50)
        _suggs_boss = [
            s for s in _suggs_boss
            if (s.get("data_basis") or {}).get("guardrail", {}).get("validation_status") == "valid"
        ]
        # 优先显示sales和marketing建议
        _suggs_sorted = sorted(_suggs_boss, key=lambda x: (
            0 if 'sales' in (x.get('suggestion_type','')) else
            1 if 'marketing' in (x.get('suggestion_type','')) else 2
        ))[:3]

        if _suggs_sorted:
            for _sg in _suggs_sorted:
                _sg_type_raw = _sg.get('suggestion_type', '建议')
                _sg_type_label = {
                    'weekly_sales_suggestion_v2': '💼 销售建议',
                    'weekly_marketing_suggestion': '📢 市场建议',
                    'daily_reminder': '📅 每日提醒',
                    'product_supply_risk': '⚠️ 产品风险',
                }.get(_sg_type_raw, f'📋 {_sg_type_raw}')
                _sg_text = (_sg.get('recommendation') or _sg.get('content') or '')[:300]
                _sg_date = (_sg.get('created_at') or '')[:10]
                _guard = (_sg.get("data_basis") or {}).get("guardrail", {})

                with st.expander(f"**{_sg_type_label}** — {_sg_date}", expanded=True):
                    st.markdown(_sg_text)
                    st.caption(
                        f"evidence: {_guard.get('evidence') or '—'} | "
                        f"confidence: {_guard.get('confidence') or '—'} | "
                        f"responsible_role: {_guard.get('responsible_role') or '—'}"
                    )
                    _btn_cols = st.columns([1, 1, 4])
                    if _btn_cols[0].button("📋 转任务", key=f"boss_sg_{_suggs_sorted.index(_sg)}"):
                        _dept_map = {'weekly_sales_suggestion_v2':'销售部', 'weekly_marketing_suggestion':'市场部', 'daily_reminder':'管理层', 'product_supply_risk':'产品部'}
                        _create_task_from_suggestion(
                            title=_sg_text[:50],
                            desc=_sg_text,
                            dept=_dept_map.get(_sg_type_raw, '市场部'),
                            deadline_days=7,
                            source_agent=_sg_type_raw,
                        )
                        st.success("✅ 已写入部门任务台")
        else:
            st.info("AI建议今日尚未生成（每日08:30自动运行）")
    except Exception as _e_sg:
        st.caption(f"建议加载：{_e_sg}")

    st.divider()

    # ══ Section 6：各产品本月表现 ══════════════════════════
    st.markdown("### 📦 产品本月战况")
    try:
        _prod_cnt_this = {}
        _prod_rev_this = {}
        for _o in _orders_this_month:
            _p = _o.get('product') or '未知'
            _prod_cnt_this[_p] = _prod_cnt_this.get(_p, 0) + 1
            _prod_rev_this[_p] = _prod_rev_this.get(_p, 0) + (_o.get('amount') or 0)

        _prod_cnt_last = {}
        _prod_rev_last = {}
        for _o in _orders_last_month:
            _p = _o.get('product') or '未知'
            _prod_cnt_last[_p] = _prod_cnt_last.get(_p, 0) + 1
            _prod_rev_last[_p] = _prod_rev_last.get(_p, 0) + (_o.get('amount') or 0)

        all_prods = set(list(_prod_cnt_this.keys()) + list(_prod_cnt_last.keys())) - {'未知', None}
        if all_prods:
            _prod_rows_boss = []
            for _p in sorted(all_prods, key=lambda x: -_prod_rev_this.get(x, 0)):
                _c_this = _prod_cnt_this.get(_p, 0)
                _c_last = _prod_cnt_last.get(_p, 0)
                _r_this = _prod_rev_this.get(_p, 0)
                _r_last = _prod_rev_last.get(_p, 0)
                _trend = f"{int((_c_this/_progress_pct-_c_last)/max(_c_last,1)*100):+d}%" if _c_last else "新品"
                _status = "🟢" if _c_this >= _c_last * _progress_pct * 0.9 else "🔴"
                _prod_rows_boss.append({
                    '状态': _status,
                    '产品': PRODUCT_ZH.get(_p, _p),
                    '本月单量': _c_this,
                    '本月营收': f"元{int(_r_this):,}",
                    '上月单量': _c_last,
                    '环比趋势': _trend,
                })
            st.dataframe(_pd_boss.DataFrame(_prod_rows_boss), width='stretch', hide_index=True)
    except Exception as _e_pt:
        st.caption(f"产品战况：{_e_pt}")

    st.divider()

    # ══ Section 7：销售团队本月排行 ══════════════════════
    st.markdown("### 👥 本月销售团队战况")
    try:
        _owner_this = {}
        for _o in _orders_this_month:
            _own = ((_o.get('sales_owner') or '未分配') + ' ').split()[0]
            _owner_this.setdefault(_own, {'cnt':0,'amt':0})
            _owner_this[_own]['cnt'] += 1
            _owner_this[_own]['amt'] += _o.get('amount') or 0

        if _owner_this:
            _team_rows = []
            for _rank, (_own, _d) in enumerate(sorted(_owner_this.items(), key=lambda x: -x[1]['amt']), 1):
                _avg = int(_d['amt'] / max(_d['cnt'], 1))
                _team_rows.append({
                    '排名': _rank, '顾问': _own, '本月单量': _d['cnt'],
                    '本月营收': f"元{int(_d['amt']):,}", '客单价': f"元{_avg:,}",
                    '状态': '🥇' if _rank==1 else ('🥈' if _rank==2 else ('🥉' if _rank==3 else ''))
                })
            st.dataframe(_pd_boss.DataFrame(_team_rows), width='stretch', hide_index=True)
    except Exception as _e_team:
        st.caption(f"团队数据：{_e_team}")


# ══════════════════════════════════════════════
# 页面 2：营销日历
# ══════════════════════════════════════════════
elif page == "📅 营销日历":
    st.title("📅 营销日历")

    # ── 季节性热点分析（直接从订单数据计算）──
    try:
        st.markdown("### 📈 历史订单：月度旺季分析（2023-2026全量）")
        import pandas as _pd_cal
        _orders_cal = list_orders(days=1825, limit=20000)
        _month_bucket: dict = {}
        _month_rev_bucket: dict = {}
        for _oc in _orders_cal:
            _ym = (_oc.get('order_date') or '')[:7]
            if len(_ym) == 7:
                _m_key = _ym[5:]  # 月份 "01"~"12"
                _month_bucket[_m_key] = _month_bucket.get(_m_key, 0) + 1
                _month_rev_bucket[_m_key] = _month_rev_bucket.get(_m_key, 0) + (_oc.get('amount') or 0)

        _month_name = {'01':'1月','02':'2月','03':'3月','04':'4月','05':'5月','06':'6月',
                       '07':'7月','08':'8月','09':'9月','10':'10月','11':'11月','12':'12月'}
        if _month_bucket:
            _max_m = max(_month_bucket.values())
            _cal_rows = []
            for _mk in sorted(_month_bucket):
                _cnt_m = _month_bucket[_mk]
                _rev_m = _month_rev_bucket.get(_mk, 0)
                _label = _month_name.get(_mk, _mk)
                _tag = '🔥旺季' if _cnt_m >= _max_m * 0.8 else ('📈较旺' if _cnt_m >= _max_m * 0.5 else '❄️淡季')
                _cal_rows.append({'月份': _label, '历史订单量(月均)': _cnt_m,
                                  '月均营收': f"元{int(_rev_m):,}", '旺淡季': _tag})
            _df_cal = _pd_cal.DataFrame(_cal_rows)
            st.dataframe(_df_cal, width='stretch', hide_index=True)

            _top3_cal = sorted(_cal_rows, key=lambda x: -x['历史订单量(月均)'])[:3]
            _top3_names = '、'.join(r['月份'] for r in _top3_cal)
            _top3_hint = '、'.join(r['月份'] for r in sorted(_cal_rows, key=lambda x: -x['历史订单量(月均)'])[:2])
            st.info(f"📌 旺季TOP3月份：**{_top3_names}**，建议在旺季前4-6周启动推广预热，加大投放预算。")

            # 近12个月趋势
            st.markdown("### 📅 近12个月实际走势")
            _recent_monthly: dict = {}
            _recent_rev: dict = {}
            for _oc in _orders_cal:
                _ym2 = (_oc.get('order_date') or '')[:7]
                if len(_ym2) == 7:
                    _recent_monthly[_ym2] = _recent_monthly.get(_ym2, 0) + 1
                    _recent_rev[_ym2] = _recent_rev.get(_ym2, 0) + (_oc.get('amount') or 0)
            _months_12 = sorted(_recent_monthly)[-12:]
            _trend_rows = []
            for _m12 in _months_12:
                _cnt12 = _recent_monthly[_m12]
                _rev12 = _recent_rev.get(_m12, 0)
                _trend_rows.append({'月份': _m12, '订单数': _cnt12, '营收(万元)': round(_rev12/10000, 1)})
            _trend_df = _pd_cal.DataFrame(_trend_rows).set_index('月份')
            _tc1, _tc2 = st.columns(2)
            _tc1.bar_chart(_trend_df[['订单数']], height=200)
            _tc2.bar_chart(_trend_df[['营收(万元)']], height=200)
        else:
            st.info("暂无历史订单数据")
    except Exception as _e_cal:
        st.warning(f"季节性数据加载失败：{_e_cal}")

    st.divider()

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
                    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


# ══════════════════════════════════════════════
# 页面 3：内容池
# ══════════════════════════════════════════════
elif page in ("📝 推广素材台", "📝 内容池"):
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
    _filter_pending = _cb2.button("⏳ 查看待审核", width='stretch',
                                   type="primary" if _cnt_pending > 0 else "secondary")
    _filter_approved = _cb3.button("✅ 查看可用素材", width='stretch')
    _show_all = _cb1.button("📋 查看全部内容", width='stretch')
    if _cb4.button("🔄 刷新列表", width='stretch'):
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

    # ── 内容策略参考（内容库为空时重点展示）────────────
    if len(_all_contents) == 0:
        st.info("📌 内容库当前为空。以下是基于订单数据的**内容创作优先级建议**，可参考生成素材：")
        try:
            import pandas as _pd_content
            _s0_ct = get_order_stats(days=0)
            _s30_ct = get_order_stats(days=30)
            _prod_cnt = dict(_s0_ct['by_product'])
            _prod_rev = dict(_s0_ct.get('revenue_by_product', []))
            _sch_cnt  = dict(_s0_ct['by_school'])
            _valid_sch_ct = [s for s in _sch_cnt if _is_valid_school(s)]

            _cc1, _cc2 = st.columns(2)
            with _cc1:
                st.markdown("**📦 应重点推广的产品（按营收）**")
                _ct_prod_rows = []
                for p, rev in sorted(_prod_rev.items(), key=lambda x: -x[1]):
                    if not p or p == '未知': continue
                    _ct_prod_rows.append({
                        '产品': p, '总营收': f"元{int(rev):,}",
                        '订单量': _prod_cnt.get(p, 0),
                        '内容方向': '高客单精品稿' if rev/_s0_ct['total_amount'] > 0.15 else '走量爆款'
                    })
                st.dataframe(_pd_content.DataFrame(_ct_prod_rows[:6]), width='stretch', hide_index=True)

            with _cc2:
                st.markdown("**🏫 应重点覆盖的学校（Top10）**")
                _ct_sch_rows = [{'学校': s, '历史订单': _sch_cnt[s],
                                  '内容优先级': '🔴高' if _sch_cnt[s] > 500 else ('🟡中' if _sch_cnt[s] > 100 else '🟢普')}
                                for s in _valid_sch_ct[:10]]
                st.dataframe(_pd_content.DataFrame(_ct_sch_rows), width='stretch', hide_index=True)

            st.markdown("**💡 建议每周创作清单：**")
            _top_p = [p for p, _ in sorted(_prod_rev.items(), key=lambda x: -x[1]) if p and p != '未知'][:3]
            _top_s = _valid_sch_ct[:3]
            for _tp in _top_p:
                for _ts in _top_s[:2]:
                    st.markdown(f"- **{_ts} × {_tp}**：小红书选题 + 顾问私聊话术各1条")
        except Exception as _e_ct:
            st.caption(f"内容建议加载中：{_e_ct}")
        st.divider()

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
elif page in ("💼 顾问作战台", "💼 销售作战台"):
    # ══ 今日战报 ══════════════════════════════════════════════════════════════
    try:
        st.markdown("## 💼 顾问作战台")
        st.markdown("---")
        _today_str = datetime.now().strftime('%Y-%m-%d')
        _orders_7 = list_orders(days=7, limit=500)
        _today_orders = [o for o in _orders_7 if (o.get('order_date') or '')[:10] == _today_str]
        _owner_7d = {}
        for o in _orders_7:
            _own = ((o.get('sales_owner') or '未分配') + ' ').split()[0]
            _owner_7d.setdefault(_own, {'cnt':0, 'amt':0})
            _owner_7d[_own]['cnt'] += 1
            _owner_7d[_own]['amt'] += o.get('amount') or 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("今日成单", len(_today_orders))
        c2.metric("近7天单量", len(_orders_7))
        c3.metric("近7天营收", f"元{sum(o.get('amount',0) for o in _orders_7):,.0f}")
        c4.metric("活跃顾问数", len(_owner_7d))

        st.markdown("### 📊 近7天顾问排行")
        import pandas as _pd_adv
        _adv_rows = [{'顾问': k, '单量': v['cnt'], '营收': f"元{int(v['amt']):,}", '客单价': f"元{int(v['amt']/max(v['cnt'],1)):,}"}
                     for k, v in sorted(_owner_7d.items(), key=lambda x:-x[1]['amt'])]
        if _adv_rows:
            st.dataframe(_pd_adv.DataFrame(_adv_rows), width='stretch', hide_index=True)
        st.divider()
    except Exception as _e_zb:
        st.warning(f"今日战报加载中：{_e_zb}")

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
    if _sb1.button("📋 查看本周销售建议", type="primary", width='stretch'):
        st.session_state["sales_show_weekly"] = True
    if _sb2.button("📊 提交客户反馈", width='stretch'):
        st.session_state["sales_show_feedback"] = True
    if _sb3.button("🔄 刷新素材", width='stretch'):
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

    # ══ 产品数据快照 ══════════════════════════════════════════════════════════
    try:
        st.markdown("### 📦 产品全量数据")
        _all_st = get_order_stats(days=0)
        _30_st  = get_order_stats(days=30)
        _prod_all = dict(_all_st['by_product'])
        _prod_rev  = dict(_all_st.get('revenue_by_product', []))
        _prod_30   = dict(_30_st['by_product'])

        import pandas as _pd_pf
        _pf_rows = []
        for prd, cnt in sorted(_prod_all.items(), key=lambda x: -x[1]):
            if not prd or prd == '未知': continue
            rev = _prod_rev.get(prd, 0)
            avg = int(rev/max(cnt,1))
            _pf_rows.append({'产品': prd, '总单量': cnt, '总营收': f"元{int(rev):,}", '均价': f"元{avg:,}", '近30天': _prod_30.get(prd,0)})
        if _pf_rows:
            st.dataframe(_pd_pf.DataFrame(_pf_rows), width='stretch', hide_index=True)
        st.divider()
    except Exception as _e_pf:
        st.info(f"产品数据加载中：{_e_pf}")

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

    # ── 数据驱动战略分析 ──
    try:
        _s0_strat  = get_order_stats(days=0)
        _s30_strat = get_order_stats(days=30)
        _s90_strat = get_order_stats(days=90)

        st.markdown("### 📊 数据支撑的战略分析")
        c1_st, c2_st, c3_st, c4_st = st.columns(4)
        _prod_rev_st = dict(_s0_strat.get('revenue_by_product') or [])
        _top_prod_st = max(_prod_rev_st, key=_prod_rev_st.get) if _prod_rev_st else 'essay'
        _top_rev_st  = _prod_rev_st.get(_top_prod_st, 0)
        _tot_rev_st  = max(_s0_strat.get('total_amount', 1), 1)
        c1_st.metric("营收支柱产品", _top_prod_st[:8],
                     delta=f"元{int(_top_rev_st/10000)}万 ({int(_top_rev_st/_tot_rev_st*100)}%)")
        _m30 = _s30_strat.get('total', 0)
        _m90 = _s90_strat.get('total', 0)
        _growth_st = (_m30 - _m90 / 3) / max(_m90 / 3, 1)
        c2_st.metric("月度增长率", f"{_growth_st:+.1%}")
        _valid_sch_st = [(s, n) for s, n in (_s0_strat.get('by_school') or [])
                         if s and s not in ('未知', '未知学校', 'None', '未知（学生不愿意说）')]
        c3_st.metric("TOP学校", _valid_sch_st[0][0][:8] if _valid_sch_st else "-",
                     delta=f"{_valid_sch_st[0][1]}单" if _valid_sch_st else None)
        c4_st.metric("全量营收", f"元{int(_tot_rev_st/10000)}万")

        # 产品组合战略分析
        _prod_all_st = dict(_s0_strat.get('by_product') or [])
        import pandas as _pd_strat
        _rows_s = []
        for _p_s, _rev_s in sorted(_prod_rev_st.items(), key=lambda x: -x[1]):
            if not _p_s or _p_s == '未知':
                continue
            _cnt_s = _prod_all_st.get(_p_s, 0)
            _rows_s.append({
                '产品': _p_s,
                '营收贡献': f"元{int(_rev_s):,}",
                '营收占比': f"{_rev_s/_tot_rev_st*100:.1f}%",
                '订单量': _cnt_s,
                '均价': f"元{int(_rev_s/max(_cnt_s,1)):,}",
                '战略价值': '⭐核心' if _rev_s/_tot_rev_st > 0.2 else ('✅成长' if _cnt_s > 500 else '🔹补充'),
            })
        if _rows_s:
            st.markdown("**📦 产品战略优先级（按营收贡献）**")
            st.dataframe(_pd_strat.DataFrame(_rows_s), width='stretch', hide_index=True)

        # 学校战略分析
        _sch_rows_st = []
        for _sc_name, _sc_cnt in (_s0_strat.get('by_school') or [])[:15]:
            if not _sc_name or _sc_name in ('未知', '未知学校', 'None', '未知（学生不愿意说）'):
                continue
            _sch_rows_st.append({'学校': _sc_name, '订单量': _sc_cnt,
                                  '战略等级': '🎯重点' if _sc_cnt > 500 else ('📈培育' if _sc_cnt > 100 else '🔹观察')})
        if _sch_rows_st:
            st.markdown("**🏫 学校战略分级**")
            st.dataframe(_pd_strat.DataFrame(_sch_rows_st[:10]), width='stretch', hide_index=True)
    except Exception as _e_strat:
        st.caption(f"战略数据加载中：{_e_strat}")

    st.divider()

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

    # ── 今日数据提醒 ──
    try:
        st.markdown("### 📋 今日数据提醒")
        _s_today_t = get_order_stats(days=1)
        _s_week_t  = get_order_stats(days=7)
        _s_month_t = get_order_stats(days=30)
        _cols_t = st.columns(3)
        _cols_t[0].metric("今日订单", _s_today_t.get('total', 0),
                          delta=f"本周累计{_s_week_t.get('total',0)}单")
        _cols_t[1].metric("今日营收", f"元{int(_s_today_t.get('total_amount',0)):,}")
        _cols_t[2].metric("本月订单", _s_month_t.get('total', 0),
                          delta=f"营收元{int(_s_month_t.get('total_amount',0)/10000)}万")

        _suggs_t = list_suggestions(limit=20)
        if _suggs_t:
            st.markdown("### 💡 AI建议待办（来自最新运行）")
            for _sg_t in _suggs_t[:8]:
                _sg_content = _sg_t.get('recommendation') or _sg_t.get('content') or str(_sg_t)[:200]
                _sg_type = _sg_t.get('suggestion_type', '建议')
                _sg_date = (_sg_t.get('created_at') or '')[:10]
                with st.expander(f"**[{_sg_type}]** — {_sg_date}", expanded=False):
                    st.markdown(_sg_content[:500] if _sg_content else "（内容待加载）")
    except Exception as _e_task:
        st.caption(f"数据加载中：{_e_task}")

    st.divider()

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
        if st.button("🚀 运行每日工作流", width='stretch', type="primary"):
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
elif page in ("📁 数据资料中心", "📁 资料上传中心"):
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
    _do_scan    = _ub1.button("🔍 扫描知识库", width='stretch', type="primary")
    _do_import  = _ub2.button("📥 导入数据", width='stretch')
    _do_signals = _ub3.button("📡 更新市场信号", width='stretch')

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
                    st.dataframe(df_o, width='stretch', hide_index=True)
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
                    st.dataframe(df_l, width='stretch', hide_index=True)
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
        if st.button("🔍 扫描知识库资料", key="btn_scan", type="primary", width='stretch'):
            _run_cmd_up("扫描知识库", _base + ["scan-knowledge-base"], "正在扫描文件...")
            st.rerun()

        st.divider()

        # ── 按钮2：生成摘要（可选，调用Claude）
        st.markdown("#### 2. 生成/更新资料摘要（可选）")
        st.caption("对尚未生成摘要的文档，调用 Claude 生成 150-300 字短摘要 + 关键词。Agent 生成内容时优先读摘要。")
        st.warning("⚠️ 此操作会调用 Claude API，消耗 token。建议仅在需要时使用。", icon="⚠️")

        docs_no_summary = list_knowledge_docs(has_summary=False)
        st.caption(f"当前待生成摘要文档：{len(docs_no_summary)} 个")

        if st.button("🤖 生成/更新资料摘要", key="btn_summary", width='stretch'):
            if not docs_no_summary:
                st.info("所有文档已有摘要，无需更新。")
            else:
                from services.llm import LLMRouter as _LLMRouter
                _llm_sum = _LLMRouter()
                progress = st.progress(0)
                for i, doc in enumerate(docs_no_summary[:10]):  # 每次最多10个，控制token
                    fp = Path(doc["file_path"]) if doc.get("file_path") else None
                    if not fp or not fp.exists():
                        continue
                    try:
                        raw = fp.read_text(encoding="utf-8", errors="ignore")[:3000]  # 最多3000字符
                        _sum_prompt = (
                            f"请对以下知识库文档生成简短摘要，用于销售辅助系统。\n\n"
                            f"文档类别：{doc['category']}\n文件名：{doc['file_name']}\n\n"
                            f"文档内容（节选）：\n{raw}\n\n"
                            "请用JSON格式回复，包含以下字段：\n"
                            "summary（摘要，150-300字中文）\n"
                            "keywords（关键词列表，5-10个）\n"
                            "related_products（关联产品ID列表，从以下选择：final_prediction/guaranteed/dissertation/annual_package/dp_premium/ai_learning/regular）\n"
                            "related_scenarios（适用销售场景列表，3-5个）\n"
                            "只返回JSON，不要其他内容。"
                        )
                        _sum_resp = _llm_sum.chat(_sum_prompt, max_tokens=600, task_type="knowledge_summary")
                        import json as _json
                        raw_resp = (_sum_resp.text or "").strip()
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
        if st.button("📥 导入订单数据", key="btn_orders", type="primary", width='stretch',
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
        if st.button("📥 导入咨询数据", key="btn_leads", type="primary", width='stretch',
                     disabled=not leads_csv.exists()):
            _run_cmd_up("导入咨询", _base + ["ingest-leads", "data/leads.csv"], "正在导入咨询数据...", timeout=30)

        st.divider()

        # ── 按钮5：更新市场信号
        st.markdown("#### 5. 更新市场信号")
        st.caption("基于 orders/leads 数据用 Python/SQL 统计，生成热门学校/产品/DDL提醒等信号。调用 Claude 仅用于生成建议动作（少量 token）。")
        if st.button("📡 更新市场信号", key="btn_signals", type="primary", width='stretch'):
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
            st.dataframe(pd.DataFrame(_file_rows), width='stretch', hide_index=True)
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
            st.dataframe(_af_df, width='stretch', hide_index=True)

            # 允许撤销确认
            st.markdown("---")
            _revoke_id = st.number_input("撤销某条事实（输入 ID）", min_value=0, value=0, step=1)
            if st.button("⚠️ 撤销确认（改为待确认）") and _revoke_id > 0:
                update_fact_status(int(_revoke_id), "pending", is_active=False)
                st.warning(f"已撤销事实 #{_revoke_id}")
                st.rerun()


# ══════════════════════════════════════════════
# 页面：广告预测台
# ══════════════════════════════════════════════
elif page == "🎯 广告预测台":
    render_hero("🎯 广告预测台", "基于学校评分 × 产品评分 × 历史数据的咨询量预测区间")

    _preds = list_campaign_predictions(limit=200)
    _opp_school  = {o["entity_name"]: o for o in list_opportunity_scores(score_type="school")}
    _opp_product = {o["entity_name"]: o for o in list_opportunity_scores(score_type="product")}

    # ── 顶部操作区 ──
    _pc = st.columns([2, 2, 1, 1])
    _week_input = _pc[0].text_input("预测周", value=datetime.now().strftime("%Y-%m-%d"),
                                    help="格式 YYYY-MM-DD，填写周一日期")
    _run_pred = _pc[3].button("▶ 生成本周预测", type="primary")

    if _run_pred:
        with st.spinner("正在生成预测（规则计算 + Claude 生成推广钩子）..."):
            try:
                from agents.campaign_prediction_agent import CampaignPredictionAgent
                import yaml
                with open(ROOT / "config.yaml") as _f:
                    _cfg = yaml.safe_load(_f)
                _agent = CampaignPredictionAgent(_cfg)
                _new_preds = _agent.run(week_start=_week_input, top_schools=5, top_products=3)
                st.success(f"已生成 {len(_new_preds)} 条预测，刷新页面查看。")
                st.rerun()
            except Exception as _e:
                st.error(f"生成失败：{_e}")

    if not _preds:
        st.info("暂无AI预测数据。以下为基于历史数据的学校×产品分析：")
        try:
            import pandas as _pd_pred
            _s0_pred = get_order_stats(days=0)
            _by_sch_pred  = dict((_s0_pred.get('by_school') or []))
            _by_prod_pred = dict((_s0_pred.get('by_product') or []))
            _by_rev_pred  = dict((_s0_pred.get('revenue_by_product') or []))
            _total_pred   = max(_s0_pred.get('total', 1), 1)

            st.markdown("### 📊 历史数据驱动的广告优先级分析")
            _pred_c1, _pred_c2 = st.columns(2)
            with _pred_c1:
                st.markdown("**🏫 学校投放优先级（订单量）**")
                _sch_rows_p = [{'学校': s, '历史订单': n,
                                 '市场份额': f"{n/_total_pred*100:.1f}%",
                                 '投放建议': '🎯重点' if n > 500 else ('📈培育' if n > 100 else '🔹试投')}
                               for s, n in sorted(_by_sch_pred.items(), key=lambda x: -x[1])
                               if s and s not in ('未知', '未知学校', 'None', '未知（学生不愿意说）')][:10]
                st.dataframe(_pd_pred.DataFrame(_sch_rows_p), width='stretch', hide_index=True)
            with _pred_c2:
                st.markdown("**📦 产品投放优先级（营收）**")
                _total_rev_p = max(_s0_pred.get('total_amount', 1), 1)
                _prod_rows_p = [{'产品': p,
                                  '历史订单': _by_prod_pred.get(p, 0),
                                  '营收': f"元{int(r):,}",
                                  '营收占比': f"{r/_total_rev_p*100:.1f}%",
                                  '推广建议': '🎯主推' if r/_total_rev_p > 0.2 else ('📈辅推' if r/_total_rev_p > 0.05 else '🔹测试')}
                                for p, r in sorted(_by_rev_pred.items(), key=lambda x: -x[1])
                                if p and p != '未知'][:8]
                st.dataframe(_pd_pred.DataFrame(_prod_rows_p), width='stretch', hide_index=True)

            st.info("💡 建议：先运行「学校评分」和「产品评分」，再点击上方「生成本周预测」获得AI预测区间。")
        except Exception as _e_pred:
            st.caption(f"预测数据加载中：{_e_pred}")
        st.stop()

    # ── 机会评分总览 ──
    st.subheader("📊 机会评分全景")
    _oc1, _oc2 = st.columns(2)
    with _oc1:
        st.markdown("**学校机会评分**")
        if _opp_school:
            _sch_df = pd.DataFrame([{
                "学校": n, "分数": v["score"], "等级": v["level"],
                "信号灯": {"green":"🟢","yellow":"🟡","red":"🔴","gray":"⚫"}.get(v["traffic_light"],"⚫"),
            } for n, v in sorted(_opp_school.items(), key=lambda x: -x[1]["score"])[:10]])
            st.dataframe(_sch_df, width='stretch', hide_index=True)
        else:
            st.caption("尚无数据，请先运行学校评分")
    with _oc2:
        st.markdown("**产品机会评分**")
        if _opp_product:
            _pro_df = pd.DataFrame([{
                "产品": n, "分数": v["score"], "等级": v["level"],
                "信号灯": {"green":"🟢","yellow":"🟡","red":"🔴","gray":"⚫"}.get(v["traffic_light"],"⚫"),
                "风险": "、".join(v.get("risk_flags", [])[:2]),
            } for n, v in sorted(_opp_product.items(), key=lambda x: -x[1]["score"])[:8]])
            st.dataframe(_pro_df, width='stretch', hide_index=True)
        else:
            st.caption("尚无数据，请先运行产品分析")

    st.divider()

    # ── 预测汇总表 ──
    if _preds:
        st.markdown(f"### 📊 本周广告预测（{len(_preds)}条预测）")
        try:
            import pandas as _pd_pr2
            _pred_rows2 = []
            for _p2 in _preds[:12]:
                _pred_rows2.append({
                    '学校': (_p2.get('school') or '')[:12],
                    '产品': _p2.get('product') or '',
                    '渠道': _p2.get('channel') or '',
                    '预计线索': f"{_p2.get('predicted_leads_low',0)}-{_p2.get('predicted_leads_high',0)}条",
                    '置信度': _p2.get('confidence') or '',
                    '推广钩子': (_p2.get('hook_theme') or '')[:30],
                    '预测周': (_p2.get('prediction_week') or '')[:10],
                })
            st.dataframe(_pd_pr2.DataFrame(_pred_rows2), width='stretch', hide_index=True)
        except Exception as _e_pr2:
            st.caption(f"预测汇总加载中：{_e_pr2}")

    # ── 预测列表 ──
    st.subheader("📋 广告预测明细")
    _pf1, _pf2, _pf3 = st.columns(3)
    _pf_week = _pf1.selectbox("筛选周次", ["全部"] + sorted({p["prediction_week"] for p in _preds}, reverse=True))
    _pf_school = _pf2.selectbox("筛选学校", ["全部"] + sorted({p["school"] for p in _preds if p["school"]}))
    _pf_conf = _pf3.selectbox("置信度", ["全部", "high", "medium", "low"])

    _fp = [p for p in _preds
           if (_pf_week == "全部" or p["prediction_week"] == _pf_week)
           and (_pf_school == "全部" or p["school"] == _pf_school)
           and (_pf_conf == "全部" or p["confidence"] == _pf_conf)]

    _CONF_COLOR = {"high": "🟢", "medium": "🟡", "low": "🔴"}
    for _p in _fp[:30]:
        with st.expander(
            f"{_CONF_COLOR.get(_p['confidence'],'⚫')} {_p['school']} × {_p['product']} × {_p['channel']} "
            f"｜预测 {_p['predicted_leads_low']}–{_p['predicted_leads_high']} 条",
            expanded=False
        ):
            _ec1, _ec2 = st.columns(2)
            _ec1.metric("区间下限", _p["predicted_leads_low"])
            _ec2.metric("区间上限", _p["predicted_leads_high"])
            if _p.get("hook_theme"):
                st.markdown(f"**推广钩子：** {_p['hook_theme']}")
            if _p.get("rationale"):
                st.markdown(f"**推理：** {_p['rationale']}")
            if _p.get("confidence_note"):
                st.caption(f"⚠️ {_p['confidence_note']}")
            _meta = []
            if _p.get("school_score"): _meta.append(f"学校分{_p['school_score']}")
            if _p.get("product_score"): _meta.append(f"产品分{_p['product_score']}")
            if _p.get("historical_leads"): _meta.append(f"历史同期{_p['historical_leads']}条")
            if _meta:
                st.caption("数据依据：" + " · ".join(_meta))


# ══════════════════════════════════════════════
# 页面：执行监督台
# ══════════════════════════════════════════════
elif page == "✅ 执行监督台":
    render_hero("✅ 执行监督台", "实时追踪各部门任务执行情况，快速处理阻碍")

    # ── 顶部统计 ──
    _es = get_task_execution_stats()
    _em1, _em2, _em3, _em4, _em5 = st.columns(5)
    render_metric(_em1, _es["total"], "总任务数", color="#6366f1")
    render_metric(_em2, _es["done"], "已完成",
                  sub=f"{int(_es['completion_rate']*100)}% 完成率", color="#22c55e")
    _doing = _es["total"] - _es["done"] - _es["delayed"] - _es["blocked"]
    render_metric(_em3, max(0, _doing), "进行中", color="#3b82f6")
    render_metric(_em4, _es["delayed"], "延迟", color="#f59e0b")
    render_metric(_em5, _es["blocked"], "阻碍", color="#ef4444")

    st.divider()

    # ── 部门完成度 ──
    st.subheader("📊 部门执行完成度")
    _dept_data = _es.get("by_dept", {})
    if _dept_data:
        _dept_rows = []
        for _d, _v in _dept_data.items():
            _dept_rows.append({
                "部门": _d,
                "总任务": _v["total"],
                "已完成": _v["done"],
                "延迟": _v["delayed"],
                "阻碍": _v["blocked"],
                "完成率": f"{int(_v['completion_rate']*100)}%",
            })
        st.dataframe(pd.DataFrame(_dept_rows), width='stretch', hide_index=True)
    else:
        st.caption("暂无任务数据")

    st.divider()

    # ── 任务列表（筛选 + 一键更新状态）──
    st.subheader("📋 任务明细")
    _tf1, _tf2, _tf3 = st.columns(3)
    _tf_dept   = _tf1.selectbox("部门", ["全部"] + DEPT_OPTIONS)
    _tf_status = _tf2.selectbox("状态", ["全部", "todo", "doing", "delayed", "blocked", "done"])
    _tf_prio   = _tf3.selectbox("优先级", ["全部"] + PRIORITY_OPTIONS)

    _all_tasks = list_tasks(
        department=None if _tf_dept == "全部" else _tf_dept,
        status=None if _tf_status == "全部" else _tf_status,
        priority=None if _tf_prio == "全部" else _tf_prio,
        limit=200,
    )

    _STATUS_ICON = {"todo": "⬜", "doing": "🔵", "done": "✅", "delayed": "🟡", "blocked": "🔴", "cancelled": "⚫"}
    _PRIO_COLOR  = {"紧急": "#ef4444", "高": "#f97316", "中": "#3b82f6", "低": "#6b7280"}

    if not _all_tasks:
        st.info("暂无任务记录。以下为当前业务数据快照，供执行参考：")
        try:
            import pandas as _pd_exec
            _s1_exec  = get_order_stats(days=1)
            _s7_exec  = get_order_stats(days=7)
            _s30_exec = get_order_stats(days=30)
            st.markdown("### 📸 业务数据快照")
            _ec1, _ec2, _ec3, _ec4 = st.columns(4)
            _ec1.metric("今日订单", _s1_exec.get('total', 0))
            _ec2.metric("本周订单", _s7_exec.get('total', 0),
                        delta=f"营收元{int(_s7_exec.get('total_amount',0)/10000)}万")
            _ec3.metric("本月订单", _s30_exec.get('total', 0))
            _ec4.metric("本月营收", f"元{int(_s30_exec.get('total_amount',0)/10000)}万")

            # AI建议作为执行参考
            _suggs_exec = list_suggestions(limit=10)
            if _suggs_exec:
                st.markdown("### 💡 AI建议 → 待转化为执行任务")
                _exec_rows = []
                for _sg_e in _suggs_exec:
                    _exec_rows.append({
                        '建议类型': _sg_e.get('suggestion_type', '-'),
                        '标题': (_sg_e.get('title') or '')[:40],
                        '优先级': _sg_e.get('priority', '-'),
                        '状态': _sg_e.get('status', '-'),
                    })
                st.dataframe(_pd_exec.DataFrame(_exec_rows), width='stretch', hide_index=True)
                st.caption("👆 可在「部门任务台」将以上建议转化为具体执行任务")
        except Exception as _e_exec:
            st.caption(f"数据快照加载中：{_e_exec}")
    else:
        for _t in _all_tasks[:100]:
            with st.expander(
                f"{_STATUS_ICON.get(_t['status'],'⬜')} [{_t.get('priority','中')}] "
                f"{_t['title'][:60]} — {_t.get('department','')}",
                expanded=(_t["status"] in ("blocked", "delayed")),
            ):
                _tc1, _tc2 = st.columns([3, 1])
                with _tc1:
                    if _t.get("description"):
                        st.markdown(_t["description"])
                    _info = []
                    if _t.get("related_school"): _info.append(f"学校: {_t['related_school']}")
                    if _t.get("related_product"): _info.append(f"产品: {_t['related_product']}")
                    if _t.get("due_date"): _info.append(f"截止: {_t['due_date'][:10]}")
                    if _t.get("owner"): _info.append(f"负责人: {_t['owner']}")
                    if _info: st.caption(" · ".join(_info))
                    if _t.get("blockers"):
                        st.error(f"🚨 阻碍：{_t['blockers']}")
                    if _t.get("completion_result"):
                        st.success(f"✅ 完成结果：{_t['completion_result']}")
                with _tc2:
                    _new_status = st.selectbox(
                        "更新状态", ["todo", "doing", "done", "delayed", "blocked"],
                        index=["todo","doing","done","delayed","blocked"].index(_t["status"])
                              if _t["status"] in ["todo","doing","done","delayed","blocked"] else 0,
                        key=f"status_{_t['id']}")
                    _blocker_input = ""
                    _result_input  = ""
                    if _new_status in ("blocked", "delayed"):
                        _blocker_input = st.text_area("阻碍原因", key=f"blocker_{_t['id']}", height=60)
                    if _new_status == "done":
                        _result_input = st.text_area("完成结果", key=f"result_{_t['id']}", height=60)
                    if st.button("保存", key=f"save_{_t['id']}"):
                        update_task_extended(
                            _t["id"], status=_new_status,
                            blockers=_blocker_input or None,
                            completion_result=_result_input or None,
                        )
                        st.success("已更新")
                        st.rerun()

    st.divider()

    # ── 手动新建任务 ──
    with st.expander("➕ 手动新建任务"):
        _nc1, _nc2 = st.columns(2)
        _nt_title  = _nc1.text_input("任务标题", key="nt_title")
        _nt_dept   = _nc2.selectbox("部门", DEPT_OPTIONS, key="nt_dept")
        _nt_prio   = _nc1.selectbox("优先级", PRIORITY_OPTIONS, index=1, key="nt_prio")
        _nt_owner  = _nc2.text_input("负责人", key="nt_owner")
        _nt_school = _nc1.text_input("关联学校", key="nt_school")
        _nt_product= _nc2.text_input("关联产品", key="nt_product")
        _nt_due    = st.date_input("截止日期", key="nt_due")
        _nt_desc   = st.text_area("任务描述", key="nt_desc", height=80)
        if st.button("创建任务", type="primary", key="create_task"):
            if _nt_title:
                from database import save_task
                save_task({
                    "title": _nt_title, "department": _nt_dept,
                    "priority": _nt_prio, "owner": _nt_owner,
                    "related_school": _nt_school, "related_product": _nt_product,
                    "due_date": datetime.combine(_nt_due, datetime.min.time()),
                    "description": _nt_desc, "task_source": "手动",
                })
                st.success("任务已创建")
                st.rerun()
            else:
                st.warning("请填写任务标题")


# ══════════════════════════════════════════════
# 页面：周复盘台
# ══════════════════════════════════════════════
elif page in ("🔁 周复盘台", "🔁 每周复盘台"):
    render_hero("🔁 周复盘台", "预测 vs 实际对比 · 执行完成度分析 · 归因与下周重点")

    _reviews = list_weekly_reviews(limit=12)

    # ── 生成按钮 ──
    _rv1, _rv2 = st.columns([3, 1])
    _rv_week = _rv1.text_input("复盘周次（周一日期）",
                               value=(datetime.now() - __import__('datetime').timedelta(days=datetime.now().weekday()+7)).strftime("%Y-%m-%d"))
    if _rv2.button("▶ 生成本周复盘", type="primary"):
        with st.spinner("正在生成周复盘（Claude 分析归因）..."):
            try:
                from agents.weekly_review_agent import WeeklyReviewAgent
                import yaml
                with open(ROOT / "config.yaml") as _f:
                    _cfg = yaml.safe_load(_f)
                _rev = WeeklyReviewAgent(_cfg).run(week_start=_rv_week)
                st.success("复盘已生成，刷新查看。")
                st.rerun()
            except Exception as _e:
                st.error(f"生成失败：{_e}")

    if not _reviews:
        st.info("暂无AI复盘数据。以下为基于订单数据的本周快速复盘：")
        try:
            import datetime as _dt_wr
            import pandas as _pd_wr
            _today_wr    = _dt_wr.datetime.now()
            _week_start_wr = (_today_wr - _dt_wr.timedelta(days=_today_wr.weekday())).strftime('%Y-%m-%d')
            _orders_14_wr = list_orders(days=14, limit=1000)
            _this_week_wr = [o for o in _orders_14_wr if (o.get('order_date') or '')[:10] >= _week_start_wr]
            _last_week_wr = [o for o in _orders_14_wr if (o.get('order_date') or '')[:10] < _week_start_wr]

            st.markdown("## 🔁 本周数据复盘")
            c1_wr, c2_wr, c3_wr, c4_wr = st.columns(4)
            _tw_rev_wr = sum(o.get('amount', 0) for o in _this_week_wr)
            _lw_rev_wr = sum(o.get('amount', 0) for o in _last_week_wr)
            c1_wr.metric("本周订单", len(_this_week_wr), delta=f"vs上周{len(_last_week_wr)}单")
            c2_wr.metric("本周营收", f"元{int(_tw_rev_wr):,}", delta=f"vs上周元{int(_lw_rev_wr):,}")
            _tw_owners_wr = set(((o.get('sales_owner') or '') + ' ').split()[0] for o in _this_week_wr if o.get('sales_owner'))
            c3_wr.metric("本周成单顾问", len(_tw_owners_wr))
            _tw_prods_wr = {}
            for _o_wr in _this_week_wr:
                _p_wr = _o_wr.get('product', '') or ''
                _tw_prods_wr[_p_wr] = _tw_prods_wr.get(_p_wr, 0) + 1
            _best_prod_wr = max(_tw_prods_wr, key=_tw_prods_wr.get) if _tw_prods_wr else '-'
            c4_wr.metric("本周主力产品", (_best_prod_wr or '-')[:8],
                         delta=f"{_tw_prods_wr.get(_best_prod_wr, 0)}单" if _best_prod_wr != '-' else None)

            # 本周产品明细
            if _tw_prods_wr:
                st.markdown("**📦 本周产品分布**")
                _wr_prod_rows = [{'产品': p, '订单量': c} for p, c in
                                 sorted(_tw_prods_wr.items(), key=lambda x: -x[1]) if p]
                st.dataframe(_pd_wr.DataFrame(_wr_prod_rows), width='stretch', hide_index=True)

            # 上周 vs 本周对比
            if _last_week_wr:
                _lw_prods_wr = {}
                for _o_lw in _last_week_wr:
                    _p_lw = _o_lw.get('product', '') or ''
                    _lw_prods_wr[_p_lw] = _lw_prods_wr.get(_p_lw, 0) + 1
                _all_prods_wr = set(list(_tw_prods_wr.keys()) + list(_lw_prods_wr.keys()))
                _cmp_rows_wr = []
                for _pp in _all_prods_wr:
                    if not _pp:
                        continue
                    _tw_c = _tw_prods_wr.get(_pp, 0)
                    _lw_c = _lw_prods_wr.get(_pp, 0)
                    _cmp_rows_wr.append({'产品': _pp, '本周': _tw_c, '上周': _lw_c,
                                         '变化': f"{_tw_c - _lw_c:+d}"})
                if _cmp_rows_wr:
                    st.markdown("**📊 本周 vs 上周产品对比**")
                    st.dataframe(_pd_wr.DataFrame(sorted(_cmp_rows_wr, key=lambda x: -x['本周'])),
                                 width='stretch', hide_index=True)
        except Exception as _e_wr:
            st.caption(f"复盘数据加载中：{_e_wr}")

        # 展示 weekly_sales 建议作为复盘参考
        try:
            _wr_suggs = list_suggestions(suggestion_type="weekly_sales_suggestion", limit=5)
            if not _wr_suggs:
                _wr_suggs = list_suggestions(limit=5)
            if _wr_suggs:
                st.divider()
                st.markdown("### 💡 AI销售建议（作为本周复盘参考）")
                for _wr_sg in _wr_suggs[:5]:
                    _wr_txt = (_wr_sg.get('recommendation') or _wr_sg.get('content') or '')[:500]
                    _wr_tp  = _wr_sg.get('suggestion_type', '建议')
                    _wr_dt  = (_wr_sg.get('created_at') or '')[:10]
                    with st.expander(f"**[{_wr_tp}]** — {_wr_dt}", expanded=False):
                        st.markdown(_wr_txt if _wr_txt else "（内容待加载）")
        except Exception as _e_wr2:
            st.caption(f"建议加载中：{_e_wr2}")

        st.stop()

    # ── 选择复盘周 ──
    _week_options = [r["review_week"] for r in _reviews]
    _sel_week = st.selectbox("查看哪一周", _week_options)
    _rv = get_weekly_review(_sel_week)
    if not _rv:
        st.info("该周暂无复盘")
        st.stop()

    st.divider()

    # ── 预测 vs 实际 ──
    st.subheader("📈 预测 vs 实际")
    _kc = st.columns(4)
    render_metric(_kc[0], _rv["total_leads_predicted"], "预测咨询（中位）", color="#6366f1")
    render_metric(_kc[1], _rv["total_leads_actual"], "实际咨询",
                  sub=f"差值 {_rv['total_leads_actual'] - _rv['total_leads_predicted']:+d}",
                  color="#22c55e" if _rv["total_leads_actual"] >= _rv["total_leads_predicted"] else "#ef4444")
    render_metric(_kc[2], _rv["tasks_done"], "任务完成",
                  sub=f"共{_rv['tasks_total']}个 · delayed={_rv['tasks_delayed']} blocked={_rv['tasks_blocked']}",
                  color="#3b82f6")
    _cr = round(_rv["tasks_done"] / _rv["tasks_total"] * 100) if _rv["tasks_total"] else 0
    render_metric(_kc[3], f"{_cr}%", "任务完成率", color="#f59e0b")

    # ── 学校拆分 ──
    if _rv.get("school_breakdown"):
        st.subheader("🏫 各学校 预测 vs 实际")
        _bd_rows = sorted(_rv["school_breakdown"], key=lambda x: -x.get("actual", 0))[:10]
        _bd_df = pd.DataFrame([{
            "学校": r["school"], "预测": r["predicted"], "实际": r["actual"],
            "差值": f"{r['actual'] - r['predicted']:+d}",
        } for r in _bd_rows])
        st.dataframe(_bd_df, width='stretch', hide_index=True)

    # ── 部门完成度 ──
    if _rv.get("dept_completion"):
        st.subheader("✅ 部门执行完成度")
        _dc_rows = [{
            "部门": d, "总任务": v["total"], "已完成": v["done"],
            "完成率": f"{int(v.get('completion_rate', 0)*100)}%",
        } for d, v in _rv["dept_completion"].items()]
        st.dataframe(pd.DataFrame(_dc_rows), width='stretch', hide_index=True)

    st.divider()

    # ── 复盘文字 ──
    st.subheader("📝 复盘分析")
    _col_l, _col_r = st.columns(2)
    with _col_l:
        if _rv.get("key_wins"):
            st.markdown("**🌟 本周亮点**")
            for _w in _rv["key_wins"]:
                st.markdown(f"- {_w}")
        if _rv.get("root_causes"):
            st.markdown("**🔍 归因分析**")
            for _c in _rv["root_causes"]:
                st.markdown(f"- {_c}")
    with _col_r:
        if _rv.get("key_misses"):
            st.markdown("**⚠️ 本周落差**")
            for _m in _rv["key_misses"]:
                st.markdown(f"- {_m}")
        if _rv.get("next_week_focus"):
            st.markdown("**🎯 下周重点**")
            for _nf in _rv["next_week_focus"]:
                st.markdown(f"- {_nf}")

    if _rv.get("review_summary"):
        st.info(f"**总结：** {_rv['review_summary']}")


# ══════════════════════════════════════════════
# 页面：归因分析台 (V10)
# ══════════════════════════════════════════════
elif page == "📈 归因分析台":
    st.title("📈 归因分析台")
    st.caption("渠道 / 顾问 / 产品-学校 / 时效 · 基于真实成单数据归因分析")

    from database import get_latest_attribution, list_attribution_snapshots

    # ── 触发分析 ─────────────────────────────────────────────────────
    col_run, col_period = st.columns([2, 1])
    with col_run:
        days_lb = st.selectbox("分析区间（天）", [30, 60, 90, 180], index=2)
    with col_period:
        if st.button("🔄 重新分析", width='stretch'):
            with st.spinner("归因分析中…"):
                try:
                    from agents.attribution_analysis_agent import AttributionAnalysisAgent
                    _cfg = {}
                    try:
                        import yaml
                        with open("config/agents.yaml") as f:
                            _cfg = yaml.safe_load(f) or {}
                    except Exception:
                        pass
                    _snap = AttributionAnalysisAgent(_cfg).run(days_lookback=days_lb)
                    st.success(f"分析完成：{_snap['order_count']}条订单 / {_snap['lead_count']}条线索")
                    st.rerun()
                except Exception as _e:
                    st.error(f"分析失败：{_e}")

    snap = get_latest_attribution()

    # ── 实时数据归因（直接计算，不依赖snap） ─────────────────────────────
    st.markdown("### 📊 实时归因分析（直接数据库计算）")
    _attr_tab1, _attr_tab2, _attr_tab3, _attr_tab4 = st.tabs(
        ["👤 销售归因", "📦 产品归因", "🏫 学校归因", "📡 渠道归因"]
    )

    with _attr_tab1:
        st.markdown("##### 销售顾问业绩归因（近90天）")
        try:
            _orders_90 = list_orders(days=90, limit=3000)
            _owner_stats: dict = {}
            for _ao in _orders_90:
                _own = ((_ao.get('sales_owner') or '未分配') + ' ').split()[0]
                _owner_stats.setdefault(_own, {'cnt': 0, 'amt': 0, 'products': {}})
                _owner_stats[_own]['cnt'] += 1
                _owner_stats[_own]['amt'] += _ao.get('amount') or 0
                _prd = _ao.get('product') or '未知'
                _owner_stats[_own]['products'][_prd] = _owner_stats[_own]['products'].get(_prd, 0) + 1
            if _owner_stats:
                _attr1_rows = []
                for _ar, (_an, _ad) in enumerate(
                    sorted(_owner_stats.items(), key=lambda x: -x[1]['amt']), 1
                ):
                    _a_avg = int(_ad['amt'] / max(_ad['cnt'], 1))
                    _a_top_prod = max(_ad['products'], key=lambda p: _ad['products'][p]) if _ad['products'] else '—'
                    _attr1_rows.append({
                        '排名': _ar,
                        '姓名': _an,
                        '单量': _ad['cnt'],
                        '营收': f"元{int(_ad['amt']):,}",
                        '客单价': f"元{_a_avg:,}",
                        '主力产品': _a_top_prod,
                    })
                import pandas as _pd_a1
                st.dataframe(_pd_a1.DataFrame(_attr1_rows), width='stretch', hide_index=True)
            else:
                st.info("近90天暂无销售数据")
        except Exception as _e_a1:
            st.info(f"销售数据加载中：{_e_a1}")

    with _attr_tab2:
        st.markdown("##### 产品归因（全量）")
        try:
            _atr_os_all  = get_order_stats(days=0)
            _atr_os30    = get_order_stats(days=30)
            _atr_os60    = get_order_stats(days=60)
            _atr_p_all_cnt = dict(_atr_os_all.get('by_product', []))
            _atr_p_all_rev = dict(_atr_os_all.get('revenue_by_product', []))
            _atr_p30_cnt   = dict(_atr_os30.get('by_product', []))
            _atr_p60_cnt   = dict(_atr_os60.get('by_product', []))
            _atr_total_rev = sum(_atr_p_all_rev.values()) or 1
            _a2_rows = []
            for _ap in sorted(_atr_p_all_cnt.keys(), key=lambda p: -_atr_p_all_rev.get(p, 0)):
                _ap_cnt  = _atr_p_all_cnt.get(_ap, 0)
                _ap_rev  = _atr_p_all_rev.get(_ap, 0)
                _ap_30   = _atr_p30_cnt.get(_ap, 0)
                _ap_60h  = _atr_p60_cnt.get(_ap, 0) / 2
                _ap_avg  = int(_ap_rev / max(_ap_cnt, 1))
                _ap_pct  = round(_ap_rev / _atr_total_rev * 100, 1)
                _ap_trend = "📈" if _ap_30 > _ap_60h * 1.1 else "📉" if _ap_30 < _ap_60h * 0.9 else "➡️"
                _a2_rows.append({
                    '产品': _ap,
                    '总单量': _ap_cnt,
                    '总营收': f"元{int(_ap_rev):,}",
                    '近30天': _ap_30,
                    '均价': f"元{_ap_avg:,}",
                    '占总营收%': f"{_ap_pct}%",
                    '趋势': _ap_trend,
                })
            if _a2_rows:
                import pandas as _pd_a2
                st.dataframe(_pd_a2.DataFrame(_a2_rows), width='stretch', hide_index=True)
            else:
                st.info("暂无产品数据")
        except Exception as _e_a2:
            st.info(f"产品数据加载中：{_e_a2}")

    with _attr_tab3:
        st.markdown("##### 学校归因 — Top15（全量）")
        try:
            _atr_sch_all  = get_order_stats(days=0)
            _atr_sch_cnt  = dict(_atr_sch_all.get('by_school', []))
            _atr_sch_rev  = dict(_atr_sch_all.get('revenue_by_school', []))
            _top15_schs = [s for s, _ in _atr_sch_all.get('by_school', []) if _is_valid_school(s)][:15]
            # 主力产品（从orders计算）
            _atr_sch_orders = list_orders(days=365, limit=5000)
            _sch_prods: dict = {}
            for _sco in _atr_sch_orders:
                _s = _sco.get('school') or '未知'
                _p = _sco.get('product') or '未知'
                _sch_prods.setdefault(_s, {})
                _sch_prods[_s][_p] = _sch_prods[_s].get(_p, 0) + 1
            _a3_rows = []
            for _ri, _sc in enumerate(_top15_schs, 1):
                _sc_cnt = _atr_sch_cnt.get(_sc, 0)
                _sc_rev = _atr_sch_rev.get(_sc, 0)
                _sc_prods = _sch_prods.get(_sc, {})
                _sc_top_p = max(_sc_prods, key=lambda p: _sc_prods[p]) if _sc_prods else '—'
                _a3_rows.append({
                    '排名': _ri,
                    '学校': _sc,
                    '总单量': _sc_cnt,
                    '总营收': f"元{int(_sc_rev):,}",
                    '主力产品': _sc_top_p,
                })
            if _a3_rows:
                import pandas as _pd_a3
                st.dataframe(_pd_a3.DataFrame(_a3_rows), width='stretch', hide_index=True)
            else:
                st.info("暂无学校数据")
        except Exception as _e_a3:
            st.info(f"学校数据加载中：{_e_a3}")

    with _attr_tab4:
        # Tab4改为：国家/地区分布分析（从orders计算，因为leads渠道字段为空）
        st.subheader("🌏 国家/地区订单分布")
        try:
            _country_stats = get_order_stats(days=0)
            _country_data = [(c, n) for c, n in _country_stats.get('by_country', [])
                             if c and c not in ('未知', 'None', None)][:15]
            if _country_data:
                import pandas as _pd_ctry
                _ctry_df = _pd_ctry.DataFrame([
                    {'国家/地区': c, '订单量': n, '占比': f"{n/max(sum(x[1] for x in _country_data),1)*100:.1f}%"}
                    for c, n in _country_data
                ])
                st.dataframe(_ctry_df, width='stretch', hide_index=True)
            else:
                st.info("暂无国家/地区数据")

            # 销售顾问-产品矩阵
            st.subheader("👤 顾问专长产品分析（近90天）")
            _orders_90c = list_orders(days=90, limit=3000)
            _advisor_prod = {}
            for _o in _orders_90c:
                _own = ((_o.get('sales_owner') or '未分配') + ' ').split()[0]
                _prd = _o.get('product') or '未知'
                _advisor_prod.setdefault(_own, {})
                _advisor_prod[_own][_prd] = _advisor_prod[_own].get(_prd, 0) + 1
            if _advisor_prod:
                _rows_ap = []
                for _own, _prods in sorted(_advisor_prod.items(), key=lambda x: -sum(x[1].values()))[:10]:
                    _best_prd = max(_prods, key=_prods.get)
                    _total = sum(_prods.values())
                    _rows_ap.append({'顾问': _own, '近90天总单': _total, '主力产品': _best_prd,
                                     '主力产品单量': _prods[_best_prd],
                                     '其他产品': '/'.join(f"{p}({n})" for p, n in sorted(_prods.items(), key=lambda x: -x[1]) if p != _best_prd)[:50]})
                import pandas as _pd_ap
                st.dataframe(_pd_ap.DataFrame(_rows_ap), width='stretch', hide_index=True)
        except Exception as _e_tab4:
            st.warning(f"加载中：{_e_tab4}")

    st.divider()

    if not snap:
        st.info("暂无AI归因快照，点击「重新分析」生成。（实时数据已在上方展示）")
        st.stop()

    st.caption(f"AI快照区间：{snap['period_start']} → {snap['period_end']}  ·  生成于 {snap['created_at'][:10]}")

    # ── 总览指标 ────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("分析订单数", snap["order_count"])
    m2.metric("分析线索数", snap["lead_count"])
    m3.metric("总营收", f"元{snap['total_revenue']:,.0f}")
    ch_data = snap.get("channel_data") or []
    top_ch = ch_data[0]["channel"] if ch_data else "-"
    m4.metric("最高营收渠道", top_ch)

    # ── 关键洞察 ────────────────────────────────────────────────────
    insights = snap.get("key_insights") or []
    actions  = snap.get("action_items") or []
    if insights:
        st.subheader("💡 关键洞察")
        for _ins in insights:
            st.success(f"· {_ins}")
    if actions:
        st.subheader("🎯 下周行动建议")
        for _act in actions:
            st.info(f"→ {_act}")

    st.divider()

    # ── Tab 分四个维度 ───────────────────────────────────────────────
    tab_ch, tab_adv, tab_ps, tab_speed = st.tabs(
        ["📡 渠道归因", "👤 顾问归因", "📦 产品×学校", "⏱ 时效归因"]
    )

    with tab_ch:
        st.markdown("##### 渠道归因（线索来源 → 成单 → 营收）")
        ch_data = snap.get("channel_data") or []
        if ch_data:
            import pandas as pd
            df_ch = pd.DataFrame(ch_data)
            df_ch = df_ch.rename(columns={
                "channel": "渠道", "lead_count": "线索数",
                "order_count": "成单数", "revenue": "营收(¥)",
                "cvr": "转化率(%)", "avg_days_to_close": "平均成交天数"
            })
            st.dataframe(df_ch, width='stretch', hide_index=True)

            # 营收条形图
            try:
                import plotly.express as px
                fig = px.bar(df_ch, x="渠道", y="营收(¥)", color="转化率(%)",
                             color_continuous_scale="RdYlGn",
                             title="各渠道营收 & 转化率")
                st.plotly_chart(fig, width='stretch')
            except ImportError:
                pass
        else:
            st.info("暂无渠道数据")

    with tab_adv:
        st.markdown("##### 顾问归因（GMV / 单量 / 客单价）")
        adv_data = snap.get("advisor_data") or []
        if adv_data:
            import pandas as pd
            df_adv = pd.DataFrame(adv_data)
            df_adv = df_adv.rename(columns={
                "advisor": "顾问", "order_count": "成单数",
                "gmv": "GMV(¥)", "avg_amount": "客单价(¥)",
                "top_product": "主力产品", "top_school": "主力学校"
            })
            st.dataframe(df_adv, width='stretch', hide_index=True)

            try:
                import plotly.express as px
                fig = px.bar(df_adv, x="顾问", y="GMV(¥)", text="成单数",
                             title="顾问 GMV 对比")
                fig.update_traces(textposition="outside")
                st.plotly_chart(fig, width='stretch')
            except ImportError:
                pass
        else:
            st.info("暂无顾问数据")

    with tab_ps:
        st.markdown("##### 产品 × 学校成单热力分析（Top 20）")
        ps_data = snap.get("product_school_data") or []
        if ps_data:
            import pandas as pd
            df_ps = pd.DataFrame(ps_data[:20])
            df_ps = df_ps.rename(columns={
                "product": "产品", "school": "学校",
                "order_count": "成单数", "revenue": "营收(¥)", "avg_amount": "客单价(¥)"
            })
            st.dataframe(df_ps, width='stretch', hide_index=True)

            try:
                import plotly.express as px
                pivot = df_ps.pivot_table(
                    index="产品", columns="学校", values="成单数", fill_value=0
                )
                fig = px.imshow(pivot, color_continuous_scale="Blues",
                                title="产品 × 学校成单热力图", aspect="auto")
                st.plotly_chart(fig, width='stretch')
            except ImportError:
                pass
        else:
            st.info("暂无产品-学校数据")

    with tab_speed:
        st.markdown("##### 时效归因（线索 → 成单平均天数，按顾问）")
        speed_data = snap.get("speed_data") or []
        if speed_data:
            import pandas as pd
            df_sp = pd.DataFrame(speed_data)
            df_sp = df_sp.rename(columns={
                "advisor": "顾问", "sample_count": "样本数",
                "avg_days": "平均天数", "median_days": "中位数天数",
                "min_days": "最快(天)", "max_days": "最慢(天)"
            })
            st.dataframe(df_sp, width='stretch', hide_index=True)

            try:
                import plotly.express as px
                fig = px.bar(df_sp, x="顾问", y="平均天数",
                             error_y=df_sp["最慢(天)"] - df_sp["平均天数"],
                             title="各顾问平均成交周期（越低越快）",
                             color="平均天数", color_continuous_scale="RdYlGn_r")
                st.plotly_chart(fig, width='stretch')
            except ImportError:
                pass
        else:
            st.info("暂无时效数据（需要线索和订单能匹配到同一客户）")

    # ── 历史快照 ────────────────────────────────────────────────────
    with st.expander("📂 历史归因快照"):
        history = list_attribution_snapshots(limit=10)
        for _h in history:
            st.markdown(
                f"**{_h['snapshot_date']}** — {_h['period_start']}→{_h['period_end']} "
                f"| {_h['order_count']}单 元{_h['total_revenue']:,.0f}"
            )
            for _ins in (_h.get("key_insights") or []):
                st.caption(f"· {_ins}")
            st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# V11 建设中的模块（stub）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 学管销售台":
    st.title("📋 学管销售台")
    st.caption("渠道线索跟进 · 销售风险预警 · 新品销售准备 — 学管（推广/小红书/垂直号渠道销售）")

    from database.models import Order, Lead, OrderRiskSignal
    from database.db import get_session
    from database import list_product_launches, list_deliverables
    from sqlalchemy import func as _f
    from datetime import datetime as _dt, timedelta as _td

    now_dt = _dt.now()

    # ── 数据加载 ──────────────────────────────────────────────────────────────
    with get_session() as _s:
        # 近30天订单
        _orders_all = _s.query(Order).filter(
            Order.created_at >= now_dt - _td(days=30)
        ).order_by(Order.deadline).all()
        _orders_dict = [{c.name: getattr(r,c.name) for c in r.__table__.columns} for r in _orders_all]

        # DDL危险订单（7天内到期）
        _ddl_danger = [o for o in _orders_dict if o.get("deadline") and (
            isinstance(o["deadline"], _dt) and (o["deadline"] - now_dt).days <= 7
            or isinstance(o["deadline"], str) and o["deadline"]
        )]

        # 风险信号
        _risks = _s.query(OrderRiskSignal).order_by(OrderRiskSignal.created_at.desc()).limit(30).all()
        _risks_dict = [{c.name: getattr(r,c.name) for c in r.__table__.columns} for r in _risks]

        # 近30天线索（待承接）
        _leads_pending = _s.query(Lead).filter(
            Lead.deal_status.in_(["won", "completed"]),
            Lead.created_at >= now_dt - _td(days=30)
        ).order_by(Lead.deadline).all()
        _leads_dict = [{c.name: getattr(r,c.name) for c in r.__table__.columns} for r in _leads_pending]

    # ── 顶部汇总指标 ──────────────────────────────────────────────────────────
    _ma1,_ma2,_ma3,_ma4,_ma5 = st.columns(5)
    _ma1.metric("📦 近30天订单", len(_orders_dict))
    _ma2.metric("🚨 7天内DDL", len(_ddl_danger), delta=f"需紧急跟进" if _ddl_danger else None, delta_color="inverse")
    _ma3.metric("⚠️ 风险信号", len(_risks_dict))
    _ma4.metric("✅ 已成交线索（近30天）", len(_leads_dict))
    # 产品上线交付物问题
    _pl_all = list_product_launches()
    _deliv_issues = sum(
        sum(1 for d in list_deliverables((_lc if isinstance(_lc,dict) else _lc.__dict__).get("id")) if d.get("sales_flagged"))
        for _lc in _pl_all
    ) if _pl_all else 0
    _ma5.metric("🚩 新品销售待确认", _deliv_issues)

    st.divider()

    _tab_ddl, _tab_orders, _tab_risks, _tab_accept, _tab_launch = st.tabs([
        "🚨 DDL预警", "📦 订单管理", "⚠️ 风险信号", "📲 渠道线索跟进", "🚀 新品销售准备"
    ])

    # ── Tab1: DDL预警 ─────────────────────────────────────────────────────────
    with _tab_ddl:
        if not _ddl_danger:
            st.success("✅ 近7天无即将到期订单")
        else:
            st.error(f"共 {len(_ddl_danger)} 单即将到期，请优先处理！")
            for _o in sorted(_ddl_danger, key=lambda x: x.get("deadline") or "9999"):
                _ddl = _o.get("deadline")
                if isinstance(_ddl, _dt):
                    _days_left = (_ddl - now_dt).days
                    _ddl_str = _ddl.strftime("%m-%d %H:%M")
                elif _ddl:
                    _days_left = "?"
                    _ddl_str = str(_ddl)[:16]
                else:
                    continue
                _urgency = "🔴" if isinstance(_days_left,int) and _days_left<=2 else "🟡"
                _c1,_c2,_c3,_c4 = st.columns([3,2,2,2])
                _c1.markdown(f"{_urgency} **{_o.get('customer_id','—')}**")
                _c1.caption(f"{_o.get('product','—')} · {_o.get('service_type','—')}")
                _c2.markdown(f"DDL: `{_ddl_str}`")
                _c3.markdown(f"剩余: **{_days_left}天**" if isinstance(_days_left,int) else "剩余:?")
                _c4.markdown(f"元{int(_o.get('amount') or 0):,}")
                st.divider()

    # ── Tab2: 订单管理 ────────────────────────────────────────────────────────
    with _tab_orders:
        if not _orders_dict:
            st.info("近30天暂无订单数据")
        else:
            # 按产品分组统计
            _by_prod = {}
            for _o in _orders_dict:
                _p = _o.get("product","其他")
                _by_prod.setdefault(_p, []).append(_o)

            for _prod, _ords in sorted(_by_prod.items(), key=lambda x: -len(x[1])):
                _total_rev = sum(_o.get("amount") or 0 for _o in _ords)
                with st.expander(f"**{_prod}** — {len(_ords)}单 · 元{int(_total_rev):,}", expanded=False):
                    for _o in _ords:
                        _oc1,_oc2,_oc3,_oc4 = st.columns([3,2,2,2])
                        _oc1.markdown(f"{_o.get('customer_id','—')}")
                        _oc1.caption(f"{_o.get('school','')} {_o.get('major','')}")
                        _ddl_raw = _o.get("deadline")
                        _oc2.caption(f"DDL: {str(_ddl_raw)[:16] if _ddl_raw else '未设'}")
                        _oc3.caption(f"负责: {_o.get('sales_owner','—')}")
                        _oc4.caption(f"元{int(_o.get('amount') or 0):,}")

    # ── Tab3: 风险信号 ────────────────────────────────────────────────────────
    with _tab_risks:
        if not _risks_dict:
            st.success("✅ 暂无风险信号")
        else:
            _risk_types = {"ddl_risk":"⏰ DDL风险","missing_material":"📄 材料缺失",
                          "teacher_unresponsive":"👨‍🏫 老师未响应","client_complaint":"😤 客户投诉",
                          "quality_risk":"🔍 质量风险"}
            for _r in _risks_dict:
                _rtype = _risk_types.get(_r.get("risk_type",""), _r.get("risk_type","⚠️ 风险"))
                _rc1,_rc2 = st.columns([5,2])
                with _rc1:
                    st.markdown(f"**{_rtype}** — 订单 #{_r.get('order_id','?')}")
                    if _r.get("description"):
                        st.caption(_r["description"])
                with _rc2:
                    st.caption(str(_r.get("created_at",""))[:16])
                st.divider()

    # ── Tab4: 渠道线索跟进 ────────────────────────────────────────────────────
    with _tab_accept:
        st.caption("学管负责承接推广/小红书/垂直号渠道线索，跟进转化，记录成交或流失原因")
        if not _leads_dict:
            st.info("近30天暂无已成交线索")
        else:
            st.info(f"共 {len(_leads_dict)} 条近30天已成交线索")
            for _l in _leads_dict:
                _lc1,_lc2,_lc3,_lc4 = st.columns([3,2,2,2])
                _lc1.markdown(f"**{_l.get('customer_name','匿名')}**")
                _lc1.caption(f"{_l.get('product_interest','—')} · {_l.get('school','')}")
                _lc2.caption(f"渠道: {_l.get('source_channel','—')}")
                _ddl_l = _l.get("deadline")
                _lc3.caption(f"DDL: {str(_ddl_l)[:10] if _ddl_l else '未定'}")
                _lc4.caption(f"元{int(_l.get('quoted_price') or 0):,}")
                # 销售跟进清单
                with st.expander("📋 成交记录确认", expanded=False):
                    _items = [
                        "客户痛点已准确识别",
                        "产品已匹配客户需求",
                        "报价已确认（无超出承诺范围）",
                        "成交后信息已规范交接给后台",
                        "客户预期已管理（交付边界已告知）",
                        "是否有复购 / 转介绍机会",
                    ]
                    for _item in _items:
                        st.checkbox(_item, key=f"accept_{_l.get('id','?')}_{_item[:8]}")
                st.divider()

    # ── Tab5: 新品销售准备 ────────────────────────────────────────────────────
    with _tab_launch:
        st.caption("学管在新品上线前需确认：产品培训已完成 · 渠道话术已就绪 · 哪类线索适合这个产品")
        if not _pl_all:
            st.info("暂无在途新产品上线卡")
        else:
            for _lc in _pl_all:
                _ld = _lc if isinstance(_lc, dict) else _lc.__dict__
                _pname = _ld.get("product_name","—")
                _delivs = list_deliverables(_ld.get("id"))
                _xg_delivs = [d for d in _delivs if "学管" in (d.get("owner_dept") or "")]
                _xg_flagged = [d for d in _xg_delivs if d.get("sales_flagged")]
                if not _xg_delivs:
                    continue
                _done = sum(1 for d in _xg_delivs if d.get("status") in ("已完成","已交付"))
                _gate2 = _ld.get("gate2_status","not_started")
                _gate2_icon = {"not_started":"⬜","in_progress":"🟡","passed":"🟢","blocked":"🔴"}.get(_gate2,"⬜")
                with st.expander(
                    f"{'🔴' if _xg_flagged else '🟡' if _done<len(_xg_delivs) else '🟢'} "
                    f"**{_pname}** — 学管销售准备 {_done}/{len(_xg_delivs)} 项完成"
                    + (f" 🚩{len(_xg_flagged)}项待处理" if _xg_flagged else ""),
                    expanded=bool(_xg_flagged)
                ):
                    st.markdown("**学管需完成的销售准备：**")
                    for _dv in _xg_delivs:
                        _dv_s = _dv.get("status","待完成")
                        _icon = {"待完成":"⬜","进行中":"🟡","已完成":"🟢","有问题":"🔴"}.get(_dv_s,"⬜")
                        _flag = " 🚩" if _dv.get("sales_flagged") else ""
                        st.markdown(f"{_icon} {_dv.get('deliverable','—')}{_flag}")
                        if _dv.get("sales_note"):
                            st.caption(f"　反馈：{_dv['sales_note']}")
                    st.caption("关卡进度：" + " → ".join(
                        f"{'✅' if _ld.get(f'gate{i}_status')=='passed' else '🟡' if _ld.get(f'gate{i}_status')=='in_progress' else '⬜'}关{i}"
                        for i in range(1,6)
                    ))
                    if _ld.get("has_delivery_risk"):
                        st.error("⚠️ 该产品存在销售风险提示，学管需在推荐前了解不能承诺的内容")

    # ══ 新增：团队全量业绩排行（2023-至今） ════════════════════════════════
    st.divider()
    st.markdown("### 🏆 团队全量业绩排行（全量历史）")
    try:
        _xg_all_orders = list_orders(days=1460, limit=20000)  # 4年
        _xg_owner_all: dict = {}
        for _xo in _xg_all_orders:
            _xown = ((_xo.get('sales_owner') or '未分配') + ' ').split()[0]
            _xg_owner_all.setdefault(_xown, {'cnt': 0, 'amt': 0, 'months': set(), 'products': {}})
            _xg_owner_all[_xown]['cnt'] += 1
            _xg_owner_all[_xown]['amt'] += _xo.get('amount') or 0
            _xm = (_xo.get('order_date') or '')[:7]
            if _xm: _xg_owner_all[_xown]['months'].add(_xm)
            _xp = _xo.get('product') or '未知'
            _xg_owner_all[_xown]['products'][_xp] = _xg_owner_all[_xown]['products'].get(_xp, 0) + 1
        if _xg_owner_all:
            _xg_all_rows = []
            for _xr, (_xn, _xd) in enumerate(
                sorted(_xg_owner_all.items(), key=lambda x: -x[1]['amt']), 1
            ):
                _xm_cnt = max(len(_xd['months']), 1)
                _xavg_m = int(_xd['cnt'] / _xm_cnt)
                _xtp = max(_xd['products'], key=lambda p: _xd['products'][p]) if _xd['products'] else '—'
                _xg_all_rows.append({
                    '排名': _xr,
                    '姓名': _xn,
                    '总单量': _xd['cnt'],
                    '总营收': f"元{int(_xd['amt']):,}",
                    '月均单量': _xavg_m,
                    '主力产品': _xtp,
                })
            import pandas as _pd_xg
            st.dataframe(_pd_xg.DataFrame(_xg_all_rows), width='stretch', hide_index=True)
        else:
            st.info("暂无历史销售数据")
    except Exception as _e_xg:
        st.info(f"历史数据加载中：{_e_xg}")

    # ══ 新增：近30天 vs 上30天对比 ════════════════════════════════════════
    st.divider()
    st.markdown("### 📊 近30天 vs 上30天 销售对比")
    try:
        import datetime as _xdt
        _xnow = _xdt.datetime.now()
        _x30_start = (_xnow - _xdt.timedelta(days=30)).strftime('%Y-%m-%d')
        _x60_start = (_xnow - _xdt.timedelta(days=60)).strftime('%Y-%m-%d')
        _x60_end   = (_xnow - _xdt.timedelta(days=31)).strftime('%Y-%m-%d')
        _xg_60_orders = list_orders(days=60, limit=3000)
        _xg_this30 = [o for o in _xg_60_orders if (o.get('order_date') or '') >= _x30_start]
        _xg_last30 = [o for o in _xg_60_orders
                      if _x60_start <= (o.get('order_date') or '') <= _x60_end]
        _xg_this_map: dict = {}
        _xg_last_map: dict = {}
        for _xo in _xg_this30:
            _n = ((_xo.get('sales_owner') or '未分配') + ' ').split()[0]
            _xg_this_map[_n] = _xg_this_map.get(_n, 0) + 1
        for _xo in _xg_last30:
            _n = ((_xo.get('sales_owner') or '未分配') + ' ').split()[0]
            _xg_last_map[_n] = _xg_last_map.get(_n, 0) + 1
        _all_xg_owners = set(list(_xg_this_map.keys()) + list(_xg_last_map.keys()))
        if _all_xg_owners:
            _cmp_rows = []
            for _xn in sorted(_all_xg_owners, key=lambda n: -_xg_this_map.get(n, 0)):
                _this = _xg_this_map.get(_xn, 0)
                _last = _xg_last_map.get(_xn, 0)
                _diff = _this - _last
                _pct  = f"+{_diff}" if _diff >= 0 else str(_diff)
                _rate = f"{_diff / max(_last, 1) * 100:.0f}%" if _last else "—"
                _cmp_rows.append({
                    '姓名': _xn,
                    '近30天单量': _this,
                    '上30天单量': _last,
                    '变化': _pct,
                    '变化率': _rate,
                })
            import pandas as _pd_cmp
            st.dataframe(_pd_cmp.DataFrame(_cmp_rows), width='stretch', hide_index=True)
        else:
            st.info("近60天暂无销售数据")
    except Exception as _e_cmp:
        st.info(f"对比数据加载中：{_e_cmp}")

elif page == "🚦 产品红绿灯":
    st.title("🚦 产品红绿灯")
    st.caption("全产品健康度一览 — 绿色可放大，黄色需观察，红色需干预")

    # ══ 实时产品健康度 ══════════════════════════════════════════════════════
    try:
        st.markdown("### ⚡ 实时产品健康度")
        _s0 = get_order_stats(days=0)
        _s30 = get_order_stats(days=30)
        _s90 = get_order_stats(days=90)
        _pr_all = dict(_s0['by_product'])
        _pr_30  = dict(_s30['by_product'])
        _pr_90  = dict(_s90['by_product'])
        _pr_rev = dict(_s0.get('revenue_by_product', []))

        _product_list = [p for p, _ in _s0['by_product'] if p and p != '未知']
        _cols_tl = st.columns(min(len(_product_list), 3))
        for i, prd in enumerate(_product_list[:6]):
            cnt_30 = _pr_30.get(prd, 0)
            cnt_90_daily = _pr_90.get(prd, 0) / 3  # 月均
            status = "🟢 增长" if cnt_30 >= cnt_90_daily * 1.1 else ("🟡 稳定" if cnt_30 >= cnt_90_daily * 0.8 else "🔴 下滑")
            with _cols_tl[i % 3]:
                st.metric(f"{status} {prd}", f"{cnt_30}单/月", delta=f"历史月均{int(cnt_90_daily)}单")
        st.divider()
    except Exception as _e_tl:
        st.info(f"产品健康度加载中：{_e_tl}")

    from database import list_product_launches, list_deliverables
    from database.models import Lead, Order
    from database.db import get_session
    from sqlalchemy import func as _func

    launches = list_product_launches()

    if not launches:
        st.info("暂无产品数据，请在「新产品上线台」创建产品上线卡。")
    else:
        def _get_stats(pname):
            try:
                with get_session() as s:
                    leads = s.query(_func.count(Lead.id)).filter(Lead.product_interest.ilike(f"%{pname}%")).scalar() or 0
                    won = s.query(_func.count(Lead.id)).filter(Lead.product_interest.ilike(f"%{pname}%"), Lead.deal_status.in_(["won", "completed"])).scalar() or 0
                    orders = s.query(_func.count(Order.id)).filter(Order.product.ilike(f"%{pname}%")).scalar() or 0
                    revenue = s.query(_func.sum(Order.amount)).filter(Order.product.ilike(f"%{pname}%")).scalar() or 0
                cvr = round(won/leads*100,1) if leads>0 else 0
                return leads, won, orders, revenue, cvr
            except Exception:
                return 0,0,0,0,0

        def _score(ld, delivs, stats):
            """综合评分 0-100，决定红绿灯颜色"""
            score = 100
            leads, won, orders, revenue, cvr = stats
            # 关卡阻断 -20
            for i in range(1,6):
                if ld.get(f"gate{i}_status") == "blocked": score -= 20
            # 关卡停滞 -10
            for i in range(1,6):
                if ld.get(f"gate{i}_status") == "not_started" and i <= 3: score -= 5
            # 交付物问题 -5 each
            flagged = sum(1 for d in delivs if d.get("sales_flagged"))
            score -= flagged * 5
            # 管理层叫停 -30
            if ld.get("mgmt_approval") == "stopped": score -= 30
            # 管理层推迟 -10
            if ld.get("mgmt_approval") == "deferred": score -= 10
            # 异常标记 -10 each
            if ld.get("has_delivery_risk"): score -= 10
            if ld.get("sales_continuing_promises") and ld.get("mgmt_approval")=="stopped": score -= 20
            # 咨询转化率低 -10
            if leads >= 5 and cvr < 10: score -= 10
            # 有成交加分
            if orders >= 3: score += 10
            if cvr >= 30: score += 10
            return max(0, min(100, score))

        # 汇总行
        total = len(launches)
        green_count = yellow_count = red_count = 0

        product_data = []
        for lc in launches:
            ld = lc if isinstance(lc, dict) else lc.__dict__
            pname = ld.get("product_name","—")
            delivs = list_deliverables(ld.get("id"))
            stats = _get_stats(pname)
            score = _score(ld, delivs, stats)
            if score >= 70: green_count += 1
            elif score >= 40: yellow_count += 1
            else: red_count += 1
            product_data.append((ld, delivs, stats, score))

        # 汇总指标
        mc1,mc2,mc3,mc4 = st.columns(4)
        mc1.metric("🟢 健康（可放大）", green_count)
        mc2.metric("🟡 观察（需跟进）", yellow_count)
        mc3.metric("🔴 风险（需干预）", red_count)
        mc4.metric("📦 产品总数", total)
        st.divider()

        # 排序：红→黄→绿
        product_data.sort(key=lambda x: x[3])

        for ld, delivs, stats, score in product_data:
            pname = ld.get("product_name","—")
            leads, won, orders, revenue, cvr = stats

            if score >= 70:
                light = "🟢"; color = "#16a34a"; label = "健康 · 可放大"
            elif score >= 40:
                light = "🟡"; color = "#d97706"; label = "观察 · 需跟进"
            else:
                light = "🔴"; color = "#dc2626"; label = "风险 · 需干预"

            # 关卡进度条文字
            gate_str = " → ".join(
                f"{'✅' if ld.get(f'gate{i}_status')=='passed' else '🔴' if ld.get(f'gate{i}_status')=='blocked' else '🟡' if ld.get(f'gate{i}_status')=='in_progress' else '⬜'}关{i}"
                for i in range(1,6)
            )

            with st.container():
                col_light, col_info, col_metrics = st.columns([1,4,4])
                with col_light:
                    st.markdown(
                        f"<div style='font-size:48px;text-align:center'>{light}</div>"
                        f"<div style='text-align:center;font-size:12px;color:{color};font-weight:600'>{label}</div>"
                        f"<div style='text-align:center;font-size:18px;font-weight:700;color:{color}'>{score}分</div>",
                        unsafe_allow_html=True
                    )
                with col_info:
                    st.markdown(f"**{pname}**")
                    st.caption(f"负责人：{ld.get('owner','—')} ｜ 审批：{ld.get('mgmt_approval','pending')}")
                    st.caption(gate_str)
                    flagged = sum(1 for d in delivs if d.get("sales_flagged"))
                    if flagged:
                        st.error(f"🚩 {flagged} 项交付物有问题")
                    if ld.get("mgmt_approval") == "stopped":
                        st.error("🛑 管理层已叫停")
                with col_metrics:
                    mc1,mc2,mc3 = st.columns(3)
                    mc1.metric("咨询", leads)
                    mc2.metric("成交", orders)
                    mc3.metric("转化", f"{cvr}%")
                    mc1.metric("收入", f"元{int(revenue):,}" if revenue else "¥0")
                    mc2.metric("交付物问题", flagged)
                    mc3.metric("综合评分", f"{score}/100")

                # 处置建议
                if score < 40:
                    suggestions = []
                    for i in range(1,6):
                        if ld.get(f"gate{i}_status") == "blocked":
                            suggestions.append(f"关{i}已阻断，需立即解锁")
                    if flagged: suggestions.append(f"处理 {flagged} 项被标记的交付物")
                    if ld.get("mgmt_approval")=="stopped": suggestions.append("管理层已叫停，等待新指令")
                    if leads>=5 and cvr<10: suggestions.append(f"转化率仅{cvr}%，建议复盘话术或定价")
                    if suggestions:
                        with st.expander("💡 处置建议", expanded=True):
                            for s in suggestions:
                                st.warning(s)
                elif score < 70:
                    with st.expander("💡 跟进建议", expanded=False):
                        if leads < 3: st.info("咨询量偏少，建议加强推广")
                        if cvr < 20: st.info(f"转化率{cvr}%偏低，建议顾问复盘话术")
                        not_started = [i for i in range(1,6) if ld.get(f"gate{i}_status")=="not_started"]
                        if not_started: st.info(f"关{not_started}尚未启动，请推进")
                st.divider()

elif page == "🔮 增长预测台":
    import datetime as _fdt_mod
    import pandas as _pd_fc

    st.markdown("## 🔮 增长预测台")
    st.caption("基于真实历史数据的预测 · 不是占位页 · 每周自动更新")

    # ── 月度目标设置 ──────────────────────────────────────────
    _fc_target = st.number_input("📌 月度营收目标（万元）", min_value=50, max_value=5000, value=200, step=10, key="fc_target")
    _fc_target_rev = _fc_target * 10000

    # ── 基础数据 ──────────────────────────────────────────────
    try:
        _fc_now = _fdt_mod.datetime.now()
        _fc_day = _fc_now.day
        _fc_month_days = (_fc_now.replace(month=_fc_now.month % 12 + 1, day=1) - _fdt_mod.timedelta(days=1)).day if _fc_now.month < 12 else 31

        # 近365天订单做趋势分析
        _fc_orders = list_orders(days=730, limit=20000)
        if not _fc_orders:
            st.info("no_data：orders 表暂无真实订单，增长预测台不生成收入、订单、产品趋势或行动结论。")
            st.stop()

        # 按月聚合
        _fc_monthly_cnt = {}
        _fc_monthly_rev = {}
        for _o in _fc_orders:
            _ym = (_o.get('order_date') or '')[:7]
            if len(_ym) == 7:
                _fc_monthly_cnt[_ym] = _fc_monthly_cnt.get(_ym, 0) + 1
                _fc_monthly_rev[_ym] = _fc_monthly_rev.get(_ym, 0) + (_o.get('amount') or 0)

        _fc_months_sorted = sorted(_fc_monthly_cnt.keys())
        _fc_last12 = _fc_months_sorted[-13:-1] if len(_fc_months_sorted) > 13 else _fc_months_sorted[:-1]

        # 当月已完成
        _fc_this_month = _fc_now.strftime('%Y-%m')
        _fc_this_rev = _fc_monthly_rev.get(_fc_this_month, 0)
        _fc_this_cnt = _fc_monthly_cnt.get(_fc_this_month, 0)

        # 日均（基于近3个月，排除本月）
        _fc_recent_rev = [_fc_monthly_rev.get(m, 0) for m in _fc_last12[-3:]]
        _fc_recent_cnt = [_fc_monthly_cnt.get(m, 0) for m in _fc_last12[-3:]]
        _fc_avg_monthly_rev = sum(_fc_recent_rev) / max(len(_fc_recent_rev), 1)
        _fc_avg_monthly_cnt = sum(_fc_recent_cnt) / max(len(_fc_recent_cnt), 1)

        # 本月预测（按当前进度外推）
        _fc_progress = _fc_day / _fc_month_days
        _fc_proj_rev = _fc_this_rev / max(_fc_progress, 0.01)
        _fc_proj_cnt = _fc_this_cnt / max(_fc_progress, 0.01)

        # 下月预测（基于近3月均值，考虑季节性）
        _fc_next_month_num = (_fc_now.month % 12) + 1
        _fc_same_month_last_year = f"{_fc_now.year - 1}-{_fc_next_month_num:02d}"
        _fc_seasonal_factor = _fc_monthly_rev.get(_fc_same_month_last_year, _fc_avg_monthly_rev) / max(_fc_avg_monthly_rev, 1)
        _fc_next_rev = _fc_avg_monthly_rev * max(min(_fc_seasonal_factor, 1.5), 0.5)
        _fc_next_cnt = _fc_avg_monthly_cnt * max(min(_fc_seasonal_factor, 1.5), 0.5)

    except Exception as _e_fc_data:
        st.error(f"数据加载失败：{_e_fc_data}")
        st.stop()

    # ── 预测结果展示 ───────────────────────────────────────────
    _fc_c1, _fc_c2, _fc_c3, _fc_c4 = st.columns(4)
    _fc_c1.metric("本月预计营收", f"元{int(_fc_proj_rev/10000)}万", delta=f"已完成元{int(_fc_this_rev/10000)}万")
    _fc_c2.metric("本月预计订单", f"{int(_fc_proj_cnt)}单", delta=f"已完成{_fc_this_cnt}单")
    _fc_c3.metric("下月预测营收", f"元{int(_fc_next_rev/10000)}万", delta=f"季节因子{_fc_seasonal_factor:.1f}x")
    _fc_c4.metric("下月预测订单", f"{int(_fc_next_cnt)}单")

    # ── 目标差距分析 ──────────────────────────────────────────
    st.markdown("### 📊 目标达成分析")
    _fc_gap = _fc_target_rev - _fc_proj_rev
    _fc_days_left = _fc_month_days - _fc_day
    _fc_needed_daily = _fc_gap / max(_fc_days_left, 1)
    _fc_current_daily = _fc_this_rev / max(_fc_day, 1)

    _fc_track_color = "#10b981" if _fc_gap <= 0 else "#ef4444"
    _fc_track_msg = f"✅ 预计超额完成目标 **元{int(-_fc_gap/10000)}万**" if _fc_gap <= 0 else f"⚠️ 预计缺口 **元{int(_fc_gap/10000)}万**，剩余{_fc_days_left}天需每天新增 元{int(_fc_needed_daily/10000)}万（当前日均 元{int(_fc_current_daily/10000)}万）"
    st.markdown(f"<div style='background:{_fc_track_color}20;border-left:4px solid {_fc_track_color};padding:10px 16px;border-radius:4px'>{_fc_track_msg}</div>", unsafe_allow_html=True)

    st.progress(min(_fc_this_rev / _fc_target_rev, 1.0), text=f"月度营收目标完成率：{_fc_this_rev/_fc_target_rev:.0%}")

    # 需要补多少线索/成交
    if _fc_gap > 0:
        _fc_avg_order_val = _fc_avg_monthly_rev / max(_fc_avg_monthly_cnt, 1)
        _fc_needed_orders = int(_fc_gap / max(_fc_avg_order_val, 1))
        _fc_ls30 = get_lead_stats(days=30)
        _fc_cvr = _fc_ls30.get('conversion_rate')

        _fc_gap_c1, _fc_gap_c2, _fc_gap_c3 = st.columns(3)
        _fc_gap_c1.metric("还需成交", f"{_fc_needed_orders}单", delta=f"均价元{int(_fc_avg_order_val):,}")
        if _fc_cvr is not None:
            _fc_needed_leads = int(_fc_needed_orders / max(_fc_cvr, 0.01))
            _fc_gap_c2.metric("还需线索", f"{_fc_needed_leads}条", delta=f"按{_fc_cvr:.0%}转化率")
        else:
            _fc_gap_c2.metric("还需线索", "no_data", delta="缺少真实转化率")
        _fc_gap_c3.metric("剩余天数", f"{_fc_days_left}天", delta=f"日均需{int(_fc_needed_orders/max(_fc_days_left,1))}单")

    st.divider()

    # ── 近12个月趋势 ──────────────────────────────────────────
    st.markdown("### 📈 近12个月历史趋势")
    if _fc_last12:
        _fc_trend_df = _pd_fc.DataFrame([
            {'月份': m, '订单数': _fc_monthly_cnt.get(m,0), '营收(万元)': round(_fc_monthly_rev.get(m,0)/10000, 1),
             '目标线': round(_fc_target_rev/10000, 1)}
            for m in _fc_last12
        ]).set_index('月份')
        _ftc1, _ftc2 = st.columns(2)
        _ftc1.bar_chart(_fc_trend_df[['订单数']], height=220)
        _ftc2.bar_chart(_fc_trend_df[['营收(万元)','目标线']], height=220)

    st.divider()

    # ── 产品爆发/衰退预测 ─────────────────────────────────────
    st.markdown("### 🚀 产品趋势预测（下月）")
    try:
        _fc_s30 = get_order_stats(days=30)
        _fc_s60 = get_order_stats(days=60)
        _fc_s90 = get_order_stats(days=90)
        _fc_prod30 = dict(_fc_s30['by_product'])
        _fc_prod60 = dict(_fc_s60['by_product'])
        _fc_prod_rev = dict(_fc_s30.get('revenue_by_product', []))

        _fc_prod_rows = []
        for _p, _c30 in _fc_prod30.items():
            if not _p or _p == '未知': continue
            _c60_avg = _fc_prod60.get(_p, 0) / 2
            _growth = (_c30 - _c60_avg) / max(_c60_avg, 1) if _c60_avg > 0 else 0
            _next_pred = int(_c30 * (1 + _growth * 0.5))
            _status = "🚀 爆发" if _growth > 0.2 else ("📈 增长" if _growth > 0 else ("📉 下滑" if _growth < -0.1 else "→ 平稳"))
            _fc_prod_rows.append({
                '产品': PRODUCT_ZH.get(_p, _p),
                '近30天': _c30,
                '预测下月': _next_pred,
                '增长率': f"{_growth:+.0%}",
                '趋势': _status,
                '本月营收': f"元{int(_fc_prod_rev.get(_p,0)):,}",
            })

        _fc_prod_rows.sort(key=lambda x: -_fc_prod30.get(
            next((k for k, v in PRODUCT_ZH.items() if v == x['产品']), x['产品']), 0))

        if _fc_prod_rows:
            st.dataframe(_pd_fc.DataFrame(_fc_prod_rows), width='stretch', hide_index=True)
    except Exception as _e_prod_fc:
        st.caption(f"产品预测：{_e_prod_fc}")

    st.divider()

    # ── 三层数据融合需求预测信号 ─────────────────────────────────
    st.markdown("### 🎯 AI需求预测信号（三层数据融合）")
    st.caption("数据源：学校学术日历 + 课程Assessment + 历史订单画像 + 当前线索热度")
    try:
        from database.crud import list_demand_forecast_signals, clear_expired_forecast_signals
        import datetime as _fc_dt2

        # 筛选器
        _sig_cols = st.columns(5)
        _sig_window = _sig_cols[0].selectbox("时间窗口", [7, 14, 30, 60], index=2, key="sig_window")
        _sig_country = _sig_cols[1].selectbox("国家", ["全部", "AU", "UK", "HK"], key="sig_country")
        _sig_product = _sig_cols[2].selectbox(
            "产品",
            ["全部"] + list(PRODUCT_ZH.keys()),
            format_func=lambda x: "全部" if x == "全部" else PRODUCT_ZH.get(x, x),
            key="sig_product",
        )
        _sig_conf = _sig_cols[3].selectbox("最低可信度", ["全部", "高(≥0.7)", "中(≥0.4)"], key="sig_conf")
        _sig_school = _sig_cols[4].text_input("学校关键词", "", key="sig_school_kw")

        _min_conf = 0.0
        if _sig_conf == "高(≥0.7)": _min_conf = 0.7
        elif _sig_conf == "中(≥0.4)": _min_conf = 0.4

        _all_signals = list_demand_forecast_signals(
            time_window=_sig_window,
            min_confidence=_min_conf,
            limit=200,
        )

        # 过滤
        if _sig_country != "全部":
            _all_signals = [s for s in _all_signals if s.get("country") == _sig_country]
        if _sig_product != "全部":
            _all_signals = [s for s in _all_signals if s.get("product") == _sig_product]
        if _sig_school:
            _all_signals = [s for s in _all_signals if _sig_school in (s.get("school") or "")]

        if _all_signals:
            # 汇总指标
            _sc1, _sc2, _sc3, _sc4 = st.columns(4)
            _high_conf = [s for s in _all_signals if s.get("confidence_score", 0) >= 0.7]
            _schools_covered = len(set(s.get("school") for s in _all_signals))
            _products_covered = len(set(s.get("product") for s in _all_signals))
            _sc1.metric("预测信号数", len(_all_signals))
            _sc2.metric("高置信度信号", len(_high_conf), delta=f"{len(_high_conf)/max(len(_all_signals),1):.0%}")
            _sc3.metric("覆盖学校", _schools_covered)
            _sc4.metric("涉及产品", _products_covered)

            # 信号强度最高的Top10展示
            _top_signals = sorted(_all_signals, key=lambda x: -x.get("signal_strength", 0))[:50]

            import pandas as _pd_sig
            _sig_rows = []
            for _s in _top_signals:
                _conf_label = _s.get("confidence_label") or ("高" if _s.get("confidence_score",0)>=0.7 else "中" if _s.get("confidence_score",0)>=0.4 else "低")
                _conf_icon = {"高": "🟢", "中": "🟡", "低": "🔴"}.get(_conf_label, "⚪")
                _sig_rows.append({
                    "可信度": f"{_conf_icon}{_conf_label}",
                    "预测产品": PRODUCT_ZH.get(_s.get("product",""), _s.get("product","")),
                    "学校": (_s.get("school") or "")[:10],
                    "专业": _s.get("major_category",""),
                    "时间窗口": f"{_s.get('window_start','')}~{_s.get('window_end','')}",
                    "信号强度": f"{_s.get('signal_strength',0):.0%}",
                    "预测依据": (_s.get("forecast_reason") or "")[:60],
                    "推广动作": (_s.get("promo_action") or "")[:50],
                    "销售动作": (_s.get("sales_action") or "")[:50],
                    "触发来源": _s.get("triggered_by",""),
                })
            st.dataframe(_pd_sig.DataFrame(_sig_rows), width='stretch', hide_index=True)

            # 展开查看完整预测详情
            with st.expander("📋 查看完整预测详情（Top10）", expanded=False):
                for i, _s in enumerate(_top_signals[:10], 1):
                    _conf = _s.get("confidence_score", 0)
                    _conf_label = "高" if _conf >= 0.7 else "中" if _conf >= 0.4 else "低"
                    st.markdown(f"""
**{i}. {PRODUCT_ZH.get(_s.get('product',''), _s.get('product',''))} — {_s.get('school','')} {_s.get('major_category','')}**
- 时间窗口：{_s.get('window_start','')} ~ {_s.get('window_end','')}（{_sig_window}天）
- 信号强度：{_s.get('signal_strength',0):.0%} | 可信度：{_conf_label}（{_conf:.2f}）
- 预测依据：{_s.get('forecast_reason','') or '—'}
- 推广动作：{_s.get('promo_action','') or '—'}
- 销售动作：{_s.get('sales_action','') or '—'}
- 数据来源：{', '.join(_s.get('data_sources') or [])}
---""")

            # 高优先级信号一键生成推广任务
            _top3_high = [s for s in _top_signals if s.get("confidence_score",0) >= 0.6][:3]
            if _top3_high and st.button("📋 生成Top推广任务", key="fc_signal_task"):
                for _ts in _top3_high:
                    _create_task_from_suggestion(
                        title=f"需求预测推广：{PRODUCT_ZH.get(_ts.get('product',''), _ts.get('product',''))}@{_ts.get('school','')}",
                        desc=f"预测依据：{_ts.get('forecast_reason','')}\n推广动作：{_ts.get('promo_action','')}\n时间窗口：{_ts.get('window_start','')}~{_ts.get('window_end','')}",
                        dept="市场部", deadline_days=3,
                        source_agent="需求预测引擎", priority="高",
                        product=PRODUCT_ZH.get(_ts.get("product",""), _ts.get("product","")),
                        channel="小红书",
                        success_criteria=f"该校该产品线索增加",
                        review_metric="线索量/成交量对比",
                    )
                st.success(f"✅ 已生成 {len(_top3_high)} 个推广任务")
        else:
            st.info("暂无预测信号。运行 `python agents/demand_forecast_engine.py --all` 生成。")

        # 数据源健康度
        with st.expander("📊 三层数据源健康度", expanded=False):
            from database.crud import list_school_academic_calendars, list_course_assessments_v2, list_major_demand_profiles
            _t1_cnt = len(list_school_academic_calendars(limit=200))
            _t2_cnt = len(list_course_assessments_v2(limit=1000))
            _t3_cnt = len(list_major_demand_profiles(limit=1000))
            st.markdown(f"""
| 层级 | 描述 | 记录数 | 状态 |
|---|---|---|---|
| 第一层 | 学校学术日历（school_academic_calendars） | **{_t1_cnt}** 条 | {"✅" if _t1_cnt > 10 else "⚠️ 需填充"} |
| 第二层 | 课程考核数据（course_assessments_v2） | **{_t2_cnt}** 条 | {"✅" if _t2_cnt > 50 else "⚠️ 需填充"} |
| 第三层 | 专业需求画像（major_demand_profiles） | **{_t3_cnt}** 条（来自CRM历史） | {"✅" if _t3_cnt > 5 else "⚠️ 历史数据不足"} |
| 预测层 | 需求预测信号（demand_forecast_signals） | **{len(_all_signals)}** 条当前有效 | {"✅" if _all_signals else "需运行预测引擎"} |

⚡ 刷新预测：服务器运行 `python agents/demand_forecast_engine.py --forecast`
            """)
    except Exception as _e_sig:
        st.caption(f"需求预测信号加载中：{_e_sig}")

    st.divider()

    # ── 学校需求期预测（双数据源融合）────────────────────────
    st.markdown("### 🏫 学校需求期预测")
    st.caption("数据源 1：内部真实订单历史趋势　|　数据源 2：学校官方/推断学术日历（school_calendar 表）")
    try:
        import datetime as _sch_dt

        # ── 数据源1：内部订单历史趋势 ──
        _fc_sch30 = dict(get_order_stats(days=30)['by_school'])
        _fc_sch90 = dict(get_order_stats(days=90)['by_school'])

        # ── 数据源2：未来60天的学校日历事件 ──
        _today_sch = _sch_dt.date.today()
        _future60   = _today_sch + _sch_dt.timedelta(days=60)
        _all_cal = list_school_calendar(limit=500)
        # 过滤出未来60天内的事件
        _upcoming_events = {}   # school -> list of events
        for _ev in _all_cal:
            _ev_start = _ev.get('start_date')
            if not _ev_start: continue
            try:
                _ev_date = _sch_dt.date.fromisoformat(str(_ev_start)[:10])
            except:
                continue
            if _today_sch <= _ev_date <= _future60:
                _sch_name = _ev.get('school', '')
                if _sch_name:
                    _upcoming_events.setdefault(_sch_name, []).append({
                        'date': _ev_date,
                        'type': _ev.get('event_type', ''),
                        'name': _ev.get('event_name', ''),
                        'source': _ev.get('source', ''),
                    })

        # ── 融合两个数据源 ──
        _fc_sch_rows = []
        _all_schools = set(
            [s for s in _fc_sch30 if _is_valid_school(s)] +
            list(_upcoming_events.keys())
        )
        for _s in _all_schools:
            _c30 = _fc_sch30.get(_s, 0)
            _c90_avg = _fc_sch90.get(_s, 0) / 3
            _sch_growth = (_c30 - _c90_avg) / max(_c90_avg, 1) if _c90_avg > 0 else 0
            _events = _upcoming_events.get(_s, [])

            # 事件驱动需求：考试期/提交期 → 强需求信号
            _event_signal = ""
            _demand_boost = 0
            _event_types = [e['type'] for e in _events]
            if 'exam_period' in _event_types:
                _event_signal = f"⚠️ 考试期({min(e['date'] for e in _events if e['type']=='exam_period')})"
                _demand_boost = 30
            elif 'submission' in _event_types:
                _event_signal = f"📝 论文/作业提交({min(e['date'] for e in _events if e['type']=='submission')})"
                _demand_boost = 20
            elif 'teaching_start' in _event_types:
                _event_signal = f"🏫 开学({min(e['date'] for e in _events if e['type']=='teaching_start')})"
                _demand_boost = 10

            # 综合需求评分（历史趋势 + 事件信号）
            _demand_score = int(min(_c30, 100) * 0.6 + _demand_boost * 0.4)
            if _sch_growth > 0.2: _demand_score = int(_demand_score * 1.2)

            # 只显示有实际订单或有未来事件的学校
            if _c30 < 3 and not _events: continue

            _status = (
                "🔥 强需求" if _demand_boost >= 20 and _sch_growth >= 0 else
                "📈 上升+事件" if _events and _sch_growth > 0 else
                "🔥 需求旺" if _sch_growth > 0.2 else
                "📈 上升" if _sch_growth > 0 else
                "📅 有节点" if _events else "→ 平稳"
            )

            _ev_source = ("官方" if any("官方" in e.get('source','') for e in _events) else
                          "推断" if _events else "—")

            _fc_sch_rows.append({
                '学校': _s,
                '近30天订单': _c30,
                '历史月均': int(_c90_avg),
                '订单趋势': f"{_sch_growth:+.0%}" if _c90_avg > 0 else "新",
                '未来60天节点': _event_signal or "—",
                '节点来源': _ev_source,
                '综合状态': _status,
                '建议': '🎯立即跟进' if '强需求' in _status or '上升+事件' in _status else
                        ('加大投入' if '上升' in _status or '需求旺' in _status else '维持关注'),
            })

        _fc_sch_rows.sort(key=lambda x: (
            0 if '强需求' in x['综合状态'] else
            1 if '上升+事件' in x['综合状态'] else
            2 if '需求旺' in x['综合状态'] else 3,
            -x['近30天订单']
        ))

        if _fc_sch_rows:
            st.dataframe(_pd_fc.DataFrame(_fc_sch_rows[:20]), width='stretch', hide_index=True)

            # 高优先级学校一键生成任务
            _hot_schools = [r for r in _fc_sch_rows if '立即跟进' in r['建议']]
            if _hot_schools:
                st.warning(f"**⚠️ 以下 {len(_hot_schools)} 所学校有考试/提交节点即将到来，建议立即启动定向推广：**")
                st.markdown("、".join([r['学校'] for r in _hot_schools[:5]]))
                if st.button("📋 生成学校定向推广任务", key="fc_sch_task"):
                    _create_task_from_suggestion(
                        title=f"学校节点定向推广：{'、'.join([r['学校'] for r in _hot_schools[:3]])}等",
                        desc=f"以下学校未来60天有考试/提交节点，需要立即启动定向推广：\n" +
                             "\n".join([f"- {r['学校']}：{r['未来60天节点']}（{r['节点来源']}）" for r in _hot_schools[:5]]),
                        dept="市场部", deadline_days=3,
                        source_agent="增长预测台-学校节点", priority="高",
                        success_criteria="完成定向内容投放",
                        review_metric="各学校线索数变化"
                    )
                    st.success("✅ 已创建任务")
        else:
            st.info("暂无足够数据生成学校需求预测")

        # 数据源说明
        with st.expander("📊 数据源说明", expanded=False):
            _cal_total = len(_all_cal)
            _upcoming_total = sum(len(v) for v in _upcoming_events.values())
            st.markdown(f"""
**数据源 1 — 内部订单历史**
- 来源：`orders` 表，近30天 vs 近90天真实成交数据
- 用途：判断各学校当前订单趋势

**数据源 2 — 学校学术日历**
- 来源：`school_calendar` 表，共 **{_cal_total}** 条记录
- 未来60天内有事件的学校：**{len(_upcoming_events)}** 所，共 **{_upcoming_total}** 个节点
- 事件来源：{", ".join(set(e.get('source','') for ev in _all_cal[:20] for e in [ev] if ev.get('source')))}
- ⚠️ 当前数据主要为"国家通用推断"，如需更准确的预测，请接入各学校官方学术日历
            """)

    except Exception as _e_sch_fc:
        st.caption(f"学校预测：{_e_sch_fc}")

    st.divider()

    # ── 未来30/60天线索预测 ───────────────────────────────────
    st.markdown("### 📞 线索预测（未来30/60天）")
    try:
        _fc_ls30 = get_lead_stats(days=30)
        _fc_ls60 = get_lead_stats(days=60)
        _fc_lead_30 = _fc_ls30.get('total', 0)
        _fc_lead_60 = _fc_ls60.get('total', 0)
        if _fc_lead_30 <= 0 and _fc_lead_60 <= 0:
            st.info("no_data：leads 表暂无真实线索，线索预测不生成结论。")
            raise RuntimeError("leads no_data")
        _fc_cvr = _fc_ls30.get('conversion_rate')
        if _fc_cvr is None:
            st.info("no_data：leads.deal_status 不足以计算真实转化率，线索预测不生成成交/营收结论。")
            raise RuntimeError("lead conversion no_data")
        _fc_avg_order_val = _fc_avg_monthly_rev / max(_fc_avg_monthly_cnt, 1)

        # 线索趋势
        _fc_lead_trend = (_fc_lead_30 - _fc_lead_60 / 2) / max(_fc_lead_60 / 2, 1)
        _fc_lead_next30 = int(_fc_lead_30 * (1 + _fc_lead_trend * 0.5))
        _fc_lead_next60 = int(_fc_lead_next30 * 2 * (1 + _fc_lead_trend * 0.3))
        _fc_deal_next30 = int(_fc_lead_next30 * _fc_cvr)
        _fc_rev_next30 = int(_fc_deal_next30 * _fc_avg_order_val)

        _fl_c1, _fl_c2, _fl_c3, _fl_c4 = st.columns(4)
        _fl_c1.metric("近30天实际线索", f"{_fc_lead_30}条", delta=f"转化率{_fc_cvr:.0%}")
        _fl_c2.metric("预测下30天线索", f"{_fc_lead_next30}条", delta=f"趋势{_fc_lead_trend:+.0%}")
        _fl_c3.metric("预测下30天成交", f"{_fc_deal_next30}单", delta=f"预计营收元{int(_fc_rev_next30/10000)}万")
        _fl_c4.metric("预测下60天线索", f"{_fc_lead_next60}条", delta="含季节因子")

        # 结构化预测结论
        _fc_lead_risk = "🔴 高" if _fc_lead_trend < -0.1 else ("🟡 中" if _fc_lead_trend < 0 else "🟢 低")
        st.info(f"""
**预测结论：** 未来30天预计获得 {_fc_lead_next30} 条线索，按当前 {_fc_cvr:.0%} 转化率，预计成交 {_fc_deal_next30} 单，营收 元{int(_fc_rev_next30/10000)}万。

**预测依据：** 近30天线索量 vs 近60天日均趋势，增长率 {_fc_lead_trend:+.0%}

**风险等级：** {_fc_lead_risk} — {'线索量在下降，需要加大推广力度' if _fc_lead_trend < 0 else '线索量稳定增长'}

**建议动作：** {'立即启动线索补充计划，目标7天内新增' + str(int((_fc_avg_monthly_cnt * _fc_cvr - _fc_deal_next30))) + '条高意向线索' if _fc_lead_trend < 0 else '保持当前推广节奏，优化转化率'}

**责任部门：** 市场部（获客）+ 销售部（转化）
        """)
    except Exception as _e_lead_fc:
        st.caption(f"线索预测：{_e_lead_fc}")

    st.divider()

    # ── 渠道增长趋势（来自CRM线索 source_channel 字段）────────
    st.markdown("### 📡 渠道线索来源分析（CRM真实数据）")
    try:
        import pandas as _pd_ch_fc
        _ch_ls30 = get_lead_stats(days=30)
        _ch_ls60 = get_lead_stats(days=60)
        _ch_by30 = dict(_ch_ls30.get("by_channel", []))
        _ch_by60 = dict(_ch_ls60.get("by_channel", []))

        # 过滤掉空值和未知
        _ch_by30 = {k: v for k, v in _ch_by30.items() if k and k not in ("未知", "None", "")}
        _ch_by60 = {k: v for k, v in _ch_by60.items() if k and k not in ("未知", "None", "")}

        if _ch_by30:
            _total_ch = sum(_ch_by30.values())
            _ch_rows = []
            for _chn, _cnt30 in sorted(_ch_by30.items(), key=lambda x: -x[1]):
                _cnt60_prior = max(_ch_by60.get(_chn, 0) - _cnt30, 0)  # 前30天 = 60天总 - 近30天
                _trend = (_cnt30 - _cnt60_prior) / max(_cnt60_prior, 1) if _cnt60_prior > 0 else 0
                _trend_label = "🚀 快速增长" if _trend > 0.2 else ("📈 增长" if _trend > 0 else ("📉 下滑" if _trend < -0.1 else "→ 平稳"))
                _share = _cnt30 / _total_ch if _total_ch > 0 else 0
                _ch_rows.append({
                    "渠道": _chn,
                    "近30天线索": _cnt30,
                    "前30天线索": _cnt60_prior,
                    "环比趋势": f"{_trend:+.0%}" if _cnt60_prior > 0 else "新渠道",
                    "趋势": _trend_label,
                    "线索占比": f"{_share:.0%}",
                })
            st.dataframe(_pd_ch_fc.DataFrame(_ch_rows), width='stretch', hide_index=True)

            # 结论
            _best_ch = max(_ch_by30, key=_ch_by30.get)
            _growing = [r["渠道"] for r in _ch_rows if "增长" in r["趋势"] or "快速" in r["趋势"]]
            _declining = [r["渠道"] for r in _ch_rows if "下滑" in r["趋势"]]
            st.success(f"**主力渠道：{_best_ch}**，近30天 {_ch_by30[_best_ch]} 条线索（占比 {_ch_by30[_best_ch]/_total_ch:.0%}）")
            if _growing:
                st.info(f"📈 增长中的渠道：{'、'.join(_growing)} — 建议加大投入")
            if _declining:
                st.warning(f"📉 下滑渠道：{'、'.join(_declining)} — 建议排查原因或调整策略")
        else:
            st.warning("CRM线索数据中暂无渠道来源记录（source_channel 字段为空）。请在录入线索时填写来源渠道。")
    except Exception as _e_ch_fc:
        st.error(f"渠道数据加载失败：{_e_ch_fc}")

    if st.button("→ 查看渠道作战台", key="fc_to_channel"):
        st.session_state["page_jump"] = "📡 渠道作战台"

    st.divider()

    # ── 五部门行动分解 ────────────────────────────────────────
    st.markdown("### 📋 目标达成行动分解（五部门）")

    # 计算共用变量
    try:
        _fc_avg_order_val
    except NameError:
        _fc_avg_order_val = _fc_avg_monthly_rev / max(_fc_avg_monthly_cnt, 1)
    try:
        _fc_cvr
    except NameError:
        _fc_cvr = None
    try:
        _fc_gap
    except NameError:
        _fc_gap = _fc_target_rev - _fc_proj_rev

    _fc_tab_mkt, _fc_tab_sales, _fc_tab_prod, _fc_tab_delivery, _fc_tab_mgmt = st.tabs(
        ["📢 推广/市场", "💼 销售/顾问/学管", "📦 产品/后台", "👩‍🏫 交付/老师", "🎯 管理层"]
    )

    with _fc_tab_mkt:
        _mkt_actions = []
        if _fc_gap > 0 and _fc_cvr:
            _needed_leads = int(_fc_gap / max(_fc_avg_order_val, 1) / max(_fc_cvr, 0.01))
            _mkt_actions.append(f"本月还需新增线索约 **{_needed_leads}条**（按客单价元{int(_fc_avg_order_val):,}、转化率{_fc_cvr:.0%}计）")
        elif _fc_gap > 0:
            _mkt_actions.append("no_data：缺少真实线索转化率，暂不计算需要补充的线索数")
        if _fc_prod_rows:
            _hot_prods = [r['产品'] for r in _fc_prod_rows if '爆发' in r['趋势'] or '增长' in r['趋势']][:2]
            if _hot_prods: _mkt_actions.append(f"重点推广增长产品：{'、'.join(_hot_prods)}")
        _mkt_actions.extend(["加强旺季学校定向投放", "提升小红书和社群内容发布频次", "启动老客户转介绍激励活动"])
        for _a in _mkt_actions: st.markdown(f"• {_a}")
        st.markdown(f"**关联渠道：** 小红书、社群、垂直号")
        if _fc_prod_rows: st.markdown(f"**关联产品：** {', '.join([r['产品'] for r in _fc_prod_rows[:3]])}")
        st.markdown("**完成标准：** 线索量达成目标 · 成本/线索 < 200元")
        st.markdown("**复盘指标：** 线索数、转化率、获客成本")
        if st.button("📋 生成推广任务", key="fc_mkt_task"):
            _create_task_from_suggestion(
                title="本月推广行动计划", desc="\n".join(_mkt_actions),
                dept="市场部", deadline_days=3, source_agent="增长预测台",
                priority="高", channel="小红书、社群",
                success_criteria="线索量达标", review_metric="线索数、获客成本"
            )
            st.success("✅ 已创建任务")

    with _fc_tab_sales:
        _sales_actions = []
        if _fc_gap > 0:
            _needed_deals = int(_fc_gap / max(_fc_avg_order_val, 1))
            _sales_actions.append(f"还需成交 **{_needed_deals}单**（客单价约元{int(_fc_avg_order_val):,}）")
        _sales_actions.extend(["优先跟进高意向线索（当天回复）", "推进复购：主动联系3个月内老客户", "推动转介绍：每个满意客户争取1个推荐"])
        if _fc_prod_rows:
            _top_prod = _fc_prod_rows[0]['产品'] if _fc_prod_rows else ""
            _sales_actions.append(f"重点推销本周热门产品：{_top_prod}")
        for _a in _sales_actions: st.markdown(f"• {_a}")
        st.markdown("**完成标准：** 成交数达标 · 客单价维持均值")
        st.markdown("**复盘指标：** 成交数、成交额、客单价、转化率")
        if st.button("📋 生成销售任务", key="fc_sales_task"):
            _create_task_from_suggestion(
                title="本月销售冲刺计划", desc="\n".join(_sales_actions),
                dept="销售部", deadline_days=3, source_agent="增长预测台",
                priority="高", success_criteria="成交数达标",
                review_metric="成交数、成交额、转化率"
            )
            st.success("✅ 已创建任务")

    with _fc_tab_prod:
        _prod_fc_actions = ["更新产品目录，确保话术和价格与市场一致"]
        if _fc_prod_rows:
            _decline_prods = [r['产品'] for r in _fc_prod_rows if '下滑' in r['趋势']]
            if _decline_prods: _prod_fc_actions.append(f"排查下滑产品原因：{', '.join(_decline_prods[:2])}")
        _prod_fc_actions.extend(["准备下季度新产品，评估市场需求", "完善产品说明文档，支持销售话术"])
        for _a in _prod_fc_actions: st.markdown(f"• {_a}")
        if st.button("📋 生成产品任务", key="fc_prod_task"):
            _create_task_from_suggestion(
                title="本月产品优化计划", desc="\n".join(_prod_fc_actions),
                dept="产品部", deadline_days=7, source_agent="增长预测台",
                priority="中", success_criteria="产品目录更新完毕",
                review_metric="产品满意度、退款率"
            )
            st.success("✅ 已创建任务")

    with _fc_tab_delivery:
        _delivery_actions = []
        if _fc_proj_cnt > _fc_avg_monthly_cnt * 1.15:
            _delivery_actions.append(f"⚠️ 预计单量比历史均值高 {int((_fc_proj_cnt/_fc_avg_monthly_cnt-1)*100)}%，需提前储备师资")
        _delivery_actions.extend(["确认现有老师产能是否有缺口", "建立备用老师资源库", "监控交付质量（好评率/返修率）", "提前识别高风险客户，主动干预"])
        for _a in _delivery_actions: st.markdown(f"• {_a}")
        st.markdown("**完成标准：** 无交付超时 · 好评率 > 90%")
        st.markdown("**复盘指标：** 交付及时率、好评率、返修率")
        if st.button("📋 生成交付任务", key="fc_delivery_task"):
            _create_task_from_suggestion(
                title="本月交付产能保障计划", desc="\n".join(_delivery_actions),
                dept="交付部", deadline_days=5, source_agent="增长预测台",
                priority="高" if _fc_proj_cnt > _fc_avg_monthly_cnt * 1.15 else "中",
                success_criteria="无交付超时", review_metric="交付及时率、好评率"
            )
            st.success("✅ 已创建任务")

    with _fc_tab_mgmt:
        _mgmt_actions = []
        if _fc_gap > 0:
            _mgmt_actions.append(f"拍板：是否追加推广预算（缺口元{int(_fc_gap/10000)}万）")
        if _fc_proj_cnt > _fc_avg_monthly_cnt * 1.2:
            _mgmt_actions.append("拍板：师资储备预算，应对产能扩张")
        _mgmt_actions.extend(["审批本月AI建议生成的任务清单", "跟进上周复盘结论落实情况", "确认下月主推产品和渠道方向"])
        for _a in _mgmt_actions: st.markdown(f"• {_a}")
        if st.button("📋 生成管理层待办", key="fc_mgmt_task"):
            _create_task_from_suggestion(
                title="本月管理层决策清单", desc="\n".join(_mgmt_actions),
                dept="管理层", deadline_days=2, source_agent="增长预测台",
                priority="紧急" if _fc_gap > 0 else "高",
                success_criteria="所有拍板事项确认完毕",
                review_metric="目标完成率"
            )
            st.success("✅ 已创建任务")


elif page == "🔧 系统诊断台":
    st.title("🔧 系统诊断台")
    st.info("🚧 该模块建设中，敬请期待。")

    # ── Tab1：收入预测 ────────────────────────────────────────────────────────
    with _ft1:
        st.markdown("#### 本月 / 下月收入预测")
        # 按天分组统计近30天收入
        _daily_rev = collections.defaultdict(float)
        _daily_count = collections.defaultdict(int)
        for _o in _f_orders_d:
            _ca = _o.get("created_at")
            if not _ca: continue
            _day = str(_ca)[:10]
            _daily_rev[_day] += float(_o.get("amount") or 0)
            _daily_count[_day] += 1

        _days_elapsed = _fn.day
        _month_orders = [o for o in _f_orders_d if str(o.get("created_at",""))[:7] == _fn.strftime("%Y-%m")]
        _month_revenue = sum(float(o.get("amount") or 0) for o in _month_orders)
        _month_count   = len(_month_orders)
        _daily_avg = _month_revenue / max(_days_elapsed, 1)
        _days_left = 30 - _days_elapsed
        _predicted_this_month = _month_revenue + _daily_avg * _days_left
        _predicted_next_month = _daily_avg * 30  # 基于当月日均

        _pa, _pb, _pc, _pd = st.columns(4)
        _pa.metric("本月已成交", f"元{int(_month_revenue):,}", f"{_month_count}单")
        _pb.metric("本月预测完成", f"元{int(_predicted_this_month):,}", f"日均元{int(_daily_avg):,}")
        _pc.metric("下月预测", f"元{int(_predicted_next_month):,}", "基于当月日均")
        _pd.metric("月度目标达成预测", f"{min(100,int(_predicted_this_month/300000*100))}%",
                   "目标¥300,000" if _predicted_this_month < 300000 else "预计达标")

        # 近30天收入趋势图
        if _daily_rev:
            import pandas as _fpd
            _rev_df = _fpd.DataFrame([
                {"日期": k, "收入": v}
                for k, v in sorted(_daily_rev.items())[-30:]
            ]).set_index("日期")
            st.markdown("**近30天日收入趋势**")
            st.bar_chart(_rev_df, height=200)

        # 产品收入占比
        _prod_rev = collections.defaultdict(float)
        for _o in _f_orders_d:
            _prod_rev[_o.get("product") or "未分类"] += float(_o.get("amount") or 0)
        if _prod_rev:
            st.markdown("**产品收入占比（近90天）**")
            _pr_cols = st.columns(min(4, len(_prod_rev)))
            _total_rev = sum(_prod_rev.values())
            for _pri, (_pname, _prev) in enumerate(sorted(_prod_rev.items(), key=lambda x:-x[1])[:4]):
                _pr_cols[_pri].metric(_pname[:12], f"元{int(_prev):,}", f"{int(_prev/_total_rev*100)}%")

        # 渠道收入
        _ch_rev = collections.defaultdict(float)
        for _o in _f_orders_d:
            _ch = _o.get("source_channel") or "未知"
            _ch_rev[_ch] += float(_o.get("amount") or 0)
        if _ch_rev:
            st.markdown("**渠道收入分布**")
            _ch_df_data = {k: v for k,v in sorted(_ch_rev.items(), key=lambda x:-x[1])[:6]}
            st.bar_chart(_ch_df_data, height=150)

        # ── 全年进度 ──────────────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📅 全年进度与预测")
        try:
            import datetime as _fdt2
            _fy_now = _fdt2.datetime.now()
            _fy_this_year = _fy_now.year
            _fy_start_this = f"{_fy_this_year}-01-01"
            _fy_start_last = f"{_fy_this_year - 1}-01-01"
            _fy_today_str  = _fy_now.strftime('%Y-%m-%d')
            _fy_today_last = f"{_fy_this_year - 1}-{_fy_now.strftime('%m-%d')}"

            _fy_orders_all = list_orders(days=730, limit=10000)
            _fy_rev_this = sum(
                o.get('amount') or 0 for o in _fy_orders_all
                if _fy_start_this <= (o.get('order_date') or '') <= _fy_today_str
            )
            _fy_rev_last = sum(
                o.get('amount') or 0 for o in _fy_orders_all
                if _fy_start_last <= (o.get('order_date') or '') <= _fy_today_last
            )
            _fy_days_elapsed = _fy_now.timetuple().tm_yday
            _fy_daily_avg = _fy_rev_this / max(_fy_days_elapsed, 1)
            _fy_predicted = _fy_daily_avg * 365

            _fp1, _fp2, _fp3, _fp4 = st.columns(4)
            _fp1.metric("今年截至今日营收", f"元{int(_fy_rev_this):,}")
            _fp2.metric("去年同期营收", f"元{int(_fy_rev_last):,}",
                        delta=f"{(_fy_rev_this / max(_fy_rev_last,1) - 1)*100:.1f}%" if _fy_rev_last else None)
            _fp3.metric("日均营收", f"元{int(_fy_daily_avg):,}", f"已过{_fy_days_elapsed}天")
            _fp4.metric("全年预测营收", f"元{int(_fy_predicted):,}", "按当前日均×365天")

            # 季节性分析（按月统计历史均值）
            st.markdown("**季节性分析 — 各月历史均值**")
            _month_rev_hist: dict = {}
            for _fyo in _fy_orders_all:
                _fym = (_fyo.get('order_date') or '')[:7]
                if not _fym: continue
                _mkey = _fym[5:7]  # 月份 "01"~"12"
                _month_rev_hist.setdefault(_mkey, [])
                _month_rev_hist[_mkey].append(_fyo.get('amount') or 0)
            if _month_rev_hist:
                import pandas as _fpd4
                _season_rows = []
                for _mnum in sorted(_month_rev_hist.keys()):
                    _m_vals = _month_rev_hist[_mnum]
                    _m_avg  = sum(_m_vals) / max(len(_m_vals), 1)
                    _season_rows.append({'月份': f"{int(_mnum)}月", '历史月均营收': f"元{int(_m_avg):,}", '数据量': len(_m_vals)})
                _season_df = _fpd4.DataFrame(_season_rows).set_index('月份')
                st.dataframe(_season_df, width='stretch')
        except Exception as _e_fy:
            st.info(f"全年进度计算中：{_e_fy}")

    # ── Tab2：线索预测 ────────────────────────────────────────────────────────
    with _ft2:
        st.markdown("#### 未来30天 / 60天线索预测")

        # 按周统计线索
        _weekly_leads = collections.defaultdict(int)
        _weekly_won   = collections.defaultdict(int)
        for _l in _f_leads_d:
            _ca = _l.get("created_at")
            if not _ca: continue
            try:
                _ld = _ca if isinstance(_ca, _fdt) else _fdt.fromisoformat(str(_ca)[:19])
                _wk = _ld.strftime("%Y-W%U")
                _weekly_leads[_wk] += 1
                if _l.get("deal_status") in ("won", "completed"):
                    _weekly_won[_wk] += 1
            except: pass

        _sorted_weeks = sorted(_weekly_leads.keys())[-12:]
        if _sorted_weeks:
            _avg_weekly_leads = sum(_weekly_leads[w] for w in _sorted_weeks) / len(_sorted_weeks)
            _avg_weekly_won   = sum(_weekly_won.get(w,0) for w in _sorted_weeks) / len(_sorted_weeks)
            _cvr = _avg_weekly_won / max(_avg_weekly_leads, 1)

            _la, _lb, _lc2, _ld2 = st.columns(4)
            _la.metric("周均咨询", f"{_avg_weekly_leads:.1f}条")
            _lb.metric("周均成交", f"{_avg_weekly_won:.1f}单")
            _lc2.metric("平均转化率", f"{_cvr*100:.1f}%")
            _ld2.metric("30天预测线索", f"{int(_avg_weekly_leads*4.3)}条")

            st.markdown("**近12周线索与成交趋势**")
            import pandas as _fpd2
            _lead_df = _fpd2.DataFrame([
                {"周": w, "咨询": _weekly_leads[w], "成交": _weekly_won.get(w,0)}
                for w in _sorted_weeks
            ]).set_index("周")
            st.line_chart(_lead_df, height=220)

        # 渠道线索分布
        _ch_leads = collections.defaultdict(int)
        _ch_won   = collections.defaultdict(int)
        for _l in _f_leads_d:
            _ch = _l.get("source_channel") or "未知"
            _ch_leads[_ch] += 1
            if _l.get("deal_status") in ("won", "completed"):
                _ch_won[_ch] += 1

        if _ch_leads:
            st.markdown("**渠道线索质量对比**")
            _ch_rows = []
            for _ch_n, _ch_tot in sorted(_ch_leads.items(), key=lambda x:-x[1]):
                _ch_cvr = _ch_won.get(_ch_n,0) / max(_ch_tot, 1)
                _ch_rows.append({"渠道": _ch_n, "线索数": _ch_tot, "成交数": _ch_won.get(_ch_n,0), "转化率": f"{_ch_cvr*100:.1f}%"})
            import pandas as _fpd3
            st.dataframe(_fpd3.DataFrame(_ch_rows), hide_index=True, width='stretch')

        # 缺口分析
        st.markdown("#### 🔍 缺口分析")
        _target_monthly_orders = 50
        _current_monthly = len([o for o in _f_orders_d if str(o.get("created_at",""))[:7]==_fn.strftime("%Y-%m")])
        _predicted_monthly_orders = int(_avg_weekly_leads * 4.3 * _cvr) if _f_has_leads else 0
        _gap = _target_monthly_orders - _predicted_monthly_orders

        if _gap > 0:
            st.warning(f"⚠️ 预计月成交 **{_predicted_monthly_orders}单**，目标 **{_target_monthly_orders}单**，缺口 **{_gap}单**")
            # 找缺口最大渠道
            _weakest = min(_ch_leads.items(), key=lambda x: _ch_won.get(x[0],0)/max(x[1],1)) if _ch_leads else None
            if _weakest:
                _wn = _weakest[0]
                _wc = _ch_won.get(_wn,0)/max(_ch_leads[_wn],1)
                st.markdown(f"- **转化率最低渠道：{_wn}**（转化率{_wc*100:.1f}%），是主要缺口来源")
        else:
            st.success(f"✅ 预计月成交 **{_predicted_monthly_orders}单**，超出目标 **{_target_monthly_orders}单**")

    # ── Tab3：产品爆发指数 ────────────────────────────────────────────────────
    with _ft3:
        st.markdown("#### 产品爆发指数（基于线索成交数据）")
        st.caption("爆发指数 = 近30天成交量 / 近60天均量 × 100，>120为爆发，<80为衰退")

        _prod_30 = collections.defaultdict(lambda: {"leads":0,"won":0,"revenue":0})
        _prod_60 = collections.defaultdict(lambda: {"leads":0,"won":0,"revenue":0})
        _now_30 = _fn - _ftd(days=30)
        _now_60 = _fn - _ftd(days=60)

        for _l in _f_leads_d:
            _pn = _l.get("product_interest") or "未分类"
            try:
                _ld = _l.get("created_at")
                _ld = _ld if isinstance(_ld,_fdt) else _fdt.fromisoformat(str(_ld)[:19])
                if _ld >= _now_30: _prod_30[_pn]["leads"] += 1
                if _ld >= _now_60: _prod_60[_pn]["leads"] += 1
                if _l.get("deal_status") in ("won", "completed"):
                    if _ld >= _now_30: _prod_30[_pn]["won"] += 1
                    if _ld >= _now_60: _prod_60[_pn]["won"] += 1
            except: pass

        for _o in _f_orders_d:
            _pn = _o.get("product") or "未分类"
            try:
                _od = _o.get("created_at")
                _od = _od if isinstance(_od,_fdt) else _fdt.fromisoformat(str(_od)[:19])
                _amt = float(_o.get("amount") or 0)
                if _od >= _now_30: _prod_30[_pn]["revenue"] += _amt
                if _od >= _now_60: _prod_60[_pn]["revenue"] += _amt
            except: pass

        _all_prods = set(list(_prod_30.keys()) + list(_prod_60.keys()))
        _prod_explosion = []
        for _pn in _all_prods:
            _won30 = _prod_30[_pn]["won"]
            _won60_avg = _prod_60[_pn]["won"] / 2  # 60天的半均 = 30天等价
            _idx = int(_won30 / max(_won60_avg, 0.5) * 100)
            _rev = _prod_30[_pn]["revenue"]
            _prod_explosion.append({"产品": _pn, "近30天成交": _won30, "爆发指数": _idx, "近30天收入": f"元{int(_rev):,}"})

        _prod_explosion.sort(key=lambda x: -x["爆发指数"])

        if _prod_explosion:
            import pandas as _fpd4
            _pe_df = _fpd4.DataFrame(_prod_explosion)
            st.dataframe(_pe_df, hide_index=True, width='stretch')

            st.markdown("**爆发指数可视化**")
            _bar_data = {row["产品"][:15]: row["爆发指数"] for row in _prod_explosion[:8]}
            st.bar_chart(_bar_data, height=200)

            _exploding = [r for r in _prod_explosion if r["爆发指数"] >= 120]
            _declining = [r for r in _prod_explosion if r["爆发指数"] <= 80]
            if _exploding:
                st.success(f"🚀 爆发产品：{', '.join(r['产品'] for r in _exploding[:3])} → 建议加大推广力度")
            if _declining:
                st.warning(f"⚠️ 衰退产品：{', '.join(r['产品'] for r in _declining[:3])} → 建议分析原因，调整策略")
        else:
            st.info("数据不足，建议上传更多线索和订单数据")

    # ── Tab4：学校节点需求 ────────────────────────────────────────────────────
    with _ft4:
        st.markdown("#### 学校时间节点 × 需求预测")
        _cal = list_school_calendar(limit=50)
        if not _cal:
            st.info("暂无学校节点数据，请前往「市场情报台」添加或导入学校节点")
        else:
            from datetime import date as _fdate
            _upcoming = []
            for _c in _cal:
                _start = _c.get("start_date")
                if not _start: continue
                try:
                    _sd = _start if isinstance(_start, _fdate) else _fdate.fromisoformat(str(_start)[:10])
                    _days_to = (_sd - _fn.date()).days
                    if -7 <= _days_to <= 60:
                        _upcoming.append({**_c, "_days_to": _days_to})
                except: pass
            _upcoming.sort(key=lambda x: x["_days_to"])

            if _upcoming:
                st.markdown(f"**未来60天内有 {len(_upcoming)} 个关键节点**")
                for _uc in _upcoming:
                    _dt = _uc.get("_days_to", 0)
                    _urgency = "🔴" if _dt <= 7 else "🟡" if _dt <= 21 else "🟢"
                    _dt_str = f"今天" if _dt == 0 else f"{_dt}天后" if _dt > 0 else f"{abs(_dt)}天前"
                    _school = _uc.get("school_name","—")
                    _stage  = _uc.get("current_stage","—")
                    _prods  = _uc.get("recommended_products","")
                    st.markdown(f"{_urgency} **{_school}** · {_stage} · {_dt_str}")
                    if _prods:
                        st.caption(f"　推荐产品：{_prods}")
                    st.divider()
            else:
                st.info("未来60天内无学校节点记录")

        # 按月需求预测
        st.markdown("#### 按月历史需求分布")
        _monthly_leads = collections.defaultdict(int)
        for _l in _f_leads_d:
            _ca = _l.get("created_at")
            if not _ca: continue
            _m = str(_ca)[:7]
            _monthly_leads[_m] += 1

        if _monthly_leads:
            import pandas as _fpd5
            _ml_df = _fpd5.DataFrame([
                {"月份": k, "线索数": v}
                for k, v in sorted(_monthly_leads.items())
            ]).set_index("月份")
            st.bar_chart(_ml_df, height=180)

    # ── Tab5：7天行动建议 ─────────────────────────────────────────────────────
    with _ft5:
        st.markdown("#### 各部门未来7天行动建议")
        st.caption("基于当前数据状态生成，不依赖LLM，所有建议有数据依据")

        _dept_actions = {
            "市场/推广": [],
            "顾问": [],
            "学管": [],
            "后台/产品": [],
            "管理层": [],
        }

        # 基于数据生成建议
        if _f_has_leads:
            _pending_leads = [l for l in _f_leads_d if l.get("deal_status") not in ("won","lost") and l.get("created_at")]
            _old_leads = []
            for _pl2 in _pending_leads:
                try:
                    _pld = _pl2.get("created_at")
                    _pld = _pld if isinstance(_pld,_fdt) else _fdt.fromisoformat(str(_pld)[:19])
                    if (_fn - _pld).days > 3:
                        _old_leads.append(_pl2)
                except: pass
            if _old_leads:
                _dept_actions["顾问"].append(f"跟进 **{len(_old_leads)}** 条超3天未成交线索，分析卡点原因")
                _dept_actions["学管"].append(f"检查 **{len(_old_leads)}** 条线索中学管渠道来源，确认是否已跟进")

        if _ch_leads and _f_has_leads:
            _best_ch = max(_ch_leads.items(), key=lambda x: _ch_won.get(x[0],0)/max(x[1],1))
            _dept_actions["市场/推广"].append(f"加大 **{_best_ch[0]}** 渠道投放，该渠道转化率最高")

        _exploding_prods = [r["产品"] for r in _prod_explosion if r["爆发指数"] >= 120] if _prod_explosion else []
        if _exploding_prods:
            _dept_actions["市场/推广"].append(f"重点推广 **{', '.join(_exploding_prods[:2])}**，当前爆发趋势明显")
            _dept_actions["顾问"].append(f"优先推荐 **{_exploding_prods[0]}**，近期成交率上升")

        if _upcoming:
            _urgent_nodes = [u for u in _upcoming if u.get("_days_to",99) <= 14]
            if _urgent_nodes:
                _school_names = list({u.get("school_name","") for u in _urgent_nodes[:3]})
                _dept_actions["市场/推广"].append(f"**{', '.join(_school_names)}** 进入考季，立即启动押题产品推广")
                _dept_actions["顾问"].append(f"主动触达 **{', '.join(_school_names)}** 学生，推荐Final精准押题")

        if _stuck_gates:
            _sg_names = [sg.get("product_name","—") for sg in _stuck_gates[:2]]
            _dept_actions["管理层"].append(f"解决 **{', '.join(_sg_names)}** 产品关卡阻断，明确推进方向")
            _dept_actions["后台/产品"].append(f"完成 **{', '.join(_sg_names)}** 被卡关卡的交付物，推动过关")

        if _gap > 0 if '_gap' in dir() else False:
            _dept_actions["管理层"].append(f"当月成交缺口 **{_gap}单**，需调整资源或策略")

        # 渲染
        _dept_icons = {"市场/推广":"📣","顾问":"💼","学管":"📋","后台/产品":"📦","管理层":"🏆"}
        for _dept_name, _actions in _dept_actions.items():
            _icon = _dept_icons.get(_dept_name,"📌")
            with st.expander(f"{_icon} **{_dept_name}**（{len(_actions)}条建议）", expanded=len(_actions)>0):
                if not _actions:
                    st.markdown("*本周暂无特别行动建议，保持常规执行即可*")
                for _ai, _action in enumerate(_actions):
                    st.markdown(f"**{_ai+1}.** {_action}")
                    _ac1, _ac2 = st.columns([1,3])
                    if _ac1.button("📋 转为任务", key=f"pred_task_{_dept_name}_{_ai}"):
                        _tid = _create_task_from_suggestion(
                            title=_action[:50],
                            desc=_action,
                            dept=_dept_name,
                            source_agent="增长预测台",
                            deadline_days=7,
                            priority="高",
                        )
                        if _tid:
                            st.success(f"✅ 已创建任务，前往「部门任务台」查看")

elif page == "🔧 系统诊断台":
    st.title("🔧 系统诊断台")
    st.info("🚧 该模块建设中，敬请期待。")


# ══════════════════════════════════════════════════════════════════════════════
# V11 新产品上线台（修订版 — 按公司真实部门职责与材料清单）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚀 新产品上线台":
    from database import (
        save_product_launch, list_product_launches, get_product_launch,
        update_product_launch, delete_product_launch,
        migrate_product_launch_v2,
        save_gate_review, list_gate_reviews,
        save_dept_feedback, list_dept_feedbacks, update_dept_feedback_status,
        save_uploaded_file, list_uploaded_files, delete_uploaded_file,
        save_internal_message, list_internal_messages, migrate_files_messages,
        save_deliverable, list_deliverables, update_deliverable, delete_deliverable, migrate_deliverables,
    )
    import os, time, requests as _requests
    migrate_product_launch_v2()
    migrate_files_messages()
    migrate_deliverables()
    UPLOAD_DIR = str(ROOT / "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    WECHAT_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=6fb301ee-26ad-4dc7-bcfb-a97274c7d477"

    def _push_wechat(text: str) -> str:
        try:
            r = _requests.post(WECHAT_WEBHOOK, json={"msgtype": "text", "text": {"content": text}}, timeout=5)
            return "推送成功" if r.json().get("errcode") == 0 else f"失败:{r.json().get('errmsg')}"
        except Exception as e:
            return f"推送异常:{e}"

    def _get_product_stats(product_name: str) -> dict:
        """从 leads / orders 表拉该产品的咨询+成交数据"""
        from database import get_session
        from database.models import Lead, Order
        from sqlalchemy import func
        try:
            with get_session() as s:
                leads_total = s.query(func.count(Lead.id)).filter(
                    Lead.product_interest.ilike(f"%{product_name}%")
                ).scalar() or 0
                leads_won = s.query(func.count(Lead.id)).filter(
                    Lead.product_interest.ilike(f"%{product_name}%"),
                    Lead.deal_status.in_(["won", "completed"])
                ).scalar() or 0
                orders_count = s.query(func.count(Order.id)).filter(
                    Order.product.ilike(f"%{product_name}%")
                ).scalar() or 0
                revenue = s.query(func.sum(Order.amount)).filter(
                    Order.product.ilike(f"%{product_name}%")
                ).scalar() or 0
            cvr = round(leads_won / leads_total * 100, 1) if leads_total > 0 else 0
            return {
                "leads_total": leads_total,
                "leads_won": leads_won,
                "orders_count": orders_count,
                "revenue": revenue,
                "cvr": cvr,
            }
        except Exception:
            return {"leads_total": 0, "leads_won": 0, "orders_count": 0, "revenue": 0, "cvr": 0}

    def _auto_alert(launches: list) -> list:
        """检查所有产品，返回需要推送的预警列表"""
        alerts = []
        now = datetime.now()
        for lc in launches:
            ld = lc if isinstance(lc, dict) else lc.__dict__
            pname = ld.get("product_name", "未知产品")
            # 1. 关卡超7天未推进
            for i in range(1, 6):
                gf = f"gate{i}_status"
                if ld.get(gf) == "in_progress":
                    updated = ld.get("updated_at") or ld.get("created_at")
                    if updated:
                        try:
                            if isinstance(updated, str):
                                updated = datetime.fromisoformat(updated)
                            days = (now - updated).days
                            if days >= 7:
                                alerts.append(f"⏰ 【{pname}】关{i}已进行中 {days} 天未推进，请检查")
                        except Exception:
                            pass
            # 2. 有交付物被标记问题
            delivs = list_deliverables(ld.get("id"), None)
            flagged = [d for d in delivs if d.get("sales_flagged")]
            if flagged:
                depts = list({normalize_role(d.get("owner_dept","?")) for d in flagged})
                alerts.append(f"🚩 【{pname}】{len(flagged)} 项交付物被标记有问题，涉及：{'、'.join(depts)}")
            # 3. 管理层叫停但顾问仍承诺
            if ld.get("mgmt_approval") == "stopped" and ld.get("sales_continuing_promises"):
                alerts.append(f"🛑 【{pname}】管理层已叫停但顾问仍在继续承诺，需立即干预")
            # 4. 推广已发但推广关未启动
            if ld.get("has_promo_published") and ld.get("gate3_status") == "not_started":
                alerts.append(f"🔴 【{pname}】推广素材已发出但推广准备关未启动")
        return alerts

    st.title("🚀 新产品上线台")
    st.caption("相互协同 + 相互制约 — 五关把控，部门互评，全程锁态")

    # ── 常量定义（按公司真实文档）────────────────────────────────────────────
    GATE_NAMES = {
        1: "产品定义关",
        2: "交付承接关",
        3: "推广准备关",
        4: "销售转化关",
        5: "复盘优化关",
    }
    GATE_PREREQS = {1: [], 2: [1], 3: [2], 4: [3], 5: [4]}

    # 每关每部门需准备/确认的材料清单
    GATE_CHECKLISTS = {
        1: {  # 产品定义关
            "后台/产品": [
                "产品说明书：适合谁 / 不适合谁",
                "服务内容与交付物说明",
                "定价逻辑（基础价/加急费/高难度费）",
                "承诺边界：能承诺什么 / 不能承诺什么",
                "风险情况：哪些场景易产生投诉或交付风险",
                "交付SOP框架（步骤/节点/老师资源要求）",
            ],
            "顾问": [
                "顾问渠道客户高频痛点（final/挂科/AI率/低分/论文/ddl）",
                "真实购买场景：客户在什么情况下最容易购买",
                "客户付费理由：结果、安全、省心、速度、老师能力",
                "客户拒绝原因：贵、不信、怕没效果、觉得自己能做",
                "老客户需求 / 竞品反馈 / 成交机会",
            ],
            "学管": [
                "学管渠道（推广/小红书/垂直号）客户高频痛点整理",
                "渠道线索客群特征：和顾问侧客户有何差异",
                "哪类线索最适合这个产品 / 哪类不适合",
                "渠道客户常见拒绝理由（与顾问侧不同的部分）",
                "从学管渠道视角：推广卖点是否打中渠道客户痛点",
            ],
        },
        2: {  # 交付承接关
            "后台/产品": [
                "交付SOP文档完整版（步骤/节点/责任人/时间要求）",
                "老师资源确认（专业范围/接单容量/报价规则）",
                "质检标准与交付验收标准",
                "售后处理方式（投诉 / 修改 / 退款边界）书面化",
                "押题产品完整流程：资料收集→考点确认→老师产出→质检→交付→客户确认",
            ],
            "顾问": [
                "成交后交接清单确认（考试时间/课程资料/客户期待/承诺边界/是否紧急）",
                "明确哪些情况销售不能承诺给客户",
                "确认顾问侧成交信息如何规范交接给后台",
            ],
            "学管": [
                "确认成交后学管侧的交接流程（学管渠道客户如何交接）",
                "明确哪些情况学管渠道不能成交（超出交付范围的需求）",
                "学管渠道特殊客户需求的上报机制",
            ],
        },
        3: {  # 推广准备关
            "市场/推广": [
                "推广素材：朋友圈文案 / 社群内容 / 小红书图文",
                "客户真实痛点文案（来自顾问+学管反馈）",
                "推广形式：倒计时 / 风险自测 / 案例故事 / 热点图",
                "内容覆盖渠道：朋友圈、社群、小红书、私聊",
                "按时间节点安排（开学季/论文季/Final季/考前）",
            ],
            "顾问": [
                "审核文案：是否符合顾问渠道客户真实痛点",
                "审核文案：是否有成交钩子",
                "提供：顾问侧高频成交话术 / 案例素材",
            ],
            "学管": [
                "审核推广内容是否符合小红书/垂直号渠道特性",
                "确认学管渠道的推广素材和跟进话术",
                "提供：学管渠道高频客户问题 / 渠道成交案例素材",
                "审核推广承诺是否超出实际可交付范围",
            ],
        },
        4: {  # 销售转化关
            "顾问": [
                "完成产品培训考核（必须能回答以下6项）",
                "→ 这个产品一句话怎么介绍",
                "→ 三类适合客户 & 三类不适合客户",
                "→ 三个核心卖点",
                "→ 三个不能承诺的点",
                "→ 客户说贵怎么回答",
                "→ 客户说考虑一下怎么推进",
                "统一报价与逼单方式",
                "顾问渠道小范围试卖：优先老客户 / 有明确需求客户 / ddl紧急客户",
                "记录：推荐数、意向数、成交数、客户最关心什么",
            ],
            "学管": [
                "完成产品培训考核（同顾问标准，6项必考）",
                "学管渠道小范围试卖：优先小红书/推广渠道高意向线索",
                "记录：学管渠道推荐数、意向数、成交数",
                "学管渠道客户反馈：哪类线索最容易成交 / 最常见异议",
            ],
            "市场/推广": [
                "正式推广启动（多渠道放量）",
                "更新推广素材（根据顾问+学管反馈优化）",
            ],
        },
        5: {  # 复盘优化关
            "顾问": [
                "顾问渠道：推荐数 / 意向数 / 成交数统计",
                "最有效话术沉淀（顾问渠道）",
                "卡点原因分析（哪里流失最多）",
                "哪类客户最适合这个产品",
            ],
            "学管": [
                "学管渠道：推荐数 / 意向数 / 成交数统计",
                "最有效话术沉淀（学管渠道，与顾问侧对比）",
                "卡点原因分析（学管渠道客户的流失节点）",
                "小红书/推广渠道哪类线索质量最高",
            ],
            "市场/推广": [
                "各渠道推广数据（曝光/咨询/转化）",
                "哪条内容效果最好",
                "推广建议（继续 / 优化 / 换形式）",
            ],
            "后台/产品": [
                "复盘结论选择：继续放大 / 调整后放大 / 节点性推广 / 暂停",
                "话术/推广/交付/价格问题汇总",
                "是否沉淀到知识库",
            ],
        },
    }

    # 每关审核部门
    GATE_DEPTS = {
        1: ["产品/后台", "销售/顾问/学管"],
        2: ["产品/后台", "销售/顾问/学管", "交付/老师"],
        3: ["推广/市场", "销售/顾问/学管", "产品/后台"],
        4: ["销售/顾问/学管", "推广/市场"],
        5: ["产品/后台", "销售/顾问/学管", "推广/市场", "管理层"],
    }

    STATUS_COLORS = {"not_started": "⬜", "in_progress": "🟡", "passed": "🟢", "blocked": "🔴"}
    STATUS_LABELS = {"not_started": "未开始", "in_progress": "进行中", "passed": "已通过", "blocked": "已阻断"}
    APPROVAL_LABELS = {
        "pending": "⏳ 待审批", "approved": "✅ 已批准",
        "deferred": "⏸ 已推迟", "adjusted": "🔄 已调整", "stopped": "🛑 已叫停",
    }
    REVIEW_CONCLUSION_OPTIONS = ["继续放大", "调整后放大", "节点性推广", "暂停"]

    FEEDBACK_TYPES = [
        "定价偏高，学员反馈性价比低",
        "交付质量不稳定，学管投诉多",
        "推广素材与实际不符，导致退款",
        "销售话术不统一，顾问各说各的",
        "报名流程复杂，转化漏斗过长",
        "师资排期冲突，上课保障困难",
        "课程设置与目标院校要求脱节",
        "优惠政策没有同步给学管/顾问",
        "数据未同步到伙伴CRM，跟进混乱",
        "复盘缺席，问题未沉淀到知识库",
    ]

    def _gate_field(n): return f"gate{n}_status"

    def _prereqs_ok(ld, gate_num):
        return all(ld.get(_gate_field(p)) == "passed" for p in GATE_PREREQS[gate_num])

    def _anomaly_check(ld):
        alerts = []
        g = lambda k: ld.get(k, "not_started")
        if g("gate3_status") == "passed" and g("gate1_status") != "passed":
            alerts.append("⚠️ 推广关已通过但产品定义关未通过")
        if g("gate4_status") == "passed" and g("gate2_status") != "passed":
            alerts.append("⚠️ 销售关已通过但交付承接关未通过")
        if ld.get("has_active_quotes") and g("gate4_status") == "not_started":
            alerts.append("🔴 顾问已在报价但销售关未开启")
        if ld.get("has_promo_published") and g("gate3_status") == "not_started":
            alerts.append("🔴 推广素材已发出但推广准备关未通过")
        if ld.get("has_delivery_risk") and g("gate2_status") == "passed":
            alerts.append("🔴 交付承接关已通过但存在交付风险，需重新确认")
        if not ld.get("sales_training_done") and g("gate4_status") == "in_progress":
            alerts.append("⚠️ 销售关进行中但顾问培训未完成")
        if ld.get("sales_continuing_promises") and ld.get("mgmt_approval") == "stopped":
            alerts.append("🛑 管理层已叫停但顾问仍在继续承诺")
        if ld.get("needs_sync_to_xueguan") and not ld.get("sales_training_done"):
            alerts.append("⚠️ 需同步学管但顾问培训未完成，信息断层风险")
        if (ld.get("promo_leads_count") or 0) > 0 and g("gate3_status") == "not_started":
            alerts.append("🔴 已有推广线索进入但推广准备关未启动")
        if not ld.get("prev_review_done") and g("gate5_status") == "in_progress":
            alerts.append("⚠️ 复盘关进行中但前一轮复盘未完成")
        return alerts

    def _lc_dict(lc):
        return lc if isinstance(lc, dict) else lc.__dict__

    all_launches = list_product_launches()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 看板总览", "🚦 关卡管理", "💬 部门互评", "➕ 新建/编辑", "👔 管理层审批", "📎 资料 & 消息"
    ])

    # ── Tab 1: 看板总览 ────────────────────────────────────────────────────────
    with tab1:
        if not all_launches:
            st.info("暂无产品上线卡，请在「新建/编辑」标签页创建。")
        else:
            # 自动预警检查
            alerts = _auto_alert(all_launches)
            if alerts:
                with st.expander(f"🔔 自动预警（{len(alerts)} 条）", expanded=True):
                    for a in alerts:
                        st.warning(a)
                    if st.button("📲 一键推送预警到企业微信", key="push_all_alerts"):
                        text = "【新产品上线台 · 自动预警】\n\n" + "\n".join(alerts)
                        result = _push_wechat(text)
                        st.success(f"推送结果：{result}")
                st.divider()

            for lc in all_launches:
                ld = _lc_dict(lc)
                lid = ld.get("id")
                pname = ld.get("product_name","—")
                anomalies = _anomaly_check(ld)
                stats = _get_product_stats(pname)

                with st.container():
                    # 行1：名称 + 关卡 + 审批
                    col_name, col_gates, col_ap = st.columns([3, 5, 2])
                    with col_name:
                        st.markdown(f"**{pname}**")
                        _owners = [x for x in [ld.get("advisor_owner"), ld.get("xueguan_owner"), ld.get("backend_owner")] if x]
                        st.caption(f"负责人：{' / '.join(_owners) if _owners else '—'} ｜ 截止：{ld.get('deadline','—')}")
                    with col_gates:
                        gcols = st.columns(5)
                        for i, gc in enumerate(gcols, 1):
                            sv = ld.get(_gate_field(i), "not_started")
                            gc.markdown(
                                f"{STATUS_COLORS.get(sv,'⬜')} **关{i}**<br>"
                                f"<small>{GATE_NAMES[i]}<br>{STATUS_LABELS.get(sv,'')}</small>",
                                unsafe_allow_html=True,
                            )
                    with col_ap:
                        ap = ld.get("mgmt_approval", "pending")
                        st.markdown(APPROVAL_LABELS.get(ap, ap))

                    # 行2：咨询 + 成交数据
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("咨询量", stats["leads_total"])
                    m2.metric("已成交线索", stats["leads_won"])
                    m3.metric("转化率", f"{stats['cvr']}%")
                    m4.metric("订单数", stats["orders_count"])
                    m5.metric("成交收入", f"元{int(stats['revenue']):,}" if stats["revenue"] else "¥0")

                    if anomalies:
                        with st.expander(f"⚠️ {len(anomalies)} 条异常", expanded=False):
                            for a in anomalies:
                                st.error(a)
                    st.divider()

    # ── Tab 2: 关卡管理 ────────────────────────────────────────────────────────
    with tab2:
        if not all_launches:
            st.info("请先创建产品上线卡。")
        else:
            names2 = [_lc_dict(lc).get("product_name","—") for lc in all_launches]
            sel2 = st.selectbox("选择产品", names2, key="gate_sel")
            sel_lc = next((lc for lc in all_launches if _lc_dict(lc).get("product_name") == sel2), None)
            if sel_lc:
                ld = _lc_dict(sel_lc)
                lid = ld.get("id")

                for gate_num in range(1, 6):
                    gname = GATE_NAMES[gate_num]
                    cur = ld.get(_gate_field(gate_num), "not_started")
                    prereqs_ok = _prereqs_ok(ld, gate_num)
                    reviews = list_gate_reviews(lid, gate_num)

                    with st.expander(
                        f"{STATUS_COLORS.get(cur,'⬜')} 关{gate_num}：{gname} — {STATUS_LABELS.get(cur,'')}",
                        expanded=(cur == "in_progress"),
                    ):
                        # 前置锁定提示
                        if not prereqs_ok and cur == "not_started":
                            prereq_str = "、".join(GATE_NAMES[p] for p in GATE_PREREQS[gate_num])
                            st.warning(f"🔒 前置条件未满足：{prereq_str} 须先通过")
                        else:
                            new_status = st.selectbox(
                                "更新关卡状态",
                                ["not_started","in_progress","passed","blocked"],
                                index=["not_started","in_progress","passed","blocked"].index(cur),
                                format_func=lambda x: STATUS_LABELS.get(x, x),
                                key=f"gstatus_{lid}_{gate_num}",
                            )
                            if st.button(f"保存关{gate_num}状态", key=f"gsave_{lid}_{gate_num}"):
                                update_product_launch(lid, {_gate_field(gate_num): new_status})
                                st.success("已保存")
                                st.rerun()

                        # 各部门材料清单
                        st.markdown("---")
                        st.markdown(f"**📋 本关各部门材料 & 职责清单**")
                        for dept, items in GATE_CHECKLISTS[gate_num].items():
                            st.markdown(f"**{dept}**")
                            for item in items:
                                prefix = "&nbsp;&nbsp;&nbsp;&nbsp;" if item.startswith("→") else "- "
                                st.markdown(f"{prefix}{item}", unsafe_allow_html=True)

                        # ── 交付物：按部门分块展示 ──────────────────────────
                        st.markdown("---")
                        st.markdown("**📦 各部门交付物 & 质量标准**")

                        # 如果该关卡还没有任何交付物，自动从 GATE_CHECKLISTS 预初始化
                        delivs_all = list_deliverables(lid, gate_num)
                        if not delivs_all and cur in ("in_progress", "passed"):
                            for dept_name, items in GATE_CHECKLISTS[gate_num].items():
                                for item in items:
                                    if not item.startswith("→"):
                                        save_deliverable({
                                            "launch_id": lid,
                                            "gate_num": gate_num,
                                            "deliverable": item,
                                            "quality_std": "",
                                            "deadline": "",
                                            "owner_dept": dept_name,
                                            "status": "待完成",
                                        })
                            delivs_all = list_deliverables(lid, gate_num)

                        # 按部门分组
                        dept_order = list(GATE_CHECKLISTS[gate_num].keys())
                        other_depts = list({d.get("owner_dept") for d in delivs_all if d.get("owner_dept") not in dept_order})
                        all_depts_ordered = dept_order + other_depts

                        STATUS_ICON2 = {"待完成":"⬜","进行中":"🟡","已完成":"🟢","有问题":"🔴","待定义":"⬜","已定义":"🟡","已交付":"🟢"}
                        STATUS_OPTS2 = ["待完成","进行中","已完成","有问题"]

                        any_flagged = [d for d in delivs_all if d.get("sales_flagged")]
                        if any_flagged:
                            st.error(f"🚩 {len(any_flagged)} 项被顾问/销售标记有问题，请相关部门处理")

                        for dept_name in all_depts_ordered:
                            dept_delivs = [d for d in delivs_all if d.get("owner_dept") == dept_name]
                            if not dept_delivs:
                                continue
                            done = sum(1 for d in dept_delivs if d.get("status") in ("已完成","已交付"))
                            flagged_dept = sum(1 for d in dept_delivs if d.get("sales_flagged"))
                            dept_label = f"**{dept_name}** — {done}/{len(dept_delivs)} 完成"
                            if flagged_dept:
                                dept_label += f" 🚩{flagged_dept}项问题"
                            st.markdown(dept_label)

                            for dv in dept_delivs:
                                dv_id = dv.get("id")
                                dv_status = dv.get("status","待完成")
                                sicon = STATUS_ICON2.get(dv_status,"⬜")
                                flag_tag = " 🚩" if dv.get("sales_flagged") else ""
                                with st.expander(f"{sicon} {dv.get('deliverable','—')}{flag_tag}", expanded=bool(dv.get("sales_flagged"))):
                                    # 负责部门：更新状态 + 质量标准
                                    row1c1, row1c2 = st.columns([3,2])
                                    with row1c1:
                                        if dv.get("quality_std"):
                                            st.caption(f"质量标准：{dv['quality_std']}")
                                        if dv.get("deadline"):
                                            st.caption(f"预计完成：{dv['deadline']}")
                                    with row1c2:
                                        cur_idx = STATUS_OPTS2.index(dv_status) if dv_status in STATUS_OPTS2 else 0
                                        new_st2 = st.selectbox("状态", STATUS_OPTS2, index=cur_idx, key=f"dvst2_{dv_id}")
                                        if st.button("✓ 保存", key=f"dvsave2_{dv_id}"):
                                            update_deliverable(dv_id, {"status": new_st2})
                                            st.rerun()
                                    # 其他部门监管
                                    with st.form(f"monitor_{dv_id}"):
                                        mon_note = st.text_input("监管意见（任何部门均可填写）", value=dv.get("sales_note","") or "", key=f"mn_{dv_id}")
                                        mc1, mc2 = st.columns(2)
                                        mon_confirm = mc1.checkbox("✅ 确认达标", value=bool(dv.get("sales_confirmed")), key=f"mc_{dv_id}")
                                        mon_flag = mc2.checkbox("🚩 标记有问题", value=bool(dv.get("sales_flagged")), key=f"mf_{dv_id}")
                                        if st.form_submit_button("提交监管意见"):
                                            update_deliverable(dv_id, {
                                                "sales_note": mon_note,
                                                "sales_confirmed": mon_confirm,
                                                "sales_flagged": mon_flag,
                                                "status": "有问题" if mon_flag else ("已完成" if mon_confirm else dv_status),
                                            })
                                            st.rerun()
                                    if dv.get("sales_note") and not st.session_state.get(f"mn_{dv_id}"):
                                        st.caption(f"最新意见：{dv['sales_note']}")
                            st.divider()

                        # 各部门手动新增交付物
                        with st.expander("➕ 手动新增交付物", expanded=False):
                            with st.form(f"add_deliv_{lid}_{gate_num}"):
                                dc1, dc2, dc3 = st.columns(3)
                                new_deliv = dc1.text_input("交付物名称 *", key=f"nd_name_{lid}_{gate_num}")
                                new_deadline = dc2.text_input("预计完成时间", placeholder="如：上线前3天", key=f"nd_dl_{lid}_{gate_num}")
                                new_owner = dc3.selectbox("负责部门", DEPT_OPTIONS, key=f"nd_dept_{lid}_{gate_num}")
                                new_std = st.text_area("质量标准", key=f"nd_std_{lid}_{gate_num}")
                                if st.form_submit_button("添加"):
                                    if not new_deliv:
                                        st.error("请填写交付物名称")
                                    else:
                                        save_deliverable({
                                            "launch_id": lid, "gate_num": gate_num,
                                            "deliverable": new_deliv, "quality_std": new_std,
                                            "deadline": new_deadline, "owner_dept": normalize_role(new_owner),
                                            "status": "待完成",
                                        })
                                        st.success(f"「{new_deliv}」已添加")
                                        st.rerun()

                        # 部门评审记录
                        st.markdown("---")
                        st.markdown("**🗳 部门评审**")
                        for dept in GATE_DEPTS[gate_num]:
                            dept_revs = [r for r in reviews if (_lc_dict(r).get("reviewer_dept")) == dept]
                            latest = dept_revs[-1] if dept_revs else None
                            lrd = _lc_dict(latest) if latest else {}
                            rs = lrd.get("review_status","—")
                            icon = {"approved":"✅","needs_revision":"🔄","rejected":"❌"}.get(rs,"⬜")
                            c1, c2 = st.columns([2,3])
                            c1.markdown(f"{icon} **{dept}**: {'未评审' if rs=='—' else rs}")
                            if lrd.get("comment"): c2.caption(lrd["comment"])

                        with st.form(key=f"rev_form_{lid}_{gate_num}"):
                            r_dept = st.selectbox("我的部门", GATE_DEPTS[gate_num], key=f"rdept_{lid}_{gate_num}")
                            r_status = st.radio(
                                "评审结论",
                                ["approved","needs_revision","rejected"],
                                format_func=lambda x: {"approved":"✅ 通过","needs_revision":"🔄 需修改","rejected":"❌ 拒绝"}.get(x,x),
                                horizontal=True, key=f"rstatus_{lid}_{gate_num}",
                            )
                            r_comment = st.text_area("意见备注", key=f"rcomment_{lid}_{gate_num}")
                            if st.form_submit_button("提交评审"):
                                save_gate_review({
                                    "launch_id": lid, "gate_num": gate_num,
                                    "reviewer_dept": normalize_role(r_dept), "review_status": r_status, "comment": r_comment,
                                })
                                st.success("评审已提交")
                                st.rerun()

                        # 复盘关专属：结构化复盘表单
                        if gate_num == 5 and cur in ("in_progress", "passed"):
                            st.markdown("---")
                            st.markdown("### 📝 复盘结构化表单（上线后3-7天完成）")
                            st.markdown("**一、三个核心判断**")
                            with st.form(f"review5_form_{lid}"):
                                q1 = st.text_area("① 是否有真实客户需求？（成交数/客户反应/最关心什么）", key=f"rv5_q1_{lid}")
                                q2 = st.text_area("② 哪类客户最适合这个产品？（画像/场景/痛点）", key=f"rv5_q2_{lid}")
                                q3 = st.text_area("③ 最大成交阻力是什么？（价格/信任/流程/话术）", key=f"rv5_q3_{lid}")
                                st.markdown("**二、各部门反馈**")
                                fb_sales = st.text_area("顾问反馈（话术卡点/成交率/客户问题）", key=f"rv5_sales_{lid}")
                                fb_mkt = st.text_area("市场/推广反馈（渠道效果/最佳内容/建议）", key=f"rv5_mkt_{lid}")
                                fb_xg = st.text_area("学管反馈（交付质量/投诉/修改率/风险点）", key=f"rv5_xg_{lid}")
                                fb_prod = st.text_area("后台/产品反馈（价格/定位/SOP问题）", key=f"rv5_prod_{lid}")
                                st.markdown("**三、最终结论**")
                                conclusion = st.radio(
                                    "本产品下一步方向",
                                    REVIEW_CONCLUSION_OPTIONS,
                                    horizontal=True, key=f"rv5_conclusion_{lid}",
                                )
                                save_to_kb = st.checkbox("✅ 沉淀到知识库（复盘结论将记录为公司经验）", key=f"rv5_kb_{lid}")
                                if st.form_submit_button("提交复盘"):
                                    review_text = (
                                        f"【复盘结论】{conclusion}\n\n"
                                        f"① 真实需求：{q1}\n② 适合客户：{q2}\n③ 最大阻力：{q3}\n\n"
                                        f"顾问反馈：{fb_sales}\n市场反馈：{fb_mkt}\n"
                                        f"学管反馈：{fb_xg}\n产品反馈：{fb_prod}\n\n"
                                        f"是否沉淀知识库：{'是' if save_to_kb else '否'}"
                                    )
                                    save_gate_review({
                                        "launch_id": lid, "gate_num": 5,
                                        "reviewer_dept": "管理层",
                                        "review_status": "approved",
                                        "comment": review_text,
                                    })
                                    update_product_launch(lid, {"prev_review_done": True})
                                    st.success(f"复盘已提交，结论：{conclusion}")
                                    st.rerun()

    # ── Tab 3: 部门互评 ────────────────────────────────────────────────────────
    with tab3:
        if not all_launches:
            st.info("请先创建产品上线卡。")
        else:
            names3 = [_lc_dict(lc).get("product_name","—") for lc in all_launches]
            sel3 = st.selectbox("选择产品", names3, key="fb_sel")
            sel_lc3 = next((lc for lc in all_launches if _lc_dict(lc).get("product_name") == sel3), None)
            if sel_lc3:
                ld3 = _lc_dict(sel_lc3)
                lid3 = ld3.get("id")
                feedbacks = list_dept_feedbacks(lid3)

                DEPTS_ALL = DEPT_OPTIONS
                open_fb = [fb for fb in feedbacks if _lc_dict(fb).get("status") == "open"]
                ack_fb = [fb for fb in feedbacks if _lc_dict(fb).get("status") == "acknowledged"]
                res_fb = [fb for fb in feedbacks if _lc_dict(fb).get("status") == "resolved"]
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("🔴 待处理", len(open_fb))
                col_m2.metric("🟡 已知悉", len(ack_fb))
                col_m3.metric("🟢 已解决", len(res_fb))
                st.divider()

                with st.form("fb_form"):
                    c1, c2 = st.columns(2)
                    fb_from = c1.selectbox("发起部门", DEPTS_ALL, key="fb_from")
                    fb_to = c2.selectbox("反馈对象部门", DEPTS_ALL, key="fb_to")
                    fb_type = st.selectbox("反馈类型", FEEDBACK_TYPES, key="fb_type")
                    fb_desc = st.text_area("详细描述", key="fb_desc")
                    if st.form_submit_button("提交反馈"):
                        if fb_from == fb_to:
                            st.error("发起部门和对象部门不能相同")
                        else:
                            save_dept_feedback({
                                "launch_id": lid3, "from_dept": normalize_role(fb_from),
                                "to_dept": normalize_role(fb_to), "feedback_type": fb_type,
                                "description": fb_desc, "status": "open",
                            })
                            st.success("反馈已提交")
                            st.rerun()

                st.divider()
                st.subheader(f"📋 反馈记录（共 {len(feedbacks)} 条）")
                for fb in feedbacks:
                    fbd = _lc_dict(fb)
                    fstatus = fbd.get("status","open")
                    icon = {"open":"🔴","acknowledged":"🟡","resolved":"🟢"}.get(fstatus,"⬜")
                    c1, c2 = st.columns([5,2])
                    with c1:
                        st.markdown(f"{icon} **{fbd.get('from_dept','?')} → {fbd.get('to_dept','?')}**  「{fbd.get('feedback_type','?')}」")
                        if fbd.get("description"): st.caption(fbd["description"])
                    with c2:
                        fb_id = fbd.get("id")
                        if fstatus == "open":
                            if st.button("已知悉", key=f"fb_ack_{fb_id}"):
                                update_dept_feedback_status(fb_id, "acknowledged"); st.rerun()
                        elif fstatus == "acknowledged":
                            if st.button("已解决", key=f"fb_res_{fb_id}"):
                                update_dept_feedback_status(fb_id, "resolved"); st.rerun()
                    st.divider()

    # ── Tab 4: 新建/编辑 ──────────────────────────────────────────────────────
    with tab4:
        edit_mode = st.radio("操作模式", ["新建产品", "编辑已有产品"], horizontal=True)
        if edit_mode == "新建产品":
            with st.form("new_launch_form"):
                st.subheader("产品上线卡 — 基本信息")
                _cat_labels = [f"{p['name']} ({p['id']})" for p in _CATALOG_PRODUCTS]
                _cat_lookup = dict(zip(_cat_labels, _CATALOG_PRODUCTS))
                c1, c2 = st.columns(2)
                with c1:
                    nl_cat_label = st.selectbox("产品目录 *", _cat_labels)
                    nl_cat = _cat_lookup[nl_cat_label]
                    nl_stage = st.selectbox("阶段", ["需求判断", "上线准备", "小范围试推", "正式推广", "复盘", "暂停"])
                    nl_target = st.text_input("目标学生需求")
                    nl_channels = st.text_input("推荐渠道（逗号分隔）")
                with c2:
                    nl_backend_owner = st.text_input("后台负责人")
                    nl_advisor_owner = st.text_input("顾问负责人")
                    nl_xueguan_owner = st.text_input("学管负责人")
                    nl_promo_owner = st.text_input("推广负责人")
                    nl_deadline = st.date_input("目标上线日期")
                nl_match_logic = st.text_area("产品匹配逻辑")
                nl_boundary = st.text_area("销售边界 / 禁用表达")
                nl_next_action = st.text_area("下一步动作")
                st.subheader("行为标记（用于异常检测）")
                bc1, bc2 = st.columns(2)
                with bc1:
                    nl_aq = st.checkbox("顾问已在报价")
                    nl_pp = st.checkbox("推广素材已发出")
                    nl_dr = st.checkbox("存在交付风险")
                    nl_st = st.checkbox("顾问培训已完成")
                with bc2:
                    nl_cp = st.checkbox("顾问仍在继续承诺")
                    nl_sx = st.checkbox("需同步给学管")
                    nl_pl = st.number_input("推广线索数", min_value=0)
                    nl_sf = st.number_input("销售跟进数", min_value=0)
                if st.form_submit_button("🚀 创建产品上线卡"):
                    save_product_launch({
                        "catalog_id": nl_cat["id"],
                        "product_name": nl_cat["name"],
                        "stage": nl_stage,
                        "target_student_needs": nl_target,
                        "product_match_logic": nl_match_logic,
                        "recommended_channels": nl_channels,
                        "backend_owner": nl_backend_owner,
                        "advisor_owner": nl_advisor_owner,
                        "xueguan_owner": nl_xueguan_owner,
                        "promo_owner": nl_promo_owner,
                        "deadline": str(nl_deadline),
                        "status_risk_boundary": "in_progress" if nl_boundary else "not_ready",
                        "next_action": nl_next_action or nl_boundary,
                        "has_active_quotes": nl_aq, "has_promo_published": nl_pp,
                        "has_delivery_risk": nl_dr, "sales_training_done": nl_st,
                        "sales_continuing_promises": nl_cp, "needs_sync_to_xueguan": nl_sx,
                        "promo_leads_count": int(nl_pl), "sales_followup_count": int(nl_sf),
                    })
                    st.success(f"「{nl_cat['name']}」上线卡已创建！")
                    st.rerun()
        else:
            if not all_launches:
                st.info("暂无产品。")
            else:
                edit_names = [_lc_dict(lc).get("product_name","—") for lc in all_launches]
                edit_sel = st.selectbox("选择要编辑的产品", edit_names, key="edit_sel")
                edit_lc = next((lc for lc in all_launches if _lc_dict(lc).get("product_name") == edit_sel), None)
                if edit_lc:
                    ed = _lc_dict(edit_lc)
                    eid = ed.get("id")
                    with st.form("edit_launch_form"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_name = st.text_input("产品名称", value=ed.get("product_name",""), disabled=True)
                            _stage_options = ["需求判断", "上线准备", "小范围试推", "正式推广", "复盘", "暂停"]
                            _stage_index = _stage_options.index(ed.get("stage")) if ed.get("stage") in _stage_options else 0
                            e_stage = st.selectbox("阶段", _stage_options, index=_stage_index)
                            e_backend_owner = st.text_input("后台负责人", value=ed.get("backend_owner","") or "")
                            e_advisor_owner = st.text_input("顾问负责人", value=ed.get("advisor_owner","") or "")
                        with c2:
                            e_xueguan_owner = st.text_input("学管负责人", value=ed.get("xueguan_owner","") or "")
                            e_promo_owner = st.text_input("推广负责人", value=ed.get("promo_owner","") or "")
                            e_target = st.text_input("目标学生需求", value=ed.get("target_student_needs","") or "")
                        e_match = st.text_area("产品匹配逻辑", value=ed.get("product_match_logic","") or "")
                        e_channels = st.text_input("推荐渠道", value=ed.get("recommended_channels","") or "")
                        e_next = st.text_area("下一步动作", value=ed.get("next_action","") or "")
                        st.subheader("行为标记")
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            e_aq = st.checkbox("顾问已在报价", value=bool(ed.get("has_active_quotes")))
                            e_pp = st.checkbox("推广素材已发出", value=bool(ed.get("has_promo_published")))
                            e_dr = st.checkbox("存在交付风险", value=bool(ed.get("has_delivery_risk")))
                            e_st = st.checkbox("顾问培训已完成", value=bool(ed.get("sales_training_done")))
                        with bc2:
                            e_cp = st.checkbox("顾问仍在继续承诺", value=bool(ed.get("sales_continuing_promises")))
                            e_sx = st.checkbox("需同步给学管", value=bool(ed.get("needs_sync_to_xueguan")))
                            e_pl = st.number_input("推广线索数", value=int(ed.get("promo_leads_count") or 0))
                            e_sf = st.number_input("销售跟进数", value=int(ed.get("sales_followup_count") or 0))
                        if st.form_submit_button("💾 保存修改"):
                            update_product_launch(eid, {
                                "stage": e_stage,
                                "backend_owner": e_backend_owner, "advisor_owner": e_advisor_owner,
                                "xueguan_owner": e_xueguan_owner, "promo_owner": e_promo_owner,
                                "target_student_needs": e_target, "product_match_logic": e_match,
                                "recommended_channels": e_channels, "next_action": e_next,
                                "has_active_quotes": e_aq, "has_promo_published": e_pp,
                                "has_delivery_risk": e_dr, "sales_training_done": e_st,
                                "sales_continuing_promises": e_cp, "needs_sync_to_xueguan": e_sx,
                                "promo_leads_count": int(e_pl), "sales_followup_count": int(e_sf),
                            })
                            st.success("修改已保存")
                            st.rerun()
                    st.divider()
                    if st.button("🗑 删除此产品上线卡", type="secondary"):
                        delete_product_launch(eid)
                        st.warning("已删除")
                        st.rerun()

    # ── Tab 5: 管理层审批 ──────────────────────────────────────────────────────
    with tab5:
        if not all_launches:
            st.info("暂无产品上线卡。")
        else:
            for lc in all_launches:
                ld = _lc_dict(lc)
                lid = ld.get("id")
                ap = ld.get("mgmt_approval","pending")
                ap_note = ld.get("mgmt_approval_note","")
                anomalies = _anomaly_check(ld)
                with st.expander(f"{APPROVAL_LABELS.get(ap,ap)} — {ld.get('product_name','—')}", expanded=(ap=="pending")):
                    c1, c2 = st.columns([2,3])
                    with c1:
                        _owners_ap = [x for x in [ld.get("advisor_owner"), ld.get("xueguan_owner"), ld.get("backend_owner")] if x]
                        st.markdown(f"**负责人**: {' / '.join(_owners_ap) if _owners_ap else '—'}")
                        st.markdown(f"**目标日期**: {ld.get('deadline','—')}")
                        st.markdown(f"**产品目录ID**: {ld.get('catalog_id','—')}")
                    with c2:
                        gates_str = "  ".join(
                            f"{STATUS_COLORS.get(ld.get(_gate_field(i),'not_started'),'⬜')} {GATE_NAMES[i]}"
                            for i in range(1,6)
                        )
                        st.markdown(gates_str)
                    if anomalies:
                        st.error("存在异常，请审阅：")
                        for a in anomalies:
                            st.markdown(f"- {a}")
                    with st.form(f"approval_{lid}"):
                        new_ap = st.radio(
                            "审批决策",
                            ["pending","approved","deferred","adjusted","stopped"],
                            index=["pending","approved","deferred","adjusted","stopped"].index(ap),
                            format_func=lambda x: APPROVAL_LABELS.get(x,x),
                            horizontal=True, key=f"ap_radio_{lid}",
                        )
                        new_note = st.text_area("审批意见", value=ap_note or "", key=f"ap_note_{lid}")
                        if st.form_submit_button("提交审批"):
                            update_product_launch(lid, {"mgmt_approval": new_ap, "mgmt_approval_note": new_note})
                            st.success("审批已更新")
                            st.rerun()

    # ── Tab 6: 资料 & 消息 ────────────────────────────────────────────────────
    with tab6:
        if not all_launches:
            st.info("请先创建产品上线卡。")
        else:
            names6 = [_lc_dict(lc).get("product_name","—") for lc in all_launches]
            sel6 = st.selectbox("选择产品", names6, key="fm_sel")
            sel_lc6 = next((lc for lc in all_launches if _lc_dict(lc).get("product_name") == sel6), None)
            if sel_lc6:
                ld6 = _lc_dict(sel_lc6)
                lid6 = ld6.get("id")

                sub1, sub2 = st.tabs(["📁 资料库", "💬 消息互通"])

                # ── 资料库 ────────────────────────────────────────────────
                with sub1:
                    FILE_CATS = ["产品说明书", "销售话术", "推广素材", "交付SOP", "复盘报告", "其他"]
                    DEPTS_UP = DEPT_OPTIONS
                    GATE_OPTS = {0: "通用（不限关卡）", 1: "关1 产品定义关", 2: "关2 交付承接关",
                                 3: "关3 推广准备关", 4: "关4 销售转化关", 5: "关5 复盘优化关"}

                    with st.form("upload_form"):
                        st.subheader("📤 上传资料")
                        uploaded = st.file_uploader(
                            "选择文件（支持 PDF/Word/Excel/图片，单文件最大50MB）",
                            type=["pdf","docx","doc","xlsx","xls","pptx","ppt","png","jpg","jpeg","txt","md","csv"],
                        )
                        uc1, uc2, uc3 = st.columns(3)
                        up_cat = uc1.selectbox("资料分类", FILE_CATS, key="up_cat")
                        up_gate = uc2.selectbox("关联关卡", list(GATE_OPTS.keys()),
                                                format_func=lambda x: GATE_OPTS[x], key="up_gate")
                        up_dept = uc3.selectbox("上传部门", DEPTS_UP, key="up_dept")
                        up_desc = st.text_input("备注说明（可选）", key="up_desc")
                        if st.form_submit_button("📤 上传"):
                            if not uploaded:
                                st.error("请选择文件")
                            else:
                                ts = int(time.time())
                                stored = f"{ts}_{uploaded.name}"
                                fpath = os.path.join(UPLOAD_DIR, stored)
                                with open(fpath, "wb") as f:
                                    f.write(uploaded.read())
                                save_uploaded_file({
                                    "launch_id": lid6,
                                    "gate_num": up_gate,
                                    "filename": uploaded.name,
                                    "stored_name": stored,
                                    "file_size": os.path.getsize(fpath),
                                    "category": up_cat,
                                    "uploader": normalize_role(up_dept),
                                    "description": up_desc,
                                    "file_path": fpath,
                                })
                                st.success(f"「{uploaded.name}」上传成功")
                                st.rerun()

                    st.divider()
                    st.subheader("📂 已上传资料")

                    files = list_uploaded_files(lid6)
                    if not files:
                        st.info("暂无资料，请上传。")
                    else:
                        # 按关卡分组展示
                        for gate_key, gate_label in GATE_OPTS.items():
                            gate_files = [f for f in files if f.get("gate_num") == gate_key]
                            if not gate_files:
                                continue
                            st.markdown(f"**{gate_label}**")
                            for f in gate_files:
                                fsize_kb = round((f.get("file_size") or 0) / 1024, 1)
                                c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                                c1.markdown(f"📄 {f['filename']}")
                                c2.caption(f"{f.get('category','')} · {f.get('uploader','')}")
                                c3.caption(f"{fsize_kb} KB · {str(f.get('created_at',''))[:16]}")
                                # 下载按钮
                                fpath = f.get("file_path","")
                                if fpath and os.path.exists(fpath):
                                    with open(fpath, "rb") as fh:
                                        c4.download_button(
                                            "⬇", data=fh.read(),
                                            file_name=f["filename"],
                                            key=f"dl_{f['id']}",
                                        )
                                if f.get("description"):
                                    st.caption(f"　　↳ {f['description']}")
                            st.divider()

                # ── 消息互通 ─────────────────────────────────────────────
                with sub2:
                    DEPTS_MSG = DEPT_OPTIONS
                    MSG_TYPES = ["📢 通知", "✅ 任务", "🚨 紧急", "📝 复盘"]

                    with st.form("msg_form"):
                        st.subheader("✉️ 发送消息")
                        mc1, mc2, mc3 = st.columns(3)
                        msg_from = mc1.selectbox("发送部门", DEPTS_MSG, key="msg_from")
                        msg_to = mc2.selectbox("接收部门", ["全员"] + DEPTS_MSG, key="msg_to")
                        msg_type = mc3.selectbox("消息类型", MSG_TYPES, key="msg_type")
                        msg_content = st.text_area("消息内容 *", height=120, key="msg_content")
                        push_wx = st.checkbox("📲 同时推送到企业微信", value=True, key="push_wx")
                        if st.form_submit_button("发送"):
                            if not msg_content.strip():
                                st.error("请填写消息内容")
                            else:
                                push_result = ""
                                clean_type = msg_type.split(" ")[-1]
                                if push_wx:
                                    wx_text = (
                                        f"【新产品上线台 · {clean_type}】\n"
                                        f"产品：{ld6.get('product_name','—')}\n"
                                        f"{msg_from} → {msg_to}\n\n"
                                        f"{msg_content}"
                                    )
                                    push_result = _push_wechat(wx_text)
                                save_internal_message({
                                    "launch_id": lid6,
                                    "from_dept": msg_from,
                                    "to_dept": msg_to,
                                    "msg_type": clean_type,
                                    "content": msg_content,
                                    "pushed_to_wechat": push_wx,
                                    "push_status": push_result,
                                })
                                if push_wx:
                                    if "成功" in push_result:
                                        st.success(f"消息已发送并推送企业微信 ✅")
                                    else:
                                        st.warning(f"消息已保存，企业微信推送：{push_result}")
                                else:
                                    st.success("消息已发送")
                                st.rerun()

                    st.divider()
                    st.subheader("📋 消息记录")
                    messages = list_internal_messages(lid6)
                    if not messages:
                        st.info("暂无消息记录。")
                    else:
                        TYPE_ICONS = {"通知":"📢","任务":"✅","紧急":"🚨","复盘":"📝"}
                        for msg in messages:
                            mtype = msg.get("msg_type","通知")
                            icon = TYPE_ICONS.get(mtype,"💬")
                            wx_tag = "📲" if msg.get("pushed_to_wechat") else ""
                            c1, c2 = st.columns([6,2])
                            with c1:
                                st.markdown(
                                    f"{icon} **{msg.get('from_dept','?')} → {msg.get('to_dept','?')}**  "
                                    f"<small>{str(msg.get('created_at',''))[:16]}</small> {wx_tag}",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(f"> {msg.get('content','')}")
                            with c2:
                                if msg.get("push_status"):
                                    st.caption(msg["push_status"])
                            st.divider()
