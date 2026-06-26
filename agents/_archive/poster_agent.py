"""
PosterAgent — AI设计海报文案 + Pillow渲染成图片
支持：小红书封面图、促销海报、转介绍活动海报、朋友圈配图
"""
import json
import textwrap
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic

import subprocess
import tempfile


# ── 字体路径（Mac系统字体）──
FONT_PATHS = {
    "bold":    "/System/Library/Fonts/STHeiti Medium.ttc",
    "regular": "/System/Library/Fonts/PingFang.ttc",
    "fallback": "/System/Library/Fonts/Geneva.ttf",
}

# ── 品牌配色方案 ──
COLOR_THEMES = {
    "urgent": {       # 🔴 紧急/期末冲刺 — 深红橙
        "bg":       "#1A0A00",
        "accent":   "#FF4500",
        "accent2":  "#FF8C00",
        "text":     "#FFFFFF",
        "subtext":  "#FFD700",
        "tag_bg":   "#FF4500",
        "tag_text": "#FFFFFF",
    },
    "warm": {         # 🟡 学年包/温暖转化
        "bg":       "#0F0A1E",
        "accent":   "#7B2FBE",
        "accent2":  "#FF6B9D",
        "text":     "#FFFFFF",
        "subtext":  "#E0B3FF",
        "tag_bg":   "#7B2FBE",
        "tag_text": "#FFFFFF",
    },
    "fresh": {        # 🟢 开学季/新生
        "bg":       "#001A2C",
        "accent":   "#00C9A7",
        "accent2":  "#00A3FF",
        "text":     "#FFFFFF",
        "subtext":  "#A0E8D8",
        "tag_bg":   "#00C9A7",
        "tag_text": "#001A2C",
    },
    "professional": { # ⚪ 对公/机构合作
        "bg":       "#0D1117",
        "accent":   "#2563EB",
        "accent2":  "#60A5FA",
        "text":     "#FFFFFF",
        "subtext":  "#94A3B8",
        "tag_bg":   "#2563EB",
        "tag_text": "#FFFFFF",
    },
}

SYSTEM_PROMPT = """你是一个专业的留学教育营销设计师，擅长创作吸引眼球的海报文案。
你的任务是为给定的营销场景设计海报内容结构。

海报文案原则：
- 标题：最多15字，直击痛点或利益点，可含emoji
- 副标题：补充信息，20字内
- 正文要点：3-4条，每条≤20字，用符号开头（✅❌🎯⚡等）
- 底部行动号召：10字内，强引导（如"立即咨询" "扫码了解"）
- 标签：2-3个，每个4-8字
- 整体风格要有冲击力，不要中庸"""


class PosterAgent:
    def __init__(self, client: Anthropic, config: dict):
        self.client = client
        self.config = config
        self.model = config["anthropic"]["model"]
        self.output_dir = Path(config["output"]["base_dir"]) / "posters"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────
    # 主入口：生成海报
    # ─────────────────────────────────────────
    def generate_poster(
        self,
        topic: str,
        product_id: str = "regular",
        poster_type: str = "xiaohongshu",  # xiaohongshu / promo / moments
        theme: str = "auto",
        school: str = None,
    ) -> str:
        """生成一张海报，返回图片路径"""
        # 1. AI设计文案
        design = self._design_copy(topic, product_id, poster_type, school)

        # 2. 选配色
        if theme == "auto":
            theme = self._auto_theme(product_id, topic)

        # 3. 渲染图片
        size = self._poster_size(poster_type)
        img_path = self._render_poster(design, theme, size, poster_type)

        return img_path

    def generate_series(self, product_id: str, count: int = 3) -> list[str]:
        """为某产品生成系列海报"""
        product = next((p for p in self.config["products"] if p["id"] == product_id), {})
        topics = [
            f"{product.get('name','')}真实学员成绩变化",
            f"为什么{product.get('name','')}能帮你稳住GPA",
            f"{product.get('name','')}限时早鸟价",
        ]
        paths = []
        for topic in topics[:count]:
            path = self.generate_poster(topic, product_id, poster_type="xiaohongshu")
            paths.append(path)
        return paths

    # ─────────────────────────────────────────
    # AI文案设计
    # ─────────────────────────────────────────
    def _design_copy(self, topic, product_id, poster_type, school):
        product = next((p for p in self.config["products"] if p["id"] == product_id), {})
        school_str = f"目标学校：{school}" if school else ""

        size_desc = {
            "xiaohongshu": "小红书封面（正方形，文字要大，视觉冲击强）",
            "promo":        "促销海报（竖版，信息丰富）",
            "moments":      "朋友圈配图（正方形，简洁有力）",
        }.get(poster_type, "营销海报")

        prompt = f"""
为以下场景设计海报文案：
- 主题：{topic}
- 产品：{product.get('name','')} — {product.get('description','')}
- 核心卖点：{', '.join(product.get('selling_points', [])[:3])}
- 目标客群：{product.get('target','')}
- 海报类型：{size_desc}
{school_str}

输出JSON（严格格式，不要markdown代码块）：
{{
  "headline": "主标题（10字内，含emoji，最吸引眼球）",
  "subheadline": "副标题（15字内，补充价值点）",
  "badge": "角标文字（4字内，如：限时/紧急/热门）",
  "points": [
    "✅ 卖点1（≤18字）",
    "⚡ 卖点2（≤18字）",
    "🎯 卖点3（≤18字）"
  ],
  "cta": "行动号召（6字内，如：立即咨询）",
  "tags": ["标签1", "标签2"],
  "color_hint": "urgent/warm/fresh/professional（根据内容情绪选择）"
}}
"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # 清理可能的 markdown
        if "```" in raw:
            raw = raw.split("```")[1] if "```json" not in raw else raw.split("```json")[1]
            raw = raw.split("```")[0]
        try:
            return json.loads(raw.strip())
        except Exception:
            # fallback 默认文案
            return {
                "headline": f"🎯 {topic[:10]}",
                "subheadline": product.get("description", "")[:20],
                "badge": "热门",
                "points": [f"✅ {sp[:18]}" for sp in product.get("selling_points", ["专业辅导"])[:3]],
                "cta": "立即咨询",
                "tags": [product.get("name", "辅导"), "留学"],
                "color_hint": "warm",
            }

    # ─────────────────────────────────────────
    # 图片渲染（HTML → Puppeteer → PNG）
    # ─────────────────────────────────────────
    def _render_poster(self, design: dict, theme: str, size: tuple, poster_type: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        design["color_hint"] = theme

        # 写临时 design JSON
        design_path = self.output_dir / f"_design_{ts}.json"
        design_path.write_text(json.dumps(design, ensure_ascii=False))

        out_path = self.output_dir / f"poster_{ts}_{theme}.png"
        render_js = Path(__file__).parent.parent / "poster_render.js"

        result = subprocess.run(
            ["node", str(render_js), str(design_path), str(out_path)],
            capture_output=True, text=True, timeout=90
        )
        design_path.unlink(missing_ok=True)  # 清理临时文件

        if result.returncode != 0:
            raise RuntimeError(f"渲染失败：{result.stderr}")

        return str(out_path)

    def _poster_size(self, poster_type: str) -> tuple:
        return {
            "xiaohongshu": (1080, 1440),
            "promo":        (750, 1334),
            "moments":      (900, 900),
        }.get(poster_type, (1080, 1440))

    def _auto_theme(self, product_id: str, topic: str) -> str:
        urgent_keywords = ["期末", "冲刺", "救急", "紧急", "补考", "挂科", "倒计时"]
        warm_keywords   = ["学年包", "全年", "保障", "包过", "稳定"]
        fresh_keywords  = ["开学", "新生", "规划", "暑期", "入学"]
        pro_keywords    = ["对公", "机构", "合作", "B2B"]
        text = topic + product_id
        if any(k in text for k in urgent_keywords): return "urgent"
        if any(k in text for k in pro_keywords):    return "professional"
        if any(k in text for k in fresh_keywords):  return "fresh"
        return "warm"
