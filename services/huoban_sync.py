"""
伙伴云 → 极致增长系统 数据同步服务

同步方向：单向只读（CRM → 本地数据库）
同步内容：
  1. 客户信息 → leads（线索/客户）
  2. 订单     → orders（成交订单）

表 ID（九宙SCRM 空间 4000000007072757）：
  客户信息: 2100000052578962
  订单:     2100000052585140
  客户跟进: 2100000052581248
"""

import os
import sys
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 确保项目根目录在 path 里
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

HUOBAN_BASE   = "https://api.huoban.com"
HUOBAN_KEY    = os.environ.get("HUOBAN_API_KEY", "")

TABLE_CUSTOMER = "2100000052578962"  # 客户信息
TABLE_ORDER    = "2100000052585140"  # 订单
TABLE_FOLLOWUP = "2100000052581248"  # 客户跟进

# ── 字段 ID 映射（客户信息）──────────────────────────────────────────
F_CUST = {
    "name":         "2200000439320003",   # 编号前缀
    "code":         "2200000439336782",   # 客户编号
    "grade":        "2200000439328103",   # 客户等级
    "status":       "2200000439328960",   # 状态（已成交/跟进中…）
    "country":      "2200000439330603",   # 国家（关联）
    "school":       "2200000439327529",   # 学校（关联）
    "major":        "2200000439320008",   # 专业（文本）
    "academic_year":"2200000439327531",   # 年级（关联）
    "first_contact":"2200000439327532",   # 首次咨询时间
    "total_spend":  "2200000458571341",   # 消费总额
    "owner":        "2200000448270163",   # 负责人（user）
    "source":       "2200000439327528",   # 来源（关联 客户来源）
    "spend_range":  "2200000511241321",   # 消费区间
}

# ── 字段 ID 映射（订单）──────────────────────────────────────────────
F_ORDER = {
    "order_no":     "2200000441163869",   # 订单编号
    "customer":     "2200000441216481",   # 关联客户
    "new_old":      "2200000441216482",   # 新老客户
    "order_date":   "2200000441216485",   # 下单日期
    "status":       "2200000440508484",   # 订单状态
    "product":      "2200000440003524",   # 课程名称（文本）
    "product_rel":  "2200000439396420",   # 作业类型（关联）
    "word_count":   "2200000439569094",   # 词数
    "unit_price":   "2200000439393503",   # 单价
    "actual_amount":"2200000440776754",   # 实收金额
    "consultant":   "2200000439492428",   # 顾问（关联）
    "major":        "2200000440712244",   # 专业（文本）
    "teacher":      "2200000439394071",   # 老师（关联）
    "created_at":   "2200000441170872",   # 创建时间
    # 客户关联字段（订单API响应中通过关联展开）
    "country":      "1172001134000000",   # 国家（来自客户表）
    "school":       "1172001118000000",   # 学校（来自客户表）
}

# 客户状态 → deal_status
STATUS_MAP = {
    "新线索":   "new",
    "已联系":   "contacted",
    "跟进中":   "follow_up",
    "已报价":   "quoted",
    "已成交":   "completed",
    "已流失":   "lost",
    "无效":     "lost",
}

# 订单状态 → order status
ORDER_STATUS_MAP = {
    "待派单":   "pending",
    "派单中":   "in_progress",
    "已派单":   "in_progress",
    "交稿中":   "in_progress",
    "质检中":   "in_progress",
    "订单完结": "completed",
    "已退款":   "refunded",
    "已取消":   "cancelled",
}


# ── HTTP 工具 ─────────────────────────────────────────────────────────

def _headers():
    return {
        "Open-Authorization": f"Bearer {HUOBAN_KEY}",
        "Content-Type": "application/json",
    }


def _post(path: str, body: dict) -> dict:
    r = requests.post(
        f"{HUOBAN_BASE}{path}",
        headers=_headers(),
        json=body,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _iter_items(table_id: str, filters: Optional[list] = None,
                updated_after: Optional[str] = None, page_size: int = 100):
    """分页拉取表格条目，支持时间过滤"""
    offset = 0
    body: dict = {"table_id": table_id, "offset": offset, "limit": page_size}

    if filters:
        body["filter"] = {"conjunction": "AND", "conditions": filters}

    # 伙伴云支持按更新时间过滤
    if updated_after:
        cond = {
            "field_id": "updated_on",
            "operator": "gte",
            "value": updated_after,
        }
        if "filter" in body:
            body["filter"]["conditions"].append(cond)
        else:
            body["filter"] = {"conjunction": "AND", "conditions": [cond]}

    while True:
        body["offset"] = offset
        resp = _post("/openapi/v1/item/list", body)
        if resp.get("code") != 0:
            logger.error(f"Huoban API error: {resp.get('message')} ({resp.get('code')})")
            break
        items = resp.get("data", {}).get("items", [])
        if not items:
            break
        yield from items
        if len(items) < page_size:
            break
        offset += page_size


# ── 字段值提取工具 ───────────────────────────────────────────────────

def _txt(fields: dict, fid: str) -> str:
    v = fields.get(fid)
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    return ""


def _rel_title(fields: dict, fid: str) -> str:
    """关联字段取第一条 title"""
    v = fields.get(fid)
    if isinstance(v, list) and v:
        return v[0].get("title", "")
    return ""


def _choice(fields: dict, fid: str) -> str:
    """单选字段取 name"""
    v = fields.get(fid)
    if isinstance(v, list) and v:
        return v[0].get("name", "")
    return ""


def _user(fields: dict, fid: str) -> str:
    """用户字段取 name"""
    v = fields.get(fid)
    if isinstance(v, list) and v:
        return v[0].get("name", "")
    return ""


def _num(fields: dict, fid: str) -> float:
    v = fields.get(fid)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _date(fields: dict, fid: str) -> str:
    v = fields.get(fid)
    if isinstance(v, str) and v:
        return v[:10]   # 取 YYYY-MM-DD
    return ""


COUNTRY_MAP = {
    "英国": "UK", "英格兰": "UK", "苏格兰": "UK",
    "澳大利亚": "AU", "澳洲": "AU",
    "美国": "US",
    "加拿大": "CA",
    "新西兰": "NZ",
    "爱尔兰": "IE",
    "新加坡": "SG",
    "香港": "HK",
    "中国": "CN",
}

SERVICE_TYPE_MAP = {
    "Dissertation": "论文辅导",
    "Essay": "Essay辅导",
    "Assignment": "作业辅导",
    "Exam": "考试辅导",
    "Final Exam": "考试辅导",
    "一对一": "一对一辅导",
    "小班": "小班课",
    "年包": "年包服务",
    "保分": "保分服务",
    "DP": "DP辅导",
    "IB": "IB辅导",
}


def _map_country(name: str) -> str:
    for key, code in COUNTRY_MAP.items():
        if key in name:
            return code
    return name[:20] if name else ""


def _clean_school(raw: str) -> str:
    if not raw:
        return ""
    for sep in ["University", "university", "College", "college"]:
        idx = raw.find(sep)
        if idx > 0:
            return raw[:idx].strip()
    return raw.strip()[:100]


def _infer_service_type(product: str) -> str:
    if not product:
        return ""
    for key, val in SERVICE_TYPE_MAP.items():
        if key.lower() in product.lower():
            return val
    return product[:50]


# ── 数据转换 ─────────────────────────────────────────────────────────

def _item_to_lead(item: dict) -> dict:
    f = item.get("fields", {})
    raw_status = _choice(f, F_CUST["status"])
    deal_status = STATUS_MAP.get(raw_status, "new")

    # 学校名称：去掉括号中的英文部分，如 "杜伦大学University of Durham" → "杜伦大学"
    school_raw = _rel_title(f, F_CUST["school"])
    school = school_raw.split("University")[0].split("university")[0].strip() or school_raw

    return {
        "crm_id":          item.get("item_id", ""),
        "crm_source":      "huoban",
        "student_name":    item.get("title", ""),
        "name":            item.get("title", ""),   # leads 表用 name
        "school":          school,
        "country_region":  _rel_title(f, F_CUST["country"]).replace("（", "(").split("(")[0].strip(),
        "major":           _txt(f, F_CUST["major"]),
        "academic_year":   _rel_title(f, F_CUST["academic_year"]),
        "deal_status":     deal_status,
        "sales_owner":     _user(f, F_CUST["owner"]),
        "assigned_person": _user(f, F_CUST["owner"]),
        "inquiry_date":    _date(f, F_CUST["first_contact"]),
        "total_spend":     _num(f, F_CUST["total_spend"]),
        "crm_grade":       _choice(f, F_CUST["grade"]),
        "crm_status_raw":  raw_status,
        "crm_updated_at":  item.get("updated_on", ""),
    }


def _item_to_order(item: dict) -> dict:
    f = item.get("fields", {})
    raw_status = _choice(f, F_ORDER["status"])
    order_status = ORDER_STATUS_MAP.get(raw_status, "in_progress")
    is_completed = order_status == "completed"

    # 国家：提取括号前的中文，再映射为简短代码
    country_raw = _rel_title(f, F_ORDER["country"])
    country_raw = country_raw.replace("（", "(").split("(")[0].strip()
    country_code = _map_country(country_raw)

    # 学校：去掉括号中的英文部分
    school_raw = _rel_title(f, F_ORDER["school"])
    school = _clean_school(school_raw)

    product_text = _txt(f, F_ORDER["product"]) or _rel_title(f, F_ORDER["product_rel"])

    return {
        "crm_id":         item.get("item_id", ""),
        "crm_source":     "huoban",
        "order_no":       _txt(f, F_ORDER["order_no"]),
        "customer_name":  _rel_title(f, F_ORDER["customer"]),
        "product":        product_text,
        "major":          _txt(f, F_ORDER["major"]),
        "amount":         _num(f, F_ORDER["actual_amount"]),
        "unit_price":     _num(f, F_ORDER["unit_price"]),
        "word_count":     int(_num(f, F_ORDER["word_count"])),
        "order_date":     _date(f, F_ORDER["order_date"]),
        "status":         "completed" if is_completed else order_status,
        "is_new_customer":_choice(f, F_ORDER["new_old"]) == "新客户",
        "sales_owner":    _rel_title(f, F_ORDER["consultant"]),
        "country":        country_code,
        "school":         school,
        "service_type":   _infer_service_type(product_text),
        "crm_status_raw": raw_status,
        "crm_updated_at": item.get("updated_on", ""),
    }


# ── 主同步函数 ───────────────────────────────────────────────────────

def sync_leads(days_back: int = 7, full_sync: bool = False) -> dict:
    """
    从伙伴云同步客户信息到本地 leads 表。
    days_back: 只同步最近 N 天有更新的记录（full_sync=True 则全量）
    """
    from database import save_lead

    updated_after = None
    if not full_sync:
        dt = datetime.now() - timedelta(days=days_back)
        updated_after = dt.strftime("%Y-%m-%d %H:%M:%S")

    new_count = updated_count = error_count = 0

    from database.crud import upsert_lead_from_crm
    for item in _iter_items(TABLE_CUSTOMER, updated_after=updated_after):
        try:
            lead_data = _item_to_lead(item)
            if not lead_data["name"]:
                continue
            result = upsert_lead_from_crm(lead_data)
            if result == "created":
                new_count += 1
            else:
                updated_count += 1
        except Exception as e:
            logger.error(f"sync_leads: error on item {item.get('item_id')}: {e}")
            error_count += 1

    logger.info(f"[HuobanSync] leads: new={new_count} updated={updated_count} errors={error_count}")
    return {"new": new_count, "updated": updated_count, "errors": error_count}


def sync_orders(days_back: int = 7, full_sync: bool = False) -> dict:
    """
    从伙伴云同步订单到本地 orders 表。
    """
    from database import save_order

    updated_after = None
    if not full_sync:
        dt = datetime.now() - timedelta(days=days_back)
        updated_after = dt.strftime("%Y-%m-%d %H:%M:%S")

    new_count = updated_count = error_count = 0

    from database.crud import upsert_order_from_crm
    for item in _iter_items(TABLE_ORDER, updated_after=updated_after):
        try:
            order_data = _item_to_order(item)
            if not order_data["order_no"]:
                continue
            result = upsert_order_from_crm(order_data)
            if result == "created":
                new_count += 1
            else:
                updated_count += 1
        except Exception as e:
            logger.error(f"sync_orders: error on item {item.get('item_id')}: {e}")
            error_count += 1

    logger.info(f"[HuobanSync] orders: new={new_count} updated={updated_count} errors={error_count}")
    return {"new": new_count, "updated": updated_count, "errors": error_count}


def sync_all(days_back: int = 1, full_sync: bool = False) -> dict:
    """每日增量同步（默认只拉最近1天更新）"""
    leads_result  = sync_leads(days_back=days_back,  full_sync=full_sync)
    orders_result = sync_orders(days_back=days_back, full_sync=full_sync)
    return {
        "leads":  leads_result,
        "orders": orders_result,
        "synced_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print("=== 伙伴云全量同步测试 ===")
    result = sync_all(days_back=30, full_sync=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
