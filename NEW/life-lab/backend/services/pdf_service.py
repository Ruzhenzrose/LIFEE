"""
PDF report generation with proper multi-page layout using ReportLab Platypus.

Uses the high-level Platypus engine (Paragraphs, Spacers, Tables) so long text
flows across pages automatically — no more truncated content.
"""
import logging
import os
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
    KeepTogether,
)

from models import SimulationState

logger = logging.getLogger("life-simulator.pdf")

# ---------------------------------------------------------------------------
# Font registration (runs once at import time)
# ---------------------------------------------------------------------------
_BUNDLED_FONT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts", "simhei.ttf")

_FONT_SEARCH_PATHS = [
    _BUNDLED_FONT,
    "simhei.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/truetype/simhei.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]


def _register_chinese_font() -> str:
    """Try multiple paths to find and register a CJK font."""
    for path in _FONT_SEARCH_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CJKFont", path))
                logger.info("Registered CJK font from: %s", path)
                return "CJKFont"
            except Exception as exc:
                logger.warning("Failed to register font %s: %s", path, exc)
    logger.warning("No CJK font found — Chinese characters may not render.")
    return "Helvetica"


PDF_FONT: str = _register_chinese_font()

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


def _build_styles():
    """Build a custom stylesheet for the report."""
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName=PDF_FONT,
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#1a1a2e"),
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#7f8c8d"),
            alignment=TA_CENTER,
            spaceAfter=24,
        ),
        "heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName=PDF_FONT,
            fontSize=15,
            leading=22,
            textColor=colors.HexColor("#2980b9"),
            spaceBefore=20,
            spaceAfter=10,
        ),
        "heading_epiphany": ParagraphStyle(
            "EpiphanyHeading",
            parent=base["Heading2"],
            fontName=PDF_FONT,
            fontSize=16,
            leading=24,
            textColor=colors.HexColor("#8e44ad"),
            spaceBefore=20,
            spaceAfter=12,
        ),
        "body": ParagraphStyle(
            "BodyText",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=10.5,
            leading=16,
            textColor=colors.HexColor("#2c3e50"),
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "timeline_entry": ParagraphStyle(
            "TimelineEntry",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#333333"),
            leftIndent=14,
            spaceAfter=8,
        ),
        "stat_label": ParagraphStyle(
            "StatLabel",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#7f8c8d"),
        ),
        "stat_value": ParagraphStyle(
            "StatValue",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#2c3e50"),
        ),
        "conclusion_win": ParagraphStyle(
            "ConclusionWin",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=14,
            leading=20,
            textColor=colors.HexColor("#27ae60"),
            alignment=TA_CENTER,
            spaceBefore=10,
            spaceAfter=10,
        ),
        "conclusion_loss": ParagraphStyle(
            "ConclusionLoss",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=14,
            leading=20,
            textColor=colors.HexColor("#c0392b"),
            alignment=TA_CENTER,
            spaceBefore=10,
            spaceAfter=10,
        ),
        "epiphany": ParagraphStyle(
            "EpiphanyBody",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=11,
            leading=18,
            textColor=colors.HexColor("#2c3e50"),
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "footer_note": ParagraphStyle(
            "FooterNote",
            parent=base["Normal"],
            fontName=PDF_FONT,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#95a5a6"),
            alignment=TA_CENTER,
            spaceBefore=30,
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _hr(color_hex: str = "#ecf0f1"):
    return HRFlowable(
        width="100%", thickness=1,
        color=colors.HexColor(color_hex),
        spaceAfter=8, spaceBefore=4,
    )


def _make_info_table(rows, styles):
    """Build a two-column info table (label | value)."""
    table = Table(
        rows,
        colWidths=[1.3 * inch, 4.5 * inch],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#ecf0f1")),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#bdc3c7")),
    ]))
    return table


# ---------------------------------------------------------------------------
# PDF creation
# ---------------------------------------------------------------------------

def create_pdf_report(
    filepath: str,
    history: List[str],
    epiphany: str,
    state: SimulationState,
    conclusion: Optional[str] = None,
) -> None:
    """
    Generate a comprehensive Life Simulation Report as a multi-page PDF.

    Includes: profile summary, full timeline, outcome, and complete epiphany.
    All content auto-wraps and paginates — nothing is truncated.
    """
    styles = _build_styles()

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        topMargin=0.8 * inch,
        bottomMargin=0.7 * inch,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
    )

    story: list = []

    # ══════════════════════════════════════════════════════════════════
    # SECTION 1 — COVER / TITLE
    # ══════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 40))
    story.append(Paragraph("🧬 人生模拟报告", styles["title"]))
    story.append(Paragraph("Life Simulation Report · Powered by Life Lab", styles["subtitle"]))

    # Conclusion banner
    if conclusion:
        conclusion_escaped = _escape(conclusion)
        if "胜利" in conclusion:
            story.append(Paragraph(
                f"🏆 模拟结局：{conclusion_escaped}",
                styles["conclusion_win"],
            ))
        elif "失败" in conclusion:
            story.append(Paragraph(
                f"💔 模拟结局：{conclusion_escaped}",
                styles["conclusion_loss"],
            ))
        else:
            story.append(Paragraph(
                f"🏁 模拟结局：{conclusion_escaped}",
                styles["body"],
            ))
        story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════
    # SECTION 2 — PROFILE SUMMARY
    # ══════════════════════════════════════════════════════════════════
    story.append(Paragraph("📋 模拟概况", styles["heading"]))
    story.append(_hr())

    profile_rows = [
        [
            Paragraph("目标", styles["stat_label"]),
            Paragraph(_escape(state.target_goal), styles["stat_value"]),
        ],
        [
            Paragraph("胜利条件", styles["stat_label"]),
            Paragraph(_escape(state.win_condition), styles["stat_value"]),
        ],
        [
            Paragraph("失败条件", styles["stat_label"]),
            Paragraph(_escape(state.loss_condition), styles["stat_value"]),
        ],
        [
            Paragraph("核心困境", styles["stat_label"]),
            Paragraph(_escape(state.current_dilemma), styles["stat_value"]),
        ],
        [
            Paragraph("最终年龄", styles["stat_label"]),
            Paragraph(str(state.age), styles["stat_value"]),
        ],
    ]

    # Attributes row
    attrs = state.attributes
    attr_parts = "  |  ".join([
        f"❤️ 健康 {attrs.get('health', '?')}",
        f"💰 财富 {attrs.get('wealth', '?')}",
        f"😊 快乐 {attrs.get('happiness', '?')}",
        f"⚡ 能力 {attrs.get('capability', '?')}",
    ])
    profile_rows.append([
        Paragraph("最终属性", styles["stat_label"]),
        Paragraph(attr_parts, styles["stat_value"]),
    ])

    story.append(_make_info_table(profile_rows, styles))
    story.append(Spacer(1, 12))

    # Initial narrative if available
    if state.narrative_start:
        story.append(Paragraph("📝 初始叙事", styles["heading"]))
        story.append(_hr())
        story.append(Paragraph(_escape(state.narrative_start), styles["body"]))
        story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════════
    # SECTION 3 — FULL TIMELINE
    # ══════════════════════════════════════════════════════════════════
    story.append(Paragraph("📖 模拟时间线", styles["heading"]))
    story.append(_hr())

    if history:
        for idx, entry in enumerate(history, start=1):
            story.append(
                Paragraph(
                    f"<b>{idx}.</b>  {_escape(entry)}",
                    styles["timeline_entry"],
                )
            )
    else:
        story.append(Paragraph("（无历史记录）", styles["body"]))

    # ══════════════════════════════════════════════════════════════════
    # SECTION 4 — EPIPHANY / LIFE SUMMARY (new page)
    # ══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("💡 人生总结与启示", styles["heading_epiphany"]))
    story.append(_hr("#d5b8ff"))

    if epiphany:
        for para_text in epiphany.split("\n"):
            stripped = para_text.strip()
            if not stripped:
                story.append(Spacer(1, 6))
                continue
            # Detect markdown-style headings from AI output
            if stripped.startswith("## "):
                story.append(Paragraph(
                    _escape(stripped[3:]),
                    styles["heading"],
                ))
            elif stripped.startswith("# "):
                story.append(Paragraph(
                    _escape(stripped[2:]),
                    styles["heading_epiphany"],
                ))
            elif stripped.startswith("**") and stripped.endswith("**"):
                story.append(Paragraph(
                    f"<b>{_escape(stripped[2:-2])}</b>",
                    styles["epiphany"],
                ))
            else:
                story.append(Paragraph(_escape(stripped), styles["epiphany"]))
    else:
        story.append(Paragraph("（未生成人生启示）", styles["body"]))

    # ══════════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 30))
    story.append(_hr("#bdc3c7"))
    story.append(Paragraph(
        "本报告由 Life Lab 人生模拟器自动生成，仅供娱乐与参考。",
        styles["footer_note"],
    ))

    # ── Build ─────────────────────────────────────────────────────────
    doc.build(story)
    logger.info("PDF report saved: %s", filepath)
