"""
ResourceChecker — 资源校验器

检查：
  - 老师是否够用（按学科）
  - 产品是否可推（结合容量 + 历史风险）
  - 是否超卖风险
  - 是否需要暂停推广

输出：
{
  "overall": "green|yellow|red|blocked",
  "by_product": {"final_prediction": {"status": "green", "note": "..."}, ...},
  "teacher_summary": [{"subject": "...", "available": N, "total": N, "status": "..."}],
  "recommendations": ["..."],
  "generated_at": "..."
}
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

PRODUCT_SUBJECT_MAP = {
    "final_prediction": ["商科", "管理", "金融", "经济", "会计", "社科"],
    "dissertation":     ["商科", "社科", "管理", "教育", "法律"],
    "annual_package":   ["商科", "管理", "金融", "经济"],
    "guaranteed":       ["商科", "管理", "金融", "经济", "会计"],
    "regular":          ["商科", "管理", "金融", "经济", "会计", "计算机", "社科"],
    "dp_premium":       ["商科", "管理", "金融", "社科"],
}

PRODUCT_DISPLAY = {
    "final_prediction": "Final精准押题",
    "regular":          "课业辅导",
    "dissertation":     "毕业论文辅导",
    "guaranteed":       "保过辅导",
    "annual_package":   "学年包",
    "dp_premium":       "DP旗舰版",
}

OVERSELL_THRESHOLD = 0.85
WARN_THRESHOLD     = 0.70


class ResourceChecker:

    def check(self) -> dict:
        from database import list_teacher_capacity, list_order_risks, list_orders

        capacities = list_teacher_capacity()
        risks      = list_order_risks(limit=30)
        orders     = list_orders(days=7, limit=200)

        # ── 老师容量 ─────────────────────────────────────────────
        cap_by_subject = {}
        for cap in capacities:
            subj = cap.get("subject_area", "未知")
            cap_by_subject[subj] = cap

        teacher_summary = []
        for subj, cap in cap_by_subject.items():
            total = cap.get("total_slots", 0) or 0
            avail = cap.get("available_slots", 0) or 0
            usage = (total - avail) / total if total > 0 else 0.0
            if avail <= 0:
                status = "blocked"
            elif usage >= OVERSELL_THRESHOLD:
                status = "red"
            elif usage >= WARN_THRESHOLD:
                status = "yellow"
            else:
                status = "green"
            teacher_summary.append({
                "subject":   subj,
                "available": avail,
                "total":     total,
                "usage_pct": round(usage * 100, 1),
                "status":    status,
            })

        # ── 按产品汇总 ────────────────────────────────────────────
        by_product = {}
        for pid, subjects in PRODUCT_SUBJECT_MAP.items():
            pname      = PRODUCT_DISPLAY.get(pid, pid)
            worst      = "green"
            tight_subj = []
            for subj in subjects:
                cap = cap_by_subject.get(subj)
                if not cap:
                    continue
                total = cap.get("total_slots", 0) or 0
                avail = cap.get("available_slots", 0) or 0
                usage = (total - avail) / total if total > 0 else 0.0
                if avail <= 0:
                    worst = "blocked"
                    tight_subj.append(f"{subj}(满)")
                elif usage >= OVERSELL_THRESHOLD:
                    if worst not in ("blocked",):
                        worst = "red"
                    tight_subj.append(f"{subj}({round(usage*100)}%)")
                elif usage >= WARN_THRESHOLD:
                    if worst == "green":
                        worst = "yellow"
                    tight_subj.append(f"{subj}({round(usage*100)}%)")

            note = f"关键学科偏紧：{tight_subj}" if tight_subj else "容量充足"
            by_product[pid] = {"name": pname, "status": worst, "note": note}

        # ── 整体状态 ──────────────────────────────────────────────
        statuses = [v["status"] for v in by_product.values()]
        if "blocked" in statuses:
            overall = "blocked"
        elif statuses.count("red") >= 2:
            overall = "red"
        elif "red" in statuses or statuses.count("yellow") >= 3:
            overall = "yellow"
        elif not capacities:
            overall = "yellow"
        else:
            overall = "green"

        # ── 建议 ─────────────────────────────────────────────────
        recommendations = self._make_recommendations(overall, by_product, teacher_summary)

        return {
            "overall":          overall,
            "by_product":       by_product,
            "teacher_summary":  teacher_summary,
            "recommendations":  recommendations,
            "generated_at":     datetime.utcnow().isoformat(),
        }

    def _make_recommendations(self, overall, by_product, teacher_summary) -> list:
        recs = []
        if overall == "blocked":
            recs.append("⛔ 存在满员学科，对应产品必须暂停推广")
        if overall == "red":
            recs.append("🔴 多个学科容量紧张，建议本周控制新单量，优先处理现有客户")
        blocked_prods = [v["name"] for v in by_product.values() if v["status"] == "blocked"]
        if blocked_prods:
            recs.append(f"以下产品建议暂停推广（容量满）：{', '.join(blocked_prods)}")
        yellow_prods = [v["name"] for v in by_product.values() if v["status"] in ("yellow", "red")]
        if yellow_prods:
            recs.append(f"以下产品需学管密切监控承接量：{', '.join(yellow_prods)}")
        if overall == "green":
            recs.append("✅ 整体容量充足，可正常推广所有产品")
        return recs
