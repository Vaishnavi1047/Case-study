"""
Tests for Conversational Agent Flow & Ambiguity Resolution.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token
from app.database import init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db(force_reset=True)

def test_ambiguous_request_triggers_clarification():
    """
    'Can I go a bit late?' does not name a time.
    The agent must NOT guess; it must ask a clarifying question and offer available slots.
    """
    token = create_access_token(employee_id="emp_acme_1", company_id="acme")
    res = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Can I go a bit late?"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLARIFICATION_NEEDED"
    assert "What time would you like to depart?" in data["reply"]
    assert "Available options" in data["reply"]

def test_multi_turn_follow_up_shift_change():
    """
    Context carryover:
    Turn 1: 'Can I go a bit late?' -> Clarification asked
    Turn 2: 'Make it 9 instead' -> Agent understands 9 PM (21:00) and executes change.
    """
    token = create_access_token(employee_id="emp_acme_2", company_id="acme")
    
    # Turn 1
    res1 = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Can I leave later tonight?"}
    )
    assert res1.status_code == 200
    session_id = res1.json()["session_id"]
    assert res1.json()["status"] == "CLARIFICATION_NEEDED"

    # Turn 2 with session_id carried over
    res2 = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Make it 9 PM instead", "session_id": session_id}
    )
    assert res2.status_code == 200
    data2 = res2.json()
    # At default reference time 17:30, 20:00 drop change is 2.5h prior -> passes Acme 2h cutoff
    # 21:00 CAB-A2 has free seats -> Confirmed!
    assert data2["status"] == "CONFIRMED"
    assert "successfully changed" in data2["reply"]
    assert "21:00" in data2["reply"]
