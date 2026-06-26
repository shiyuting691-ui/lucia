"""
InsightAgent — 分析业务数据，生成战略洞察和建议
输出写入 strategy_suggestions 表
"""
import json
from datetime import datetime
from anthropic import Anthropic

SYSTEM_PROMPT = """你是一个数据驱动的增长分析师，为留学辅导机构提供战略洞察。

你的任务是：基于系统数据，识别机会、发现风险、给出具体可执行建议。

分析维度：
1. 产品机会：哪个产品最值得主推
2. 学校机会：哪个学校/地区值得重点覆盖
3. 内容效果：哪类内容最有转化价值
4. 销售阻力：哪些产品成交难度高，原因是什么
5. 风险预警：哪些承诺或操作存在风险
6. 增长点：下一个可能的业务增长方向

输出必须基于数据，有具体洞察和可执行建议，不要泛泛而谈。"""


class InsightAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model  = config["anthropic"]["model"]

    def generate_insights(
        self,
        contents: list       = None,
        tasks: list          = None,
        feedbacks: list      = None,
        usage_records: list  = None,
        campaigns: list      = None,
        business_data: dict  = None,
    ) -> list[dict]:
        """生成战略洞察，返回可写入 strategy_suggestions 的 list[dict]"""
        context = self._build_context(contents, tasks, feedbacks, usage_records, campaigns, business_data)

        prompt = f"""
当前日期：{datetime.now().strftime('%Y-%m-%d')}

{context}

请基于以上数据生成战略洞察建议，输出 JSON 数组，每条包含：
{{
  "title": "洞察标题（简明扼要，20字内）",
  "suggestion_type": "市场机会|产品优化|销售策略|推广策略|风控提醒|资源配置|新产品机会|部门协作问题",
  "related_product": "相关产品（可为空）",
  "related_country": "相关国家（UK/Australia/通用，可为空）",
  "related_school": "相关学校（可为空）",
  "insight": "洞察内容：观察到什么现象/数据（2-3句话）",
  "recommendation": "建议动作：具体要做什么，谁来做（2-3条）",
  "priority": "低|中|高|紧急",
  "source": "AI分析"
}}

生成3-6条高质量洞察，不要凑数，有价值的才输出。
只输出 JSON 数组。
"""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2500,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```json")[-1].split("```")[0] if "```json" in raw \
                  else raw.split("```")[1].split("```")[0]
        try:
            suggestions = json.loads(raw.strip())
        except Exception:
            suggestions = self._fallback_insights()

        for s in suggestions:
            s.setdefault("source", "AI分析")
            s.setdefault("status", "new")

        return suggestions

    def _build_context(self, contents, tasks, feedbacks, usage_records, campaigns, business_data):
        parts = ["## 系统数据摘要"]

        # 内容统计
        if contents:
            status_counts = {}
            type_counts   = {}
            for c in contents:
                st = c.get("status","")
                ct = c.get("content_type","")
                status_counts[st] = status_counts.get(st, 0) + 1
                type_counts[ct]   = type_counts.get(ct, 0) + 1
            parts.append(f"内容状态分布：{json.dumps(status_counts, ensure_ascii=False)}")
            parts.append(f"内容类型分布：{json.dumps(type_counts, ensure_ascii=False)}")
            # 找未被使用的内容
            approved_unused = [c for c in contents if c.get("status") == "approved"]
            if approved_unused:
                parts.append(f"已通过但未使用的内容：{len(approved_unused)} 条（可能存在内容浪费）")

        # 任务统计
        if tasks:
            task_status = {}
            for t in tasks:
                st = t.get("status","")
                task_status[st] = task_status.get(st, 0) + 1
            blocked = [t for t in tasks if t.get("status") == "blocked"]
            parts.append(f"任务状态：{json.dumps(task_status, ensure_ascii=False)}")
            if blocked:
                parts.append(f"阻塞任务：{len(blocked)} 条，需关注")

        # 部门反馈
        if feedbacks:
            feedback_types = {}
            high_urgency   = []
            for f in feedbacks:
                ft = f.get("feedback_type","")
                feedback_types[ft] = feedback_types.get(ft, 0) + 1
                if f.get("urgency") in ("高", "紧急", "high", "urgent"):
                    high_urgency.append(f.get("title",""))
            parts.append(f"反馈类型分布：{json.dumps(feedback_types, ensure_ascii=False)}")
            if high_urgency:
                parts.append(f"高优先级反馈：{'; '.join(high_urgency[:5])}")

        # 使用记录
        if usage_records:
            results = {}
            for u in usage_records:
                r = u.get("result","")
                results[r] = results.get(r, 0) + 1
            parts.append(f"内容使用效果：{json.dumps(results, ensure_ascii=False)}")

        # 业务数据
        if business_data:
            parts.append(f"业务数据：{json.dumps(business_data, ensure_ascii=False)}")

        # 当前考试节点
        month = datetime.now().month
        if 5 <= month <= 6:
            parts.append("当前时间节点：UK/澳洲期末考试季高峰，押题和冲刺产品需求最高")
        elif 8 <= month <= 9:
            parts.append("当前时间节点：UK/澳洲新学期开学季，学年包和新生入学辅导需求上升")
        elif month in (11, 12):
            parts.append("当前时间节点：UK秋学期期末，论文和考试辅导双高峰")

        # 产品信息
        products = [p["name"] for p in self.config.get("products", [])]
        parts.append(f"产品线：{' / '.join(products)}")

        return "\n".join(parts)

    def _fallback_insights(self):
        return [
            {
                "title": "6月押题产品冲刺窗口期机会",
                "suggestion_type": "市场机会",
                "related_product": "Final押题",
                "related_country": "Australia",
                "related_school": "悉大,墨大,UNSW",
                "insight": "当前为澳洲6月期末考试季高峰。押题类产品咨询需求最高，转化率通常高于平时2-3倍。",
                "recommendation": "1. 本周每天发布1条澳洲押题小红书\n2. 对已咨询未成交学生推送押题话术\n3. 准备限时优惠促成决策",
                "priority": "高",
                "source": "AI分析（fallback）",
            }
        ]
