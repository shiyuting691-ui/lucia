"""
FormatterAgent — 把营销内容格式化为企业微信 Markdown，推送到群
企业微信 Markdown 支持：**加粗**、<font color>颜色、> 引用、# 标题
颜色：info=蓝、warning=黄/橙、comment=灰、green_text=绿（部分客户端）
"""
import requests
import time


class FormatterAgent:
    # 企业微信支持的颜色标签
    BLUE   = lambda _, t: f'<font color="info">{t}</font>'
    ORANGE = lambda _, t: f'<font color="warning">{t}</font>'
    GREY   = lambda _, t: f'<font color="comment">{t}</font>'

    def __init__(self, webhook: str):
        self.webhook = webhook

    # ─────────────────────────────────────────
    # 发送入口
    # ─────────────────────────────────────────
    def send(self, blocks: list[str], delay: float = 0.6):
        """批量发送多条 Markdown 消息"""
        results = []
        for block in blocks:
            try:
                r = requests.post(self.webhook, json={
                    "msgtype": "markdown",
                    "markdown": {"content": block}
                }, timeout=10)
                ok = r.json().get("errcode") == 0
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"WeChat push failed: {e}")
                ok = False
            results.append(ok)
            if delay:
                time.sleep(delay)
        return results

    def send_one(self, content: str) -> bool:
        try:
            r = requests.post(self.webhook, json={
                "msgtype": "markdown",
                "markdown": {"content": content}
            }, timeout=10)
            return r.json().get("errcode") == 0
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"WeChat push failed: {e}")
            return False

    # ─────────────────────────────────────────
    # 月度计划格式化
    # ─────────────────────────────────────────
    def format_monthly_plan(self, plan: dict) -> list[str]:
        month = plan.get("month", "本月")
        theme = plan.get("core_theme", "")
        goal  = plan.get("core_goal", "")
        analysis = plan.get("situation_analysis", [])
        if isinstance(analysis, str):
            analysis = [s.strip() for s in analysis.split("【") if s.strip()]

        blocks = []

        # ── 封面块 ──
        blocks.append(
            f"# 📅 {month}营销战略计划\n"
            f"> **核心主题：**{theme}\n\n"
            f"> **核心目标：**<font color=\"warning\">{goal}</font>"
        )

        # ── 形势判断 ──
        analysis_lines = "\n".join(
            f"> {'🟢' if '机会' in str(a) else '🔴'} {str(a)[:80]}"
            for a in (analysis[:3] if isinstance(analysis, list) else [analysis])
        )
        blocks.append(
            f"## 💡 核心判断\n{analysis_lines}"
        )

        # ── 产品优先级 ──
        priority_lines = ""
        for p in plan.get("product_priority", [])[:3]:
            rank_emoji = ["🥇","🥈","🥉"][int(p.get("rank",1))-1] if int(p.get("rank",1)) <= 3 else "▪"
            priority_lines += (
                f">{rank_emoji} **{p.get('product','')}**\n"
                f">原因：{p.get('reason','')[:60]}\n"
                f">目标：<font color=\"warning\">{p.get('target','')}</font>\n\n"
            )
        blocks.append(f"## 🏆 产品优先级\n{priority_lines.rstrip()}")

        # ── 四周重点 ──
        week_lines = ""
        urgency_map = {"第1周": "🔴", "第2周": "🔴", "第3周": "🟡", "第4周": "🟢"}
        for w in plan.get("weekly_focus", []):
            week_label = w.get("week","")
            emoji = next((v for k,v in urgency_map.items() if k in week_label), "▪")
            week_lines += (
                f">{emoji} **{week_label}** — {w.get('theme','')}\n"
                f">核心：{w.get('core_action','')[:60]}\n"
                f">主推：<font color=\"info\">{w.get('product_focus','')}</font>　"
                f"KPI：<font color=\"warning\">{w.get('kpi','')[:30]}</font>\n\n"
            )
        blocks.append(f"## 📆 四周执行重点\n{week_lines.rstrip()}")

        # ── 渠道策略 ──
        cs = plan.get("channel_strategy", {})
        ch_lines = (
            f">📱 **小红书：** {str(cs.get('xiaohongshu',''))[:80]}\n\n"
            f">💬 **群推：** {str(cs.get('group_push',''))[:60]}\n\n"
            f">🔄 **转介绍：** {str(cs.get('referral',''))[:60]}"
        )
        blocks.append(f"## 📣 渠道策略\n{ch_lines}")

        # ── 风险 + 成功标准 ──
        risk_lines = "\n".join(
            f">⚠️ {r}" for r in plan.get("risk_alerts", [])[:3]
        )
        kpi_lines = "\n".join(
            f">✅ <font color=\"warning\">{m}</font>"
            for m in plan.get("success_metrics", [])[:3]
        )
        blocks.append(
            f"## ⚠️ 风险提示\n{risk_lines}\n\n"
            f"## ✅ 成功标准\n{kpi_lines}\n\n"
            f"<font color=\"comment\">📌 本计划基于历史数据自动生成，接入实时数据后更精准</font>"
        )

        return blocks

    # ─────────────────────────────────────────
    # 周计划格式化
    # ─────────────────────────────────────────
    def format_weekly_plan(self, plan: dict) -> list[str]:
        week   = plan.get("week", "本周")
        theme  = plan.get("week_theme", "")
        goal   = plan.get("week_goal", "")
        insight = plan.get("key_insight", "")

        blocks = []

        # ── 封面 ──
        blocks.append(
            f"# 📋 本周推广执行计划\n"
            f"## <font color=\"info\">{week}</font>\n\n"
            f">**主题：**{theme}\n"
            f">**目标：**<font color=\"warning\">{goal}</font>\n\n"
            f"💡 {insight}"
        )

        # ── 每日计划 ──
        daily = plan.get("daily_plan", [])
        if daily:
            day_lines = ""
            p_emoji = {"高": "🔴", "中": "🟡", "低": "🟢"}
            for d in daily:
                pe = p_emoji.get(d.get("priority","中"), "⚪")
                day_lines += (
                    f">{pe} **{d.get('date','')} {d.get('weekday','')}** — "
                    f"<font color=\"info\">{d.get('focus','')[:30]}</font>\n"
                    f">小红书：{d.get('xiaohongshu_topic','')[:40]}\n"
                    f">销售：{d.get('sales_action','')[:40]}\n\n"
                )
            blocks.append(f"## 📅 每日执行\n{day_lines.rstrip()}")

        # ── 分部门 ──
        tf = plan.get("team_focus", {})
        team_lines = (
            f">📚 **学管：** {tf.get('xueguan','')[:80]}\n\n"
            f">💼 **顾问：** {tf.get('consultant','')[:80]}\n\n"
            f">📱 **推广部：** {tf.get('operation','')[:80]}"
        )
        blocks.append(f"## 👥 分部门分工\n{team_lines}")

        # ── 转介绍 + 监控指标 ──
        referral = plan.get("referral_trigger_this_week", "")
        watch = plan.get("data_to_watch", [])
        watch_lines = "\n".join(f">📊 {d}" for d in watch[:3])
        blocks.append(
            f"## 🔄 转介绍触发点\n>{referral[:120]}\n\n"
            f"## 📈 本周监控数据\n{watch_lines}"
        )

        # ── 重点内容方向 ──
        highlight = plan.get("week_highlight_content", "")
        if highlight:
            blocks.append(
                f"## ✍️ 本周重点内容方向\n"
                f"<font color=\"comment\">（运营直接执行）</font>\n\n"
                f">{highlight[:200]}"
            )

        return blocks

    # ─────────────────────────────────────────
    # 每日素材格式化
    # ─────────────────────────────────────────
    def format_daily_content(self, post: dict, referral_kit: dict = None) -> list[str]:
        blocks = []

        # ── 小红书笔记 ──
        title  = post.get("title", "")
        cover  = post.get("cover_text", "")
        body   = post.get("body", "")
        tags   = " ".join([f"#{t}" for t in post.get("hashtags", [])[:8]])
        cta    = post.get("call_to_action", "")
        timing = post.get("post_timing", "")
        urgency = post.get("urgency", "")
        u_emoji = {"🔴紧急": "🔴", "🟡预热": "🟡", "🟢铺垫": "🟢"}.get(urgency, "📱")

        blocks.append(
            f"# {u_emoji} 今日小红书笔记\n\n"
            f">**标题：** <font color=\"warning\">{title}</font>\n"
            f">**封面文案：** {cover}\n"
            f">**建议发布：** <font color=\"info\">{timing}</font>"
        )
        blocks.append(
            f"## 📝 正文\n```\n{body[:500]}\n```"
        )
        blocks.append(
            f"## 🏷️ 标签\n<font color=\"comment\">{tags}</font>\n\n"
            f"## 📣 引导话术\n>{cta}"
        )

        # ── 转介绍话术（如果有） ──
        if referral_kit and not referral_kit.get("parse_error"):
            scripts = referral_kit.get("referral_scripts", {})
            short   = scripts.get("short_version", "")
            s2s     = scripts.get("student_to_student", "")
            group_msgs = referral_kit.get("group_messages", {})
            xueguan = group_msgs.get("xueguan_group", "")
            new_lead = group_msgs.get("new_lead_first_msg", "")

            if short or s2s:
                blocks.append(
                    f"## 💬 转介绍话术 — {referral_kit.get('product_name','')}\n\n"
                    f">**30字简版（直接转发）：**\n>{short}\n\n"
                    f">**学生互推版：**\n>{s2s[:120]}"
                )
            if xueguan or new_lead:
                blocks.append(
                    f"## 📢 群发消息\n\n"
                    f">**学管群：**\n>{xueguan[:120]}\n\n"
                    f">**新咨询首条：**\n>{new_lead[:100]}"
                )

        return blocks

    # ─────────────────────────────────────────
    # 摘要通知（控制台模式）
    # 企业微信只推摘要+跳转链接，完整内容在控制台查看
    # ─────────────────────────────────────────
    def format_notify_summary(
        self,
        event_type: str,
        summary: str,
        details: list[str] = None,
        console_url: str = "http://localhost:8501",
    ) -> str:
        """
        生成简洁通知消息，引导用户去控制台查看完整内容
        event_type: 'monthly_plan' | 'weekly_plan' | 'content_ready' | 'review_needed' | 'task_reminder'
        """
        event_icons = {
            "monthly_plan":    "📅",
            "weekly_plan":     "📋",
            "content_ready":   "✅",
            "review_needed":   "👀",
            "task_reminder":   "⏰",
        }
        icon = event_icons.get(event_type, "📢")

        lines = [f"# {icon} {summary}\n"]
        if details:
            for d in details[:4]:
                lines.append(f"> {d}")
        lines.append(f"\n[**→ 打开营销控制台查看详情**]({console_url})")
        lines.append(f"\n<font color=\"comment\">🤖 自动生成 · {__import__('datetime').datetime.now().strftime('%m/%d %H:%M')}</font>")
        return "\n".join(lines)

    def notify_content_generated(self, content_type: str, count: int, pending_review: int = 0) -> bool:
        """内容生成后推送通知"""
        type_name = {
            "monthly_plan": "月度营销战略计划",
            "weekly_plan":  "本周执行计划",
            "xiaohongshu":  "小红书笔记",
            "referral_script": "转介绍素材包",
        }.get(content_type, content_type)

        msg = self.format_notify_summary(
            event_type = "content_ready" if pending_review == 0 else "review_needed",
            summary    = f"{type_name}已生成，共 {count} 条",
            details    = [
                f"待审核内容：{pending_review} 条" if pending_review else "内容已自动通过，可直接使用",
                "点击链接在控制台查看、复制和分发",
            ],
        )
        return self.send_one(msg)

    # ─────────────────────────────────────────
    # 通用推送：任意文本美化
    # ─────────────────────────────────────────
    def format_simple_report(self, title: str, sections: list[dict]) -> str:
        """
        sections: [{"emoji":"📊","label":"标题","content":"内容","color":"info/warning/comment"}]
        """
        lines = [f"# {title}\n"]
        for s in sections:
            color = s.get("color", "")
            content = s.get("content", "")
            if color:
                content = f'<font color="{color}">{content}</font>'
            lines.append(f"## {s.get('emoji','')} {s.get('label','')}\n>{content}\n")
        return "\n".join(lines)
