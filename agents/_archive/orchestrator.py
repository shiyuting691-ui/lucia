"""
OrchestratorAgent — 调度协调所有Agent，输出结构化文件
"""
import json
import os
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

from .exam_calendar_agent import ExamCalendarAgent
from .content_generation_agent import ContentGenerationAgent
from .referral_material_agent import ReferralMaterialAgent


class OrchestratorAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = Anthropic()  # 读取 ANTHROPIC_API_KEY 环境变量
        self.base_output = Path(config["output"]["base_dir"])
        self.base_output.mkdir(parents=True, exist_ok=True)

        self.calendar_agent = ExamCalendarAgent(self.client, config)
        self.content_agent = ContentGenerationAgent(self.client, config)
        self.referral_agent = ReferralMaterialAgent(self.client, config)

    def run_daily(self):
        """每日任务：生成当天需要的内容"""
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"\n{'='*50}")
        print(f"📅 每日内容生产任务 — {today}")
        print(f"{'='*50}")

        # 1. 生成/更新内容日历（每周一刷新，其他日期检查是否存在）
        calendar = self._get_or_refresh_calendar()

        # 2. 找到今天或最近的内容节点，生成小红书帖子
        today_nodes = self._find_nodes_for_today(calendar)
        if today_nodes:
            print(f"\n🎯 找到 {len(today_nodes)} 个今日内容节点")
            posts = []
            for node in today_nodes[:3]:  # 每天最多3篇
                print(f"  ✍️  生成笔记：{node.get('theme', '')}")
                post = self.content_agent._generate_single_post(node, calendar.get("calendar_summary", ""))
                posts.append(post)
            self._save_xiaohongshu_posts(posts, today)
            print(f"  ✅ 已生成 {len(posts)} 篇小红书笔记")
        else:
            print("  ℹ️  今日无特定内容节点，生成通用日常内容")
            posts = self.content_agent.generate_batch_by_product("regular", count=2)
            self._save_xiaohongshu_posts(posts, today)

        print(f"\n✅ 每日任务完成，输出目录：{self.base_output}/xiaohongshu/{today}/")
        return {"date": today, "posts_generated": len(posts)}

    def run_weekly(self):
        """每周任务：刷新日历 + 生成全套转介绍素材"""
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"\n{'='*50}")
        print(f"📆 每周全量任务 — {today}")
        print(f"{'='*50}")

        # 1. 刷新日历
        print("\n🗓️  刷新30天内容日历...")
        calendar = self._refresh_calendar()

        # 2. 批量生成所有产品的转介绍素材
        print("\n📦 生成转介绍素材包...")
        referral_results = {}
        for product in self.config["products"]:
            if product["id"] == "b2b":
                continue
            print(f"  🔧 {product['name']} 素材包生成中...")
            kit = self.referral_agent.generate_referral_kit(
                product_id=product["id"],
                country=None,
            )
            referral_results[product["id"]] = kit
        self._save_referral_kits(referral_results, today)
        print(f"  ✅ 已生成 {len(referral_results)} 套转介绍素材")

        # 3. 英澳各生成一套季节性活动素材
        print("\n🌍 生成季节性活动素材...")
        current_month = datetime.now().month
        season = self._detect_season(current_month)
        for country in ["英国", "澳洲"]:
            print(f"  🎯 {country} {season} 素材...")
            campaign = self.referral_agent.generate_seasonal_campaign(season, country)
            self._save_campaign(campaign, today, country)
        print(f"  ✅ 季节性活动素材完成")

        # 4. 批量生成学年包专项内容（本周重点）
        print("\n💎 生成学年包专项推广内容...")
        annual_posts = self.content_agent.generate_batch_by_product("annual_package", count=5)
        self._save_xiaohongshu_posts(annual_posts, today, subfolder="annual_package_focus")

        summary = {
            "date": today,
            "calendar_nodes": len(calendar.get("key_nodes", [])),
            "referral_kits": len(referral_results),
            "seasonal_campaigns": 2,
            "annual_package_posts": len(annual_posts),
        }
        self._save_weekly_summary(summary, today)

        print(f"\n✅ 每周任务完成！详情见 {self.base_output}/")
        return summary

    def run_full_init(self):
        """首次初始化：生成所有基础素材"""
        print("\n🚀 首次初始化：生成全套基础素材")
        results = {}

        # 日历
        print("\n1/4 生成内容日历...")
        results["calendar"] = self._refresh_calendar()

        # 所有产品的转介绍包
        print("\n2/4 生成全产品转介绍素材包...")
        results["referral_kits"] = {}
        for product in self.config["products"]:
            kit = self.referral_agent.generate_referral_kit(product["id"])
            results["referral_kits"][product["id"]] = kit
            print(f"  ✅ {product['name']}")

        # 英澳两个地区的素材
        print("\n3/4 生成分地区内容...")
        results["campaigns"] = {}
        for country in ["英国", "澳洲"]:
            season = self._detect_season(datetime.now().month)
            campaign = self.referral_agent.generate_seasonal_campaign(season, country)
            results["campaigns"][country] = campaign
            print(f"  ✅ {country} {season}")

        # 小红书首批内容
        print("\n4/4 生成首批小红书内容...")
        calendar = results["calendar"]
        posts = self.content_agent.generate_posts_from_calendar(calendar, max_posts=7)
        today = datetime.now().strftime("%Y-%m-%d")
        self._save_xiaohongshu_posts(posts, today, subfolder="initial_batch")
        results["initial_posts_count"] = len(posts)

        print(f"\n🎉 初始化完成！所有素材已保存至 {self.base_output}/")
        return results

    # ──────────────────────────────────────────────
    # 内部工具方法
    # ──────────────────────────────────────────────

    def _get_or_refresh_calendar(self) -> dict:
        calendar_path = self.base_output / "content_calendar" / "latest.json"
        if calendar_path.exists():
            with open(calendar_path, "r", encoding="utf-8") as f:
                cal = json.load(f)
            # 如果日历是今天或最近7天内生成的，直接复用
            generated_at = cal.get("generated_at", "")
            if generated_at:
                gen_date = datetime.fromisoformat(generated_at)
                if (datetime.now() - gen_date).days < 7:
                    return cal
        return self._refresh_calendar()

    def _refresh_calendar(self) -> dict:
        calendar = self.calendar_agent.generate_calendar(days=30)
        cal_dir = self.base_output / "content_calendar"
        cal_dir.mkdir(parents=True, exist_ok=True)
        with open(cal_dir / "latest.json", "w", encoding="utf-8") as f:
            json.dump(calendar, f, ensure_ascii=False, indent=2)
        dated_file = cal_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(dated_file, "w", encoding="utf-8") as f:
            json.dump(calendar, f, ensure_ascii=False, indent=2)
        print(f"  💾 日历已保存：{dated_file}")
        return calendar

    def _find_nodes_for_today(self, calendar: dict) -> list:
        today_str = datetime.now().strftime("%Y-%m-%d")
        nodes = calendar.get("key_nodes", [])
        today_nodes = [n for n in nodes if n.get("date", "").startswith(today_str[:7])]
        if not today_nodes:
            today_nodes = nodes[:2]
        return today_nodes

    def _save_xiaohongshu_posts(self, posts: list, date: str, subfolder: str = None):
        folder_name = subfolder or date
        out_dir = self.base_output / "xiaohongshu" / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # 保存整合JSON
        with open(out_dir / "all_posts.json", "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)

        # 每篇单独保存为易读txt
        for i, post in enumerate(posts, 1):
            txt_path = out_dir / f"post_{i:02d}_{post.get('product_id', 'general')}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"【标题】{post.get('title', '')}\n\n")
                f.write(f"【封面文案】{post.get('cover_text', '')}\n\n")
                f.write(f"【正文】\n{post.get('body', '')}\n\n")
                f.write(f"【标签】{' '.join(['#' + t for t in post.get('hashtags', [])])}\n\n")
                f.write(f"【引导话术】{post.get('call_to_action', '')}\n")
                f.write(f"【建议发布时间】{post.get('post_timing', '')}\n")

    def _save_referral_kits(self, kits: dict, date: str):
        out_dir = self.base_output / "referral_scripts" / date
        out_dir.mkdir(parents=True, exist_ok=True)

        with open(out_dir / "all_kits.json", "w", encoding="utf-8") as f:
            json.dump(kits, f, ensure_ascii=False, indent=2)

        for product_id, kit in kits.items():
            txt_path = out_dir / f"{product_id}_referral_kit.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"# {kit.get('product_name', product_id)} 转介绍素材包\n\n")
                scripts = kit.get("referral_scripts", {})
                f.write("## 转介绍话术\n")
                for k, v in scripts.items():
                    f.write(f"\n【{k}】\n{v}\n")

                moments = kit.get("wechat_moments", [])
                f.write("\n\n## 朋友圈文案\n")
                for m in moments:
                    f.write(f"\n【{m.get('style', '')}】\n{m.get('content', '')}\n")

                group_msgs = kit.get("group_messages", {})
                f.write("\n\n## 群发消息\n")
                for k, v in group_msgs.items():
                    f.write(f"\n【{k}】\n{v}\n")

    def _save_campaign(self, campaign: dict, date: str, country: str):
        out_dir = self.base_output / "wechat_content" / date
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{country}_{campaign.get('season', '')}_campaign.json"
        with open(out_dir / fname, "w", encoding="utf-8") as f:
            json.dump(campaign, f, ensure_ascii=False, indent=2)

    def _save_weekly_summary(self, summary: dict, date: str):
        out_dir = self.base_output / "summaries"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"weekly_{date}.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def _detect_season(self, month: int) -> str:
        if month in [8, 9]:
            return "开学季"
        elif month in [11, 12]:
            return "期末冲刺季"
        elif month in [1, 2]:
            return "新年冲刺季"
        elif month in [4, 5, 6]:
            return "毕业季/论文季"
        else:
            return "暑期规划季"
