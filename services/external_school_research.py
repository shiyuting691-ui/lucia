"""
外部学校情报接口 — 第一阶段仅占位，不调用任何外部搜索 API。

后续可接：Tavily / SerpAPI / Perplexity API / Exa / 手动上传学校日历资料。
接入后返回结构保持不变，confidence 与 public_sources 由实际来源填充。
严禁在未配置外部来源时返回任何编造的学校信息。
"""


def research_school_context(country: str, school_name: str) -> dict:
    return {
        "school_name": school_name,
        "country": country,
        "confidence": "low",
        "public_sources": [],
        "missing_data": ["external_search_not_configured"],
        "note": "外部学校情报暂未配置，当前仅基于内部数据判断。",
    }
