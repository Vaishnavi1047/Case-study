"""
LangGraph Workflow Definition for MoveInSync Shift Change Agent.
Orchestrates:
1. Intent & Ambiguity Parsing
2. Clarification Branching (context-carried follow-ups)
3. Deterministic Policy Verification & Safe Tool Execution
4. Empathetic, Plain Error & Response Formatting for Employees
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.llm import IntentParser
from app.agent.tools import (
    get_my_roster_tool,
    check_cab_options_tool,
    request_shift_change_tool
)

def parse_input_node(state: AgentState) -> Dict[str, Any]:
    """Extracts intent and detects ambiguity from the current user message."""
    parsed = IntentParser.parse(state.user_input, state.messages)
    return {
        "intent": parsed["intent"],
        "target_time": parsed["target_time"],
        "is_ambiguous": parsed["is_ambiguous"],
        "llm_calls_count": state.llm_calls_count + 1
    }

def handle_ambiguity_node(state: AgentState) -> Dict[str, Any]:
    """Generates a clarifying question and lists available slots."""
    # Read current roster & available slots to guide the user
    cabs_result = check_cab_options_tool(state.company_id)
    available_slots = []
    if cabs_result.get("success"):
        available_slots = [
            f"{c['departure_time']} ({c['available_seats']} seats free)"
            for c in cabs_result["cabs"] if c["available_seats"] > 0
        ]

    slots_str = ", ".join(available_slots) if available_slots else "No other slots available today"

    reply = (
        f"Sure, I can help you shift your drop. What time would you like to depart? "
        f"Available options on your route are: {slots_str}. (e.g. reply 'Make it 9 PM' or '21:00')"
    )

    return {
        "final_reply": reply,
        "status": "CLARIFICATION_NEEDED",
        "is_ambiguous": True
    }

def check_roster_node(state: AgentState) -> Dict[str, Any]:
    """Fetches employee roster and formats status."""
    res = get_my_roster_tool(state.company_id, state.employee_id)
    if not res.get("success"):
        return {
            "final_reply": res.get("error", "No roster scheduled for you today."),
            "status": "ERROR"
        }

    r = res["roster"]
    reply = (
        f"Your current schedule for today ({r['date']}) is a {r['trip_type']} at "
        f"{r['scheduled_time']} on {r['route']} (Cab: {r['cab_id']}, Status: {r['status']})."
    )
    return {
        "final_reply": reply,
        "status": "OK",
        "tool_result": res
    }

def execute_shift_change_node(state: AgentState) -> Dict[str, Any]:
    """Executes the shift change with deterministic rule verification."""
    if not state.target_time:
        return {
            "final_reply": "Please specify the time you would like to move your drop to.",
            "status": "CLARIFICATION_NEEDED"
        }

    res = request_shift_change_tool(
        company_id=state.company_id,
        employee_id=state.employee_id,
        target_time=state.target_time
    )

    status = res.get("status", "ERROR")
    reply = res.get("message", "Something went wrong processing your request.")
    escalated = res.get("escalated", False)
    request_id = res.get("request_id")

    return {
        "final_reply": reply,
        "status": status,
        "escalated": escalated,
        "request_id": request_id,
        "tool_result": res
    }

def fallback_node(state: AgentState) -> Dict[str, Any]:
    """Handles unsupported inputs gracefully without technical jargon."""
    reply = (
        "I am your MoveInSync transport assistant. You can ask me to check your roster today "
        "or request a shift change (for example: 'Shift my drop to 9 PM'). How can I help you?"
    )
    return {
        "final_reply": reply,
        "status": "OK"
    }

# Conditional Routing Logic
def route_after_parse(state: AgentState) -> str:
    if state.is_ambiguous:
        return "handle_ambiguity"
    elif state.intent == "shift_change" and state.target_time:
        return "execute_shift_change"
    elif state.intent == "check_roster":
        return "check_roster"
    else:
        return "fallback"

# Graph Construction
workflow = StateGraph(AgentState)

workflow.add_node("parse_input", parse_input_node)
workflow.add_node("handle_ambiguity", handle_ambiguity_node)
workflow.add_node("check_roster", check_roster_node)
workflow.add_node("execute_shift_change", execute_shift_change_node)
workflow.add_node("fallback", fallback_node)

workflow.set_entry_point("parse_input")

workflow.add_conditional_edges(
    "parse_input",
    route_after_parse,
    {
        "handle_ambiguity": "handle_ambiguity",
        "execute_shift_change": "execute_shift_change",
        "check_roster": "check_roster",
        "fallback": "fallback"
    }
)

workflow.add_edge("handle_ambiguity", END)
workflow.add_edge("execute_shift_change", END)
workflow.add_edge("check_roster", END)
workflow.add_edge("fallback", END)

# Compile LangGraph application
app_graph = workflow.compile()

def run_agent_message(
    company_id: str,
    employee_id: str,
    message: str,
    conversation_history: list = None
) -> Dict[str, Any]:
    """Runs a single conversation turn through the LangGraph agent."""
    initial_state = AgentState(
        company_id=company_id,
        employee_id=employee_id,
        messages=conversation_history or [],
        user_input=message
    )

    try:
        final_state = app_graph.invoke(initial_state)
        return {
            "reply": final_state.get("final_reply", "Request processed."),
            "status": final_state.get("status", "OK"),
            "escalated": final_state.get("escalated", False),
            "request_id": final_state.get("request_id"),
            "llm_calls_count": final_state.get("llm_calls_count", 1)
        }
    except Exception as e:
        # Guarantee no stack traces and graceful degradation
        return {
            "reply": "We are experiencing a temporary transport service delay. Please check back shortly or call the transport desk helpline.",
            "status": "ERROR",
            "escalated": False,
            "request_id": None,
            "llm_calls_count": 0
        }

