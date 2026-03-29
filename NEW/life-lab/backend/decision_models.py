"""
Pydantic data models for the Quantitative Decision Assistant.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class DecisionRequest(BaseModel):
    dilemma: str


class Scenarios(BaseModel):
    best_case: str
    worst_case: str
    most_likely: str


class DecisionOption(BaseModel):
    name: str
    description: str
    scores: Dict[str, float]        # 6 dimension scores (0-100)
    expected_value: float            # overall EV (0-100)
    scenarios: Scenarios


class DecisionResponse(BaseModel):
    options: List[DecisionOption]
    recommendation: str
