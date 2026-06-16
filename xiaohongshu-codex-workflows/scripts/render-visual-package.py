#!/usr/bin/env python3
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path.cwd()
VISUAL_JSON = ROOT / "outputs" / "visual-package.json"
OUT_DIR = ROOT / "outputs" / "visual-images"
MANIFEST = OUT_DIR / "manifest.json"

WIDTH = 1080
HEIGHT = 1440

FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]


def font(size, bold=False):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=1 if bold else 0)
    return ImageFont.load_default()


F_TITLE = font(92, True)
F_SUBTITLE = font(56, True)
F_BODY = font(42)
F_SMALL = font(30)
F_TINY = font(24)
F_CHAT = font(34)


def wrap_text(text, max_chars):
    text = str(text).replace("\n", " ").strip()
    if not text:
        return []
    parts = re.split(r"(\s+)", text)
    if len(parts) > 1:
        lines, current = [], ""
        for part in parts:
            if len(current + part) > max_chars:
                if current.strip():
                    lines.append(current.strip())
                current = part
            else:
                current += part
        if current.strip():
            lines.append(current.strip())
        return lines
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def draw_multiline(draw, xy, text, font_obj, fill, max_chars, line_gap=12):
    x, y = xy
    for line in wrap_text(text, max_chars):
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += font_obj.size + line_gap
    return y


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def save(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


def make_contact_sheet(files, out_path, title):
    thumbs = []
    for item in files:
        path = Path(item["path"])
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        img.thumbnail((260, 347))
        frame = Image.new("RGB", (300, 430), "#f7f3ea")
        x = (300 - img.width) // 2
        frame.paste(img, (x, 18))
        draw = ImageDraw.Draw(frame)
        label = item.get("kind") or item.get("type") or path.stem
        draw.text((18, 374), label[:16], font=F_TINY, fill="#3f362d")
        thumbs.append(frame)

    if not thumbs:
        return None

    cols = min(3, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 320 + 40, rows * 460 + 120), "#eee5d7")
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 32), title, font=F_BODY, fill="#2b2520")

    for idx, thumb in enumerate(thumbs):
        col = idx % cols
        row = idx // cols
        sheet.paste(thumb, (30 + col * 320, 100 + row * 460))

    save(sheet, out_path)
    return str(out_path)


def quality_checks(files):
    checks = []
    for item in files:
        path = Path(item["path"])
        if not path.exists():
            checks.append({**item, "ok": False, "issue": "missing"})
            continue
        img = Image.open(path)
        ok = img.size == (WIDTH, HEIGHT)
        checks.append({
            **item,
            "ok": ok,
            "size": list(img.size),
            "issue": "" if ok else "unexpected_size"
        })
    return checks


def base(role):
    if role == "student":
        img = Image.new("RGB", (WIDTH, HEIGHT), "#f7f2e8")
        draw = ImageDraw.Draw(img)
        for x in range(0, WIDTH, 48):
            draw.line((x, 0, x, HEIGHT), fill="#efe7d8", width=1)
        for y in range(0, HEIGHT, 48):
            draw.line((0, y, WIDTH, y), fill="#efe7d8", width=1)
        return img
    if role == "ip":
        img = Image.new("RGB", (WIDTH, HEIGHT), "#f4ead8")
        draw = ImageDraw.Draw(img)
        for i in range(26):
            y = 90 + i * 48
            draw.line((90, y, WIDTH - 90, y), fill="#ead9bd", width=1)
        return img
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f6f4ec")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, 180), fill="#162338")
    return img


def draw_tag(draw, text, xy, fill="#fff4bd", text_fill="#44351e"):
    x, y = xy
    w = max(220, len(text) * 30 + 44)
    rounded(draw, (x, y, x + w, y + 62), 22, fill)
    draw.text((x + 22, y + 14), text, font=F_SMALL, fill=text_fill)


def student_desk_slide():
    img = Image.new("RGB", (WIDTH, HEIGHT), "#d7c5aa")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#d5c1a2")
    draw.rounded_rectangle((78, 115, WIDTH - 78, 520), radius=36, fill="#2a2a2d")
    draw.rounded_rectangle((112, 155, WIDTH - 112, 485), radius=18, fill="#f7f6ef")
    draw.text((142, 188), "final revision mess", font=F_SMALL, fill="#8b8579")
    draw.text((142, 250), "week 7 还没看完", font=F_SUBTITLE, fill="#28231f")
    draw.text((142, 335), "reference 到底要不要背", font=F_BODY, fill="#443c34")
    draw.rounded_rectangle((115, 610, 520, 1040), radius=12, fill="#fff8e8")
    for i in range(8):
        y = 670 + i * 42
        draw.line((150, y, 480, y), fill="#ded0b5", width=2)
    draw.text((150, 635), "to do", font=F_BODY, fill="#7b5b2a")
    for i, item in enumerate(["lecture 8", "past paper", "rubric??"]):
        draw.text((155, 720 + i * 82), f"□ {item}", font=F_BODY, fill="#3b3329")
    draw.rounded_rectangle((610, 650, 930, 820), radius=18, fill="#ffe8a3")
    draw.text((642, 693), "DDL越看越近", font=F_BODY, fill="#5d4211")
    draw.rounded_rectangle((590, 890, 970, 1070), radius=18, fill="#f4f4f4")
    draw.text((625, 935), "范围太散了", font=F_BODY, fill="#333333")
    draw.rectangle((0, 1225, WIDTH, HEIGHT), fill="#1f1f1f")
    for i in range(13):
        x = 36 + i * 78
        draw.rounded_rectangle((x, 1265, x + 56, 1322), radius=10, fill="#343434")
    draw.text((85, 1135), "不是没学，是不知道先救哪里", font=F_BODY, fill="#fffaf0")
    return img


def student_countdown_slide():
    img = base("student")
    draw = ImageDraw.Draw(img)
    draw.text((86, 110), "DDL 倒计时", font=F_SUBTITLE, fill="#2b2520")
    draw.rounded_rectangle((115, 250, WIDTH - 115, 530), radius=34, fill="#ffe7e0", outline="#e5b3aa", width=3)
    draw.text((175, 315), "还剩：3天", font=F_TITLE, fill="#6d2b22")
    draw.text((175, 430), "先救能交的部分", font=F_BODY, fill="#6d2b22")
    tasks = ["先搭outline", "补2-3个证据", "引用格式最后查", "别从封面开始精修"]
    y = 650
    for task in tasks:
        rounded(draw, (115, y, WIDTH - 115, y + 92), 24, "#fffaf0", outline="#eadbc5", width=2)
        draw.text((155, y + 25), f"□ {task}", font=F_BODY, fill="#3f362d")
        y += 125
    draw.text((115, HEIGHT - 170), "越到ddl越不能乱救。", font=F_BODY, fill="#827568")
    return img


def chat_bubble(draw, xy, text, incoming=True):
    x, y = xy
    lines = wrap_text(text, 16)
    h = 34 + len(lines) * 44
    w = min(720, max(220, max(len(line) for line in lines) * 36 + 58))
    fill = "#ffffff" if incoming else "#95ec69"
    box = (x, y, x + w, y + h)
    rounded(draw, box, 24, fill)
    ty = y + 22
    for line in lines:
        draw.text((x + 28, ty), line, font=F_CHAT, fill="#1f1f1f")
        ty += 44
    return h


def student_chat_slide():
    img = Image.new("RGB", (WIDTH, HEIGHT), "#ededed")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, 118), fill="#f7f7f7")
    draw.text((72, 48), "final互助小群(8)", font=F_BODY, fill="#111111")
    draw.text((486, 142), "23:48", font=F_TINY, fill="#8e8e8e")
    messages = [
        ("小林", "你们reference真的要背吗…"),
        ("momo", "别问 我现在连week7都没看完"),
        ("Yan", "我也是 刚打开rubric就想睡"),
        ("阿梨", "考场越漂亮题越难是真的😇"),
        ("小林", "我现在最怕essay题问得很抽象"),
        ("momo", "我已经开始算最低要考几分了"),
        ("Yan", "analysis和evaluation到底差在哪"),
        ("阿梨", "救命 这不就是我"),
    ]
    y = 205
    for idx, (name, msg) in enumerate(messages):
        draw.ellipse((62, y + 4, 112, y + 54), fill=["#c8d7e9", "#e8c9c9", "#d9e7ce"][idx % 3])
        draw.text((132, y - 8), name, font=F_TINY, fill="#838383")
        h = chat_bubble(draw, (132, y + 24), msg, True)
        y += h + 42
    draw.rounded_rectangle((92, HEIGHT - 160, WIDTH - 92, HEIGHT - 68), radius=28, fill="#fff8e7", outline="#e0c58d", width=2)
    draw.text((128, HEIGHT - 132), "有没有也在final硬撑的同学？", font=F_BODY, fill="#4c3514")
    return img


def student_rubric_slide():
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f2efe8")
    draw = ImageDraw.Draw(img)
    rounded(draw, (76, 96, WIDTH - 76, HEIGHT - 96), 28, "#ffffff", outline="#d9d2c5", width=2)
    draw.text((128, 150), "Assessment Brief", font=F_SUBTITLE, fill="#222222")
    draw.text((128, 222), "Module: [blurred]", font=F_SMALL, fill="#777777")
    y = 310
    for i in range(11):
        draw.rounded_rectangle((128, y, WIDTH - 128, y + 34), radius=8, fill="#e9e9e9")
        y += 58
    for word, y0 in [("analysis", 425), ("evidence", 600), ("reference", 775)]:
        draw.rounded_rectangle((220, y0, 510, y0 + 64), radius=18, outline="#d83a2e", width=6)
        draw.text((245, y0 + 12), word, font=F_BODY, fill="#1f1f1f")
    draw.line((175, 1010, 840, 980), fill="#d83a2e", width=8)
    draw.text((135, 1080), "我到底先写哪一块？", font=F_SUBTITLE, fill="#241f1b")
    draw.text((135, 1185), "截图要打码，只保留关键词", font=F_SMALL, fill="#8b7f70")
    return img


def student_comment_slide():
    img = base("student")
    draw = ImageDraw.Draw(img)
    draw.text((86, 110), "今天真的有点撑不住", font=F_SUBTITLE, fill="#2b2520")
    prompts = [
        "复习范围太散",
        "rubric 看不懂",
        "reference 不知道怎么准备",
        "ddl 越看越近",
    ]
    y = 265
    for item in prompts:
        rounded(draw, (95, y, WIDTH - 95, y + 105), 26, "#fffaf0", outline="#eadbc5", width=2)
        draw.text((135, y + 30), f"☐ {item}", font=F_BODY, fill="#40382f")
        y += 140
    draw.rounded_rectangle((110, 945, WIDTH - 110, 1160), radius=32, fill="#ffe7e0")
    draw.text((150, 995), "有没有同样 final 硬撑的同学？", font=F_BODY, fill="#6d2b22")
    draw.text((150, 1062), "你们现在最卡哪一步…", font=F_BODY, fill="#6d2b22")
    draw.text((112, HEIGHT - 180), "评论区像求助，不要像引流。", font=F_SMALL, fill="#827568")
    return img


def cover(visual):
    role = visual["role"]
    img = base(role)
    draw = ImageDraw.Draw(img)
    lines = str(visual["coverText"]).split("\n")

    if role == "student":
        draw.text((82, 90), "Notes", font=F_SMALL, fill="#9a8c75")
        rounded(draw, (70, 150, WIDTH - 70, HEIGHT - 120), 42, "#fffaf0", outline="#eadbc5", width=3)
        y = 270
        for line in lines:
            draw.text((130, y), line, font=F_TITLE, fill="#2b2520")
            y += 118
        draw_tag(draw, "DDL快到了", (128, y + 34), "#ffe7e0", "#7d2b1f")
        draw_tag(draw, "范围太散", (390, y + 34), "#fff1a8", "#5a4310")
        draw.line((128, 690, 760, 648), fill="#d93a2f", width=10)
        draw.arc((690, 578, 935, 720), 8, 350, fill="#d93a2f", width=9)
        draw.text((130, HEIGHT - 220), "不是没学，是越看越慌", font=F_BODY, fill="#63564a")
    elif role == "ip":
        rounded(draw, (86, 118, WIDTH - 86, HEIGHT - 118), 40, "#fff8eb", outline="#decaa5", width=3)
        draw.text((130, 180), lines[0], font=F_TITLE, fill="#2c281f")
        draw.text((130, 298), lines[1] if len(lines) > 1 else "", font=F_TITLE, fill="#2c281f")
        bullets = ["任务类型", "评分点", "倒推时间"]
        y = 515
        for i, b in enumerate(bullets, 1):
            rounded(draw, (135, y, WIDTH - 135, y + 118), 28, "#fff0b8")
            draw.text((175, y + 34), f"{i}. {b}", font=F_SUBTITLE, fill="#4f3b13")
            y += 155
        draw.text((135, HEIGHT - 205), "先别急着硬背，先拆清楚。", font=F_BODY, fill="#6c604f")
    else:
        draw.text((78, 58), "风险排查", font=F_SUBTITLE, fill="#fffaf0")
        y = 255
        for line in lines:
            draw.text((86, y), line, font=F_TITLE, fill="#172033")
            y += 118
        steps = ["任务类型", "最紧急风险", "处理方式"]
        y = 590
        for i, step in enumerate(steps, 1):
            rounded(draw, (112, y, WIDTH - 112, y + 112), 26, "#e7edf5", outline="#9fb0c5", width=2)
            draw.ellipse((142, y + 28, 196, y + 82), fill="#162338")
            draw.text((160, y + 36), str(i), font=F_SMALL, fill="#ffffff")
            draw.text((230, y + 30), step, font=F_SUBTITLE, fill="#162338")
            y += 150
        draw.text((112, HEIGHT - 190), "不承诺结果，只先判断问题在哪。", font=F_BODY, fill="#596274")
    return img


def content_slide(visual, index, slide_text):
    role = visual["role"]
    slide = slide_text if isinstance(slide_text, dict) else {"kind": "", "text": str(slide_text)}
    kind = slide.get("kind", "")
    text = slide.get("text", str(slide_text))

    if role == "student":
        if kind == "student-desk":
            return student_desk_slide()
        if kind == "student-chat":
            return student_chat_slide()
        if kind == "student-rubric":
            return student_rubric_slide()
        if kind == "student-countdown":
            return student_countdown_slide()
        if kind == "student-comment" or index >= 5:
            return student_comment_slide()

    img = base(role)
    draw = ImageDraw.Draw(img)
    if role == "ip":
        rounded(draw, (90, 120, WIDTH - 90, HEIGHT - 120), 36, "#fff8eb", outline="#decaa5", width=3)
        draw_tag(draw, "学姐拆解", (130, 170), "#fff0b8")
        draw_multiline(draw, (130, 285), text, F_SUBTITLE, "#2c281f", 13, 18)
        y = 590
        for item in ["先看要求", "再拆评分", "最后倒推"]:
            rounded(draw, (150, y, WIDTH - 150, y + 98), 24, "#ffffff", outline="#decaa5", width=2)
            draw.text((190, y + 25), item, font=F_BODY, fill="#493d2c")
            y += 128
    else:
        draw.rectangle((0, 0, WIDTH, 160), fill="#162338")
        draw.text((70, 52), f"Step {index}", font=F_SUBTITLE, fill="#ffffff")
        draw_multiline(draw, (90, 240), text, F_SUBTITLE, "#162338", 13, 18)
        nodes = ["exam", "essay", "report", "dissertation"]
        cols = 2
        for i, node in enumerate(nodes):
            x = 120 + (i % cols) * 430
            y = 650 + math.floor(i / cols) * 170
            rounded(draw, (x, y, x + 350, y + 110), 24, "#e7edf5", outline="#9fb0c5", width=2)
            draw.text((x + 35, y + 34), node, font=F_BODY, fill="#162338")
        draw.text((90, HEIGHT - 185), "先判断，再行动。", font=F_BODY, fill="#596274")
    return img


def main():
    if not VISUAL_JSON.exists():
        raise SystemExit(f"Missing {VISUAL_JSON}")
    data = json.loads(VISUAL_JSON.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = []
    for visual in data.get("visuals", []):
        role = visual["role"]
        role_dir = OUT_DIR / role
        role_dir.mkdir(parents=True, exist_ok=True)

        cover_path = role_dir / "01-cover.png"
        save(cover(visual), cover_path)
        files.append({"role": role, "roleName": visual["roleName"], "type": "cover", "path": str(cover_path)})

        for idx, slide in enumerate(visual.get("slides", []), start=2):
            path = role_dir / f"{idx:02d}-slide.png"
            save(content_slide(visual, idx, slide), path)
            slide_text = slide.get("text", "") if isinstance(slide, dict) else str(slide)
            slide_kind = slide.get("kind", "") if isinstance(slide, dict) else ""
            files.append({
                "role": role,
                "roleName": visual["roleName"],
                "type": "slide",
                "path": str(path),
                "kind": slide_kind,
                "text": slide_text
            })

    role_sheets = {}
    for role in sorted({item["role"] for item in files}):
        role_files = [item for item in files if item["role"] == role]
        sheet_path = OUT_DIR / role / "00-contact-sheet.png"
        role_sheets[role] = make_contact_sheet(role_files, sheet_path, f"{role} 图片预览")

    all_sheet = make_contact_sheet(files, OUT_DIR / "00-all-contact-sheet.png", "小红书三账号图片总览")
    checks = quality_checks(files)

    manifest = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(),
        "source": str(VISUAL_JSON),
        "outputDir": str(OUT_DIR),
        "count": len(files),
        "contactSheet": all_sheet,
        "roleContactSheets": role_sheets,
        "quality": {
            "ok": all(item["ok"] for item in checks),
            "checked": len(checks),
            "failed": [item for item in checks if not item["ok"]]
        },
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {MANIFEST}")
    print(f"PNG 图片 {len(files)} 张，目录：{OUT_DIR}")


if __name__ == "__main__":
    main()
