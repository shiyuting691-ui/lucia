"""
School Calendar Scraper
策略1：尝试ICS日历订阅文件（直接解析，无需LLM）
策略2：HTML爬取 + LLM解析（兜底）
策略3：seed_known_calendars() 按学期模式预填充2025-2026基础数据

依赖（已在 requirements.txt 中）：
  requests>=2.31.0
  beautifulsoup4>=4.12.0
"""

import json
import logging
import re
import sys
import os
from datetime import datetime, date, timedelta
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.crud import save_school_calendar, get_session
from database.models import SchoolCalendar
from services.llm import LLMRouter

logger = logging.getLogger(__name__)

# ── 每所学校：ics_urls 优先尝试，urls 是 HTML 兜底 ──────────────────
TARGET_SCHOOLS = [
    # 澳洲
    {"name": "新南威尔士大学", "country": "AU",
     "ics_urls": [
         "https://www.student.unsw.edu.au/sites/default/files/uploads/group110/Calendar/2025calendar.ics",
         "https://www.student.unsw.edu.au/calendar.ics",
     ],
     "urls": [
         "https://www.student.unsw.edu.au/dates",
         "https://www.student.unsw.edu.au/managing-your-studies/key-dates",
     ]},
    {"name": "悉尼大学", "country": "AU",
     "ics_urls": [
         "https://www.sydney.edu.au/students/important-dates.ics",
     ],
     "urls": [
         "https://www.sydney.edu.au/students/important-dates.html",
         "https://www.sydney.edu.au/students/key-dates.html",
     ]},
    {"name": "墨尔本大学", "country": "AU",
     "ics_urls": [],
     "urls": [
         "https://www.unimelb.edu.au/dates",
         "https://students.unimelb.edu.au/your-course/manage-your-course/your-enrolment-and-enrolment-changes/dates-and-timetables",
     ]},
    {"name": "莫纳什大学Monash", "country": "AU",
     "ics_urls": [
         "https://www.monash.edu/students/admin/dates/key-dates.ics",
     ],
     "urls": [
         "https://www.monash.edu/students/admin/dates",
         "https://www.monash.edu/students/admin/enrolments/key-dates",
     ]},
    {"name": "昆士兰大学", "country": "AU",
     "ics_urls": [
         "https://my.uq.edu.au/information-and-services/manage-my-program/student-admin/key-dates/calendar.ics",
     ],
     "urls": [
         "https://my.uq.edu.au/information-and-services/manage-my-program/student-admin/key-dates",
         "https://www.uq.edu.au/study/important-dates",
     ]},
    # 英国
    {"name": "伦敦大学学院UCL", "country": "UK",
     "ics_urls": [
         "https://www.ucl.ac.uk/students/sites/students/files/term-dates-2025-26.ics",
         "https://www.ucl.ac.uk/calendar/term-dates.ics",
     ],
     "urls": [
         "https://www.ucl.ac.uk/students/life-ucl/term-dates-and-closures/term-dates-and-closures-2024-25",
         "https://www.ucl.ac.uk/students/life-ucl/term-dates-and-closures",
     ]},
    {"name": "伯明翰大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.birmingham.ac.uk/students/academic-life/dates/index.aspx",
         "https://www.birmingham.ac.uk/students/academic-life/dates",
     ]},
    {"name": "伦敦国王学院KCL", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.kcl.ac.uk/importantdates",
         "https://www.kcl.ac.uk/study/term-dates",
     ]},
    {"name": "利兹大学", "country": "UK",
     "ics_urls": [
         "https://students.leeds.ac.uk/calendar.ics",
     ],
     "urls": [
         "https://students.leeds.ac.uk/info/10110/getting_here_and_settling_in/697/term_and_semester_dates",
         "https://www.leeds.ac.uk/info/1000007/studying/91/key_dates",
     ]},
    {"name": "谢菲尔德大学", "country": "UK",
     "ics_urls": [
         "https://www.sheffield.ac.uk/academic-calendar.ics",
     ],
     "urls": [
         "https://www.sheffield.ac.uk/calendar/key-dates",
         "https://www.sheffield.ac.uk/students/dates",
     ]},
    {"name": "曼彻斯特大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.manchester.ac.uk/study/experience/student-life/key-dates-and-deadlines/",
         "https://www.manchester.ac.uk/study/term-dates/",
     ]},
    {"name": "布里斯托大学", "country": "UK",
     "ics_urls": [
         "https://www.bristol.ac.uk/students/your-studies/academic-year/calendar.ics",
     ],
     "urls": [
         "https://www.bristol.ac.uk/students/your-studies/academic-year/",
         "https://www.bristol.ac.uk/students/term-dates/",
     ]},
    {"name": "华威大学", "country": "UK",
     "ics_urls": [
         "https://warwick.ac.uk/services/calendar/term-dates.ics",
     ],
     "urls": [
         "https://warwick.ac.uk/services/calendar/",
         "https://warwick.ac.uk/insite/topics/termdates/",
     ]},
    {"name": "杜伦大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.durham.ac.uk/colleges-and-student-experience/student-experience/term-dates/",
         "https://www.durham.ac.uk/about-us/governance/term-dates/",
     ]},
    {"name": "格拉斯哥大学", "country": "UK",
     "ics_urls": [
         "https://www.gla.ac.uk/myglasgow/registry/semesterdates/semesterdates2025-26.ics",
     ],
     "urls": [
         "https://www.gla.ac.uk/myglasgow/registry/semesterdates/",
         "https://www.gla.ac.uk/students/termdates/",
     ]},
    {"name": "南安普敦大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.southampton.ac.uk/student-life/academic-life/key-dates.page",
         "https://www.southampton.ac.uk/about/governance/term-dates.page",
     ]},
    {"name": "爱丁堡大学", "country": "UK",
     "ics_urls": [
         "https://www.ed.ac.uk/sites/default/files/atoms/files/semester-dates-2025-26.ics",
         "https://www.ed.ac.uk/calendar/semester-dates.ics",
     ],
     "urls": [
         "https://www.ed.ac.uk/semester-dates",
         "https://www.ed.ac.uk/students/studying/semester-dates",
     ]},
    {"name": "约克大学", "country": "UK",
     "ics_urls": [
         "https://www.york.ac.uk/about/term-dates/term-dates-2025-26.ics",
     ],
     "urls": [
         "https://www.york.ac.uk/about/term-dates/",
         "https://www.york.ac.uk/students/study/term-dates/",
     ]},
    {"name": "诺丁汉大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.nottingham.ac.uk/about/campus/important-dates.aspx",
         "https://www.nottingham.ac.uk/currentstudents/dates.aspx",
     ]},
    {"name": "雷丁大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.reading.ac.uk/essentials/The_University/Important_dates",
         "https://www.reading.ac.uk/studying-at-ug/dates-terms/",
     ]},
    {"name": "伦敦玛丽女王大学Queen Mary", "country": "UK",
     "ics_urls": [
         "https://www.qmul.ac.uk/calendar/ical/",
     ],
     "urls": [
         "https://www.qmul.ac.uk/calendar/",
         "https://www.qmul.ac.uk/students/dates/",
     ]},
    {"name": "纽卡斯尔大学", "country": "UK",
     "ics_urls": [],
     "urls": [
         "https://www.ncl.ac.uk/students/progress/student-records/term-dates/",
     ]},
    # 香港
    {"name": "香港教育大学", "country": "HK",
     "ics_urls": [],
     "urls": [
         "https://www.eduhk.hk/main/en/study_at_eduhk/academic_calendar",
         "https://www.eduhk.hk/registry/academic_calendar/",
     ]},
    {"name": "香港理工大学", "country": "HK",
     "ics_urls": [],
     "urls": [
         "https://www.polyu.edu.hk/ar/academic-calendar/",
         "https://www.polyu.edu.hk/en/home/study/academic-calendar/",
     ]},
    {"name": "香港城市大学", "country": "HK",
     "ics_urls": [],
     "urls": [
         "https://www.cityu.edu.hk/registrar/academic_calendar.htm",
         "https://www.cityu.edu.hk/academic-calendar/",
     ]},
    {"name": "香港大学", "country": "HK",
     "ics_urls": [],
     "urls": [
         "https://www.hku.hk/calendar/",
         "https://www.hku.hk/currentstudents/academic-calendar/",
     ]},
]

# ── 2025-2026 标准学期模式种子数据 ─────────────────────────────────────
# 数据来源：各国大学官网公开信息汇总，置信度=medium，source=模式推断
# 格式：school_name -> list of events
_SEED_2025_2026 = {
    # ── 澳洲学校（学期制，南半球）────────────────────────────────
    "AU_S1": {  # 澳洲通用Semester 1
        "events": [
            {"event_type": "teaching_start", "event_name": "Semester 1 开学", "start_date": "2025-02-24", "end_date": None, "term": "Semester 1"},
            {"event_type": "teaching_end", "event_name": "Semester 1 最后上课日", "start_date": "2025-05-30", "end_date": None, "term": "Semester 1"},
            {"event_type": "exam_period", "event_name": "Semester 1 期末考试", "start_date": "2025-06-02", "end_date": "2025-06-21", "term": "Semester 1"},
            {"event_type": "teaching_start", "event_name": "Semester 2 开学", "start_date": "2025-07-21", "end_date": None, "term": "Semester 2"},
            {"event_type": "teaching_end", "event_name": "Semester 2 最后上课日", "start_date": "2025-10-24", "end_date": None, "term": "Semester 2"},
            {"event_type": "exam_period", "event_name": "Semester 2 期末考试", "start_date": "2025-10-27", "end_date": "2025-11-15", "term": "Semester 2"},
        ]
    },
    # ── 英国学校（三学期制/两学期制）──────────────────────────────
    "UK_3TERM": {  # 英国通用三学期
        "events": [
            {"event_type": "teaching_start", "event_name": "Autumn Term 开学", "start_date": "2025-09-22", "end_date": None, "term": "Autumn Term"},
            {"event_type": "holiday", "event_name": "Reading Week", "start_date": "2025-11-03", "end_date": "2025-11-07", "term": "Autumn Term"},
            {"event_type": "teaching_end", "event_name": "Autumn Term 结束", "start_date": "2025-12-12", "end_date": None, "term": "Autumn Term"},
            {"event_type": "teaching_start", "event_name": "Spring Term 开学", "start_date": "2026-01-12", "end_date": None, "term": "Spring Term"},
            {"event_type": "holiday", "event_name": "Reading Week", "start_date": "2026-02-16", "end_date": "2026-02-20", "term": "Spring Term"},
            {"event_type": "teaching_end", "event_name": "Spring Term 结束", "start_date": "2026-03-20", "end_date": None, "term": "Spring Term"},
            {"event_type": "teaching_start", "event_name": "Summer Term 开学", "start_date": "2026-04-27", "end_date": None, "term": "Summer Term"},
            {"event_type": "exam_period", "event_name": "Summer Exams", "start_date": "2026-05-11", "end_date": "2026-06-19", "term": "Summer Term"},
            {"event_type": "submission", "event_name": "Dissertation 提交截止（参考）", "start_date": "2026-09-11", "end_date": None, "term": "Summer Term"},
        ]
    },
    "UK_SEMESTER": {  # 爱丁堡/格拉斯哥等学期制
        "events": [
            {"event_type": "teaching_start", "event_name": "Semester 1 开学", "start_date": "2025-09-15", "end_date": None, "term": "Semester 1"},
            {"event_type": "teaching_end", "event_name": "Semester 1 结束", "start_date": "2025-12-05", "end_date": None, "term": "Semester 1"},
            {"event_type": "exam_period", "event_name": "Semester 1 考试", "start_date": "2026-01-05", "end_date": "2026-01-16", "term": "Semester 1"},
            {"event_type": "teaching_start", "event_name": "Semester 2 开学", "start_date": "2026-01-19", "end_date": None, "term": "Semester 2"},
            {"event_type": "teaching_end", "event_name": "Semester 2 结束", "start_date": "2026-04-10", "end_date": None, "term": "Semester 2"},
            {"event_type": "exam_period", "event_name": "Semester 2 考试", "start_date": "2026-04-20", "end_date": "2026-05-15", "term": "Semester 2"},
            {"event_type": "submission", "event_name": "Dissertation 提交截止（参考）", "start_date": "2026-08-28", "end_date": None, "term": "Semester 2"},
        ]
    },
    # ── 香港学校 ────────────────────────────────────────────────
    "HK_SEMESTER": {
        "events": [
            {"event_type": "teaching_start", "event_name": "Semester 1 开学", "start_date": "2025-09-01", "end_date": None, "term": "Semester 1"},
            {"event_type": "teaching_end", "event_name": "Semester 1 结束", "start_date": "2025-12-12", "end_date": None, "term": "Semester 1"},
            {"event_type": "exam_period", "event_name": "Semester 1 考试", "start_date": "2025-12-15", "end_date": "2025-12-31", "term": "Semester 1"},
            {"event_type": "teaching_start", "event_name": "Semester 2 开学", "start_date": "2026-01-12", "end_date": None, "term": "Semester 2"},
            {"event_type": "teaching_end", "event_name": "Semester 2 结束", "start_date": "2026-04-17", "end_date": None, "term": "Semester 2"},
            {"event_type": "exam_period", "event_name": "Semester 2 考试", "start_date": "2026-04-20", "end_date": "2026-05-08", "term": "Semester 2"},
        ]
    },
}

# 每所学校对应哪个模板（加个性化偏移量）
_SCHOOL_TEMPLATE_MAP = {
    # 澳洲（UNSW稍早，悉尼稍晚）
    "新南威尔士大学": ("AU_S1", {"2025-02-24": "2025-02-17"}),  # UNSW早一周
    "悉尼大学": ("AU_S1", {}),
    "墨尔本大学": ("AU_S1", {"2025-02-24": "2025-03-03"}),  # 墨大晚一周
    "莫纳什大学Monash": ("AU_S1", {}),
    "昆士兰大学": ("AU_S1", {"2025-02-24": "2025-02-24"}),
    # 英国三学期制
    "伦敦大学学院UCL": ("UK_3TERM", {}),
    "伯明翰大学": ("UK_3TERM", {}),
    "伦敦国王学院KCL": ("UK_3TERM", {}),
    "利兹大学": ("UK_3TERM", {}),
    "谢菲尔德大学": ("UK_3TERM", {}),
    "曼彻斯特大学": ("UK_3TERM", {}),
    "布里斯托大学": ("UK_3TERM", {}),
    "华威大学": ("UK_3TERM", {}),
    "杜伦大学": ("UK_3TERM", {}),
    "南安普敦大学": ("UK_3TERM", {}),
    "诺丁汉大学": ("UK_3TERM", {}),
    "雷丁大学": ("UK_3TERM", {}),
    "伦敦玛丽女王大学Queen Mary": ("UK_3TERM", {}),
    "纽卡斯尔大学": ("UK_3TERM", {}),
    # 英国学期制
    "爱丁堡大学": ("UK_SEMESTER", {}),
    "格拉斯哥大学": ("UK_SEMESTER", {}),
    "约克大学": ("UK_SEMESTER", {"2025-09-15": "2025-09-29"}),  # 约克稍晚
    # 香港
    "香港教育大学": ("HK_SEMESTER", {}),
    "香港理工大学": ("HK_SEMESTER", {}),
    "香港城市大学": ("HK_SEMESTER", {}),
    "香港大学": ("HK_SEMESTER", {"2025-09-01": "2025-09-08"}),  # 港大稍晚
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/calendar;q=0.8,*/*;q=0.7",
}

_VALID_EVENT_TYPES = {"teaching_start", "teaching_end", "exam_period", "submission", "holiday"}


# ── ICS 解析 ─────────────────────────────────────────────────────────

def _fetch_ics(url: str, timeout: int = 15) -> Optional[str]:
    """尝试获取ICS文件，返回原始文本，失败返回None。"""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and ("BEGIN:VCALENDAR" in resp.text or "BEGIN:VEVENT" in resp.text):
            return resp.text
    except Exception as e:
        logger.debug("ICS fetch failed %s: %s", url, e)
    return None


def _parse_ics_text(ics_text: str, school_name: str) -> list:
    """
    解析ICS文本，提取学术日历事件。
    只解析标题含 exam/assignment/teaching/term/semester/lecture/submission/holiday/break/reading 的事件。
    """
    events = []
    keywords = {
        "exam": "exam_period",
        "assessment": "exam_period",
        "test": "exam_period",
        "assignment": "submission",
        "submission": "submission",
        "deadline": "submission",
        "dissertation": "submission",
        "thesis": "submission",
        "teaching": "teaching_start",
        "lecture": "teaching_start",
        "semester": "teaching_start",
        "term": "teaching_start",
        "orientation": "teaching_start",
        "enrolment": "teaching_start",
        "enroll": "teaching_start",
        "holiday": "holiday",
        "break": "holiday",
        "reading week": "holiday",
        "recess": "holiday",
        "vacation": "holiday",
        "closure": "holiday",
    }

    # 分割VEVENT块
    vevent_pattern = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
    for match in vevent_pattern.finditer(ics_text):
        block = match.group(1)
        summary = re.search(r"SUMMARY[^:]*:(.*?)(?:\r?\n[A-Z])", block + "\nEND", re.DOTALL)
        dtstart = re.search(r"DTSTART[^:]*:(\d{8})", block)
        dtend = re.search(r"DTEND[^:]*:(\d{8})", block)

        if not summary or not dtstart:
            continue

        title = summary.group(1).strip().replace("\\n", " ").replace("\\,", ",")
        title_lower = title.lower()

        # 年份过滤：只要2025/2026的
        start_raw = dtstart.group(1)
        if not start_raw.startswith(("2025", "2026")):
            continue

        # 事件类型匹配
        event_type = None
        for kw, etype in keywords.items():
            if kw in title_lower:
                event_type = etype
                break
        if not event_type:
            continue

        start_date = f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:8]}"
        end_date = None
        if dtend:
            end_raw = dtend.group(1)
            end_date = f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:8]}"
            if end_date == start_date:
                end_date = None

        # 推断term
        month = int(start_raw[4:6])
        if month in (9, 10, 11, 12):
            term = "Autumn Term" if "term" in title_lower.replace("semester", "") else "Semester 1"
        elif month in (1, 2, 3, 4):
            term = "Spring Term" if "spring" in title_lower else "Semester 2"
        else:
            term = "Semester 2" if month in (5, 6) else "Semester 1"

        events.append({
            "event_type": event_type,
            "event_name": title,
            "start_date": start_date,
            "end_date": end_date,
            "term": term,
            "confidence": "high",
        })

    return events


# ── HTML 爬取 ─────────────────────────────────────────────────────────

def _fetch_page_text(url: str, timeout: int = 15) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:8000]


def _fetch_any(urls: list, timeout: int = 15) -> tuple:
    last_err = None
    for url in urls:
        try:
            text = _fetch_page_text(url, timeout=timeout)
            if len(text) > 300:
                return url, text
        except Exception as e:
            last_err = e
            logger.debug("URL failed %s: %s", url, e)
    raise last_err or Exception("All URLs failed")


def _build_prompt(school_name: str, country: str, page_text: str) -> str:
    return f"""You are an academic calendar parser. Extract key academic dates from the university webpage text below.

University: {school_name} ({country})
Academic year context: 2025-2026

Extract ONLY these 5 event types:
- teaching_start  (semester/term teaching begins)
- teaching_end    (semester/term teaching ends / last day of classes)
- exam_period     (exam period start and end)
- submission      (assignment/thesis/dissertation submission deadlines)
- holiday         (public or university holidays, reading weeks, breaks)

Return a JSON array (and NOTHING else) in this exact format:
[
  {{"event_type": "teaching_start", "event_name": "Semester 1 begins", "start_date": "2025-07-21", "end_date": null, "term": "Semester 1", "confidence": "high"}},
  ...
]

Rules:
- Dates must be YYYY-MM-DD format. If only month/year known, use first day of month and set confidence to "low".
- confidence: "high" if exact date given, "medium" if approximate, "low" if inferred.
- If start and end are the same, set end_date to null.
- Include events for BOTH 2025 and 2026 if present.
- Return empty array [] if no relevant dates found.

Webpage text:
{page_text}"""


def _parse_llm_response(raw: str) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


# ── 数据库操作 ────────────────────────────────────────────────────────

def _delete_records(school_name: str, source: str) -> int:
    from sqlalchemy import delete as sa_delete
    with get_session() as s:
        result = s.execute(
            sa_delete(SchoolCalendar).where(
                SchoolCalendar.school == school_name,
                SchoolCalendar.source == source,
            )
        )
        return result.rowcount


def _write_events(events: list, school_name: str, country: str, source: str) -> int:
    seen = set()
    count = 0
    for ev in events:
        etype = ev.get("event_type", "")
        if etype not in _VALID_EVENT_TYPES:
            continue
        key = (school_name, ev.get("start_date", ""), etype, ev.get("event_name", "")[:30])
        if key in seen:
            continue
        seen.add(key)

        start_str = ev.get("start_date", "") or ""
        try:
            year = int(start_str[:4])
            academic_year = f"{year}-{year + 1}" if year < 2026 else f"{year - 1}-{year}"
        except (ValueError, TypeError):
            academic_year = "2025-2026"

        save_school_calendar({
            "school": school_name,
            "country": country,
            "academic_year": academic_year,
            "term": ev.get("term") or "",
            "event_type": etype,
            "event_name": ev.get("event_name") or "",
            "start_date": ev.get("start_date") or None,
            "end_date": ev.get("end_date") or None,
            "confidence": ev.get("confidence") or "medium",
            "source": source,
            "notes": "",
        })
        count += 1
    return count


# ── 种子数据预填充 ────────────────────────────────────────────────────

def seed_known_calendars(overwrite: bool = False) -> dict:
    """
    按学期模式预填充2025-2026年所有学校的关键节点。
    source='模式推断', confidence='medium'
    overwrite=False：如果该校已有模式推断数据则跳过。
    返回 {school_name: count} 统计。
    """
    results = {}
    for school_cfg in TARGET_SCHOOLS:
        name = school_cfg["name"]
        country = school_cfg["country"]

        if name not in _SCHOOL_TEMPLATE_MAP:
            continue

        # 检查是否已有数据
        if not overwrite:
            with get_session() as s:
                from sqlalchemy import select, func
                existing = s.execute(
                    select(func.count()).where(
                        SchoolCalendar.school == name,
                        SchoolCalendar.source == "模式推断",
                    )
                ).scalar()
                if existing and existing > 0:
                    logger.info("Seed skip (already exists): %s (%d records)", name, existing)
                    results[name] = 0
                    continue

        template_key, date_overrides = _SCHOOL_TEMPLATE_MAP[name]
        template = _SEED_2025_2026[template_key]

        events = []
        for ev in template["events"]:
            ev_copy = dict(ev)
            # 应用个性化日期覆盖
            if ev_copy["start_date"] in date_overrides:
                ev_copy["start_date"] = date_overrides[ev_copy["start_date"]]
            ev_copy["confidence"] = "medium"
            events.append(ev_copy)

        if overwrite:
            _delete_records(name, "模式推断")

        count = _write_events(events, name, country, source="模式推断")
        logger.info("Seed %s: %d events written", name, count)
        results[name] = count

    return results


# ── 主爬虫类 ─────────────────────────────────────────────────────────

class SchoolCalendarScraper:
    def __init__(self, config=None):
        self.config = config or {}
        self.llm = LLMRouter()

    def run(self, schools: Optional[List[dict]] = None) -> list:
        targets = schools if schools is not None else TARGET_SCHOOLS
        results = []
        for school_cfg in targets:
            try:
                result = self.scrape_one(school_cfg)
            except Exception as exc:
                result = {
                    "school": school_cfg.get("name", ""),
                    "ok": False,
                    "count": 0,
                    "error": str(exc),
                    "method": "error",
                }
            results.append(result)
            logger.info("Result: %s", result)
        return results

    def scrape_one(self, school_config: dict) -> dict:
        name = school_config.get("name", "")
        country = school_config.get("country", "")
        ics_urls = school_config.get("ics_urls", [])
        html_urls = school_config.get("urls") or ([school_config["url"]] if school_config.get("url") else [])

        # ── 策略1：ICS 文件 ──────────────────────────────────────
        for ics_url in ics_urls:
            ics_text = _fetch_ics(ics_url)
            if ics_text:
                events = _parse_ics_text(ics_text, name)
                if events:
                    _delete_records(name, "官方日历")
                    count = _write_events(events, name, country, source="官方日历")
                    logger.info("ICS success %s: %d events from %s", name, count, ics_url)
                    return {"school": name, "ok": True, "count": count, "error": "", "method": "ics"}

        # ── 策略2：HTML + LLM ────────────────────────────────────
        if not html_urls:
            return {"school": name, "ok": False, "count": 0, "error": "No URLs", "method": "none"}

        try:
            used_url, page_text = _fetch_any(html_urls)
            prompt = _build_prompt(name, country, page_text)
            resp = self.llm.generate_text(prompt, max_tokens=1000)
            raw_text = (getattr(resp, "content", None) or getattr(resp, "text", None) or "")
            events = _parse_llm_response(raw_text)

            if not isinstance(events, list):
                events = []

            if events:
                _delete_records(name, "官方日历")
                count = _write_events(events, name, country, source="官方日历")
                return {"school": name, "ok": True, "count": count, "error": "", "method": "html+llm"}
            else:
                return {"school": name, "ok": True, "count": 0, "error": "No events parsed from HTML", "method": "html+llm"}

        except requests.exceptions.RequestException as exc:
            return {"school": name, "ok": False, "count": 0, "error": f"HTTP: {exc}", "method": "html"}
        except Exception as exc:
            return {"school": name, "ok": False, "count": 0, "error": str(exc), "method": "html"}


# ── CLI 入口 ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="仅运行种子数据预填充")
    parser.add_argument("--seed-overwrite", action="store_true", help="强制覆盖已有种子数据")
    parser.add_argument("--scrape", action="store_true", help="仅运行在线爬取")
    args = parser.parse_args()

    if args.seed or args.seed_overwrite:
        print("正在预填充种子数据...")
        seed_results = seed_known_calendars(overwrite=args.seed_overwrite)
        total = sum(seed_results.values())
        print(f"种子数据写入完成：{total} 条，{len([v for v in seed_results.values() if v > 0])} 所学校")
        for school, cnt in seed_results.items():
            if cnt > 0:
                print(f"  ✓ {school}: {cnt} 条")

    if args.scrape or (not args.seed and not args.seed_overwrite):
        if not args.scrape:
            print("\n同时运行在线爬取...")
        scraper = SchoolCalendarScraper()
        results = scraper.run()
        ok_count = sum(1 for r in results if r["ok"] and r["count"] > 0)
        total_events = sum(r["count"] for r in results)
        print(f"\n=== 在线爬取完成 ===")
        print(f"有效数据: {ok_count}/{len(results)} 所学校")
        print(f"写入事件总数: {total_events}")
        for r in results:
            status = "✓" if (r["ok"] and r["count"] > 0) else ("~" if r["ok"] else "✗")
            print(f"  {status} {r['school']}: {r['count']} 条 [{r.get('method','')}] {r.get('error', '')}")
