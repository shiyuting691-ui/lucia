# 极致教育增长作战系统

极致教育内部营销自动化系统，基于真实订单/线索/老师储备数据，结合 AI Agent，生成可执行的推广策略、销售建议和每日提醒。

---

## 当前 MVP 主线

```
上传公司资料 → 提取业务事实（人工确认）→ AI 生成策略建议 → 企业微信推送
数据导入（订单/线索）→ Dashboard 看板 → 周度/月度策略报告
```

---

## 技术栈

| 模块 | 技术 |
|------|------|
| Dashboard | Streamlit |
| AI | Anthropic Claude（claude-sonnet-4-6） |
| 数据库 | SQLite + SQLAlchemy ORM |
| 包管理 | pip / uv |
| 推送 | 企业微信 Webhook |
| 定时任务 | Linux crontab |
| 部署 | systemd + Nginx |
| 语言 | Python 3.11+ |

---

## 核心页面

| 页面 | 功能 |
|------|------|
| 📚 公司资料学习中心 | 上传资料 → AI 提取事实 → 人工确认 → 供 Agent 使用 |
| 📦 产品推广策略台 | 月度策略 / 周度打法 / 部门行动 / 推广素材 |
| 📊 数据概览 | 订单/线索趋势、产品销量、学校分布 |
| 🔔 每日提醒 | 高优先级客户、DDL 风险、老师未反馈 |
| 📥 资料上传中心 | 订单/线索/老师储备 CSV 数据导入 |
| 📝 内容素材库 | 小红书/朋友圈/社群内容管理 |

---

## Agent 职责摘要

| Agent | 职责 |
|-------|------|
| `FactExtractionAgent` | 从上传资料中提取业务事实，写入 company_facts（待人工确认） |
| `GroundedBusinessAgent` | 所有业务 Agent 生成前的事实检索门卫，防止 AI 脑补 |
| `PromotionStrategyAgent` | 生成月度推广策略（产品优先级/渠道/活动/升单路径） |
| `WeeklyMarketingSuggestionAgent` | 生成周度推广部行动建议和内容素材清单 |
| `WeeklySalesSuggestionAgent` | 生成周度顾问跟进建议、话术、优先线索 |
| `ProductSupplyRiskAgent` | 分析老师资源 vs 订单需求，输出推广边界（强推/正常/谨慎/暂停） |
| `DailyEffectiveReminderAgent` | 每日生成有效提醒（高意向客户/DDL 风险/老师未反馈） |
| `ContentGenerationAgent` | 生成小红书/朋友圈/社群推广内容 |
| `SalesMaterialAgent` | 生成销售话术、异议应对、转介绍脚本 |
| `RiskReviewAgent` | 内容风险审查（禁用词/合规检查） |
| `DepartmentTaskAgent` | 生成各部门（推广部/顾问/学管/后台）本周任务清单 |

---

## 本地启动

```bash
python main.py init        # 初始化数据库
python main.py health-check  # 健康检查
python main.py dashboard   # 启动 Dashboard（http://localhost:8501）
```

---

## 数据导入

```bash
python main.py ingest-orders data/orders_sample.csv
python main.py ingest-leads data/leads_sample.csv
python main.py ingest-teacher-capacity data/teacher_capacity_sample.csv
python main.py update-market-signals
python main.py update-order-risks
```

---

## 企业微信推送

在 `.env` 中配置：
```
WECHAT_WORK_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
```

手动触发推送：
```bash
python main.py run-daily-reminder    # 每日提醒
python main.py run-weekly-promotion  # 周度建议
python main.py run-monthly-promotion # 月度策略
```

---

## 服务器部署

详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

快速版：
```bash
ssh root@121.43.83.158
git clone https://github.com/shiyuting691-ui/lucia.git /opt/jizhi-growth-system
cd /opt/jizhi-growth-system
cp .env.example .env && nano .env
bash deploy/deploy.sh https://github.com/shiyuting691-ui/lucia.git
```

---

## GitHub 注意事项

以下文件**已通过 .gitignore 排除**，不会进入仓库：

- `.env`（API Key）
- `marketing.db`（数据库）
- `data/orders_2025*.csv` / `data/leads_2025*.csv`（真实业务数据）
- `knowledge_base/` 下所有业务资料文件

可以提交的文件：
- `data/*_sample.csv`（演示数据，无真实信息）
- `data/*_template.csv`（字段模板）
- `knowledge_base/*.py`（Python 代码模块）
- 所有 `.gitkeep` 目录占位文件

---

## 敏感数据说明

1. `.env` 不允许提交 GitHub
2. `marketing.db` 不允许提交 GitHub
3. 真实订单/线索/老师储备数据不允许提交 GitHub
4. 知识库业务资料（话术/产品说明/风控规则）不允许提交 GitHub
5. 服务器仅限内部访问，不建议直接对外开放
6. 当前版本为 MVP，建议后续加入访问密码或 IP 白名单

---

## 目录结构

```
├── agents/              # AI Agent 模块
├── database/            # 数据库 ORM + CRUD
├── workflows/           # 定时任务工作流
├── knowledge_base/      # 业务知识库（代码模块 + 资料目录）
├── data/                # 数据文件（sample/template 可提交）
├── deploy/              # 部署脚本
├── docs/                # 部署和使用文档
├── dashboard.py         # Streamlit Dashboard 入口
├── main.py              # CLI 命令入口
├── config.yaml          # 配置文件
├── requirements.txt     # 依赖清单
└── .env.example         # 环境变量模板
```
