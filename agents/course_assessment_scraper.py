"""
Course Assessment Scraper
爬取热门专业的作业DDL、考试时间、课程大纲。
目标：中国留学生最多的专业（商科/CS/工程/法律/心理等）

数据策略：
  1. Monash Unit Guide（静态HTML，可直接requests抓取）
  2. UNSW Course Outline（部分公开）
  3. UQ Course Profile（部分公开）
  4. 模式推断种子数据（按学期周次推算典型DDL）
"""

import json
import logging
import re
import sys
import os
from datetime import datetime, date, timedelta
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.crud import save_course_assessment, delete_course_assessments, migrate_course_assessments
from services.llm import LLMRouter

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}

# ── 热门课程目标表 ──────────────────────────────────────────────────────
# 中国留学生占比高的专业课程，按校爬取
TARGET_COURSES = [
    # ── UNSW ──────────────────────────────────────────────────────────
    # 商科
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT1501", "subject_name": "Accounting & Financial Management",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/ACCT1501"]},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "FINS1612", "subject_name": "Capital Markets and Institutions",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/FINS1612"]},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "ECON1101", "subject_name": "Microeconomics 1",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/ECON1101"]},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "MGMT1001", "subject_name": "Managing Organisations and People",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/MGMT1001"]},
    # CS
    {"school": "新南威尔士大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP1511", "subject_name": "Programming Fundamentals",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/COMP1511"]},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP2521", "subject_name": "Data Structures and Algorithms",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/COMP2521"]},
    # 心理
    {"school": "新南威尔士大学", "country": "AU", "major_category": "心理",
     "subject_code": "PSYC1001", "subject_name": "Psychology 1A",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/PSYC1001"]},
    # 法律
    {"school": "新南威尔士大学", "country": "AU", "major_category": "法律",
     "subject_code": "LAWS1052", "subject_name": "Foundations of Law",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "unsw_handbook",
     "urls": ["https://www.handbook.unsw.edu.au/undergraduate/courses/2025/LAWS1052"]},

    # ── Monash ─────────────────────────────────────────────────────────
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "ACC1100", "subject_name": "Introduction to Financial Accounting",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "monash_unitguide",
     "urls": ["https://unitguidemanager.monash.edu/view?unitCode=ACC1100&year=2025&mode=S1-01-ON"]},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "FIN2101", "subject_name": "Business Finance",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "monash_unitguide",
     "urls": ["https://unitguidemanager.monash.edu/view?unitCode=FIN2101&year=2025&mode=S1-01-ON"]},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "ECF1100", "subject_name": "Business Economics",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "monash_unitguide",
     "urls": ["https://unitguidemanager.monash.edu/view?unitCode=ECF1100&year=2025&mode=S1-01-ON"]},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "CS/IT",
     "subject_code": "FIT1045", "subject_name": "Introduction to Programming",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "monash_unitguide",
     "urls": ["https://unitguidemanager.monash.edu/view?unitCode=FIT1045&year=2025&mode=S1-01-ON"]},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "MKT1120", "subject_name": "Marketing Theory and Practice",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "monash_unitguide",
     "urls": ["https://unitguidemanager.monash.edu/view?unitCode=MKT1120&year=2025&mode=S1-01-ON"]},

    # ── UQ ─────────────────────────────────────────────────────────────
    {"school": "昆士兰大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT1101", "subject_name": "Accounting for Decision Making",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "uq_profile",
     "urls": ["https://my.uq.edu.au/programs-courses/course.html?course_code=ACCT1101"]},
    {"school": "昆士兰大学", "country": "AU", "major_category": "商科",
     "subject_code": "ECON1010", "subject_name": "Introduction to Economics 1",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "uq_profile",
     "urls": ["https://my.uq.edu.au/programs-courses/course.html?course_code=ECON1010"]},
    {"school": "昆士兰大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "CSSE1001", "subject_name": "Introduction to Software Engineering",
     "semester": "Semester 1", "academic_year": "2025",
     "type": "uq_profile",
     "urls": ["https://my.uq.edu.au/programs-courses/course.html?course_code=CSSE1001"]},
]

# ── 模式推断种子数据（按学期第N周推算典型DDL）─────────────────────────────
# 澳洲Semester 1 2025: 教学开始 2025-02-24，共13周
# 典型作业安排: Ass1=Week5, Ass2=Week9, Final=Week13考试周

_AU_S1_2025_START = date(2025, 2, 24)   # 澳洲S1 2025 教学开始
_AU_S2_2025_START = date(2025, 7, 21)   # 澳洲S2 2025 教学开始
_UK_AUT_2025_START = date(2025, 9, 22)  # 英国秋季学期

def _week_date(semester_start: date, week: int, weekday: int = 4) -> str:
    """计算第N周周五（weekday=4）的日期，返回 YYYY-MM-DD。"""
    d = semester_start + timedelta(weeks=week - 1, days=weekday)
    return d.strftime("%Y-%m-%d")


# 热门课程的典型考核模式（按专业类别，适用于大多数澳洲大学）
_ASSESSMENT_PATTERNS = {
    "商科_AU_S1": [
        {"assessment_type": "assignment", "assessment_name": "Assignment 1（个人报告/分析）",
         "due_week": "Week 5", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 5)},
        {"assessment_type": "quiz", "assessment_name": "Mid-semester Quiz",
         "due_week": "Week 7", "weight_pct": 15.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 7)},
        {"assessment_type": "assignment", "assessment_name": "Assignment 2（小组报告）",
         "due_week": "Week 10", "weight_pct": 25.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 10)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-06-09"},  # S1考试期约6月初
    ],
    "CS/IT_AU_S1": [
        {"assessment_type": "assignment", "assessment_name": "Lab Assignment 1",
         "due_week": "Week 4", "weight_pct": 15.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 4)},
        {"assessment_type": "assignment", "assessment_name": "Lab Assignment 2",
         "due_week": "Week 8", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 8)},
        {"assessment_type": "assignment", "assessment_name": "Major Project",
         "due_week": "Week 12", "weight_pct": 25.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 12)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-06-11"},
    ],
    "法律_AU_S1": [
        {"assessment_type": "assignment", "assessment_name": "Legal Research Essay",
         "due_week": "Week 6", "weight_pct": 30.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 6)},
        {"assessment_type": "assignment", "assessment_name": "Case Analysis",
         "due_week": "Week 10", "weight_pct": 30.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 10)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-06-12"},
    ],
    "心理_AU_S1": [
        {"assessment_type": "assignment", "assessment_name": "Research Report 1",
         "due_week": "Week 5", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 5)},
        {"assessment_type": "quiz", "assessment_name": "Online Quizzes（共4次）",
         "due_week": "Week 3-11", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 3)},
        {"assessment_type": "assignment", "assessment_name": "Research Report 2",
         "due_week": "Week 10", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S1_2025_START, 10)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-06-10"},
    ],
    "商科_AU_S2": [
        {"assessment_type": "assignment", "assessment_name": "Assignment 1（个人报告/分析）",
         "due_week": "Week 5", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 5)},
        {"assessment_type": "quiz", "assessment_name": "Mid-semester Quiz",
         "due_week": "Week 7", "weight_pct": 15.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 7)},
        {"assessment_type": "assignment", "assessment_name": "Assignment 2（小组报告）",
         "due_week": "Week 10", "weight_pct": 25.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 10)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-11-05"},
    ],
    "CS/IT_AU_S2": [
        {"assessment_type": "assignment", "assessment_name": "Lab Assignment 1",
         "due_week": "Week 4", "weight_pct": 15.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 4)},
        {"assessment_type": "assignment", "assessment_name": "Lab Assignment 2",
         "due_week": "Week 8", "weight_pct": 20.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 8)},
        {"assessment_type": "assignment", "assessment_name": "Major Project",
         "due_week": "Week 12", "weight_pct": 25.0,
         "due_date_fn": lambda: _week_date(_AU_S2_2025_START, 12)},
        {"assessment_type": "exam", "assessment_name": "Final Exam",
         "due_week": "Exam Period", "weight_pct": 40.0,
         "due_date_fn": lambda: "2025-11-07"},
    ],
    # 英国商科（以秋季学期为主，1月考）
    "商科_UK_AUT": [
        {"assessment_type": "assignment", "assessment_name": "Essay / Coursework 1",
         "due_week": "Week 6", "weight_pct": 30.0,
         "due_date_fn": lambda: _week_date(_UK_AUT_2025_START, 6)},
        {"assessment_type": "assignment", "assessment_name": "Group Project",
         "due_week": "Week 10", "weight_pct": 30.0,
         "due_date_fn": lambda: _week_date(_UK_AUT_2025_START, 10)},
        {"assessment_type": "exam", "assessment_name": "January Exam",
         "due_week": "Week 15（1月考试周）", "weight_pct": 40.0,
         "due_date_fn": lambda: "2026-01-12"},
    ],
    "CS/IT_UK_AUT": [
        {"assessment_type": "assignment", "assessment_name": "Coursework 1（代码/报告）",
         "due_week": "Week 5", "weight_pct": 25.0,
         "due_date_fn": lambda: _week_date(_UK_AUT_2025_START, 5)},
        {"assessment_type": "assignment", "assessment_name": "Coursework 2（项目）",
         "due_week": "Week 11", "weight_pct": 35.0,
         "due_date_fn": lambda: _week_date(_UK_AUT_2025_START, 11)},
        {"assessment_type": "exam", "assessment_name": "January Exam",
         "due_week": "Week 15（1月考试周）", "weight_pct": 40.0,
         "due_date_fn": lambda: "2026-01-13"},
    ],
}

# 各学校各专业→使用哪个模板（S1/S2/AUT分开）
_SCHOOL_MAJOR_SEED = [
    # 澳洲S1 商科
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT1501", "subject_name": "Accounting & Financial Management",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "FINS1612", "subject_name": "Capital Markets",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "ECON1101", "subject_name": "Microeconomics 1",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP1511", "subject_name": "Programming Fundamentals",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP2521", "subject_name": "Data Structures & Algorithms",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "法律",
     "subject_code": "LAWS1052", "subject_name": "Foundations of Law",
     "semester": "Semester 1", "pattern_key": "法律_AU_S1"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "心理",
     "subject_code": "PSYC1001", "subject_name": "Psychology 1A",
     "semester": "Semester 1", "pattern_key": "心理_AU_S1"},
    # Monash S1
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "ACC1100", "subject_name": "Introduction to Financial Accounting",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "FIN2101", "subject_name": "Business Finance",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "CS/IT",
     "subject_code": "FIT1045", "subject_name": "Introduction to Programming",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    # UQ S1
    {"school": "昆士兰大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT1101", "subject_name": "Accounting for Decision Making",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "昆士兰大学", "country": "AU", "major_category": "商科",
     "subject_code": "ECON1010", "subject_name": "Introduction to Economics 1",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "昆士兰大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "CSSE1001", "subject_name": "Intro to Software Engineering",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    # 悉尼S1
    {"school": "悉尼大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT1001", "subject_name": "Accounting for Business Decisions",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "悉尼大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "INFO1110", "subject_name": "Introduction to Programming",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    {"school": "悉尼大学", "country": "AU", "major_category": "法律",
     "subject_code": "LAWS1001", "subject_name": "Foundations of Law",
     "semester": "Semester 1", "pattern_key": "法律_AU_S1"},
    # 墨尔本S1
    {"school": "墨尔本大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT10001", "subject_name": "Accounting Reports and Analysis",
     "semester": "Semester 1", "pattern_key": "商科_AU_S1"},
    {"school": "墨尔本大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP10001", "subject_name": "Foundations of Computing",
     "semester": "Semester 1", "pattern_key": "CS/IT_AU_S1"},
    # 澳洲S2（下半年）
    {"school": "新南威尔士大学", "country": "AU", "major_category": "商科",
     "subject_code": "ACCT2011", "subject_name": "Financial Accounting",
     "semester": "Semester 2", "pattern_key": "商科_AU_S2"},
    {"school": "新南威尔士大学", "country": "AU", "major_category": "CS/IT",
     "subject_code": "COMP1531", "subject_name": "Software Engineering Fundamentals",
     "semester": "Semester 2", "pattern_key": "CS/IT_AU_S2"},
    {"school": "莫纳什大学Monash", "country": "AU", "major_category": "商科",
     "subject_code": "ACC2100", "subject_name": "Financial Accounting and Reporting",
     "semester": "Semester 2", "pattern_key": "商科_AU_S2"},
    # 英国秋季
    {"school": "伦敦大学学院UCL", "country": "UK", "major_category": "商科",
     "subject_code": "ECON0001", "subject_name": "Quantitative Economics",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
    {"school": "伦敦大学学院UCL", "country": "UK", "major_category": "CS/IT",
     "subject_code": "COMP0002", "subject_name": "Principles of Programming",
     "semester": "Autumn Term", "pattern_key": "CS/IT_UK_AUT"},
    {"school": "曼彻斯特大学", "country": "UK", "major_category": "商科",
     "subject_code": "BMAN10001", "subject_name": "Accounting for Decision-Making",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
    {"school": "曼彻斯特大学", "country": "UK", "major_category": "CS/IT",
     "subject_code": "COMP10120", "subject_name": "Introduction to Programming",
     "semester": "Autumn Term", "pattern_key": "CS/IT_UK_AUT"},
    {"school": "利兹大学", "country": "UK", "major_category": "商科",
     "subject_code": "LUBS1025", "subject_name": "Accounting 1",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
    {"school": "谢菲尔德大学", "country": "UK", "major_category": "商科",
     "subject_code": "MAN104", "subject_name": "Accounting & Financial Analysis",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
    {"school": "伯明翰大学", "country": "UK", "major_category": "商科",
     "subject_code": "07 26440", "subject_name": "Financial Reporting",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
    {"school": "伦敦国王学院KCL", "country": "UK", "major_category": "商科",
     "subject_code": "4AABC100", "subject_name": "Introduction to Accounting",
     "semester": "Autumn Term", "pattern_key": "商科_UK_AUT"},
]


# ── 页面获取 + LLM解析 ────────────────────────────────────────────────

def _fetch_text(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n", strip=True).splitlines() if ln.strip()]
    return "\n".join(lines)[:10000]


def _build_assessment_prompt(school: str, subject_code: str, subject_name: str,
                              semester: str, page_text: str) -> str:
    return f"""You are an academic assessment parser for a student services company.

Extract ALL assessment tasks from this course outline/unit guide.

Course: {subject_code} {subject_name}
School: {school}
Semester: {semester}

Return ONLY a JSON array with this exact format:
[
  {{
    "assessment_type": "assignment",
    "assessment_name": "Assignment 1",
    "due_date": "2025-04-11",
    "due_week": "Week 7",
    "weight_pct": 20.0,
    "notes": "Individual report, 1500 words"
  }},
  {{
    "assessment_type": "exam",
    "assessment_name": "Final Examination",
    "due_date": "2025-06-10",
    "due_week": "Exam Period",
    "weight_pct": 50.0,
    "notes": "2 hours, open book"
  }}
]

assessment_type must be one of: exam / assignment / quiz / project / presentation
due_date: YYYY-MM-DD format. If exact date not given, estimate from week number assuming Semester 1 starts 2025-02-24.
weight_pct: percentage as number (e.g. 30.0 for 30%)
Return [] if no assessment data found.

Page content:
{page_text}"""


def _parse_json_response(raw: str) -> list:
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


# ── 种子数据预填充 ──────────────────────────────────────────────────────

def seed_assessment_patterns(overwrite: bool = False) -> dict:
    """
    按学期模式预填充热门课程的典型考核安排。
    source='模式推断', confidence='medium'
    """
    results = {}
    for entry in _SCHOOL_MAJOR_SEED:
        school = entry["school"]
        country = entry["country"]
        major_cat = entry["major_category"]
        subj_code = entry["subject_code"]
        subj_name = entry["subject_name"]
        semester = entry["semester"]
        pattern_key = entry["pattern_key"]

        if pattern_key not in _ASSESSMENT_PATTERNS:
            logger.warning("No pattern for %s", pattern_key)
            continue

        pattern = _ASSESSMENT_PATTERNS[pattern_key]
        key_label = f"{school}_{subj_code}"

        # 不覆盖已有模式推断数据
        if not overwrite:
            from database.crud import list_course_assessments
            existing = list_course_assessments(school=school, major_category=major_cat)
            existing_codes = {r["subject_code"] for r in existing if r.get("source") == "模式推断"}
            if subj_code in existing_codes:
                results[key_label] = 0
                continue

        if overwrite:
            delete_course_assessments(school, subj_code, source="模式推断")

        count = 0
        for p in pattern:
            due_date = p["due_date_fn"]()
            save_course_assessment({
                "school": school,
                "country": country,
                "major_category": major_cat,
                "subject_code": subj_code,
                "subject_name": subj_name,
                "semester": semester,
                "academic_year": "2025-2026",
                "assessment_type": p["assessment_type"],
                "assessment_name": p["assessment_name"],
                "due_date": due_date,
                "due_week": p["due_week"],
                "weight_pct": p["weight_pct"],
                "notes": "",
                "source": "模式推断",
                "source_url": "",
                "confidence": "medium",
            })
            count += 1

        logger.info("Seed %s %s: %d assessments", school, subj_code, count)
        results[key_label] = count

    return results


# ── 在线爬取 ──────────────────────────────────────────────────────────

class CourseAssessmentScraper:
    def __init__(self, config=None):
        self.config = config or {}
        self.llm = LLMRouter()

    def run(self, courses: Optional[List[dict]] = None) -> list:
        targets = courses if courses is not None else TARGET_COURSES
        results = []
        for course in targets:
            try:
                result = self.scrape_one(course)
            except Exception as exc:
                result = {
                    "school": course.get("school", ""),
                    "subject_code": course.get("subject_code", ""),
                    "ok": False, "count": 0, "error": str(exc),
                }
            results.append(result)
            logger.info("Result: %s", result)
        return results

    def scrape_one(self, course: dict) -> dict:
        school = course["school"]
        country = course["country"]
        major_cat = course["major_category"]
        subj_code = course["subject_code"]
        subj_name = course["subject_name"]
        semester = course["semester"]
        urls = course.get("urls", [])

        last_err = ""
        for url in urls:
            try:
                page_text = _fetch_text(url)
                if len(page_text) < 200:
                    continue

                prompt = _build_assessment_prompt(school, subj_code, subj_name, semester, page_text)
                resp = self.llm.generate_text(prompt, max_tokens=1500)
                raw = (getattr(resp, "content", None) or getattr(resp, "text", None) or "")
                assessments = _parse_json_response(raw)

                if not assessments:
                    continue

                # 清除旧官方数据
                delete_course_assessments(school, subj_code, source="课程大纲")

                count = 0
                for a in assessments:
                    atype = a.get("assessment_type", "")
                    if atype not in ("exam", "assignment", "quiz", "project", "presentation"):
                        continue
                    save_course_assessment({
                        "school": school,
                        "country": country,
                        "major_category": major_cat,
                        "subject_code": subj_code,
                        "subject_name": subj_name,
                        "semester": semester,
                        "academic_year": "2025-2026",
                        "assessment_type": atype,
                        "assessment_name": a.get("assessment_name", ""),
                        "due_date": a.get("due_date") or None,
                        "due_week": a.get("due_week") or "",
                        "weight_pct": a.get("weight_pct") or None,
                        "notes": a.get("notes") or "",
                        "source": "课程大纲",
                        "source_url": url,
                        "confidence": "high",
                    })
                    count += 1

                return {"school": school, "subject_code": subj_code,
                        "ok": True, "count": count, "error": ""}

            except Exception as e:
                last_err = str(e)
                logger.debug("Failed %s %s: %s", school, url, e)

        return {"school": school, "subject_code": subj_code,
                "ok": False, "count": 0, "error": last_err or "All URLs failed"}


# ── CLI ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="预填充模式推断数据")
    parser.add_argument("--seed-overwrite", action="store_true", help="强制覆盖种子数据")
    parser.add_argument("--scrape", action="store_true", help="在线爬取课程大纲")
    parser.add_argument("--migrate", action="store_true", help="建表")
    args = parser.parse_args()

    if args.migrate:
        migrate_course_assessments()
        print("建表完成")

    if args.seed or args.seed_overwrite:
        print("预填充考核模式数据...")
        res = seed_assessment_patterns(overwrite=args.seed_overwrite)
        total = sum(res.values())
        filled = len([v for v in res.values() if v > 0])
        print(f"完成：{total} 条考核记录，{filled} 门课程")

    if args.scrape or (not args.seed and not args.seed_overwrite and not args.migrate):
        print("在线爬取课程大纲...")
        scraper = CourseAssessmentScraper()
        results = scraper.run()
        ok = sum(1 for r in results if r["ok"] and r["count"] > 0)
        total = sum(r["count"] for r in results)
        print(f"\n=== 完成：{ok}/{len(results)} 门课，{total} 条记录 ===")
        for r in results:
            icon = "✓" if (r["ok"] and r["count"] > 0) else ("~" if r["ok"] else "✗")
            print(f"  {icon} {r['school']} {r['subject_code']}: {r['count']} 条 {r.get('error','')}")
