# DATA_CONTRACT.md

正式页面必须遵守以下数据契约。字段为空时统一显示：`暂无真实数据，无法判断。`

## 全局规则

- 没有真实数据库数据，不允许输出业务结论。
- 没有 `evidence`，不允许展示 AI 建议。
- 没有产品目录匹配，不允许展示产品推荐。
- 没有角色定义匹配，不允许生成任务。
- `mock/sample/demo/fake/placeholder/fallback/示例/模拟/假数据/演示` 数据不得进入正式页面。

## 老板驾驶舱基础版

允许展示：

| 内容 | 表 | 字段 | 空值处理 |
|---|---|---|---|
| 真实任务 | `tasks` | `title`, `department`, `priority`, `status`, `due_date` | 显示无真实任务 |
| 真实审批 | `product_launches` | `mgmt_approval`, `mgmt_approval_note` | 显示无真实审批 |
| 真实逾期 | `tasks` | `due_date`, `status` | 显示无真实逾期 |
| 真实产品上线状态 | `product_launches` | `catalog_id`, `product_name`, `stage`, `*_owner`, `gate*_status` | 显示无真实上线记录 |
| 真实风险记录 | `order_risk_signals`, `department_feedback` | 风险字段、反馈字段 | 显示无真实风险 |

禁止展示：收入预测、增长机会、AI战略建议、产品爆发判断、渠道结论。

## 产品目录与推荐台

允许展示：

| 内容 | 表/来源 | 字段 | 空值处理 |
|---|---|---|---|
| 产品目录 | `knowledge_base/product_catalog.py` | `PRODUCT_CATALOG` | 目录为空则系统不可用 |
| 产品推荐 | `leads`, `orders` + 产品目录 | `product_interest`, `product`, `pain_point`, `deadline` | 无真实线索/订单则只展示目录，不推荐 |

AI禁止生成新产品名。

## 新产品上线台

允许展示：

| 内容 | 表 | 字段 | 空值处理 |
|---|---|---|---|
| 上线卡 | `product_launches` | `catalog_id`, `product_name`, `stage`, `target_student_needs`, `product_match_logic`, `recommended_channels` | 显示无真实上线记录 |
| 负责人 | `product_launches` | `promo_owner`, `advisor_owner`, `xueguan_owner`, `backend_owner`, `mgmt_decision` | 显示待分配 |
| 关卡 | `product_launches` | `gate1_status` 至 `gate5_status` | 显示未开始 |
| 交付物 | `launch_deliverables` | `deliverable`, `quality_std`, `owner_dept`, `status` | 显示无交付物 |
| 部门反馈 | `launch_dept_feedback` | `from_dept`, `to_dept`, `feedback_type`, `description`, `status` | 显示无反馈 |

产品必须来自 PRODUCT_CATALOG。

## 暂停页面

以下页面默认 no_data，直到完成数据契约重建：

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

## AI输出

允许 AI 做：

- 摘要已有真实记录。
- 把真实 evidence 转成待办草案。
- 标注缺失数据。

禁止 AI 做：

- 在无 evidence 时生成业务结论。
- 发明产品、角色、学校、渠道、成交趋势。
- 用 fallback 伪装真实建议。

## 正式输出契约

所有业务结论、推广建议、任务建议在进入正式页面前必须通过 `services/output_contracts.py`：

| 字段 | 要求 |
|---|---|
| `evidence` | 必须指向真实表/记录，如 `orders.id=1`、`teacher_capacity.id=2` |
| `confidence` | 只能是 `high`、`medium`、`low` |
| `responsible_role` | 必须命中 `ROLE_DEFINITION.md` |
| `product` | 如涉及产品，必须能映射到 `PRODUCT_CATALOG.md` |
| `recommendation/content` | 必须存在，且不能由 fallback 在无数据时生成 |

校验失败的 AI 输出不得进入 `list_suggestions()` 默认正式列表；渠道内容策略校验失败则保存为 `skipped` 或不保存。
