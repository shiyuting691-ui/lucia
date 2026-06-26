"""服务器端一次性归因验证脚本"""
import os, yaml, json, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///data/marketing.db")
sys.path.insert(0, "/opt/jizhi-growth-system")

from anthropic import Anthropic
from agents.channel_attribution_agent import ChannelAttributionAgent
from agents.role_execution_agent import RoleExecutionAgent

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

client = Anthropic()  # 使用环境变量 ANTHROPIC_API_KEY

print("=== 运行 ChannelAttributionAgent ===")
ch_agent = ChannelAttributionAgent(client, cfg)
ch_result = ch_agent.run(days_lookback=90)

print(f"分析区间: {ch_result['period']}")
print(f"渠道表现条数: {len(ch_result['channel_performance'])}")
for row in ch_result["channel_performance"]:
    print(f"  {row['channel_zh']}: 线索{row['leads_count']} 成交{row['deal_count']} 转化{row['conversion_rate']*100:.0f}%")

print(f"\n数据缺口 ({len(ch_result['missing_data'])} 项):")
for m in ch_result["missing_data"]:
    print(f"  ❌ {m['field']}: {m['impact']}")

print("\n洞察摘要:")
ins = ch_result.get("insights", {})
if isinstance(ins, dict):
    for k, v in ins.items():
        if v:
            print(f"  [{k}]")
            for item in (v if isinstance(v, list) else [v]):
                print(f"    - {item}")
else:
    print(f"  {ins}")

print("\n=== 运行 RoleExecutionAgent ===")
role_agent = RoleExecutionAgent(client, cfg)
role_result = role_agent.run(days_lookback=90)

print(f"角色执行条数: {len(role_result['role_execution'])}")
for row in role_result["role_execution"][:5]:
    print(f"  {row['role_zh']} × {row['channel_zh']}: 分配{row['assigned_leads_count']} 成交{row['deal_count']} 超时{row['overdue_followups_count']}")

print(f"\n协调问题 ({len(role_result['department_coordination_issues'])} 条):")
for issue in role_result["department_coordination_issues"]:
    print(f"  {issue}")

print("\n✅ 归因验证完成")
