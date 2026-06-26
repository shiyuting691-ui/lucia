"""测试伙伴云解析 — 拉5条客户和5条订单，打印解析结果"""
import sys, os, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")

from services.huoban_crm import (
    fetch_all_items, parse_customer, parse_order,
    TABLE_CUSTOMER, TABLE_ORDER
)

print("=== 客户信息（前5条解析）===")
customers = fetch_all_items(TABLE_CUSTOMER)
print(f"客户总数: {len(customers)}")
for item in customers[:5]:
    lead = parse_customer(item)
    print(f"  name={lead['name']}  school={lead['school']}  country={lead['country']}"
          f"  status={lead['deal_status']}  channel={lead['lead_source_channel']}"
          f"  date={lead['inquiry_date']}")

print("\n=== 订单（前5条解析）===")
orders = fetch_all_items(TABLE_ORDER)
print(f"订单总数: {len(orders)}")
for item in orders[:5]:
    order = parse_order(item)
    print(f"  order_no={order['order_no']}  customer={order['customer_name']}"
          f"  sales={order['sales_owner']}  amount={order['amount']}"
          f"  status={order['status']}  product={order['product']}")
