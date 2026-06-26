"""
极致教育 · 实用增长工作台

启动：
  streamlit run practical_app.py

目标：
  - 不复用旧 dashboard 的复杂页面壳
  - 只展示来自真实数据库的数据
  - 无数据时明确 no_data，不输出结论
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database import (
    init_db,
    list_orders,
    list_leads,
    list_tasks,
    save_task,
    update_task_status,
    list_product_launches,
    save_product_launch,
    update_product_launch,
)
from services.guardrails import catalog_product_options, validate_product
from services.business_constants import normalize_department


ROOT = Path(__file__).parent


@st.cache_resource
def _boot():
    init_db()
    return True


_boot()

st.set_page_config(
    page_title="极致教育 · 实用增长工作台",
    page_icon="",
    layout="wide",
)

st.markdown(
    """
<style>
div.block-container{padding-top:1.2rem;max-width:1320px}
.topline{font-size:13px;color:#64748b;margin-bottom:14px}
.workband{border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;background:#fff}
.ok{color:#047857;font-weight:650}
.warn{color:#b45309;font-weight:650}
.bad{color:#b91c1c;font-weight:650}
.muted{color:#64748b}
.small{font-size:12px;color:#64748b}
</style>
""",
    unsafe_allow_html=True,
)


PRODUCTS = catalog_product_options()
PRODUCT_NAME_BY_ID = {p["id"]: p["name"] for p in PRODUCTS}
PRODUCT_LABELS = [f"{p['name']} ({p['id']})" for p in PRODUCTS]
PRODUCT_BY_LABEL = dict(zip(PRODUCT_LABELS, PRODUCTS))


def fmt_money(v: float | int | None) -> str:
    v = float(v or 0)
    if v >= 10000:
        return f"{v / 10000:.1f}万"
    return f"{v:.0f}"


def no_data(message: str):
    st.info(f"no_data：{message}")


def product_display(raw: str | None) -> str:
    mapped = validate_product(raw or "")
    pid = mapped.get("canonical_product_id")
    return PRODUCT_NAME_BY_ID.get(pid, raw or "未知产品")


def load_data():
    orders_30 = list_orders(days=30, limit=5000)
    orders_7 = list_orders(days=7, limit=1000)
    leads_30 = list_leads(days=30, limit=5000)
    leads_7 = list_leads(days=7, limit=1000)
    tasks = list_tasks(limit=500)
    launches = list_product_launches()
    return orders_30, orders_7, leads_30, leads_7, tasks, launches


orders_30, orders_7, leads_30, leads_7, tasks_all, launches_all = load_data()

st.title("极致教育 · 实用增长工作台")
st.markdown(
    f"<div class='topline'>只看真实数据 · 无数据不下结论 · {datetime.now().strftime('%Y-%m-%d %H:%M')} 更新</div>",
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "工作区",
    ["今日作战台", "新产品上线", "增长判断", "数据健康"],
)


def render_today():
    st.subheader("今日作战台")
    st.caption("老板和团队每天先看这里：今天该处理什么，依据是什么，谁负责。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("近7天订单", len(orders_7))
    c2.metric("近7天线索", len(leads_7))
    c3.metric("待办任务", sum(1 for t in tasks_all if t.get("status") in ("todo", "doing")))
    c4.metric("上线产品卡", len(launches_all))

    st.divider()

    left, mid, right = st.columns([1.1, 1, 1])

    with left:
        st.markdown("#### 1. 今天优先跟进")
        if not leads_30:
            no_data("leads 表暂无近30天线索，无法生成跟进清单。")
        else:
            rows = []
            for lead in leads_30:
                status = lead.get("deal_status") or "new"
                if status in ("won", "lost", "inactive"):
                    continue
                deadline = lead.get("deadline") or ""
                score = 0
                if deadline:
                    try:
                        days_left = (datetime.fromisoformat(deadline[:10]) - datetime.now()).days
                        if days_left <= 7:
                            score += 40
                    except Exception:
                        pass
                if lead.get("quoted_price"):
                    score += 25
                if status in ("quoted", "follow_up", "contacted"):
                    score += 20
                if lead.get("pain_point"):
                    score += 15
                rows.append({
                    "优先级": score,
                    "客户": lead.get("customer_name") or "未命名",
                    "学校": lead.get("school") or "",
                    "产品": product_display(lead.get("product_interest")),
                    "状态": status,
                    "顾问": lead.get("sales_owner") or "未分配",
                    "证据": "leads.deadline/quoted_price/deal_status/pain_point",
                })
            rows = sorted(rows, key=lambda x: -x["优先级"])[:12]
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                no_data("近30天线索都已成交/流失/休眠，没有需要跟进的对象。")

    with mid:
        st.markdown("#### 2. 今天能推什么")
        if not orders_30:
            no_data("orders 表暂无近30天订单，不能判断热销产品。")
        else:
            prod_counter = Counter(product_display(o.get("product")) for o in orders_30)
            revenue = defaultdict(float)
            for order in orders_30:
                revenue[product_display(order.get("product"))] += float(order.get("amount") or 0)
            product_rows = [
                {
                    "产品": p,
                    "近30天订单": n,
                    "近30天营收": fmt_money(revenue[p]),
                    "confidence": "medium" if n >= 3 else "low",
                    "responsible_role": "顾问",
                    "evidence": "orders.product/orders.amount",
                }
                for p, n in prod_counter.most_common(8)
                if p != "未知产品"
            ]
            if product_rows:
                st.dataframe(pd.DataFrame(product_rows), width="stretch", hide_index=True)
            else:
                no_data("订单产品无法映射到产品目录。")

    with right:
        st.markdown("#### 3. 卡点")
        overdue = []
        today_s = datetime.now().date().isoformat()
        for task in tasks_all:
            due = (task.get("due_date") or "")[:10]
            if task.get("status") in ("todo", "doing") and due and due < today_s:
                overdue.append(task)
        if overdue:
            dept_counts = Counter(normalize_department(t.get("department") or "未分配") for t in overdue)
            st.warning(f"有 {len(overdue)} 个逾期任务")
            st.dataframe(
                pd.DataFrame([
                    {"角色": d, "逾期数": n, "evidence": "tasks.due_date/tasks.status"}
                    for d, n in dept_counts.most_common()
                ]),
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("当前没有逾期待办。")

    st.divider()
    st.markdown("#### 立即创建任务")
    with st.form("quick_task"):
        tc1, tc2, tc3 = st.columns([2, 1, 1])
        title = tc1.text_input("任务标题")
        dept = tc2.selectbox("负责角色", ["顾问", "学管", "推广部", "后台", "管理层"])
        priority = tc3.selectbox("优先级", ["高", "中", "低", "紧急"])
        desc = st.text_area("任务说明/证据")
        submitted = st.form_submit_button("创建任务")
        if submitted:
            if not title.strip():
                st.error("请填写任务标题。")
            else:
                save_task({
                    "title": title.strip(),
                    "description": desc.strip(),
                    "department": normalize_department(dept),
                    "priority": priority,
                    "task_source": "实用工作台",
                    "due_date": datetime.now() + timedelta(days=2),
                })
                st.success("任务已创建。刷新后可在待办里看到。")


def render_launch():
    st.subheader("新产品上线")
    st.caption("只允许从产品目录选，不允许自由编产品名。")

    left, right = st.columns([0.95, 1.25])

    with left:
        st.markdown("#### 创建上线卡")
        with st.form("launch_form"):
            label = st.selectbox("产品目录", PRODUCT_LABELS)
            product = PRODUCT_BY_LABEL[label]
            stage = st.selectbox("阶段", ["需求判断", "上线准备", "小范围试推", "正式推广", "复盘", "暂停"])
            target_need = st.text_area("目标学生需求")
            match_logic = st.text_area("产品匹配逻辑")
            channels = st.text_input("推荐渠道")
            c1, c2 = st.columns(2)
            advisor = c1.text_input("顾问负责人")
            xueguan = c2.text_input("学管负责人")
            backend = c1.text_input("后台负责人")
            promo = c2.text_input("推广负责人")
            next_action = st.text_area("下一步动作")
            if st.form_submit_button("创建"):
                save_product_launch({
                    "catalog_id": product["id"],
                    "product_name": product["name"],
                    "stage": stage,
                    "target_student_needs": target_need,
                    "product_match_logic": match_logic,
                    "recommended_channels": channels,
                    "advisor_owner": advisor,
                    "xueguan_owner": xueguan,
                    "backend_owner": backend,
                    "promo_owner": promo,
                    "next_action": next_action,
                })
                st.success("上线卡已创建。")

    with right:
        st.markdown("#### 当前上线卡")
        if not launches_all:
            no_data("暂无产品上线卡。")
        else:
            rows = []
            for item in launches_all:
                readiness = [
                    item.get("status_advisor_script"),
                    item.get("status_xueguan_rules"),
                    item.get("status_promo_materials"),
                    item.get("status_catalog"),
                    item.get("status_teacher_resource"),
                    item.get("status_risk_boundary"),
                    item.get("status_forbidden_claims"),
                ]
                ready_count = sum(1 for x in readiness if x == "ready")
                rows.append({
                    "ID": item.get("id"),
                    "产品": item.get("product_name"),
                    "阶段": item.get("stage"),
                    "准备度": f"{ready_count}/7",
                    "顾问": item.get("advisor_owner") or "",
                    "学管": item.get("xueguan_owner") or "",
                    "下一步": item.get("next_action") or "",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown("#### 更新阶段")
        if launches_all:
            options = {f"#{x['id']} {x['product_name']}": x for x in launches_all}
            selected = st.selectbox("选择上线卡", list(options))
            new_stage = st.selectbox("新阶段", ["需求判断", "上线准备", "小范围试推", "正式推广", "复盘", "暂停"])
            note = st.text_area("下一步动作/审批意见")
            if st.button("保存更新"):
                update_product_launch(options[selected]["id"], {"stage": new_stage, "next_action": note})
                st.success("已更新。")


def render_growth():
    st.subheader("增长判断")
    st.caption("这里不是 AI 算命，只做基于 orders/leads/tasks 的可解释判断。")

    if len(orders_30) < 5:
        no_data("近30天订单少于5单，不输出增长趋势结论。")
        return

    total_rev = sum(float(o.get("amount") or 0) for o in orders_30)
    avg_order = total_rev / max(len(orders_30), 1)
    lead_count = len(leads_30)
    won_count = sum(1 for l in leads_30 if l.get("deal_status") in ("won", "completed"))
    cvr = won_count / lead_count if lead_count else None

    c1, c2, c3 = st.columns(3)
    c1.metric("近30天营收", fmt_money(total_rev))
    c2.metric("平均客单价", fmt_money(avg_order))
    c3.metric("线索转化率", f"{cvr:.1%}" if cvr is not None else "no_data")

    st.divider()
    st.markdown("#### 本周判断")

    judgments = []
    prod_counter = Counter(product_display(o.get("product")) for o in orders_30)
    top_product, top_count = prod_counter.most_common(1)[0]
    judgments.append({
        "判断": f"当前主要收入来自 {top_product}",
        "建议动作": "顾问优先复盘该产品成交话术，推广部只放大已验证素材",
        "responsible_role": "顾问",
        "confidence": "medium" if top_count >= 3 else "low",
        "evidence": f"orders.product 近30天 {top_count} 单",
    })

    if cvr is None:
        judgments.append({
            "判断": "无法判断线索转化率",
            "建议动作": "先补全 leads.deal_status，再决定是否加投放",
            "responsible_role": "后台",
            "confidence": "no_data",
            "evidence": "leads.deal_status 缺失或无线索",
        })
    elif cvr < 0.2:
        judgments.append({
            "判断": "线索转化率偏低",
            "建议动作": "顾问/学管抽查最近20条未成交线索，按价格/信任/产品不匹配分类",
            "responsible_role": "顾问",
            "confidence": "medium",
            "evidence": f"leads 近30天 won={won_count}, total={lead_count}",
        })
    else:
        judgments.append({
            "判断": "转化率暂未显示明显异常",
            "建议动作": "保持当前跟进节奏，重点提高高客单产品占比",
            "responsible_role": "顾问",
            "confidence": "medium",
            "evidence": f"leads 近30天 won={won_count}, total={lead_count}",
        })

    st.dataframe(pd.DataFrame(judgments), width="stretch", hide_index=True)

    st.markdown("#### 一键落任务")
    for idx, item in enumerate(judgments):
        if st.button(f"创建任务：{item['建议动作'][:28]}", key=f"growth_task_{idx}"):
            save_task({
                "title": item["建议动作"],
                "description": f"{item['判断']}\n证据：{item['evidence']}\nconfidence：{item['confidence']}",
                "department": item["responsible_role"],
                "priority": "高" if item["confidence"] != "no_data" else "中",
                "task_source": "实用增长判断",
                "due_date": datetime.now() + timedelta(days=3),
            })
            st.success("任务已创建。")


def render_health():
    st.subheader("数据健康")
    st.caption("先知道哪些数据能用，哪些不能用。")
    checks = [
        {"数据": "orders", "记录": len(orders_30), "状态": "可用" if orders_30 else "no_data", "用途": "收入、产品趋势"},
        {"数据": "leads", "记录": len(leads_30), "状态": "可用" if leads_30 else "no_data", "用途": "跟进、转化率"},
        {"数据": "tasks", "记录": len(tasks_all), "状态": "可用" if tasks_all else "no_data", "用途": "执行卡点"},
        {"数据": "product_launches", "记录": len(launches_all), "状态": "可用" if launches_all else "no_data", "用途": "新产品上线"},
        {"数据": "PRODUCT_CATALOG", "记录": len(PRODUCTS), "状态": "可用" if PRODUCTS else "no_data", "用途": "产品校验"},
    ]
    st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True)

    st.markdown("#### 待办任务")
    active = [t for t in tasks_all if t.get("status") in ("todo", "doing")]
    if not active:
        no_data("暂无未完成任务。")
    else:
        df = pd.DataFrame(active)[["id", "title", "department", "priority", "status", "due_date"]]
        st.dataframe(df, width="stretch", hide_index=True)
        task_ids = {f"#{t['id']} {t['title']}": t["id"] for t in active}
        selected = st.selectbox("标记任务完成", list(task_ids))
        if st.button("完成"):
            update_task_status(task_ids[selected], "done", notes="实用工作台标记完成")
            st.success("已标记完成。")


if page == "今日作战台":
    render_today()
elif page == "新产品上线":
    render_launch()
elif page == "增长判断":
    render_growth()
else:
    render_health()
