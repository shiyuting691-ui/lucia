"""
CRUD 操作 — 供 Agent 和 Dashboard 调用
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from .models import (Content, Campaign, Task, KnowledgeDoc, Product, School,
                     DepartmentFeedback, StrategySuggestion, ContentUsage, WorkflowRun,
                     CompanyFact, BusinessDictionaryTerm,
                     SchoolScore, SchoolStrategyCard)
from .db import get_session


# ─────────────────────────────────────────
# Content CRUD
# ─────────────────────────────────────────

def save_content(data: dict, session: Session = None) -> Content:
    """保存一条内容，返回 Content 对象。可传入外部 session（事务批量写入）"""
    def _do(s: Session):
        content = Content(
            title           = data.get("title", ""),
            content_type    = data.get("content_type", "xiaohongshu"),
            target_user     = data.get("target_user", ""),
            product_id      = data.get("product"),
            school_name     = data.get("school", ""),
            channel         = data.get("channel", ""),
            target_country  = data.get("target_country", ""),
            campaign_id     = data.get("campaign_id"),
            body            = data.get("content", data.get("body", "")),
            cover_text      = data.get("cover_text", ""),
            hashtags        = data.get("hashtags", []),
            call_to_action  = data.get("call_to_action", ""),
            status          = data.get("status", "draft"),
            risk_notes      = data.get("risk_notes", []),
            suggested_use   = data.get("suggested_use", ""),
            post_timing     = data.get("post_timing", ""),
            urgency         = data.get("urgency", ""),
            market_period   = data.get("market_period", ""),
            raw_output      = data,
        )
        s.add(content)
        s.flush()
        return content

    if session:
        return _do(session)
    else:
        with get_session() as s:
            c = _do(s)
            s.expunge(c)
            return c


def list_contents(
    status: str = None,
    content_type: str = None,
    product_id: str = None,
    channel: str = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    """查询内容列表，返回 dict list 供前端展示"""
    with get_session() as s:
        q = select(Content).order_by(desc(Content.created_at))
        if status:
            q = q.where(Content.status == status)
        if content_type:
            q = q.where(Content.content_type == content_type)
        if product_id:
            q = q.where(Content.product_id == product_id)
        if channel:
            q = q.where(Content.channel == channel)
        q = q.limit(limit).offset(offset)
        rows = s.execute(q).scalars().all()
        return [_content_to_dict(r) for r in rows]


def get_content(content_id: int) -> Optional[dict]:
    with get_session() as s:
        c = s.get(Content, content_id)
        return _content_to_dict(c) if c else None


def update_content_status(content_id: int, status: str, comment: str = None, used_by: str = None) -> bool:
    with get_session() as s:
        c = s.get(Content, content_id)
        if not c:
            return False
        c.status = status
        c.updated_at = datetime.utcnow()
        if comment:
            c.review_comment = comment
        if used_by:
            c.used_by = used_by
            c.used_at = datetime.utcnow()
        return True


def _content_to_dict(c: Content) -> dict:
    if not c:
        return {}
    return {
        "id":             c.id,
        "title":          c.title,
        "content_type":   c.content_type,
        "product_id":     c.product_id,
        "school_name":    c.school_name,
        "channel":        c.channel,
        "target_country": c.target_country,
        "body":           c.body,
        "cover_text":     c.cover_text,
        "hashtags":       c.hashtags or [],
        "call_to_action": c.call_to_action,
        "status":         c.status,
        "risk_notes":     c.risk_notes or [],
        "suggested_use":  c.suggested_use,
        "post_timing":    c.post_timing,
        "urgency":        c.urgency,
        "market_period":  c.market_period,
        "review_comment": c.review_comment,
        "used_by":        c.used_by,
        "used_at":        c.used_at.isoformat() if c.used_at else None,
        "created_at":     c.created_at.isoformat() if c.created_at else None,
        "updated_at":     c.updated_at.isoformat() if c.updated_at else None,
    }


# ─────────────────────────────────────────
# Campaign CRUD
# ─────────────────────────────────────────

def save_campaign(data: dict) -> int:
    import json as _json

    def _parse_dt(v):
        if isinstance(v, datetime): return v
        if isinstance(v, str) and v:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try: return datetime.strptime(v, fmt)
                except ValueError: pass
        return None

    # plan_data 必须是 JSON-safe 的（datetime 转字符串）
    def _json_safe(obj):
        if isinstance(obj, datetime): return obj.isoformat()
        if isinstance(obj, dict):     return {k: _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):     return [_json_safe(i) for i in obj]
        return obj

    with get_session() as s:
        camp = Campaign(
            name           = data.get("name", ""),
            campaign_type  = data.get("campaign_type", ""),
            period_start   = _parse_dt(data.get("period_start")),
            period_end     = _parse_dt(data.get("period_end")),
            core_theme     = data.get("core_theme", ""),
            core_goal      = data.get("core_goal", ""),
            target_country = data.get("target_country", ""),
            plan_data      = _json_safe(data),
        )
        s.add(camp)
        s.flush()
        campaign_id = camp.id
    return campaign_id


def list_campaigns(limit: int = 20) -> List[dict]:
    with get_session() as s:
        rows = s.execute(
            select(Campaign).order_by(desc(Campaign.created_at)).limit(limit)
        ).scalars().all()
        return [
            {
                "id":            r.id,
                "name":          r.name,
                "campaign_type": r.campaign_type,
                "core_theme":    r.core_theme,
                "core_goal":     r.core_goal,
                "status":         r.status,
                "target_country": r.target_country,
                "period_start":   r.period_start.isoformat() if r.period_start else None,
                "period_end":     r.period_end.isoformat() if r.period_end else None,
                "plan_data":      r.plan_data,
                "created_at":     r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


# ─────────────────────────────────────────
# Dashboard 统计
# ─────────────────────────────────────────

def get_dashboard_stats() -> dict:
    with get_session() as s:
        from sqlalchemy import func
        total    = s.execute(select(func.count()).select_from(Content)).scalar()
        pending  = s.execute(select(func.count()).select_from(Content).where(Content.status == "pending_review")).scalar()
        approved = s.execute(select(func.count()).select_from(Content).where(Content.status == "approved")).scalar()
        used     = s.execute(select(func.count()).select_from(Content).where(Content.status == "used")).scalar()
        draft    = s.execute(select(func.count()).select_from(Content).where(Content.status == "draft")).scalar()

        # 按类型统计
        type_counts = {}
        for row in s.execute(
            select(Content.content_type, func.count()).group_by(Content.content_type)
        ).all():
            type_counts[row[0]] = row[1]

        # 最近内容
        recent = s.execute(
            select(Content).order_by(desc(Content.created_at)).limit(5)
        ).scalars().all()

        # 高优先级反馈/建议数量
        high_feedback = s.execute(
            select(func.count()).select_from(DepartmentFeedback)
            .where(DepartmentFeedback.urgency.in_(["高", "紧急"]))
            .where(DepartmentFeedback.status == "open")
        ).scalar()

        high_suggestions = s.execute(
            select(func.count()).select_from(StrategySuggestion)
            .where(StrategySuggestion.priority.in_(["高", "紧急"]))
            .where(StrategySuggestion.status == "new")
        ).scalar()

        return {
            "total":            total,
            "draft":            draft,
            "pending":          pending,
            "approved":         approved,
            "used":             used,
            "by_type":          type_counts,
            "recent":           [_content_to_dict(r) for r in recent],
            "high_feedback":    high_feedback,
            "high_suggestions": high_suggestions,
        }


# ─────────────────────────────────────────
# Knowledge Doc CRUD
# ─────────────────────────────────────────

def save_knowledge_doc(data: dict) -> int:
    with get_session() as s:
        # 若已存在同路径文档，更新而非重复插入
        existing = s.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.file_path == data.get("file_path"))
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                if hasattr(KnowledgeDoc, k):
                    setattr(existing, k, v)
            existing.updated_at = datetime.utcnow()
            s.flush()
            return existing.id
        doc = KnowledgeDoc(**{k: v for k, v in data.items() if hasattr(KnowledgeDoc, k)})
        s.add(doc)
        s.flush()
        return doc.id


def update_knowledge_doc_summary(doc_id: int, summary: str, keywords: list = None,
                                  related_products: list = None, related_scenarios: list = None) -> bool:
    with get_session() as s:
        doc = s.get(KnowledgeDoc, doc_id)
        if not doc:
            return False
        doc.summary    = summary
        doc.keywords   = keywords or []
        doc.summary_at = datetime.utcnow()
        if related_products is not None:
            doc.related_products  = related_products
        if related_scenarios is not None:
            doc.related_scenarios = related_scenarios
        doc.updated_at = datetime.utcnow()
        return True


def list_knowledge_docs(category: str = None, has_summary: bool = None) -> List[dict]:
    with get_session() as s:
        q = select(KnowledgeDoc).order_by(KnowledgeDoc.category, KnowledgeDoc.file_name)
        if category:
            q = q.where(KnowledgeDoc.category == category)
        if has_summary is True:
            q = q.where(KnowledgeDoc.summary != None)
        if has_summary is False:
            q = q.where(KnowledgeDoc.summary == None)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id":                r.id,
                "file_name":         r.file_name,
                "category":          r.category,
                "file_path":         r.file_path,
                "file_type":         r.file_type,
                "file_size":         r.file_size,
                "is_enabled":        r.is_enabled,
                "is_expired":        r.is_expired,
                "related_products":  r.related_products or [],
                "related_scenarios": getattr(r, "related_scenarios", None) or [],
                "keywords":          getattr(r, "keywords", None) or [],
                "summary":           getattr(r, "summary", None) or "",
                "summary_at":        r.summary_at.isoformat() if getattr(r, "summary_at", None) else None,
                "last_synced_at":    r.last_synced_at.isoformat() if r.last_synced_at else None,
                "created_at":        r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def get_knowledge_stats() -> dict:
    """返回各分类文件数量统计"""
    with get_session() as s:
        from sqlalchemy import func
        rows = s.execute(
            select(KnowledgeDoc.category, func.count())
            .where(KnowledgeDoc.is_enabled == True)
            .group_by(KnowledgeDoc.category)
        ).all()
        total      = s.execute(select(func.count()).select_from(KnowledgeDoc).where(KnowledgeDoc.is_enabled == True)).scalar()
        with_summary = s.execute(
            select(func.count()).select_from(KnowledgeDoc)
            .where(KnowledgeDoc.summary != None)
            .where(KnowledgeDoc.is_enabled == True)
        ).scalar()
        return {
            "total": total,
            "with_summary": with_summary,
            "by_category": {r[0] or "未分类": r[1] for r in rows},
        }


# ─────────────────────────────────────────
# Department Feedback CRUD
# ─────────────────────────────────────────

def save_feedback(data: dict) -> int:
    with get_session() as s:
        fb = DepartmentFeedback(
            department      = data.get("department", ""),
            feedback_type   = data.get("feedback_type", "其他"),
            related_product = data.get("related_product", ""),
            related_school  = data.get("related_school", ""),
            title           = data.get("title", ""),
            content         = data.get("content", ""),
            urgency         = data.get("urgency", "中"),
            status          = data.get("status", "open"),
            created_by      = data.get("created_by", ""),
        )
        s.add(fb)
        s.flush()
        return fb.id


def list_feedbacks(status: str = None, department: str = None, urgency: str = None) -> List[dict]:
    with get_session() as s:
        q = select(DepartmentFeedback).order_by(
            desc(DepartmentFeedback.created_at)
        )
        if status:
            q = q.where(DepartmentFeedback.status == status)
        if department:
            q = q.where(DepartmentFeedback.department == department)
        if urgency:
            q = q.where(DepartmentFeedback.urgency == urgency)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id":               r.id,
                "department":       r.department,
                "feedback_type":    r.feedback_type,
                "related_product":  r.related_product,
                "related_school":   r.related_school,
                "title":            r.title,
                "content":          r.content,
                "urgency":          r.urgency,
                "status":           r.status,
                "created_by":       r.created_by,
                "created_at":       r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def update_feedback_status(feedback_id: int, status: str) -> bool:
    with get_session() as s:
        fb = s.get(DepartmentFeedback, feedback_id)
        if not fb:
            return False
        fb.status = status
        fb.updated_at = datetime.utcnow()
        return True


# ─────────────────────────────────────────
# Strategy Suggestions CRUD
# ─────────────────────────────────────────

def save_suggestion(data: dict = None, **kwargs) -> int:
    """支持两种调用方式：save_suggestion(dict) 或 save_suggestion(title=..., content=..., ...)"""
    d = data if data is not None else kwargs
    with get_session() as s:
        sg = StrategySuggestion(
            title           = d.get("title", ""),
            suggestion_type = d.get("suggestion_type", "市场机会"),
            related_product = d.get("related_product", ""),
            related_country = d.get("related_country", ""),
            related_school  = d.get("related_school", ""),
            insight         = d.get("insight", ""),
            recommendation  = d.get("recommendation", ""),
            content         = d.get("content", ""),
            data_basis      = d.get("data_basis"),
            priority        = d.get("priority", "中"),
            status          = d.get("status", "new"),
            source          = d.get("source", "AI生成"),
        )
        s.add(sg)
        s.flush()
        return sg.id


def list_suggestions(status: str = None, priority: str = None,
                     suggestion_type: str = None, limit: int = 200) -> List[dict]:
    with get_session() as s:
        q = select(StrategySuggestion).order_by(
            desc(StrategySuggestion.created_at)
        )
        if status:
            q = q.where(StrategySuggestion.status == status)
        if priority:
            q = q.where(StrategySuggestion.priority == priority)
        if suggestion_type:
            q = q.where(StrategySuggestion.suggestion_type == suggestion_type)
        rows = s.execute(q.limit(limit)).scalars().all()
        return [
            {
                "id":               r.id,
                "title":            r.title,
                "suggestion_type":  r.suggestion_type,
                "related_product":  r.related_product,
                "related_country":  r.related_country,
                "related_school":   r.related_school,
                "insight":          r.insight,
                "recommendation":   r.recommendation,
                "content":          r.content,
                "data_basis":       r.data_basis,
                "priority":         r.priority,
                "status":           r.status,
                "source":           r.source,
                "created_at":       r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def update_suggestion_status(sg_id: int, status: str) -> bool:
    with get_session() as s:
        sg = s.get(StrategySuggestion, sg_id)
        if not sg:
            return False
        sg.status = status
        sg.updated_at = datetime.utcnow()
        return True


# ─────────────────────────────────────────
# Task CRUD
# ─────────────────────────────────────────

def save_task(data: dict) -> int:
    with get_session() as s:
        task = Task(
            title               = data.get("title", ""),
            description         = data.get("description", ""),
            task_type           = data.get("task_type", ""),
            department          = data.get("department", ""),
            owner               = data.get("owner", ""),
            priority            = data.get("priority", "中"),
            task_source         = data.get("task_source", "AI生成"),
            related_product     = data.get("related_product", ""),
            related_school      = data.get("related_school", ""),
            related_content_id  = data.get("related_content_id"),
            related_campaign_id = data.get("related_campaign_id"),
            expected_output     = data.get("expected_output", ""),
            due_date            = data.get("due_date"),
            status              = data.get("status", "todo"),
            notes               = data.get("notes", ""),
        )
        s.add(task)
        s.flush()
        return task.id


def list_tasks(
    department: str = None,
    status: str = None,
    priority: str = None,
    task_type: str = None,
    limit: int = 200,
) -> List[dict]:
    with get_session() as s:
        q = select(Task).order_by(desc(Task.created_at))
        if department:
            q = q.where(Task.department == department)
        if status:
            q = q.where(Task.status == status)
        if priority:
            q = q.where(Task.priority == priority)
        if task_type:
            q = q.where(Task.task_type == task_type)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [_task_to_dict(r) for r in rows]


def update_task_status(task_id: int, status: str, notes: str = None) -> bool:
    with get_session() as s:
        t = s.get(Task, task_id)
        if not t:
            return False
        t.status = status
        t.updated_at = datetime.utcnow()
        if status == "done":
            t.completed_at = datetime.utcnow()
        if notes:
            t.notes = (t.notes or "") + f"\n[{datetime.utcnow().strftime('%m/%d %H:%M')}] {notes}"
        return True


def _task_to_dict(t: Task) -> dict:
    return {
        "id":                   t.id,
        "title":                t.title,
        "description":          t.description,
        "task_type":            t.task_type,
        "department":           t.department,
        "owner":                t.owner,
        "priority":             t.priority,
        "task_source":          t.task_source,
        "related_product":      t.related_product,
        "related_school":       t.related_school,
        "related_content_id":   t.related_content_id,
        "related_campaign_id":  t.related_campaign_id,
        "expected_output":      t.expected_output,
        "status":               t.status,
        "notes":                t.notes,
        "due_date":             t.due_date.isoformat() if t.due_date else None,
        "created_at":           t.created_at.isoformat() if t.created_at else None,
        "completed_at":         t.completed_at.isoformat() if t.completed_at else None,
    }


def get_task_stats() -> dict:
    with get_session() as s:
        from sqlalchemy import func
        total   = s.execute(select(func.count()).select_from(Task)).scalar()
        todo    = s.execute(select(func.count()).select_from(Task).where(Task.status == "todo")).scalar()
        doing   = s.execute(select(func.count()).select_from(Task).where(Task.status == "doing")).scalar()
        done    = s.execute(select(func.count()).select_from(Task).where(Task.status == "done")).scalar()
        blocked = s.execute(select(func.count()).select_from(Task).where(Task.status == "blocked")).scalar()
        # 按部门统计
        dept_counts = {}
        for row in s.execute(
            select(Task.department, func.count()).group_by(Task.department)
        ).all():
            if row[0]:
                dept_counts[row[0]] = row[1]
        return {"total": total, "todo": todo, "doing": doing, "done": done,
                "blocked": blocked, "by_dept": dept_counts}


# ─────────────────────────────────────────
# ContentUsage CRUD
# ─────────────────────────────────────────

def save_content_usage(data: dict) -> int:
    with get_session() as s:
        u = ContentUsage(
            content_id      = data["content_id"],
            used_by         = data.get("used_by", ""),
            department      = data.get("department", ""),
            channel         = data.get("channel", ""),
            usage_context   = data.get("usage_context", ""),
            customer_stage  = data.get("customer_stage", ""),
            result          = data.get("result", "未知"),
            feedback        = data.get("feedback", ""),
        )
        s.add(u)
        s.flush()
        # 同步更新 contents 表状态
        c = s.get(Content, data["content_id"])
        if c and c.status == "approved":
            c.status = "used"
            c.used_by = data.get("used_by", "")
            c.used_at = datetime.utcnow()
        return u.id


def list_content_usages(content_id: int = None, limit: int = 100) -> List[dict]:
    with get_session() as s:
        q = select(ContentUsage).order_by(desc(ContentUsage.created_at))
        if content_id:
            q = q.where(ContentUsage.content_id == content_id)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id":             r.id,
                "content_id":     r.content_id,
                "used_by":        r.used_by,
                "department":     r.department,
                "channel":        r.channel,
                "usage_context":  r.usage_context,
                "customer_stage": r.customer_stage,
                "result":         r.result,
                "feedback":       r.feedback,
                "created_at":     r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def get_usage_stats() -> dict:
    """统计内容使用效果"""
    with get_session() as s:
        from sqlalchemy import func
        total = s.execute(select(func.count()).select_from(ContentUsage)).scalar()
        result_counts = {}
        for row in s.execute(
            select(ContentUsage.result, func.count()).group_by(ContentUsage.result)
        ).all():
            result_counts[row[0]] = row[1]
        channel_counts = {}
        for row in s.execute(
            select(ContentUsage.channel, func.count()).group_by(ContentUsage.channel)
        ).all():
            if row[0]:
                channel_counts[row[0]] = row[1]
        return {"total": total, "by_result": result_counts, "by_channel": channel_counts}


# ─────────────────────────────────────────
# WorkflowRun CRUD
# ─────────────────────────────────────────

def start_workflow_run(workflow_name: str, trigger: str = "manual") -> int:
    with get_session() as s:
        run = WorkflowRun(
            workflow_name = workflow_name,
            status        = "running",
            trigger       = trigger,
            steps_run     = [],
        )
        s.add(run)
        s.flush()
        return run.id


def finish_workflow_run(
    run_id: int,
    status: str,
    steps: list,
    records_count: int = 0,
    error_message: str = None,
    summary: str = None,
):
    with get_session() as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return
        run.status               = status
        run.finished_at          = datetime.utcnow()
        run.duration_seconds     = (run.finished_at - run.started_at).total_seconds() \
                                   if run.started_at else 0
        run.steps_run            = steps
        run.created_records_count= records_count
        run.error_message        = error_message
        run.summary              = summary


def list_workflow_runs(limit: int = 20) -> List[dict]:
    with get_session() as s:
        rows = s.execute(
            select(WorkflowRun).order_by(desc(WorkflowRun.started_at)).limit(limit)
        ).scalars().all()
        return [
            {
                "id":           r.id,
                "workflow_name":r.workflow_name,
                "status":       r.status,
                "trigger":      r.trigger,
                "started_at":   r.started_at.isoformat() if r.started_at else None,
                "finished_at":  r.finished_at.isoformat() if r.finished_at else None,
                "duration_seconds": r.duration_seconds,
                "steps_run":    r.steps_run or [],
                "created_records_count": r.created_records_count,
                "error_message":r.error_message,
                "summary":      r.summary,
            }
            for r in rows
        ]


# ═══════════════════════════════════════════════════════════════
# V4 — 订单 / 咨询 / 学校节点 / 市场信号 / 往年规律
# ═══════════════════════════════════════════════════════════════
from .models import Order, Lead, SchoolCalendar, MarketSignal, YearlyPattern, TeacherCapacity, OrderRiskSignal


# ── 订单 ──────────────────────────────────────────────────────
def save_order(data: dict) -> int:
    from datetime import datetime as _dt
    def _parse(v):
        if isinstance(v, str) and v:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
                try: return _dt.strptime(v, fmt)
                except ValueError: pass
        return v or None

    with get_session() as s:
        obj = Order(
            order_date   = _parse(data.get("order_date")),
            customer_id  = str(data.get("customer_id", "")),
            school       = data.get("school", ""),
            country      = data.get("country", ""),
            major        = data.get("major", ""),
            course_code  = data.get("course_code", ""),
            product      = data.get("product", ""),
            service_type = data.get("service_type", ""),
            deadline     = _parse(data.get("deadline")),
            amount       = float(data.get("amount", 0) or 0),
            sales_owner  = data.get("sales_owner", ""),
            status       = data.get("status", "confirmed"),
            source_file  = data.get("source_file", ""),
        )
        s.add(obj); s.flush(); return obj.id


def list_orders(days: int = 30, school: str = None, country: str = None,
                product: str = None, limit: int = 500) -> List[dict]:
    from datetime import timedelta
    with get_session() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = select(Order).where(Order.order_date >= cutoff).order_by(desc(Order.order_date))
        if school:   q = q.where(Order.school == school)
        if country:  q = q.where(Order.country == country)
        if product:  q = q.where(Order.product == product)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {"id": r.id, "order_date": r.order_date.isoformat() if r.order_date else None,
             "school": r.school, "country": r.country, "major": r.major,
             "course_code": r.course_code, "product": r.product, "service_type": r.service_type,
             "deadline": r.deadline.isoformat() if r.deadline else None,
             "amount": r.amount, "sales_owner": r.sales_owner, "status": r.status,
             "customer_id": r.customer_id}
            for r in rows
        ]


def get_order_stats(days: int = 30) -> dict:
    """按学校/产品/国家汇总近N天订单"""
    from datetime import timedelta
    with get_session() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = s.execute(
            select(Order).where(Order.order_date >= cutoff)
        ).scalars().all()
        school_cnt: dict = {}
        product_cnt: dict = {}
        country_cnt: dict = {}
        total_amount = 0.0
        for r in rows:
            school_cnt[r.school or "未知"] = school_cnt.get(r.school or "未知", 0) + 1
            product_cnt[r.product or "未知"] = product_cnt.get(r.product or "未知", 0) + 1
            country_cnt[r.country or "未知"] = country_cnt.get(r.country or "未知", 0) + 1
            total_amount += r.amount or 0
        return {
            "total": len(rows),
            "total_amount": total_amount,
            "by_school": sorted(school_cnt.items(), key=lambda x: -x[1]),
            "by_product": sorted(product_cnt.items(), key=lambda x: -x[1]),
            "by_country": sorted(country_cnt.items(), key=lambda x: -x[1]),
        }


# ── 咨询/线索 ───────────────────────────────────────────────────
def save_lead(data: dict) -> int:
    from datetime import datetime as _dt
    def _parse(v):
        if isinstance(v, str) and v:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
                try: return _dt.strptime(v, fmt)
                except ValueError: pass
        return v or None

    with get_session() as s:
        obj = Lead(
            inquiry_date     = _parse(data.get("inquiry_date")),
            customer_name    = data.get("customer_name", ""),
            school           = data.get("school", ""),
            country          = data.get("country", ""),
            major            = data.get("major", ""),
            course_code      = data.get("course_code", ""),
            product_interest = data.get("product_interest", ""),
            pain_point       = data.get("pain_point", ""),
            deadline         = _parse(data.get("deadline")),
            quoted_price     = float(data.get("quoted_price", 0) or 0),
            deal_status      = data.get("deal_status", "new"),
            lost_reason      = data.get("lost_reason", ""),
            sales_owner      = data.get("sales_owner", ""),
            source_channel   = data.get("source_channel", ""),
            source_file      = data.get("source_file", ""),
        )
        s.add(obj); s.flush(); return obj.id


def list_leads(days: int = 30, school: str = None, country: str = None,
               deal_status: str = None, limit: int = 500) -> List[dict]:
    from datetime import timedelta
    with get_session() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = select(Lead).where(Lead.inquiry_date >= cutoff).order_by(desc(Lead.inquiry_date))
        if school:      q = q.where(Lead.school == school)
        if country:     q = q.where(Lead.country == country)
        if deal_status: q = q.where(Lead.deal_status == deal_status)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {"id": r.id, "inquiry_date": r.inquiry_date.isoformat() if r.inquiry_date else None,
             "customer_name": r.customer_name, "school": r.school, "country": r.country,
             "major": r.major, "course_code": r.course_code,
             "product_interest": r.product_interest, "pain_point": r.pain_point,
             "deadline": r.deadline.isoformat() if r.deadline else None,
             "quoted_price": r.quoted_price, "deal_status": r.deal_status,
             "lost_reason": r.lost_reason, "sales_owner": r.sales_owner,
             "source_channel": r.source_channel}
            for r in rows
        ]


def get_lead_stats(days: int = 30) -> dict:
    from datetime import timedelta
    with get_session() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = s.execute(
            select(Lead).where(Lead.inquiry_date >= cutoff)
        ).scalars().all()
        school_cnt: dict = {}
        product_cnt: dict = {}
        channel_cnt: dict = {}
        won = lost = 0
        for r in rows:
            school_cnt[r.school or "未知"] = school_cnt.get(r.school or "未知", 0) + 1
            product_cnt[r.product_interest or "未知"] = product_cnt.get(r.product_interest or "未知", 0) + 1
            channel_cnt[r.source_channel or "未知"] = channel_cnt.get(r.source_channel or "未知", 0) + 1
            if r.deal_status == "won": won += 1
            if r.deal_status == "lost": lost += 1
        return {
            "total": len(rows),
            "won": won,
            "lost": lost,
            "conversion_rate": round(won / len(rows), 3) if rows else 0,
            "by_school": sorted(school_cnt.items(), key=lambda x: -x[1]),
            "by_product": sorted(product_cnt.items(), key=lambda x: -x[1]),
            "by_channel": sorted(channel_cnt.items(), key=lambda x: -x[1]),
        }


# ── 学校节点 ───────────────────────────────────────────────────
def save_school_calendar(data: dict) -> int:
    from datetime import datetime as _dt
    def _parse(v):
        if isinstance(v, str) and v:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try: return _dt.strptime(v, fmt)
                except ValueError: pass
        return v or None

    with get_session() as s:
        obj = SchoolCalendar(
            school        = data.get("school", ""),
            country       = data.get("country", ""),
            academic_year = data.get("academic_year", ""),
            term          = data.get("term", ""),
            event_type    = data.get("event_type", ""),
            event_name    = data.get("event_name", ""),
            start_date    = _parse(data.get("start_date")),
            end_date      = _parse(data.get("end_date")),
            confidence    = data.get("confidence", "medium"),
            source        = data.get("source", ""),
            notes         = data.get("notes", ""),
        )
        s.add(obj); s.flush(); return obj.id


def list_school_calendar(school: str = None, country: str = None,
                         days_ahead: int = 30) -> List[dict]:
    from datetime import timedelta
    with get_session() as s:
        now = datetime.utcnow()
        future = now + timedelta(days=days_ahead)
        q = select(SchoolCalendar).where(
            SchoolCalendar.start_date >= now,
            SchoolCalendar.start_date <= future,
        ).order_by(SchoolCalendar.start_date)
        if school:  q = q.where(SchoolCalendar.school == school)
        if country: q = q.where(SchoolCalendar.country == country)
        rows = s.execute(q).scalars().all()
        return [
            {"id": r.id, "school": r.school, "country": r.country,
             "academic_year": r.academic_year, "term": r.term,
             "event_type": r.event_type, "event_name": r.event_name,
             "start_date": r.start_date.isoformat() if r.start_date else None,
             "end_date": r.end_date.isoformat() if r.end_date else None,
             "confidence": r.confidence, "source": r.source, "notes": r.notes}
            for r in rows
        ]


# ── 市场信号 ───────────────────────────────────────────────────
def save_market_signal(data: dict) -> int:
    with get_session() as s:
        obj = MarketSignal(
            country          = data.get("country", ""),
            school           = data.get("school", ""),
            product          = data.get("product", ""),
            signal_type      = data.get("signal_type", ""),
            signal_value     = float(data.get("signal_value", 0) or 0),
            trend            = data.get("trend", "stable"),
            evidence         = data.get("evidence", ""),
            priority         = data.get("priority", "中"),
            suggested_action = data.get("suggested_action", ""),
        )
        s.add(obj); s.flush(); return obj.id


def list_market_signals(days: int = 7, priority: str = None,
                        country: str = None, limit: int = 50) -> List[dict]:
    from datetime import timedelta
    with get_session() as s:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = select(MarketSignal).where(
            MarketSignal.created_at >= cutoff
        ).order_by(desc(MarketSignal.created_at))
        if priority: q = q.where(MarketSignal.priority == priority)
        if country:  q = q.where(MarketSignal.country == country)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {"id": r.id,
             "signal_date": r.signal_date.isoformat() if r.signal_date else None,
             "country": r.country, "school": r.school, "product": r.product,
             "signal_type": r.signal_type, "signal_value": r.signal_value,
             "trend": r.trend, "evidence": r.evidence,
             "priority": r.priority, "suggested_action": r.suggested_action,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]


# ── 往年规律 ───────────────────────────────────────────────────
def save_yearly_pattern(data: dict) -> int:
    with get_session() as s:
        obj = YearlyPattern(
            country                    = data.get("country", ""),
            school                     = data.get("school", ""),
            product                    = data.get("product", ""),
            period_start               = data.get("period_start", ""),
            period_end                 = data.get("period_end", ""),
            pattern_summary            = data.get("pattern_summary", ""),
            historical_volume          = int(data.get("historical_volume", 0) or 0),
            conversion_rate            = float(data.get("conversion_rate", 0) or 0),
            recommended_lead_time_days = int(data.get("recommended_lead_time_days", 14) or 14),
            suggested_campaign         = data.get("suggested_campaign", ""),
        )
        s.add(obj); s.flush(); return obj.id


def list_yearly_patterns(country: str = None, school: str = None,
                         product: str = None) -> List[dict]:
    with get_session() as s:
        q = select(YearlyPattern).order_by(YearlyPattern.period_start)
        if country: q = q.where(YearlyPattern.country == country)
        if school:  q = q.where(YearlyPattern.school == school)
        if product: q = q.where(YearlyPattern.product == product)
        rows = s.execute(q).scalars().all()
        return [
            {"id": r.id, "country": r.country, "school": r.school, "product": r.product,
             "period_start": r.period_start, "period_end": r.period_end,
             "pattern_summary": r.pattern_summary,
             "historical_volume": r.historical_volume,
             "conversion_rate": r.conversion_rate,
             "recommended_lead_time_days": r.recommended_lead_time_days,
             "suggested_campaign": r.suggested_campaign}
            for r in rows
        ]


def get_current_patterns(days_window: int = 14) -> List[dict]:
    """返回当前日期前后 days_window 天内的往年规律"""
    from datetime import timedelta
    now = datetime.utcnow()
    month_day = now.strftime("%m-%d")
    with get_session() as s:
        rows = s.execute(select(YearlyPattern)).scalars().all()
        result = []
        for r in rows:
            try:
                start = r.period_start or ""
                end   = r.period_end   or ""
                if not start: continue
                # 简单字符串比较（MM-DD 格式）
                if start <= month_day <= (end or "12-31"):
                    result.append({
                        "country": r.country, "school": r.school, "product": r.product,
                        "period_start": r.period_start, "period_end": r.period_end,
                        "pattern_summary": r.pattern_summary,
                        "historical_volume": r.historical_volume,
                        "conversion_rate": r.conversion_rate,
                        "recommended_lead_time_days": r.recommended_lead_time_days,
                        "suggested_campaign": r.suggested_campaign,
                    })
            except Exception:
                pass
        return result


# ══════════════════════════════════════════════════════════════
# V5 — 老师储备容量 / 订单风险信号
# ══════════════════════════════════════════════════════════════

# ── 老师储备容量 ────────────────────────────────────────────────
def save_teacher_capacity(data: dict) -> int:
    """保存一条老师储备容量记录，返回 id"""
    with get_session() as s:
        obj = TeacherCapacity(
            subject_area      = str(data.get("subject_area", "")),
            course_type       = str(data.get("course_type", "")),
            country           = str(data.get("country", "")),
            school_experience = str(data.get("school_experience", "")),
            available_slots   = int(data.get("available_slots", 0) or 0),
            current_load      = int(data.get("current_load", 0) or 0),
            max_capacity      = int(data.get("max_capacity", 10) or 10),
            capacity_status   = str(data.get("capacity_status", "正常")),
            risk_level        = str(data.get("risk_level", "low")),
            notes             = str(data.get("notes", "")),
            updated_at        = datetime.utcnow(),
        )
        s.add(obj)
        s.flush()
        return obj.id


def list_teacher_capacity(
    subject_area: str = None,
    course_type: str = None,
    country: str = None,
) -> List[dict]:
    """查询老师储备容量列表，支持过滤条件"""
    with get_session() as s:
        q = select(TeacherCapacity).order_by(TeacherCapacity.subject_area)
        if subject_area:
            q = q.where(TeacherCapacity.subject_area == subject_area)
        if course_type:
            q = q.where(TeacherCapacity.course_type == course_type)
        if country:
            q = q.where(TeacherCapacity.country == country)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id":               r.id,
                "subject_area":     r.subject_area,
                "course_type":      r.course_type,
                "country":          r.country,
                "school_experience":r.school_experience,
                "available_slots":  r.available_slots,
                "current_load":     r.current_load,
                "max_capacity":     r.max_capacity,
                "capacity_status":  r.capacity_status,
                "risk_level":       r.risk_level,
                "notes":            r.notes,
                "updated_at":       r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


# ── 订单风险信号 ────────────────────────────────────────────────
def save_order_risk(data: dict) -> int:
    """保存一条订单风险信号，返回 id"""
    with get_session() as s:
        obj = OrderRiskSignal(
            signal_date      = data.get("signal_date", datetime.utcnow()),
            product          = str(data.get("product", "")),
            country          = str(data.get("country", "")),
            school           = str(data.get("school", "")),
            subject_area     = str(data.get("subject_area", "")),
            course_code      = str(data.get("course_code", "")),
            risk_type        = str(data.get("risk_type", "")),
            risk_level       = str(data.get("risk_level", "medium")),
            evidence         = str(data.get("evidence", "")),
            suggested_action = str(data.get("suggested_action", "")),
        )
        s.add(obj)
        s.flush()
        return obj.id


def list_order_risks(
    risk_level: str = None,
    product: str = None,
    limit: int = 50,
) -> List[dict]:
    """查询订单风险信号列表"""
    with get_session() as s:
        q = select(OrderRiskSignal).order_by(desc(OrderRiskSignal.created_at))
        if risk_level:
            q = q.where(OrderRiskSignal.risk_level == risk_level)
        if product:
            q = q.where(OrderRiskSignal.product == product)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id":               r.id,
                "signal_date":      r.signal_date.isoformat() if r.signal_date else None,
                "product":          r.product,
                "country":          r.country,
                "school":           r.school,
                "subject_area":     r.subject_area,
                "course_code":      r.course_code,
                "risk_type":        r.risk_type,
                "risk_level":       r.risk_level,
                "evidence":         r.evidence,
                "suggested_action": r.suggested_action,
                "created_at":       r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def clear_order_risks() -> int:
    """清空全部订单风险信号（重新生成前调用）"""
    with get_session() as s:
        from sqlalchemy import delete
        result = s.execute(delete(OrderRiskSignal))
        return result.rowcount


# ══════════════════════════════════════════════════════════════════
# CompanyFact — 公司事实表
# ══════════════════════════════════════════════════════════════════

def save_company_fact(data: dict) -> int:
    """新增一条公司事实（默认 is_active=False，等待人工确认）"""
    with get_session() as s:
        obj = CompanyFact(
            fact_type      = str(data.get("fact_type", "公司基础事实")),
            title          = str(data.get("title", "")),
            content        = str(data.get("content", "")),
            source_file    = str(data.get("source_file", "")),
            source_section = str(data.get("source_section", "")),
            confidence     = str(data.get("confidence", "medium")),
            is_active      = bool(data.get("is_active", False)),
            review_status  = str(data.get("review_status", "pending")),
            review_note    = str(data.get("review_note", "")),
            extracted_by   = str(data.get("extracted_by", "FactExtractionAgent")),
        )
        s.add(obj)
        s.flush()
        return obj.id


def list_company_facts(
    fact_type: str = None,
    is_active: bool = None,
    review_status: str = None,
    limit: int = 200,
) -> List[dict]:
    """查询公司事实列表"""
    with get_session() as s:
        q = select(CompanyFact).order_by(desc(CompanyFact.created_at))
        if fact_type:
            q = q.where(CompanyFact.fact_type == fact_type)
        if is_active is not None:
            q = q.where(CompanyFact.is_active == is_active)
        if review_status:
            q = q.where(CompanyFact.review_status == review_status)
        q = q.limit(limit)
        rows = s.execute(q).scalars().all()
        return [_fact_to_dict(r) for r in rows]


def _fact_to_dict(r: CompanyFact) -> dict:
    return {
        "id":             r.id,
        "fact_type":      r.fact_type,
        "title":          r.title,
        "content":        r.content,
        "source_file":    r.source_file,
        "source_section": r.source_section,
        "confidence":     r.confidence,
        "is_active":      r.is_active,
        "review_status":  r.review_status,
        "review_note":    r.review_note,
        "extracted_by":   r.extracted_by,
        "created_at":     r.created_at.isoformat() if r.created_at else None,
        "updated_at":     r.updated_at.isoformat() if r.updated_at else None,
    }


def update_fact_status(fact_id: int, review_status: str, review_note: str = "", is_active: bool = None) -> bool:
    """更新事实审核状态；review_status: confirmed/modified/rejected/inaccurate"""
    with get_session() as s:
        obj = s.get(CompanyFact, fact_id)
        if not obj:
            return False
        obj.review_status = review_status
        if review_note:
            obj.review_note = review_note
        if is_active is None:
            obj.is_active = (review_status == "confirmed")
        else:
            obj.is_active = is_active
        obj.updated_at = datetime.utcnow()
        return True


def update_fact_content(fact_id: int, content: str, review_note: str = "") -> bool:
    """修改事实内容（人工修改后启用）"""
    with get_session() as s:
        obj = s.get(CompanyFact, fact_id)
        if not obj:
            return False
        obj.content = content
        obj.review_status = "modified"
        obj.is_active = True
        if review_note:
            obj.review_note = review_note
        obj.updated_at = datetime.utcnow()
        return True


def get_active_facts_for_prompt(fact_types: List[str] = None) -> List[dict]:
    """获取所有已确认事实，供 Agent 构建 prompt 使用"""
    with get_session() as s:
        q = select(CompanyFact).where(CompanyFact.is_active == True).order_by(CompanyFact.fact_type)
        if fact_types:
            from sqlalchemy import or_
            q = q.where(CompanyFact.fact_type.in_(fact_types))
        rows = s.execute(q).scalars().all()
        return [_fact_to_dict(r) for r in rows]


def count_facts_by_type() -> dict:
    """统计各 fact_type 已确认 / 待确认数量，供缺口清单使用"""
    with get_session() as s:
        from sqlalchemy import func
        rows = s.execute(
            select(CompanyFact.fact_type, CompanyFact.is_active,
                   func.count(CompanyFact.id).label("cnt"))
            .group_by(CompanyFact.fact_type, CompanyFact.is_active)
        ).all()
        result: dict = {}
        for fact_type, is_active, cnt in rows:
            if fact_type not in result:
                result[fact_type] = {"confirmed": 0, "pending": 0, "total": 0}
            if is_active:
                result[fact_type]["confirmed"] += cnt
            else:
                result[fact_type]["pending"] += cnt
            result[fact_type]["total"] += cnt
        return result


# ══════════════════════════════════════════════════════════════════
# BusinessDictionary — 业务词典表
# ══════════════════════════════════════════════════════════════════

def save_dictionary_term(data: dict) -> int:
    """新增或更新一条业务词典条目（按 standard_term 去重）"""
    with get_session() as s:
        existing = s.execute(
            select(BusinessDictionaryTerm).where(
                BusinessDictionaryTerm.standard_term == data.get("standard_term", "")
            )
        ).scalar_one_or_none()
        if existing:
            existing.aliases         = data.get("aliases", existing.aliases)
            existing.forbidden_terms = data.get("forbidden_terms", existing.forbidden_terms)
            existing.description     = data.get("description", existing.description)
            existing.source_file     = data.get("source_file", existing.source_file)
            existing.is_active       = bool(data.get("is_active", True))
            existing.updated_at      = datetime.utcnow()
            return existing.id
        obj = BusinessDictionaryTerm(
            term_type      = str(data.get("term_type", "部门名称")),
            standard_term  = str(data.get("standard_term", "")),
            aliases        = data.get("aliases", []),
            forbidden_terms= data.get("forbidden_terms", []),
            description    = str(data.get("description", "")),
            source_file    = str(data.get("source_file", "")),
            is_active      = bool(data.get("is_active", True)),
        )
        s.add(obj)
        s.flush()
        return obj.id


def list_dictionary_terms(term_type: str = None, is_active: bool = True) -> List[dict]:
    """查询词典条目"""
    with get_session() as s:
        q = select(BusinessDictionaryTerm).order_by(BusinessDictionaryTerm.term_type)
        if term_type:
            q = q.where(BusinessDictionaryTerm.term_type == term_type)
        if is_active is not None:
            q = q.where(BusinessDictionaryTerm.is_active == is_active)
        rows = s.execute(q).scalars().all()
        return [_term_to_dict(r) for r in rows]


def _term_to_dict(r: BusinessDictionaryTerm) -> dict:
    return {
        "id":             r.id,
        "term_type":      r.term_type,
        "standard_term":  r.standard_term,
        "aliases":        r.aliases or [],
        "forbidden_terms":r.forbidden_terms or [],
        "description":    r.description,
        "source_file":    r.source_file,
        "is_active":      r.is_active,
        "created_at":     r.created_at.isoformat() if r.created_at else None,
    }


def get_forbidden_terms() -> List[str]:
    """获取所有禁用词列表（用于注入 prompt 约束）"""
    terms = list_dictionary_terms(is_active=True)
    forbidden = []
    for t in terms:
        forbidden.extend(t.get("forbidden_terms") or [])
    return list(set(forbidden))


def get_standard_terms_map() -> dict:
    """返回 {禁用词/别名: 标准词} 映射，用于自动替换"""
    terms = list_dictionary_terms(is_active=True)
    mapping = {}
    for t in terms:
        std = t["standard_term"]
        for alias in (t.get("aliases") or []):
            mapping[alias] = std
        for fb in (t.get("forbidden_terms") or []):
            mapping[fb] = std
    return mapping


def seed_default_dictionary():
    """初始化默认词典（部门名称和产品名称），仅在词典为空时执行"""
    existing = list_dictionary_terms(is_active=None)
    if existing:
        return  # 已有数据，跳过

    defaults = [
        # ── 部门名称 ──
        {"term_type": "部门名称", "standard_term": "推广部",
         "aliases": ["市场", "营销", "内容推广", "推广"],
         "forbidden_terms": ["市场部", "营销部"],
         "description": "负责小红书、朋友圈、社群、海报、推广素材，制造咨询入口。",
         "source_file": "knowledge_base/01_部门职责/自动化营销系统审查_部门职责与业务规则说明.docx"},
        {"term_type": "部门名称", "standard_term": "顾问",
         "aliases": ["销售", "客户顾问", "咨询顾问"],
         "forbidden_terms": ["销售部", "销售团队"],
         "description": "负责客户跟进、报价、异议处理、成交、复购、转介绍。",
         "source_file": "knowledge_base/01_部门职责/自动化营销系统审查_部门职责与业务规则说明.docx"},
        {"term_type": "部门名称", "standard_term": "学管",
         "aliases": ["后端交付", "服务管理", "学管部"],
         "forbidden_terms": ["后端"],
         "description": "负责老师资源匹配、订单交付、DDL管控、售后风险管理。",
         "source_file": "knowledge_base/01_部门职责/自动化营销系统审查_部门职责与业务规则说明.docx"},
        {"term_type": "部门名称", "standard_term": "后台",
         "aliases": ["产品配置", "系统支持", "数据维护", "产品后台"],
         "forbidden_terms": ["产品部"],
         "description": "负责产品资料维护、系统配置、数据沉淀、规则制定。",
         "source_file": "knowledge_base/01_部门职责/自动化营销系统审查_部门职责与业务规则说明.docx"},
        # ── 产品名称 ──
        {"term_type": "产品名称", "standard_term": "课业辅导（单次）",
         "aliases": ["单次辅导", "普通辅导", "regular"],
         "forbidden_terms": ["普通课", "散单", "单课"],
         "description": "单次作业/Essay/考试/Report辅导，按需下单。",
         "source_file": "knowledge_base/02_产品体系/"},
        {"term_type": "产品名称", "standard_term": "Final精准押题",
         "aliases": ["押题", "final押题", "final_prediction"],
         "forbidden_terms": ["押题服务", "考前押题服务"],
         "description": "基于课程资料预测考试重点，输出押题卷+知识点地图。",
         "source_file": "knowledge_base/02_产品体系/Final精准押题_产品说明_v1.md"},
        {"term_type": "产品名称", "standard_term": "毕业论文辅导（Dissertation）",
         "aliases": ["论文辅导", "dissertation", "毕业论文"],
         "forbidden_terms": ["论文代写"],
         "description": "毕业论文/大论文全程辅导，覆盖选题到终稿。",
         "source_file": "knowledge_base/02_产品体系/Dissertation_产品说明_v1.md"},
        {"term_type": "产品名称", "standard_term": "学年包",
         "aliases": ["年包", "annual_package", "全年包"],
         "forbidden_terms": ["年度套餐", "全年套餐"],
         "description": "全学年GPA托管服务，含VIP师资、双人质检、GPA管家。",
         "source_file": "knowledge_base/02_产品体系/学年包_产品说明_v1.md"},
        {"term_type": "产品名称", "standard_term": "保过辅导",
         "aliases": ["guaranteed", "保过", "包过"],
         "forbidden_terms": ["保过服务", "包过辅导服务"],
         "description": "考试/写作全程辅导，不过退款。",
         "source_file": "knowledge_base/02_产品体系/保过辅导_产品说明_v1.md"},
        {"term_type": "产品名称", "standard_term": "DP高端服务（Distinction Pass）",
         "aliases": ["DP", "dp_premium", "DP服务", "Distinction Pass"],
         "forbidden_terms": ["高端服务", "VIP服务", "顶级服务"],
         "description": "以Distinction为目标，合同约定分数，达不到按比例退款。",
         "source_file": "knowledge_base/02_产品体系/DP高端服务_产品说明_v1.md"},
        {"term_type": "产品名称", "standard_term": "AI合规学习",
         "aliases": ["AI合规", "ai_compliance"],
         "forbidden_terms": [],
         "description": "帮助学生合规使用AI工具，规避学术风险。",
         "source_file": "knowledge_base/02_产品体系/AI合规学习_产品说明_v1.md"},
    ]

    for d in defaults:
        save_dictionary_term(d)


# ─────────────────────────────────────────
# 学校机会评分 CRUD（V7）
# ─────────────────────────────────────────

def _school_score_to_dict(s: SchoolScore) -> dict:
    return {
        "id": s.id, "school_name": s.school_name, "country": s.country,
        "opportunity_score": s.opportunity_score, "priority_level": s.priority_level,
        "current_stage": s.current_stage, "demand_heat": s.demand_heat,
        "hot_products": s.hot_products or [], "score_reason": s.score_reason or [],
        "internal_evidence": s.internal_evidence or [], "risk_notes": s.risk_notes or [],
        "missing_data": s.missing_data or [],
        "last_scored_at": s.last_scored_at.strftime("%Y-%m-%d %H:%M") if s.last_scored_at else "",
    }


def save_school_score(data: dict) -> int:
    """按 school_name upsert：同一学校只保留最新一条评分"""
    with get_session() as s:
        row = s.execute(select(SchoolScore).where(
            SchoolScore.school_name == data["school_name"])).scalar_one_or_none()
        if row is None:
            row = SchoolScore(school_name=data["school_name"])
            s.add(row)
        for k in ("country", "opportunity_score", "priority_level", "current_stage",
                  "demand_heat", "hot_products", "score_reason", "internal_evidence",
                  "risk_notes", "missing_data"):
            if k in data:
                setattr(row, k, data[k])
        row.last_scored_at = datetime.utcnow()
        s.flush()
        return row.id


def list_school_scores(priority_level: str = None, country: str = None,
                       limit: int = 100) -> List[dict]:
    with get_session() as s:
        q = select(SchoolScore).order_by(desc(SchoolScore.opportunity_score))
        if priority_level:
            q = q.where(SchoolScore.priority_level == priority_level)
        if country:
            q = q.where(SchoolScore.country == country)
        return [_school_score_to_dict(r) for r in s.execute(q.limit(limit)).scalars()]


# ─────────────────────────────────────────
# 学校策略卡 CRUD（V7）
# ─────────────────────────────────────────

def _strategy_card_to_dict(c: SchoolStrategyCard) -> dict:
    return {
        "id": c.id, "school_name": c.school_name, "country": c.country,
        "period": c.period, "priority_level": c.priority_level,
        "current_stage": c.current_stage, "demand_heat": c.demand_heat,
        "main_product": c.main_product,
        "secondary_products": c.secondary_products or [],
        "cautious_products": c.cautious_products or [],
        "paused_products": c.paused_products or [],
        "why_this_strategy": c.why_this_strategy or [],
        "marketing_suggestions": c.marketing_suggestions or [],
        "sales_suggestions": c.sales_suggestions or [],
        "academic_support_notes": c.academic_support_notes or [],
        "backend_support_notes": c.backend_support_notes or [],
        "risk_notes": c.risk_notes or [],
        "suggested_materials": c.suggested_materials or [],
        "next_7d_prediction": c.next_7d_prediction or "",
        "next_14d_prediction": c.next_14d_prediction or "",
        "next_30d_prediction": c.next_30d_prediction or "",
        "data_evidence": c.data_evidence or [],
        "confidence": c.confidence,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
    }


def save_strategy_card(data: dict) -> int:
    """按 school_name + period upsert：每学校每周期只保留最新一张卡"""
    with get_session() as s:
        row = s.execute(select(SchoolStrategyCard).where(
            SchoolStrategyCard.school_name == data["school_name"],
            SchoolStrategyCard.period == data.get("period", "weekly"),
        )).scalar_one_or_none()
        if row is None:
            row = SchoolStrategyCard(school_name=data["school_name"],
                                     period=data.get("period", "weekly"))
            s.add(row)
        for k in ("country", "priority_level", "current_stage", "demand_heat",
                  "main_product", "secondary_products", "cautious_products",
                  "paused_products", "why_this_strategy", "marketing_suggestions",
                  "sales_suggestions", "academic_support_notes", "backend_support_notes",
                  "risk_notes", "suggested_materials", "next_7d_prediction",
                  "next_14d_prediction", "next_30d_prediction", "data_evidence",
                  "confidence"):
            if k in data:
                setattr(row, k, data[k])
        row.created_at = datetime.utcnow()
        s.flush()
        return row.id


def get_strategy_card(school_name: str, period: str = "weekly") -> Optional[dict]:
    with get_session() as s:
        row = s.execute(select(SchoolStrategyCard).where(
            SchoolStrategyCard.school_name == school_name,
            SchoolStrategyCard.period == period,
        )).scalar_one_or_none()
        return _strategy_card_to_dict(row) if row else None


def list_strategy_cards(period: str = "weekly", priority_level: str = None,
                        limit: int = 100) -> List[dict]:
    with get_session() as s:
        q = select(SchoolStrategyCard).where(SchoolStrategyCard.period == period)
        if priority_level:
            q = q.where(SchoolStrategyCard.priority_level == priority_level)
        q = q.order_by(desc(SchoolStrategyCard.created_at))
        return [_strategy_card_to_dict(r) for r in s.execute(q.limit(limit)).scalars()]


# ─────────────────────────────────────────
# Agent 运行日志 + 质量反馈 CRUD（V8）
# ─────────────────────────────────────────

def save_agent_run(data: dict) -> int:
    from .models import AgentRun
    with get_session() as s:
        row = AgentRun(
            workflow_name    = data.get("workflow_name", ""),
            agent_name       = data["agent_name"],
            agent_layer      = data.get("agent_layer", ""),
            run_id           = data.get("run_id", ""),
            status           = data.get("status", "failed"),
            input_summary    = (data.get("input_summary") or "")[:1000],
            output_summary   = (data.get("output_summary") or "")[:1000],
            error_message    = data.get("error_message"),
            tokens_used      = data.get("tokens_used", 0),
            cost_estimate    = data.get("cost_estimate", 0.0),
            duration_seconds = data.get("duration_seconds", 0.0),
            started_at       = data.get("started_at"),
            finished_at      = data.get("finished_at"),
        )
        s.add(row)
        s.flush()
        return row.id


def list_agent_runs(agent_name: str = None, status: str = None,
                    days: int = 7, limit: int = 200) -> List[dict]:
    from .models import AgentRun
    from datetime import timedelta
    with get_session() as s:
        q = select(AgentRun).order_by(desc(AgentRun.created_at))
        if agent_name:
            q = q.where(AgentRun.agent_name == agent_name)
        if status:
            q = q.where(AgentRun.status == status)
        if days:
            q = q.where(AgentRun.created_at >= datetime.utcnow() - timedelta(days=days))
        rows = s.execute(q.limit(limit)).scalars()
        return [{
            "id": r.id, "workflow_name": r.workflow_name, "agent_name": r.agent_name,
            "agent_layer": r.agent_layer, "run_id": r.run_id, "status": r.status,
            "input_summary": r.input_summary, "output_summary": r.output_summary,
            "error_message": r.error_message, "tokens_used": r.tokens_used,
            "cost_estimate": r.cost_estimate, "duration_seconds": r.duration_seconds,
            "started_at": r.started_at.strftime("%m-%d %H:%M:%S") if r.started_at else "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        } for r in rows]


def get_agent_last_runs() -> dict:
    """每个 agent 的最近一次运行（管理中心总览用）"""
    from .models import AgentRun
    with get_session() as s:
        rows = s.execute(select(AgentRun).order_by(desc(AgentRun.created_at)).limit(500)).scalars()
        latest = {}
        for r in rows:
            if r.agent_name not in latest:
                latest[r.agent_name] = {
                    "status": r.status, "error_message": r.error_message,
                    "at": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
                }
        return latest


def save_agent_feedback(data: dict) -> int:
    from .models import AgentFeedback
    with get_session() as s:
        row = AgentFeedback(
            agent_run_id        = data.get("agent_run_id"),
            agent_name          = data["agent_name"],
            feedback_user       = data.get("feedback_user", ""),
            usefulness_score    = data.get("usefulness_score"),
            accuracy_score      = data.get("accuracy_score"),
            actionability_score = data.get("actionability_score"),
            hallucination_flag  = bool(data.get("hallucination_flag", False)),
            feedback_text       = data.get("feedback_text", ""),
        )
        s.add(row)
        s.flush()
        return row.id


def list_agent_feedbacks(agent_name: str = None, limit: int = 100) -> List[dict]:
    from .models import AgentFeedback
    with get_session() as s:
        q = select(AgentFeedback).order_by(desc(AgentFeedback.created_at))
        if agent_name:
            q = q.where(AgentFeedback.agent_name == agent_name)
        return [{
            "id": r.id, "agent_run_id": r.agent_run_id, "agent_name": r.agent_name,
            "feedback_user": r.feedback_user, "usefulness_score": r.usefulness_score,
            "accuracy_score": r.accuracy_score, "actionability_score": r.actionability_score,
            "hallucination_flag": r.hallucination_flag, "feedback_text": r.feedback_text,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        } for r in s.execute(q.limit(limit)).scalars()]
