"""LIFEE CLI 模块"""
from .app import main
from .chat import chat_loop
from .debate import debate_loop

__all__ = ["main", "chat_loop", "debate_loop"]
