"""
营销自动化系统入口
用法：
  python main.py init                        # 首次初始化，生成全套素材
  python main.py daily                       # 每日任务
  python main.py weekly                      # 每周任务
  python main.py monthly                     # 生成月度营销战略计划并推送企业微信
  python main.py weekplan                    # 生成本周执行计划并推送企业微信
  python main.py post <topic> <product_id>   # 按需生成单篇小红书
  python main.py referral <product_id>       # 生成特定产品转介绍素材
  python main.py ingest <data.json>          # 导入订单/咨询数据，更新计划
  python main.py daemon                      # 守护进程模式（持续调度）
  python main.py dashboard                   # 启动可视化控制台
  python main.py init-db                     # 初始化数据库（首次运行）
  python main.py list-contents [--status=X]  # 查看内容列表
  python main.py push-summary                # 推送企业微信摘要
  python main.py generate-daily             # 生成今日营销动作
  python main.py generate-tasks             # 生成各部门执行任务
  python main.py generate-insights          # 生成战略洞察建议
  python main.py review-risks               # 对草稿/待审内容做风险检查
  python main.py daily-brief                # 生成今日简报并推送企业微信
  python main.py run-daily                  # 运行每日自动化工作流（V3）
  python main.py ingest-orders <file>       # 导入订单 CSV/Excel（V4）
  python main.py ingest-leads <file>        # 导入咨询 CSV/Excel（V4）
  python main.py ingest-calendar <file>     # 导入学校节点 CSV/Excel（V4）
  python main.py analyze-history            # 分析历史规律，写入 yearly_patterns（V4）
  python main.py update-market-signals      # 生成市场信号，写入 market_signals（V4）
  python main.py run-monthly-promotion [--month 2026-07]  # 生成月度推广策略
  python main.py run-weekly-promotion [--week 2026-06-09] # 生成周度推广建议（销售+市场）
  python main.py run-daily-reminder [--date 2026-06-12]   # 生成每日有效提醒
"""
import os
import sys
import yaml
import json
import time
import requests
import schedule
from pathlib import Path
from datetime import datetime

from agents import OrchestratorAgent
from agents.content_generation_agent import ContentGenerationAgent
from agents.referral_material_agent import ReferralMaterialAgent
from agents.planning_agent import PlanningAgent
from agents.poster_agent import PosterAgent
from agents.formatter_agent import FormatterAgent
from anthropic import Anthropic
from database import (
    init_db, save_content, save_campaign,
    update_content_status, get_dashboard_stats,
    list_contents, save_suggestion, list_suggestions,
    save_task, list_tasks, update_task_status, get_task_stats,
    list_feedbacks, list_content_usages, get_usage_stats,
)

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=6fb301ee-26ad-4dc7-bcfb-a97274c7d477"
FORMATTER = None  # 延迟初始化

def get_formatter():
    global FORMATTER
    if FORMATTER is None:
        FORMATTER = FormatterAgent(WECOM_WEBHOOK)
    return FORMATTER

def send_to_wecom(messages: list[str]):
    """批量推送消息到企业微信群"""
    for msg in messages:
        resp = requests.post(WECOM_WEBHOOK, json={"msgtype": "text", "text": {"content": msg}})
        if resp.json().get("errcode") == 0:
            print(f"  ✅ 已推送（{len(msg)}字）")
        else:
            print(f"  ❌ 推送失败：{resp.text}")
        time.sleep(0.5)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_init(orchestrator: OrchestratorAgent):
    results = orchestrator.run_full_init()
    print(f"\n📊 初始化报告：")
    print(f"  - 日历节点数：{len(results['calendar'].get('key_nodes', []))}")
    print(f"  - 转介绍素材包：{len(results['referral_kits'])} 套")
    print(f"  - 地区活动素材：{len(results['campaigns'])} 个")
    print(f"  - 首批小红书笔记：{results['initial_posts_count']} 篇")


def cmd_daily(orchestrator: OrchestratorAgent):
    result = orchestrator.run_daily()
    print(f"\n每日任务完成：{result}")


def cmd_weekly(orchestrator: OrchestratorAgent):
    result = orchestrator.run_weekly()
    print(f"\n每周任务完成：{result}")


def cmd_post(config: dict, topic: str, product_id: str):
    client = Anthropic()
    agent = ContentGenerationAgent(client, config)
    post = agent.generate_single_post(topic=topic, product_id=product_id)
    print(f"\n{'='*50}")
    print(f"📝 【{post.get('title', '')}】")
    print(f"\n封面：{post.get('cover_text', '')}")
    print(f"\n正文：\n{post.get('body', '')}")
    print(f"\n标签：{' '.join(['#' + t for t in post.get('hashtags', [])])}")
    print(f"\n引导语：{post.get('call_to_action', '')}")

    # 保存到文件
    out_dir = Path(config["output"]["base_dir"]) / "xiaohongshu" / "on_demand"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = out_dir / f"{ts}_{product_id}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存：{fname}")

    # 写入数据库
    try:
        save_content({
            "title":        post.get("title", topic),
            "content_type": "xiaohongshu",
            "product":      product_id,
            "channel":      "xiaohongshu",
            "body":         post.get("body", ""),
            "cover_text":   post.get("cover_text", ""),
            "hashtags":     post.get("hashtags", []),
            "call_to_action": post.get("call_to_action", ""),
            "post_timing":  post.get("post_timing", ""),
            "urgency":      post.get("urgency", ""),
            "status":       "draft",
        })
        print(f"  💾 已写入数据库（状态：草稿）")
    except Exception as e:
        print(f"  ⚠️  数据库写入失败：{e}")


def cmd_referral(config: dict, product_id: str):
    client = Anthropic()
    agent = ReferralMaterialAgent(client, config)
    kit = agent.generate_referral_kit(product_id=product_id)
    print(f"\n{'='*50}")
    print(f"📦 {kit.get('product_name', product_id)} 转介绍素材包")

    scripts = kit.get("referral_scripts", {})
    print(f"\n【学生互推话术】\n{scripts.get('student_to_student', '')}")
    print(f"\n【家长推荐话术】\n{scripts.get('student_to_parent', '')}")
    print(f"\n【30字简版】\n{scripts.get('short_version', '')}")

    out_dir = Path(config["output"]["base_dir"]) / "referral_scripts" / "on_demand"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = out_dir / f"{ts}_{product_id}_kit.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(kit, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整素材包已保存：{fname}")

    # 写入数据库
    try:
        scripts = kit.get("referral_scripts", {})
        save_content({
            "title":        f"{kit.get('product_name', product_id)} 转介绍素材包",
            "content_type": "referral_script",
            "product":      product_id,
            "channel":      "referral",
            "body":         json.dumps(scripts, ensure_ascii=False),
            "suggested_use": "学生互推、家长推荐",
            "status":       "draft",
        })
        print(f"  💾 已写入数据库（状态：草稿）")
    except Exception as e:
        print(f"  ⚠️  数据库写入失败：{e}")


def cmd_daemon(orchestrator: OrchestratorAgent, config: dict):
    """守护进程模式：按配置自动调度"""
    daily_time = config["schedule"].get("daily_content_time", "08:00")
    weekly_day = config["schedule"].get("weekly_plan_day", "Monday").lower()

    print(f"\n🤖 守护进程启动")
    print(f"  每日任务时间：{daily_time}")
    print(f"  每周全量任务：{weekly_day}")
    print(f"  按 Ctrl+C 退出\n")

    schedule.every().day.at(daily_time).do(orchestrator.run_daily)
    getattr(schedule.every(), weekly_day).at("07:00").do(orchestrator.run_weekly)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    config = load_config()

    # 数据库自动初始化（首次运行时创建表）
    try:
        init_db(config)
    except Exception as e:
        print(f"⚠️  数据库初始化警告：{e}")

    cmd = args[0]

    if cmd in ("initdb", "init-db"):
        print("✅ 数据库已初始化")
        return

    if cmd == "dashboard":
        import subprocess
        dashboard_path = Path(__file__).parent / "dashboard.py"
        print("🖥️  启动营销控制台... 打开 http://localhost:8501")
        subprocess.run(["streamlit", "run", str(dashboard_path)])
        return

    if cmd == "list-contents":
        status_filter = None
        for a in args[1:]:
            if a.startswith("--status="):
                status_filter = a.split("=", 1)[1]
        contents = list_contents(status=status_filter, limit=50)
        STATUS_ZH = {"draft":"草稿","pending_review":"待审核","approved":"已通过",
                     "used":"已使用","reviewed":"已复盘","archived":"已废弃"}
        print(f"\n{'─'*70}")
        print(f"{'ID':<5} {'类型':<18} {'标题':<30} {'状态':<10} {'创建时间'}")
        print(f"{'─'*70}")
        for c in contents:
            st = STATUS_ZH.get(c['status'], c['status'])
            title = (c.get('title') or '（无标题）')[:28]
            ctype = c.get('content_type','')[:16]
            created = (c.get('created_at') or '')[:10]
            print(f"{c['id']:<5} {ctype:<18} {title:<30} {st:<10} {created}")
        print(f"{'─'*70}")
        print(f"共 {len(contents)} 条内容（status={status_filter or '全部'}）\n")
        return

    if cmd == "push-summary":
        stats = get_dashboard_stats()
        formatter = get_formatter()
        msg = formatter.format_notify_summary(
            event_type = "review_needed" if stats["pending"] > 0 else "content_ready",
            summary    = "今日营销系统摘要",
            details    = [
                f"内容总数：{stats['total']} 条",
                f"待审核：{stats['pending']} 条" if stats['pending'] else "✅ 暂无待审核内容",
                f"已通过可用：{stats['approved']} 条",
                f"高优先级反馈：{stats.get('high_feedback',0)} 条" if stats.get('high_feedback') else "暂无高优先级反馈",
            ],
        )
        ok = formatter.send_one(msg)
        print(f"{'✅' if ok else '❌'} 企业微信摘要推送{'成功' if ok else '失败'}")
        return

    if cmd == "generate-daily":
        print("\n🎯 生成今日营销动作...")
        client = Anthropic()
        agent = PlanningAgent(client, config)
        data_file = Path("data/business_data.json")
        biz_data = json.loads(data_file.read_text()) if data_file.exists() else None
        # 生成今日营销方向
        today = datetime.now().strftime("%Y-%m-%d")
        out_dir = Path(config["output"]["base_dir"]) / "plans"
        ts = datetime.now().strftime("%Y-%m")
        monthly_path = out_dir / f"monthly_{ts}.json"
        monthly_plan = json.loads(monthly_path.read_text()) if monthly_path.exists() else None
        plan = agent.generate_weekly_plan(monthly_plan=monthly_plan, business_data=biz_data)
        # 写库
        try:
            save_content({
                "title":        f"{today} 今日营销方向",
                "content_type": "weekly_plan",
                "channel":      "wecom",
                "body":         json.dumps(plan, ensure_ascii=False),
                "status":       "approved",
                "market_period": plan.get("week_theme",""),
            })
        except Exception:
            pass
        # 推送摘要
        formatter = get_formatter()
        msg = formatter.format_notify_summary(
            event_type = "content_ready",
            summary    = f"今日营销动作已生成 · {today}",
            details    = [
                f"本周主题：{plan.get('week_theme','')}",
                f"本周目标：{plan.get('week_goal','')}",
                "今日内容和话术已进入内容池，请在控制台查看",
            ],
        )
        formatter.send_one(msg)
        print(f"✅ 今日营销动作已生成并推送，请运行 python main.py dashboard 查看")
        return

    if cmd in ("init", "daily", "weekly"):
        # OrchestratorAgent 已废弃（registry status=deprecated），旧编排流程不再执行
        _REPLACEMENT = {
            "init":   "数据库表已自动创建；基础素材请通过页面或 run-weekly-promotion 生成",
            "daily":  "python main.py run-daily  或  run-daily-reminder",
            "weekly": "python main.py run-weekly-promotion",
        }
        print(f"⚠️  命令 '{cmd}' 已废弃：旧版 OrchestratorAgent 编排流程已被 workflows/ 体系取代。")
        print(f"    替代方式：{_REPLACEMENT[cmd]}")
        return

    elif cmd == "post":
        if len(args) < 3:
            print("用法：python main.py post <topic> <product_id>")
            print("例如：python main.py post '期末考试冲刺攻略' regular")
            sys.exit(1)
        cmd_post(config, topic=args[1], product_id=args[2])

    elif cmd == "referral":
        if len(args) < 2:
            print("用法：python main.py referral <product_id>")
            print("例如：python main.py referral annual_package")
            sys.exit(1)
        cmd_referral(config, product_id=args[1])

    elif cmd == "monthly":
        print("\n📅 生成月度营销战略计划...")
        client = Anthropic()
        agent = PlanningAgent(client, config)
        # 尝试加载已有数据
        data_file = Path("data/business_data.json")
        biz_data = json.loads(data_file.read_text()) if data_file.exists() else None
        plan = agent.generate_monthly_plan(business_data=biz_data)
        # 保存
        out_dir = Path(config["output"]["base_dir"]) / "plans"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m")
        plan_path = out_dir / f"monthly_{ts}.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        print(f"  💾 已保存：{plan_path}")
        # 推送企业微信（Markdown 美化版）
        print("  📨 推送到企业微信...")
        messages = get_formatter().format_monthly_plan(plan)
        get_formatter().send(messages)
        print(f"\n✅ 月度计划已生成并推送，共{len(messages)}条消息")

        # 写入数据库
        try:
            campaign_id = save_campaign({
                "name":          f"{plan.get('month','')}营销战略计划",
                "campaign_type": "monthly_plan",
                "core_theme":    plan.get("core_theme", ""),
                "core_goal":     plan.get("core_goal", ""),
                "period_start":  datetime.now(),
            })
            save_content({
                "title":        f"{plan.get('month','')}营销战略计划",
                "content_type": "monthly_plan",
                "channel":      "wecom",
                "body":         json.dumps(plan, ensure_ascii=False),
                "status":       "approved",
                "campaign_id":  campaign_id,
                "market_period": plan.get("core_theme", ""),
            })
            print(f"  💾 已写入数据库（campaign_id={campaign_id}）")
        except Exception as e:
            print(f"  ⚠️  数据库写入失败（不影响推送）：{e}")

    elif cmd == "weekplan":
        print("\n📋 生成本周执行计划...")
        client = Anthropic()
        agent = PlanningAgent(client, config)
        # 加载月度计划（如果有）
        out_dir = Path(config["output"]["base_dir"]) / "plans"
        ts = datetime.now().strftime("%Y-%m")
        monthly_path = out_dir / f"monthly_{ts}.json"
        monthly_plan = json.loads(monthly_path.read_text()) if monthly_path.exists() else None
        # 加载业务数据（如果有）
        data_file = Path("data/business_data.json")
        biz_data = json.loads(data_file.read_text()) if data_file.exists() else None
        plan = agent.generate_weekly_plan(monthly_plan=monthly_plan, business_data=biz_data)
        # 保存
        out_dir.mkdir(parents=True, exist_ok=True)
        week_ts = datetime.now().strftime("%Y-W%V")
        plan_path = out_dir / f"weekly_{week_ts}.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        print(f"  💾 已保存：{plan_path}")
        # 推送企业微信（Markdown 美化版）
        print("  📨 推送到企业微信...")
        messages = get_formatter().format_weekly_plan(plan)
        get_formatter().send(messages)
        print(f"\n✅ 周计划已生成并推送，共{len(messages)}条消息")

        # 写入数据库
        try:
            save_content({
                "title":        f"{plan.get('week','')}执行计划",
                "content_type": "weekly_plan",
                "channel":      "wecom",
                "body":         json.dumps(plan, ensure_ascii=False),
                "status":       "approved",
                "market_period": plan.get("week_theme", ""),
            })
            print(f"  💾 已写入数据库")
        except Exception as e:
            print(f"  ⚠️  数据库写入失败（不影响推送）：{e}")

    elif cmd == "poster":
        # 用法：python main.py poster <主题> [product_id] [xiaohongshu/promo/moments]
        if len(args) < 2:
            print("用法：python main.py poster <主题> [product_id] [类型]")
            print("例如：python main.py poster '澳洲期末冲刺最后2周' regular xiaohongshu")
            sys.exit(1)
        topic      = args[1]
        product_id = args[2] if len(args) > 2 else "regular"
        ptype      = args[3] if len(args) > 3 else "xiaohongshu"
        client = Anthropic()
        agent  = PosterAgent(client, config)
        print(f"\n🎨 生成海报：{topic}")
        path = agent.generate_poster(topic=topic, product_id=product_id, poster_type=ptype)
        print(f"✅ 海报已生成：{path}")
        # 用系统预览打开
        import subprocess
        subprocess.Popen(["open", path])

    elif cmd == "poster_series":
        product_id = args[1] if len(args) > 1 else "annual_package"
        client = Anthropic()
        agent  = PosterAgent(client, config)
        print(f"\n🎨 生成{product_id}系列海报（3张）...")
        paths = agent.generate_series(product_id=product_id, count=3)
        for p in paths:
            print(f"  ✅ {p}")
        import subprocess
        subprocess.Popen(["open", str(Path(config["output"]["base_dir"]) / "posters")])

    elif cmd == "ingest":
        if len(args) < 2:
            print("用法：python main.py ingest <data.json>")
            print("data.json 格式：{\"revenue\": \"109万\", \"consultations\": 262, \"orders\": [...], ...}")
            sys.exit(1)
        src = Path(args[1])
        if not src.exists():
            print(f"文件不存在：{src}")
            sys.exit(1)
        dest = Path("data/business_data.json")
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(src.read_text())
        print(f"✅ 数据已导入：{dest}")
        print("  现在运行 'python main.py monthly' 或 'python main.py weekplan' 可使用真实数据生成计划")

    elif cmd == "daemon":
        orchestrator = OrchestratorAgent(config)
        cmd_daemon(orchestrator, config)

    # ── V2 新命令 ──────────────────────────────────────────────────

    elif cmd == "generate-tasks":
        print("\n🎯 生成各部门执行任务...")
        from agents.department_task_agent import DepartmentTaskAgent
        client = Anthropic()
        agent  = DepartmentTaskAgent(client, config)

        # 加载计划
        out_dir = Path(config["output"]["base_dir"]) / "plans"
        ts = datetime.now().strftime("%Y-%m")
        week_ts = datetime.now().strftime("%Y-W%V")
        monthly_plan = json.loads((out_dir / f"monthly_{ts}.json").read_text()) \
                       if (out_dir / f"monthly_{ts}.json").exists() else None
        weekly_plan  = json.loads((out_dir / f"weekly_{week_ts}.json").read_text()) \
                       if (out_dir / f"weekly_{week_ts}.json").exists() else None
        pending_contents = list_contents(status="pending_review", limit=20)

        tasks = agent.generate_tasks(
            monthly_plan      = monthly_plan,
            weekly_plan       = weekly_plan,
            pending_contents  = pending_contents,
        )

        saved = 0
        dept_count: dict = {}
        for t in tasks:
            save_task(t)
            saved += 1
            dept = t.get("department","未知")
            dept_count[dept] = dept_count.get(dept, 0) + 1

        print(f"✅ 已生成并入库 {saved} 条任务")
        for dept, cnt in dept_count.items():
            print(f"  {dept}：{cnt} 条")

        # 推送摘要
        formatter = get_formatter()
        lines = [f"{dept} {cnt}条" for dept, cnt in dept_count.items()]
        formatter.send_one(formatter.format_notify_summary(
            "content_ready", f"各部门任务已生成，共 {saved} 条",
            details=lines + ["请进入控制台【部门任务台】查看"]
        ))

    elif cmd == "generate-insights":
        print("\n💡 生成战略洞察建议...")
        from agents.insight_agent import InsightAgent
        from agents.product_improvement_agent import ProductImprovementAgent
        client = Anthropic()

        contents      = list_contents(limit=200)
        tasks_data    = list_tasks(limit=200)
        feedbacks     = list_feedbacks()
        usage_records = list_content_usages(limit=200)
        campaigns_data= list_campaigns(limit=20)
        data_file     = Path("data/business_data.json")
        biz_data      = json.loads(data_file.read_text()) if data_file.exists() else None

        # InsightAgent
        insight_agent = InsightAgent(client, config)
        insights = insight_agent.generate_insights(
            contents=contents, tasks=tasks_data, feedbacks=feedbacks,
            usage_records=usage_records, campaigns=campaigns_data, business_data=biz_data,
        )
        for s in insights:
            save_suggestion(s)

        # ProductImprovementAgent
        improve_agent = ProductImprovementAgent(client, config)
        improvements  = improve_agent.generate_improvements(feedbacks=feedbacks, usage_records=usage_records)
        for s in improvements:
            save_suggestion(s)

        total = len(insights) + len(improvements)
        print(f"✅ 已生成 {total} 条战略建议（洞察:{len(insights)} / 产品优化:{len(improvements)}）")
        get_formatter().send_one(get_formatter().format_notify_summary(
            "content_ready", f"战略建议已生成，共 {total} 条",
            details=[f"洞察类：{len(insights)} 条", f"产品优化：{len(improvements)} 条",
                     "请进入控制台【战略建议台】查看"]
        ))

    elif cmd == "review-risks":
        print("\n🔍 风险审核中...")
        from agents.risk_review_agent import RiskReviewAgent
        client = Anthropic()
        agent  = RiskReviewAgent(client, config)

        # 取草稿和待审内容
        to_review = list_contents(status="draft", limit=20) + \
                    list_contents(status="pending_review", limit=20)

        if not to_review:
            print("  暂无需要审核的内容（草稿/待审核）")
        else:
            ok = high = blocked = 0
            for c in to_review:
                result = agent.review_content(c)
                level  = result.get("risk_level", "low")
                notes  = result.get("risk_notes", [])

                # 更新 risk_notes 到数据库
                from database.db import get_session
                from database.models import Content
                with get_session() as s:
                    content = s.get(Content, c["id"])
                    if content:
                        content.risk_notes = notes
                        if level == "block":
                            content.status = "archived"
                        elif level in ("high",) and content.status == "pending_review":
                            content.review_comment = f"[风控退回] {'; '.join(notes[:2])}"
                            content.status = "rejected"

                icon = {"safe":"✅","low":"🟡","medium":"🟠","high":"🔴","block":"⛔"}.get(level,"⚪")
                print(f"  {icon} [{level}] {c.get('title','')[:40]}")
                if notes:
                    for n in notes[:2]:
                        print(f"      ⚠️  {n}")
                if level == "safe":  ok += 1
                elif level in ("high","block"):  high += 1

            print(f"\n✅ 审核完成 {len(to_review)} 条：安全{ok} / 高风险{high}")
            get_formatter().send_one(get_formatter().format_notify_summary(
                "review_needed" if high else "content_ready",
                f"风险审核完成，共 {len(to_review)} 条",
                details=[f"安全通过：{ok} 条", f"高风险/阻断：{high} 条",
                         "请进入控制台【内容池】处理有风险的内容"]
            ))

    elif cmd == "daily-brief":
        print("\n📋 生成今日简报...")
        stats         = get_dashboard_stats()
        tasks_data    = list_tasks(status="todo", limit=50)
        feedbacks     = list_feedbacks(status="open")
        suggestions   = list_suggestions(status="new")
        usage_stats   = get_usage_stats()

        high_feedback = [f for f in feedbacks if f.get("urgency") in ("高","紧急")]
        high_sgs      = [s for s in suggestions if s.get("priority") in ("高","紧急")]
        today_tasks   = [t for t in tasks_data if t.get("status") == "todo"]

        # 找本周主推产品
        plans_dir = Path(config["output"]["base_dir"]) / "plans"
        ts = datetime.now().strftime("%Y-%m")
        monthly_plan = None
        if (plans_dir / f"monthly_{ts}.json").exists():
            monthly_plan = json.loads((plans_dir / f"monthly_{ts}.json").read_text())
        main_product = ""
        if monthly_plan:
            pp = monthly_plan.get("product_priority", [])
            if pp:
                main_product = pp[0].get("product", "")

        # 按部门整理今日任务
        dept_tasks: dict = {}
        for t in today_tasks[:15]:
            dept = t.get("department","其他")
            dept_tasks.setdefault(dept, []).append(t["title"])

        # 构建企业微信简报
        today_str = datetime.now().strftime("%Y年%m月%d日")
        lines = [f"# 📋 极致增长系统 · 今日简报", f"## {today_str}\n"]
        if main_product:
            lines.append(f"> 🎯 **今日主推产品：** {main_product}")
        lines.append(f"> 📝 待审核内容：**{stats['pending']}** 条")
        lines.append(f"> ✅ 已通过可用内容：**{stats['approved']}** 条")
        lines.append(f"> 📌 待执行任务：**{len(today_tasks)}** 条")
        lines.append(f"> 🔴 高优先级反馈：**{len(high_feedback)}** 条\n")

        for dept, dept_task_titles in list(dept_tasks.items())[:5]:
            lines.append(f"**{dept}任务：**")
            for title in dept_task_titles[:3]:
                lines.append(f"> • {title}")
            lines.append("")

        if high_sgs:
            lines.append("**💡 今日战略建议：**")
            for sg in high_sgs[:2]:
                lines.append(f"> ⭐ {sg['title']}")
            lines.append("")

        lines.append(f"[**→ 打开控制台查看完整详情**](http://localhost:8501)")
        lines.append(f"\n<font color=\"comment\">🤖 极致增长系统 · {datetime.now().strftime('%H:%M')}自动生成</font>")

        msg = "\n".join(lines)
        ok  = get_formatter().send_one(msg)
        print(f"{'✅' if ok else '❌'} 今日简报推送{'成功' if ok else '失败'}")
        print(f"\n简报摘要：")
        print(f"  今日主推：{main_product or '未设置'}")
        print(f"  待审核：{stats['pending']} / 待执行任务：{len(today_tasks)} / 高优反馈：{len(high_feedback)}")

    elif cmd == "ingest-orders":
        if len(args) < 2:
            print("用法：python main.py ingest-orders <file.csv>")
            sys.exit(1)
        from agents.data_ingestion_agent import DataIngestionAgent
        agent = DataIngestionAgent(config)
        result = agent.ingest_orders(args[1])
        print(f"\n{'✅' if not result.get('error') else '❌'} {result.get('message', result.get('error'))}")
        if result.get("error"):
            print(f"错误详情：{result['error']}")

    elif cmd == "ingest-leads":
        if len(args) < 2:
            print("用法：python main.py ingest-leads <file.csv>")
            sys.exit(1)
        from agents.data_ingestion_agent import DataIngestionAgent
        agent = DataIngestionAgent(config)
        result = agent.ingest_leads(args[1])
        print(f"\n{'✅' if not result.get('error') else '❌'} {result.get('message', result.get('error'))}")

    elif cmd == "ingest-calendar":
        if len(args) < 2:
            print("用法：python main.py ingest-calendar <file.csv>")
            sys.exit(1)
        from agents.data_ingestion_agent import DataIngestionAgent
        agent = DataIngestionAgent(config)
        result = agent.ingest_school_calendar(args[1])
        print(f"\n{'✅' if not result.get('error') else '❌'} {result.get('message', result.get('error'))}")

    elif cmd == "analyze-history":
        print("\n🔍 分析历史数据规律...")
        from agents.historical_pattern_agent import HistoricalPatternAgent
        agent = HistoricalPatternAgent(config)
        result = agent.run()
        icon = "✅" if not result.get("error") else "❌"
        print(f"\n{icon} {result.get('message', result.get('error', ''))}")

    elif cmd == "update-market-signals":
        print("\n📡 更新市场信号...")
        from agents.school_market_intelligence_agent import SchoolMarketIntelligenceAgent
        agent = SchoolMarketIntelligenceAgent(config)
        result = agent.run()
        print(f"\n✅ 生成信号 {result.get('signals_saved', 0)} 条")
        if result.get("hot_schools"):
            print(f"   🔥 热门学校：{'、'.join(result['hot_schools'][:5])}")
        if result.get("hot_products"):
            print(f"   💼 热门产品：{'、'.join(result['hot_products'][:5])}")
        if result.get("marketing_actions"):
            print("\n   🎯 推荐营销动作：")
            for action in result["marketing_actions"][:3]:
                print(f"      • {action}")
        if result.get("error"):
            print(f"   ⚠️ 部分错误：{result['error']}")

    elif cmd == "scan-knowledge-base":
        """扫描 knowledge_base/ 目录，登记文件信息到 knowledge_docs 表，不调用 Claude"""
        from pathlib import Path as _Path

        KB_DIR = _Path(__file__).parent / "knowledge_base"
        CATEGORY_MAP = {
            "01_产品知识库": "产品知识库",
            "02_销售话术库": "销售话术库",
            "03_客户异议库": "客户异议库",
            "04_营销案例库": "营销案例库",
            "05_小红书风格库": "小红书风格库",
            "06_风控表达库": "风控表达库",
            "07_学校节点库": "学校节点库",
        }
        ALLOWED_EXTS = {".md", ".txt", ".pdf", ".docx", ".doc", ".csv", ".html", ".htm"}

        from database import save_knowledge_doc
        scanned = 0
        skipped = 0
        for subdir, category in CATEGORY_MAP.items():
            subdir_path = KB_DIR / subdir
            if not subdir_path.exists():
                continue
            for f in subdir_path.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in ALLOWED_EXTS:
                    skipped += 1
                    continue
                if f.name.startswith("."):
                    continue
                save_knowledge_doc({
                    "file_name":     f.name,
                    "category":      category,
                    "file_path":     str(f.resolve()),
                    "file_type":     f.suffix.lower().lstrip("."),
                    "file_size":     f.stat().st_size,
                    "is_enabled":    True,
                    "last_synced_at": datetime.now(),
                })
                scanned += 1
                print(f"  ✅ [{category}] {f.name}")
        print(f"\n扫描完成：登记 {scanned} 个文件，跳过 {skipped} 个非支持格式文件。")

    elif cmd == "run-monthly-promotion":
        """生成月度推广策略：python main.py run-monthly-promotion [--month 2026-07]"""
        target_month = None
        for arg in args[1:]:
            if arg.startswith("--month="):
                target_month = arg.split("=", 1)[1]
            elif arg.startswith("--month"):
                idx = args.index(arg)
                if idx + 1 < len(args):
                    target_month = args[idx + 1]
        from workflows.monthly_promotion import MonthlyPromotionWorkflow
        wf = MonthlyPromotionWorkflow(config, target_month=target_month)
        result = wf.run(trigger="cli")
        print(f"\n{'─'*60}")
        print(f"✅ 月度推广策略生成完成")
        print(f"   月份：{result.get('target_month', target_month)}")
        print(f"   状态：{result.get('status')}")
        print(f"   摘要：{result.get('summary', '')}")
        if result.get("strategy_preview"):
            print(f"\n策略预览（前300字）：\n{result['strategy_preview']}")

    elif cmd == "run-weekly-promotion":
        """生成周度推广建议：python main.py run-weekly-promotion [--week 2026-06-09]"""
        week_start = None
        for arg in args[1:]:
            if arg.startswith("--week="):
                week_start = arg.split("=", 1)[1]
            elif arg.startswith("--week"):
                idx = args.index(arg)
                if idx + 1 < len(args):
                    week_start = args[idx + 1]
        from workflows.weekly_promotion import WeeklyPromotionWorkflow
        wf = WeeklyPromotionWorkflow(config, week_start=week_start)
        result = wf.run(trigger="cli")
        print(f"\n{'─'*60}")
        print(f"✅ 周度推广建议生成完成")
        print(f"   周次：{result.get('week_start', week_start)}")
        print(f"   状态：{result.get('status')}")
        print(f"   摘要：{result.get('summary', '')}")

    elif cmd == "run-daily-reminder":
        """生成每日有效提醒：python main.py run-daily-reminder [--date 2026-06-12]"""
        target_date = None
        for arg in args[1:]:
            if arg.startswith("--date="):
                target_date = arg.split("=", 1)[1]
            elif arg.startswith("--date"):
                idx = args.index(arg)
                if idx + 1 < len(args):
                    target_date = args[idx + 1]
        from workflows.daily_reminder import DailyReminderWorkflow
        wf = DailyReminderWorkflow(config, target_date=target_date)
        result = wf.run(trigger="cli")
        print(f"\n{'─'*60}")
        print(f"✅ 每日提醒生成完成")
        print(f"   日期：{result.get('target_date', target_date)}")
        print(f"   状态：{result.get('status')}")
        if result.get("reminder_preview"):
            print(f"\n提醒内容：\n{result['reminder_preview']}")

    elif cmd == "init-demo":
        """一键演示初始化：导入样本数据→生成月度计划→生成任务→分析市场→推送企业微信"""
        import subprocess
        if os.getenv("ALLOW_DEMO_DATA") != "1":
            print("演示数据入口已关闭：正式系统禁止默认导入 sample/demo 数据。")
            print("如仅用于本地演示，请显式设置 ALLOW_DEMO_DATA=1 后再运行。")
            return
        env = os.environ.copy()

        def run_step(step_name, step_cmd):
            print(f"\n{'─'*50}")
            print(f"▶  {step_name}")
            r = subprocess.run(step_cmd, cwd=str(Path(__file__).parent), env=env)
            if r.returncode != 0:
                print(f"  ⚠️  {step_name} 返回非零，继续下一步...")

        base_args = ["uv","run","--with","sqlalchemy","--with","anthropic",
                     "--with","pyyaml","--with","requests","--with","schedule","python","main.py"]

        print("=" * 60)
        print("🚀 极致教育增长作战系统 · MVP 演示初始化")
        print("=" * 60)

        # 步骤1：导入演示数据
        sample_orders   = Path("data/orders_sample.csv")
        sample_leads    = Path("data/leads_sample.csv")
        sample_calendar = Path("data/school_calendar_sample.csv")
        if sample_orders.exists():
            run_step("导入演示订单", base_args + ["ingest-orders", str(sample_orders)])
        if sample_leads.exists():
            run_step("导入演示咨询", base_args + ["ingest-leads", str(sample_leads)])
        if sample_calendar.exists():
            run_step("导入学校节点", base_args + ["ingest-calendar", str(sample_calendar)])

        # 步骤2：分析历史规律
        run_step("分析历史规律", base_args + ["analyze-history"])

        # 步骤3：生成月度营销战略
        run_step("生成月度营销战略计划", base_args + ["monthly"])

        # 步骤4：生成各部门任务
        run_step("生成各部门执行任务", base_args + ["generate-tasks"])

        # 步骤5：运行市场信号更新
        run_step("更新市场信号", base_args + ["update-market-signals"])

        # 步骤6：推送今日简报
        run_step("推送企业微信简报", base_args + ["daily-brief"])

        print("\n" + "=" * 60)
        print("✅ MVP 演示初始化完成！")
        print("=" * 60)
        print("\n📊 控制台启动命令（新终端窗口运行）：")
        print("   uv run --with sqlalchemy --with streamlit --with anthropic --with pyyaml --with requests --with schedule streamlit run dashboard.py")
        print("\n💡 演示要点：")
        print("  1. 📡 市场情报台 — 查看热门学校/产品/市场信号")
        print("  2. 📝 内容池 — 查看 AI 生成的草稿内容，点击审核通过")
        print("  3. ✅ 部门任务台 — 查看各部门待执行任务")
        print("  4. 🗣️ 产品反馈台 — 提交部门反馈")
        print("  5. 🤖 自动化工作流 — 点击运行每日工作流")
        print("  6. 📢 企业微信 — 检查群消息是否收到推送\n")

    elif cmd == "ingest-teacher-capacity":
        # 导入老师储备数据：python main.py ingest-teacher-capacity <file.csv>
        if len(args) < 2:
            print("用法：python main.py ingest-teacher-capacity <file.csv>")
            sys.exit(1)
        import pandas as pd
        from database import save_teacher_capacity
        df = pd.read_csv(args[1])
        saved = 0
        for _, row in df.iterrows():
            try:
                save_teacher_capacity(row.to_dict())
                saved += 1
            except Exception as e:
                print(f"跳过：{e}")
        print(f"✅ 老师储备数据导入完成：{saved} 条")

    elif cmd == "update-order-risks":
        # 重新生成订单风险信号：python main.py update-order-risks
        from database import (
            init_db as _init_db, list_orders as _list_orders,
            list_teacher_capacity as _list_tc,
            save_order_risk as _save_risk, clear_order_risks as _clear_risks,
        )
        from datetime import datetime as _dt2, timedelta as _td
        _init_db(config)
        _clear_risks()
        risks_saved = 0

        # 规则1：老师资源紧张的学科
        _capacities = _list_tc()
        for _cap in _capacities:
            if _cap.get("capacity_status") in ("紧张", "暂停接单"):
                _save_risk({
                    "signal_date": _dt2.utcnow(),
                    "product": _cap.get("course_type", ""),
                    "country": _cap.get("country", ""),
                    "subject_area": _cap.get("subject_area", ""),
                    "risk_type": "老师资源紧张",
                    "risk_level": _cap.get("risk_level", "high"),
                    "evidence": (
                        f"{_cap.get('subject_area')} {_cap.get('course_type')} "
                        f"当前负载 {_cap.get('current_load')}/{_cap.get('max_capacity')}，"
                        f"状态：{_cap.get('capacity_status')}"
                    ),
                    "suggested_action": (
                        f"谨慎推广 {_cap.get('subject_area')} {_cap.get('course_type')}，"
                        f"先评估老师档期再接单"
                    ),
                })
                risks_saved += 1

        # 规则2：押题/保过产品销售承诺风险（固定规则）
        for _product, _risk_desc in [
            ("final_prediction", "押题产品不能承诺100%押中，需统一使用'复习重点预测+Mock训练+评分点梳理'"),
            ("guaranteed", "保过辅导不能承诺任何分数，需明确退款条款"),
        ]:
            _save_risk({
                "signal_date": _dt2.utcnow(),
                "product": _product,
                "risk_type": "销售承诺风险",
                "risk_level": "medium",
                "evidence": "业务规则：押题/保过类产品存在系统性表达风险",
                "suggested_action": _risk_desc,
            })
            risks_saved += 1

        # 规则3：分析近期订单集中方向
        from collections import Counter as _Counter
        _recent_orders = _list_orders(days=14, limit=500)
        _product_counter = _Counter(_o.get("product") for _o in _recent_orders)

        # 规则4：AI率风险（Dissertation相关）
        _diss_count = _product_counter.get("dissertation", 0)
        if _diss_count > 0:
            _save_risk({
                "signal_date": _dt2.utcnow(),
                "product": "dissertation",
                "risk_type": "AI率风险",
                "risk_level": "medium",
                "evidence": f"近14天Dissertation订单{_diss_count}单，AI率检测客户预期偏高",
                "suggested_action": "统一销售表达：不绝对保证AI率，但确保Turnitin+AI双检测",
            })
            risks_saved += 1

        print(f"✅ 订单风险信号生成完成：{risks_saved} 条")

    elif cmd == "run-daily":
        print("\n🚀 运行每日自动化工作流...")
        from workflows.daily import DailyWorkflow
        trigger = args[1] if len(args) > 1 else "manual"
        wf = DailyWorkflow(config)
        result = wf.run(trigger=trigger)
        status = result.get("status", "unknown")
        icon = {"success": "✅", "partial_success": "⚠️", "failed": "❌"}.get(status, "⚪")
        print(f"\n{icon} 工作流状态：{status}  (run_id={result.get('run_id')})")
        print(f"\n{result.get('summary', '')}")
        if result.get("error"):
            print(f"错误：{result['error']}")

    elif cmd == "update-school-scores":
        print("\n🏫 计算学校机会评分（内部数据，纯规则，不调用AI）...")
        from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
        top_n = int(args[1]) if len(args) > 1 else 20
        results = SchoolOpportunityScoringAgent(config).run(top_n=top_n)
        print(f"\n{'学校':<10s}{'国家':<10s}{'机会分':<6s}{'优先级':<8s}{'阶段':<14s}{'热度':<8s}")
        for r in results:
            print(f"{r['school_name']:<10s}{r['country']:<10s}{r['opportunity_score']:<6d}"
                  f"{r['priority_level']:<8s}{r['current_stage']:<14s}{r['demand_heat']:<8s}")
        n_unknown = sum(1 for r in results if r["priority_level"] == "Unknown")
        print(f"\n✅ 已评分 {len(results)} 所学校（其中 {n_unknown} 所资料不足=Unknown），写入 school_scores 表")

    elif cmd == "generate-school-strategy-cards":
        print("\n🃏 生成学校策略卡（仅 S/A/B 级，资料不足学校跳过）...")
        from agents.school_strategy_card_agent import SchoolStrategyCardAgent
        cards = SchoolStrategyCardAgent(config).run()
        ok = [c for c in cards if "error" not in c]
        for c in ok:
            print(f"  ✅ {c['school_name']} [{c['priority_level']}] 主推:{c.get('main_product','')} 可信度:{c.get('confidence','')}")
        for c in cards:
            if "error" in c:
                print(f"  ❌ {c.get('school_name','?')}: {c['error']}")
        print(f"\n✅ 生成 {len(ok)} 张策略卡，写入 school_strategy_cards 表")

    # ── V9 新增命令 ──────────────────────────────────────────────

    elif cmd == "update-opportunity-scores":
        print("\n📊 更新全类型机会评分（学校+产品+线索）...")
        from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
        from agents.product_supply_risk_agent import ProductSupplyRiskAgent
        from agents.lead_opportunity_scoring_agent import LeadOpportunityScoringAgent
        sr = SchoolOpportunityScoringAgent(config).run(top_n=20)
        ProductSupplyRiskAgent(config).analyze(period_days=14)
        lr = LeadOpportunityScoringAgent(config).run(days_lookback=14)
        print(f"✅ 学校评分{len(sr)}所，线索评分{len(lr)}条，产品评分已写入 opportunity_scores")

    elif cmd == "predict-campaigns":
        week_start = None
        for a in args:
            if a.startswith("--week="):
                week_start = a[7:]
            elif a.startswith("--week"):
                idx = args.index(a)
                if idx + 1 < len(args):
                    week_start = args[idx + 1]
        print(f"\n🎯 生成广告预测（周：{week_start or '本周'}）...")
        from agents.campaign_prediction_agent import CampaignPredictionAgent
        preds = CampaignPredictionAgent(config).run(week_start=week_start, top_schools=5, top_products=3)
        for p in preds[:10]:
            print(f"  {p['school']} × {p['product']} × {p['channel']}: "
                  f"{p['predicted_leads_low']}–{p['predicted_leads_high']} 条（{p['confidence']}）")
        print(f"✅ 生成 {len(preds)} 条预测，写入 campaign_predictions 表")

    elif cmd == "generate-execution-tasks":
        print("\n✅ 从本周策略生成执行任务（基于学校策略卡 + 供给分析）...")
        from agents.school_opportunity_scoring_agent import SchoolOpportunityScoringAgent
        from database import save_task
        scores = SchoolOpportunityScoringAgent(config).run(top_n=10)
        created = 0
        for s in scores:
            if s["priority_level"] not in ("S", "A"):
                continue
            save_task({
                "title": f"【{s['priority_level']}级】{s['school_name']} 本周推广跟进",
                "department": "推广部", "priority": "高" if s["priority_level"] == "S" else "中",
                "task_source": "AI生成", "task_type": "内容发布",
                "related_school": s["school_name"],
                "description": f"学校机会分{s['opportunity_score']}，当前阶段：{s['current_stage']}，主推：{'、'.join(s['hot_products'][:2])}",
            })
            created += 1
        print(f"✅ 已生成 {created} 条执行任务，写入 tasks 表")

    elif cmd == "run-daily-execution-check":
        print("\n🔔 运行每日执行监督工作流...")
        from workflows.daily_execution import DailyExecutionWorkflow
        result = DailyExecutionWorkflow(config).run()
        print(f"✅ {result.get('summary','完成')}")

    elif cmd == "run-weekly-review":
        week_start = None
        for a in args:
            if a.startswith("--week="):
                week_start = a[7:]
            elif a == "--week" and args.index(a) + 1 < len(args):
                week_start = args[args.index(a) + 1]
        if not week_start:
            from datetime import timedelta
            today = datetime.now()
            week_start = (today - timedelta(days=today.weekday() + 7)).strftime("%Y-%m-%d")
        print(f"\n🔁 生成周复盘（{week_start}）...")
        from agents.weekly_review_agent import WeeklyReviewAgent
        rv = WeeklyReviewAgent(config).run(week_start=week_start)
        print(f"✅ 复盘已生成：{rv.get('review_summary','')[:100]}")
        print(f"  任务完成：{rv.get('tasks_done',0)}/{rv.get('tasks_total',0)}")

    elif cmd == "run-weekly-growth":
        week_start = None
        for a in args:
            if a.startswith("--week="):
                week_start = a[7:]
            elif a == "--week" and args.index(a) + 1 < len(args):
                week_start = args[args.index(a) + 1]
        print(f"\n🚀 运行每周增长管理工作流（{week_start or '本周'}）...")
        from workflows.weekly_growth import WeeklyGrowthWorkflow
        result = WeeklyGrowthWorkflow(config, week_start=week_start).run()
        print(f"✅ {result.get('summary','完成')}")

    elif cmd == "run-weekly-growth-brief":
        dry_run  = "--dry-run" in args
        use_llm  = True if "--use-llm" in args else (False if "--no-llm" in args else None)
        # 默认：dry-run → no-llm；live → use-llm
        if use_llm is None:
            use_llm = not dry_run
        if dry_run:
            mode_label = f"DRY-RUN · {'允许LLM' if use_llm else '零LLM'} · 不推送企微"
        else:
            mode_label = "LIVE（含LLM · 将存库 · 将推送）"
        print(f"\n🗺️  本周增长作战单 [{mode_label}]")
        print("=" * 60)

        from agents.weekly_growth_brief_agent import WeeklyGrowthBriefAgent
        brief = WeeklyGrowthBriefAgent().run(dry_run=dry_run, use_llm=use_llm)

        # ── ① 5个时间窗口 ─────────────────────────────────────
        print("\n【① 时间窗口预测】")
        for w, info in brief['time_windows'].items():
            top_p = info.get("top_products", [])
            top_name = top_p[0].get("product", "") if top_p else ""
            print(f"  [{w}] 紧迫度={info.get('urgency','?'):<4} "
                  f"预估线索={info.get('total_leads',0):>3}条"
                  + (f"  主推：{top_name}" if top_name else ""))

        # ── ② 渠道内容建议 ────────────────────────────────────
        print(f"\n【② 渠道内容建议（{len(brief['channel_strategy'])}条）】")
        CH_CN = {"xiaohongshu":"小红书","vertical_account":"垂直号",
                 "moments":"朋友圈","community":"社群",
                 "referral":"转介绍","old_customer":"老客户"}
        for ch in brief['channel_strategy']:
            ch_name = CH_CN.get(ch.get("channel",""), ch.get("channel",""))
            print(f"  [{ch.get('priority','P2')}] {ch_name:<6} {ch.get('hook_idea','')[:50]}")
            print(f"       依据：{ch.get('reason','')[:60]}")

        # ── ③ 顾问建议 ────────────────────────────────────────
        print(f"\n【③ 顾问建议（{len(brief['consultant_suggestions'])}条）】")
        for s in brief['consultant_suggestions']:
            action = str(s.get('action', ''))
            print(f"  [P{s.get('priority','')}] {action}")
            if s.get('next_questions'):
                print(f"       补问：{s['next_questions'][0]}")
            if s.get('not_recommended'):
                print(f"       不推荐：{'、'.join(s['not_recommended'])}")
            print(f"       目标：{s.get('success_metric','')}")
            print(f"       依据：{s.get('data_evidence','')}")

        # ── ④ 学管建议 ────────────────────────────────────────
        print("\n【④ 学管建议】")
        xs = brief.get('xueguan_suggestions', {})
        print(f"  核心：{xs.get('week_focus','')}")
        for act in xs.get("coordinator_actions", []):
            print(f"  · {act}")
        print(f"  风险：{xs.get('delivery_risks','')}")

        # ── ⑤ 产品红绿灯（按本周需求排序）────────────────────
        print("\n【⑤ 产品红绿灯（按本周需求相关度排序）】")

        # 从 matched_needs 建立 产品→需求 上下文映射
        _product_need_ctx: dict = {}
        for _match in brief.get('matched_needs', []):
            for _rec in _match.get('recommended_products', []):
                _pid = _rec['product_id']
                if _pid not in _product_need_ctx:
                    _product_need_ctx[_pid] = {
                        'need_label':   _match['label'],
                        'heat':         _match['heat_score'],
                        'orders':       _match['order_count'],
                        'action_level': _match.get('action_level', 'hold'),
                        'push_level':   _rec.get('push_level', 'unknown'),
                    }

        _ACTION_STR = {
            'push_now':     '→ 本周主推',
            'push_cautious':'→ 谨慎推，先问学管',
            'hold':         '→ 暂无需求，不主动推',
        }
        _STATUS_ICON = {'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'grey': '⚫'}

        # 排序：有需求信号的排前（按热度），无信号的排后
        def _tl_sort(item):
            _pid, _ = item
            _ctx = _product_need_ctx.get(_pid)
            return (-(_ctx['heat'] if _ctx else 0), _pid)

        for pid, tl in sorted(brief['product_traffic_lights'].items(), key=_tl_sort):
            ctx    = _product_need_ctx.get(pid)
            icon   = _STATUS_ICON.get(tl.get('status', ''), '⚫')
            pname  = tl.get('product_name', pid)
            reason = tl.get('status_reason', '')
            cap    = tl.get('teacher_capacity', '')
            print(f"\n  {icon} {pname}")
            print(f"     红绿灯：{reason}")
            if cap and cap != '数据不足':
                print(f"     容量：{cap}")
            if ctx and ctx['heat'] > 0:
                action_str = _ACTION_STR.get(ctx['action_level'], '')
                print(f"     本周需求：{ctx['need_label']}（近30天{ctx['orders']}单，热度{ctx['heat']}%）{action_str}")
            else:
                print(f"     本周需求：暂无明确信号 → 不主动推，维持常规")

        # ── ⑥ 数据依据 ───────────────────────────────────────
        print("\n【⑥ 数据依据】")
        snap = brief.get("wechat_push_preview", "")
        db_snap = brief.get("missing_data_report", {})
        print(f"  orders总量：{db_snap.get('order_count_total', '?')}条")
        print(f"  近30天成单：{db_snap.get('order_count_30d', '?')}单")
        print(f"  leads总量：{db_snap.get('lead_count', '?')}条")
        print(f"  teacher_capacity：{db_snap.get('teacher_capacity', '?')}条")
        print(f"  school_calendar：{db_snap.get('school_calendar', '?')}条")

        # ── ⑦ 缺失数据清单 ───────────────────────────────────
        print("\n【⑦ 缺失数据清单】")
        mdr = brief.get("missing_data_report", {})
        missing = mdr.get("missing", [])
        warnings_list = mdr.get("warnings", [])
        if missing:
            for m in missing:
                print(f"  {m}")
        if warnings_list:
            for w in warnings_list:
                print(f"  {w}")
        if not missing and not warnings_list:
            print("  ✅ 数据完整，无缺失")
        print(f"  数据充分度：{'✅ 充分' if mdr.get('is_data_sufficient') else '❌ 不足，建议补录后再发布'}")

        # ── ⑧ 可信度 ─────────────────────────────────────────
        print(f"\n【⑧ 可信度】{brief['confidence'].upper()}"
              f"  |  AI来源：{brief['ai_source']}"
              f"  |  风险等级：{brief['overall_risk'].upper()}")

        # ── ⑨ 内容校准记录 ───────────────────────────────────
        print("\n【⑨ 内容校准（RiskGuard禁用词）】")
        fb = brief.get("risk_alerts", [])
        calibration = [a for a in fb if a.get("rule_id", "").startswith("R12")]
        if calibration:
            for a in calibration:
                print(f"  {a.get('blocked_content','')} → {a.get('suggested_fix','')}")
        else:
            print("  ✅ 未触发禁用词")

        # ── ⑩ RiskGuard 检查结果 ──────────────────────────────
        print(f"\n【⑩ RiskGuard告警（{len(brief['risk_alerts'])}条）】")
        sev_map = {"critical":"🚨","high":"🔴","medium":"🟡","low":"⚪"}
        for a in sorted(brief['risk_alerts'],
                        key=lambda x: {"critical":0,"high":1,"medium":2,"low":3}.get(x.get("severity","low"),3)):
            sev = a.get("severity","low")
            print(f"  {sev_map.get(sev,'')} [{sev.upper()}] {a.get('rule_name','')}")
            print(f"       → {a.get('suggested_fix','')[:60]}")
        if not brief['risk_alerts']:
            print("  ✅ 无告警")

        print("\n" + "=" * 60)
        if dry_run:
            print("✅ [DRY-RUN完成] 以上内容未发送企业微信，未写入数据库")
            print("   验证通过后运行（不加--dry-run）正式发布")
        else:
            print(f"✅ [LIVE完成] brief_id={brief.get('brief_id')}  已存库")

    elif cmd == "diagnose-orders-date":
        # ══════════════════════════════════════════════════════════
        # orders 日期诊断：不修改数据，只读
        # ══════════════════════════════════════════════════════════
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt, timedelta as _td
        _db_path = os.environ.get("DATABASE_URL", "sqlite:///data/marketing.db")
        _db_path = _db_path.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.isabs(_db_path):
            _db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _db_path)

        print(f"\n🔍 【orders 日期诊断】数据库：{_db_path}")
        print("=" * 65)

        _conn = _sqlite3.connect(_db_path)
        _cur  = _conn.cursor()

        # 1. 总数
        _total = _cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        print(f"\n① orders 总数：{_total} 条")

        # 2. order_date 非空/空
        _nonempty = _cur.execute(
            "SELECT COUNT(*) FROM orders WHERE order_date IS NOT NULL AND order_date != ''"
        ).fetchone()[0]
        _empty = _total - _nonempty
        print(f"② order_date 非空：{_nonempty} 条 / 为空：{_empty} 条")

        # 3. 字段类型（SQLite TYPEOF）
        _sample_type = _cur.execute(
            "SELECT TYPEOF(order_date) FROM orders WHERE order_date IS NOT NULL LIMIT 1"
        ).fetchone()
        print(f"③ order_date 字段类型（SQLite TYPEOF）：{_sample_type[0] if _sample_type else '无数据'}")

        # 4. 最新10条原始值
        _latest10 = _cur.execute(
            "SELECT order_date FROM orders WHERE order_date IS NOT NULL ORDER BY order_date DESC LIMIT 10"
        ).fetchall()
        print(f"\n④ 最新10条 order_date 原始值：")
        for row in _latest10:
            print(f"   {row[0]!r}")

        # 5. min / max
        _minmax = _cur.execute(
            "SELECT MIN(order_date), MAX(order_date) FROM orders WHERE order_date IS NOT NULL"
        ).fetchone()
        print(f"\n⑤ min(order_date)：{_minmax[0]}")
        print(f"   max(order_date)：{_minmax[1]}")

        # 6. 当前时间基准
        _now_utc   = _dt.utcnow()
        _now_local = _dt.now()
        print(f"\n⑥ 当前时间基准")
        print(f"   datetime.utcnow()  = {_now_utc.isoformat()}")
        print(f"   datetime.now()     = {_now_local.isoformat()}")
        print(f"   UTC偏移（本地-UTC）= {(_now_local - _now_utc).total_seconds()/3600:.1f} 小时")

        # 7. 近期订单数（分别用 UTC 和本地时间查）
        print(f"\n⑦ 近期订单数（SQL直接比较字符串）：")
        for _days in [7, 30, 60, 90, 180, 365]:
            _cutoff_utc   = (_now_utc   - _td(days=_days)).strftime("%Y-%m-%d %H:%M:%S")
            _cutoff_local = (_now_local - _td(days=_days)).strftime("%Y-%m-%d %H:%M:%S")
            _cnt_utc   = _cur.execute(
                "SELECT COUNT(*) FROM orders WHERE order_date >= ?", (_cutoff_utc,)
            ).fetchone()[0]
            _cnt_local = _cur.execute(
                "SELECT COUNT(*) FROM orders WHERE order_date >= ?", (_cutoff_local,)
            ).fetchone()[0]
            print(f"   近{_days:>3}天 | UTC截止={_cutoff_utc[:10]} → {_cnt_utc}条 "
                  f"| 本地截止={_cutoff_local[:10]} → {_cnt_local}条")

        # 8. 样本分析（是否有 date-only 格式）
        _date_only = _cur.execute(
            "SELECT COUNT(*) FROM orders WHERE order_date IS NOT NULL AND LENGTH(order_date) = 10"
        ).fetchone()[0]
        _datetime_full = _cur.execute(
            "SELECT COUNT(*) FROM orders WHERE order_date IS NOT NULL AND LENGTH(order_date) > 10"
        ).fetchone()[0]
        print(f"\n⑧ 格式分析：")
        print(f"   纯日期格式(YYYY-MM-DD, 长度=10)：{_date_only} 条")
        print(f"   含时间格式(长度>10)：{_datetime_full} 条")

        # 9. 是否存在 created_at
        _has_created = _cur.execute(
            "SELECT COUNT(*) FROM orders WHERE created_at IS NOT NULL"
        ).fetchone()[0]
        _created_max = _cur.execute("SELECT MAX(created_at) FROM orders").fetchone()[0]
        print(f"\n⑨ created_at 非空：{_has_created}条  最新值：{_created_max}")

        # 10. 综合判断
        print(f"\n⑩ 综合判断：")
        _max_date_str = _minmax[1] or ""
        if not _minmax[1]:
            print("   ❌ order_date 全部为空，无法分析")
        else:
            # 尝试解析 max 日期
            _parsed_max = None
            for _fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    _parsed_max = _dt.strptime(_max_date_str[:19], _fmt[:len(_max_date_str[:19])])
                    break
                except Exception:
                    pass
            if _parsed_max:
                _days_since_max = (_now_local - _parsed_max).days
                print(f"   最新订单距今：{_days_since_max} 天（{_max_date_str}）")
                if _days_since_max > 30:
                    print(f"   ⚠️  最新订单已超过30天 → 近30天真实为0，不是时区问题")
                    print(f"   ⚠️  需确认：CRM同步是否已停止？最近一次同步时间？")
                else:
                    print(f"   ✅ 最新订单在30天内 → 查询逻辑可能存在时区/格式问题")
                    if _date_only > 0 and _datetime_full == 0:
                        print(f"   🔍 所有 order_date 为纯日期格式（YYYY-MM-DD）")
                        print(f"   🔍 当前查询使用 datetime 字符串比较，可能因格式不匹配导致0结果")
                        print(f"   → 修复建议：查询时用 DATE(order_date) >= ? 而非全量字符串比较")
            else:
                print(f"   ⚠️  无法解析 max(order_date) = {_max_date_str!r}")

        _conn.close()
        print("\n" + "=" * 65)
        print("诊断完成，未修改任何数据。")

    elif cmd == "diagnose-teacher-capacity":
        # ══════════════════════════════════════════════════════════
        # teacher_capacity 产品匹配诊断：不修改数据，只读
        # ══════════════════════════════════════════════════════════
        import sqlite3 as _sqlite3
        _db_path = os.environ.get("DATABASE_URL", "sqlite:///data/marketing.db")
        _db_path = _db_path.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.isabs(_db_path):
            _db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _db_path)

        print(f"\n🔍 【teacher_capacity 产品匹配诊断】")
        print("=" * 65)

        _conn = _sqlite3.connect(_db_path)
        _cur  = _conn.cursor()

        # 1. 总数
        _total = _cur.execute("SELECT COUNT(*) FROM teacher_capacity").fetchone()[0]
        print(f"\n① teacher_capacity 总数：{_total} 条")

        # 2. 原始 product_name 列表（去重，含数量）
        _raw_products = _cur.execute(
            "SELECT product_name, COUNT(*) as cnt FROM teacher_capacity "
            "GROUP BY product_name ORDER BY cnt DESC"
        ).fetchall()
        print(f"\n② 原始 product_name（{len(_raw_products)}种）：")
        for _pn, _cnt in _raw_products:
            print(f"   {_cnt:>3}条  |  {_pn!r}")

        # 3. subject_area / teacher_name / capacity 字段样本
        _cols = [d[1] for d in _cur.execute("PRAGMA table_info(teacher_capacity)").fetchall()]
        print(f"\n③ teacher_capacity 表字段：{_cols}")
        _samples = _cur.execute(
            "SELECT * FROM teacher_capacity LIMIT 5"
        ).fetchall()
        print(f"\n④ 前5条样本数据：")
        for row in _samples:
            print(f"   {dict(zip(_cols, row))}")

        _conn.close()

        # 4. 系统核心产品列表（ProductTrafficLight 中的定义）
        _CORE_PRODUCTS = [
            ("final_prediction",  "Final考前冲刺规划"),
            ("regular",           "课业辅导"),
            ("dissertation",      "毕业论文辅导"),
            ("guaranteed",        "保过辅导"),
            ("annual_package",    "学年包"),
            ("dp_premium",        "DP旗舰版"),
        ]
        _PRODUCT_SUBJECT_MAP = {
            "final_prediction":  ["final_exam", "exam_prep", "final"],
            "regular":           ["regular", "coursework", "general"],
            "dissertation":      ["dissertation", "thesis"],
            "guaranteed":        ["guaranteed", "pass_guarantee"],
            "annual_package":    ["annual", "package"],
            "dp_premium":        ["dp", "diploma"],
        }
        print(f"\n⑤ 系统核心产品（ProductTrafficLight 定义）：")
        for _pid, _pname in _CORE_PRODUCTS:
            _keywords = _PRODUCT_SUBJECT_MAP.get(_pid, [])
            print(f"   {_pid:<20} {_pname}  匹配关键词：{_keywords}")

        # 5. 逐条匹配分析
        print(f"\n⑥ 原始 product_name vs 核心产品匹配结果：")
        _unmatched = []
        _matched   = []
        for _pn, _cnt in _raw_products:
            _pn_lower = (_pn or "").lower()
            _hit = None
            for _pid, _pname in _CORE_PRODUCTS:
                _kws = _PRODUCT_SUBJECT_MAP.get(_pid, [])
                if any(_kw in _pn_lower for _kw in _kws):
                    _hit = (_pid, _pname)
                    break
            if _hit:
                _matched.append((_pn, _cnt, _hit))
                print(f"   ✅ {_pn!r:30} ({_cnt}条) → {_hit[0]}")
            else:
                _unmatched.append((_pn, _cnt))
                print(f"   ❌ {_pn!r:30} ({_cnt}条) → 无法匹配")

        print(f"\n⑦ 汇总：匹配成功 {len(_matched)} 种，无法匹配 {len(_unmatched)} 种")

        # 6. 为什么核心产品是灰
        print(f"\n⑧ 核心产品为何是灰（逐个分析）：")
        _matched_pids = {h[0] for _, _, h in _matched}
        for _pid, _pname in _CORE_PRODUCTS:
            if _pid in _matched_pids:
                print(f"   🟡 {_pname}：有匹配的老师资源（但需确认 capacity > 0）")
            else:
                _kws = _PRODUCT_SUBJECT_MAP.get(_pid, [])
                print(f"   ⚫ {_pname}：无匹配 —— 当前原始字段不含关键词 {_kws}")

        # 7. 建议映射表
        print(f"\n⑨ 建议产品映射表（基于原始数据推断，需人工确认）：")
        print(f"   {'原始 product_name':<35} → 建议映射到")
        _SUGGEST_MAP = {
            "dissertation": "dissertation",
            "essay": "regular",
            "assignment": "regular",
            "exam": "final_prediction",
            "final": "final_prediction",
            "coursework": "regular",
            "tutoring": "regular",
            "包课": "annual_package",
            "年包": "annual_package",
            "保分": "guaranteed",
            "dp": "dp_premium",
            "report": "regular",
        }
        _conn2 = _sqlite3.connect(_db_path)
        _cur2  = _conn2.cursor()
        _raw2  = _cur2.execute(
            "SELECT DISTINCT product_name FROM teacher_capacity WHERE product_name IS NOT NULL"
        ).fetchall()
        _conn2.close()
        for (_pn,) in _raw2:
            _pn_lower = (_pn or "").lower()
            _suggestion = next(
                (v for k, v in _SUGGEST_MAP.items() if k in _pn_lower), "❓ 需人工确认"
            )
            print(f"   {_pn!r:<35} → {_suggestion}")

        # 同时诊断 orders 里的产品分布
        _conn3 = _sqlite3.connect(_db_path)
        _cur3  = _conn3.cursor()
        _order_products = _cur3.execute(
            "SELECT product, COUNT(*) as cnt FROM orders "
            "WHERE product IS NOT NULL AND product != '' "
            "GROUP BY product ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
        _conn3.close()
        print(f"\n⑩ orders 表中 product 字段分布（Top20）：")
        for _pn, _cnt in _order_products:
            _pn_lower = (_pn or "").lower()
            _suggestion = next(
                (v for k, v in _SUGGEST_MAP.items() if k in _pn_lower), "❓"
            )
            print(f"   {_cnt:>5}条  |  {_pn!r:<30} → 建议：{_suggestion}")

        print("\n" + "=" * 65)
        print("诊断完成，未修改任何数据。")

    elif cmd == "run-attribution":
        days_lb = 90
        for a in args:
            if a.startswith("--days="):
                days_lb = int(a[7:])
            elif a == "--days" and args.index(a) + 1 < len(args):
                days_lb = int(args[args.index(a) + 1])
        print(f"\n📊 运行归因分析（最近 {days_lb} 天）...")
        from agents.attribution_analysis_agent import AttributionAnalysisAgent
        snap = AttributionAnalysisAgent(config).run(days_lookback=days_lb)
        print(f"✅ 归因完成：{snap['order_count']} 订单 / {snap['lead_count']} 线索 / ¥{snap['total_revenue']:,.0f}")
        for ins in snap.get("key_insights") or []:
            print(f"  💡 {ins}")
        for act in snap.get("action_items") or []:
            print(f"  → {act}")

    elif cmd == "health-check":
        import sys as _sys
        ok = True
        checks = []

        # Python 版本
        v = _sys.version_info
        checks.append(("✅" if v >= (3, 11) else "⚠️", f"Python {v.major}.{v.minor}.{v.micro}"))

        # .env 文件
        env_exists = os.path.exists(".env")
        checks.append(("✅" if env_exists else "⚠️",
                        ".env 文件已存在" if env_exists else ".env 文件不存在（请从 .env.example 复制并填写）"))

        # API Keys
        ak = os.environ.get("ANTHROPIC_API_KEY", "")
        checks.append(("✅" if ak else "⚠️", "ANTHROPIC_API_KEY " + ("已配置" if ak else "未配置（必填）")))

        ww = os.environ.get("WECHAT_WORK_WEBHOOK", "")
        checks.append(("✅" if ww else "⚠️", "WECHAT_WORK_WEBHOOK " + ("已配置" if ww else "未配置（推送功能不可用）")))

        # 数据库连接 + 核心表
        try:
            from database.db import init_db as _hc_init_db, engine
            from sqlalchemy import inspect as _inspect, text
            _hc_init_db()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            insp = _inspect(engine)
            tables = insp.get_table_names()
            core_tables = ["orders", "leads", "company_facts", "business_dictionary"]
            missing_tables = [t for t in core_tables if t not in tables]
            if missing_tables:
                checks.append(("⚠️", f"数据库已连接，缺少表：{missing_tables}（运行 python main.py init）"))
            else:
                checks.append(("✅", f"数据库已连接，核心表齐全（共 {len(tables)} 张表）"))
        except Exception as e:
            checks.append(("❌", f"数据库连接失败：{e}"))
            ok = False

        # 关键文件
        for fname in ["dashboard.py", "config.yaml", "requirements.txt"]:
            exists = os.path.exists(fname)
            checks.append(("✅" if exists else "❌", fname + (" 存在" if exists else " 不存在")))
            if not exists:
                ok = False

        # 关键目录
        for dname in ["data", "knowledge_base", "agents", "database", "workflows"]:
            exists = os.path.isdir(dname)
            checks.append(("✅" if exists else "❌", f"{dname}/ " + ("存在" if exists else "不存在")))
            if not exists:
                ok = False

        # 运行时目录（非必须，自动创建）
        for dname in ["logs", "outputs", "deploy"]:
            exists = os.path.isdir(dname)
            checks.append(("✅" if exists else "⚠️", f"{dname}/ " + ("存在" if exists else "不存在（首次运行会自动创建）")))

        # 核心 Agent 导入
        try:
            from agents.grounded_business_agent import GroundedBusinessAgent
            from agents.fact_extraction_agent import FactExtractionAgent
            from agents.promotion_strategy_agent import PromotionStrategyAgent
            checks.append(("✅", "核心 Agent 导入成功"))
        except Exception as e:
            checks.append(("❌", f"核心 Agent 导入失败：{e}"))
            ok = False

        print("\n" + "=" * 52)
        print("  极致教育增长作战系统 · 健康检查")
        print("=" * 52)
        for icon, msg in checks:
            print(f"  {icon}  {msg}")
        print("=" * 52)
        print("  结论：" + ("✅ 系统基本正常，可以启动" if ok else "⚠️  存在需要处理的问题，请检查上方 ⚠️/❌ 项"))
        print()

    elif cmd == "test-llm":
        _cmd_test_llm(args)

    elif cmd == "diagnose-product-catalog":
        _cmd_diagnose_product_catalog()

    elif cmd == "diagnose-student-needs":
        _cmd_diagnose_student_needs()

    elif cmd == "test-traffic-light":
        _cmd_test_traffic_light()

    else:
        print(f"未知命令：{cmd}")
        print(__doc__)
        sys.exit(1)


def _cmd_test_llm(args: list):
    """python main.py test-llm [--provider claude|deepseek|qwen|rule]"""
    from services.llm import LLMRouter
    from services.llm.anthropic_provider import AnthropicProvider
    from services.llm.openai_compatible_provider import OpenAICompatibleProvider
    from services.llm.rule_fallback_provider import RuleFallbackProvider

    target = None
    for a in args:
        if a.startswith("--provider="):
            target = a.split("=", 1)[1]
        elif a == "--provider" and args.index(a) + 1 < len(args):
            target = args[args.index(a) + 1]

    print("\n" + "=" * 52)
    print("  LLM Health Check")
    print("=" * 52)

    providers = {
        "claude":        AnthropicProvider(),
        "deepseek":      OpenAICompatibleProvider("deepseek"),
        "qwen":          OpenAICompatibleProvider("qwen"),
        "rule_fallback": RuleFallbackProvider(),
    }

    check_list = [target] if target else list(providers.keys())
    results = {}
    for name in check_list:
        p = providers.get(name)
        if not p:
            print(f"\n  {name}: unknown provider")
            continue
        print(f"\n  {name}:")
        r = p.health_check()
        status = r.get("status", "?")
        avail  = r.get("available", False)
        print(f"    status:    {status}")
        if r.get("error"):
            print(f"    error:     {r['error'][:80]}")
        if r.get("model"):
            print(f"    model:     {r['model']}")
        print(f"    available: {'✅ true' if avail else '❌ false'}")
        results[name] = r

    print("\n" + "-" * 52)
    router = LLMRouter()
    active = next(
        (n for n in router._order if results.get(n, {}).get("available")),
        "rule_fallback"
    )
    print(f"  Router order:   {router._order}")
    print(f"  Active provider: ✅ {active}")
    print("=" * 52 + "\n")


def _cmd_diagnose_student_needs():
    """python main.py diagnose-student-needs — 诊断学生需求识别结果"""
    print("\n" + "=" * 65)
    print("  学生需求识别诊断（StudentNeedEngine）")
    print("=" * 65)

    try:
        from services.student_need_engine import StudentNeedEngine
        result = StudentNeedEngine().run(days=30)
    except Exception as e:
        print(f"\n❌ StudentNeedEngine 运行失败: {e}")
        import traceback; traceback.print_exc()
        return

    print(f"\n数据范围：近30天  总订单：{result['total_orders']}条  总线索：{result['total_leads']}条\n")
    print(f"{'需求类型':<28} {'订单':>5} {'线索':>5} {'热度':>6}  {'执行建议'}")
    print("-" * 65)

    for m in result["need_summary"]:
        heat_bar = "█" * (m["heat_score"] // 10) + "░" * (10 - m["heat_score"] // 10)
        print(f"{m['label']:<28} {m['order_count']:>5} {m['lead_count']:>5} "
              f"{m['heat_score']:>5}%  {heat_bar}")

    active = [m for m in result["need_summary"] if m["heat_score"] > 0]
    print(f"\n✅ 有热度的需求类型：{len(active)} 个")

    if active:
        print("\n--- 推荐产品映射 ---")
        for m in active[:4]:
            recs     = "、".join(m["recommended_products"])
            not_recs = "、".join(m["not_recommended"].keys())
            print(f"  {m['label']}：推 [{recs}]  |  不推 [{not_recs}]")

    unmapped = result.get("unmapped_orders", [])
    if unmapped:
        unmapped_cnt = sum(c for _, c in unmapped)
        print(f"\n⚠️  未映射 CRM 产品名：{len(unmapped)} 种，共 {unmapped_cnt} 条订单")
        for name, cnt in unmapped[:8]:
            print(f"     {name!r:25s} {cnt}条")
        if len(unmapped) > 8:
            print(f"     ... 共 {len(unmapped)} 种")
        print("\n   → 建议将这些名称加入 services/student_need_engine.py 的 crm_keywords")

    print("\n" + "=" * 65 + "\n")


def _cmd_diagnose_product_catalog():
    """
    python main.py diagnose-product-catalog
    诊断产品目录库加载状态及 CRM 数据映射情况。
    """
    import sqlite3 as _sql
    print("\n" + "=" * 65)
    print("  产品目录库诊断")
    print("=" * 65)

    # ── 1. 产品目录库基本信息 ──────────────────────────────────────
    try:
        from services.product_catalog_service import ProductCatalogService
        products = ProductCatalogService.load_active_products()
        catalog_ok = True
    except Exception as e:
        print(f"\n❌ 产品目录库加载失败: {e}")
        catalog_ok = False
        products = []

    if not catalog_ok:
        print("\n未找到产品目录库，请提供产品目录文件或知识库路径。")
        return

    categories = set(p["product_category"] for p in products)
    all_aliases = sum(len(p["aliases"]) for p in products)
    alias_map   = ProductCatalogService.get_alias_map()

    print(f"\n① 产品目录库状态：✅ 已找到")
    print(f"   来源：knowledge_base/product_catalog.py → PRODUCT_CATALOG")
    print(f"   active 产品数量：{len(products)}")
    print(f"   产品类别数量：{len(categories)}  ({', '.join(sorted(categories))})")
    print(f"   aliases 总数量：{all_aliases}（含名称、别名）")
    print(f"\n   产品列表：")
    for p in products:
        print(f"     {p['canonical_product_id']:20s}  {p['product_name']}  "
              f"[{p['product_category']}]  aliases={len(p['aliases'])}")

    # ── 2. ProductTrafficLight 硬编码检查 ────────────────────────
    import ast, pathlib
    tl_file = pathlib.Path(__file__).parent / "agents" / "product_traffic_light.py"
    hardcoded = False
    if tl_file.exists():
        src = tl_file.read_text()
        for marker in ["PRODUCTS = [", "CORE_PRODUCTS", "\"final_prediction\"",
                        "\"annual_package\"", "\"dp_premium\"", "\"guaranteed\""]:
            # 允许出现在注释里，只检查赋值语句
            if f"{marker}" in src and "ProductCatalogService" not in src:
                hardcoded = True
                break
    print(f"\n② ProductTrafficLight 硬编码检查：{'❌ 仍有硬编码' if hardcoded else '✅ 已使用产品目录库'}")

    # ── 3. orders 产品映射 ────────────────────────────────────────
    _db_path = os.environ.get("DATABASE_URL", "sqlite:///data/marketing.db")
    _db_path = _db_path.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.isabs(_db_path):
        _db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _db_path)

    try:
        conn = _sql.connect(_db_path)
        raw_orders = conn.execute(
            "SELECT product, COUNT(*) FROM orders WHERE product IS NOT NULL AND product != '' "
            "GROUP BY product ORDER BY COUNT(*) DESC"
        ).fetchall()
        raw_leads = conn.execute(
            "SELECT product_interest, COUNT(*) FROM leads "
            "WHERE product_interest IS NOT NULL AND product_interest != '' "
            "GROUP BY product_interest ORDER BY COUNT(*) DESC"
        ).fetchall()
        raw_cap = conn.execute(
            "SELECT subject_area, COUNT(*) FROM teacher_capacity "
            "GROUP BY subject_area ORDER BY COUNT(*) DESC"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"\n❌ 数据库读取失败: {e}")
        return

    def _check_mapping(raw_list, label):
        mapped, unmapped = [], []
        for raw, cnt in raw_list:
            result = ProductCatalogService.map_raw_product(raw)
            if result["canonical_product_id"]:
                mapped.append((raw, cnt, result["canonical_product_id"], result["confidence"]))
            else:
                unmapped.append((raw, cnt))
        total_mapped   = sum(c for _, c, _, _ in mapped)
        total_unmapped = sum(c for _, c in unmapped)
        total = total_mapped + total_unmapped
        print(f"\n{label}（共 {total} 条记录，{len(raw_list)} 种原始名）：")
        print(f"   ✅ 已映射：{len(mapped)} 种原始名，{total_mapped} 条记录")
        for raw, cnt, pid, conf in mapped[:8]:
            print(f"      {raw!r:25s} → {pid:20s}  ({cnt}条, {conf})")
        if len(mapped) > 8:
            print(f"      ... 共 {len(mapped)} 种")
        if unmapped:
            print(f"   ❌ 未映射（unmapped_products）：{len(unmapped)} 种原始名，{total_unmapped} 条记录")
            for raw, cnt in unmapped[:5]:
                print(f"      {raw!r:25s}  ({cnt}条) ← 需补充 alias")
            if len(unmapped) > 5:
                print(f"      ... 共 {len(unmapped)} 种")
        else:
            print(f"   ✅ 无未映射记录")

    _check_mapping(raw_orders, "③ orders.product 映射")
    _check_mapping(raw_leads,  "④ leads.product_interest 映射")

    # teacher_capacity 用 subject_area 匹配
    cap_mapped, cap_unmapped = [], []
    kw_map = {}
    for p in products:
        for kw in p.get("capacity_subject_keywords", []):
            kw_map[kw] = p["canonical_product_id"]
    for sa, cnt in raw_cap:
        low = str(sa).lower()
        matched = next((pid for kw, pid in kw_map.items() if kw in low), None)
        if matched:
            cap_mapped.append((sa, cnt, matched))
        else:
            cap_unmapped.append((sa, cnt))
    print(f"\n⑤ teacher_capacity.subject_area 映射（共 {len(raw_cap)} 种）：")
    print(f"   ✅ 已映射：{len(cap_mapped)} 种")
    for sa, cnt, pid in cap_mapped:
        print(f"      {str(sa):25s} → {pid}")
    if cap_unmapped:
        print(f"   ❌ 未映射：{len(cap_unmapped)} 种")
        for sa, cnt in cap_unmapped:
            print(f"      {str(sa):25s}  ({cnt}条)")
    else:
        print(f"   ✅ 无未映射记录")

    print("\n" + "=" * 65)
    print("  诊断完成，未修改任何数据。")
    print("=" * 65 + "\n")


def _cmd_test_traffic_light():
    """python main.py test-traffic-light — 单独跑红绿灯，输出每个产品详情。"""
    print("\n" + "=" * 65)
    print("  ProductTrafficLight 测试")
    print("=" * 65)

    try:
        from agents.product_traffic_light import ProductTrafficLight
        tl = ProductTrafficLight()
        result = tl.run()
    except RuntimeError as e:
        print(f"\n❌ {e}")
        return
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        import traceback; traceback.print_exc()
        return

    print(f"\n共评估 {len(result)} 个产品（来源：产品目录库）\n")
    for pid, info in result.items():
        icon = {"green": "🟢", "yellow": "🟡", "red": "🔴", "grey": "⚫"}.get(info["status"], "?")
        print(f"  {icon}  [{pid}] {info['product_name']}")
        print(f"       状态：{info['status_reason']}")
        print(f"       需求：{info['demand_trend']}（近7天={info['demand_7d']}单，前7天={info['demand_prev_7d']}单）")
        print(f"       容量：{info['teacher_capacity']}")
        print(f"       顾问：{info['consultant_note'][:60]}...")
        print(f"       学管：{info['xueguan_note'][:60]}...")
        print(f"       推广渠道：{', '.join(info['recommended_channels']) or '无'}")
        if info["missing_data"]:
            print(f"       缺失：{' / '.join(info['missing_data'])}")
        if info["forbidden_claims"]:
            print(f"       禁用：{', '.join(info['forbidden_claims'][:3])}")
        print(f"       来源：{info.get('catalog_source', '?')}")
        print()

    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
