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
    "OpportunityScore", "LeadScore", "CampaignPrediction", "WeeklyReview",
    "AttributionSnapshot",
    "ChannelPerformance", "RoleExecutionMetrics",
    # Phase 2（旧）
    "ChannelContentRecommendation", "TimeWindowForecast",
    # Phase 2 v2（统一表名 + 新表）
    "ContentStrategyRecommendation", "ChannelContent", "WeeklyGrowthBrief",
    "CourseAssessment",
    # Phase 3 需求预测三层体系
    "SchoolAcademicCalendar", "CourseAssessmentV2", "MajorDemandProfile",
    "DemandForecastSignal", "DataSourceRegistry",
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
TASK_STATUS = ("todo", "doing", "done", "delayed", "blocked", "cancelled")
TASK_TYPES  = ("内容发布", "顾问跟进", "后台维护", "学管反馈",
               "风控审核", "管理层决策", "数据复盘", "客户跟进")

class Task(Base):
    __tablename__ = "tasks"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    title               = Column(String(200), nullable=False)
    description         = Column(Text)
    task_type           = Column(String(50))
    department          = Column(String(50))        # 推广部/顾问/学管/后台/管理层
    owner               = Column(String(100))       # 负责人
    priority            = Column(String(20), default="中")  # 低/中/高/紧急
    task_source         = Column(String(50))        # AI生成/手动/系统调度
    related_product     = Column(String(100))
    related_school      = Column(String(100))
    related_content_id  = Column(Integer, ForeignKey("contents.id"), nullable=True)
    related_campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    strategy_id         = Column(Integer, nullable=True)    # 关联 opportunity_scores.id
    expected_output     = Column(Text)
    due_date            = Column(DateTime)
    status              = Column(String(20), default="todo")  # 见 TASK_STATUS
    completion_result   = Column(Text)              # 完成时填写：实际产出/结果
    blockers            = Column(Text)              # blocked/delayed 时填写：阻碍原因
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
    "后台问题", "顾问异议", "客户需求变化", "学管交付风险",
    "老师资源紧张", "学校课程难度变化", "价格问题", "售后问题", "其他"
)
URGENCY_LEVELS = ("低", "中", "高", "紧急")
FEEDBACK_STATUS = ("open", "in_progress", "resolved", "closed")

class DepartmentFeedback(Base):
    __tablename__ = "department_feedback"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    department      = Column(String(50), nullable=False)  # 推广部/顾问/学管/后台/管理层
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
    "后台维护", "增长机会", "顾问策略", "推广策略",
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
    # CRM 同步字段
    crm_id        = Column(String(50), nullable=True, index=True)
    crm_source    = Column(String(20), nullable=True)
    crm_updated_at= Column(String(30), nullable=True)


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
    # V11 渠道-角色归因字段
    lead_source_channel = Column(String(50))    # 规范渠道值：见 VALID_CHANNELS
    lead_source_detail  = Column(String(200))   # 渠道补充说明
    content_id          = Column(Integer, ForeignKey("contents.id"), nullable=True)
    campaign_id         = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    source_owner_role   = Column(String(50))    # 产生线索的角色：promotion_team/xueguan/consultant
    source_owner_name   = Column(String(100))   # 产生线索的人员名
    assigned_role       = Column(String(50))    # 当前承接角色：xueguan/consultant
    assigned_person     = Column(String(100))   # 当前承接人员名
    customer_stage      = Column(String(50))    # 初次接触/已报价/跟进中/已成交/流失
    followup_status     = Column(String(30))    # pending/in_progress/overdue/done
    last_followup_time  = Column(DateTime)
    next_followup_time  = Column(DateTime)
    deal_amount         = Column(Float)         # 成交金额（won 后填写）
    risk_flag           = Column(Boolean, default=False)
    risk_reason         = Column(Text)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # CRM 同步字段
    crm_id          = Column(String(50), nullable=True, index=True)   # 伙伴云 item_id
    crm_source      = Column(String(20), nullable=True)               # 来源系统：huoban
    crm_updated_at  = Column(String(30), nullable=True)               # CRM 侧最后更新时间


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
    "学校需求升温", "AI问题高发", "价格异议增加", "学管交付风险增加",
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


# ─────────────────────────────────────────
# 机会评分汇总表 — 统一存 school/product/lead/campaign 四类评分
# ─────────────────────────────────────────
OPPORTUNITY_TYPES = ("school", "product", "lead", "campaign")
OPPORTUNITY_LEVELS = ("S", "A", "B", "C", "低机会", "Unknown")
TRAFFIC_LIGHT = ("green", "yellow", "red", "gray")

class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    score_type      = Column(String(20), nullable=False)    # 见 OPPORTUNITY_TYPES
    entity_name     = Column(String(100), nullable=False)   # 学校名 / 产品名 / lead_id / 活动名
    entity_id       = Column(String(100))                   # 对应原表 id（可选）
    score           = Column(Integer, default=0)            # 0-100
    level           = Column(String(20), default="Unknown") # 见 OPPORTUNITY_LEVELS
    traffic_light   = Column(String(10), default="gray")    # 见 TRAFFIC_LIGHT
    score_breakdown = Column(JSON, default=dict)            # {"维度": 分数}
    score_reason    = Column(JSON, default=list)            # 评分依据列表
    risk_flags      = Column(JSON, default=list)            # 风险标记
    recommendation  = Column(Text)                          # 一句话行动建议
    data_anchored   = Column(Boolean, default=False)        # 是否为历史同期锚定
    anchor_note     = Column(String(200))                   # 锚定说明
    scored_at       = Column(DateTime, default=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 线索机会评分表 — 纯规则，标记高价值待跟进线索
# ─────────────────────────────────────────
class LeadScore(Base):
    __tablename__ = "lead_scores"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    lead_id         = Column(Integer, nullable=False)       # 对应 leads.id
    customer_name   = Column(String(100))
    school          = Column(String(100))
    product_interest= Column(String(100))
    score           = Column(Integer, default=0)            # 0-100
    level           = Column(String(20), default="Unknown") # S/A/B/C/低机会
    score_reason    = Column(JSON, default=list)
    urgent_flags    = Column(JSON, default=list)            # ["DDL≤7天", "热门学校"]
    suggested_action= Column(Text)                          # 建议顾问跟进动作
    scored_at       = Column(DateTime, default=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 广告预测表 — 每次预测一条，带置信区间，不给单点预测
# ─────────────────────────────────────────
PREDICTION_BASIS = ("historical_data", "rule_only", "insufficient_data")

class CampaignPrediction(Base):
    __tablename__ = "campaign_predictions"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    prediction_week     = Column(String(10), nullable=False)    # "2026-06-09"
    school              = Column(String(100))
    product             = Column(String(100))
    channel             = Column(String(50))                    # 小红书/朋友圈/社群/转介绍
    hook_theme          = Column(String(200))                   # 推广钩子/主题（Claude生成）
    predicted_leads_low = Column(Integer, default=0)            # 区间下限
    predicted_leads_high= Column(Integer, default=0)            # 区间上限
    confidence          = Column(String(10), default="low")     # high/medium/low
    confidence_note     = Column(Text)                          # 置信度说明
    basis               = Column(String(30), default="rule_only")  # 见 PREDICTION_BASIS
    school_score        = Column(Integer)                       # 引用 school_scores.score
    product_score       = Column(Integer)                       # 引用 opportunity_scores.score
    historical_leads    = Column(Integer)                       # 同期历史咨询量
    rationale           = Column(Text)                          # Claude 撰写的推理
    created_at          = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 周复盘表 — 预测 vs 实际对比 + 执行完成度分析
# ─────────────────────────────────────────
class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    review_week             = Column(String(10), nullable=False)    # "2026-06-09"
    total_leads_predicted   = Column(Integer, default=0)
    total_leads_actual      = Column(Integer, default=0)
    total_orders_predicted  = Column(Integer, default=0)
    total_orders_actual     = Column(Integer, default=0)
    school_breakdown        = Column(JSON, default=list)    # [{school, pred, actual, diff}]
    product_breakdown       = Column(JSON, default=list)
    tasks_total             = Column(Integer, default=0)
    tasks_done              = Column(Integer, default=0)
    tasks_delayed           = Column(Integer, default=0)
    tasks_blocked           = Column(Integer, default=0)
    dept_completion         = Column(JSON, default=dict)    # {dept: {total, done, rate}}
    key_wins                = Column(JSON, default=list)    # 本周亮点
    key_misses              = Column(JSON, default=list)    # 本周落差
    root_causes             = Column(JSON, default=list)    # 归因分析
    next_week_focus         = Column(JSON, default=list)    # 下周重点
    review_summary          = Column(Text)                  # Claude 生成的复盘叙述
    generated_by            = Column(String(50), default="WeeklyReviewAgent")
    created_at              = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 归因快照表 — 渠道/顾问/产品/时效归因分析结果
# ─────────────────────────────────────────
class AttributionSnapshot(Base):
    __tablename__ = "attribution_snapshots"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date    = Column(String(10), nullable=False)   # "2026-06-13"
    period_start     = Column(String(10))                   # 分析区间起点
    period_end       = Column(String(10))                   # 分析区间终点

    # 渠道归因 — [{channel, lead_count, order_count, revenue, cvr, avg_days}]
    channel_data     = Column(JSON, default=list)
    # 顾问归因 — [{advisor, order_count, gmv, avg_amount, top_product, top_school}]
    advisor_data     = Column(JSON, default=list)
    # 产品-学校矩阵 — [{product, school, order_count, revenue, avg_amount}]
    product_school_data = Column(JSON, default=list)
    # 时效归因 — [{channel/advisor, avg_days_to_close, median_days}]
    speed_data       = Column(JSON, default=list)

    # Claude 生成的 3 条关键洞察（注入策略卡）
    key_insights     = Column(JSON, default=list)
    # 给下周推广的建议（直接推送企微）
    action_items     = Column(JSON, default=list)

    order_count      = Column(Integer, default=0)   # 分析区间订单总数
    lead_count       = Column(Integer, default=0)   # 分析区间线索总数
    total_revenue    = Column(Float, default=0.0)

    generated_by     = Column(String(50), default="AttributionAnalysisAgent")
    created_at       = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 渠道表现汇总表
# ─────────────────────────────────────────
class ChannelPerformance(Base):
    __tablename__ = "channel_performance"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    period                = Column(String(20), nullable=False)  # "2026-W24" or "2026-06"
    channel               = Column(String(50), nullable=False)  # 见 VALID_CHANNELS
    owner_role            = Column(String(50))                  # 见 VALID_ROLES
    owner_name            = Column(String(100))
    leads_count           = Column(Integer, default=0)
    qualified_leads_count = Column(Integer, default=0)
    quoted_count          = Column(Integer, default=0)
    deal_count            = Column(Integer, default=0)
    deal_amount           = Column(Float, default=0.0)
    conversion_rate       = Column(Float, default=0.0)          # deal/leads 0~1
    avg_response_time     = Column(String(50))                  # "4.2小时"
    lost_count            = Column(Integer, default=0)
    main_lost_reasons     = Column(JSON, default=list)          # ["价格高","跟进慢"]
    risk_count            = Column(Integer, default=0)
    created_at            = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 角色执行指标表
# ─────────────────────────────────────────
class RoleExecutionMetrics(Base):
    __tablename__ = "role_execution_metrics"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    period                = Column(String(20), nullable=False)
    role                  = Column(String(50), nullable=False)  # 见 VALID_ROLES
    person_name           = Column(String(100))
    channel               = Column(String(50))
    assigned_leads_count  = Column(Integer, default=0)
    followed_leads_count  = Column(Integer, default=0)
    overdue_followups_count = Column(Integer, default=0)
    quoted_count          = Column(Integer, default=0)
    deal_count            = Column(Integer, default=0)
    deal_amount           = Column(Float, default=0.0)
    conversion_rate       = Column(Float, default=0.0)
    risk_feedback_count   = Column(Integer, default=0)
    useful_feedback_count = Column(Integer, default=0)
    task_completion_rate  = Column(Float, default=0.0)
    created_at            = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# 执行反馈表 — 记录每条动作的执行结果（用于复盘）
# ─────────────────────────────────────────
class ExecutionFeedback(Base):
    __tablename__ = "execution_feedback"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    action_id       = Column(String(50), nullable=False, index=True)   # 推送中的动作标识
    push_date       = Column(String(20), nullable=False)               # 推送日期 YYYY-MM-DD
    department      = Column(String(50), nullable=False)               # promotion_team/consultant/...
    action_text     = Column(Text)                                     # 动作描述原文
    priority        = Column(String(10))                               # P0/P1/P2
    expected_result = Column(Text)                                     # 预期结果
    actual_result   = Column(Text)                                     # 实际结果（手动填入）
    completed       = Column(Boolean, default=None)                    # True/False/None=未反馈
    deviation       = Column(Text)                                     # 偏差说明
    reason          = Column(Text)                                     # 未完成原因
    feedback_by     = Column(String(100))                              # 填写人
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# LLM 调用日志表 — 记录每次 AI 调用情况
# ─────────────────────────────────────────
# ─────────────────────────────────────────
# Phase 2：渠道内容策略建议
# ─────────────────────────────────────────
class ChannelContentRecommendation(Base):
    __tablename__ = "channel_content_recommendations"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)
    rec_date        = Column(String(10), index=True)   # YYYY-MM-DD
    channel         = Column(String(50), index=True)   # xiaohongshu/moments/community/...
    content_type    = Column(String(50))               # 痛点文案/案例展示/对比图/活动预热/...
    target_school   = Column(String(100))              # 目标学校，空=通用
    target_product  = Column(String(50))               # 目标产品
    hook_idea       = Column(Text)                     # 钩子/标题思路
    body_idea       = Column(Text)                     # 正文框架
    cta             = Column(String(200))              # 行动号召
    priority        = Column(String(5), default="P1") # P0/P1/P2
    reason          = Column(Text)                     # 为什么现在推这个
    expected_leads  = Column(Integer, default=0)
    status          = Column(String(20), default="draft")  # draft/published/skipped
    published_at    = Column(DateTime)
    actual_leads    = Column(Integer)
    provider        = Column(String(50))               # 生成该建议的 LLM


# ─────────────────────────────────────────
# Phase 2：时间窗口预测
# ─────────────────────────────────────────
class TimeWindowForecast(Base):
    __tablename__ = "time_window_forecasts"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    created_at          = Column(DateTime, default=datetime.utcnow, index=True)
    forecast_date       = Column(String(10), index=True)   # 生成日期 YYYY-MM-DD
    window              = Column(String(20), index=True)   # 统一枚举：0-7天/8-14天/15-21天/22-30天/31-60天
    window_label        = Column(String(50))               # 显示名：本周（0-7天）
    school_name         = Column(String(100))              # 目标学校（替代旧字段 school）
    school              = Column(String(100))              # 兼容旧字段，逐步迁移到 school_name
    product_id          = Column(String(50))               # 产品ID（替代旧字段 product）
    product             = Column(String(50))               # 兼容旧字段
    product_name        = Column(String(100))              # 产品显示名
    country             = Column(String(10))               # UK/AU/US
    urgency             = Column(String(20))               # 极高/高/中/低
    demand_score        = Column(Float, default=0.0)       # 0-100 综合需求分
    predicted_leads     = Column(Integer, default=0)
    predicted_orders    = Column(Integer, default=0)
    recommended_channels = Column(JSON, default=list)      # ["xiaohongshu","moments"]
    role_actions_json   = Column(JSON, default=list)       # 结构化 role_actions（见 Schema 3.1）
    calendar_note_json  = Column(JSON, default=dict)       # {has_confirmed_date, source_url, confidence...}
    key_events          = Column(JSON, default=list)       # ["考试周","开学季"]
    action_hint         = Column(Text)                     # 兼容旧字段，简短提示
    reason              = Column(Text)                     # 推荐理由
    data_evidence       = Column(Text)                     # 数据依据
    risk_note           = Column(Text)                     # 风险说明
    missing_data        = Column(JSON, default=list)       # 缺少哪些数据
    priority            = Column(String(5), default="P1")  # P0/P1/P2
    confidence          = Column(String(20), default="medium")
    basis               = Column(JSON, default=dict)       # 计算依据


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 v2：content_strategy_recommendations（统一表名）
# 按"渠道 × 学校 × 产品 × 时间窗口"输出结构化内容策略
# ─────────────────────────────────────────────────────────────────────────────
class ContentStrategyRecommendation(Base):
    __tablename__ = "content_strategy_recommendations"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    created_at          = Column(DateTime, default=datetime.utcnow, index=True)
    rec_date            = Column(String(10), index=True)    # YYYY-MM-DD
    time_window         = Column(String(20), index=True)    # 枚举：0-7天/8-14天/15-21天/22-30天/31-60天
    channel             = Column(String(50), index=True)    # 渠道枚举（见常量）
    school_name         = Column(String(100))               # 目标学校，空=通用
    country             = Column(String(10))                # UK/AU/US
    product_id          = Column(String(50))                # 产品ID
    product_name        = Column(String(100))               # 产品显示名
    content_angle       = Column(String(100))               # 内容角度
    content_type        = Column(String(50))                # 图文/视频/九宫格/文字/直播预告
    hook                = Column(Text)                      # 标题/开场句（已过RiskGuard检查）
    body_idea           = Column(Text)                      # 正文框架（3要点）
    cta                 = Column(String(300))               # CTA
    target_audience     = Column(String(300))               # 受众描述
    reason              = Column(Text)                      # 推荐理由
    data_evidence       = Column(Text)                      # 数据依据或"规则兜底"标注
    sales_handoff       = Column(Text)                      # 顾问承接方式
    xueguan_action      = Column(Text)                      # 学管需确认事项
    risk_note           = Column(Text)                      # 风险说明
    priority            = Column(String(5), default="P1")  # P0/P1/P2
    confidence          = Column(String(20), default="medium")  # high/medium/low
    missing_data        = Column(JSON, default=list)        # 缺少哪些数据
    provider            = Column(String(50))                # deepseek/rule_fallback
    status              = Column(String(20), default="pending")  # pending/converted/skipped


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 v2：channel_contents（渠道内容草稿/执行记录）
# 推广部实际执行的内容，关联 content_strategy_recommendations
# ─────────────────────────────────────────────────────────────────────────────
class ChannelContent(Base):
    __tablename__ = "channel_contents"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    created_at              = Column(DateTime, default=datetime.utcnow, index=True)
    content_date            = Column(String(10), index=True)  # YYYY-MM-DD
    channel                 = Column(String(50), index=True)
    school_name             = Column(String(100))
    country                 = Column(String(10))
    product_id              = Column(String(50))
    time_window             = Column(String(20))              # 0-7天/8-14天/...
    content_angle           = Column(String(100))
    content_type            = Column(String(50))
    hook                    = Column(Text)
    body_outline            = Column(Text)
    cta                     = Column(String(300))
    target_audience         = Column(String(300))
    risk_note               = Column(Text)
    priority                = Column(String(5), default="P1")
    status                  = Column(String(20), default="draft")  # draft/approved/published/skipped/rejected
    published_at            = Column(DateTime)
    actual_leads            = Column(Integer, default=0)
    actual_orders           = Column(Integer, default=0)
    feedback_note           = Column(Text)
    source_recommendation_id = Column(Integer)               # 来源 content_strategy_recommendations.id
    provider                = Column(String(50))
    confidence              = Column(String(20), default="medium")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 v2：weekly_growth_briefs（作战单归档）
# 每次 run-weekly-growth-brief 的完整输出存档
# ─────────────────────────────────────────────────────────────────────────────
class WeeklyGrowthBrief(Base):
    __tablename__ = "weekly_growth_briefs"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    created_at           = Column(DateTime, default=datetime.utcnow, index=True)
    brief_week           = Column(String(10), index=True)   # YYYY-MM-DD（本周一）
    time_window_json     = Column(JSON, default=dict)       # 5个时间窗口预测
    channel_strategy_json = Column(JSON, default=dict)      # 7渠道内容策略
    consultant_json      = Column(JSON, default=list)       # 顾问建议列表
    xueguan_json         = Column(JSON, default=dict)       # 学管建议（结构化）
    traffic_light_json   = Column(JSON, default=dict)       # 产品红绿灯（6产品）
    risk_guard_json      = Column(JSON, default=dict)       # RiskGuard检查结果
    data_summary_json    = Column(JSON, default=dict)       # 数据依据汇总
    confidence           = Column(String(20), default="medium")
    provider             = Column(String(50))               # deepseek/rule_fallback
    push_sent            = Column(Boolean, default=False)
    push_chunks          = Column(Integer, default=0)


# ─────────────────────────────────────────────────────────────────────────────
# time_window_forecasts 在 Phase 2 已建，v2 补字段（nullable，兼容旧数据）
# 以下字段通过 init_db create_all 补建（SQLite 不支持 ADD COLUMN via ORM，
# 需手动 ALTER 或重建。新部署直接建全。）
# ─────────────────────────────────────────────────────────────────────────────


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    created_at         = Column(DateTime, default=datetime.utcnow, index=True)
    task_type          = Column(String(100))    # action_planner / weekly_review / daily_push ...
    provider           = Column(String(50))     # claude / deepseek / qwen / rule_fallback
    model              = Column(String(100))    # 具体模型名
    success            = Column(Boolean, default=False)
    error_type         = Column(String(50))     # forbidden_403 / timeout / invalid_json ...
    error_message      = Column(Text)
    latency_ms         = Column(Integer, default=0)
    prompt_tokens      = Column(Integer, default=0)
    completion_tokens  = Column(Integer, default=0)
    total_tokens       = Column(Integer, default=0)
    fallback_used      = Column(Boolean, default=False)


# ─────────────────────────────────────────────────────────────────────────────
# V11 新产品上线台
# ─────────────────────────────────────────────────────────────────────────────

class ProductLaunch(Base):
    __tablename__ = "product_launches"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 基础信息
    product_name            = Column(String(200), nullable=False)
    catalog_id              = Column(String(100))           # 产品目录 ID
    stage                   = Column(String(50), default="需求判断")
    # 需求判断/上线准备/小范围试推/正式推广/复盘/暂停

    # 负责人
    mgmt_decision           = Column(String(100))           # 管理层决策状态
    promo_owner             = Column(String(100))           # 推广负责人
    advisor_owner           = Column(String(100))           # 顾问负责人
    xueguan_owner           = Column(String(100))           # 学管负责人
    backend_owner           = Column(String(100))           # 后台负责人

    # 产品定向
    target_student_needs    = Column(Text)                  # 目标学生需求
    product_match_logic     = Column(Text)                  # 推荐产品匹配逻辑
    recommended_channels    = Column(Text)                  # 推荐渠道（逗号分隔）

    # 准备状态（ready/not_ready/in_progress）
    status_advisor_script   = Column(String(20), default="not_ready")   # 顾问话术状态
    status_xueguan_rules    = Column(String(20), default="not_ready")   # 学管承接规则状态
    status_promo_materials  = Column(String(20), default="not_ready")   # 推广素材状态
    status_catalog          = Column(String(20), default="not_ready")   # 产品目录库状态
    status_teacher_resource = Column(String(20), default="not_ready")   # 老师资源状态
    status_risk_boundary    = Column(String(20), default="not_ready")   # 风险边界状态
    status_forbidden_claims = Column(String(20), default="not_ready")   # 禁用表达状态

    # 数据指标
    consult_count           = Column(Integer, default=0)    # 当前咨询数
    deal_count              = Column(Integer, default=0)    # 当前成交数
    deal_amount             = Column(Integer, default=0)    # 当前成交金额（元）

    # 反馈文本
    client_objections       = Column(Text)                  # 客户主要异议
    xueguan_risk_feedback   = Column(Text)                  # 学管风险反馈
    promo_effect            = Column(Text)                  # 推广效果
    next_action             = Column(Text)                  # 下一步动作
    deadline                = Column(String(50))            # 截止时间

    # ── 五大关卡状态（not_started / in_progress / passed / blocked）──────────
    gate1_status            = Column(String(20), default="not_started")   # 产品定义关
    gate2_status            = Column(String(20), default="not_started")   # 交付承接关
    gate3_status            = Column(String(20), default="not_started")   # 推广准备关
    gate4_status            = Column(String(20), default="not_started")   # 销售转化关
    gate5_status            = Column(String(20), default="not_started")   # 复盘优化关

    # ── 管理层审批（pending/approved/deferred/adjusted/stopped）─────────────
    mgmt_approval           = Column(String(30), default="pending")
    mgmt_approval_note      = Column(Text)

    # ── 行为标记（用于异常检测）──────────────────────────────────────────────
    has_active_quotes       = Column(Boolean, default=False)   # 销售已开始报价
    has_promo_published     = Column(Boolean, default=False)   # 推广已开始宣传
    has_delivery_risk       = Column(Boolean, default=False)   # 学管反馈交付风险
    sales_training_done     = Column(Boolean, default=False)   # 销售培训完成
    sales_continuing_promises = Column(Boolean, default=False) # 学管示警后销售仍承诺
    needs_sync_to_xueguan   = Column(Boolean, default=False)   # 成交未同步学管
    promo_leads_count       = Column(Integer, default=0)       # 推广带来线索数
    sales_followup_count    = Column(Integer, default=0)       # 销售跟进记录数
    prev_review_done        = Column(Boolean, default=False)   # 上一轮复盘是否完成
    launch_date             = Column(DateTime)                 # 正式上线日期


class LaunchGateReview(Base):
    """各部门对关卡的审核记录"""
    __tablename__ = "launch_gate_reviews"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    launch_id       = Column(Integer, index=True, nullable=False)
    gate_num        = Column(Integer, nullable=False)          # 1-5
    reviewer_dept   = Column(String(50), nullable=False)       # 销售部/推广部/学管部/产品部/管理层
    review_status   = Column(String(20), nullable=False)       # approved/needs_revision/rejected
    comment         = Column(Text)


class LaunchDeptFeedback(Base):
    """部门间互评反馈"""
    __tablename__ = "launch_dept_feedback"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    launch_id       = Column(Integer, index=True, nullable=False)
    from_dept       = Column(String(50), nullable=False)
    to_dept         = Column(String(50), nullable=False)
    feedback_type   = Column(String(50), nullable=False)       # 10种类型之一
    description     = Column(Text)
    status          = Column(String(20), default="open")       # open/acknowledged/resolved


class UploadedFile(Base):
    """产品上线台 — 资料上传记录"""
    __tablename__ = "uploaded_files"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    launch_id   = Column(Integer, index=True, nullable=False)
    gate_num    = Column(Integer, default=0)
    filename    = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False)
    file_size   = Column(Integer, default=0)
    category    = Column(String(50), default="通用")
    uploader    = Column(String(50))
    description = Column(Text)
    file_path   = Column(String(500))


class InternalMessage(Base):
    """内部消息记录（含企业微信推送记录）"""
    __tablename__ = "internal_messages"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    launch_id        = Column(Integer, index=True, nullable=False)
    from_dept        = Column(String(50))
    to_dept          = Column(String(50), default="全员")
    msg_type         = Column(String(20), default="通知")
    content          = Column(Text, nullable=False)
    pushed_to_wechat = Column(Boolean, default=False)
    push_status      = Column(String(100))



class LaunchDeliverable(Base):
    """产品上线台 — 各关卡交付物与标准（产品部定义，销售部监管）"""
    __tablename__ = "launch_deliverables"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    launch_id       = Column(Integer, index=True, nullable=False)
    gate_num        = Column(Integer, nullable=False)       # 1-5
    deliverable     = Column(String(200), nullable=False)   # 交付物名称
    quality_std     = Column(Text)                          # 质量标准描述
    deadline        = Column(String(50))                    # 预计完成时间
    owner_dept      = Column(String(50), default="后台/产品") # 负责部门
    status          = Column(String(20), default="待定义")  # 待定义/已定义/已交付/有问题
    # 销售部监管
    sales_confirmed = Column(Boolean, default=False)        # 顾问已确认
    sales_note      = Column(Text)                          # 顾问监管意见
    sales_flagged   = Column(Boolean, default=False)        # 顾问标记有问题


class CourseAssessment(Base):
    """课程作业/考试安排 — 按热门专业爬取的DDL和考试时间"""
    __tablename__ = "course_assessments"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 学校/课程信息
    school          = Column(String(100), index=True, nullable=False)
    country         = Column(String(10), default="AU")
    major_category  = Column(String(50), index=True)   # 商科/CS/工程/法律/心理/建筑/传媒
    subject_code    = Column(String(30), index=True)   # e.g. ACCT1501
    subject_name    = Column(String(200))              # e.g. Accounting & Financial Management
    semester        = Column(String(30))               # Semester 1 / Term 1 / Autumn Term
    academic_year   = Column(String(10), default="2025-2026")

    # 考核信息
    assessment_type = Column(String(30))   # exam / assignment / quiz / project / presentation
    assessment_name = Column(String(200))  # Assignment 1 / Final Exam / Mid-term Quiz
    due_date        = Column(String(20))   # YYYY-MM-DD
    due_week        = Column(String(20))   # Week 6 / Week 12
    weight_pct      = Column(Float)        # 30.0 = 30%
    notes           = Column(Text)

    # 数据来源
    source          = Column(String(50), default="课程大纲")  # 课程大纲 / 考试时间表 / 模式推断
    source_url      = Column(String(500))
    confidence      = Column(String(10), default="medium")   # high / medium / low
    scraped_at      = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3：需求预测三层体系 + 信号表 + 数据源注册表
# ─────────────────────────────────────────────────────────────────────────────

class SchoolAcademicCalendar(Base):
    """第一层：学校级学术日历 — 每学期一行，结构化字段"""
    __tablename__ = "school_academic_calendars"

    id                          = Column(Integer, primary_key=True, autoincrement=True)
    created_at                  = Column(DateTime, default=datetime.utcnow)
    updated_at                  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    school                      = Column(String(100), index=True, nullable=False)
    country                     = Column(String(10), index=True)           # AU / UK / HK
    academic_year               = Column(String(10), default="2025-2026")
    semester                    = Column(String(50))                       # Semester 1 / Autumn Term
    term_start                  = Column(String(20))                       # YYYY-MM-DD
    term_end                    = Column(String(20))
    teaching_start              = Column(String(20))
    teaching_end                = Column(String(20))
    reading_week_start          = Column(String(20))
    reading_week_end            = Column(String(20))
    exam_period_start           = Column(String(20))
    exam_period_end             = Column(String(20))
    resit_exam_start            = Column(String(20))
    resit_exam_end              = Column(String(20))
    dissertation_deadline_start = Column(String(20))
    dissertation_deadline_end   = Column(String(20))
    source_url                  = Column(String(500))
    source_type                 = Column(String(30), default="pattern")    # official/scraped/pattern/manual
    confidence_score            = Column(Float, default=0.6)               # 0.0–1.0
    last_updated                = Column(DateTime, default=datetime.utcnow)
    notes                       = Column(Text)


class CourseAssessmentV2(Base):
    """第二层：课程级Assessment数据（v2，字段更完整）"""
    __tablename__ = "course_assessments_v2"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    school              = Column(String(100), index=True, nullable=False)
    country             = Column(String(10), default="AU")
    major_category      = Column(String(50), index=True)
    subject_code        = Column(String(30), index=True)
    subject_name        = Column(String(200))
    semester            = Column(String(30))
    academic_year       = Column(String(10), default="2025-2026")
    assessment_type     = Column(String(30))                               # exam/assignment/quiz/project/presentation
    assessment_name     = Column(String(200))
    assessment_weight   = Column(Float)                                    # 30.0 = 30%
    due_week            = Column(String(20))                               # Week 6
    due_date_if_public  = Column(String(20))                              # YYYY-MM-DD
    final_exam_yes_no   = Column(Boolean, default=False)
    presentation_yes_no = Column(Boolean, default=False)
    group_work_yes_no   = Column(Boolean, default=False)
    suitable_products   = Column(JSON)                                     # ["Essay写作", "作业委托"]
    source_url          = Column(String(500))
    source_type         = Column(String(30), default="pattern")            # official/scraped/pattern
    confidence_score    = Column(Float, default=0.5)
    notes               = Column(Text)


class MajorDemandProfile(Base):
    """第三层：专业需求画像 — 从历史订单+线索提取，按学校+专业+产品汇总"""
    __tablename__ = "major_demand_profiles"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    school              = Column(String(100), index=True, nullable=False)
    country             = Column(String(10))
    major_category      = Column(String(50), index=True)
    subject_code        = Column(String(30))
    product_type        = Column(String(100), index=True)
    # 需求规律
    peak_relative_week  = Column(Integer)                                  # 学期第N周，需求最高
    peak_month          = Column(Integer)                                  # 1-12
    avg_orders_peak     = Column(Float, default=0)
    avg_order_value     = Column(Float, default=0)
    primary_channel     = Column(String(50))
    total_orders        = Column(Integer, default=0)
    total_revenue       = Column(Float, default=0)
    lead_to_order_rate  = Column(Float)                                    # 0.0–1.0
    data_period_start   = Column(String(20))                              # 统计期起始
    data_period_end     = Column(String(20))
    last_computed       = Column(DateTime, default=datetime.utcnow)
    notes               = Column(Text)


class DemandForecastSignal(Base):
    """需求预测信号 — 综合三层数据生成的预测结果"""
    __tablename__ = "demand_forecast_signals"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    school              = Column(String(100), index=True)
    major_category      = Column(String(50))
    product             = Column(String(100), index=True)
    country             = Column(String(10))
    time_window_days    = Column(Integer)                                  # 7/14/30/60
    window_start        = Column(String(20))                              # YYYY-MM-DD
    window_end          = Column(String(20))
    signal_strength     = Column(Float, default=0.5)                      # 0.0–1.0
    confidence_score    = Column(Float, default=0.5)                      # 0.0–1.0
    confidence_label    = Column(String(10), default="中")                # 高/中/低
    forecast_reason     = Column(Text)
    data_sources        = Column(JSON)                                     # list of source names
    promo_action        = Column(Text)
    sales_action        = Column(Text)
    triggered_by        = Column(String(50))                              # calendar/assessment/history/lead_heat
    expires_at          = Column(String(20))


class DataSourceRegistry(Base):
    """数据源注册表 — 追踪所有数据来源的状态和可信度"""
    __tablename__ = "data_source_registry"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source_name     = Column(String(100), unique=True, nullable=False)
    source_type     = Column(String(30))                                   # academic_calendar/course_profile/crm/pattern
    school          = Column(String(100))
    country         = Column(String(10))
    url             = Column(String(500))
    last_scraped    = Column(DateTime)
    last_success    = Column(DateTime)
    scrape_success  = Column(Boolean)
    record_count    = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.5)
    scrape_method   = Column(String(30))                                   # ics/html/pdf/api/manual/pattern
    failure_reason  = Column(Text)
    notes           = Column(Text)
