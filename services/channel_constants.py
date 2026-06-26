"""极致教育 · 渠道与角色常量"""

CHANNEL_EN_TO_ZH = {
    "promotion":      "推广",
    "xiaohongshu":    "小红书",
    "vertical_account": "垂直号",
    "moments":        "朋友圈",
    "community":      "社群",
    "referral":       "转介绍",
    "old_customer":   "老客户",
    "manual":         "人工录入",
    "unknown":        "未知",
}

VALID_CHANNELS = tuple(CHANNEL_EN_TO_ZH.keys())

CHANNEL_ALIASES = {
    "小红书": "xiaohongshu",
    "朋友圈": "moments",
    "社群": "community",
    "转介绍": "referral",
    "老客户": "old_customer",
    "推广": "promotion",
    "垂直号": "vertical_account",
    "人工": "manual",
    "直接联系": "manual",
    "": "unknown",
}

ROLE_EN_TO_ZH = {
    "promotion_team": "推广部",
    "xueguan":        "学管",
    "consultant":     "顾问",
    "backend":        "后台",
    "management":     "管理层",
}

VALID_ROLES = tuple(ROLE_EN_TO_ZH.keys())

ROLE_ALIASES = {
    "推广部": "promotion_team",
    "学管": "xueguan",
    "顾问": "consultant",
    "后台": "backend",
    "管理层": "management",
    "市场部": "promotion_team",
    "销售部": "consultant",
    "销售顾问": "consultant",
    "产品部": "backend",
    "后端":   "xueguan",
    "学管部": "xueguan",
    "运营部": "promotion_team",
    "教研部": "xueguan",
}

# 渠道 → 默认来源角色（当没有明确 source_owner_role 时的推断逻辑）
CHANNEL_DEFAULT_ROLE = {
    "promotion":      "promotion_team",
    "xiaohongshu":    None,   # 学管或顾问，不能强行推断
    "vertical_account": None, # 同上
    "moments":        "promotion_team",
    "community":      "promotion_team",
    "referral":       "consultant",
    "old_customer":   "consultant",
    "manual":         None,
    "unknown":        None,
}


def normalize_channel(raw: str) -> str:
    if not raw:
        return "unknown"
    raw = raw.strip()
    if raw in VALID_CHANNELS:
        return raw
    return CHANNEL_ALIASES.get(raw, "unknown")


def normalize_role(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if raw in VALID_ROLES:
        return raw
    return ROLE_ALIASES.get(raw, "")


def channel_zh(channel: str) -> str:
    return CHANNEL_EN_TO_ZH.get(channel, channel)


def role_zh(role: str) -> str:
    return ROLE_EN_TO_ZH.get(role, role)
