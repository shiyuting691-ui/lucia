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
    # CRM 同步
    upsert_lead_from_crm, upsert_order_from_crm,
    # 执行反馈
    save_execution_feedback, list_execution_feedbacks,
    update_execution_feedback, get_execution_feedback_stats,
    # LLM 调用日志
    save_llm_call_log,
    # Phase 2（旧，兼容保留）
    save_channel_content_recommendation, list_channel_content_recommendations,
    update_channel_content_status,
    save_time_window_forecast, list_time_window_forecasts,
    get_latest_time_window_forecasts,
    # Phase 2 v2：统一表名 + 新表
    save_content_strategy_recommendation, list_content_strategy_recommendations,
    update_content_strategy_status,
    save_channel_content, list_channel_contents, update_channel_content,
    record_channel_content_result,
    save_weekly_growth_brief, get_latest_growth_brief,
    list_growth_briefs, mark_growth_brief_pushed,
    save_time_window_forecast_v2, get_latest_forecasts_by_window,
    # V11 新产品上线台
    save_product_launch, list_product_launches, get_product_launch,
    update_product_launch, delete_product_launch,
    migrate_product_launch_v2,
    save_gate_review, list_gate_reviews,
    save_dept_feedback, list_dept_feedbacks, update_dept_feedback_status,
    save_uploaded_file, list_uploaded_files, delete_uploaded_file,
    save_internal_message, list_internal_messages, migrate_files_messages,
    save_deliverable, list_deliverables, update_deliverable, delete_deliverable, migrate_deliverables,
    # V12 三层需求预测
    save_school_academic_calendar, list_school_academic_calendars, upsert_school_academic_calendar,
    save_course_assessment_v2, list_course_assessments_v2, delete_course_assessments_v2,
    save_major_demand_profile, list_major_demand_profiles,
    save_demand_forecast_signal, list_demand_forecast_signals, clear_expired_forecast_signals,
    upsert_data_source, list_data_sources, migrate_demand_tables,
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
    # CRM 同步
    "upsert_lead_from_crm", "upsert_order_from_crm",
    # 执行反馈
    "save_execution_feedback", "list_execution_feedbacks",
    "update_execution_feedback", "get_execution_feedback_stats",
    # LLM 调用日志
    "save_llm_call_log",
    # Phase 2（旧，兼容保留）
    "save_channel_content_recommendation", "list_channel_content_recommendations",
    "update_channel_content_status",
    "save_time_window_forecast", "list_time_window_forecasts",
    "get_latest_time_window_forecasts",
    # Phase 2 v2
    "save_content_strategy_recommendation", "list_content_strategy_recommendations",
    "update_content_strategy_status",
    "save_channel_content", "list_channel_contents", "update_channel_content",
    "record_channel_content_result",
    "save_weekly_growth_brief", "get_latest_growth_brief",
    "list_growth_briefs", "mark_growth_brief_pushed",
    "save_time_window_forecast_v2", "get_latest_forecasts_by_window",
    # V11 新产品上线台
    "save_product_launch", "list_product_launches", "get_product_launch",
    "update_product_launch", "delete_product_launch",
    "migrate_product_launch_v2",
    "save_gate_review", "list_gate_reviews",
    "save_dept_feedback", "list_dept_feedbacks", "update_dept_feedback_status",
    "save_uploaded_file", "list_uploaded_files", "delete_uploaded_file",
    "save_internal_message", "list_internal_messages", "migrate_files_messages",
    "save_deliverable", "list_deliverables", "update_deliverable", "delete_deliverable", "migrate_deliverables",
    # V12 三层需求预测
    "save_school_academic_calendar", "list_school_academic_calendars", "upsert_school_academic_calendar",
    "save_course_assessment_v2", "list_course_assessments_v2", "delete_course_assessments_v2",
    "save_major_demand_profile", "list_major_demand_profiles",
    "save_demand_forecast_signal", "list_demand_forecast_signals", "clear_expired_forecast_signals",
    "upsert_data_source", "list_data_sources", "migrate_demand_tables",
]
