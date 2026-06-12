# 数据准备指南 · DATA_PREPARATION_GUIDE

> 本文档说明系统所需的每类数据：存储位置、填写规范、导入方式、以及导入后被哪些 Agent 使用。  
> 最后更新：2026-06-11

---

## 目录

1. [订单数据 orders.csv](#1-订单数据-orderscsv)
2. [线索数据 leads.csv](#2-线索数据-leadscsv)
3. [学校日历 school_calendar.csv](#3-学校日历-school_calendarcsv)
4. [产品知识库 knowledge_base/01_产品知识库/](#4-产品知识库)
5. [销售话术库 knowledge_base/02_销售话术库/](#5-销售话术库)
6. [风控表达库 knowledge_base/06_风控表达库/](#6-风控表达库)
7. [配置文件 config.yaml](#7-配置文件-configyaml)

---

## 1. 订单数据 orders.csv

**存储位置：** `data/orders.csv`  
**模板文件：** `data/orders_template.csv`

### 字段说明

| 字段 | 说明 | 示例 | 必填 |
|------|------|------|------|
| order_date | 下单日期，格式 YYYY-MM-DD | 2026-06-01 | ✅ |
| school | 学校名称，与 config.yaml 中一致 | UCL / LSE / 悉大 | ✅ |
| country | 国家，UK 或 Australia | UK | ✅ |
| product | 产品 ID，见下方产品列表 | dissertation / guaranteed / annual_package | ✅ |
| course_code | 课程代码（选填） | ECON3001 | ❌ |
| deadline | 交付/考试截止日期，YYYY-MM-DD | 2026-06-25 | ✅ |
| amount | 订单金额（人民币） | 9000 | ✅ |
| sales_owner | 负责销售姓名 | Lucia / 销售A | ✅ |
| status | 订单状态：completed / in_progress / cancelled | completed | ✅ |

**产品 ID 对照表：**
- `dissertation` — 论文辅导
- `guaranteed` — 保过辅导
- `annual_package` — 学年包
- `dp_premium` — DP 高端服务
- `ai_learning` — AI 合规学习
- `final_prediction` — Final 精准押题

### 如何导入

```bash
# 复制模板，填入真实数据后执行：
uv run --with sqlalchemy --with pandas main.py ingest-orders data/orders.csv
```

导入成功后会输出：`✅ 成功导入 N 条订单`

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| DataIngestionAgent | 解析并写入数据库 |
| HistoricalPatternAgent | 分析历史规律，识别旺季淡季 |
| SchoolMarketIntelligenceAgent | 统计各校订单趋势，生成市场信号 |
| BusinessContextAgent | 读取订单统计，构建当日销售背景 |
| SalesMaterialAgent | 基于热门学校/产品生成定向素材 |

---

## 2. 线索数据 leads.csv

**存储位置：** `data/leads.csv`  
**模板文件：** `data/leads_template.csv`

### 字段说明

| 字段 | 说明 | 示例 | 必填 |
|------|------|------|------|
| inquiry_date | 询盘日期，YYYY-MM-DD | 2026-06-01 | ✅ |
| school | 学校名称 | UCL | ✅ |
| country | 国家，UK 或 Australia | UK | ✅ |
| product_interest | 感兴趣产品（同产品 ID） | dissertation | ✅ |
| pain_point | 学生痛点（自然语言描述） | 不知道如何写研究方法章节 | ✅ |
| deadline | 学生截止日期，YYYY-MM-DD | 2026-06-25 | ❌ |
| deal_status | 成交状态：won / lost / in_progress | won | ✅ |
| lost_reason | 丢单原因（deal_status=lost 时填写） | 价格太高 / 找了其他机构 | ❌ |
| sales_owner | 负责销售姓名 | 销售A | ✅ |
| source_channel | 来源渠道：小红书 / 朋友圈 / 社群 / 私信 / 转介绍 / 其他 | 小红书 | ✅ |

### 如何导入

```bash
uv run --with sqlalchemy --with pandas main.py ingest-leads data/leads.csv
```

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| DataIngestionAgent | 解析并写入数据库 |
| SchoolMarketIntelligenceAgent | 分析询盘趋势、丢单原因，生成市场预警 |
| BusinessContextAgent | 读取线索转化率，提供销售背景 |
| FeedbackCollectorAgent | 丢单原因作为改进产品/价格的依据 |

---

## 3. 学校日历 school_calendar.csv

**存储位置：** `data/school_calendar.csv`  
**样本文件：** `data/school_calendar_sample.csv`

### 字段说明

| 字段 | 说明 | 示例 | 必填 |
|------|------|------|------|
| school | 学校名称 | UCL | ✅ |
| country | 国家 | UK | ✅ |
| event_type | 节点类型：exam_period / submission_deadline / term_start / holiday | exam_period | ✅ |
| event_name | 节点名称（自然语言） | 2026夏季期末考试周 | ✅ |
| start_date | 开始日期，YYYY-MM-DD | 2026-06-10 | ✅ |
| end_date | 结束日期，YYYY-MM-DD | 2026-06-25 | ✅ |
| notes | 备注（选填） | 覆盖所有本科课程 | ❌ |

**event_type 对照：**
- `exam_period` — 考试周（触发 Final 押题推广）
- `submission_deadline` — 论文/作业截止（触发 Dissertation 推广）
- `term_start` — 开学（触发学年包推广）
- `holiday` — 假期（静默期，减少推送）

### 如何导入

```bash
uv run --with sqlalchemy --with pandas main.py ingest-calendar data/school_calendar.csv
```

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| DataIngestionAgent | 解析并写入数据库 |
| SchoolMarketIntelligenceAgent | 识别未来 30 天节点，触发推广信号 |
| BusinessContextAgent | 提取 upcoming_nodes，写入当日营销背景 |
| SalesMaterialAgent | 根据迫近节点生成紧迫感素材 |
| DailyWorkflow | 调度整个 pipeline 的输入依据 |

---

## 4. 产品知识库

**存储位置：** `knowledge_base/01_产品知识库/`

### 文件列表

| 文件名 | 对应产品 |
|--------|----------|
| Final精准押题_产品说明_v1.md | Final 精准押题 |
| Dissertation_产品说明_v1.md | 论文辅导 |
| 学年包_产品说明_v1.md | 学年包 |
| DP高端服务_产品说明_v1.md | DP 高端服务 |
| AI合规学习_产品说明_v1.md | AI 合规学习 |
| 保过辅导_产品说明_v1.md | 保过辅导 |

### 如何填写

每个文件按以下结构填写（模板已包含所有章节，搜索 `待填写` 替换即可）：

1. **产品概述** — 适用学校、价格区间、服务周期
2. **核心卖点** — 3 条以内，供销售主推
3. **服务内容** — 具体交付内容（课时、资料、答疑等）
4. **目标用户画像** — 主要场景、痛点、决策触发点
5. **销售注意事项** — ✅可说 / ❌不可说
6. **常见问题** — Q&A 格式，供销售快速引用
7. **成功案例** — 脱敏案例（不含真实姓名）

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| SalesMaterialAgent | 生成内容时注入产品知识，确保准确性 |
| RiskReviewAgent | 校验生成内容是否符合产品说明 |
| ProductLaunchAgent | 新产品推广时读取产品说明生成 5 类内容 |

---

## 5. 销售话术库

**存储位置：** `knowledge_base/02_销售话术库/`

### 文件列表

| 文件名 | 适用场景 |
|--------|----------|
| 价格异议_销售话术_v1.md | 客户说"太贵了"/"能便宜点吗" |
| 初次接触_破冰话术_v1.md | 第一次联系潜在客户 |
| 考试季紧急推广_话术_v1.md | 考前 2-4 周，制造紧迫感 |
| 转介绍裂变_话术_v1.md | 请老客户推荐朋友 |
| 续费升级_话术_v1.md | 老客户续费或升级套餐 |
| 论文辅导_专项话术_v1.md | Dissertation 产品专项话术 |
| 保过辅导_专项话术_v1.md | Guaranteed 产品专项话术 |
| 丢单挽回_话术_v1.md | 客户已拒绝后的挽回尝试 |

### 如何填写

话术模板中 `[待填写：XXX]` 的部分按实际业务填入。填写后告知 Agent 使用对应文件。

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| SalesMaterialAgent | 生成销售跟进话术时参考 |
| ContentGenerationAgent | 生成社群/私信内容时保持话术一致性 |

---

## 6. 风控表达库

**存储位置：** `knowledge_base/06_风控表达库/`

### 文件列表

| 文件名 | 内容 |
|--------|------|
| 禁用词与高风险表达_v1.md | 绝对禁用词、高风险表达、平台特殊规则 |
| 押题产品风控规则_v1.md | Final 押题产品专项风控 |
| 小红书发布规则_v1.md | 小红书平台合规要点 |
| 企业微信群发规则_v1.md | 企业微信群发频率和内容限制 |
| 价格促销合规规范_v1.md | 促销信息发布的合规要求 |
| 学生案例使用规范_v1.md | 使用真实学生案例的授权和脱敏要求 |

### 被哪些 Agent 使用

| Agent | 用途 |
|-------|------|
| RiskReviewAgent | **核心使用方**：所有对外内容发布前必经此检查 |
| ContentGenerationAgent | 生成时自动规避禁用词 |
| SalesMaterialAgent | 话术生成时注入风控约束 |

---

## 7. 配置文件 config.yaml

**存储位置：** `config.yaml`（项目根目录）

### 关键配置项

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `anthropic.model` | 使用的 AI 模型 | claude-sonnet-4-6 |
| `schools.uk` / `schools.australia` | 目标学校列表（静态备用） | UCL / 悉大 |
| `products` | 产品列表（静态备用） | dissertation / guaranteed |
| `pilot_team` | 试点团队成员 | reviewer: Lucia |
| `wecom_webhook` | 企业微信推送 webhook | https://... |

### 如何更新

直接编辑 `config.yaml` 即可，无需导入命令。系统每次运行时自动读取最新配置。

---

## 快速启动清单

完成数据准备后，按以下顺序初始化系统：

```bash
# 1. 导入订单
uv run --with sqlalchemy --with pandas main.py ingest-orders data/orders.csv

# 2. 导入线索
uv run --with sqlalchemy --with pandas main.py ingest-leads data/leads.csv

# 3. 导入学校日历
uv run --with sqlalchemy --with pandas main.py ingest-calendar data/school_calendar.csv

# 4. 分析历史规律（自动写入 yearly_patterns 表）
uv run --with sqlalchemy --with anthropic main.py analyze-history

# 5. 生成市场信号（自动写入 market_signals 表）
uv run --with sqlalchemy --with anthropic main.py update-market-signals

# 6. 运行每日工作流（生成内容 + 推送企业微信）
uv run --with sqlalchemy --with anthropic --with requests main.py run-daily
```

或一键初始化（含样本数据）：

```bash
uv run --with sqlalchemy --with anthropic --with pandas --with requests main.py init-demo
```

---

## 数据流向图

```
CSV 文件 (orders/leads/calendar)
    ↓ DataIngestionAgent
SQLite 数据库
    ├── orders / leads 表
    │       ↓ HistoricalPatternAgent → yearly_patterns 表
    │       ↓ SchoolMarketIntelligenceAgent → market_signals 表
    │               ↓ BusinessContextAgent (当日背景)
    │                       ↓ SalesMaterialAgent (生成内容)
    │                               ↓ DistributionAgent (推送企业微信)
    └── school_calendar 表
            ↓ SchoolMarketIntelligenceAgent (upcoming_nodes)

knowledge_base/ (产品知识 / 话术 / 风控)
    ↓ 直接被 SalesMaterialAgent / RiskReviewAgent / ContentGenerationAgent 读取
```

---

*如有疑问请联系 Lucia 或查看各 Agent 源代码中的 docstring。*
