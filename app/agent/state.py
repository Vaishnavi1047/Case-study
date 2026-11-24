"""
State definition for LangGraph Shift-Change Agent.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    # Authenticated Identity Context (Injected securely from JWT)
    company_id: str
    employee_id: str

    # Message & Context History
    messages: List[Dict[str, str]] = Field(default_factory=list)
    user_input: str = ""

    # Extracted NLU attributes
    intent: Optional[str] = None  # "check_roster", "shift_change", "general"
    target_time: Optional[str] = None  # e.g. "21:00"
    is_ambiguous: bool = False

    # Tool Execution Results
    tool_result: Optional[Dict[str, Any]] = None

    # Response & Status
    final_reply: str = ""
    status: str = "OK"  # "OK", "CLARIFICATION_NEEDED", "PENDING_APPROVAL", "REJECTED", "ERROR"
    escalated: bool = False
    request_id: Optional[str] = None

    # LLM Call Budget Tracking (Guaranteed <= 4 calls per turn)
    llm_calls_count: int = 0

