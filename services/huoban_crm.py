"""
伙伴云 CRM 同步服务

同步方向：伙伴云 → 本地 SQLite
同步内容：
  - 客户信息 → leads（线索）
  - 订单     → orders（订单）
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── 伙伴云连接配置 ─────────────────────────────────────────────
HUOBAN_BASE  = "https://api.huoban.com"
HUOBAN_KEY   = os.environ.get("HUOBAN_API_KEY", "")
SPACE_ID     = "4000000007072757"   # 九宙SCRM

# ── 表 ID ────────────────────────────────────────────────────
TABLE_CUSTOMER  = "2100000052578962"   # 客户信息  (6697条)
TABLE_ORDER     = "2100000052585140"   # 订单      (14071条)
TABLE_FOLLOWUP  = "2100000052581248"   # 客户跟进

# ── 客户信息字段映射 ──────────────────────────────────────────
# field_id → 本地字段名
CUSTOMER_FIELD_MAP = {
    "2200000439320003": "name_prefix",      # 客户前缀 (如 YYZ)
    "2200000439336782": "customer_no",      # 客户编号 (如 K0008)
    "2200000439328103": "customer_grade",   # 客户等级 (A/B/C/D)
    "2200000439328960": "deal_status_raw",  # 客户状态 (已成交/跟进中/...)
    "2200000439330603": "country",          # 国家
    "2200000439327529": "school",           # 院校
    "2200000443868706": "major",            # 专业
    "2200000439327531": "grade",            # 学历年级
    "2200000439327532": "inquiry_date",     # 首次咨询时间
    "2200000458571341": "estimated_amount", # 预估金额
    "2200000439328163": "source_channel_raw", # 来源渠道
}

# 客户状态 → deal_status
DEAL_STATUS_MAP = {
    "已成交": "completed",
    "跟进中": "follow_up",
    "新客户": "new",
    "意向客户": "contacted",
    "报价中": "quoted",
    "流失": "lost",
    "无效": "invalid",
}

# ── 订单字段映射 ──────────────────────────────────────────────
ORDER_FIELD_MAP = {
    "2200000441163869": "order_no",          # 订单号
    "2200000441216481": "customer_ref",      # 关联客户
    "2200000441216482": "customer_type",     # 新/老客户
    "2200000439492428": "sales_person",      # 顾问/销售
    "2200000441216485": "order_date",        # 下单日期
    "2200000440508484": "status_raw",        # 订单状态
    "2200000439396420": "product_type",      # 作业类型
    "2200000439393503": "amount",            # 金额
    "2200000440776754": "actual_received",   # 实收金额
    "2200000441163617": "settlement_status", # 结算状态
    "2200000441163618": "delivery_status",   # 交稿状态
    "2200000441163620": "delivery_time",     # 交稿时间
    "2200000441216489": "teacher_fee",       # 稿费
    "2200000441163624": "deadline",          # 截止日期
}

# 订单状态 → status
ORDER_STATUS_MAP = {
    "订单完结": "completed",
    "进行中":   "in_progress",
    "待派单":   "pending",
    "已取消":   "cancelled",
    "退单":     "refunded",
}


# ── HTTP 工具 ─────────────────────────────────────────────────
def _headers():
    return {
        "Open-Authorization": f"Bearer {HUOBAN_KEY}",
        "Content-Type": "application/json",
    }


def _post(path: str, body: dict, timeout: int = 15) -> dict:
    r = requests.post(HUOBAN_BASE + path, headers=_headers(), json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("code", 0) not in (0, 200):
        raise ValueError(f"伙伴云API错误: {data.get('message')} code={data.get('code')}")
    return data


def _extract(field_val, key="name") -> Optional[str]:
    """从伙伴云关联字段/选项字段提取文本值"""
    if field_val is None:
        return None
    if isinstance(field_val, list):
        if not field_val:
            return None
        first = field_val[0]
        return first.get("title") or first.get(key) or first.get("name")
    if isinstance(field_val, dict):
        return field_val.get("title") or field_val.get(key) or field_val.get("name")
    return str(field_val) if field_val else None


# ── 拉取数据（自动分页）──────────────────────────────────────
def fetch_all_items(table_id: str, updated_after: Optional[datetime] = None,
                    limit_per_page: int = 100) -> list:
    """
    拉取指定表的所有条目（自动翻页）。
    updated_after: 只拉取该时间之后更新的记录（增量同步用）
    """
    items = []
    offset = 0
    body_base: dict = {"table_id": table_id, "limit": limit_per_page}

    # 伙伴云支持按创建/更新时间过滤
    if updated_after:
        body_base["filters"] = [{
            "field_id": "created_at",  # 或 updated_at，按实际字段
            "type": "gte",
            "value": updated_after.strftime("%Y-%m-%d %H:%M:%S"),
        }]

    while True:
        body = {**body_base, "offset": offset}
        try:
            resp = _post("/openapi/v1/item/list", body)
        except Exception as e:
            logger.error(f"[HuobanCRM] fetch_all_items table={table_id} offset={offset} err={e}")
            break

        data = resp.get("data", {})
        if isinstance(data, list):
            batch = data
            has_more = False
        else:
            batch    = data.get("items") or []
            has_more = data.get("has_more", False)
        items.extend(batch)
        if not has_more or len(batch) == 0:
            break
        offset += len(batch)

    logger.info(f"[HuobanCRM] fetched {len(items)} items from table={table_id}")
    return items


# ── 转换：客户信息 → lead dict ────────────────────────────────
def parse_customer(item: dict) -> dict:
    f = item.get("fields", {})

    prefix    = f.get("2200000439320003") or ""
    cust_no   = f.get("2200000439336782") or ""
    full_name = f"{prefix}{cust_no}".strip() or item.get("title", "")

    status_raw = _extract(f.get("2200000439328960")) or ""
    deal_status = DEAL_STATUS_MAP.get(status_raw, "follow_up")

    country = _extract(f.get("2200000439330603"))
    if country:
        # 去掉括号里的英文
        country = country.split("（")[0].split("(")[0].strip()

    source_raw = _extract(f.get("2200000439328163"))
    # 简单映射渠道
    source_channel = "unknown"
    if source_raw:
        if "小红书" in source_raw:
            source_channel = "xiaohongshu"
        elif "朋友圈" in source_raw:
            source_channel = "moments"
        elif "转介绍" in source_raw or "代理" in source_raw:
            source_channel = "referral"
        elif "老客户" in source_raw or "复购" in source_raw:
            source_channel = "old_customer"
        elif "社群" in source_raw or "群" in source_raw:
            source_channel = "community"
        elif "推广" in source_raw or "投放" in source_raw:
            source_channel = "promotion"
        elif "垂直" in source_raw or "学生号" in source_raw:
            source_channel = "vertical_account"

    inquiry_date = f.get("2200000439327532")
    if inquiry_date and isinstance(inquiry_date, str):
        inquiry_date = inquiry_date[:10]  # 只取日期部分

    return {
        "external_id":          item.get("item_id"),
        "external_source":      "huoban_crm",
        "name":                 full_name,
        "student_name":         item.get("title", full_name),
        "school":               _extract(f.get("2200000439327529")),
        "major":                _extract(f.get("2200000443868706")),
        "country":              country,
        "grade":                _extract(f.get("2200000439327531")),
        "deal_status":          deal_status,
        "lead_source_channel":  source_channel,
        "inquiry_date":         inquiry_date,
        "estimated_amount":     f.get("2200000458571341"),
        "customer_grade":       _extract(f.get("2200000439328103")),
        "raw_status":           status_raw,
    }


# ── 转换：订单 → order dict ───────────────────────────────────
def parse_order(item: dict) -> dict:
    f = item.get("fields", {})

    status_raw  = _extract(f.get("2200000440508484")) or ""
    status      = ORDER_STATUS_MAP.get(status_raw, "in_progress")

    customer_ref = f.get("2200000441216481")
    customer_name = _extract(customer_ref)

    sales_person_raw = f.get("2200000439492428")
    sales_owner = _extract(sales_person_raw)
    if sales_owner and "  " in sales_owner:
        # 格式 "付蕊蕊  660" → 去掉编号
        sales_owner = sales_owner.split("  ")[0].strip()

    order_date = f.get("2200000441216485")
    if order_date and isinstance(order_date, str):
        order_date = order_date[:10]

    delivery_time = f.get("2200000441163620")
    if delivery_time and isinstance(delivery_time, str):
        delivery_time = delivery_time[:10]

    return {
        "external_id":       item.get("item_id"),
        "external_source":   "huoban_crm",
        "order_no":          f.get("2200000441163869"),
        "customer_name":     customer_name,
        "sales_owner":       sales_owner,
        "order_date":        order_date,
        "status":            status,
        "product":           _extract(f.get("2200000439396420")),
        "amount":            f.get("2200000439393503"),
        "actual_received":   f.get("2200000440776754"),
        "teacher_fee":       f.get("2200000441216489"),
        "delivery_time":     delivery_time,
        "is_new_customer":   (_extract(f.get("2200000441216482")) == "新客户"),
        "raw_status":        status_raw,
    }


# ── 主同步函数 ─────────────────────────────────────────────────
def sync_to_local(days_lookback: int = 1, full_sync: bool = False) -> dict:
    """
    同步伙伴云数据到本地 DB。
    days_lookback: 增量同步拉最近N天（默认1天，cron用）
    full_sync: True时全量同步（首次运行用）
    返回 {leads_synced, orders_synced, errors}
    """
    from database import upsert_lead_from_crm, upsert_order_from_crm

    updated_after = None if full_sync else (
        datetime.now() - timedelta(days=days_lookback)
    )

    results = {"leads_synced": 0, "orders_synced": 0, "errors": []}

    # 1. 同步客户信息 → leads
    try:
        customers = fetch_all_items(TABLE_CUSTOMER, updated_after=updated_after)
        for item in customers:
            try:
                lead = parse_customer(item)
                upsert_lead_from_crm({
                    "crm_id":         lead["external_id"],
                    "crm_source":     "huoban",
                    "name":           lead["name"],
                    "student_name":   lead["student_name"],
                    "school":         lead.get("school"),
                    "major":          lead.get("major"),
                    "country":        lead.get("country"),
                    "grade":          lead.get("grade"),
                    "deal_status":    lead["deal_status"],
                    "source_channel": lead["lead_source_channel"],
                    "inquiry_date":   lead.get("inquiry_date"),
                    "amount":         lead.get("estimated_amount"),
                    "sales_owner":    None,
                })
                results["leads_synced"] += 1
            except Exception as e:
                results["errors"].append(f"lead {item.get('item_id')}: {e}")
        logger.info(f"[HuobanCRM] leads synced: {results['leads_synced']}")
    except Exception as e:
        results["errors"].append(f"客户信息同步失败: {e}")
        logger.error(f"[HuobanCRM] customer sync error: {e}")

    # 2. 同步订单
    try:
        orders = fetch_all_items(TABLE_ORDER, updated_after=updated_after)
        for item in orders:
            try:
                order = parse_order(item)
                upsert_order_from_crm({
                    "crm_id":        order["external_id"],
                    "crm_source":    "huoban",
                    "customer_name": order.get("customer_name"),
                    "product":       order.get("product"),
                    "amount":        order.get("amount"),
                    "sales_owner":   order.get("sales_owner"),
                    "status":        order["status"],
                    "order_date":    order.get("order_date"),
                })
                results["orders_synced"] += 1
            except Exception as e:
                results["errors"].append(f"order {item.get('item_id')}: {e}")
        logger.info(f"[HuobanCRM] orders synced: {results['orders_synced']}")
    except Exception as e:
        results["errors"].append(f"订单同步失败: {e}")
        logger.error(f"[HuobanCRM] order sync error: {e}")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("测试拉取客户信息（前5条）...")
    items = fetch_all_items(TABLE_CUSTOMER)
    for item in items[:5]:
        lead = parse_customer(item)
        print(lead)
    print("\n测试拉取订单（前5条）...")
    items = fetch_all_items(TABLE_ORDER)
    for item in items[:5]:
        order = parse_order(item)
        print(order)
