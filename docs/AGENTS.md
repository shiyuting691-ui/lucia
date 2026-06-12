# Agent 清单

共 26 个业务 agent，全部使用 Anthropic Claude（claude-sonnet-4-6）。

## 知识基础层（所有业务生成的前置闸门）

| Agent | 文件 | 职能 |
|-------|------|------|
| GroundedBusinessAgent | grounded_business_agent.py | 生成前闸门：读取已确认的 company_facts + business_dictionary，无确认事实时阻止下游生成（can_generate=False） |
| FactExtractionAgent | fact_extraction_agent.py | 从上传文件（docx/pdf/html/md/txt）提取业务事实，存入 company_facts（is_active=False，待人工审核） |

## 策略生成层（已接入 GroundedBusinessAgent）

| Agent | 文件 | 职能 |
|-------|------|------|
| PromotionStrategyAgent | promotion_strategy_agent.py | 月度产品推广策略 |
| WeeklyMarketingSuggestionAgent | weekly_marketing_suggestion_agent.py | 推广部每周建议 |
| WeeklySalesSuggestionAgent | weekly_sales_suggestion_agent.py | 顾问团队每周销售建议 |
| ContentGenerationAgent | content_generation_agent.py | 内容池文案生成 |
| RiskReviewAgent | risk_review_agent.py | 内容风控审核（禁用承诺用语） |
| DepartmentTaskAgent | department_task_agent.py | 部门任务拆解 |
| DailyEffectiveReminderAgent | daily_effective_reminder_agent.py | 每日有效动作提醒 |
| SalesMaterialAgent | sales_material_agent.py | 销售素材生成 |
| ProductSupplyRiskAgent | product_supply_risk_agent.py | 产品交付/师资供给风险 |

## 数据层

| Agent | 文件 | 职能 |
|-------|------|------|
| DataIngestionAgent | data_ingestion_agent.py | 订单/线索 CSV 导入 |
| InsightAgent | insight_agent.py | 数据洞察 |
| HistoricalPatternAgent | historical_pattern_agent.py | 历史规律分析（yearly_patterns） |
| SchoolMarketIntelligenceAgent | school_market_intelligence_agent.py | 学校市场情报 |
| ExamCalendarAgent | exam_calendar_agent.py | 考试日历（school_calendar） |

## 其他

orchestrator（编排）、planning_agent、distribution_agent、poster_agent、
referral_material_agent、feedback_collector_agent、formatter_agent、
product_improvement_agent、product_launch_agent、business_context_agent。

## 调用约定

所有策略生成 agent 在调用 Claude 前必须先执行：

```python
gba_ctx = self._gba.get_context(task_type)
if not gba_ctx["can_generate"]:
    return {"error": ..., "missing_info": gba_ctx["missing_information"]}
```

部门名称必须使用 `services/business_constants.py` 中的 `VALID_DEPARTMENTS`，
禁止硬编码"市场部""销售部"等错误叫法。
