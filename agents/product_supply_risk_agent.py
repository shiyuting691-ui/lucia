"""
ProductSupplyRiskAgent — 产品供给与订单风险判断
输入：orders/leads/teacher_capacity/order_risk_signals/market_signals
输出：JSON 格式的供给分析、老师资源匹配、订单风险、推广边界建议
"""
import json
import logging
import sys
import os
from datetime import datetime, timedelta
from collections import Counter
import anthropic

from database import (
    list_orders, list_teacher_capacity, list_order_risks,
    list_market_signals, save_suggestion, save_opportunity_score,
)
from services.output_contracts import evidence_from_records, has_real_data, no_data_result

# 加载知识库
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import PRODUCT_CATALOG, PRODUCT_NAME_MAP
    from company_context import get_company_context_for_prompt
except ImportError:
    PRODUCT_CATALOG = {}
    PRODUCT_NAME_MAP = {}
    def get_company_context_for_prompt(): return ""

from agents.grounded_business_agent import GroundedBusinessAgent

logger = logging.getLogger(__name__)

# 产品ID → 覆盖学科范围（用于判断老师资源匹配）
PRODUCT_SUBJECT_MAP = {
    "language_tutoring": ["英语", "语言"],
    "pse_followup": ["英语", "语言"],
    "hwept_sprint": ["英语", "语言"],
    "prestudy": ["商科", "管理", "金融", "经济", "会计", "计算机", "工程", "社科"],
    "assignment_done": ["商科", "管理", "金融", "经济", "会计", "计算机", "工程", "社科"],
    "coursework_tutoring": ["商科", "管理", "金融", "经济", "会计", "计算机", "工程", "社科"],
    "exam_support": ["商科", "管理", "金融", "经济", "会计", "计算机", "工程", "社科"],
    "prediction": ["商科", "管理", "金融", "经济", "会计", "计算机", "工程", "社科"],
    "guaranteed": ["商科", "管理", "金融", "经济", "会计"],
    "dissertation_full": ["商科", "社科", "管理", "教育", "法律"],
    "quality_70": ["商科", "社科", "管理", "教育", "法律"],
    "ai_reduction": ["商科", "社科", "管理", "教育"],
    "annual_package": ["商科", "管理", "金融", "经济"],
    "course_package": ["商科", "管理", "金融", "经济", "会计", "计算机", "社科", "教育"],
    "dp_excellence": ["商科", "管理", "金融", "社科"],
    "anxin_package": ["商科", "管理", "金融", "经济", "社科"],
    "graduation_carefree": ["商科", "社科", "管理", "教育", "法律"],
    "ai_top_student": ["商科", "社科", "管理", "教育"],
}

# 高风险学科（老师储备通常不足）
RISKY_SUBJECTS = {"计算机", "工程", "数学", "物理", "数据分析"}


class ProductSupplyRiskAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self._gba = GroundedBusinessAgent()

    def analyze(self, period_days: int = 14) -> dict:
        """执行产品供给与订单风险分析，返回完整结果 dict"""
        logger.info(f"[ProductSupplyRiskAgent] analyzing last {period_days} days")

        # ── 数据收集 ──────────────────────────────────────────────
        recent_orders = list_orders(days=period_days, limit=300)
        capacities    = list_teacher_capacity()
        risks         = list_order_risks(limit=50)
        signals       = list_market_signals(limit=20)
        if not has_real_data(recent_orders, capacities, risks, signals):
            return no_data_result("缺少订单、老师容量、风险或市场信号数据，无法生成产品供给与推广边界")

        # 订单分布统计
        product_counter = Counter(o.get("product") for o in recent_orders)
        school_counter  = Counter(o.get("school") for o in recent_orders)
        country_counter = Counter(o.get("country") for o in recent_orders)

        # 老师资源映射：学科 → 资源列表
        cap_by_subject: dict = {}
        for cap in capacities:
            key = cap.get("subject_area", "")
            cap_by_subject.setdefault(key, []).append(cap)

        # ── 推广边界计算 ────────────────────────────────────────────
        promotion_boundary = []
        for pid, info in PRODUCT_CATALOG.items():
            subjects = PRODUCT_SUBJECT_MAP.get(pid, [])
            tight_subjects = []
            ok_subjects    = []
            evidence = []

            for subj in subjects:
                caps = cap_by_subject.get(subj, [])
                if caps:
                    evidence.extend(f"teacher_capacity.subject_area={subj}" for _ in caps[:1])
                    # 找该学科最差资源状态
                    status_order = {"充足": 0, "正常": 1, "紧张": 2, "暂停接单": 3}
                    worst = max(caps, key=lambda c: status_order.get(c.get("capacity_status", "正常"), 1))
                    if worst.get("capacity_status") in ("紧张", "暂停接单"):
                        tight_subjects.append(subj)
                    else:
                        ok_subjects.append(subj)
                else:
                    tight_subjects.append(subj)

            order_count = product_counter.get(pid, 0)
            if order_count:
                evidence.append(f"orders.product={pid};count={order_count}")
            product_risks = [r for r in risks if r.get("product") in (pid, info.get("name"))]
            evidence.extend(evidence_from_records("order_risk_signals", product_risks, limit=3))
            if not evidence:
                continue

            # 推广等级判断
            if tight_subjects and not ok_subjects:
                push_level = "pause"
                reason = f"缺少或存在紧张老师资源记录：{'/'.join(tight_subjects[:3])}"
            elif tight_subjects:
                push_level = "cautious"
                reason = f"部分学科老师记录缺失或紧张（{'/'.join(tight_subjects[:3])}），需先确认档期"
            elif order_count > 20:
                push_level = "strong"
                reason = f"近{period_days}天订单{order_count}单，需求旺盛，老师资源充足"
            elif order_count > 5:
                push_level = "normal"
                reason = f"近{period_days}天订单{order_count}单，正常推广"
            else:
                push_level = "normal"
                reason = f"近{period_days}天订单{order_count}单，容量证据存在，正常推广"

            promotion_boundary.append({
                "product":              info["name"],
                "product_id":           pid,
                "can_push":             push_level not in ("pause",),
                "push_level":           push_level,
                "reason":               reason,
                "sales_note":           f"{'需销售/顾问/学管确认交付能力，' if tight_subjects else ''}使用标准话术",
                "marketing_note":       f"{'不建议大范围投放，' if push_level in ('cautious','pause') else ''}内容主题聚焦真实卖点",
                "academic_support_note":f"{'需先评估老师档期' if tight_subjects else '有容量记录，可继续接单'}",
                "tight_subjects":       tight_subjects,
                "ok_subjects":          ok_subjects[:3],
                "evidence":             evidence,
            })

        # ── 阶段订单风险汇总 ──────────────────────────────────────
        stage_risks = []
        for risk in risks[:10]:
            stage_risks.append({
                "risk_type":      risk.get("risk_type", ""),
                "related_product":PRODUCT_NAME_MAP.get(risk.get("product", ""), risk.get("product", "")),
                "related_subject":risk.get("subject_area", ""),
                "evidence":       risk.get("evidence", ""),
                "risk_level":     risk.get("risk_level", "medium"),
                "suggested_action":risk.get("suggested_action", ""),
            })

        # ── 老师资源分析 ──────────────────────────────────────────
        cap_analysis = []
        for cap in capacities:
            status = cap.get("capacity_status", "正常")
            cap_analysis.append({
                "subject_area":   cap.get("subject_area"),
                "course_type":    cap.get("course_type"),
                "capacity_status":status,
                "risk_level":     cap.get("risk_level"),
                "current_load":   cap.get("current_load"),
                "max_capacity":   cap.get("max_capacity"),
                "recommendation": (
                    "可强推" if status == "充足"
                    else "正常推广" if status == "正常"
                    else "谨慎推广，先评估" if status == "紧张"
                    else "暂停强推"
                ),
            })

        # ── 订单分布统计 ──────────────────────────────────────────
        order_distribution = []
        for pid, count in product_counter.most_common(6):
            pname = PRODUCT_NAME_MAP.get(pid, pid)
            top_schools  = [s for s, _ in school_counter.most_common(3)]
            top_countries= [c for c, _ in country_counter.most_common(2)]
            order_distribution.append({
                "direction":    f"{pname} 需求",
                "product":      pname,
                "product_id":   pid,
                "volume":       count,
                "top_schools":  top_schools,
                "top_countries":top_countries,
                "trend":        "上升" if count > max(len(recent_orders), 1) * 0.2 else "正常",
                "insight":      f"近{period_days}天 {count} 单，占比 {count/max(len(recent_orders),1)*100:.0f}%",
            })

        # ── 部门动作建议 ────────────────────────────────────────────
        strong_products  = [b for b in promotion_boundary if b["push_level"] == "strong"]
        cautious_products= [b for b in promotion_boundary if b["push_level"] in ("cautious", "pause")]

        dept_actions = [
            {
                "department": "推广/市场",
                "actions": [
                    f"重点铺设 {p['product']} 相关内容（{p['reason'][:40]}）"
                    for p in strong_products[:2]
                ] + [
                    f"暂缓 {p['product']} 大范围投放（老师资源：{'/'.join(p['tight_subjects'][:2])} 紧张）"
                    for p in cautious_products[:1]
                ],
            },
            {
                "department": "销售/顾问/学管",
                "actions": [
                    f"优先推广 {p['product']}，{p['sales_note']}"
                    for p in strong_products[:2]
                ] + [
                    f"推广 {p['product']} 前先由销售/顾问/学管确认老师档期"
                    for p in cautious_products[:1]
                ],
            },
            {
                "department": "销售/顾问/学管",
                "actions": [
                    "反馈本周各学科老师可接单数量",
                    "标记高风险订单（DDL 48小时内、计算类复杂考试）",
                    "更新不可承诺话术清单",
                ],
            },
            {
                "department": "管理层",
                "actions": [
                    f"评估是否补充 {p['tight_subjects'][0] if p['tight_subjects'] else ''} 方向老师"
                    for p in cautious_products[:2] if p.get("tight_subjects")
                ] + [
                    f"本期可加大 {p['product']} 推广投入"
                    for p in strong_products[:1]
                ],
            },
        ]

        # ── 汇总结果 ──────────────────────────────────────────────
        result = {
            "period_days":              period_days,
            "generated_at":             datetime.utcnow().isoformat(),
            "order_count":              len(recent_orders),
            "order_distribution":       order_distribution,
            "teacher_capacity_analysis":cap_analysis,
            "stage_order_risks":        stage_risks,
            "promotion_boundary":       promotion_boundary,
            "department_actions":       dept_actions,
        }

        # 保存为 strategy_suggestion
        save_suggestion(
            suggestion_type="product_supply_risk",
            title=f"产品供给与订单风险分析（近{period_days}天）",
            content=json.dumps(result, ensure_ascii=False, indent=2),
            data_basis={
                "order_count": len(recent_orders),
                "period_days": period_days,
                "evidence": (
                    evidence_from_records("orders", recent_orders, limit=5)
                    + evidence_from_records("teacher_capacity", capacities, limit=5)
                    + evidence_from_records("order_risk_signals", risks, limit=5)
                ),
                "confidence": "medium" if promotion_boundary else "low",
                "responsible_role": "产品/后台",
            },
            priority="high",
        )

        logger.info(f"[ProductSupplyRiskAgent] analysis done, saved as suggestion")

        # 将每个产品的推广等级写入 opportunity_scores（score_type=product）
        push_score_map = {"strong": 85, "normal": 60, "cautious": 35, "pause": 10}
        traffic_map    = {"strong": "green", "normal": "yellow", "cautious": "yellow", "pause": "red"}
        level_map      = {"strong": "A", "normal": "B", "cautious": "C", "pause": "低机会"}
        for b in promotion_boundary:
            pid  = b.get("product_id", "")
            name = b.get("product", pid)
            pl   = b.get("push_level", "normal")
            # 订单量加权：strong+订单≥20 升到 S
            vol  = product_counter.get(pid, 0)
            raw  = push_score_map.get(pl, 60)
            bonus = min(15, vol // 2)
            total_score = min(100, raw + bonus)
            lv = "S" if total_score >= 85 else level_map.get(pl, "B")
            save_opportunity_score({
                "score_type":    "product",
                "entity_name":   name,
                "entity_id":     pid,
                "score":         total_score,
                "level":         lv,
                "traffic_light": traffic_map.get(pl, "yellow"),
                "score_reason":  [b.get("reason", ""), f"近{period_days}天订单{vol}单"],
                "risk_flags":    [f"{s}老师紧张" for s in b.get("tight_subjects", [])],
                "recommendation":b.get("sales_note", ""),
            })

        return result
