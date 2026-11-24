"""
Tests for Deterministic Policy Engine (Enforced in Code, not LLM prompt).
Tests cut-off rules and cab capacity limits across different companies.
"""
from datetime import datetime
import pytest
from app.models import Company, CabOption
from app.policy import check_cutoff_rule, check_cab_capacity

def test_cutoff_policy_different_per_company():
    """
    Acme has 120-min (2h) cutoff.
    Beta has 240-min (4h) cutoff.
    For a 20:00 drop evaluated at 17:30 (2.5 hours prior):
    - Acme: Allowed (2.5h >= 2.0h)
    - Beta: Rejected (2.5h < 4.0h) -> Policy violation
    """
    current_time = datetime(2026, 11, 24, 17, 30, 0)
    scheduled_drop = "20:00"

    acme_corp = Company(id="acme", name="Acme Corp", cutoff_minutes=120, max_capacity=4)
    beta_corp = Company(id="beta", name="Beta Logistics", cutoff_minutes=240, max_capacity=6)

    # Acme passes cut-off
    acme_ok, acme_msg = check_cutoff_rule(acme_corp, scheduled_drop, current_time)
    assert acme_ok is True
    assert "satisfies" in acme_msg

    # Beta fails cut-off
    beta_ok, beta_msg = check_cutoff_rule(beta_corp, scheduled_drop, current_time)
    assert beta_ok is False
    assert "Cut-off policy violation" in beta_msg
    assert "requires changes to be requested at least 240 minutes" in beta_msg

def test_cutoff_policy_violation_within_window():
    """At 18:30 (1.5 hours before 20:00), Acme's 2-hour rule must trigger violation."""
    late_time = datetime(2026, 11, 24, 18, 30, 0)
    scheduled_drop = "20:00"
    acme_corp = Company(id="acme", name="Acme Corp", cutoff_minutes=120, max_capacity=4)

    is_ok, msg = check_cutoff_rule(acme_corp, scheduled_drop, late_time)
    assert is_ok is False
    assert "Cut-off policy violation" in msg
    assert "Only 90 minutes remain" in msg

def test_cab_capacity_enforcement():
    """Tests that full cabs are rejected deterministically."""
    full_cab = CabOption(
        cab_id="CAB-FULL",
        company_id="acme",
        departure_time="22:00",
        route="SOUTH",
        capacity=4,
        booked_seats=4
    )
    ok, msg = check_cab_capacity(full_cab)
    assert ok is False
    assert "full capacity" in msg

    available_cab = CabOption(
        cab_id="CAB-OPEN",
        company_id="acme",
        departure_time="21:00",
        route="SOUTH",
        capacity=4,
        booked_seats=2
    )
    ok_avail, msg_avail = check_cab_capacity(available_cab)
    assert ok_avail is True
    assert "2 of 4 free" in msg_avail

