"""
Pydantic data models for the Life Simulator API.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class UserAttributes(BaseModel):
    health: float = 50.0
    wealth: float = 50.0
    happiness: float = 50.0
    capability: float = 50.0


class SimulationState(BaseModel):
    age: float
    attributes: Dict[str, float]
    inventory: List[str]
    current_dilemma: str
    target_goal: str
    win_condition: str
    loss_condition: str
    narrative_start: Optional[str] = None


class InitRequest(BaseModel):
    user_input: str


class SimulationRequest(BaseModel):
    current_state: SimulationState
    user_choice: str
    history: List[str] = []


class EpiphanyRequest(BaseModel):
    history: List[str]
    dilemma: str
    final_state: SimulationState
    conclusion: Optional[str] = None  # "win", "loss", or None
