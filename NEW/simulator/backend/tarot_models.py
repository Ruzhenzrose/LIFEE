"""
Pydantic data models for the AI Tarot feature.
"""
from typing import List, Optional

from pydantic import BaseModel


class TarotCard(BaseModel):
    name: str
    name_cn: str
    orientation: str           # "upright" or "reversed"
    orientation_cn: str        # "正位" or "逆位"
    keywords: str
    position: str              # e.g. "过去", "现在", "未来"


class TarotReadingRequest(BaseModel):
    question: str
    spread_type: str = "three_card"   # "single", "three_card", "celtic_cross"


class TarotReadingResponse(BaseModel):
    cards: List[TarotCard]
    reading: str
    spread_name: str
    spread_name_cn: str
