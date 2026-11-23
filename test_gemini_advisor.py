
from tools.llm_advisor import ask_llm_advisor

vlm_report = {
    "symbol": "BTC/USDT",
    "timeframe": "15m",
    "current_detections": [
        {
            "name": "Bullish Flag",
            "type": "continuation",
            "direction": "LONG",
            "status": "developing",
            "formation_state": "developing",
            "confidence": 0.85,
            "key_levels": {
                "level_high": 68000,
                "level_low": 67000,
                "trigger_level": 68000,
                "invalidation_level": 66800
            },
            "evidence": ["Bullish consolidation"],
            "missing_conditions": ["Breakout above 68000"]
        }
    ],
    "tracked_patterns": [],
    "market_structure": "Bullish",
    "overall_visual_bias": "Bullish",
    "breakout_status": "Not confirmed",
    "confidence": 0.85,
    "visual_evidence": ["Price consolidating below resistance"],
    "limitations": []
}

market_context = {
    "current_price": 67500,
    "volume": "Not provided",
    "candle_status": "Unknown"
}

result = ask_llm_advisor(
    vlm_report=vlm_report,
    market_context=market_context,
    has_open_position=False
)

import json
print(json.dumps(result, indent=4, default=str))
