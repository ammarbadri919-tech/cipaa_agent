import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL_NAME = "gemini-decision-1"


def ask_llm_advisor(
    vlm_report: dict,
    market_context: dict,
    has_open_position: bool = False,
    open_position: dict | None = None,
) -> dict:
    """
    Gemini Decision 1 evaluates all unique patterns from the
    Pattern Tracker together with enriched market confirmation checks.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from .env")

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    current_patterns = vlm_report.get("current_detections", [])
    tracked_patterns = vlm_report.get("tracked_patterns", [])

    actions = {
        "WAIT": (
            "The trading opportunity is not ready, or the open position "
            "has not reached a supported exit condition."
        ),
    }
    if has_open_position:
        actions["EXIT"] = (
            "The open tracked analysis position should be closed when its setup "
            "is invalidated or the market meaningfully reverses against its "
            "direction (bearish against LONG, bullish against SHORT). Do not "
            "claim an exchange order was placed."
        )
    else:
        actions["ENTER"] = (
            "A sufficiently confirmed trading opportunity exists. The primary "
            "pattern is confirmed, aligns with market structure and visual bias, "
            "and supplied price confirmation supports entry."
        )


    input_data = {
        "symbol": vlm_report.get("symbol"),
        "timeframe": vlm_report.get("timeframe"),
        "current_detections": current_patterns,
        "tracked_patterns": tracked_patterns,
        "vlm_market_analysis": {
            "market_structure": vlm_report.get("market_structure"),
            "overall_visual_bias": vlm_report.get("overall_visual_bias"),
            "breakout_status": vlm_report.get("breakout_status"),
            "confidence": vlm_report.get("confidence"),
            "visual_evidence": vlm_report.get("visual_evidence"),
            "limitations": vlm_report.get("limitations", []),
        },
        "market_context": market_context,
        "has_open_position": has_open_position,
        "open_position": open_position if has_open_position else None,
    }

    instructions = (
        "You are CryptoGuardian's Pattern Decision Agent.\n\n"
        "Decide whether to ENTER, WAIT, or EXIT based solely on "
        "the supplied JSON and the following principles:\n\n"
        "1. PATTERN CONFIRMATION:\n"
        "Evaluate current_detections and tracked_patterns together. "
        "Identify the strongest relevant primary pattern using its "
        "formation_state, confidence, history, and evidence. "
        "A CONFIRMED pattern is stronger evidence than CONFIRMING. "
        "CONFIRMING alone is not sufficient for ENTER unless the "
        "supplied price and breakout evidence independently supports entry. "
        "DEVELOPING or DETECTED patterns must not be treated as confirmed. "
        "Do not let secondary patterns override a stronger primary pattern.\n\n"
        "2. DIRECTION AND MARKET STRUCTURE:\n"
        "Check whether pattern direction agrees with overall_visual_bias "
        "and market_structure. LONG generally aligns with BULLISH; "
        "SHORT generally aligns with BEARISH. Treat conflicting evidence "
        "as uncertainty and prefer WAIT. Preserve relevant opposing evidence.\n\n"
        "3. PRICE AND LEVEL VALIDITY:\n"
        "Check market_context.math_trigger_checks, last_closed_candle, and "
        "last_price against the primary pattern's key_levels.trigger_level "
        "and key_levels.invalidation_level. ENTER requires price to be on "
        "the valid side of the trigger without breaching invalidation. "
        "Do not assume a breakout is confirmed from last_price alone. "
        "Prefer completed-candle confirmation when supplied. If required "
        "level data is missing, do not invent it; prefer WAIT.\n\n"
        "4. RISK AND EXIT:\n"
        "The open_position field describes a tracked analysis position, not an "
        "exchange holding. When has_open_position is true, never recommend a "
        "second ENTER; choose EXIT only when evidence supports invalidation or "
        "a reversal against that position, otherwise choose WAIT. When it is "
        "false, EXIT is not allowed.\n\n"
        "5. FINAL DECISION:\n"
        "Choose ENTER only when pattern confirmation, direction, price "
        "validity, and available risk evidence support an entry. "
        "Choose WAIT when evidence is incomplete, conflicting, early, "
        "or uncertain. Choose EXIT only under the position rules above.\n\n"
        "Make ONE overall decision for the supplied symbol and timeframe. "
        "Do not invent prices, candle closes, volume, or confirmations. "
        "Never execute trades."
    )

    result = client.decisions.create(
        model=MODEL_NAME,
        input=json.dumps(input_data, default=str),
        questions={
            "market_decision": {
                "type": "choice",
                "instructions": instructions,
                "criteria": actions,
            }
        },
    )

    answer = result.answers["market_decision"]
    decision = answer.choice

    if decision not in actions:
        raise ValueError(
            f"Unexpected decision returned: {decision}"
        )

    return {
        "symbol": vlm_report.get("symbol"),
        "timeframe": vlm_report.get("timeframe"),
        "decision": decision,
        "reason": "Decision returned by Gemini. Explanation not yet available.",
        "decision_confidence": getattr(answer, "confidence", None),
        "model": MODEL_NAME,
        "current_patterns_considered": current_patterns,
        "tracked_patterns_considered": tracked_patterns,
        "open_position": open_position if has_open_position else None,
    }
