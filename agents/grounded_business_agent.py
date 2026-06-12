"""
GroundedBusinessAgent — 所有业务 Agent 生成内容前的事实检索门卫
职责：
  1. 根据任务类型从 company_facts 检索已确认事实
  2. 从 business_dictionary 读取标准词和禁用词
  3. 判断关键信息是否足够（can_generate）
  4. 如果不足，阻止下游 Agent 并返回缺口说明
  5. 返回可用的 facts 文本块（供注入 prompt）
"""
import os
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import (
    get_active_facts_for_prompt, list_dictionary_terms,
    get_forbidden_terms, count_facts_by_type,
)

# ── 任务类型 → 所需 fact_type 映射 ────────────────────────────────
TASK_REQUIRED_FACTS = {
    "weekly_promotion":      ["推广部建议", "产品事实"],
    "weekly_sales":          ["销售事实", "产品事实"],
    "monthly_strategy":      ["产品事实", "部门事实"],
    "product_supply_risk":   ["产品事实", "老师资源事实"],
    "daily_reminder":        ["产品事实"],
    "content_generation":    ["产品事实", "风控事实", "内容风格事实"],
    "sales_material":        ["销售事实", "产品事实"],
    "risk_review":           ["风控事实", "禁用表达事实"],
    "department_task":       ["部门事实"],
    "general":               [],  # 不强制要求
}

# ── 缺口清单：12 个资料分类对应的 fact_type ─────────────────────
KNOWLEDGE_GAP_CATEGORIES = [
    {"category": "00_公司事实源",      "fact_type": "公司基础事实",  "label": "公司基础信息"},
    {"category": "01_部门职责",        "fact_type": "部门事实",      "label": "部门职责说明"},
    {"category": "02_产品体系",        "fact_type": "产品事实",      "label": "产品体系资料"},
    {"category": "03_销售话术",        "fact_type": "销售事实",      "label": "销售话术资料"},
    {"category": "04_客户异议",        "fact_type": "客户异议事实",  "label": "客户异议资料"},
    {"category": "05_风控表达",        "fact_type": "风控事实",      "label": "风控表达规则"},
    {"category": "06_学管交付",        "fact_type": "学管事实",      "label": "学管交付边界"},
    {"category": "07_老师储备",        "fact_type": "老师资源事实",  "label": "老师储备资料"},
    {"category": "08_订单咨询数据说明","fact_type": "订单数据事实",  "label": "订单数据说明"},
    {"category": "09_优秀内容样例",    "fact_type": "内容风格事实",  "label": "优秀内容样例"},
    {"category": "10_禁用表达",        "fact_type": "禁用表达事实",  "label": "禁用表达规则"},
    {"category": "11_组织命名规则",    "fact_type": "部门事实",      "label": "组织命名规则"},
]

# 关键事实类型（缺少任意一个都会影响主要功能）
CRITICAL_FACT_TYPES = {"产品事实", "部门事实"}


class GroundedBusinessAgent:
    """
    使用方式：
        gba = GroundedBusinessAgent()
        ctx = gba.get_context("weekly_promotion")
        if not ctx["can_generate"]:
            return {"error": ctx["reason"], "missing": ctx["missing_information"]}
        # 使用 ctx["facts_text"] 注入 prompt
        # 使用 ctx["forbidden_terms"] 作为禁用词约束
    """

    def get_context(self, task_type: str = "general") -> dict:
        """
        主入口。返回：
        {
          "can_generate": bool,
          "reason": str,
          "usable_facts": [dict],       # 已确认事实列表
          "facts_text": str,            # 供注入 prompt 的格式化文本
          "standard_terms": [dict],     # 词典条目
          "forbidden_terms": [str],     # 所有禁用词
          "terms_constraint_text": str, # 供注入 prompt 的词典约束文本
          "missing_information": [str], # 缺少的资料
          "data_source_note": str,      # 说明本次输出的数据来源
          "facts_count": int,
        }
        """
        # 1. 读取已确认事实
        active_facts = get_active_facts_for_prompt()
        facts_by_type = {}
        for f in active_facts:
            ft = f["fact_type"]
            facts_by_type.setdefault(ft, []).append(f)

        # 2. 读取词典
        all_terms = list_dictionary_terms(is_active=True)
        forbidden = get_forbidden_terms()

        # 3. 判断缺口
        fact_counts = count_facts_by_type()
        missing_info = self._calc_missing(fact_counts, task_type)
        critical_missing = [m for m in missing_info if any(c in m for c in CRITICAL_FACT_TYPES)]

        # 4. 判断 can_generate
        if critical_missing and len(active_facts) == 0:
            # 完全没有任何已确认事实
            can_generate = False
            reason = (
                "当前 company_facts 中没有任何已确认事实，无法生成可靠建议。"
                "请到【公司资料学习中心】上传资料并确认事实后重试。"
            )
        else:
            can_generate = True
            reason = f"已加载 {len(active_facts)} 条已确认事实，{len(all_terms)} 条词典条目。"

        # 5. 构建供 prompt 使用的文本块
        facts_text = self._build_facts_text(facts_by_type, active_facts)
        terms_text = self._build_terms_constraint_text(all_terms, forbidden)
        data_note = self._build_data_source_note(active_facts, fact_counts)

        return {
            "can_generate":         can_generate,
            "reason":               reason,
            "usable_facts":         active_facts,
            "facts_text":           facts_text,
            "standard_terms":       all_terms,
            "forbidden_terms":      forbidden,
            "terms_constraint_text":terms_text,
            "missing_information":  missing_info,
            "data_source_note":     data_note,
            "facts_count":          len(active_facts),
        }

    def _calc_missing(self, fact_counts: dict, task_type: str) -> List[str]:
        """计算缺少哪些资料"""
        missing = []
        for cat in KNOWLEDGE_GAP_CATEGORIES:
            ft = cat["fact_type"]
            label = cat["label"]
            count_info = fact_counts.get(ft, {})
            confirmed = count_info.get("confirmed", 0)
            if confirmed == 0:
                missing.append(f"{label}（{ft}）：尚无已确认事实")
        return missing

    def _build_facts_text(self, facts_by_type: dict, all_facts: list) -> str:
        """生成供注入 prompt 的事实文本"""
        if not all_facts:
            return "【当前无已确认事实，以下内容来自系统临时参考，请勿视为强约束】"

        lines = [f"## 已确认公司事实（共 {len(all_facts)} 条，来自人工审核）\n"]
        for ft, facts in facts_by_type.items():
            lines.append(f"### {ft}")
            for f in facts[:10]:  # 每类最多 10 条，防止 prompt 过长
                src = f.get("source_file", "")
                src_short = src.split("/")[-1] if src else "未知来源"
                lines.append(f"- **{f['title']}**（来源：{src_short}，可信度：{f['confidence']}）")
                lines.append(f"  {f['content'][:300]}")
            lines.append("")

        return "\n".join(lines)

    def _build_terms_constraint_text(self, terms: list, forbidden: list) -> str:
        """生成词典约束文本（注入 prompt 的禁止词说明）"""
        if not terms and not forbidden:
            return ""

        lines = ["## 业务词典约束（必须遵守）\n"]

        dept_terms = [t for t in terms if t["term_type"] == "部门名称"]
        prod_terms = [t for t in terms if t["term_type"] == "产品名称"]

        if dept_terms:
            lines.append("### 部门名称（只能使用以下标准名称）")
            for t in dept_terms:
                fb = "、".join(t.get("forbidden_terms") or [])
                aliases = "、".join(t.get("aliases") or [])
                lines.append(f"- **{t['standard_term']}**（别名可接受：{aliases}）（禁止使用：{fb}）")
                if t.get("description"):
                    lines.append(f"  定义：{t['description']}")
            lines.append("")

        if prod_terms:
            lines.append("### 产品名称（只能使用以下标准名称，禁止虚构产品）")
            for t in prod_terms:
                fb = "、".join(t.get("forbidden_terms") or [])
                lines.append(f"- **{t['standard_term']}**（禁止使用：{fb}）")
            lines.append("")

        if forbidden:
            lines.append("### 全局禁用词（不得出现在任何输出中）")
            lines.append("、".join(sorted(set(forbidden))))

        return "\n".join(lines)

    def _build_data_source_note(self, facts: list, fact_counts: dict) -> str:
        """生成数据来源说明（用于在策略台显示依据）"""
        if not facts:
            return "⚠️ 当前无已确认事实，建议基于系统临时参考生成，可信度有限。"

        sources = list({f.get("source_file", "").split("/")[-1] for f in facts if f.get("source_file")})
        sources_str = "、".join(sources[:5])
        if len(sources) > 5:
            sources_str += f"…等{len(sources)}个文件"

        confirmed_types = [ft for ft, c in fact_counts.items() if c.get("confirmed", 0) > 0]
        return (
            f"📎 依据来源：{sources_str}\n"
            f"已确认事实覆盖：{'、'.join(confirmed_types)}\n"
            f"共 {len(facts)} 条已确认事实"
        )

    def get_knowledge_gap_status(self) -> List[dict]:
        """
        返回 12 个资料分类的状态清单，供缺口清单页面使用。
        每项：{"category", "label", "fact_type", "status", "confirmed", "pending"}
        status: "未上传" | "已解析待确认" | "已确认可使用" | "部分确认"
        """
        fact_counts = count_facts_by_type()
        result = []
        for cat in KNOWLEDGE_GAP_CATEGORIES:
            ft = cat["fact_type"]
            count_info = fact_counts.get(ft, {})
            confirmed = count_info.get("confirmed", 0)
            pending = count_info.get("pending", 0)

            if confirmed > 0 and pending == 0:
                status = "已确认可使用"
            elif confirmed > 0 and pending > 0:
                status = "部分确认"
            elif pending > 0:
                status = "已解析待确认"
            else:
                status = "未上传"

            result.append({
                "category":  cat["category"],
                "label":     cat["label"],
                "fact_type": ft,
                "status":    status,
                "confirmed": confirmed,
                "pending":   pending,
            })
        return result
