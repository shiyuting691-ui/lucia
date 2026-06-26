"""
每日全量自动化运行器
用法：python scripts/run_daily_all.py [--mode daily|weekly|monthly|push]

daily  (每天08:00)：每日提醒 + 供给风险 + 风险巡检
weekly (每周一09:00)：增长简报 + 市场建议 + 销售建议 + 归因分析
monthly(每月1日 09:00)：月度推广策略 + 增长预测
push   (每天14:00)：企业微信日报推送
"""
import argparse
import logging
import sys
import os
import yaml
from datetime import datetime, date

# 确保项目根目录在路径中
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("daily_runner")


def load_config():
    with open(os.path.join(ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)


def run_step(name: str, fn):
    logger.info(f"▶ 开始：{name}")
    try:
        result = fn()
        logger.info(f"✅ 完成：{name} | {str(result)[:200]}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 失败：{name} | {e}", exc_info=True)
        return False, str(e)


def run_daily(cfg):
    """每天运行：每日提醒 + 供给风险 + 风险巡检"""
    today = date.today().strftime("%Y-%m-%d")
    results = {}

    # 1. 每日有效提醒
    ok, r = run_step("DailyEffectiveReminderAgent", lambda: (
        __import__("agents.daily_effective_reminder_agent",
                   fromlist=["DailyEffectiveReminderAgent"])
        .DailyEffectiveReminderAgent(cfg).generate(target_date=today)
    ))
    results["daily_reminder"] = {"ok": ok, "result": r}

    # 2. 产品供给风险分析
    ok, r = run_step("ProductSupplyRiskAgent", lambda: (
        __import__("agents.product_supply_risk_agent",
                   fromlist=["ProductSupplyRiskAgent"])
        .ProductSupplyRiskAgent(cfg).analyze(period_days=14)
    ))
    results["supply_risk"] = {"ok": ok, "result": r}

    # 3. 风险巡检
    ok, r = run_step("RiskGuard", lambda: (
        __import__("agents.risk_guard", fromlist=["RiskGuard"])
        .RiskGuard().assess()
    ))
    results["risk_guard"] = {"ok": ok, "result": r}

    # 4. 市场信号抓取（学校节点）
    ok, r = run_step("SchoolOpportunityScoringAgent", lambda: (
        __import__("agents.school_opportunity_scoring_agent",
                   fromlist=["SchoolOpportunityScoringAgent"])
        .SchoolOpportunityScoringAgent(cfg).run()
    ))
    results["school_scoring"] = {"ok": ok, "result": r}

    _log_summary("daily", results)
    return results


def run_weekly(cfg):
    """每周一运行：增长简报 + 市场/销售建议 + 归因分析"""
    week_start = (date.today() - __import__("datetime").timedelta(
        days=date.today().weekday())).strftime("%Y-%m-%d")
    results = {}

    # 1. 周度增长简报
    ok, r = run_step("WeeklyGrowthBriefAgent", lambda: (
        __import__("agents.weekly_growth_brief_agent",
                   fromlist=["WeeklyGrowthBriefAgent"])
        .WeeklyGrowthBriefAgent(cfg).run()
    ))
    results["weekly_brief"] = {"ok": ok, "result": r}

    # 2. 市场推广建议
    ok, r = run_step("WeeklyMarketingSuggestionAgent", lambda: (
        __import__("agents.weekly_marketing_suggestion_agent",
                   fromlist=["WeeklyMarketingSuggestionAgent"])
        .WeeklyMarketingSuggestionAgent(cfg).generate(week_start=week_start)
    ))
    results["weekly_marketing"] = {"ok": ok, "result": r}

    # 3. 销售行动建议
    ok, r = run_step("WeeklySalesSuggestionAgent", lambda: (
        __import__("agents.weekly_sales_suggestion_agent",
                   fromlist=["WeeklySalesSuggestionAgent"])
        .WeeklySalesSuggestionAgent(cfg).generate(week_start=week_start)
    ))
    results["weekly_sales"] = {"ok": ok, "result": r}

    # 4. 归因分析
    ok, r = run_step("AttributionAnalysisAgent", lambda: (
        __import__("agents.attribution_analysis_agent",
                   fromlist=["AttributionAnalysisAgent"])
        .AttributionAnalysisAgent(cfg).run(days_lookback=30)
    ))
    results["attribution"] = {"ok": ok, "result": r}

    # 5. 渠道内容策略
    ok, r = run_step("ChannelContentStrategyAgent", lambda: (
        __import__("agents.channel_content_strategy_agent",
                   fromlist=["ChannelContentStrategyAgent"])
        .ChannelContentStrategyAgent(cfg).run()
    ))
    results["channel_content"] = {"ok": ok, "result": r}

    # 6. 增长预测（线索/成交）
    ok, r = run_step("CampaignPredictionAgent", lambda: (
        __import__("agents.campaign_prediction_agent",
                   fromlist=["CampaignPredictionAgent"])
        .CampaignPredictionAgent(cfg).run(week_start=week_start)
    ))
    results["campaign_prediction"] = {"ok": ok, "result": r}

    _log_summary("weekly", results)
    return results


def run_monthly(cfg):
    """每月1日运行：月度推广策略"""
    target_month = date.today().strftime("%Y-%m")
    results = {}

    # 1. 月度推广策略
    ok, r = run_step("PromotionStrategyAgent", lambda: (
        __import__("agents.promotion_strategy_agent",
                   fromlist=["PromotionStrategyAgent"])
        .PromotionStrategyAgent(cfg).generate(target_month=target_month)
    ))
    results["promotion_strategy"] = {"ok": ok, "result": r}

    # 2. 产品红绿灯
    ok, r = run_step("ProductTrafficLight", lambda: (
        __import__("agents.product_traffic_light",
                   fromlist=["ProductTrafficLight"])
        .ProductTrafficLight(cfg).evaluate()
    ))
    results["traffic_light"] = {"ok": ok, "result": r}

    # 3. 学校学术日历爬取（每月刷新一次官方数据）
    ok, r = run_step("SchoolCalendarScraper", lambda: (
        __import__("agents.school_calendar_scraper",
                   fromlist=["SchoolCalendarScraper"])
        .SchoolCalendarScraper(cfg).run()
    ))
    results["school_calendar"] = {"ok": ok, "result": str(r)[:300]}

    _log_summary("monthly", results)
    return results


def run_push(cfg):
    """每天14:00：企业微信推送日报"""
    from database.crud import list_suggestions, list_tasks, get_order_stats
    import requests, json

    webhook = os.environ.get("WECHAT_WEBHOOK", "")
    if not webhook:
        logger.warning("未配置 WECHAT_WEBHOOK，跳过推送")
        return {}

    today = date.today().strftime("%Y-%m-%d")

    # 取今日提醒
    reminders = list_suggestions(suggestion_type="daily_reminder", limit=1)
    reminder_text = ""
    if reminders:
        r = reminders[0]
        reminder_text = r.get("recommendation") or r.get("content", "")[:500]

    # 取订单统计
    stats = get_order_stats(days=1)
    today_orders = stats.get("total", 0)
    today_amount = stats.get("total_amount", 0)

    # 取待办任务数
    tasks = list_tasks(status="todo", limit=100)
    overdue = [t for t in tasks if t.get("due_date", "") < today]

    msg = f"""📊 **极致增长日报** {today}

💰 今日成交：{today_orders}单 | ¥{today_amount:,.0f}
📋 待办任务：{len(tasks)}个 | ⚠️ 已逾期：{len(overdue)}个

🔔 今日重点提醒：
{reminder_text[:400] if reminder_text else '（无提醒，今日任务均在掌控中）'}

👉 详情：http://121.43.83.158"""

    payload = {"msgtype": "markdown", "markdown": {"content": msg}}
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        logger.info(f"企业微信推送结果：{resp.status_code} {resp.text[:100]}")
        return {"pushed": True, "status": resp.status_code}
    except Exception as e:
        logger.error(f"企业微信推送失败：{e}")
        return {"pushed": False, "error": str(e)}


def _log_summary(mode: str, results: dict):
    ok_count = sum(1 for v in results.values() if v.get("ok"))
    total = len(results)
    logger.info(f"═══ {mode} 运行汇总：{ok_count}/{total} 成功 ═══")
    for k, v in results.items():
        icon = "✅" if v.get("ok") else "❌"
        logger.info(f"  {icon} {k}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly", "push", "all"],
                        default="daily")
    args = parser.parse_args()

    cfg = load_config()

    if args.mode == "daily":
        run_daily(cfg)
    elif args.mode == "weekly":
        run_daily(cfg)   # 周一也跑每日任务
        run_weekly(cfg)
    elif args.mode == "monthly":
        run_daily(cfg)
        run_weekly(cfg)
        run_monthly(cfg)
    elif args.mode == "push":
        run_push(cfg)
    elif args.mode == "all":
        run_daily(cfg)
        run_weekly(cfg)
        run_monthly(cfg)
        run_push(cfg)
