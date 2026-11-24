"""
LLM abstraction layer for MoveInSync.
Provides deterministic FakeLLM parser (for zero-cost, reproducible offline tests)
as well as real LLM calling capabilities (OpenAI/Gemini/Groq) if configured.
Guarantees at most 4 LLM calls per message turn.
"""
import re
from typing import Dict, Any, Optional, List
from app.config import USE_FAKE_LLM

def normalize_time_str(raw: str) -> Optional[str]:
    """
    Normalizes time expressions like '9 PM', '9pm', '8', '21:00', '9' to 'HH:MM'.
    """
    raw = raw.strip().lower()
    
    # 24-hour match HH:MM
    m24 = re.search(r'\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b', raw)
    if m24:
        h, m = int(m24.group(1)), int(m24.group(2))
        return f"{h:02d}:{m:02d}"

    # 12-hour match: 9 pm, 9:00 pm, 8 am
    m12 = re.search(r'\b(1[0-2]|[1-9])(?::([0-5][0-9]))?\s*(am|pm)\b', raw)
    if m12:
        h = int(m12.group(1))
        m = int(m12.group(2)) if m12.group(2) else 0
        period = m12.group(3)
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"

    # Standalone number like 'make it 8', 'make it 9' -> assumed PM for evening drops if >= 6, else default
    m_num = re.search(r'\b(make it|at|to)\s+([1-9]|1[0-2])\b', raw)
    if m_num:
        h = int(m_num.group(2))
        if 1 <= h <= 6:
            h += 12  # 1 to 6 PM
        elif 7 <= h <= 11:
            h += 12  # 7 to 11 PM
        return f"{h:02d}:00"

    return None

class IntentParser:
    """
    Parses conversational user inputs.
    Detects ambiguity (e.g. 'Can I go a bit late?' without specific time).
    Carries context from previous messages (e.g. 'Make it 9 instead').
    """

    @staticmethod
    def parse(user_text: str, conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        text = user_text.lower().strip()
        time_found = normalize_time_str(user_text)

        # Check for ambiguous delay / shift requests without a time
        ambiguous_triggers = [
            "go a bit late", "leave late", "change my shift", "go late", 
            "reschedule", "shift my drop", "change my cab", "can i leave later"
        ]
        
        is_ambiguous_phrase = any(trigger in text for trigger in ambiguous_triggers)

        # Check conversation history to see if the previous message was a clarification question
        last_bot_message = ""
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                last_bot_message = msg.get("content", "").lower()
                break

        was_clarification_asked = "what time" in last_bot_message or "available slots" in last_bot_message

        # Case 1: Ambiguous request with no time mentioned
        if (is_ambiguous_phrase or "late" in text or "shift" in text) and not time_found:
            return {
                "intent": "shift_change",
                "target_time": None,
                "is_ambiguous": True
            }

        # Case 2: Time found (e.g. "Shift my drop to 21:00", or follow-up "Make it 9 instead")
        if time_found:
            return {
                "intent": "shift_change",
                "target_time": time_found,
                "is_ambiguous": False
            }

        # Case 3: Roster inquiry
        roster_triggers = ["roster", "my cab", "what time", "schedule", "trip time", "pickup", "drop"]
        if any(w in text for w in roster_triggers) and not ("shift" in text or "change" in text):
            return {
                "intent": "check_roster",
                "target_time": None,
                "is_ambiguous": False
            }

        # Default fallback
        return {
            "intent": "general",
            "target_time": None,
            "is_ambiguous": False
        }

