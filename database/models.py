"""
数据库模型 — SQLAlchemy ORM
本地开发使用 SQLite，生产可无缝迁移到 PostgreSQL / Supabase
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, JSON, ForeignKey, Enum as SAEnum, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# 便于外部 import
__all__ = [
    "Base", "Product", "School", "Campaign", "Content",
    "Task", "KnowledgeDoc", "DepartmentFeedback", "StrategySuggestion",
    "ContentUsage", "WorkflowRun",
    "Order", "Lead", "SchoolCalendar", "MarketSignal", "YearlyPattern",
    "TeacherCapacity", "OrderRiskSignal",
    "CompanyFact", "BusinessDictionaryTerm",
    "SchoolScore", "SchoolStrategyCard",
    "AgentRun", "AgentFeedback",
]


# ─────────────────────────────────────────
# Workflow 运行日志表
# ─────────────────────────────────────────
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    workflow_name        = Column(String(100), nullable=False)
    status               = Column(String(30), default="running")
    # running / success / partial_success / failed
    trigger              = Column(String(50), default="manual")  # manual / scheduler / api
    started_at           = Column(DateTime, default=datetime.utcnow)
    finished_at          = Column(DateTime)
    duration_seconds     = Column(Float)
    steps_run            = Column(JSON)     # [{"step": "BusinessContextAgent", "status": "ok", "records": 0}]
    error_message        = Column(Text)
    created_records_count= Column(Integer, default=0)
    summary              = Column(Text)     # 简报文字，用于企业微信推送


# ─────────────────────────────────────────
# 产品表
# ─────────────────────────────────────────
class Product(Base):
    __tablename__ = "products"

    id          = Column(String(50), primary_key=True)   # e.g. "annual_package"
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    price_range = Column(String(100))
    target      = Column(Text)
    selling_points = Column(JSON)                        # list of strings
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contents    = relationship("Content", back_populates="product_rel", foreign_keys="Content.product_id")


# ─────────────────────────────────────────
# 学校表
# ─────────────────────────────────────────
class School(Base):
    __tablename__ = "schools"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(50), nullable=False, unique=True)   # e.g. "UCL"
    full_name       = Column(String(100))
    country         = Column(String(20))    # "UK" / "Australia"
    popular_majors  = Column(JSON)
    exam_period     = Column(JSON)          # e.g. ["1月", "5月-6月"]
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 营销活动表
# ─────────────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(200), nullable=False)
    campaign_type   = Column(String(50))    # "monthly_plan" / "weekly_plan" / "seasonal"
    period_start    = Column(DateTime)
    period_end      = Column(DateTime)
    core_theme      = Column(String(200))
    core_goal       = Column(Text)
    target_country  = Column(String(20))
    status          = Column(String(30), default="active")  # active / completed / archived
    plan_data       = Column(JSON)          # 完整计划 JSON
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contents        = relationship("Content", back_populates="campaign")


# ─────────────────────────────────────────
# 内容表（核心表）
# ─────────────────────────────────────────
CONTENT_STATUS = ("draft", "pending_review", "approved", "used", "reviewed", "archived")
CONTENT_TYPES  = ("xiaohongshu", "moments", "group_msg", "referral_script",
                  "sales_script", "monthly_plan", "weekly_plan", "poster")

class Content(Base):
    __tablename__ = "contents"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    title           = Column(String(200))
    content_type    = Column(SAEnum(*CONTENT_TYPES, name="content_type_enum"), nullable=False)
    target_user     = Column(String(100))
    product_id      = Column(String(50), ForeignKey("products.id"))
    school_name     = Column(String(50))        # 冗余存储，方便查询
    channel         = Column(String(50))        # xiaohongshu / wechat / group / referral
    target_country  = Column(String(20))        # UK / Australia / All
    campaign_id     = Column(Integer, ForeignKey("campaigns.id"), nullable=True)

    # 内容正文
    body            = Column(Text)
    cover_text      = Column(String(200))       # 封面文案（小红书）
    hashtags        = Column(JSON)              # ["#留学辅导", "#UCL"]
    call_to_action  = Column(Text)

    # 状态管理
    status          = Column(SAEnum(*CONTENT_STATUS, name="content_status_enum"),
                             default="draft", nullable=False)
    risk_notes      = Column(JSON)              # ["可能违规：承诺过度"]
    suggested_use   = Column(Text)              # 建议使用场景
    review_comment  = Column(Text)              # 审核备注

    # 使用跟踪
    used_by         = Column(String(100))       # 谁使用了
    used_at         = Column(DateTime)
    post_timing     = Column(String(50))        # 建议发布时间
    urgency         = Column(String(20))        # 紧急度

    # 元数据
    raw_output      = Column(JSON)              # Agent 原始输出
    market_period   = Column(String(100))       # "UK dissertation season"
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_rel     = relationship("Product", back_populates="contents", foreign_keys=[product_id])
    campaign        = relationship("Campaign", back_populates="contents")


# ─────────────────────────────────────────
# 执行任务表（V2 升级版）
# ─────────────────────────────────────────
TASK_STATUS = ("todo", "doing", "done", "blocked", "cancelled")
TASK_TYPES  = ("内容发布", "销售跟进", "产品优化", "后端反馈",
               "风控审核", "管理层决策", "数据复盘", "客户跟进")

class Task(Base):
    __tablename__ = "tasks"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    title               = Column(String(200), nullable=False)
    description         = Column(Text)
    task_type           = Column(String(50))
    department          = Column(String(50))        # 市场部/销售部/产品部/学管部/管理层
    owner               = Column(String(100))       # 负责人
    priority            = Column(String(20), default="中")  # 低/中/高/紧急
    task_source         = Column(String(50))        # AI生成/手动/系统调度
    related_product     = Column(String(100))
    related_school      = Column(String(100))
    related_content_id  = Column(Integer, ForeignKey("contents.id"), nullable=True)
    related_campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    expected_output     = Column(Text)
    due_date            = Column(DateTime)
    status              = Column(String(20), default="todo")
    notes               = Column(Text)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at        = Column(DateTime)


# ─────────────────────────────────────────
# 内容使用记录表
# ─────────────────────────────────────────
class ContentUsage(Base):
    __tablename__ = "content_usage"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    content_id      = Column(Integer, ForeignKey("contents.id"), nullable=False)
    used_by         = Column(String(100))
    department      = Column(String(50))
    channel         = Column(String(50))        # 私聊/朋友圈/小红书/社群/企业微信/电话/转介绍
    usage_context   = Column(Text)              # 使用场景描述
    customer_stage  = Column(String(50))        # 初次接触/已报价/跟进中/已成交/流失
    result          = Column(String(50), default="未知")
    # 未知/已发送/客户已回复/产生咨询/已报价/已成交/无效/需优化
    feedback        = Column(Text)              # 主观反馈
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 知识资料表
# ─────────────────────────────────────────
class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    file_name        = Column(String(200), nullable=False)
    category         = Column(String(50))    # "产品知识库" / "销售话术库" 等
    dify_category    = Column(String(50))    # Dify 知识库分类编号
    file_path        = Column(String(500))
    file_type        = Column(String(20))    # md / pdf / docx / txt
    file_size        = Column(Integer)       # bytes
    related_products = Column(JSON)          # ["annual_package", "guaranteed"]
    related_schools  = Column(JSON)
    related_scenarios= Column(JSON)          # ["考前4周", "价格异议"] — 适用场景
    keywords         = Column(JSON)          # 提取的关键词列表
    summary          = Column(Text)          # AI 生成的短摘要（150-300字）
    summary_at       = Column(DateTime)      # 摘要生成时间
    is_enabled       = Column(Boolean, default=True)
    is_expired       = Column(Boolean, default=False)
    dify_doc_id      = Column(String(100))
    dify_dataset_id  = Column(String(100))
    last_synced_at   = Column(DateTime)
    expires_at       = Column(DateTime)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# 部门反馈表
# ─────────────────────────────────────────
FEEDBACK_TYPES = (
    "产品问题", "销售异议", "客户需求变化", "后端交付风险",
    "老师资源紧张", "学校课程难度变化", "价格问题", "售后问题", "其他"
)
URGENCY_LEVELS = ("低", "中", "高", "紧急")
FEEDBACK_STATUS = ("open", "in_progress", "resolved", "closed")

class DepartmentFeedback(Base):
    __tablename__ = "department_feedback"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    department      = Column(String(50), nullable=False)  # 市场部/销售部/产品部/学管部/管理层
    feedback_type   = Column(String(50))
    related_product = Column(String(100))
    related_school  = Column(String(100))
    title           = Column(String(200), nullable=False)
    content         = Column(Text)
    urgency         = Column(String(20), default="中")
    status          = Column(String(30), default="open")
    created_by      = Column(String(100))
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# 战略建议表
# ─────────────────────────────────────────
SUGGESTION_TYPES = (
    "产品优化", "市场机会", "销售策略", "推广策略",
    "风控提醒", "资源配置", "新产品机会"
)
SUGGESTION_PRIORITY = ("低", "中", "高", "紧急")
SUGGESTION_STATUS = ("new", "under_review", "adopted", "rejected", "archived")

class StrategySuggestion(Base):
    __tablename__ = "strategy_suggestions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    title           = Column(String(200), nullable=False)
    suggestion_type = Column(String(50))
    related_product = Column(String(100))
    related_country = Column(String(50))
    related_school  = Column(String(100))
    insight         = Column(Text)          # 洞察/背景
    recommendation  = Column(Text)          # 具体建议动作
    content         = Column(Text)          # 完整内容（月度策略/周度建议等长文本）
    data_basis      = Column(JSON)          # 生成时的数据依据
    priority        = Column(String(20), default="中")
    status          = Column(String(30), default="new")
    source          = Column(String(100))   # "AI生成" / "管理层" / "销售反馈"
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# 订单表
# ─────────────────────────────────────────
ORDER_STATUS = ("pending", "confirmed", "in_progress", "completed", "refunded", "cancelled")

class Order(Base):
    __tablename__ = "orders"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    order_date    = Column(DateTime)
    customer_id   = Column(String(100))
    school        = Column(String(100))
    country       = Column(String(20))     # UK / Australia / All
    major         = Column(String(100))
    course_code   = Column(String(50))
    product       = Column(String(100))    # 对应 products.id
    service_type  = Column(String(50))     # 一对一/小班/论文
    deadline      = Column(DateTime)
    amount        = Column(Float)
    sales_owner   = Column(String(100))
    status        = Column(String(30), default="confirmed")
    source_file   = Column(String(200))    # 来源文件（导入追踪）
    created_at    = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 咨询/线索表
# ─────────────────────────────────────────
DEAL_STATUS = ("new", "contacted", "quoted", "follow_up", "won", "lost", "inactive")

class Lead(Base):
    __tablename__ = "leads"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    inquiry_date    = Column(DateTime)
    customer_name   = Column(String(100))
    school          = Column(String(100))
    country         = Column(String(20))
    major           = Column(String(100))
    course_code     = Column(String(50))
    product_interest= Column(String(100))
    pain_point      = Column(Text)
    deadline        = Column(DateTime)
    quoted_price    = Column(Float)
    deal_status     = Column(String(30), default="new")
    lost_reason     = Column(Text)
    sales_owner     = Column(String(100))
    source_channel  = Column(String(50))   # 小红书/朋友圈/转介绍/社群/直接联系
    source_file     = Column(String(200))
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 学校节点表
# ─────────────────────────────────────────
CALENDAR_EVENT_TYPES = (
    "开学", "作业高峰", "Midterm", "Final", "Dissertation",
    "补考", "AI风险高发期", "新生入学", "选课",
)
CALENDAR_CONFIDENCE = ("high", "medium", "low")

class SchoolCalendar(Base):
    __tablename__ = "school_calendar"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    school        = Column(String(100), nullable=False)
    country       = Column(String(20))
    academic_year = Column(String(20))     # e.g. "2025-2026"
    term          = Column(String(50))     # "Semester 1" / "Term 1" / "全年"
    event_type    = Column(String(50))
    event_name    = Column(String(200))
    start_date    = Column(DateTime)
    end_date      = Column(DateTime)
    confidence    = Column(String(20), default="medium")   # high/medium/low
    source        = Column(String(100))    # "官方日历" / "历史推断" / "人工录入"
    notes         = Column(Text)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# 市场信号表
# ─────────────────────────────────────────
SIGNAL_TYPES = (
    "咨询量上升", "订单量上升", "DDL集中", "产品转化下降",
    "学校需求升温", "AI问题高发", "价格异议增加", "后端交付风险增加",
)

class MarketSignal(Base):
    __tablename__ = "market_signals"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    signal_date      = Column(DateTime, default=datetime.utcnow)
    country          = Column(String(20))
    school           = Column(String(100))
    product          = Column(String(100))
    signal_type      = Column(String(50))
    signal_value     = Column(Float)       # 数值（咨询量、订单数等）
    trend            = Column(String(20))  # up / down / stable
    evidence         = Column(Text)        # 支撑证据描述
    priority         = Column(String(20), default="中")   # 低/中/高/紧急
    suggested_action = Column(Text)
    created_at       = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 往年规律表
# ─────────────────────────────────────────
# ─────────────────────────────────────────
# 老师储备容量表（新增）
# ─────────────────────────────────────────
class TeacherCapacity(Base):
    __tablename__ = "teacher_capacity"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    subject_area     = Column(String(100))   # 商科/金融/管理/经济/会计/计算机/数据分析/工程/社科/教育/法律
    course_type      = Column(String(50))    # Final/Dissertation/Essay/Report/Quiz/Exam/学年包/保过辅导
    country          = Column(String(50))    # UK/Australia/All
    school_experience= Column(Text)          # 有经验的学校列表
    available_slots  = Column(Integer, default=0)
    current_load     = Column(Integer, default=0)
    max_capacity     = Column(Integer, default=10)
    capacity_status  = Column(String(20), default="正常")  # 充足/正常/紧张/暂停接单
    risk_level       = Column(String(20), default="low")   # low/medium/high/critical
    notes            = Column(Text)
    updated_at       = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 订单风险信号表（新增）
# ─────────────────────────────────────────
class OrderRiskSignal(Base):
    __tablename__ = "order_risk_signals"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    signal_date     = Column(DateTime, default=datetime.utcnow)
    product         = Column(String(100))
    country         = Column(String(50))
    school          = Column(String(200))
    subject_area    = Column(String(100))
    course_code     = Column(String(200))
    risk_type       = Column(String(100))   # DDL过近/老师资源紧张/课程难度高/...
    risk_level      = Column(String(20))    # low/medium/high/critical
    evidence        = Column(Text)
    suggested_action= Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)


class YearlyPattern(Base):
    __tablename__ = "yearly_patterns"

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    country                  = Column(String(20))
    school                   = Column(String(100))
    product                  = Column(String(100))
    period_start             = Column(String(10))   # "MM-DD" 格式，跨年复用
    period_end               = Column(String(10))   # "MM-DD"
    pattern_summary          = Column(Text)
    historical_volume        = Column(Integer)       # 往年同期订单量
    conversion_rate          = Column(Float)         # 往年同期转化率
    recommended_lead_time_days = Column(Integer, default=14)
    suggested_campaign       = Column(Text)          # 建议营销活动
    created_at               = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 公司事实表 — 所有业务事实必须追溯到此
# ─────────────────────────────────────────
FACT_TYPES = (
    "公司基础事实", "部门事实", "产品事实", "销售事实",
    "风控事实", "学管事实", "老师资源事实", "订单数据事实",
    "客户异议事实", "内容风格事实", "禁用表达事实",
)

class CompanyFact(Base):
    __tablename__ = "company_facts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    fact_type      = Column(String(50), nullable=False)   # 见 FACT_TYPES
    title          = Column(String(200), nullable=False)  # 事实摘要标题
    content        = Column(Text, nullable=False)         # 事实完整内容
    source_file    = Column(String(500))                  # 来源文件路径
    source_section = Column(String(200))                  # 来源章节/段落
    confidence     = Column(String(20), default="medium") # high/medium/low
    is_active      = Column(Boolean, default=False)       # 必须人工确认后才为 True
    review_status  = Column(String(30), default="pending")
    # pending / confirmed / modified / rejected / inaccurate
    review_note    = Column(Text)                         # 人工修改备注
    extracted_by   = Column(String(100), default="FactExtractionAgent")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# 业务词典表 — 标准词 / 别名 / 禁用词
# ─────────────────────────────────────────
TERM_TYPES = (
    "部门名称", "产品名称", "服务类型", "客户类型",
    "风控词", "渠道名称", "学校名称",
)

# ─────────────────────────────────────────
# 学校机会评分表 — 内部数据驱动，不允许编造学校节点
# ─────────────────────────────────────────
PRIORITY_LEVELS = ("S", "A", "B", "C", "低机会", "Unknown")
SCHOOL_STAGES = (
    "开学准备期", "Assessment高峰期", "Final冲刺期",
    "Dissertation高峰期", "补考/挂科风险期", "低需求维护期", "资料不足",
)
DEMAND_HEATS = ("high", "medium", "low", "unknown")

class SchoolScore(Base):
    __tablename__ = "school_scores"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    school_name       = Column(String(100), nullable=False)  # 标准学校名
    country           = Column(String(20))
    opportunity_score = Column(Integer, default=0)           # 0-100
    priority_level    = Column(String(10), default="Unknown") # 见 PRIORITY_LEVELS
    current_stage     = Column(String(30), default="资料不足") # 见 SCHOOL_STAGES
    demand_heat       = Column(String(10), default="unknown") # 见 DEMAND_HEATS
    hot_products      = Column(JSON, default=list)            # 最值得推的产品
    score_reason      = Column(JSON, default=list)            # 每项得分的依据
    internal_evidence = Column(JSON, default=list)            # 内部数据依据
    risk_notes        = Column(JSON, default=list)
    missing_data      = Column(JSON, default=list)            # 缺失信息清单
    last_scored_at    = Column(DateTime, default=datetime.utcnow)
    created_at        = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 学校策略卡表 — 短卡，每个判断必须带 data_evidence
# ─────────────────────────────────────────
class SchoolStrategyCard(Base):
    __tablename__ = "school_strategy_cards"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    school_name         = Column(String(100), nullable=False)
    country             = Column(String(20))
    period              = Column(String(10), default="weekly")  # weekly / monthly
    priority_level      = Column(String(10))
    current_stage       = Column(String(30))
    demand_heat         = Column(String(10))
    main_product        = Column(String(100))                   # P0 主推
    secondary_products  = Column(JSON, default=list)            # P1 次推
    cautious_products   = Column(JSON, default=list)            # 谨慎推广
    paused_products     = Column(JSON, default=list)            # 暂停强推
    why_this_strategy   = Column(JSON, default=list)
    marketing_suggestions    = Column(JSON, default=list)       # 推广部：小红书/朋友圈/社群/海报
    sales_suggestions        = Column(JSON, default=list)       # 顾问：跟进/话术/节奏/异议
    academic_support_notes   = Column(JSON, default=list)       # 学管提醒
    backend_support_notes    = Column(JSON, default=list)       # 后台支持
    risk_notes          = Column(JSON, default=list)
    suggested_materials = Column(JSON, default=list)
    next_7d_prediction  = Column(Text)
    next_14d_prediction = Column(Text)
    next_30d_prediction = Column(Text)
    data_evidence       = Column(JSON, default=list)
    confidence          = Column(String(10), default="low")     # high/medium/low
    created_at          = Column(DateTime, default=datetime.utcnow)


class BusinessDictionaryTerm(Base):
    __tablename__ = "business_dictionary"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    term_type      = Column(String(50), nullable=False)   # 见 TERM_TYPES
    standard_term  = Column(String(100), nullable=False)  # 唯一标准词
    aliases        = Column(JSON, default=list)           # ["销售", "客户顾问"]
    forbidden_terms= Column(JSON, default=list)           # ["销售部"]
    description    = Column(Text)                         # 职责/定义说明
    source_file    = Column(String(500))                  # 来源文件
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# Agent 运行日志表（V8）— 每次 Agent 运行必须记录
# ─────────────────────────────────────────
AGENT_RUN_STATUSES = ("success", "failed", "skipped", "blocked")

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    workflow_name    = Column(String(100))
    agent_name       = Column(String(100), nullable=False)
    agent_layer      = Column(String(30))
    run_id           = Column(String(50))                  # 同一workflow run共享
    status           = Column(String(20), nullable=False)  # 见 AGENT_RUN_STATUSES
    input_summary    = Column(Text)
    output_summary   = Column(Text)
    error_message    = Column(Text)                        # 错误不允许静默吞掉
    tokens_used      = Column(Integer, default=0)
    cost_estimate    = Column(Float, default=0.0)          # USD
    duration_seconds = Column(Float, default=0.0)
    started_at       = Column(DateTime)
    finished_at      = Column(DateTime)
    created_at       = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# Agent 输出质量反馈表（V8）— 人工评分，用于优化 prompt
# ─────────────────────────────────────────
class AgentFeedback(Base):
    __tablename__ = "agent_feedbacks"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    agent_run_id        = Column(Integer)
    agent_name          = Column(String(100), nullable=False)
    feedback_user       = Column(String(50))
    usefulness_score    = Column(Integer)   # 1-5
    accuracy_score      = Column(Integer)   # 1-5
    actionability_score = Column(Integer)   # 1-5
    hallucination_flag  = Column(Boolean, default=False)
    feedback_text       = Column(Text)
    created_at          = Column(DateTime, default=datetime.utcnow)
