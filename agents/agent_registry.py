"""
Agent Registry — 全系统 Agent 统一登记表（V8）

五层架构：事实层 / 数据层 / 判断层 / 生成层 / 审核与分发层
status: active / paused / deprecated / experimental

config/agents.yaml 中的 enabled/status 优先级高于本文件默认值；
配置文件不存在时使用本表默认值。停用只是不参与 workflow，不删代码。
"""
from pathlib import Path

LAYERS = ("事实层", "数据层", "判断层", "生成层", "审核与分发层")

# 必须先经过 GroundedBusinessAgent 的下游业务 Agent
GROUNDING_REQUIRED = {
    "PromotionStrategyAgent", "ProductSupplyRiskAgent",
    "WeeklyMarketingSuggestionAgent", "WeeklySalesSuggestionAgent",
    "ContentGenerationAgent", "SalesMaterialAgent", "ReferralMaterialAgent",
    "ProductLaunchAgent", "PosterAgent", "SchoolStrategyCardAgent",
    # SchoolOpportunityScoringAgent 纯规则计算不调用LLM，豁免
}

def _a(display, layer, desc, *, enabled=True, grounding=False, llm=True,
       db=False, notify=False, workflows=None, status="active", owner="系统"):
    return {
        "display_name": display, "layer": layer, "description": desc,
        "enabled": enabled, "requires_grounding": grounding, "uses_llm": llm,
        "writes_database": db, "sends_notification": notify,
        "default_workflows": workflows or [], "owner": owner, "status": status,
    }

AGENT_REGISTRY = {
    # ── 事实层 ──
    "GroundedBusinessAgent": _a("事实门卫", "事实层",
        "读取已确认公司事实和业务词典，判定 can_generate，防止业务脑补。",
        llm=False, workflows=["all_business_generation"]),
    "FactExtractionAgent": _a("事实提取器", "事实层",
        "从上传文件提取业务事实写入 company_facts（待人工审核）。",
        db=True, workflows=["资料上传中心"]),
    "BusinessContextAgent": _a("业务上下文聚合", "事实层",
        "聚合当前业务上下文快照供其他agent使用。与GBA部分重叠，待确认。",
        llm=False, db=True, workflows=["daily"], status="experimental"),

    # ── 数据层 ──
    "DataIngestionAgent": _a("数据导入器", "数据层",
        "导入订单/线索CSV，清洗写入 orders/leads。",
        llm=False, db=True, workflows=["ingest-orders", "ingest-leads"]),
    "SchoolMarketIntelligenceAgent": _a("市场情报聚合", "数据层",
        "聚合订单/咨询/节点数据生成市场信号写入 market_signals。",
        db=True, workflows=["daily", "update-market-signals"]),
    "HistoricalPatternAgent": _a("历史规律分析", "数据层",
        "分析历史订单规律写入 yearly_patterns。低频使用。",
        db=True, workflows=["analyze-history"]),
    "ExamCalendarAgent": _a("考试日历推断", "数据层",
        "用LLM推断考试日期——违反'不编造学校节点'原则，建议废弃。",
        enabled=False, status="deprecated", workflows=["orchestrator(旧)"]),
    "SchoolOpportunityScoringAgent": _a("学校机会评分", "数据层",
        "纯规则计算学校机会分写入 school_scores，不调用LLM不编造。",
        llm=False, db=True, workflows=["weekly_promotion", "update-school-scores"]),
    "LeadOpportunityScoringAgent": _a("线索机会评分", "数据层",
        "纯规则计算线索机会分写入 lead_scores，不调用LLM。",
        llm=False, db=True, workflows=["daily_execution", "update-lead-scores"]),
    "CampaignPredictionAgent": _a("广告预测", "判断层",
        "规则计算预测区间，Claude只写钩子/推理，输出写 campaign_predictions。",
        grounding=False, db=True, workflows=["weekly_growth", "predict-campaigns"]),
    "WeeklyReviewAgent": _a("周复盘生成", "生成层",
        "对比预测与实际，分析执行完成度，输出周复盘写入 weekly_reviews。",
        grounding=False, db=True, workflows=["weekly_review"]),

    # ── 判断层 ──
    "PromotionStrategyAgent": _a("月度推广策略", "判断层",
        "基于已确认事实生成月度推广策略。",
        grounding=True, db=True, workflows=["monthly_promotion"]),
    "ProductSupplyRiskAgent": _a("供给风险分析", "判断层",
        "基于老师储备和订单风险输出产品推广边界灯。",
        llm=False, grounding=True, db=True, workflows=["weekly_promotion"]),
    "InsightAgent": _a("数据洞察", "判断层",
        "对订单咨询数据生成洞察。无GBA约束，待确认使用场景。",
        workflows=["CLI"], status="experimental"),
    "SchoolStrategyCardAgent": _a("学校策略卡", "判断层",
        "基于学校评分+内部数据生成学校策略卡，已接GBA。",
        grounding=True, db=True,
        workflows=["weekly_promotion", "generate-school-strategy-cards"]),

    # ── 生成层 ──
    "WeeklyMarketingSuggestionAgent": _a("周市场建议", "生成层",
        "生成周度市场内容建议（4维度）。", grounding=True, db=True,
        workflows=["weekly_promotion"]),
    "WeeklySalesSuggestionAgent": _a("周销售建议", "生成层",
        "生成周度销售策略建议。", grounding=True, db=True,
        workflows=["weekly_promotion"]),
    "ContentGenerationAgent": _a("内容生成器", "生成层",
        "生成小红书/朋友圈等内容素材。", grounding=True,
        workflows=["post", "orchestrator(旧)"]),
    "SalesMaterialAgent": _a("销售素材生成", "生成层",
        "生成顾问销售素材。", grounding=True, db=True, workflows=["daily"]),
    "ReferralMaterialAgent": _a("转介绍素材", "生成层",
        "生成转介绍话术与素材。", grounding=True, workflows=["referral"]),
    "ProductLaunchAgent": _a("产品发布包", "生成层",
        "生成新品发布全套素材。当前无调用方。",
        enabled=False, grounding=True, db=True, status="paused"),
    "PosterAgent": _a("海报生成", "生成层",
        "生成海报文案并调用node渲染。暂停开发。",
        enabled=False, grounding=True, status="paused", workflows=["post --poster"]),
    "PlanningAgent": _a("营销计划(旧)", "生成层",
        "旧版营销计划生成，与PromotionStrategyAgent重复。",
        enabled=False, notify=True, status="paused", workflows=["旧流程"]),

    # ── 审核与分发层 ──
    "RiskReviewAgent": _a("风控审核", "审核与分发层",
        "审核内容是否含禁用承诺/违规表达。", workflows=["CLI", "审核流程"]),
    "DailyEffectiveReminderAgent": _a("每日有效提醒", "审核与分发层",
        "生成每日3-5条关键行动提醒。", db=True, workflows=["daily_reminder"]),
    "DepartmentTaskAgent": _a("部门任务拆解", "审核与分发层",
        "把策略拆解为部门任务。", workflows=["CLI"], status="experimental"),
    "DistributionAgent": _a("渠道分发", "审核与分发层",
        "把审核通过的内容分发到渠道（企微推送）。",
        llm=False, notify=True, workflows=["daily"]),
    "FormatterAgent": _a("消息格式化", "审核与分发层",
        "格式化企微消息并推送。", llm=False, notify=True, workflows=["CLI推送"]),
    "FeedbackCollectorAgent": _a("反馈收集", "审核与分发层",
        "收集部门反馈。当前反馈闭环未启用。",
        enabled=False, db=True, status="paused", workflows=["daily"]),
    "ProductImprovementAgent": _a("产品改进建议", "审核与分发层",
        "基于反馈生成产品改进建议。依赖反馈闭环，暂停。",
        enabled=False, status="paused", workflows=["CLI"]),
    "OrchestratorAgent": _a("旧版编排器", "审核与分发层",
        "早期编排器，已被 workflows/ 体系取代。不允许新代码调用。",
        enabled=False, llm=False, db=True, status="deprecated",
        workflows=["main.py init/daily/weekly(旧)"]),
}


def load_registry() -> dict:
    """合并 config/agents.yaml 覆盖项后返回最终 registry"""
    import copy
    reg = copy.deepcopy(AGENT_REGISTRY)
    cfg_path = Path(__file__).parent.parent / "config" / "agents.yaml"
    if cfg_path.exists():
        try:
            import yaml
            overrides = (yaml.safe_load(cfg_path.read_text()) or {}).get("agents", {})
            for name, ov in overrides.items():
                if name in reg and isinstance(ov, dict):
                    for k in ("enabled", "status", "owner"):
                        if k in ov:
                            reg[name][k] = ov[k]
        except Exception:
            pass  # 配置文件损坏时退回默认值，不影响启动
    return reg


def get_agent_info(agent_name: str) -> dict | None:
    return load_registry().get(agent_name)


def is_callable(agent_name: str) -> tuple[bool, str]:
    """workflow 调用前检查：返回 (是否可调用, 原因)"""
    info = get_agent_info(agent_name)
    if info is None:
        return False, f"{agent_name} 未在 registry 登记"
    if info["status"] == "deprecated":
        return False, f"{agent_name} 已废弃（{info['description'][:30]}）"
    if not info["enabled"]:
        return False, f"{agent_name} 已停用（status={info['status']}）"
    return True, ""
