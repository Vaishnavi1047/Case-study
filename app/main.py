"""
FastAPI Application for MoveInSync Shift-Change Request Agent.
"""
import uuid
from typing import Dict, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, get_employee_roster, get_shift_request, update_shift_request_status
from app.models import (
    TokenRequest, TokenResponse,
    ChatRequest, ChatResponse,
    AuthenticatedUser, ManagerActionRequest
)
from app.auth import create_access_token, get_current_employee, get_current_manager
from app.agent.graph import run_agent_message

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema and sample data on startup
    init_db()
    yield

app = FastAPI(
    title="MoveInSync Shift-Change Agent API",
    description="Campus Case Study A - Multi-tenant, policy-enforced transport shift change assistant",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store for multi-turn dialogue context: {session_id: [messages]}
# Note: For production, this can be backed by Redis / SQLite checkpointer.
SESSION_STORE: Dict[str, List[Dict[str, str]]] = {}

@app.get("/")
def read_root():
    return {
        "service": "MoveInSync Shift-Change Request Agent",
        "status": "online",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/auth/token", response_model=TokenResponse)
def login_for_access_token(req: TokenRequest):
    """
    Mock JWT issuer for testing and evaluation.
    Issues a cryptographically signed token binding employee_id and company_id.
    """
    token = create_access_token(
        employee_id=req.employee_id,
        company_id=req.company_id,
        role=req.role
    )
    return TokenResponse(
        access_token=token,
        company_id=req.company_id,
        employee_id=req.employee_id
    )

@app.post("/chat", response_model=ChatResponse)
def chat_with_agent(
    req: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_employee)
):
    """
    Primary chat endpoint for employees.
    Company and employee identity are strictly extracted from the JWT token.
    Never accepts tenant identity from request body or prompt.
    """
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:8]}"
    
    # Retrieve existing session context
    history = SESSION_STORE.get(session_id, [])

    # Process conversation turn through LangGraph
    agent_output = run_agent_message(
        company_id=current_user.company_id,
        employee_id=current_user.employee_id,
        message=req.message,
        conversation_history=history
    )

    # Update in-memory session history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": agent_output["reply"]})
    SESSION_STORE[session_id] = history

    return ChatResponse(
        reply=agent_output["reply"],
        session_id=session_id,
        status=agent_output["status"],
        escalated=agent_output["escalated"],
        request_id=agent_output["request_id"]
    )

@app.get("/roster/me")
def get_my_roster(current_user: AuthenticatedUser = Depends(get_current_employee)):
    """
    Test endpoint verifying multi-tenant data isolation.
    An employee from Company A can only retrieve their own company's roster.
    """
    roster = get_employee_roster(current_user.company_id, current_user.employee_id)
    if not roster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No roster found for your employee ID under your company."
        )
    return roster

@app.post("/manager/action")
def manager_decision(
    req: ManagerActionRequest,
    current_manager: AuthenticatedUser = Depends(get_current_manager)
):
    """
    Basic Manager Action Endpoint.
    Allows a transport manager to approve or reject an escalated request.
    (Note: Full automatic resume across process restarts is left basic as a viva extension).
    """
    existing_req = get_shift_request(req.request_id)
    if not existing_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift request {req.request_id} not found."
        )

    # Verify company boundary
    if existing_req.company_id != current_manager.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: You cannot review requests from another company."
        )

    new_status = "APPROVED" if req.action.upper() == "APPROVE" else "REJECTED"
    updated = update_shift_request_status(req.request_id, new_status)

    return {
        "success": True,
        "request_id": req.request_id,
        "previous_status": existing_req.status,
        "new_status": updated.status,
        "notes": req.notes
    }

