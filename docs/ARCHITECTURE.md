# 系统架构

极致教育增长作战系统 · 技术架构说明

## 总览

```
用户浏览器
   │
   ▼
Nginx (80) ──反向代理──► Streamlit dashboard.py (8501)
                              │
                              ├── agents/        26 个 Claude agent
                              ├── database/      SQLAlchemy + SQLite (marketing.db, 19 张表)
                              ├── services/      业务常量 / 对象存储接口
                              └── knowledge_base/ 12 个分类目录（业务文档，不进 git）

CLI: main.py（init / weekly / daily / health-check / ingest-* 等命令）
定时任务: crontab（deploy/crontab.example）+ 企业微信 webhook 推送
```

## 知识落地链路（防幻觉核心设计）

```
上传文件 → FactExtractionAgent 提取
        → company_facts (is_active=False, 待审核)
        → 人工在「公司资料学习中心」确认
        → GroundedBusinessAgent.get_context() 只读已确认事实
        → 业务 agent 生成（无确认事实则 can_generate=False，直接拒绝生成）
```

业务词典 business_dictionary 同时提供禁用词约束，注入每个生成 prompt。

## 数据库（19 张表）

核心业务表：orders（订单）、leads（线索）、company_facts（公司事实）、
business_dictionary（业务词典）、products、teacher_capacity。

支撑表：schools、campaigns、knowledge_docs、contents、tasks、
strategy_suggestions、workflow_runs、market_signals、yearly_patterns、
school_calendar、order_risk_signals、department_feedback、content_usage。

## 部署

- 服务器：阿里云 ECS（Ubuntu 22.04），路径 /opt/jizhi-growth-system
- 进程管理：systemd（deploy/jizhi-growth.service，崩溃自动重启）
- 反向代理：Nginx（deploy/jizhi-growth.nginx.conf）
- 备份：deploy/backup_sqlite.sh，保留 14 天
- 代码同步：GitHub 私有仓库 → 服务器 git pull → systemctl restart jizhi-growth

## 安全边界

以下内容永远不进 git（.gitignore 已配置）：
`.env`、`marketing.db`、真实订单/线索 CSV、knowledge_base 业务文档。

## 存储演进路线

当前文件存本地磁盘；`services/object_storage.py` 已预留 Cloudflare R2 接口，
配置 R2_* 环境变量后自动切换，调用方无需改代码。
