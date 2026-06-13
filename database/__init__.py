from .db import init_db, get_session, engine
from .crud import (
    save_content, list_contents, get_content, update_content_status,
    save_campaign, list_campaigns,
    get_dashboard_stats,
    save_knowledge_doc, list_knowledge_docs, update_knowledge_doc_summary, get_knowledge_stats,
    save_feedback, list_feedbacks, update_feedback_status,
    save_suggestion, list_suggestions, update_suggestion_status,
    save_task, list_tasks, update_task_status, get_task_stats,
    save_content_usage, list_content_usages, get_usage_stats,
    start_workflow_run, finish_workflow_run, list_workflow_runs,
    save_order, list_orders, get_order_stats,
    save_lead, list_leads, get_lead_stats,
    save_school_calendar, list_school_calendar,
    save_market_signal, list_market_signals,
    save_yearly_pattern, list_yearly_patterns, get_current_patterns,
    # V5 新增
    save_teacher_capacity, list_teacher_capacity,
    save_order_risk, list_order_risks, clear_order_risks,
    # V6 知识库事实系统
    save_company_fact, list_company_facts, update_fact_status,
    update_fact_content, get_active_facts_for_prompt, count_facts_by_type,
    save_dictionary_term, list_dictionary_terms, get_forbidden_terms,
    get_standard_terms_map, seed_default_dictionary,
    # V7 学校增长情报
    save_school_score, list_school_scores,
    save_strategy_card, get_strategy_card, list_strategy_cards,
    # V8 Agent 管理
    save_agent_run, list_agent_runs, get_agent_last_runs,
    save_agent_feedback, list_agent_feedbacks,
    # V9 增长管理系统
    save_opportunity_score, list_opportunity_scores, get_opportunity_score,
    save_lead_score, list_lead_scores,
    save_campaign_prediction, list_campaign_predictions,
    save_weekly_review, list_weekly_reviews, get_weekly_review,
    update_task_extended, get_task_execution_stats,
    # V10 归因分析
    save_attribution_snapshot, get_latest_attribution, list_attribution_snapshots,
)

__all__ = [
    "init_db", "get_session", "engine",
    "save_content", "list_contents", "get_content", "update_content_status",
    "save_campaign", "list_campaigns",
    "get_dashboard_stats",
    "save_knowledge_doc", "list_knowledge_docs", "update_knowledge_doc_summary", "get_knowledge_stats",
    "save_feedback", "list_feedbacks", "update_feedback_status",
    "save_suggestion", "list_suggestions", "update_suggestion_status",
    "save_task", "list_tasks", "update_task_status", "get_task_stats",
    "save_content_usage", "list_content_usages", "get_usage_stats",
    "start_workflow_run", "finish_workflow_run", "list_workflow_runs",
    "save_order", "list_orders", "get_order_stats",
    "save_lead", "list_leads", "get_lead_stats",
    "save_school_calendar", "list_school_calendar",
    "save_market_signal", "list_market_signals",
    "save_yearly_pattern", "list_yearly_patterns", "get_current_patterns",
    # V5 新增
    "save_teacher_capacity", "list_teacher_capacity",
    "save_order_risk", "list_order_risks", "clear_order_risks",
    # V6 知识库事实系统
    "save_company_fact", "list_company_facts", "update_fact_status",
    "update_fact_content", "get_active_facts_for_prompt", "count_facts_by_type",
    "save_dictionary_term", "list_dictionary_terms", "get_forbidden_terms",
    "get_standard_terms_map", "seed_default_dictionary",
    # V7 学校增长情报
    "save_school_score", "list_school_scores",
    "save_strategy_card", "get_strategy_card", "list_strategy_cards",
    # V8 Agent 管理
    "save_agent_run", "list_agent_runs", "get_agent_last_runs",
    "save_agent_feedback", "list_agent_feedbacks",
    # V9 增长管理系统
    "save_opportunity_score", "list_opportunity_scores", "get_opportunity_score",
    "save_lead_score", "list_lead_scores",
    "save_campaign_prediction", "list_campaign_predictions",
    "save_weekly_review", "list_weekly_reviews", "get_weekly_review",
    "update_task_extended", "get_task_execution_stats",
    # V10 归因分析
    "save_attribution_snapshot", "get_latest_attribution", "list_attribution_snapshots",
]
