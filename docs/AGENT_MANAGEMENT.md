# Agent 管理体系（V8）

## 一、五层架构

| 层 | 职责 | Agent |
|---|---|---|
| 事实层 | 资料、事实、标准词，不生成业务建议 | GroundedBusinessAgent（事实门卫）、FactExtractionAgent、BusinessContextAgent |
| 数据层 | 读取、导入、清洗、聚合数据 | DataIngestionAgent、SchoolMarketIntelligenceAgent、HistoricalPatternAgent、SchoolOpportunityScoringAgent、~~ExamCalendarAgent(废弃)~~ |
| 判断层 | 机会/风险/优先级判断 | PromotionStrategyAgent、ProductSupplyRiskAgent、InsightAgent、SchoolStrategyCardAgent |
| 生成层 | 判断后生成内容、话术、素材 | WeeklyMarketing/WeeklySales SuggestionAgent、ContentGenerationAgent、SalesMaterialAgent、ReferralMaterialAgent、PosterAgent(停)、ProductLaunchAgent(停)、PlanningAgent(停) |
| 审核与分发层 | 审核、提醒、任务、推送、反馈 | RiskReviewAgent、DailyEffectiveReminderAgent、DepartmentTaskAgent、DistributionAgent、FormatterAgent、FeedbackCollectorAgent(停)、ProductImprovementAgent(停)、~~OrchestratorAgent(废弃)~~ |

## 二、启停现状

- **默认启用（核心闭环）**：GroundedBusiness、FactExtraction、DataIngestion、PromotionStrategy、ProductSupplyRisk、WeeklyMarketing、WeeklySales、ContentGeneration、SalesMaterial、RiskReview、DailyEffectiveReminder、Distribution、SchoolOpportunityScoring、SchoolStrategyCard、ReferralMaterial
- **暂停**：Poster、ProductLaunch、ProductImprovement、FeedbackCollector、Planning（停用≠删除，改 yaml 即可恢复）
- **废弃**：OrchestratorAgent（被 workflows/ 取代）、ExamCalendarAgent（LLM 推断考试日期违反"不编造学校节点"原则）。deprecated 状态 AgentRunner 直接拒绝调用
- **待确认（experimental）**：BusinessContext、Insight、DepartmentTask

## 三、AgentRunner 调用机制

`services/agent_runner.py`，workflow 统一通过它调用 Agent：

```python
from services.agent_runner import AgentRunner
runner = AgentRunner(workflow_name="weekly_promotion")
r = runner.run("WeeklySalesSuggestionAgent",
               lambda: agent.generate(week_start=ws),
               input_summary="week=2026-06-08")
# r = {"agent_name", "status", "output", "error_message", "run_id", "duration_seconds"}
```

执行顺序：
1. registry 登记检查（未登记 → skipped）
2. enabled 检查（停用 → skipped）
3. deprecated 拦截（废弃 → skipped，不允许调用）
4. GBA 强制前置（`GROUNDING_REQUIRED` 名单内的 agent，can_generate=False → **blocked**，不运行下游）
5. 执行 + 捕获异常（错误写入 error_message，不静默吞掉）
6. 写入 agent_runs（success / failed / skipped / blocked 四态全记录）

已接入：WeeklyPromotionWorkflow、DailyReminderWorkflow。其余 workflow 逐步迁移。

## 四、必须过 GroundedBusinessAgent 的 Agent

PromotionStrategy、ProductSupplyRisk、WeeklyMarketing、WeeklySales、ContentGeneration、SalesMaterial、Referral、ProductLaunch、Poster、SchoolStrategyCard（共10个，见 `agent_registry.GROUNDING_REQUIRED`）。
SchoolOpportunityScoringAgent 豁免：纯规则计算不调用 LLM，无编造可能。

## 五、数据表

**agent_runs** — 每次 Agent 运行一条：workflow_name / agent_name / agent_layer / run_id / status(success·failed·skipped·blocked) / input_summary / output_summary / error_message / tokens_used / cost_estimate / duration_seconds / started_at / finished_at

**agent_feedbacks** — 人工质量评分：agent_run_id / usefulness_score / accuracy_score / actionability_score（各1-5）/ hallucination_flag / feedback_text。用于判断 Agent 是否有价值、优化 prompt。

## 六、常用操作

- **查看失败日志**：Agent 管理中心 → 运行日志 → 状态筛选 failed；或 SQL：`SELECT * FROM agent_runs WHERE status='failed' ORDER BY id DESC`
- **启停 Agent**：编辑 `config/agents.yaml` 对应条目的 `enabled` / `status`，重启服务生效，无需改代码。yaml 优先级高于 `agents/agent_registry.py` 默认值；yaml 不存在时用默认值
- **判断 Agent 是否有价值**：① 管理中心看最近30天运行次数（从未运行→考虑停用）；② 看质量反馈均分（有用<3 或幻觉标记多→优化 prompt 或停用）；③ 看 cost_estimate 与产出是否成比例
