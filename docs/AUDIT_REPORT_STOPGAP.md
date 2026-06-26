# 止血重建审计报告

审计范围：`dashboard.py`、`database/models.py`、`database/crud.py`、`agents/`、`knowledge_base/company_context.py`、产品目录、角色定义、mock/sample/demo/fallback 数据入口、AI 输出校验与页面字段契约。

统一止血原则：没有真实数据库数据，页面统一显示“暂无真实数据，无法判断。”；没有 `evidence`、`confidence`、`responsible_role` 的 AI 输出不得进入正式页面；产品必须命中 `PRODUCT_CATALOG`；角色必须命中 `ROLE_DEFINITION`。

## 一、当前系统最严重的 10 个问题

1. `dashboard.py` 是巨型单文件，页面、数据读取、业务判断、AI 建议和任务创建混在一起，缺少页面级数据契约。
2. 增长预测、市场情报、学校策略、渠道作战、内容池、广告预测、战略建议、归因分析、产品推广策略等页面会在数据不足时输出类似经营结论的内容。
3. `main.py init-demo` 可直接导入 `data/*_sample.csv`，演示数据没有与正式库隔离。
4. `services/llm/rule_fallback_provider.py` 原先会在 AI 不可用时生成行动建议、日报、复盘，属于规则编造。
5. `agents/weekly_sales_suggestion_agent.py` 原先在没有绿灯产品时会硬推旧产品 `final_prediction`。
6. `dashboard.py` 产品目录页原先使用本地硬编码销售话术包，与正式 `PRODUCT_CATALOG` 不是同一事实源。
7. 新产品上线台原先上传目录写死到 `/opt/jizhi-growth-system/uploads`，本机无权限会直接报错。
8. 角色体系混乱，页面中存在 `顾问`、`学管`、`市场/推广`、`后台/产品` 等历史标签，未统一到正式五类角色。
9. 部分 CRUD 入口过去没有强制角色、产品和 AI evidence 校验，错误数据可进入正式页面。
10. 页面中仍有历史文案和归档 Agent 包含旧产品、旧角色、fallback 文案，需要后续模块化清理。

## 二、页面字段和数据库不一致

| 页面 | 问题 | 止血状态 |
|---|---|---|
| 老板驾驶舱 | 原先混入预测、战略、增长判断，不符合基础版字段契约 | 已改为只读真实任务、审批、逾期、产品上线状态、风险/反馈 |
| 产品目录与推荐台 | 原先读 `dashboard.py` 硬编码产品话术，而不是目录事实源 | 已改为读 `PRODUCT_CATALOG`，推荐只基于真实 `leads/orders` evidence |
| 新产品上线台 | 上传目录为无权限绝对路径；部门字段可保存拆错角色 | 已改为项目内 `uploads/`，关键选择和保存口统一角色 |
| 增长预测台 | 原先可用默认/推断数据输出预测 | 已进入 no_data 暂停状态 |
| 渠道作战台/学校增长情报台/产品红绿灯/营销日历/内容池/每周复盘台 | 原先可展示推广节奏、学校策略、复盘等未校验建议 | 已进入 no_data 暂停状态 |
| 市场情报台/广告预测台/战略建议台/归因分析台/产品推广策略台 | 原先可展示不完整或推断性结论 | 已进入 no_data 暂停状态 |

## 三、使用假数据/演示数据的位置

- `data/orders_sample.csv`、`data/leads_sample.csv`、`data/school_calendar_sample.csv` 是演示数据。
- `README.md` 和数据指南里仍描述 sample 数据，保留为文档和本地演示用途。
- `main.py init-demo` 已加硬开关：默认拒绝导入，只有显式 `ALLOW_DEMO_DATA=1` 才允许本地演示。
- 演示数据不得进入老板驾驶舱、增长预测、任务建议、战略建议。

## 四、会无数据输出的 Agent

已止血：

- `services/llm/rule_fallback_provider.py`：不再生成行动建议/日报/复盘，只返回 no_data。
- `agents/weekly_sales_suggestion_agent.py`：无活跃线索或无绿灯产品时不生成顾问建议；无容量证据时返回 no_data。
- `agents/channel_content_strategy_agent.py`：LLM 不可用时不再 fallback 生成渠道推广建议；每条内容策略必须通过产品/evidence/role/confidence 校验。
- `agents/product_supply_risk_agent.py`：缺少订单、老师容量、风险或市场信号时返回 no_data；缺老师容量不再视为可正常推广。
- `agents/promotion_strategy_agent.py`：近12个月真实订单少于10单不生成月度策略；AI 不可用时不保存“生成失败”或规则兜底策略。
- `services/output_contracts.py`：新增正式输出契约，统一校验 evidence、confidence、responsible_role、product。

仍建议继续审计：

- `agents/attribution_analysis_agent.py`：存在 `_fallback_insights`。
- `agents/time_window_forecast_agent.py`、`agents/weekly_review_agent.py`：需要统一接入 output contracts。
- `_archive/` 下的历史 Agent 含大量 fallback/demo 逻辑，正式系统不得引用。

## 五、角色定义错误

正式角色已锁定在 `ROLE_DEFINITION.md`：

- 管理层
- 推广/市场
- 销售/顾问/学管
- 产品/后台
- 交付/老师

已修复：

- `services/business_constants.py`、`services/guardrails.py` 统一角色别名。
- `database/crud.py save_task` 增加角色校验，不匹配不得创建任务。
- 新产品上线台关键部门选择、评审、反馈、上传保存口统一正式角色。

仍需重构：

- `dashboard.py` 历史文案仍有“顾问”“学管”分开展示。
- 新产品上线台内部清单仍保留部分历史分工文案，需要下一阶段按正式角色重写。

## 六、硬编码或编造产品

正式产品目录已锁定在 `PRODUCT_CATALOG.md` 和 `knowledge_base/product_catalog.py`：

语言班辅导、PSE跟课、HWEPT冲刺、开学前预习课、作业委托、作业辅导、考试助力、押题、包过辅导、Dissertation全流程、70+质检、降AI率、学年包、包课、DP卓越安心包、安心包、毕业无忧、AI学霸成长包。

已修复：

- `knowledge_base/product_catalog.py` 改为唯一事实源。
- `services/product_catalog_service.py` 合并目录别名。
- 产品目录与推荐台只展示目录产品。
- 新产品上线台创建/更新产品必须通过目录校验。

仍需清理：

- `dashboard.py` 历史 `PRODUCT_CATALOG` 分类话术块仍在文件中，但正式产品目录页已不再执行该块。
- 若干 Agent/文案文件仍可能含旧别名，如 `final_prediction`、`regular`、`dp_premium`，需逐步改为目录 ID 或别名校验。

## 七、已进入 no_data 状态的页面

- 渠道作战台
- 增长预测台
- 市场情报台
- 学校增长情报台
- 产品红绿灯
- 广告预测台
- 战略建议台
- 归因分析台
- 产品推广策略台
- 营销日历
- 内容池
- 每周复盘台

这些页面当前先暂停，不再输出看似真实的预测、策略、归因或建议。

## 八、可以保留的页面

- 产品目录与推荐台：可保留，已改为目录展示 + 真实数据 evidence 统计。
- 新产品上线台：可保留基础流程，仍需后续清理历史文案和角色清单。
- 老板驾驶舱基础版：可保留，已限制为真实任务、审批、逾期、产品上线状态、风险记录。

## 九、建议重做的页面

- 增长预测台
- 渠道作战台
- 市场情报台
- 学校增长情报台
- 产品红绿灯
- 广告预测台
- 战略建议台
- 归因分析台
- 产品推广策略台
- 营销日历
- 内容池
- 每周复盘台

重做前必须先定义每页的数据表、字段、空数据策略和 AI 可生成边界。

## 十、修复优先级

P0 已处理：

- no_data 统一文案。
- AI fallback 停止编造。
- 产品目录校验。
- 角色定义校验。
- 演示数据默认禁止导入。
- 三个核心页面先恢复基础可用状态。
- 新增正式输出契约 `services/output_contracts.py`，并接入建议保存、内容策略保存、关键推广 Agent。

P1 下一步：

- 清理 `dashboard.py` 中所有历史产品话术和角色拆分文案。
- 把 6 个暂停页面逐个按 `DATA_CONTRACT.md` 重写数据适配层。
- 给所有 Agent 输出统一加 schema 校验。

P2 后续：

- 拆分 `dashboard.py` 页面模块。
- 为 AI 建议表增加结构化字段：`validation_status`、`evidence`、`confidence`、`responsible_role`。
- 清理历史库中的目录外产品、错误角色、演示数据。

## 十一、本轮修改文件

- `ROLE_DEFINITION.md`
- `PRODUCT_CATALOG.md`
- `DATA_CONTRACT.md`
- `docs/AUDIT_REPORT_STOPGAP.md`
- `knowledge_base/product_catalog.py`
- `services/product_catalog_service.py`
- `services/business_constants.py`
- `services/guardrails.py`
- `services/output_contracts.py`
- `services/llm/rule_fallback_provider.py`
- `database/crud.py`
- `agents/channel_content_strategy_agent.py`
- `agents/product_supply_risk_agent.py`
- `agents/promotion_strategy_agent.py`
- `agents/weekly_sales_suggestion_agent.py`
- `dashboard.py`
- `main.py`

## 十二、下一步最小可用版本

1. 保留老板驾驶舱基础版、产品目录与推荐台、新产品上线台。
2. 暂停所有预测、战略、归因、广告建议类页面，直到数据契约完成。
3. 先接入真实数据录入和清洗：任务、审批、风险、产品上线、线索、订单。
4. 所有 AI 输出必须先通过 `validate_ai_output`，并在页面展示 `evidence`、`confidence`、`responsible_role`。
5. 完成后再进入模块化重构，把每个页面拆成“数据读取层、校验层、展示层”。
