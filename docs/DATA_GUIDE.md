# 数据指南

## 数据存放位置

| 数据 | 位置 | 是否进 git |
|------|------|-----------|
| 业务数据库 | marketing.db（项目根目录） | ❌ 永不提交 |
| 订单/线索原始 CSV | data/orders_2025*.csv、data/leads_2025*.csv | ❌ 永不提交 |
| 公司业务文档 | knowledge_base/00~11 分类目录 | ❌ 永不提交 |
| 模板/示例 CSV | data/*_template.csv、data/*_sample.csv | ✅ 可提交 |
| 生成产物 | outputs/ | ❌ 不提交 |

## 数据导入命令

```bash
python main.py ingest-orders data/orders_2025.csv     # 导入订单
python main.py ingest-leads data/leads_2025.csv       # 导入线索
python main.py ingest-teacher-capacity data/teacher_capacity.csv
python main.py ingest-calendar                        # 学校考试日历
python main.py scan-knowledge-base                    # 登记知识库文件（不调用 AI）
```

## 知识库文件 → 公司事实

1. 在「资料上传中心」上传文件并选择分类（00_公司事实源 ~ 11_组织命名规则）
2. FactExtractionAgent 自动提取事实，存为待审核状态
3. 在「公司资料学习中心」逐条人工确认（is_active=True 后才会被业务 agent 使用）
4. 未经确认的事实永远不会进入任何 AI 生成的 prompt

## 本地与服务器数据同步

服务器与本地各有一份 marketing.db，互不自动同步。需要同步时：

```bash
# 本地 → 服务器（覆盖服务器数据，传完需重启服务）
scp marketing.db root@<服务器IP>:/opt/jizhi-growth-system/marketing.db
ssh root@<服务器IP> systemctl restart jizhi-growth
```

服务器每天通过 deploy/backup_sqlite.sh 备份到 backups/，保留 14 天。

## 数据健康检查

```bash
python main.py health-check    # 检查数据库连接、核心表、环境变量
python scripts/check_business_terms.py outputs/   # 扫描产出物中的禁用表达
```
