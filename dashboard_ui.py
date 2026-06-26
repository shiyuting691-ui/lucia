"""
极致教育增长系统 · Dashboard UI 工具库
- inject_css()      全局样式注入
- metric_card()     指标卡
- section_header()  区块标题
- chart_*()         Plotly 图表工厂
"""
import streamlit as st


# ══════════════════════════════════════════════════
# 全局 CSS
# ══════════════════════════════════════════════════
GLOBAL_CSS = """
<style>
/* ── 清除默认 Streamlit 样式 ── */
#MainMenu, footer, header { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1280px; }

/* ── 侧边栏 ── */
[data-testid="stSidebar"] {
    background: #0F172A;
    border-right: 1px solid #1E293B;
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .stRadio > div { gap: 2px; }
[data-testid="stSidebar"] .stRadio label {
    font-size: 13.5px;
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
    display: block;
    width: 100%;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #1E293B; }
[data-testid="stSidebar"] [aria-checked="true"] + label,
[data-testid="stSidebar"] input[type="radio"]:checked ~ label {
    background: #1D4ED8 !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] hr { border-color: #1E293B; }
[data-testid="stSidebar"] .stCaption { color: #475569 !important; font-size: 11px !important; }

/* ── 页面背景 ── */
[data-testid="stAppViewContainer"] > .main { background: #F7F8FA; }

/* ── 顶部品牌栏（Hero 替代） ── */
.page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    padding: 0 0 18px 0;
    border-bottom: 1px solid #E2E8F0;
    margin-bottom: 24px;
}
.page-title {
    font-size: 24px;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.3px;
    margin: 0;
}
.page-subtitle {
    font-size: 13px;
    color: #64748B;
    margin: 4px 0 0 0;
}
.page-badge {
    font-size: 11px;
    padding: 4px 12px;
    border-radius: 20px;
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    white-space: nowrap;
}

/* ── KPI 指标卡 ── */
.kpi-row { display: flex; gap: 14px; margin-bottom: 24px; flex-wrap: wrap; }
.kpi-card {
    flex: 1;
    min-width: 140px;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 18px 20px;
    border-left: 4px solid var(--kpi-color, #2563EB);
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.kpi-label {
    font-size: 12px;
    color: #64748B;
    font-weight: 500;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.kpi-value {
    font-size: 28px;
    font-weight: 700;
    color: #0F172A;
    line-height: 1;
    margin-bottom: 6px;
}
.kpi-delta {
    font-size: 12px;
    color: #10B981;
}
.kpi-delta.down { color: #EF4444; }
.kpi-sub { font-size: 12px; color: #94A3B8; margin-top: 4px; }

/* ── 内容区卡片 ── */
.ui-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 16px;
}
.ui-card-title {
    font-size: 15px;
    font-weight: 600;
    color: #0F172A;
    margin: 0 0 14px 0;
    padding-bottom: 12px;
    border-bottom: 1px solid #F1F5F9;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── 区块标题 ── */
.section-hd {
    font-size: 14px;
    font-weight: 600;
    color: #374151;
    margin: 0 0 12px 0;
    display: flex;
    align-items: center;
    gap: 6px;
}
.section-hd::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #F1F5F9;
    margin-left: 8px;
}

/* ── 数据行 ── */
.data-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #F8FAFC;
    font-size: 13.5px;
}
.data-row:last-child { border: none; }
.data-row-label { color: #374151; }
.data-row-val { font-weight: 600; color: #0F172A; }

/* ── 徽章 ── */
.badge {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 20px;
    font-weight: 500;
}
.badge-blue   { background:#EFF6FF; color:#1D4ED8; }
.badge-green  { background:#F0FDF4; color:#15803D; }
.badge-amber  { background:#FFFBEB; color:#B45309; }
.badge-red    { background:#FEF2F2; color:#B91C1C; }
.badge-gray   { background:#F8FAFC; color:#475569; }

/* ── 流量灯 ── */
.tl-green  { color: #10B981; }
.tl-yellow { color: #F59E0B; }
.tl-red    { color: #EF4444; }
.tl-gray   { color: #94A3B8; }

/* ── 空状态 ── */
.empty-state {
    padding: 32px 20px;
    text-align: center;
    color: #94A3B8;
    font-size: 14px;
}
.empty-icon { font-size: 32px; margin-bottom: 10px; }
.empty-text { color: #64748B; margin-bottom: 6px; }
.empty-hint { font-size: 12px; color: #94A3B8; }

/* ── 任务行 ── */
.task-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: #FAFAFA;
    border-radius: 8px;
    margin-bottom: 6px;
    border: 1px solid #F1F5F9;
}
.task-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.task-title { font-size: 13px; color: #374151; flex: 1; }
.task-dept  { font-size: 11px; color: #94A3B8; }

/* ── Streamlit 原生组件微调 ── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px 18px;
    border-left: 3px solid #2563EB;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 28px !important;
    font-weight: 700 !important;
    color: #0F172A !important;
}
[data-testid="stMetricLabel"] { font-size: 12px !important; color: #64748B !important; }

div[data-testid="column"] { padding: 0 6px; }

.stButton > button {
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    border: 1px solid #E2E8F0;
    color: #374151;
    background: #FFFFFF;
    transition: all 0.15s;
}
.stButton > button:hover {
    border-color: #2563EB;
    color: #2563EB;
    background: #EFF6FF;
}
.stButton > button[kind="primary"] {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: none !important;
}

.stSelectbox > div > div,
.stMultiSelect > div > div {
    border-radius: 8px !important;
    border-color: #E2E8F0 !important;
    font-size: 13px !important;
}

.stTextInput > div > div > input {
    border-radius: 8px !important;
    border-color: #E2E8F0 !important;
    font-size: 13px !important;
}

.stExpander {
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
}

[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

.stAlert { border-radius: 10px; }

.stTabs [data-baseweb="tab-list"] {
    background: #F8FAFC;
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-size: 13px;
    color: #64748B;
}
.stTabs [aria-selected="true"] {
    background: #FFFFFF !important;
    color: #0F172A !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* ── 侧边栏品牌 Logo ── */
.sidebar-brand {
    padding: 16px 0 8px 0;
    margin-bottom: 4px;
}
.sidebar-brand-name {
    font-size: 18px;
    font-weight: 700;
    color: #F1F5F9;
    letter-spacing: -0.3px;
}
.sidebar-brand-sub {
    font-size: 11px;
    color: #475569;
    margin-top: 2px;
}
.sidebar-section-label {
    font-size: 10px;
    color: #475569;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 12px 0 4px 2px;
}

/* ── 图表容器 ── */
.chart-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 16px;
}
.chart-title {
    font-size: 14px;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 4px;
}
.chart-subtitle {
    font-size: 12px;
    color: #94A3B8;
    margin-bottom: 14px;
}

/* ── 旧式 Hero 兼容 ── */
.hero-block { display: none; }
.metric-card { display: none; }
</style>
"""


def inject_css():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# 页面头部
# ══════════════════════════════════════════════════
def page_header(title: str, subtitle: str = "", badge: str = ""):
    badge_html = f'<span class="page-badge">{badge}</span>' if badge else ""
    st.markdown(f"""
    <div class="page-header">
      <div>
        <div class="page-title">{title}</div>
        {"" if not subtitle else f'<div class="page-subtitle">{subtitle}</div>'}
      </div>
      {badge_html}
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# KPI 指标卡（原生 st.metric 增强版）
# ══════════════════════════════════════════════════
COLORS = {
    "blue":   "#2563EB",
    "green":  "#10B981",
    "amber":  "#F59E0B",
    "purple": "#7C3AED",
    "red":    "#EF4444",
    "teal":   "#0D9488",
}

def kpi_card(col, label: str, value, sub: str = "", color: str = "blue", delta: str = ""):
    c = COLORS.get(color, color)
    delta_html = ""
    if delta:
        cls = "down" if delta.startswith("-") else ""
        delta_html = f'<div class="kpi-delta {cls}">{delta}</div>'
    col.markdown(f"""
    <div class="kpi-card" style="--kpi-color:{c}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {delta_html}
      <div class="kpi-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# 区块标题
# ══════════════════════════════════════════════════
def section_header(icon: str, title: str):
    st.markdown(f'<div class="section-hd">{icon} {title}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# 空状态
# ══════════════════════════════════════════════════
def empty_state(icon: str, text: str, hint: str = ""):
    st.markdown(f"""
    <div class="empty-state">
      <div class="empty-icon">{icon}</div>
      <div class="empty-text">{text}</div>
      {"" if not hint else f'<div class="empty-hint">{hint}</div>'}
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════
# Plotly 图表工厂（统一主题）
# ══════════════════════════════════════════════════
PLOTLY_LAYOUT = dict(
    font_family="Inter, -apple-system, sans-serif",
    font_color="#374151",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=8, r=8, t=8, b=8),
    hoverlabel=dict(
        bgcolor="#FFFFFF",
        bordercolor="#E2E8F0",
        font_size=12,
        font_color="#0F172A",
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font_size=12,
    ),
    colorway=["#2563EB", "#10B981", "#F59E0B", "#7C3AED", "#EF4444", "#0D9488"],
)

def _apply_axes(fig):
    fig.update_xaxes(
        showgrid=False,
        showline=False,
        tickfont=dict(size=11, color="#94A3B8"),
        tickcolor="#E2E8F0",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#F1F5F9",
        gridwidth=1,
        showline=False,
        tickfont=dict(size=11, color="#94A3B8"),
        zeroline=False,
    )
    return fig


def chart_bar_horizontal(df, x_col, y_col, title="", color="#2563EB", height=280):
    """水平条形图（排行榜）"""
    try:
        import plotly.graph_objects as go
        fig = go.Figure(go.Bar(
            x=df[x_col], y=df[y_col], orientation="h",
            marker_color=color,
            marker_line_width=0,
            text=[f"{v:,.0f}" for v in df[x_col]],
            textposition="outside",
            textfont=dict(size=11, color="#374151"),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=height,
                          yaxis=dict(autorange="reversed", tickfont=dict(size=12)))
        _apply_axes(fig)
        fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9")
        fig.update_yaxes(showgrid=False)
        return fig
    except Exception:
        return None


def chart_bar_grouped(df, x_col, y_cols, names, title="", height=260):
    """分组条形图"""
    try:
        import plotly.graph_objects as go
        colors = ["#2563EB", "#10B981", "#F59E0B", "#7C3AED"]
        fig = go.Figure()
        for i, (col, name) in enumerate(zip(y_cols, names)):
            fig.add_trace(go.Bar(
                x=df[x_col], y=df[col], name=name,
                marker_color=colors[i % len(colors)],
                marker_line_width=0,
            ))
        fig.update_layout(**PLOTLY_LAYOUT, height=height,
                          barmode="group", bargap=0.25, bargroupgap=0.05)
        _apply_axes(fig)
        return fig
    except Exception:
        return None


def chart_line(df, x_col, y_cols, names, title="", height=240, fill=True):
    """折线图（支持多条线，可填充）"""
    try:
        import plotly.graph_objects as go
        colors = ["#2563EB", "#10B981", "#F59E0B"]
        fig = go.Figure()
        for i, (col, name) in enumerate(zip(y_cols, names)):
            fig.add_trace(go.Scatter(
                x=df[x_col], y=df[col], name=name, mode="lines+markers",
                line=dict(color=colors[i % len(colors)], width=2.5),
                marker=dict(size=5, color=colors[i % len(colors)]),
                fill="tozeroy" if (fill and i == 0) else "none",
                fillcolor=f"rgba(37,99,235,0.06)" if i == 0 else "none",
            ))
        fig.update_layout(**PLOTLY_LAYOUT, height=height)
        _apply_axes(fig)
        return fig
    except Exception:
        return None


def chart_donut(labels, values, title="", height=220):
    """环形图"""
    try:
        import plotly.graph_objects as go
        colors = ["#2563EB", "#10B981", "#F59E0B", "#7C3AED", "#EF4444", "#0D9488", "#F97316"]
        fig = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.55,
            marker=dict(colors=colors[:len(values)], line=dict(color="#FFFFFF", width=2)),
            textinfo="percent",
            textfont=dict(size=11),
            hovertemplate="%{label}: %{value:,.0f}<extra></extra>",
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=height,
                          showlegend=True,
                          legend=dict(orientation="v", x=1.05, y=0.5,
                                      font_size=11, itemsizing="constant"))
        return fig
    except Exception:
        return None


def chart_heatmap(df, title="", height=300):
    """热力图（DataFrame，index=y轴，columns=x轴）"""
    try:
        import plotly.graph_objects as go
        import numpy as np
        z = df.values
        fig = go.Figure(go.Heatmap(
            z=z, x=list(df.columns), y=list(df.index),
            colorscale=[[0, "#EFF6FF"], [0.5, "#93C5FD"], [1, "#1D4ED8"]],
            showscale=True,
            text=z, texttemplate="%{text}",
            textfont=dict(size=10),
            hovertemplate="%{y} × %{x}: %{z}<extra></extra>",
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=height)
        fig.update_xaxes(tickfont=dict(size=10))
        fig.update_yaxes(tickfont=dict(size=10))
        return fig
    except Exception:
        return None


def render_chart(fig, use_container_width=True):
    """统一渲染 Plotly 图表"""
    if fig:
        st.plotly_chart(fig, use_container_width=use_container_width,
                        config={"displayModeBar": False})
    else:
        st.caption("图表数据不足，暂无法渲染")
