"""
StudentNeedEngine — 学生需求识别引擎（规则型，零LLM）

从 orders / leads 中提取"这周学生有什么需求"，
输出按需求类型分类的热度排名和数据依据。

需求类型（need_type）：
  exam_support      考试支持 / Final冲刺
  coursework        作业辅导 / Coursework
  dissertation      毕业论文辅导
  ai_compliance     AI合规 / Turnitin检测
  long_term_anxiety 长期学业焦虑 / 包课
  language_school   语言班 / 预科辅导
  risk_rescue       风险补救 / 补考申诉
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  需求类型定义
# ══════════════════════════════════════════════════════════════════
NEED_TYPES: dict[str, dict] = {
    "exam_support": {
        "label":       "考试支持 / Final冲刺",
        "crm_keywords": ["exam", "final", "考试", "quiz", "test", "押题",
                         "期末", "resit", "考前", "冲刺", "补考"],
        "recommended_products":  ["final_prediction", "regular", "guaranteed"],
        "not_recommended": {
            "dp_premium":     "当前急救需求，不适合推长期高端服务",
            "annual_package": "短期需求，不适合直接推全学期套餐",
        },
        "next_questions": [
            "考试时间是什么时候？",
            "课程代码是什么？",
            "目前复习到哪一步了？",
        ],
        "channels": {
            "xiaohongshu":    "考前焦虑痛点搜索内容",
            "wechat_group":   "考试节点提醒，说清楚还有多少天",
            "moments":        "往期冲刺成功案例",
        },
        "time_windows":         ["0-7天", "8-14天"],
        "urgency":              "high",
    },
    "coursework": {
        "label":       "作业辅导 / Coursework",
        "crm_keywords": ["essay", "assignment", "report", "coursework", "作业",
                         "做题", "case study", "presentation", "润色", "ppt",
                         "PPT", "proofreading", "课业", "homework",
                         "tutoring", "course work", "analysis", "project",
                         "video", "辅导", "试听"],
        "recommended_products":  ["regular", "annual_package"],
        "not_recommended": {
            "dp_premium": "单次作业需求不适合直接推高端服务，除非客户有长期多课需求",
        },
        "next_questions": [
            "题目/rubric 是什么？",
            "字数要求是多少？",
            "deadline 是什么时候？",
        ],
        "channels": {
            "xiaohongshu":    "作业避坑/结构攻略，搜索流量高",
            "vertical_account": "学姐经验，干货类内容",
            "community":      "资料领取，低门槛引流",
        },
        "time_windows":         ["0-7天", "8-14天", "15-21天"],
        "urgency":              "medium",
    },
    "dissertation": {
        "label":       "毕业论文辅导",
        "crm_keywords": ["dissertation", "thesis", "毕业论文", "大论文",
                         "proposal", "literature review", "methodology",
                         "毕设", "data analysis", "research plan", "LR"],
        "recommended_products":  ["dissertation", "regular", "dp_premium"],
        "not_recommended": {
            "final_prediction": "毕业论文与考试押题是完全不同的需求",
        },
        "next_questions": [
            "论文处于哪个阶段（选题/Plan/LR/全文）？",
            "字数和 deadline 是什么？",
            "导师有什么具体反馈？",
        ],
        "channels": {
            "xiaohongshu":    "Dissertation 避坑攻略，引搜索流量",
            "vertical_account": "学姐经验，过程详细记录",
            "moments":        "服务过程与成功案例",
            "community":      "免费自查表引流",
        },
        "time_windows":         ["0-7天", "8-14天", "15-21天", "22-30天"],
        "urgency":              "medium",
    },
    "ai_compliance": {
        "label":       "AI合规 / Turnitin检测",
        "crm_keywords": ["ai合规", "ai compliance", "turnitin", "降ai",
                         "查重", "降重", "合规", "ai率", "原创性",
                         "plagiarism", "引用"],
        "recommended_products":  ["ai_compliance", "regular"],
        "not_recommended": {
            "guaranteed": "AI合规风险处理与保过辅导是不同服务",
        },
        "next_questions": [
            "学校 AI 检测政策是什么？",
            "是否有 Turnitin 报告可以分享？",
            "文件目前是什么格式？",
        ],
        "channels": {
            "xiaohongshu": "AI检测风险科普，需求搜索量大",
            "moments":     "真实案例提醒",
            "wechat_group": "政策解读，时效性强",
        },
        "time_windows":         ["0-7天", "8-14天"],
        "urgency":              "high",
    },
    "long_term_anxiety": {
        "label":       "长期学业焦虑 / 包课",
        "crm_keywords": ["包课", "学年包", "annual", "package", "整门课",
                         "一学期", "多门课", "长期", "全程", "年包"],
        "recommended_products":  ["annual_package", "dp_premium"],
        "not_recommended": {
            "regular": "长期多课需求不应只推单次服务",
        },
        "next_questions": [
            "这学期有几门课有需求？",
            "GPA 目标是什么？",
            "预算范围大概是多少？",
        ],
        "channels": {
            "vertical_account": "信任养成，长期干货内容",
            "moments":          "长期服务案例，真实数据",
        },
        "time_windows":         ["8-14天", "15-21天", "22-30天"],
        "urgency":              "low",
    },
    "language_school": {
        "label":       "语言班 / 预科辅导",
        "crm_keywords": ["语言班", "pse", "pre-sessional", "预科",
                         "雅思", "hwept", "annotated bibliography",
                         "seminar", "pse6", "pse10", "pse14", "选课"],
        "recommended_products":  ["regular"],
        "not_recommended": {
            "final_prediction": "语言班考核形式与学术课程押题不同",
            "dissertation":     "语言班不是毕业论文",
        },
        "next_questions": [
            "语言班周期是多久（PSE6/10/14）？",
            "考核形式是什么（Presentation/Essay/Portfolio）？",
            "是否有 Presentation 需要演练？",
        ],
        "channels": {
            "xiaohongshu":    "语言班避坑攻略，开学前流量高",
            "vertical_account": "新生经验/学姐分享",
            "community":      "语言班答疑，资料领取",
        },
        "time_windows":         ["0-7天", "8-14天"],
        "urgency":              "medium",
    },
    "risk_rescue": {
        "label":       "风险补救 / 补考申诉",
        "crm_keywords": ["fail", "挂科", "补考", "申诉", "misconduct",
                         "被警告", "resit", "学术风险", "退学",
                         "学校邮件"],
        "recommended_products":  ["guaranteed", "regular"],
        "not_recommended": {
            "dp_premium":     "危机情况不适合直接推高端品牌服务",
            "annual_package": "当下是急救需求，不推长期套餐",
        },
        "next_questions": [
            "学校邮件内容是什么？",
            "申诉截止时间是什么时候？",
            "是补考还是学术申诉？",
        ],
        "channels": {
            "moments": "弱展示，不建议大规模公开硬推",
        },
        "time_windows":         ["0-7天"],
        "urgency":              "high",
    },
}

# ── CRM 原始产品名 → 需求类型（粗粒度映射，用于 orders 聚合）──────────
_RAW_TO_NEED_TYPE: dict[str, str] = {}
for _nt, _meta in NEED_TYPES.items():
    for _kw in _meta["crm_keywords"]:
        _RAW_TO_NEED_TYPE[_kw.lower()] = _nt


def _map_raw_to_need_type(raw: str) -> Optional[str]:
    """将 CRM 原始产品名/咨询内容映射到 need_type。"""
    if not raw:
        return None
    low = raw.lower().strip()
    # 精确匹配
    if low in _RAW_TO_NEED_TYPE:
        return _RAW_TO_NEED_TYPE[low]
    # 包含匹配（从长到短）
    for kw in sorted(_RAW_TO_NEED_TYPE, key=len, reverse=True):
        if kw and kw in low:
            return _RAW_TO_NEED_TYPE[kw]
    return None


# ══════════════════════════════════════════════════════════════════
#  引擎主体
# ══════════════════════════════════════════════════════════════════

class StudentNeedEngine:
    """
    从 orders / leads 聚合本周/近期的学生需求热度。
    全部基于规则，零 LLM 调用。
    """

    def run(self, days: int = 30) -> dict:
        """
        返回结构：
        {
          "need_summary": [
            {
              "need_type": "exam_support",
              "label": "考试支持 / Final冲刺",
              "order_count": 12,
              "lead_count": 5,
              "total_signals": 17,
              "heat_score": 85,       # 0-100
              "urgency": "high",
              "evidence": [...],
              "top_countries": ["UK", "AU"],
              "top_schools": ["曼大", "利兹"],
              "recommended_products": [...],
              "not_recommended": {...},
              "next_questions": [...],
              "channels": {...},
              "time_windows": [...],
            }
          ],
          "unmapped_orders": [("做题", 770), ...],
          "total_orders": 208,
          "total_leads": 0,
          "data_days": 30,
          "generated_at": "...",
        }
        """
        cutoff = datetime.now() - timedelta(days=days)

        # ── 读取订单 ───────────────────────────────────────────────
        orders_by_need:  dict[str, int] = {}
        orders_by_need_country: dict[str, dict[str, int]] = {}
        orders_by_need_school: dict[str, dict[str, int]] = {}
        unmapped_orders: dict[str, int] = {}
        total_orders = 0

        try:
            from database import list_orders
            orders = list_orders(days=days, limit=5000)
            total_orders = len(orders)
            for o in orders:
                raw = str(o.get("product") or "")
                nt = _map_raw_to_need_type(raw)
                if nt:
                    orders_by_need[nt] = orders_by_need.get(nt, 0) + 1
                    country = o.get("country") or "未知"
                    school  = o.get("school")  or "未知"
                    if nt not in orders_by_need_country:
                        orders_by_need_country[nt] = {}
                    orders_by_need_country[nt][country] = orders_by_need_country[nt].get(country, 0) + 1
                    if nt not in orders_by_need_school:
                        orders_by_need_school[nt] = {}
                    orders_by_need_school[nt][school] = orders_by_need_school[nt].get(school, 0) + 1
                else:
                    unmapped_orders[raw] = unmapped_orders.get(raw, 0) + 1
        except Exception as e:
            logger.warning(f"[StudentNeedEngine] orders read failed: {e}")

        # ── 读取线索 ───────────────────────────────────────────────
        leads_by_need: dict[str, int] = {}
        total_leads = 0

        try:
            from database import list_leads
            leads = list_leads(days=days, limit=5000)
            total_leads = len(leads)
            for lead in leads:
                raw = str(lead.get("product_interest") or "")
                nt = _map_raw_to_need_type(raw)
                if nt:
                    leads_by_need[nt] = leads_by_need.get(nt, 0) + 1
        except Exception as e:
            logger.warning(f"[StudentNeedEngine] leads read failed: {e}")

        # ── 计算热度并排序 ─────────────────────────────────────────
        all_need_types = set(list(orders_by_need.keys()) + list(leads_by_need.keys()))
        # 确保所有 need_type 都出现在结果里（即使信号为0也出现）
        all_need_types = set(NEED_TYPES.keys())

        max_signals = max(
            (orders_by_need.get(nt, 0) * 2 + leads_by_need.get(nt, 0)
             for nt in all_need_types),
            default=1
        )

        need_summary = []
        for nt, meta in NEED_TYPES.items():
            order_cnt = orders_by_need.get(nt, 0)
            lead_cnt  = leads_by_need.get(nt, 0)
            signals   = order_cnt * 2 + lead_cnt  # 订单权重更高
            heat      = min(100, int(signals / max(max_signals, 1) * 100)) if max_signals > 0 else 0

            # 来源国家/学校（取 top 3）
            country_map = orders_by_need_country.get(nt, {})
            school_map  = orders_by_need_school.get(nt, {})
            top_countries = [c for c, _ in sorted(country_map.items(), key=lambda x: -x[1])[:3]
                             if c != "未知"]
            top_schools   = [s for s, _ in sorted(school_map.items(), key=lambda x: -x[1])[:3]
                             if s != "未知"]

            # 数据依据文字
            evidence = []
            if order_cnt > 0:
                evidence.append(f"近{days}天成单{order_cnt}单")
            if lead_cnt > 0:
                evidence.append(f"近{days}天线索{lead_cnt}条")
            if top_countries:
                evidence.append(f"主要国家：{'/'.join(top_countries)}")
            if top_schools:
                evidence.append(f"热门学校：{'/'.join(top_schools[:2])}")
            if not evidence:
                evidence.append("暂无 CRM 历史数据，基于时段规律判断")

            need_summary.append({
                "need_type":           nt,
                "label":               meta["label"],
                "order_count":         order_cnt,
                "lead_count":          lead_cnt,
                "total_signals":       signals,
                "heat_score":          heat,
                "urgency":             meta["urgency"],
                "evidence":            evidence,
                "top_countries":       top_countries,
                "top_schools":         top_schools,
                "recommended_products": meta["recommended_products"],
                "not_recommended":     meta["not_recommended"],
                "next_questions":      meta["next_questions"],
                "channels":            meta["channels"],
                "time_windows":        meta["time_windows"],
            })

        # 按热度排序，有信号的排前面
        need_summary.sort(key=lambda x: (-x["heat_score"], -x["total_signals"]))

        return {
            "need_summary":    need_summary,
            "unmapped_orders": sorted(unmapped_orders.items(), key=lambda x: -x[1]),
            "total_orders":    total_orders,
            "total_leads":     total_leads,
            "data_days":       days,
            "generated_at":    datetime.now().isoformat(),
        }
