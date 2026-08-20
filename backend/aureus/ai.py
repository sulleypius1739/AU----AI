"""AUREUS AI assistant — explains setups/rejections from the REAL engine output.

The LLM is fed the authoritative V4 signal (checks, events, trade plan) and must
explain, never invent. If EMERGENT_LLM_KEY is absent it falls back to a rule-based
explanation and clearly labels the AI as NOT CONNECTED.
"""
import os
from typing import Optional

SYSTEM = (
    "You are AUREUS AI, an institutional trading-desk analyst. You explain the V4 A+ "
    "market-mechanics strategy (4H direction -> 1H fresh POI -> 15M market shift -> 15M "
    "liquidity sweep -> 10M same-direction confirmation -> POI mitigation -> M5 execution "
    "-> 2R-5R target). You ONLY explain the provided engine result. Never invent conditions "
    "that are not in the data. Be concise, precise and desk-professional. If the status is "
    "WAIT/WATCH, clearly state exactly what is missing. Quality over quantity."
)


def rule_based_explanation(signal: dict) -> str:
    lines = [f"Market: {signal['symbol']} | Bias: {signal['direction'].upper()} | Status: {signal['status']}"]
    for name, chk in signal["checks"].items():
        mark = "PASS" if chk["passed"] else "MISSING"
        lines.append(f"- {name.replace('_', ' ').title()}: {mark} — {chk['detail']}")
    if signal["actionable"] and signal.get("trade_plan"):
        p = signal["trade_plan"]
        lines.append(f"A+ trade plan: entry {p['entry']}, stop {p['stop']}, "
                     f"target {p['target']}, RR {p['rr']}R.")
    elif signal.get("missing"):
        lines.append(f"AUREUS is waiting because: {signal['missing']}.")
    return "\n".join(lines)


async def explain(signal: dict, session_id: str = "aureus") -> dict:
    key = os.environ.get("EMERGENT_LLM_KEY")
    fallback = rule_based_explanation(signal)
    if not key:
        return {"ai_connected": False, "status": "NOT CONNECTED",
                "explanation": fallback}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session_id, system_message=SYSTEM) \
            .with_model("anthropic", "claude-sonnet-4-6")
        prompt = ("Explain this AUREUS V4 engine result to a trader. State the bias, what "
                  "aligned, what is missing (if any), and whether this is an A+ setup and why:\n\n"
                  f"{signal}")
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "content", str(resp))
        return {"ai_connected": True, "status": "CONNECTED", "explanation": text}
    except Exception as e:
        return {"ai_connected": False, "status": "NOT CONNECTED",
                "explanation": fallback, "error": str(e)}
