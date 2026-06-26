"""
ProductLaunchAgent — 新产品推广内容生成
输入：产品信息 + 目标学校/国家/时间窗口
输出：推广活动记录 + 全套内容（小红书/朋友圈/社群/销售话术/转介绍脚本）
"""
import json
import logging
from datetime import datetime
import anthropic
from database import save_campaign, save_content, save_task

logger = logging.getLogger(__name__)


class ProductLaunchAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model  = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    def launch(self, product_info: dict) -> dict:
        """
        product_info 结构：
        {
          "product_id": "guaranteed",       # 产品ID
          "product_name": "包过辅导",        # 产品名
          "campaign_name": "UCL期末冲刺包",  # 推广活动名
          "target_schools": ["UCL","LSE"],   # 目标学校
          "target_country": "UK",            # 目标国家
          "period_start": "2026-06-10",      # 推广开始
          "period_end": "2026-06-30",        # 推广结束
          "core_theme": "考前30天保分冲刺",   # 核心主题
          "core_selling_point": "...",       # 核心卖点
          "price_info": "¥6500起",           # 价格信息
          "special_offer": "前10名立减500",  # 限时优惠
          "target_user": "UCL期末挂科风险学生"
        }
        返回：{"campaign_id": N, "contents_saved": N, "tasks_saved": N}
        """
        product_name   = product_info.get("product_name", "")
        campaign_name  = product_info.get("campaign_name", f"{product_name}推广活动")
        target_schools = product_info.get("target_schools", [])
        target_country = product_info.get("target_country", "UK")
        core_theme     = product_info.get("core_theme", "")
        core_selling   = product_info.get("core_selling_point", "")
        price_info     = product_info.get("price_info", "")
        special_offer  = product_info.get("special_offer", "")
        target_user    = product_info.get("target_user", "")
        schools_str    = "、".join(target_schools) if target_schools else target_country

        prompt = f"""你是极致教育留学辅导机构的营销文案专家。
现在需要为以下产品生成一套完整的推广内容包：

**产品**：{product_name}
**推广活动**：{campaign_name}
**目标学校**：{schools_str}
**核心主题**：{core_theme}
**核心卖点**：{core_selling}
**价格信息**：{price_info}
**限时优惠**：{special_offer}
**目标用户**：{target_user}

请生成以下5种内容（输出 JSON 数组，每种1条）：

1. xiaohongshu（小红书）：标题15字内+emoji，正文300字以内，真实有温度，带痛点+解决方案+案例，10个精准标签
2. moments（朋友圈文案）：150字以内，自然真实，带行动号召
3. group_msg（社群群发消息）：80字以内，直接，带限时优惠信息
4. sales_script（销售私信话术）：200字以内，针对已咨询但未成交的学生，强调核心卖点和紧迫感
5. referral_script（转介绍话术）：150字以内，让老学员帮推荐，语气自然不突兀

输出格式：
[
  {{
    "content_type": "xiaohongshu",
    "title": "...",
    "body": "...",
    "cover_text": "封面文字（15字内）",
    "hashtags": ["#标签1"],
    "call_to_action": "私信或扣1",
    "channel": "xiaohongshu",
    "target_country": "{target_country}",
    "suggested_use": "建议发布时间"
  }},
  ...
]
只输出 JSON，不要其他说明。"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=[{
                    "type": "text",
                    "text": "你是极致教育留学辅导机构的营销文案专家，专注英国和澳洲留学辅导。生成内容需真实合规，有吸引力。只输出JSON。",
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
            contents = json.loads(raw)

        except Exception as e:
            logger.error(f"ProductLaunchAgent LLM error: {e}")
            contents = []

        # 保存推广活动
        from datetime import datetime as _dt
        campaign_id = save_campaign({
            "name":           campaign_name,
            "campaign_type":  "product_launch",
            "core_theme":     core_theme,
            "core_goal":      f"推广{product_name}，目标学校：{schools_str}",
            "target_country": target_country,
            "status":         "active",
            "period_start":   product_info.get("period_start"),
            "period_end":     product_info.get("period_end"),
            "plan_data":      product_info,
        })

        # 保存内容
        saved_contents = 0
        for c in contents:
            c["product_id"]   = product_info.get("product_id", "")
            c["campaign_id"]  = campaign_id
            c["status"]       = "draft"
            c["market_period"]= f"product_launch_{product_info.get('product_id','')}"
            c["target_user"]  = target_user
            # 确保 title 不为空
            if not c.get("title"):
                ctype_names = {"xiaohongshu":"小红书","moments":"朋友圈",
                               "group_msg":"社群消息","sales_script":"销售话术",
                               "referral_script":"转介绍话术"}
                c["title"] = f"{campaign_name}·{ctype_names.get(c.get('content_type',''),c.get('content_type',''))}"
            school_label = target_schools[0] if target_schools else schools_str
            c["school_name"] = school_label
            try:
                save_content(c)
                saved_contents += 1
            except Exception as e:
                logger.warning(f"save_content error: {e}")

        # 自动生成推广任务
        tasks = [
            {
                "title": f"【推广部】发布{campaign_name}小红书内容",
                "description": f"审核并发布{campaign_name}相关小红书/朋友圈内容，内容已在系统生成，请进入内容池审核后发布",
                "task_type": "内容发布",
                "department": "推广部",
                "priority": "高",
                "task_source": "AI生成",
                "related_product": product_info.get("product_id",""),
                "expected_output": "小红书发布截图 + 朋友圈发布截图",
            },
            {
                "title": f"【顾问】跟进{campaign_name}意向客户",
                "description": f"使用系统生成的销售话术，主动联系{schools_str}中近期有咨询但未成交的学生，话术在系统「销售作战台」可查",
                "task_type": "销售跟进",
                "department": "顾问",
                "priority": "高",
                "task_source": "AI生成",
                "related_product": product_info.get("product_id",""),
                "expected_output": f"联系10名意向客户，记录跟进结果",
            },
        ]
        saved_tasks = 0
        for t in tasks:
            try:
                save_task(t)
                saved_tasks += 1
            except Exception:
                pass

        logger.info(f"ProductLaunchAgent: campaign_id={campaign_id}, contents={saved_contents}, tasks={saved_tasks}")
        return {
            "campaign_id": campaign_id,
            "contents_saved": saved_contents,
            "tasks_saved": saved_tasks,
            "contents": contents,
        }
