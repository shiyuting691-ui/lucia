"""
WeeklySalesSuggestionAgent — 周度销售建议 v2（Phase 2 v2）

顾问建议（consultant_suggestions）和学管建议（xueguan_suggestions）严格分离，
绝不混淆两个角色。使用 LLMRouter（DeepSeek → Claude → RuleFallback）。
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta

from services.llm import LLMRouter
from database import list_orders, list_leads, list_campaigns, list_market_signals, save_suggestion

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
try:
    from product_catalog import PRODUCT_NAME_MAP
    from company_context import get_company_context_for_prompt
except ImportError:
    PRODUCT_NAME_MAP = {}
    def get_company_context_for_prompt(): return ""

try:
    from agents.grounded_business_agent import GroundedBusinessAgent
    _HAS_GBA = True
except Exception:
    _HAS_GBA = False

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CONSULTANT = """你是极致教育（留学辅导机构）的顾问团队销售策略顾问。
职责：为顾问生成本周行动建议，包括跟进优先级、话术方向、成单策略。
禁止出现任何学管职责内容（排课、老师资源、交付安排）。
输出 JSON 数组，每个元素：
{
  "priority": 1,
  "action": "具体行动描述",
  "target": "面向人群/场景",
  "script_hint": "话术方向（1-2句，不超过40字）",
  "success_metric": "本周可量化目标",
  "risk_note": "需规避的说法或风险",
  "data_evidence": "依据数据"
}"""

SYSTEM_PROMPT_XUEGUAN = """你是极致教育（留学辅导机构）的学管团队运营顾问。
职责：为学管生成本周行动建议，包括排期确认、容量预警、交付准备。
禁止出现任何销售/顾问职责内容（报价、跟进线索、成单话术）。
输出单个 JSON 对象：
{
  "week_focus": "本周学管核心工作（1句话）",
  "capacity_check": "需核实的产品容量清单（列表）",
  "delivery_risks": "交付风险提示",
  "coordinator_actions": ["行动1", "行动2", "行动3"],
  "escalation_triggers": "何时需上报管理层",
  "data_evidence": "依据数据"
}"""


class WeeklySalesSuggestionAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._router = LLMRouter()
        self._gba = GroundedBusinessAgent() if _HAS_GBA else None

    def generate(self, week_start: str = None, extra_context: str = None,
                 traffic_lights: dict = None) -> dict:
        if not week_start:
            today = datetime.now()
            week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        week_dt = datetime.strptime(week_start, "%Y-%m-%d")
        week_end = (week_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        logger.info(f"[WeeklySalesSuggestion v2] week {week_start} ~ {week_end}")

        # 收集数据
        try:
            recent_orders = list_orders(limit=100, days=30)
        except Exception:
            recent_orders = []
        try:
            leads = list_leads(limit=50)
        except Exception:
            leads = []
        try:
            signals = list_market_signals(limit=10)
        except Exception:
            signals = []

        hot_leads = [l for l in leads if l.get("status") in ("contacted", "negotiating", "new")]

        from collections import Counter
        product_counter = Counter(
            o.get("product", "") for o in recent_orders if o.get("status") == "completed"
        )
        if not recent_orders and not leads and not traffic_lights:
            no_data = {
                "week_start": week_start,
                "week_end": week_end,
                "consultant_suggestions": [],
                "xueguan_suggestions": {},
                "can_generate": False,
                "no_data": True,
                "evidence": [],
                "confidence": "no_data",
                "responsible_role": "顾问",
                "missing_info": ["orders", "leads", "product_traffic_lights"],
            }
            try:
                save_suggestion(
                    suggestion_type="weekly_sales_suggestion_v2",
                    title=f"{week_start} 周度增长建议（no_data）",
                    content=json.dumps(no_data, ensure_ascii=False),
                    data_basis={
                        "no_data": True,
                        "evidence": [],
                        "confidence": "no_data",
                        "responsible_role": "顾问",
                    },
                    priority="中",
                )
            except Exception:
                pass
            return no_data

        # GBA 上下文
        gba_ctx = {"facts_count": 0, "facts_text": "", "terms_constraint_text": "",
                   "data_source_note": "RuleFallback", "can_generate": True,
                   "missing_information": []}
        if self._gba:
            try:
                gba_ctx = self._gba.get_context("weekly_sales")
            except Exception:
                pass

        context_block = gba_ctx.get("facts_text") or get_company_context_for_prompt() or ""
        terms_block = gba_ctx.get("terms_constraint_text") or ""

        # 构建公共背景
        leads_str = "\n".join(
            f"  [{l.get('status','')}] {l.get('school','')} {l.get('product_interest','')} "
            f"最后联系:{str(l.get('last_followup_time',''))[:10]}"
            for l in hot_leads[:10]
        ) or "  暂无活跃线索"

        signals_str = "\n".join(
            f"  [{s.get('signal_type','')}] {s.get('title','')} 紧急度:{s.get('urgency_level','')}"
            for s in signals[:5]
        ) or "  暂无市场信号"

        top_products_str = "\n".join(
            f"  {PRODUCT_NAME_MAP.get(p, p)}（{p}）: {n}单"
            for p, n in product_counter.most_common(5)
        ) or "  暂无"

        tl_str = ""
        if traffic_lights:
            tl_str = "\n".join(
                f"  {tl.get('product_name', pid)}: {tl.get('status_display', '')} — {tl.get('consultant_note', '')[:40]}"
                for pid, tl in traffic_lights.items()
            )

        background = f"""【周期】{week_start} ~ {week_end}
【公司事实】{gba_ctx['facts_count']}条
{context_block[:500] if context_block else ''}
{terms_block[:200] if terms_block else ''}
【热门活跃线索（{len(hot_leads)}条）】
{leads_str}
【近期热销产品】
{top_products_str}
【市场信号】
{signals_str}
【产品红绿灯】
{tl_str or '  暂无数据'}
【资源约束】
{extra_context or '  暂无推广边界数据'}"""

        # ── 顾问建议 ──
        consultant_prompt = f"""根据以下背景，为顾问生成本周行动建议（JSON数组，5条以内）：

{background}

重点关注：高意向线索跟进优先级、本周话术重点、成单机会。
绝对不要包含学管、排课、老师资源等内容。"""

        resp_c = self._router.generate_json(
            consultant_prompt, system_prompt=SYSTEM_PROMPT_CONSULTANT,
            max_tokens=1200, task_type="weekly_consultant_suggestion"
        )

        if resp_c.success and isinstance(resp_c.json_data, list) and resp_c.json_data:
            consultant_suggestions = resp_c.json_data
        else:
            consultant_suggestions = self._fallback_consultant(hot_leads, traffic_lights or {}, week_start)

        # ── 学管建议 ──
        xueguan_prompt = f"""根据以下背景，为学管生成本周行动建议（单个JSON对象）：

{background}

重点关注：老师容量确认、交付风险预警、排期安排。
绝对不要包含销售话术、线索跟进、报价等内容。"""

        resp_x = self._router.generate_json(
            xueguan_prompt, system_prompt=SYSTEM_PROMPT_XUEGUAN,
            max_tokens=800, task_type="weekly_xueguan_suggestion"
        )

        if resp_x.success and isinstance(resp_x.json_data, dict) and "week_focus" in (resp_x.json_data or {}):
            xueguan_suggestions = resp_x.json_data
        else:
            xueguan_suggestions = self._fallback_xueguan(traffic_lights or {})

        # 存库
        try:
            suggestion_id = save_suggestion(
                suggestion_type="weekly_sales_suggestion_v2",
                title=f"{week_start} 周度增长建议",
                content=json.dumps({
                    "consultant_suggestions": consultant_suggestions,
                    "xueguan_suggestions": xueguan_suggestions,
                }, ensure_ascii=False),
                data_basis={
                    "week_start": week_start, "week_end": week_end,
                    "hot_leads": len(hot_leads),
                    "consultant_provider": resp_c.provider,
                    "xueguan_provider": resp_x.provider,
                    "evidence": [
                        f"orders: last30={len(recent_orders)}",
                        f"leads: active={len(hot_leads)}",
                        f"traffic_lights: {len(traffic_lights or {})}",
                    ],
                    "confidence": "medium" if recent_orders or hot_leads else "low",
                    "responsible_role": "顾问",
                },
                priority="high",
            )
        except Exception as e:
            logger.warning(f"[WeeklySalesSuggestion] save_suggestion failed: {e}")
            suggestion_id = None

        return {
            "week_start":             week_start,
            "week_end":               week_end,
            "consultant_suggestions": consultant_suggestions,
            "xueguan_suggestions":    xueguan_suggestions,
            "consultant_provider":    resp_c.provider,
            "xueguan_provider":       resp_x.provider,
            "suggestion_id":          suggestion_id,
            "data_source_note":       gba_ctx.get("data_source_note", "DB"),
            "missing_info":           gba_ctx.get("missing_information", []),
        }

    def _fallback_consultant(self, hot_leads: list, traffic_lights: dict, week_start: str) -> list:
        green = [pid for pid, tl in traffic_lights.items() if tl.get("status") == "green"]
        if not hot_leads or not green:
            return []
        top_product = green[0]
        pname = traffic_lights.get(top_product, {}).get("product_name")
        if not pname:
            return []
        cnt = len(hot_leads)
        return [
            {
                "priority": 1,
                "action": f"优先跟进{cnt}条活跃线索中意向最高的TOP5",
                "target": "有明确截止日期的学生",
                "script_hint": "先问截止时间，再聊方案，最后确认预算",
                "success_metric": f"本周成单≥{max(1, cnt // 5)}单",
                "risk_note": "不提前承诺交付时间，接单前先确认学管资源",
                "data_evidence": f"活跃线索{cnt}条",
            },
            {
                "priority": 2,
                "action": f"主推 {pname}，配合本周渠道内容引流",
                "target": "小红书/社群新增咨询",
                "script_hint": "重点讲往年考察方向分析，结合学生实际情况定制方案",
                "success_metric": "新增咨询转化率≥30%",
                "risk_note": "不使用'保证押中'等承诺性表述",
                "data_evidence": "产品红绿灯：绿灯",
            },
            {
                "priority": 3,
                "action": "本周五前完成老客复购唤醒，联系3个月内成单客户",
                "target": "已成单老客户",
                "script_hint": "先关心上次结果，再问新学期是否有需要",
                "success_metric": "联系10位老客，转介绍或续课≥2单",
                "risk_note": "老客跟进要有温度，不要直接推销",
                "data_evidence": "老客复购利润高，转化成本低",
            },
        ]

    def _fallback_xueguan(self, traffic_lights: dict) -> dict:
        cap_check = []
        for pid, tl in traffic_lights.items():
            if tl.get("status") in ("yellow", "red"):
                cap_check.append(f"{tl.get('product_name', pid)}：{tl.get('xueguan_note', '确认容量')}")
        if not cap_check:
            return {
                "no_data": True,
                "message": "暂无真实数据，无法判断。",
                "capacity_check": [],
                "delivery_risks": "",
                "coordinator_actions": [],
                "evidence": [],
                "confidence": "no_data",
                "responsible_role": "销售/顾问/学管",
            }

        return {
            "week_focus": "基于红黄灯产品确认老师容量，提前识别交付风险",
            "capacity_check": cap_check,
            "delivery_risks": "容量偏紧产品须接单前由销售/顾问/学管确认，禁止自行承诺交付日期",
            "coordinator_actions": [
                "黄灯产品：接单前一对一确认老师档期",
                "红灯产品：有新询单时第一时间同步销售/顾问/学管资源状态",
            ],
            "escalation_triggers": "单周预计超量≥20%时上报管理层",
            "data_evidence": "红绿灯：" + (', '.join(f"{pid}={tl['status']}" for pid, tl in traffic_lights.items()) or '暂无数据'),
            "confidence": "medium",
            "responsible_role": "销售/顾问/学管",
        }
