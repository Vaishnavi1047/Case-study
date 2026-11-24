from typing import Optional, List
from pydantic import BaseModel, Field

class Company(BaseModel):
    id: str
    name: str
    cutoff_minutes: int
    max_capacity: int

class RosterEntry(BaseModel):
    roster_id: str
    company_id: str
    employee_id: str
    date: str
    trip_type: str  # DROP or PICKUP
    scheduled_time: str  # HH:MM format e.g. "20:00"
    cab_id: str
    route: str
    status: str  # SCHEDULED, CANCELLED, MODIFIED

class CabOption(BaseModel):
    cab_id: str
    company_id: str
    departure_time: str  # HH:MM format e.g. "21:00"
    route: str
    capacity: int
    booked_seats: int
    
    @property
    def available_seats(self) -> int:
        return max(0, self.capacity - self.booked_seats)

class ShiftChangeRequest(BaseModel):
    request_id: str
    company_id: str
    employee_id: str
    original_time: str
    requested_time: str
    cab_id: Optional[str] = None
    status: str  # CONFIRMED, REJECTED, PENDING_APPROVAL
    reason: str
    created_at: str

class TokenRequest(BaseModel):
    employee_id: str
    company_id: str
    role: str = "employee"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company_id: str
    employee_id: str

class AuthenticatedUser(BaseModel):
    employee_id: str
    company_id: str
    role: str = "employee"

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    status: str  # OK, CLARIFICATION_NEEDED, PENDING_APPROVAL, REJECTED, ERROR
    escalated: bool = False
    request_id: Optional[str] = None

class ManagerActionRequest(BaseModel):
    request_id: str
    action: str  # APPROVE or REJECT
    notes: Optional[str] = None

