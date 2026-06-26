"""
ChannelContentStrategyAgent — 渠道内容作战策略 v2（Phase 2 v2）

读取所有5个时间窗口的预测，为7个渠道生成内容策略。
存入：content_strategy_recommendations 表（统一表名）
红灯产品不主动引流，缺数据产品标注 missing_data。

渠道：xiaohongshu / vertical_account / moments / community /
      wechat_group / referral / old_customer
"""
import json
import logging
from datetime import datetime

from services.llm import LLMRouter
from services.output_contracts import evidence_from_records, no_data_result, validate_content_strategy_record
from database import (
    save_content_strategy_recommendation,
    get_latest_forecasts_by_window,
)

logger = logging.getLogger(__name__)

CHANNELS = [
    "xiaohongshu",
    "vertical_account",
    "moments",
    "community",
    "wechat_group",
    "referral",
    "old_customer",
]

CHANNEL_DISPLAY = {
    "xiaohongshu":      "小红书",
    "vertical_account": "垂直号/公众号",
    "moments":          "朋友圈",
    "community":        "社群",
    "wechat_group":     "微信群",
    "referral":         "转介绍",
    "old_customer":     "老客户复购",
}

# 禁止用语 → 替换说法
FORBIDDEN_TERMS = {
    "押题命中率": "考前重点范围判断",
    "保证押中":   "考前重点范围判断",
    "真题框架":   "题型方向整理",
    "覆盖率":     "复习重点梳理",
    "绝对保分":   "考前冲刺规划",
    "绝对AI率":   "往年考察方向分析",
}

SYSTEM_PROMPT = """你是极致教育（留学辅导机构）的渠道内容策略师。

职责：根据5个时间窗口的需求预测，为每个渠道生成本周内容策略。

严格禁止使用以下词语（用括号中的替代词）：
- 押题命中率 → 考前重点范围判断
- 保证押中 → 考前重点范围判断
- 真题框架 → 题型方向整理
- 覆盖率 → 复习重点梳理
- 绝对保分 / 绝对AI率 → 考前冲刺规划 / 往年考察方向分析

输出规则：
1. 每个渠道输出1条策略
2. hook_idea 必须是具体标题/开头句，不超过20字
3. body_idea 是内容框架，3个要点，每点10字内
4. cta 必须具体（私信发"XX"获取XX，不能写空洞的"点击咨询"）
5. reason 要有数据/时间窗口依据
6. 红灯产品（status=red）只能走 old_customer 渠道，不主动引新流量

输出必须是合法 JSON 数组，每个元素：
{
  "channel": "渠道ID",
  "content_type": "类型",
  "target_school": "学校名或空",
  "target_product": "产品ID",
  "hook_idea": "标题",
  "body_idea": "要点1\\n要点2\\n要点3",
  "cta": "具体CTA",
  "priority": "P0/P1/P2",
  "reason": "为什么现在",
  "expected_leads": 数字,
  "sales_handoff": "顾问跟进建议",
  "xueguan_action": "学管配合动作",
  "risk_note": "风险提示或空字符串",
  "missing_data": "缺失数据说明或空字符串"
}"""


class ChannelContentStrategyAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._router = LLMRouter()

    def run(self, decision: dict = None, traffic_lights: dict = None) -> list:
        """生成渠道内容策略，存库并返回列表"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 读取所有5个时间窗口预测
        all_forecasts = {}
        try:
            all_forecasts = get_latest_forecasts_by_window()
        except Exception as e:
            logger.warning(f"[ChannelContentStrategy] forecast read failed: {e}")

        decision = decision or {}
        traffic_lights = traffic_lights or {}
        if not any(all_forecasts.values()) and not traffic_lights:
            logger.warning("[ChannelContentStrategy] no_data: forecasts and traffic_lights are empty")
            return [no_data_result("缺少时间窗口预测和产品红绿灯数据，不能生成渠道推广建议")]

        prompt = self._build_prompt(decision, all_forecasts, traffic_lights)

        logger.info("[ChannelContentStrategy v2] calling LLMRouter")
        resp = self._router.generate_json(prompt, system_prompt=SYSTEM_PROMPT,
                                          max_tokens=3000,
                                          task_type="channel_content_strategy")

        if resp.success and resp.json_data:
            recs = resp.json_data if isinstance(resp.json_data, list) else []
        else:
            logger.warning(f"[ChannelContentStrategy] no_data: LLM failed: {resp.error}")
            return [no_data_result("AI模型不可用，且渠道推广建议不允许规则兜底生成")]

        saved = []
        for r in recs:
            r["rec_date"] = today
            r["provider"] = resp.provider if resp.success else "RuleFallback"
            r["time_window"] = "0-7天"
            r["confidence"] = r.get("confidence") or "medium"
            r["responsible_role"] = "推广/市场"
            r["data_evidence"] = r.get("data_evidence") or self._build_record_evidence(r, traffic_lights, all_forecasts)
            # 检查红灯产品：仅允许 old_customer 渠道
            pid = r.get("target_product", "")
            tl = traffic_lights.get(pid, {})
            if tl.get("status") in ("red",) and r.get("channel") != "old_customer":
                r["risk_note"] = (r.get("risk_note") or "") + " [红灯产品，仅保留老客渠道]"
                r["channel"] = "old_customer"
            # 禁用词替换
            r = self._filter_forbidden_terms(r)
            safe, guard = validate_content_strategy_record(r)
            if guard["validation_status"] != "valid":
                logger.warning(f"[ChannelContentStrategy] skipped invalid recommendation: {guard['errors']}")
                continue
            try:
                save_content_strategy_recommendation(safe)
                saved.append(safe)
            except Exception as e:
                logger.warning(f"[ChannelContentStrategy] save failed: {e}")

        logger.info(f"[ChannelContentStrategy v2] saved {len(saved)} recommendations")
        return saved

    def _build_prompt(self, decision: dict, all_forecasts: dict, traffic_lights: dict) -> str:
        phase = decision.get("phase_now", {})

        # 整理5个窗口摘要
        window_lines = []
        for w in ["0-7天", "8-14天", "15-21天", "22-30天", "31-60天"]:
            forecasts = all_forecasts.get(w, [])
            if forecasts:
                top = sorted(forecasts, key=lambda x: x.get("demand_score", 0), reverse=True)[:2]
                for f in top:
                    window_lines.append(
                        f"  [{w}] {f.get('country','')} {f.get('product_name','')} "
                        f"紧迫度={f.get('urgency','')} 预估线索={f.get('predicted_leads',0)}"
                    )
            else:
                window_lines.append(f"  [{w}] 暂无预测数据")

        # 红绿灯摘要
        tl_lines = []
        for pid, tl in traffic_lights.items():
            tl_lines.append(
                f"  {tl.get('product_name', pid)}: {tl.get('status_display', '')} — {tl.get('status_reason', '')[:40]}"
            )

        return f"""根据以下5个时间窗口预测和产品红绿灯，为7个渠道生成本周内容策略。

【需求阶段】
- 英国：{phase.get('uk_phase', '常规学期')}  澳洲：{phase.get('au_phase', '常规学期')}
- 紧迫度：{phase.get('urgency', '中')}

【5个时间窗口预测摘要】
{chr(10).join(window_lines) or '  暂无预测数据'}

【产品红绿灯】
{chr(10).join(tl_lines) or '  暂无红绿灯数据（按常规推广）'}

渠道列表（必须覆盖）：{', '.join(CHANNELS)}

注意：
- 红灯产品仅通过 old_customer 渠道，不主动引新流量
- 所有内容不得出现：押题命中率/保证押中/真题框架/覆盖率/绝对保分/绝对AI率
- sales_handoff 写顾问跟进指引，xueguan_action 写学管配合动作

请输出合法JSON数组（每个渠道1条）。"""

    def _filter_forbidden_terms(self, rec: dict) -> dict:
        for field in ("hook_idea", "body_idea", "cta", "reason", "sales_handoff"):
            val = rec.get(field, "") or ""
            for bad, good in FORBIDDEN_TERMS.items():
                val = val.replace(bad, good)
            rec[field] = val
        return rec

    def _build_record_evidence(self, rec: dict, traffic_lights: dict, all_forecasts: dict) -> list:
        evidence = []
        pid = rec.get("target_product") or rec.get("product_id")
        if pid and pid in traffic_lights:
            evidence.append(f"product_traffic_light.product_id={pid}")
        for window, forecasts in (all_forecasts or {}).items():
            for forecast in forecasts or []:
                if forecast.get("product_id") == pid or forecast.get("product") == pid:
                    fid = forecast.get("id")
                    evidence.append(f"time_window_forecasts.id={fid}" if fid else f"time_window_forecasts.window={window}")
                    break
            if evidence:
                break
        return evidence

    def _rule_fallback(self, decision: dict, traffic_lights: dict, all_forecasts: dict) -> list:
        return []
        phase = decision.get("phase_now", {})
        phase_name = phase.get("uk_phase", "考试冲刺期")

        # 确定主推产品（取绿灯或黄灯产品，按需求分数排序）
        green_products = [pid for pid, tl in traffic_lights.items()
                          if tl.get("status") in ("green", "yellow")]
        if not green_products:
            return []
        hot_product = green_products[0]
        hot_name = traffic_lights.get(hot_product, {}).get("product_name", hot_product)

        # 红灯产品集合
        red_products = {pid for pid, tl in traffic_lights.items() if tl.get("status") == "red"}

        # 从0-7天窗口取顶部线索预测量
        top_leads = 5
        w07 = all_forecasts.get("0-7天", [])
        if w07:
            top_leads = max(f.get("predicted_leads", 5) for f in w07)

        return [
            {
                "channel":        "xiaohongshu",
                "content_type":   "痛点文案",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      f"考前2周还在背笔记？{hot_name}正确打开方式",
                "body_idea":      "1. 无效备考三大误区\n2. 题型方向整理方法\n3. 真实成绩提升对比",
                "cta":            f"私信发【冲刺】免费领{hot_name}备考指引",
                "priority":       "P0",
                "reason":         f"小红书主拉新渠道，{phase_name}痛点内容转化率高，预估线索{top_leads}条",
                "expected_leads": top_leads,
                "sales_handoff":  "跟进小红书私信线索，2小时内回复，重点问截止时间",
                "xueguan_action": "确认老师排期，超额前提前告知顾问",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "vertical_account",
                "content_type":   "干货攻略",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      f"2026年{phase_name}完整备考攻略",
                "body_idea":      "1. 时间规划参考表\n2. 重点科目方向分析\n3. 辅导资源匹配建议",
                "cta":            "文末添加顾问领取完整版备考指引",
                "priority":       "P1",
                "reason":         "垂直号SEO引流，攻略类内容沉淀长期流量",
                "expected_leads": 2,
                "sales_handoff":  "垂直号引流线索补充校名/专业再跟进",
                "xueguan_action": "无需立即行动",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "moments",
                "content_type":   "老客见证",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      "她当时差点放弃，现在拿到offer了",
                "body_idea":      "1. 真实学生故事开场\n2. 辅导前后对比数据\n3. 当前名额提示",
                "cta":            "私信【我要咨询】了解剩余名额",
                "priority":       "P1",
                "reason":         "朋友圈是顾问私域主渠道，老客见证建立信任",
                "expected_leads": 3,
                "sales_handoff":  "配合朋友圈发布，当天跟进点赞/评论的潜在客户",
                "xueguan_action": "准备1-2个真实成功案例数据给顾问",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "community",
                "content_type":   "活动预热",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      f"【群内限时】{hot_name}本周特惠，截止周五",
                "body_idea":      "1. 限时优惠说明\n2. 适合人群描述\n3. 报名截止倒计时",
                "cta":            "回复【报名】锁定资格，先到先得",
                "priority":       "P1",
                "reason":         "社群存量客户转化成本最低，适合快速成单",
                "expected_leads": 4,
                "sales_handoff":  "社群报名后1小时内一对一跟进确认需求",
                "xueguan_action": "提前确认本周可接单量再发群活动",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "wechat_group",
                "content_type":   "考试倒计时",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      f"距{phase_name}还有XX天，这份备考清单发给有需要的同学",
                "body_idea":      "1. 复习重点梳理\n2. 常见考试方向分析\n3. 冲刺建议",
                "cta":            "私信发【清单】免费领",
                "priority":       "P1",
                "reason":         "微信群精准学生聚集，考前倒计时内容打开率高",
                "expected_leads": 3,
                "sales_handoff":  "私信领取清单的学生，优先跟进，记录截止日期",
                "xueguan_action": "无需立即行动",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "referral",
                "content_type":   "转介绍激励",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      "推荐朋友报名，你们各享优惠",
                "body_idea":      "1. 激励政策说明\n2. 推荐流程一张图\n3. 截止时间",
                "cta":            "私信发你的专属推荐码给好友",
                "priority":       "P2",
                "reason":         "老客转介绍信任度高、成本低，考试季前激活效果好",
                "expected_leads": 2,
                "sales_handoff":  "追踪推荐转化，给推荐人反馈进度",
                "xueguan_action": "无需立即行动",
                "risk_note":      "",
                "missing_data":   "",
            },
            {
                "channel":        "old_customer",
                "content_type":   "复购唤醒",
                "target_school":  "",
                "target_product": hot_product,
                "hook_idea":      "上次辅导效果怎么样？新学期你可能需要这个",
                "body_idea":      "1. 关心上次辅导结果\n2. 新学期需求预判\n3. 老客优先价格",
                "cta":            "回复【续课】了解老客专属方案",
                "priority":       "P1",
                "reason":         "老客复购利润高，考试季结束后是唤醒黄金期",
                "expected_leads": 3,
                "sales_handoff":  "顾问主动联系3个月内成单客户，问结果再推新需求",
                "xueguan_action": "整理已结课老客名单给顾问",
                "risk_note":      "",
                "missing_data":   "",
            },
        ]
