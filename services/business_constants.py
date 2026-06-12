"""业务常量 · 全系统唯一的组织/术语硬约束来源

所有 agent 和页面引用部门名称时，必须从这里导入，禁止硬编码。
动态术语（产品名、别名、禁用词）以数据库 business_dictionary 表为准，
本文件只放不随业务变化的组织级常量。
"""

# 公司唯一合法的部门划分（与 business_dictionary 种子数据一致）
VALID_DEPARTMENTS = ("推广部", "顾问", "学管", "后台")

# 常见错误叫法 → 标准叫法（用于校验与自动纠正提示）
DEPARTMENT_ALIASES = {
    "市场部": "推广部",
    "销售部": "顾问",
    "销售团队": "顾问",
    "后端": "学管",
    "产品部": "后台",
}

# 全局禁止出现在任何对外内容中的承诺用语
GLOBAL_FORBIDDEN_PHRASES = (
    "保证押中原题",
    "100%通过",
    "我们有内部题库",
    "保证命中",
)


def is_valid_department(name: str) -> bool:
    return name in VALID_DEPARTMENTS


def normalize_department(name: str) -> str:
    """把别名纠正为标准部门名；无法识别时原样返回。"""
    if name in VALID_DEPARTMENTS:
        return name
    return DEPARTMENT_ALIASES.get(name, name)
