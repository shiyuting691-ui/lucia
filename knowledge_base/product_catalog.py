"""
极致教育 · 产品目录
供所有 Agent 使用，确保策略输出使用真实产品名称。
数据来源：01_产品知识库 / 销售手册
"""

# 产品ID → 完整产品信息
PRODUCT_CATALOG = {
    "regular": {
        "name": "课业辅导（单次）",
        "short": "课业辅导",
        "desc": "单次作业/Essay/考试/Report辅导，按需下单。覆盖全专业，最灵活的入门选择。",
        "target_students": "有单次作业或考试压力的留学生，首次尝试用户",
        "price_range": "按字数/课时定价",
        "key_selling_points": [
            "灵活按需，无需预付大额",
            "覆盖Essay、Report、考试、演讲全类型",
            "48h内响应，急单可处理",
        ],
        "upsell_to": ["annual_package", "guaranteed", "dp_premium"],
        "best_timing": "学期中随时，尤其DDL前1-2周",
    },
    "dissertation": {
        "name": "毕业论文辅导（Dissertation）",
        "short": "Dissertation",
        "desc": "毕业论文/大论文全程辅导，从选题、文献综述到终稿质检，覆盖整个论文周期。",
        "target_students": "大三/大四/研究生即将提交毕业论文的学生",
        "price_range": "按字数定价，通常高于普通作业",
        "key_selling_points": [
            "覆盖选题→提纲→文献→各章→终稿全流程",
            "专业学科对口老师",
            "Turnitin+AI双检测",
        ],
        "upsell_to": ["dp_premium"],
        "best_timing": "毕业论文提交前3-8周，英澳论文截止高峰（5-6月、11-12月）",
    },
    "final_prediction": {
        "name": "Final精准押题",
        "short": "押题",
        "desc": "基于课程资料系统化预测考试重点，输出押题卷（主押卷+变体卷）+知识点地图。标准价¥5,000。",
        "target_students": "期末前2-4周、复习没方向、文商社科为主",
        "price_range": "¥5,000（标准版A档），含主押卷+变体卷",
        "key_selling_points": [
            "押中≥60%否则退款（文商社科全退，工科退60%）",
            "考试画像+Topic Map+买一送一两套押题卷",
            "48h紧急可协商",
        ],
        "upsell_to": ["guaranteed"],
        "best_timing": "期末考试前2-4周，补考前",
        "packages": {
            "C档·秘籍轻享版": "仅Topic Map知识点地图，引流款",
            "A档·标准押题版（主推）": "考试画像+Topic Map+主押卷+变体卷，¥5,000",
            "B档·押题+辅导版": "A档+老师1v1讲解，适合基础薄弱学生",
        },
    },
    "annual_package": {
        "name": "学年包",
        "short": "学年包",
        "desc": "全学年GPA托管服务，含前三等级VIP师资、双人质检、GPA管家8阶段全程跟踪，账户制扣费。",
        "target_students": "预估全学期消费≥2万、多门课有需求、申研有GPA要求的学生",
        "price_range": "账户制充值，充值有赠送，余额跨学期用",
        "key_selling_points": [
            "GPA管家8阶段全程：建档→规划→DDL提醒→执行跟踪→出分复盘→下学期规划",
            "前三等级高阶师资优先锁定",
            "双人质检（A写B查）+AI检测报告",
            "账户制扣费，余额可退，不强制清零",
        ],
        "upsell_to": ["dp_premium"],
        "best_timing": "开学前1-2周（新学期规划）、老客户成绩出来后（复盘时续费）、期中后",
        "upgrade_from": ["regular"],
    },
    "guaranteed": {
        "name": "保过辅导",
        "short": "保过",
        "desc": "考试/写作全程辅导，不过退款。分考试类（8步流程）和写作类两条服务线，按结果收费。",
        "target_students": "有挂科风险、必须过关、对结果要求强的学生",
        "price_range": "高于普通辅导，按结果保障定价",
        "key_selling_points": [
            "不过退款，利益绑定",
            "考试类8步完整流程：需求→方案→报价→摸底→计划→辅导→押题→结课",
            "写作类全流程托管：选题→大纲→各章→终稿质检",
        ],
        "upsell_to": ["dp_premium"],
        "best_timing": "考前4周内（焦虑感强时）、有挂科记录的老客户",
    },
    "dp_premium": {
        "name": "DP高端服务（Distinction Pass）",
        "short": "DP",
        "desc": "行业最高端学术服务品牌，以Distinction为目标，合同约定目标分数，达不到按比例退款；挂科72h双倍赔付；安全问题所有订单免费。",
        "target_students": "目标Distinction/1st、申研、高净值、有过被坑经历的学生",
        "price_range": "高端定价，基础保障型+卓越安心包两档",
        "key_selling_points": [
            "目标分数写进合同，未达标按比例退款",
            "挂科72h双倍赔付；安全问题造成后果所有订单免费",
            "全职内部签约老师+独立质检+元数据清洗",
            "项目制共享文档，30%/70%/100%节点主动反馈",
        ],
        "packages": {
            "基础保障型": "确保Pass，稳步提分，未达目标分数按比例退款",
            "卓越安心包": "冲刺Distinction/1st，全阶段质检，挂科72h双倍赔付",
        },
        "best_timing": "客户说申研/冲高分/之前被坑过/目标Distinction时",
    },
    "ai_compliance": {
        "name": "AI合规学习",
        "short": "AI合规",
        "desc": "帮助学生在AI时代合规使用AI工具完成学业，规避学术风险。",
        "target_students": "担心AI检测、想了解如何合规使用AI的学生",
        "price_range": "待定",
        "key_selling_points": ["合规使用AI", "规避学术处分风险"],
        "upsell_to": [],
        "best_timing": "开学初、学校发布AI政策时",
    },
}

# 产品升单路径（用于周度销售建议）
UPSELL_PATHS = {
    "regular":       ["annual_package", "guaranteed", "dp_premium"],
    "dissertation":  ["dp_premium"],
    "final_prediction": ["guaranteed", "annual_package"],
    "annual_package": ["dp_premium"],
    "guaranteed":    ["dp_premium"],
    "dp_premium":    [],  # 已是顶级
    "ai_compliance": ["annual_package"],
}

# 内部ID → 对外产品名（用于策略输出）
PRODUCT_NAME_MAP = {k: v["name"] for k, v in PRODUCT_CATALOG.items()}

# 季节性推荐（月份 → 优先推广产品）
SEASONAL_FOCUS = {
    1:  ["regular", "final_prediction"],       # 1月：英国期末考
    2:  ["regular", "final_prediction"],       # 2月：英国补考/澳洲开学
    3:  ["annual_package", "regular"],         # 3月：澳洲开学季
    4:  ["regular", "guaranteed"],             # 4月：英国Essay季
    5:  ["dissertation", "regular"],           # 5月：英国Dissertation截止
    6:  ["dissertation", "final_prediction"],  # 6月：英澳论文+期末双高峰
    7:  ["annual_package", "dp_premium"],      # 7月：暑期规划/升单
    8:  ["annual_package", "regular"],         # 8月：澳洲新学期
    9:  ["annual_package", "regular"],         # 9月：英国新学期
    10: ["regular", "guaranteed"],             # 10月：英澳期中
    11: ["dissertation", "regular"],           # 11月：英国Dissertation
    12: ["final_prediction", "regular"],       # 12月：期末考试季
}


def get_product_info_for_prompt(top_products: list) -> str:
    """
    将数据库产品统计 [(product_id, count), ...] 转换为
    Agent Prompt 中使用的产品信息文本块。
    """
    lines = []
    for pid, count in top_products:
        info = PRODUCT_CATALOG.get(pid)
        if not info:
            continue
        lines.append(
            f"- **{info['name']}**（内部ID: {pid}，近期销量: {count}单）\n"
            f"  定位：{info['desc']}\n"
            f"  核心卖点：{'、'.join(info['key_selling_points'][:2])}\n"
            f"  最佳推广时机：{info['best_timing']}"
        )
    return "\n\n".join(lines) if lines else "（暂无产品销售数据）"


def get_seasonal_products(month: int) -> list:
    """返回该月优先推广的产品ID列表"""
    return SEASONAL_FOCUS.get(month, ["regular"])
