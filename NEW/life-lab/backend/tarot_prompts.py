"""
Complete 78-card Tarot deck data and AI interpretation prompts.
"""
import random
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 78-Card Tarot Deck
# ---------------------------------------------------------------------------

MAJOR_ARCANA = [
    {"name": "The Fool", "name_cn": "愚者", "number": 0,
     "upright": "新开始、冒险、纯真、自由", "reversed": "鲁莽、不计后果、停滞"},
    {"name": "The Magician", "name_cn": "魔术师", "number": 1,
     "upright": "创造力、意志力、技巧、资源", "reversed": "欺骗、操控、能力不足"},
    {"name": "The High Priestess", "name_cn": "女祭司", "number": 2,
     "upright": "直觉、潜意识、神秘、内在智慧", "reversed": "隐藏的真相、忽视直觉"},
    {"name": "The Empress", "name_cn": "女皇", "number": 3,
     "upright": "丰饶、母性、自然、创造", "reversed": "过度依赖、创造力枯竭"},
    {"name": "The Emperor", "name_cn": "皇帝", "number": 4,
     "upright": "权威、结构、控制、领导力", "reversed": "专制、僵化、失控"},
    {"name": "The Hierophant", "name_cn": "教皇", "number": 5,
     "upright": "传统、信仰、遵循规则、精神指引", "reversed": "叛逆、非传统、挑战权威"},
    {"name": "The Lovers", "name_cn": "恋人", "number": 6,
     "upright": "爱情、和谐、关系、选择", "reversed": "失衡、不和谐、错误选择"},
    {"name": "The Chariot", "name_cn": "战车", "number": 7,
     "upright": "意志力、胜利、决心、掌控", "reversed": "失去方向、缺乏控制"},
    {"name": "Strength", "name_cn": "力量", "number": 8,
     "upright": "勇气、内在力量、耐心、同理心", "reversed": "软弱、自我怀疑、缺乏勇气"},
    {"name": "The Hermit", "name_cn": "隐者", "number": 9,
     "upright": "内省、独处、智慧、寻找真理", "reversed": "孤立、封闭、迷失方向"},
    {"name": "Wheel of Fortune", "name_cn": "命运之轮", "number": 10,
     "upright": "命运转折、机遇、变化、好运", "reversed": "厄运、抵制变化、失控"},
    {"name": "Justice", "name_cn": "正义", "number": 11,
     "upright": "公正、因果、真相、法律", "reversed": "不公、逃避责任、偏见"},
    {"name": "The Hanged Man", "name_cn": "倒吊人", "number": 12,
     "upright": "牺牲、等待、新视角、放手", "reversed": "拖延、抗拒牺牲、困顿"},
    {"name": "Death", "name_cn": "死神", "number": 13,
     "upright": "结束、转变、重生、放下过去", "reversed": "害怕改变、停滞、抗拒转变"},
    {"name": "Temperance", "name_cn": "节制", "number": 14,
     "upright": "平衡、调和、耐心、适度", "reversed": "失衡、过度、缺乏耐心"},
    {"name": "The Devil", "name_cn": "恶魔", "number": 15,
     "upright": "束缚、欲望、执迷、物质主义", "reversed": "挣脱束缚、觉醒、自由"},
    {"name": "The Tower", "name_cn": "塔", "number": 16,
     "upright": "突变、崩塌、破除幻象、觉醒", "reversed": "恐惧改变、苟延残喘"},
    {"name": "The Star", "name_cn": "星星", "number": 17,
     "upright": "希望、灵感、宁静、信心", "reversed": "绝望、失去信心、迷茫"},
    {"name": "The Moon", "name_cn": "月亮", "number": 18,
     "upright": "幻象、潜意识、直觉、焦虑", "reversed": "恐惧释放、逐渐清明"},
    {"name": "The Sun", "name_cn": "太阳", "number": 19,
     "upright": "快乐、成功、活力、乐观", "reversed": "消极、暂时受挫"},
    {"name": "Judgement", "name_cn": "审判", "number": 20,
     "upright": "觉醒、反思、审视、重生", "reversed": "自我怀疑、拒绝反省"},
    {"name": "The World", "name_cn": "世界", "number": 21,
     "upright": "完成、圆满、成就、旅程终点", "reversed": "未完成、缺少圆满"},
]

SUITS = ["Wands", "Cups", "Swords", "Pentacles"]
SUITS_CN = {"Wands": "权杖", "Cups": "圣杯", "Swords": "宝剑", "Pentacles": "星币"}
COURT = ["Page", "Knight", "Queen", "King"]
COURT_CN = {"Page": "侍从", "Knight": "骑士", "Queen": "王后", "King": "国王"}

_SUIT_THEMES = {
    "Wands":     {"upright": "激情、行动、创造、冒险",     "reversed": "冲动、疲惫、缺乏方向"},
    "Cups":      {"upright": "情感、关系、直觉、内心",     "reversed": "情感封闭、失落、幻想"},
    "Swords":    {"upright": "思维、决断、真相、挑战",     "reversed": "混乱、焦虑、冲突"},
    "Pentacles": {"upright": "物质、财富、实际、稳定",     "reversed": "贪婪、不安全感、损失"},
}

def _build_minor_arcana() -> list:
    """Generate all 56 minor arcana cards."""
    cards = []
    for suit in SUITS:
        suit_cn = SUITS_CN[suit]
        theme = _SUIT_THEMES[suit]
        # Number cards (Ace through 10)
        for num in range(1, 11):
            label = "Ace" if num == 1 else str(num)
            cards.append({
                "name": f"{label} of {suit}",
                "name_cn": f"{suit_cn}{label}",
                "upright": theme["upright"],
                "reversed": theme["reversed"],
            })
        # Court cards
        for court in COURT:
            cards.append({
                "name": f"{court} of {suit}",
                "name_cn": f"{suit_cn}{COURT_CN[court]}",
                "upright": theme["upright"],
                "reversed": theme["reversed"],
            })
    return cards

MINOR_ARCANA = _build_minor_arcana()
FULL_DECK = MAJOR_ARCANA + MINOR_ARCANA

# ---------------------------------------------------------------------------
# Spread Definitions
# ---------------------------------------------------------------------------

SPREADS = {
    "single": {
        "name": "单牌占卜",
        "name_en": "Single Card",
        "description": "抽取一张牌，快速获得对当前问题的指引。",
        "count": 1,
        "positions": ["指引"],
    },
    "three_card": {
        "name": "三牌阵",
        "name_en": "Past · Present · Future",
        "description": "三张牌分别代表过去、现在和未来的启示。",
        "count": 3,
        "positions": ["过去", "现在", "未来"],
    },
    "celtic_cross": {
        "name": "凯尔特十字",
        "name_en": "Celtic Cross",
        "description": "经典十牌阵，深入剖析你的处境与命运走向。",
        "count": 10,
        "positions": [
            "现状", "挑战", "潜意识", "过去",
            "可能的未来", "近期未来", "自我认知",
            "外部环境", "希望与恐惧", "最终结果",
        ],
    },
}

# ---------------------------------------------------------------------------
# Card Drawing
# ---------------------------------------------------------------------------

def draw_cards(spread_type: str) -> List[dict]:
    """
    Draw cards for a spread. Each card gets a random upright/reversed orientation.
    Returns a list of dicts: {card, orientation, position}.
    """
    spread = SPREADS.get(spread_type)
    if not spread:
        raise ValueError(f"Unknown spread type: {spread_type}")

    chosen = random.sample(FULL_DECK, spread["count"])
    result = []
    for i, card in enumerate(chosen):
        orientation = random.choice(["upright", "reversed"])
        result.append({
            "name": card["name"],
            "name_cn": card["name_cn"],
            "orientation": orientation,
            "orientation_cn": "正位" if orientation == "upright" else "逆位",
            "keywords": card[orientation],
            "position": spread["positions"][i],
        })
    return result


# ---------------------------------------------------------------------------
# AI Prompt
# ---------------------------------------------------------------------------

TAROT_READING_PROMPT = """\
你是一位经验丰富、充满神秘感的塔罗占卜师。

用户提出了一个问题，你已经为他们抽取了塔罗牌。
请根据抽到的每张牌的位置、牌名、正逆位、以及关键词，为用户写一段详细、有深度、且有温度的塔罗解读。

要求：
1. 先对每张牌逐一解读（说明牌的含义与在该位置的意义）。
2. 然后给出整体综合分析（牌与牌之间的联系、整体叙事）。
3. 最后给出一段温暖的建议。
4. 语气神秘而温暖，像一位智慧的占卜师在烛光下缓缓诉说。
5. 使用中文回答。
"""
