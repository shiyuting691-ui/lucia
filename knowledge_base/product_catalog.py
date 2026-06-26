"""极致教育产品目录事实源。

正式页面和 Agent 只能使用这里的 PRODUCT_CATALOG。未命中目录的产品
必须返回 no_data，不得展示推荐或生成任务。
"""

PRODUCT_CATALOG = {
    "language_tutoring": {
        "name": "语言班辅导",
        "short": "语言班辅导",
        "desc": "语言班课程跟进与作业/考核辅导。",
        "target_students": "语言班在读、担心无法通过语言班或衔接正课的学生",
        "price_range": "按课程/周期定价",
        "key_selling_points": ["语言班课程跟进", "作业与考核支持", "正课衔接准备"],
        "aliases": ["语言班", "语言班辅导", "language course", "pre-sessional"],
    },
    "pse_followup": {
        "name": "PSE跟课",
        "short": "PSE跟课",
        "desc": "Pre-sessional English 课程跟课与作业支持。",
        "target_students": "PSE在读、课程节奏跟不上的学生",
        "price_range": "按周期/课时定价",
        "key_selling_points": ["PSE课程跟进", "课堂任务支持", "阶段考核准备"],
        "aliases": ["PSE", "PSE跟课", "pre-sessional English"],
    },
    "hwept_sprint": {
        "name": "HWEPT冲刺",
        "short": "HWEPT冲刺",
        "desc": "HWEPT考试专项冲刺辅导。",
        "target_students": "需要通过HWEPT或类似语言测评的学生",
        "price_range": "按考试/课时定价",
        "key_selling_points": ["考试题型梳理", "短期冲刺", "弱项训练"],
        "aliases": ["HWEPT", "HWEPT冲刺"],
    },
    "prestudy": {
        "name": "开学前预习课",
        "short": "预习课",
        "desc": "开学前课程预习和学术适应辅导。",
        "target_students": "即将入学、希望提前适应课程的学生",
        "price_range": "按课程/课时定价",
        "key_selling_points": ["提前熟悉课程", "降低开学适应压力", "基础知识补齐"],
        "aliases": ["预习课", "开学前预习", "开学前预习课"],
    },
    "assignment_done": {
        "name": "作业委托",
        "short": "作业委托",
        "desc": "作业/课程任务委托式支持，需明确边界与合规风险。",
        "target_students": "DDL临近、作业压力大的学生",
        "price_range": "按字数/难度/DDL定价",
        "key_selling_points": ["按DDL倒排", "专业方向匹配", "交付前检查"],
        "aliases": ["作业委托", "assignment", "coursework"],
    },
    "coursework_tutoring": {
        "name": "作业辅导",
        "short": "作业辅导",
        "desc": "作业、Essay、Report、Presentation等课程任务辅导。",
        "target_students": "需要理解题目、提升作业质量的学生",
        "price_range": "按字数/课时定价",
        "key_selling_points": ["题目拆解", "结构辅导", "过程反馈"],
        "aliases": ["作业辅导", "Essay写作", "Report撰写", "课业辅导", "regular"],
    },
    "exam_support": {
        "name": "考试助力",
        "short": "考试助力",
        "desc": "考试复习规划、重点梳理、题型训练。",
        "target_students": "临近考试、复习没方向的学生",
        "price_range": "按课程/课时定价",
        "key_selling_points": ["复习计划", "重点梳理", "题型训练"],
        "aliases": ["考试助力", "考试辅导", "exam support", "exam"],
    },
    "prediction": {
        "name": "押题",
        "short": "押题",
        "desc": "基于课程资料做考前重点范围判断和复习方向整理。",
        "target_students": "期末/补考前2-4周，需要重点梳理的学生",
        "price_range": "按课程/资料完整度定价",
        "key_selling_points": ["重点范围判断", "复习方向整理", "题型分析"],
        "aliases": ["押题", "Final押题", "Final精准押题", "final_prediction", "final"],
    },
    "guaranteed": {
        "name": "包过辅导",
        "short": "包过辅导",
        "desc": "结果导向辅导产品，必须明确合同边界和客户配合要求。",
        "target_students": "有挂科风险、必须通过的学生",
        "price_range": "按风险和结果保障定价",
        "key_selling_points": ["流程兜底", "合同边界", "风险共担"],
        "aliases": ["包过", "保过", "包过辅导", "guaranteed"],
    },
    "dissertation_full": {
        "name": "Dissertation全流程",
        "short": "Dissertation",
        "desc": "毕业论文从选题、提纲、章节到终稿的全流程支持。",
        "target_students": "本科/硕士毕业论文阶段学生",
        "price_range": "按字数/阶段定价",
        "key_selling_points": ["全流程规划", "阶段反馈", "终稿检查"],
        "aliases": ["Dissertation", "dissertation", "毕业论文", "大论文", "Dissertation全流程"],
    },
    "quality_70": {
        "name": "70+质检",
        "short": "70+质检",
        "desc": "以目标分数为导向的质量检查和修改建议。",
        "target_students": "希望提升作业质量、降低返修风险的学生",
        "price_range": "按文档/字数定价",
        "key_selling_points": ["结构检查", "评分点检查", "修改建议"],
        "aliases": ["70+质检", "质检", "70+质量检查"],
    },
    "ai_reduction": {
        "name": "降AI率",
        "short": "降AI率",
        "desc": "围绕AI检测风险的文本检查与表达调整服务。",
        "target_students": "担心AI检测或学术合规风险的学生",
        "price_range": "按字数定价",
        "key_selling_points": ["AI风险检查", "表达调整", "合规提醒"],
        "aliases": ["降AI率", "AI检测", "AI合规", "ai_compliance"],
    },
    "annual_package": {
        "name": "学年包",
        "short": "学年包",
        "desc": "全学年学业服务包，覆盖规划、跟进、复盘。",
        "target_students": "多门课、长期规划、希望稳定跟进的学生",
        "price_range": "按学年/账户制定价",
        "key_selling_points": ["长期规划", "固定团队", "阶段复盘"],
        "aliases": ["学年包", "annual_package", "annual package"],
    },
    "course_package": {
        "name": "包课",
        "short": "包课",
        "desc": "按课程整体打包的辅导产品。",
        "target_students": "单门或多门课程需要持续跟进的学生",
        "price_range": "按课程数量定价",
        "key_selling_points": ["整课跟进", "成本可控", "持续反馈"],
        "aliases": ["包课", "全课程包", "course package"],
    },
    "dp_excellence": {
        "name": "DP卓越安心包",
        "short": "DP卓越安心包",
        "desc": "高目标分数导向的高端服务包。",
        "target_students": "目标高分、申研或高净值学生",
        "price_range": "高端定价",
        "key_selling_points": ["目标管理", "高标准质检", "阶段交付"],
        "aliases": ["DP卓越安心包", "DP", "dp_premium", "Distinction Pass"],
    },
    "anxin_package": {
        "name": "安心包",
        "short": "安心包",
        "desc": "学期阶段性综合服务包。",
        "target_students": "希望一段时间内统一安排学业支持的学生",
        "price_range": "按学期/阶段定价",
        "key_selling_points": ["统一安排", "阶段跟进", "降低沟通成本"],
        "aliases": ["安心包"],
    },
    "graduation_carefree": {
        "name": "毕业无忧",
        "short": "毕业无忧",
        "desc": "围绕毕业阶段论文、课程、风险管理的组合服务。",
        "target_students": "毕业季、多任务叠加、有毕业压力的学生",
        "price_range": "组合报价",
        "key_selling_points": ["毕业节点规划", "多任务统筹", "风险提醒"],
        "aliases": ["毕业无忧"],
    },
    "ai_top_student": {
        "name": "AI学霸成长包",
        "short": "AI学霸成长包",
        "desc": "AI工具合规使用、学习效率与学术表达提升组合服务。",
        "target_students": "希望提升AI时代学习效率且关注合规的学生",
        "price_range": "按套餐定价",
        "key_selling_points": ["AI工具使用", "学习效率", "合规边界"],
        "aliases": ["AI学霸成长包"],
    },
}

PRODUCT_NAME_MAP = {k: v["name"] for k, v in PRODUCT_CATALOG.items()}

UPSELL_PATHS = {
    "assignment_done": ["quality_70", "ai_reduction", "anxin_package"],
    "coursework_tutoring": ["annual_package", "course_package", "dp_excellence"],
    "exam_support": ["prediction", "guaranteed"],
    "prediction": ["exam_support", "guaranteed"],
    "dissertation_full": ["quality_70", "ai_reduction", "graduation_carefree"],
    "annual_package": ["dp_excellence"],
}

SEASONAL_FOCUS = {
    1: ["exam_support", "prediction"],
    2: ["language_tutoring", "prestudy"],
    3: ["annual_package", "course_package"],
    4: ["assignment_done", "coursework_tutoring"],
    5: ["dissertation_full", "quality_70"],
    6: ["exam_support", "prediction"],
    7: ["graduation_carefree", "dp_excellence"],
    8: ["prestudy", "annual_package"],
    9: ["prestudy", "course_package"],
    10: ["assignment_done", "quality_70"],
    11: ["dissertation_full", "ai_reduction"],
    12: ["exam_support", "prediction"],
}


def get_product_info_for_prompt(top_products: list) -> str:
    lines = []
    for pid, count in top_products:
        info = PRODUCT_CATALOG.get(pid)
        if not info:
            continue
        lines.append(
            f"- **{info['name']}**（内部ID: {pid}，近期销量: {count}单）\n"
            f"  定位：{info['desc']}\n"
            f"  核心卖点：{'、'.join(info['key_selling_points'][:2])}"
        )
    return "\n\n".join(lines) if lines else "暂无真实数据，无法判断。"


def get_seasonal_products(month: int) -> list:
    return SEASONAL_FOCUS.get(month, [])
