"""
Tests for Tool Failure & Safe Error Handling.
Ensures that tool or database failures produce human-friendly messages without stack traces.
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token

client = TestClient(app)

def test_database_failure_handled_gracefully():
    """
    Simulate a database failure when fetching roster.
    Agent must return a friendly, actionable message and not expose internal traceback.
    """
    token = create_access_token(employee_id="emp_acme_1", company_id="acme")

    with patch("app.database.get_employee_roster", side_effect=Exception("Database connection timeout")):
        res = client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "What is my roster?"}
        )
        assert res.status_code == 200
        reply = res.json()["reply"]
        # Must not contain Python traceback or raw exception message
        assert "Traceback" not in reply
        assert "Database connection timeout" not in reply
        assert "Unable to access roster records" in reply or "transport service delay" in reply

