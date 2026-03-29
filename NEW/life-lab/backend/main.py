"""
Life Lab API — FastAPI application entry point.

All business logic is delegated to service modules:
  - services.ai_service   → async AI calls with retry
  - services.pdf_service   → PDF report generation
  - models / tarot_models / decision_models → Pydantic request/response schemas
  - prompts / tarot_prompts / decision_prompts → AI prompt templates
  - config                 → environment-based configuration
"""
import json
import logging
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import CORS_ORIGINS, REPORT_DIR
from models import InitRequest, SimulationRequest, EpiphanyRequest
from prompts import PROFILE_BUILDER_PROMPT, SIMULATION_PROMPT, EPIPHANY_PROMPT
from tarot_models import TarotReadingRequest, TarotReadingResponse, TarotCard
from tarot_prompts import TAROT_READING_PROMPT, SPREADS, draw_cards
from decision_models import DecisionRequest, DecisionResponse
from decision_prompts import DECISION_ANALYSIS_PROMPT, DIMENSIONS
from services.ai_service import call_ai
from services.pdf_service import create_pdf_report

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("life-simulator")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Life Lab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a numeric value within [lo, hi]."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def read_root():
    return {"message": "Life Simulator API is running"}


@app.post("/api/init")
async def initialize_profile(request: InitRequest):
    """Phase 1 — Build a user profile from natural-language self-description."""
    try:
        profile_data = await call_ai(PROFILE_BUILDER_PROMPT, request.user_input)
    except Exception as exc:
        logger.error("Profile init failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate profile") from exc

    if not profile_data:
        raise HTTPException(status_code=500, detail="Failed to generate profile")

    return profile_data


@app.post("/api/simulation")
async def run_simulation_step(request: SimulationRequest):
    """Phase 2 — Run one simulation turn based on the user's choice."""
    prompt = SIMULATION_PROMPT.format(
        target_goal=request.current_state.target_goal,
        win_condition=request.current_state.win_condition,
        loss_condition=request.current_state.loss_condition,
        user_choice=request.user_choice,
    )

    try:
        turn_data = await call_ai(
            prompt,
            json.dumps(request.current_state.model_dump(), ensure_ascii=False),
        )
    except Exception as exc:
        logger.error("Simulation step failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to run simulation step") from exc

    if not turn_data:
        raise HTTPException(status_code=500, detail="Failed to run simulation step")

    # Apply state changes with clamping
    current_attrs = request.current_state.attributes.copy()
    for key, delta in turn_data.get("state_changes", {}).items():
        if key in current_attrs:
            current_attrs[key] = clamp(current_attrs[key] + delta)

    narrative = turn_data["narrative"]
    time_passed = turn_data.get("time_passed", "一段时间")

    return {
        "narrative": narrative,
        "time_passed": time_passed,
        "new_attributes": current_attrs,
        "new_age": request.current_state.age + 0.5,
        "is_concluded": turn_data.get("is_concluded", False),
        "conclusion": turn_data.get("conclusion", None),
        "next_options": turn_data.get("next_options", []),
        "history_entry": f"【{time_passed}后】{narrative}",
    }


@app.post("/api/epiphany")
async def generate_epiphany_endpoint(request: EpiphanyRequest):
    """Phase 3 — Generate life-review insights + PDF report."""
    history_text = "\n".join(request.history)
    conclusion_label = {"win": "胜利", "loss": "失败"}.get(
        request.conclusion, "模拟结束"
    )

    prompt_filled = EPIPHANY_PROMPT.format(
        target_goal=request.final_state.target_goal,
        conclusion=conclusion_label,
        history=history_text,
    )

    try:
        epiphany = await call_ai("你是一个智慧的人生导师。", prompt_filled, json_mode=False)
    except Exception as exc:
        logger.error("Epiphany generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate epiphany") from exc

    # Generate PDF report
    report_url = None
    report_filename = f"report_{uuid.uuid4()}.pdf"
    report_path = os.path.join(REPORT_DIR, report_filename)

    try:
        create_pdf_report(
            report_path,
            request.history,
            epiphany,
            request.final_state,
            conclusion=conclusion_label,
        )
        report_url = f"/api/report/{report_filename}"
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)

    return {"epiphany": epiphany, "report_url": report_url}


@app.get("/api/report/{filename}")
async def download_report(filename: str):
    """Download a previously generated PDF report."""
    file_path = os.path.join(REPORT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Report not found")


# ---------------------------------------------------------------------------
# Tarot Routes
# ---------------------------------------------------------------------------


@app.get("/api/tarot/spreads")
async def get_tarot_spreads():
    """Return available tarot spread types."""
    return {
        key: {
            "name": val["name"],
            "name_en": val["name_en"],
            "description": val["description"],
            "count": val["count"],
        }
        for key, val in SPREADS.items()
    }


@app.post("/api/tarot/reading")
async def tarot_reading(request: TarotReadingRequest):
    """Draw tarot cards and generate an AI interpretation."""
    # Validate spread type
    if request.spread_type not in SPREADS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown spread type: {request.spread_type}. "
                   f"Available: {list(SPREADS.keys())}",
        )

    spread_info = SPREADS[request.spread_type]
    drawn = draw_cards(request.spread_type)

    # Build context for AI
    cards_description = "\n".join(
        f"位置【{c['position']}】: {c['name_cn']}（{c['name']}）— {c['orientation_cn']}\n"
        f"  关键词: {c['keywords']}"
        for c in drawn
    )

    user_prompt = (
        f"用户的问题：{request.question}\n\n"
        f"牌阵：{spread_info['name']}（{spread_info['name_en']}）\n\n"
        f"抽到的牌：\n{cards_description}"
    )

    try:
        reading = await call_ai(TAROT_READING_PROMPT, user_prompt, json_mode=False)
    except Exception as exc:
        logger.error("Tarot reading failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate reading") from exc

    cards = [TarotCard(**c) for c in drawn]

    return TarotReadingResponse(
        cards=cards,
        reading=reading,
        spread_name=spread_info["name_en"],
        spread_name_cn=spread_info["name"],
    )


# ---------------------------------------------------------------------------
# Decision Routes
# ---------------------------------------------------------------------------


@app.get("/api/decision/dimensions")
async def get_decision_dimensions():
    """Return the analysis dimensions metadata."""
    return DIMENSIONS


@app.post("/api/decision/analyze")
async def analyze_decision(request: DecisionRequest):
    """Analyze a life decision with quantitative models."""
    try:
        analysis = await call_ai(
            DECISION_ANALYSIS_PROMPT,
            f"用户的决策困境：{request.dilemma}",
            json_mode=True,
        )
    except Exception as exc:
        logger.error("Decision analysis failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to analyze decision"
        ) from exc

    if not analysis:
        raise HTTPException(status_code=500, detail="Empty analysis result")

    return analysis


# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
