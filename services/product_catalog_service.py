"""
ProductCatalogService — 产品目录库统一服务

Single Source of Truth：读取 knowledge_base/product_catalog.py，
为 ProductTrafficLight / ChannelContentStrategyAgent /
WeeklySalesSuggestionAgent 等所有 Agent 提供规范化产品信息。

禁止在调用方硬编码产品列表。
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  产品扩展元数据（补充 product_catalog.py 里没有的运营字段）
#  product_catalog.py 是基础数据层；这里是运营策略层。
# ══════════════════════════════════════════════════════════════════
_PRODUCT_META: dict[str, dict] = {
    "regular": {
        "product_category":      "coursework_service",
        "aliases":               ["essay", "report", "assignment", "coursework",
                                  "作业", "课业辅导", "单次辅导", "tutoring",
                                  "presentation", "润色", "润色修改"],
        "suitable_channels":     ["xiaohongshu", "vertical_account", "moments",
                                  "wechat_group", "community", "referral"],
        "suitable_time_windows": ["0-7天", "8-14天", "15-21天"],
        "risk_level":            "low",
        "capacity_required":     True,
        "capacity_subject_keywords": ["regular", "coursework", "general"],
        "consultant_note":       "灵活报价，按字数/课时；询单后24h内回复，DDL前主动跟进",
        "xueguan_note":          "确认老师专业方向与交付时间，急单提前告知顾问",
        "forbidden_claims":      ["保证高分", "100%通过", "一定能过"],
        "active":                True,
    },
    "dissertation": {
        "product_category":      "dissertation_service",
        "aliases":               ["dissertation", "thesis", "毕业论文", "大论文",
                                  "Dissertation", "Thesis", "毕设"],
        "suitable_channels":     ["xiaohongshu", "vertical_account", "moments",
                                  "old_customer", "referral"],
        "suitable_time_windows": ["0-7天", "8-14天", "15-21天", "22-30天"],
        "risk_level":            "medium",
        "capacity_required":     True,
        "capacity_subject_keywords": ["dissertation", "thesis"],
        "consultant_note":       "确认论文字数/截止日/学校要求；报价前与学管确认老师档期",
        "xueguan_note":          "Dissertation老师资源有限，旺季（5-6月/11-12月）需提前2周排期",
        "forbidden_claims":      ["保证Distinction", "一定通过", "稳拿高分"],
        "active":                True,
    },
    "final_prediction": {
        "product_category":      "exam_service",
        "aliases":               ["final", "押题", "考前冲刺", "exam", "考试",
                                  "期末", "Final", "Exam", "final prediction",
                                  "final_prediction", "冲刺", "Final押题",
                                  "Final精准押题"],
        "suitable_channels":     ["xiaohongshu", "moments", "community",
                                  "old_customer", "wechat_group"],
        "suitable_time_windows": ["0-7天", "8-14天"],
        "risk_level":            "medium",
        "capacity_required":     True,
        "capacity_subject_keywords": ["final_exam", "exam_prep", "final"],
        "consultant_note":       "适合考前2-4周客户；不得承诺命中率或退款条件（由合同约定）",
        "xueguan_note":          "确认老师熟悉该学校该科目；旺季接单前先核实资源",
        "forbidden_claims":      ["押题命中率", "保证押中", "一定通过", "押中退款",
                                  "100%命中"],
        "active":                True,
    },
    "annual_package": {
        "product_category":      "package_service",
        "aliases":               ["包课", "学年包", "annual", "package",
                                  "annual package", "全程包", "年包"],
        "suitable_channels":     ["old_customer", "referral", "moments",
                                  "xiaohongshu"],
        "suitable_time_windows": ["8-14天", "15-21天", "22-30天", "31-60天"],
        "risk_level":            "low",
        "capacity_required":     True,
        "capacity_subject_keywords": ["annual", "package"],
        "consultant_note":       "推荐全学期消费≥2万学生；强调GPA管家8阶段跟踪与账户余额可退",
        "xueguan_note":          "开学前排期固定老师，建立学生档案；学期中定期复盘跟踪",
        "forbidden_claims":      ["保证GPA提升", "稳上Distinction"],
        "active":                True,
    },
    "guaranteed": {
        "product_category":      "guarantee_service",
        "aliases":               ["保过", "guaranteed", "pass guarantee",
                                  "保过辅导", "不过退款", "保分"],
        "suitable_channels":     ["old_customer", "moments", "referral"],
        "suitable_time_windows": ["0-7天", "8-14天", "15-21天"],
        "risk_level":            "high",
        "capacity_required":     True,
        "capacity_subject_keywords": ["guaranteed", "pass_guarantee"],
        "consultant_note":       "接单前8步流程缺一不可；有挂科记录客户优先推；报价前必须学管确认老师资质",
        "xueguan_note":          "保过产品需学管点头才可放行；确认老师历史通过率后方可承接",
        "forbidden_claims":      ["100%通过", "保证通过", "一定能过", "稳过",
                                  "无条件退款"],
        "active":                True,
    },
    "dp_premium": {
        "product_category":      "premium_service",
        "aliases":               ["dp", "DP", "distinction", "Distinction",
                                  "旗舰", "DP旗舰", "dp_premium",
                                  "Distinction Pass", "高端服务"],
        "suitable_channels":     ["old_customer", "referral", "moments"],
        "suitable_time_windows": ["8-14天", "15-21天", "22-30天"],
        "risk_level":            "medium",
        "capacity_required":     True,
        "capacity_subject_keywords": ["dp", "diploma"],
        "consultant_note":       "适合申研/冲Distinction/被坑过的客户；目标分数写入合同",
        "xueguan_note":          "DP专属签约老师资源稀缺；每单接前必须学管确认",
        "forbidden_claims":      ["保证Distinction", "一定1st", "绝对高分"],
        "active":                True,
    },
    "ai_compliance": {
        "product_category":      "ai_service",
        "aliases":               ["ai合规", "AI合规", "ai compliance",
                                  "AI合规学习", "合规", "ai检测", "AI检测",
                                  "Turnitin", "turnitin", "降重", "查重"],
        "suitable_channels":     ["xiaohongshu", "vertical_account", "moments",
                                  "wechat_group"],
        "suitable_time_windows": ["0-7天", "8-14天", "15-21天"],
        "risk_level":            "low",
        "capacity_required":     False,
        "capacity_subject_keywords": ["ai_compliance", "ai合规"],
        "consultant_note":       "开学初/学校发布AI政策时主推；帮学生了解合规使用AI工具",
        "xueguan_note":          "无需老师资源；确认学校AI政策版本后再承接",
        "forbidden_claims":      ["100%过AI检测", "保证不被查", "完美规避"],
        "active":                True,
    },
}


class ProductCatalogService:
    """
    产品目录统一服务。
    以 knowledge_base/product_catalog.py 为基础数据层，
    以 _PRODUCT_META 为运营策略扩展层，合并输出规范化产品信息。
    """

    _cache: Optional[list[dict]] = None
    _alias_map: Optional[dict[str, str]] = None

    # ── 公共接口 ──────────────────────────────────────────────────

    @classmethod
    def load_active_products(cls) -> list[dict]:
        """返回全部 active 产品的规范化信息列表（含所有运营字段）。"""
        if cls._cache is not None:
            return cls._cache

        base_catalog = cls._load_base_catalog()
        if not base_catalog:
            raise RuntimeError(
                "未找到产品目录库（knowledge_base/product_catalog.py → PRODUCT_CATALOG）。"
                "请确保文件存在且 PRODUCT_CATALOG 非空，不允许 fallback 成硬编码产品。"
            )

        products = []
        for pid, base_info in base_catalog.items():
            meta = _PRODUCT_META.get(pid, {})
            if not meta.get("active", True):
                continue

            product = {
                "canonical_product_id":   pid,
                "product_name":           base_info.get("name", pid),
                "product_short":          base_info.get("short", pid),
                "product_category":       meta.get("product_category", "other"),
                "desc":                   base_info.get("desc", ""),
                "target_students":        base_info.get("target_students", ""),
                "price_range":            base_info.get("price_range", ""),
                "key_selling_points":     base_info.get("key_selling_points", []),
                "upsell_to":              base_info.get("upsell_to", []),
                "best_timing":            base_info.get("best_timing", ""),
                # 运营策略层
                "aliases":                list(set((base_info.get("aliases") or []) + meta.get("aliases", []))),
                "suitable_channels":      meta.get("suitable_channels", []),
                "suitable_time_windows":  meta.get("suitable_time_windows", []),
                "risk_level":             meta.get("risk_level", "medium"),
                "capacity_required":      meta.get("capacity_required", True),
                "capacity_subject_keywords": meta.get("capacity_subject_keywords", []),
                "consultant_note":        meta.get("consultant_note", ""),
                "xueguan_note":           meta.get("xueguan_note", ""),
                "forbidden_claims":       meta.get("forbidden_claims", []),
                "source":                 "product_catalog",
            }
            products.append(product)

        # 保留 base_catalog 的原始顺序
        cls._cache = products
        logger.info(f"[ProductCatalog] 已加载 {len(products)} 个 active 产品")
        return products

    @classmethod
    def get_product(cls, canonical_id: str) -> Optional[dict]:
        """按 canonical_product_id 获取单个产品。"""
        for p in cls.load_active_products():
            if p["canonical_product_id"] == canonical_id:
                return p
        return None

    @classmethod
    def get_alias_map(cls) -> dict[str, str]:
        """
        返回 {原始名(小写) → canonical_product_id} 的全量别名映射。
        用于 CRM 原始产品名标准化。
        """
        if cls._alias_map is not None:
            return cls._alias_map

        alias_map: dict[str, str] = {}
        for p in cls.load_active_products():
            pid = p["canonical_product_id"]
            # canonical_id 本身也是 alias
            alias_map[pid.lower()] = pid
            # product_name / short name
            alias_map[p["product_name"].lower()] = pid
            alias_map[p["product_short"].lower()] = pid
            # 显式 aliases
            for alias in p["aliases"]:
                alias_map[alias.lower()] = pid

        cls._alias_map = alias_map
        return alias_map

    @classmethod
    def map_raw_product(cls, raw: str) -> dict:
        """
        将 CRM 原始产品名映射为 canonical_product_id。
        返回:
          {raw, canonical_product_id, matched_by, confidence}
        如果无法映射，canonical_product_id = None。
        """
        if not raw:
            return {"raw_product_name": raw, "canonical_product_id": None,
                    "matched_by": "none", "confidence": "none"}

        low = raw.lower().strip()
        alias_map = cls.get_alias_map()

        # 精确匹配
        if low in alias_map:
            return {"raw_product_name": raw,
                    "canonical_product_id": alias_map[low],
                    "matched_by": "exact_alias",
                    "confidence": "high"}

        # 子串匹配（从长到短，避免短词误匹配）
        for kw in sorted(alias_map, key=len, reverse=True):
            if kw and kw in low:
                return {"raw_product_name": raw,
                        "canonical_product_id": alias_map[kw],
                        "matched_by": "substring_alias",
                        "confidence": "medium"}

        return {"raw_product_name": raw,
                "canonical_product_id": None,
                "matched_by": "none",
                "confidence": "none"}

    @classmethod
    def get_product_ids(cls) -> list[str]:
        """返回全部 active canonical_product_id 列表。"""
        return [p["canonical_product_id"] for p in cls.load_active_products()]

    @classmethod
    def get_capacity_keywords(cls, product_id: str) -> list[str]:
        """返回某产品用于匹配 teacher_capacity.subject_area 的关键词列表。"""
        p = cls.get_product(product_id)
        return p["capacity_subject_keywords"] if p else []

    @classmethod
    def invalidate_cache(cls):
        """清除缓存（测试用）。"""
        cls._cache = None
        cls._alias_map = None

    # ── 私有方法 ──────────────────────────────────────────────────

    @classmethod
    def _load_base_catalog(cls) -> dict:
        """加载 knowledge_base/product_catalog.py 中的 PRODUCT_CATALOG。"""
        try:
            from knowledge_base.product_catalog import PRODUCT_CATALOG
            if not PRODUCT_CATALOG:
                logger.error("[ProductCatalog] PRODUCT_CATALOG 为空")
                return {}
            logger.info(f"[ProductCatalog] 成功读取产品目录，共 {len(PRODUCT_CATALOG)} 个产品")
            return PRODUCT_CATALOG
        except ImportError as e:
            logger.error(f"[ProductCatalog] 无法导入产品目录库: {e}")
            return {}
