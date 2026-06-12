"""
极致教育 · 营销自动化控制台
启动：streamlit run dashboard/app.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# 把项目根目录加入 Python 路径
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database import (
    init_db, list_contents, get_content,
    update_content_status, get_dashboard_stats, list_campaigns,
    list_knowledge_docs,
)
from database.db import engine
from database.models import Base

# ── 页面配置 ──
st.set_page_config(
    page_title="极致教育 · 营销控制台",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局样式 ──
st.markdown("""
<style>
  .metric-card {
    background: #f8f9fa; border-radius: 10px;
    padding: 16px; text-align: center;
    border-left: 4px solid #4CAF50;
  }
  .status-draft       { background:#e3f2fd; color:#1565c0; padding:2px 8px; border-radius:10px; font-size:12px; }
  .status-pending     { background:#fff3e0; color:#e65100; padding:2px 8px; border-radius:10px; font-size:12px; }
  .status-approved    { background:#e8f5e9; color:#2e7d32; padding:2px 8px; border-radius:10px; font-size:12px; }
  .status-used        { background:#f3e5f5; color:#6a1b9a; padding:2px 8px; border-radius:10px; font-size:12px; }
  .status-archived    { background:#eceff1; color:#546e7a; padding:2px 8px; border-radius:10px; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ── 初始化数据库 ──
try:
    import yaml
    config_path = ROOT / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    init_db(config)
except Exception as e:
    st.error(f"数据库初始化失败：{e}")
    st.stop()

# ── 状态标签映射 ──
STATUS_LABELS = {
    "draft":          "草稿",
    "pending_review": "待审核",
    "approved":       "已通过",
    "used":           "已使用",
    "reviewed":       "已复盘",
    "archived":       "已废弃",
}
STATUS_OPTIONS = list(STATUS_LABELS.items())

TYPE_LABELS = {
    "xiaohongshu":    "📱 小红书",
    "moments":        "🌅 朋友圈",
    "group_msg":      "💬 群消息",
    "referral_script":"🔄 转介绍",
    "sales_script":   "💼 销售话术",
    "monthly_plan":   "📅 月度计划",
    "weekly_plan":    "📋 周计划",
    "poster":         "🎨 海报",
}

PRODUCT_LABELS = {
    "regular":        "常规辅导",
    "annual_package": "学年包",
    "guaranteed":     "包过辅导",
    "dissertation":   "DP论文",
    "b2b":            "对公合作",
}

# ═══════════════════════════════════════════
# 侧边栏导航
# ═══════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/color/96/graduation-cap.png", width=60)
    st.title("营销控制台")
    st.caption("极致教育 · 内部系统")
    st.divider()

    page = st.radio(
        "导航",
        ["📊 今日看板", "📝 内容池", "📅 营销日历", "💼 销售素材库", "📚 知识库管理"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")


# ═══════════════════════════════════════════
# 页面 1：今日看板
# ═══════════════════════════════════════════
if page == "📊 今日看板":
    st.title("📊 今日营销看板")
    st.caption(f"{datetime.now().strftime('%Y年%m月%d日')} · 实时数据")

    stats = get_dashboard_stats()

    # ── 核心指标 ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("内容总数", stats["total"])
    c2.metric("🟡 待审核", stats["pending"], delta=None)
    c3.metric("🟢 已通过", stats["approved"])
    c4.metric("🟣 已使用", stats["used"])
    c5.metric("⚪ 草稿", stats["draft"])

    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("📌 最新生成内容")
        for item in stats.get("recent", []):
            status_key = item.get("status", "draft")
            label = STATUS_LABELS.get(status_key, status_key)
            with st.expander(f"{TYPE_LABELS.get(item['content_type'], item['content_type'])}  |  {item['title'] or '（无标题）'}  ·  {label}"):
                st.caption(f"产品：{PRODUCT_LABELS.get(item['product_id'], item['product_id'] or '-')}  |  创建：{item['created_at'][:16] if item['created_at'] else '-'}")
                st.write(item["body"][:300] + "..." if len(item.get("body","")) > 300 else item.get("body",""))
                if st.button("审核通过", key=f"approve_dash_{item['id']}"):
                    update_content_status(item["id"], "approved")
                    st.rerun()

    with col_right:
        st.subheader("📈 内容类型分布")
        if stats["by_type"]:
            chart_data = {TYPE_LABELS.get(k, k): v for k, v in stats["by_type"].items()}
            st.bar_chart(chart_data)
        else:
            st.info("暂无内容数据")

        st.subheader("🚀 快速操作")
        st.markdown("""
        在终端运行以下命令生成内容：
        ```bash
        # 生成月度计划
        python main.py monthly

        # 生成周计划
        python main.py weekplan

        # 生成小红书
        python main.py post '主题' regular
        ```
        """)


# ═══════════════════════════════════════════
# 页面 2：内容池
# ═══════════════════════════════════════════
elif page == "📝 内容池":
    st.title("📝 内容池")

    # ── 筛选栏 ──
    with st.container():
        fc1, fc2, fc3, fc4 = st.columns(4)
        filter_status = fc1.selectbox(
            "状态",
            ["全部"] + [k for k, _ in STATUS_OPTIONS],
            format_func=lambda x: "全部" if x == "全部" else STATUS_LABELS.get(x, x),
        )
        filter_type = fc2.selectbox(
            "类型",
            ["全部"] + list(TYPE_LABELS.keys()),
            format_func=lambda x: "全部" if x == "全部" else TYPE_LABELS.get(x, x),
        )
        filter_product = fc3.selectbox(
            "产品",
            ["全部"] + list(PRODUCT_LABELS.keys()),
            format_func=lambda x: "全部" if x == "全部" else PRODUCT_LABELS.get(x, x),
        )
        fc4.write("")
        fc4.write("")
        refresh = fc4.button("🔄 刷新")

    # ── 拉取数据 ──
    contents = list_contents(
        status       = None if filter_status == "全部" else filter_status,
        content_type = None if filter_type == "全部" else filter_type,
        product_id   = None if filter_product == "全部" else filter_product,
        limit        = 200,
    )

    st.caption(f"共 {len(contents)} 条内容")

    if not contents:
        st.info("暂无内容。运行 `python main.py post` 等命令生成内容后刷新。")
    else:
        for item in contents:
            status_key = item.get("status", "draft")
            status_label = STATUS_LABELS.get(status_key, status_key)
            type_label = TYPE_LABELS.get(item["content_type"], item["content_type"])
            product_label = PRODUCT_LABELS.get(item["product_id"] or "", item["product_id"] or "-")

            header = f"{type_label}  |  **{item['title'] or '（无标题）'}**  ·  `{status_label}`"

            with st.expander(header, expanded=False):
                # ── 基本信息 ──
                meta_cols = st.columns(4)
                meta_cols[0].caption(f"**产品**\n{product_label}")
                meta_cols[1].caption(f"**学校**\n{item['school_name'] or '-'}")
                meta_cols[2].caption(f"**渠道**\n{item['channel'] or '-'}")
                meta_cols[3].caption(f"**创建**\n{item['created_at'][:16] if item['created_at'] else '-'}")

                # ── 正文 ──
                if item.get("cover_text"):
                    st.markdown(f"**封面文案：** {item['cover_text']}")
                st.markdown("**正文：**")
                st.text_area("", value=item.get("body", ""), height=150, key=f"body_{item['id']}", disabled=True)

                if item.get("hashtags"):
                    st.caption("**标签：** " + " ".join([f"#{t}" for t in item["hashtags"]]))
                if item.get("call_to_action"):
                    st.caption(f"**引导语：** {item['call_to_action']}")
                if item.get("risk_notes"):
                    st.warning("⚠️ 风险提示：" + "；".join(item["risk_notes"]))

                st.divider()

                # ── 操作按钮 ──
                btn_cols = st.columns(5)

                # 一键复制
                copy_text = f"{item.get('title','')}\n\n{item.get('body','')}"
                if item.get("hashtags"):
                    copy_text += "\n\n" + " ".join([f"#{t}" for t in item["hashtags"]])
                btn_cols[0].code(copy_text[:100] + "...", language=None)

                if status_key == "draft":
                    if btn_cols[1].button("📤 提交审核", key=f"submit_{item['id']}"):
                        update_content_status(item["id"], "pending_review")
                        st.rerun()

                if status_key == "pending_review":
                    if btn_cols[1].button("✅ 审核通过", key=f"approve_{item['id']}"):
                        update_content_status(item["id"], "approved")
                        st.rerun()
                    if btn_cols[2].button("🔙 退回修改", key=f"reject_{item['id']}"):
                        update_content_status(item["id"], "draft", comment="退回修改")
                        st.rerun()

                if status_key == "approved":
                    if btn_cols[1].button("🎯 标记已使用", key=f"use_{item['id']}"):
                        update_content_status(item["id"], "used", used_by="销售/运营")
                        st.rerun()

                if status_key not in ("archived",):
                    if btn_cols[4].button("🗑️ 废弃", key=f"archive_{item['id']}"):
                        update_content_status(item["id"], "archived")
                        st.rerun()


# ═══════════════════════════════════════════
# 页面 3：营销日历
# ═══════════════════════════════════════════
elif page == "📅 营销日历":
    st.title("📅 营销日历")

    campaigns = list_campaigns(limit=10)

    if not campaigns:
        st.info("暂无营销计划。运行 `python main.py monthly` 生成月度计划。")
    else:
        for camp in campaigns:
            with st.container():
                st.subheader(f"📌 {camp['name']}")
                cols = st.columns(3)
                cols[0].metric("核心主题", camp.get("core_theme") or "-")
                cols[1].metric("状态", camp.get("status", "-"))
                cols[2].metric("创建时间", (camp.get("created_at") or "")[:10])

                # 该活动下的内容
                related = list_contents(limit=20)
                related = [c for c in related if c.get("campaign_id") == camp["id"]]
                if related:
                    st.caption(f"关联内容：{len(related)} 条")
                    for r in related[:5]:
                        st.markdown(f"- {TYPE_LABELS.get(r['content_type'],r['content_type'])} · {r['title'][:40]} · `{STATUS_LABELS.get(r['status'],r['status'])}`")
                st.divider()


# ═══════════════════════════════════════════
# 页面 4：销售素材库
# ═══════════════════════════════════════════
elif page == "💼 销售素材库":
    st.title("💼 销售素材库")
    st.caption("销售可直接复制使用的话术，支持一键复制和衍生变体")

    # 按产品筛选
    selected_product = st.selectbox(
        "选择产品",
        ["全部"] + list(PRODUCT_LABELS.keys()),
        format_func=lambda x: "全部" if x == "全部" else PRODUCT_LABELS.get(x, x),
    )

    # 只展示已通过/已使用的话术类内容
    scripts = list_contents(
        status       = None,
        product_id   = None if selected_product == "全部" else selected_product,
        limit        = 200,
    )
    scripts = [s for s in scripts if s["status"] in ("approved", "used") and
               s["content_type"] in ("referral_script", "sales_script", "xiaohongshu", "moments", "group_msg")]

    if not scripts:
        st.info("暂无已通过的销售素材。先生成内容并审核通过。")
    else:
        for item in scripts:
            product_label = PRODUCT_LABELS.get(item["product_id"] or "", "-")
            type_label = TYPE_LABELS.get(item["content_type"], item["content_type"])

            with st.expander(f"{type_label}  ·  {product_label}  ·  {item['title'] or '（无标题）'}"):
                body = item.get("body", "")
                st.text_area("内容", value=body, height=120, key=f"script_{item['id']}", disabled=True)

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption("👆 选中上方文本框内容后 Cmd+C 复制")
                with col2:
                    if st.button("✅ 标记已使用", key=f"used_script_{item['id']}"):
                        update_content_status(item["id"], "used", used_by="销售")
                        st.rerun()

        st.divider()
        st.subheader("🤖 生成衍生版本")
        st.info("选择一条素材后，可在终端运行以下命令生成变体：\n```\npython main.py post '话题' <product_id>\n```")


# ═══════════════════════════════════════════
# 页面 5：知识库管理
# ═══════════════════════════════════════════
elif page == "📚 知识库管理":
    st.title("📚 知识库管理")
    st.caption("管理上传到 Dify 的营销资料")

    # Dify 分类结构说明
    with st.expander("📂 Dify 知识库分类规范", expanded=True):
        st.markdown("""
        | 编号 | 知识库名称 | 对应文件 |
        |------|-----------|---------|
        | 01 | 产品知识库 | 产品推荐系统SOP、学年包介绍、包过辅导手册 |
        | 02 | 销售话术库 | 销售手册(dp/学年包/押题)、销售学习合集 |
        | 03 | 客户异议库 | 待上传 |
        | 04 | 营销案例库 | 待上传 |
        | 05 | 小红书风格库 | 待上传 |
        | 06 | 风控表达库 | 待上传 |
        | 07 | 学校节点库 | 待上传 |

        **桌面营销资料文件夹文件分类建议：**
        - `01_产品知识库`：产品推荐系统sop.pdf、学年包系列.html、极致Essay新人培训.html
        - `02_销售话术库`：包过辅导销售手册.html、dp-sales-manual.html、销售学习合集.html、押题产品销售手册.html
        - `09_学生痛点`：极致教育学生痛点分析.pdf
        """)

    # 本地知识文档列表
    docs = list_knowledge_docs()

    if not docs:
        st.info("数据库中暂无知识库记录。上传文件到 Dify 后可在此追踪状态。")

        # 展示桌面文件状态
        st.subheader("📁 待上传文件（桌面营销资料知识库文件夹）")
        desktop_files = [
            ("产品推荐系统sop.pdf", "01_产品知识库", "pdf"),
            ("极致教育学生痛点分析.pdf", "01_产品知识库", "pdf"),
            ("学年包_客户展示页_对外版_v3_final.html", "01_产品知识库", "html"),
            ("学年包_学生一页纸介绍.html", "01_产品知识库", "html"),
            ("学年包_销售手册_对内版_v6.html", "02_销售话术库", "html"),
            ("包过辅导_销售手册_v18.html", "02_销售话术库", "html"),
            ("dp-sales-manual-v4.html", "02_销售话术库", "html"),
            ("dp-client-v2.html", "02_销售话术库", "html"),
            ("押题产品_销售手册_对内版.html", "02_销售话术库", "html"),
            ("押题产品_客户展示页_对外版.html", "02_销售话术库", "html"),
            ("销售学习合集_v2.html", "02_销售话术库", "html"),
            ("极致Essay新人基础认知培训.html", "01_产品知识库", "html"),
            ("学年包_知识测试_v2.html", "02_销售话术库", "html"),
            ("销售部新产品上线流程.docx", "02_销售话术库", "docx"),
        ]

        file_table = []
        for fname, category, ftype in desktop_files:
            fpath = Path.home() / "Desktop" / "营销资料知识库" / fname
            exists = "✅" if fpath.exists() else "❌"
            size = f"{fpath.stat().st_size // 1024}KB" if fpath.exists() else "-"
            file_table.append({
                "文件名": fname, "分类": category,
                "格式": ftype, "大小": size, "状态": exists
            })

        import pandas as pd
        st.dataframe(pd.DataFrame(file_table), use_container_width=True, hide_index=True)

        st.info("💡 提供 Dify API Key 和知识库 ID，我可以帮你通过 API 批量上传所有文件。")

    else:
        # 展示已上传文档
        import pandas as pd
        df = pd.DataFrame(docs)
        st.dataframe(df, use_container_width=True, hide_index=True)
