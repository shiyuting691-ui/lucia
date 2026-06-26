# PRODUCT_CATALOG.md

正式系统只允许以下产品进入页面、Agent、任务和建议。代码事实源为 `knowledge_base/product_catalog.py`。

## 锁定产品目录

| 产品ID | 标准产品名 |
|---|---|
| language_tutoring | 语言班辅导 |
| pse_followup | PSE跟课 |
| hwept_sprint | HWEPT冲刺 |
| prestudy | 开学前预习课 |
| assignment_done | 作业委托 |
| coursework_tutoring | 作业辅导 |
| exam_support | 考试助力 |
| prediction | 押题 |
| guaranteed | 包过辅导 |
| dissertation_full | Dissertation全流程 |
| quality_70 | 70+质检 |
| ai_reduction | 降AI率 |
| annual_package | 学年包 |
| course_package | 包课 |
| dp_excellence | DP卓越安心包 |
| anxin_package | 安心包 |
| graduation_carefree | 毕业无忧 |
| ai_top_student | AI学霸成长包 |

## 强制校验

- 页面展示产品前，必须先匹配产品目录。
- Agent 生成产品推荐前，必须先匹配产品目录。
- 产品无法匹配时，显示：`暂无真实数据，无法判断。`
- 不允许使用目录外产品名替代或“猜测”产品。
- 演示数据中的产品名不得进入老板驾驶舱、增长预测、任务建议、战略建议。
