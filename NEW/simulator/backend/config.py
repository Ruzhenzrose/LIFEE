"""
Centralized configuration — loads from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Gemini / OpenAI-compatible API ---
API_KEY: str = os.getenv("GEMINI_API_KEY", "")
BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL_NAME: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3-pro-preview")

# --- CORS ---
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
CORS_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# --- Reports ---
REPORT_DIR: str = os.getenv("REPORT_DIR", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Create a .env file or set the environment variable.")
