"""
本周增长作战单生成脚本

用法：
  python scripts/weekly_growth_brief.py
  python scripts/weekly_growth_brief.py --push   # 生成后推送微信
"""
import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="生成本周增长作战单")
    parser.add_argument("--push", action="store_true", help="生成后推送企业微信")
    parser.add_argument("--no-db", action="store_true", help="仅输出，不存库")
    args = parser.parse_args()

    from database import init_db
    init_db()

    from agents.weekly_growth_brief_agent import WeeklyGrowthBriefAgent
    brief = WeeklyGrowthBriefAgent().run()

    print(f"\n{'='*60}")
    print(f"本周增长作战单  {brief['week_start']} ~ {brief['week_end']}")
    print(f"AI来源: {brief['ai_source']}  置信度: {brief['confidence']}  "
          f"风险: {brief['overall_risk']}  brief_id={brief.get('brief_id')}")
    print(f"{'='*60}\n")

    print("【产品红绿灯】")
    for pid, tl in brief['product_traffic_lights'].items():
        print(f"  {tl.get('status_display',''):<28} {tl.get('product_name', pid)}")
        print(f"    顾问：{tl.get('consultant_note','')}")
        print(f"    学管：{tl.get('xueguan_note','')}")
    print()

    print("【5个时间窗口预测】")
    for w, info in brief['time_windows'].items():
        print(f"  [{w}] 紧迫度={info.get('urgency','?')}  预估线索={info.get('total_leads',0)}条")
        for p in info.get('top_products', [])[:2]:
            print(f"    {p.get('country','')} {p.get('product','')} {p.get('leads',0)}条")
    print()

    print("【7渠道内容策略】")
    for ch in brief['channel_strategy']:
        print(f"  [{ch.get('channel','')}] {ch.get('hook_idea','')[:50]}")
        print(f"    顾问跟进：{ch.get('sales_handoff','')[:50]}")
    print()

    print("【顾问本周行动】")
    for i, s in enumerate(brief['consultant_suggestions'], 1):
        print(f"  {i}. [{s.get('priority','')}] {s.get('action','')[:60]}")
        print(f"     话术：{s.get('script_hint','')[:50]}")
    print()

    print("【学管本周行动】")
    xs = brief.get('xueguan_suggestions', {})
    print(f"  核心工作：{xs.get('week_focus','')}")
    for act in xs.get('coordinator_actions', []):
        print(f"  - {act}")
    print()

    print(f"【风险告警】（共{len(brief['risk_alerts'])}条）")
    for a in brief['risk_alerts']:
        print(f"  [{a.get('rule_id','')}] {a.get('severity',''):8s} {a.get('rule_name','')}")
        print(f"    问题：{a.get('blocked_content','')[:60]}")
        print(f"    建议：{a.get('suggested_fix','')[:60]}")
    print()

    print("【数据证据】")
    print(f"  {brief['data_evidence']}")
    print()

    if args.push:
        _push_to_wecom(brief)


def _push_to_wecom(brief: dict):
    import requests
    webhook = os.environ.get("WECHAT_WORK_WEBHOOK", os.environ.get("WECOM_WEBHOOK_URL", ""))
    if not webhook:
        print("[WARN] WECOM_WEBHOOK_URL not set, skipping push")
        return

    preview = brief.get("wechat_push_preview", "")

    def blen(s):
        return len(s.encode("utf-8"))

    LIMIT = 4000
    if blen(preview) <= LIMIT:
        chunks = [preview]
    else:
        chunks, current, cur_bytes = [], [], 0
        for line in preview.splitlines(keepends=True):
            lb = blen(line)
            if cur_bytes + lb > LIMIT and current:
                chunks.append("".join(current))
                current, cur_bytes = [], 0
            current.append(line)
            cur_bytes += lb
        if current:
            chunks.append("".join(current))

    for i, chunk in enumerate(chunks, 1):
        payload = {"msgtype": "markdown", "markdown": {"content": chunk}}
        resp = requests.post(webhook, json=payload, timeout=10)
        print(f"[WeChat] chunk {i}/{len(chunks)} → {resp.status_code} {resp.text[:80]}")


if __name__ == "__main__":
    main()
