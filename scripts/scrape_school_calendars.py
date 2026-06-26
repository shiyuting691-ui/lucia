"""
学校学术日历爬取脚本
一次性爬取主要目标学校的考试/学期时间节点，保存到 school_calendar 表作为推送依据
"""
import sys, os, json, re, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
from database.crud import get_session
from database.models import SchoolCalendar

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,zh-CN;q=0.8",
}

CURRENT_YEAR = "2025-2026"

# ── 目标学校 ──────────────────────────────────────────────────────────
SCHOOLS = [
    # ── 英国 ──
    {
        "name": "伦敦大学学院UCL", "country": "UK", "en_name": "UCL",
        "url": "https://www.ucl.ac.uk/students/life-ucl/term-dates-and-closures/term-dates-and-reading-weeks-2024-25",
    },
    {
        "name": "利兹大学", "country": "UK", "en_name": "University of Leeds",
        "url": "https://ses.leeds.ac.uk/info/21517/study/1011/term_dates",
    },
    {
        "name": "伯明翰大学", "country": "UK", "en_name": "University of Birmingham",
        "url": "https://www.birmingham.ac.uk/students/academic-life/term-dates.aspx",
    },
    {
        "name": "伦敦国王学院KCL", "country": "UK", "en_name": "King's College London",
        "url": "https://www.kcl.ac.uk/aboutkings/principal/dean/teaching/calendar/academic-calendar",
    },
    {
        "name": "华威大学", "country": "UK", "en_name": "University of Warwick",
        "url": "https://warwick.ac.uk/services/calendar/",
    },
    {
        "name": "曼彻斯特大学", "country": "UK", "en_name": "University of Manchester",
        "url": "https://www.manchester.ac.uk/study/undergraduate/key-dates/",
    },
    {
        "name": "谢菲尔德大学", "country": "UK", "en_name": "University of Sheffield",
        "url": "https://www.sheffield.ac.uk/it-services/calendars-and-timetables/term-dates",
    },
    {
        "name": "布里斯托大学", "country": "UK", "en_name": "University of Bristol",
        "url": "https://www.bristol.ac.uk/students/your-studies/academic-year/",
    },
    {
        "name": "杜伦大学", "country": "UK", "en_name": "Durham University",
        "url": "https://www.durham.ac.uk/departments/academic/student-information-and-support/term-dates/",
    },
    # ── 澳洲 ──
    {
        "name": "新南威尔士大学", "country": "AU", "en_name": "UNSW Sydney",
        "url": "https://www.student.unsw.edu.au/calendar",
    },
    {
        "name": "墨尔本大学", "country": "AU", "en_name": "University of Melbourne",
        "url": "https://students.unimelb.edu.au/your-course/manage-your-course/key-dates",
    },
    {
        "name": "悉尼大学", "country": "AU", "en_name": "University of Sydney",
        "url": "https://www.sydney.edu.au/students/academic-calendar.html",
    },
    {
        "name": "莫纳什大学", "country": "AU", "en_name": "Monash University",
        "url": "https://www.monash.edu/students/dates",
    },
    # ── 美国 ──
    {
        "name": "纽约大学", "country": "US", "en_name": "New York University",
        "url": "https://www.nyu.edu/registrar/calendars/university-academic-calendar.html",
    },
    {
        "name": "加州大学圣地亚哥分校", "country": "US", "en_name": "UC San Diego",
        "url": "https://blink.ucsd.edu/instructors/resources/academic-info/calendars/index.html",
    },
    {
        "name": "宾夕法尼亚州立大学", "country": "US", "en_name": "Penn State University",
        "url": "https://www.registrar.psu.edu/academic-calendars/2024-25.cfm",
    },
    # ── 香港 ──
    {
        "name": "香港教育大学", "country": "HK", "en_name": "EdUHK",
        "url": "https://www.eduhk.hk/re/modules/content/index.php?id=6",
    },
    {
        "name": "香港城市大学", "country": "HK", "en_name": "City University of Hong Kong",
        "url": "https://www.cityu.edu.hk/aro/reg/acadcal_ug.htm",
    },
]

# ── 关键词→事件类型 映射 ─────────────────────────────────────────────
EVENT_KEYWORDS = {
    "exam_period":    ["examination period", "exam period", "exams begin", "examinations begin", "final examination", "written examination", "end of year exam"],
    "teaching_start": ["teaching begins", "teaching starts", "instruction begins", "classes begin", "semester 1 begins", "semester 2 begins", "term 1 begins", "term 2 begins", "autumn term begins", "spring term begins", "michaelmas begins", "hilary begins"],
    "teaching_end":   ["teaching ends", "last day of teaching", "teaching period ends", "term ends", "semester ends"],
    "submission":     ["submission deadline", "coursework deadline", "assignment due", "dissertation submission", "thesis submission"],
    "results":        ["results release", "results available", "grades released", "transcript available"],
    "reading_week":   ["reading week", "revision week", "study week", "consolidation week"],
    "graduation":     ["graduation", "degree ceremony", "conferment"],
}

# 月份名映射
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_RE = re.compile(
    r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{4})',
    re.IGNORECASE
)
DATE_RE2 = re.compile(
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})',
    re.IGNORECASE
)


def _parse_date(text: str) -> date | None:
    m = DATE_RE.search(text)
    if m:
        day, mon, yr = int(m.group(1)), MONTH_MAP.get(m.group(2).lower(), 0), int(m.group(3))
        if mon and 1 <= day <= 31:
            try:
                return date(yr, mon, day)
            except ValueError:
                pass
    m = DATE_RE2.search(text)
    if m:
        mon, day, yr = MONTH_MAP.get(m.group(1).lower(), 0), int(m.group(2)), int(m.group(3))
        if mon and 1 <= day <= 31:
            try:
                return date(yr, mon, day)
            except ValueError:
                pass
    return None


def _fetch(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "pdf" in ct or url.endswith(".pdf"):
            return ""
        return resp.text
    except Exception as e:
        logger.debug(f"Fetch error {url}: {e}")
        return ""


def _extract_events(soup: BeautifulSoup) -> list:
    """从页面提取关键事件"""
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    events = []
    seen = set()

    for i, line in enumerate(lines):
        line_lower = line.lower()
        for etype, keywords in EVENT_KEYWORDS.items():
            for kw in keywords:
                if kw not in line_lower:
                    continue
                # 在当前行及相邻行找日期
                context = " ".join(lines[max(0, i-1):i+3])
                dt = _parse_date(context)
                key = (etype, line[:60])
                if key in seen:
                    break
                seen.add(key)
                events.append({
                    "event_type": etype,
                    "event_name": line[:150],
                    "start_date": dt,
                    "context": context[:200],
                })
                break

    return events[:20]


def _get_default_events(school: dict) -> list:
    """当爬取失败时，根据国家生成通用的学术事件"""
    now = datetime.now()
    year = now.year
    country = school["country"]

    if country == "UK":
        return [
            {"event_type": "teaching_start", "event_name": "秋季学期开始（推断）", "start_date": date(year, 9, 23), "context": "UK通用"},
            {"event_type": "exam_period",    "event_name": "一月考试期（推断）",   "start_date": date(year+1, 1, 6)  if now.month > 6 else date(year, 1, 6),  "context": "UK通用"},
            {"event_type": "teaching_start", "event_name": "春季学期开始（推断）", "start_date": date(year+1, 1, 20) if now.month > 6 else date(year, 1, 20), "context": "UK通用"},
            {"event_type": "exam_period",    "event_name": "夏季考试期（推断）",   "start_date": date(year, 5, 1),   "context": "UK通用"},
            {"event_type": "submission",     "event_name": "毕业论文提交（推断）", "start_date": date(year, 9, 1),   "context": "UK通用"},
        ]
    elif country == "AU":
        return [
            {"event_type": "teaching_start", "event_name": "一学期开始（推断）",   "start_date": date(year, 2, 24), "context": "AU通用"},
            {"event_type": "exam_period",    "event_name": "一学期考试期（推断）", "start_date": date(year, 6, 2),  "context": "AU通用"},
            {"event_type": "teaching_start", "event_name": "二学期开始（推断）",   "start_date": date(year, 7, 28), "context": "AU通用"},
            {"event_type": "exam_period",    "event_name": "二学期考试期（推断）", "start_date": date(year, 11, 3), "context": "AU通用"},
        ]
    elif country == "US":
        return [
            {"event_type": "teaching_start", "event_name": "秋季学期开始（推断）", "start_date": date(year, 8, 26), "context": "US通用"},
            {"event_type": "exam_period",    "event_name": "期末考试期（推断）",   "start_date": date(year, 12, 9), "context": "US通用"},
            {"event_type": "teaching_start", "event_name": "春季学期开始（推断）", "start_date": date(year+1, 1, 13) if now.month > 6 else date(year, 1, 13), "context": "US通用"},
            {"event_type": "exam_period",    "event_name": "春季期末考试（推断）", "start_date": date(year, 5, 5),  "context": "US通用"},
        ]
    elif country == "HK":
        return [
            {"event_type": "teaching_start", "event_name": "第一学期开始（推断）", "start_date": date(year, 9, 2),   "context": "HK通用"},
            {"event_type": "exam_period",    "event_name": "一学期考试（推断）",   "start_date": date(year, 12, 9),  "context": "HK通用"},
            {"event_type": "teaching_start", "event_name": "第二学期开始（推断）", "start_date": date(year+1, 1, 13) if now.month > 6 else date(year, 1, 13), "context": "HK通用"},
            {"event_type": "exam_period",    "event_name": "二学期考试（推断）",   "start_date": date(year, 4, 14),  "context": "HK通用"},
        ]
    return []


def save_events(school: dict, events: list, source: str, confidence: str):
    with get_session() as s:
        # 先清除旧数据
        s.query(SchoolCalendar).filter(
            SchoolCalendar.school == school["name"],
            SchoolCalendar.country == school["country"],
        ).delete()

        for ev in events:
            start = ev.get("start_date")
            obj = SchoolCalendar(
                school=school["name"],
                country=school["country"],
                academic_year=CURRENT_YEAR,
                term="",
                event_type=ev["event_type"],
                event_name=ev["event_name"],
                start_date=datetime.combine(start, datetime.min.time()) if start else None,
                end_date=None,
                confidence=confidence,
                source=source,
                notes=ev.get("context", ""),
                updated_at=datetime.utcnow(),
            )
            s.add(obj)
        s.flush()


def scrape_school(school: dict) -> dict:
    name = school["name"]
    logger.info(f"▶ 爬取 {name} ({school['country']})")

    html = _fetch(school["url"])
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        events = _extract_events(soup)

        if events:
            save_events(school, events, source="官方网站", confidence="high")
            logger.info(f"  ✓ 爬取成功: {len(events)} 个事件")
            return {"school": name, "status": "scraped", "events": len(events)}

    # 爬取失败或无有效内容，使用推断数据
    logger.warning(f"  ⚠ 页面无有效日期，使用国家通用日历推断")
    default_events = _get_default_events(school)
    save_events(school, default_events, source="国家通用推断", confidence="medium")
    return {"school": name, "status": "default", "events": len(default_events)}


def main():
    print(f"开始爬取 {len(SCHOOLS)} 所学校的学术日历")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = []
    for i, school in enumerate(SCHOOLS):
        result = scrape_school(school)
        results.append(result)
        if i < len(SCHOOLS) - 1:
            time.sleep(1.5)

    scraped = [r for r in results if r["status"] == "scraped"]
    default = [r for r in results if r["status"] == "default"]

    print(f"\n=== 爬取完成 ===")
    print(f"成功爬取官网: {len(scraped)}/{len(results)}")
    for r in scraped:
        print(f"  ✓ {r['school']}: {r['events']} 个事件")
    if default:
        print(f"使用推断数据: {len(default)}")
        for r in default:
            print(f"  ~ {r['school']}: {r['events']} 个推断事件")

    with get_session() as s:
        total = s.query(SchoolCalendar).count()
        print(f"\n数据库 school_calendar 总记录: {total}")


if __name__ == "__main__":
    main()
