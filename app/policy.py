"""
Policy Engine for MoveInSync Shift Change Agent.
All business rules are strictly enforced in deterministic Python code,
never entrusted to LLM prompts or hallucinations.
"""
from datetime import datetime, timedelta
from typing import Tuple, Optional
from app.models import Company, CabOption

def parse_time_today(time_str: str, base_date: datetime) -> datetime:
    """Parses 'HH:MM' string into a datetime on base_date."""
    parts = time_str.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

def check_cutoff_rule(
    company: Company,
    scheduled_time_str: str,
    current_time: datetime
) -> Tuple[bool, str]:
    """
    Checks if the shift-change request meets the company's cut-off policy.
    E.g. Acme Corp requires 120 mins before scheduled drop time.
    Returns: (is_allowed, explanation_message)
    """
    try:
        scheduled_dt = parse_time_today(scheduled_time_str, current_time)
    except Exception as e:
        return False, f"Invalid scheduled time format: {scheduled_time_str}"

    time_diff = scheduled_dt - current_time
    diff_minutes = time_diff.total_seconds() / 60.0

    if diff_minutes < 0:
        return False, (
            f"The scheduled drop at {scheduled_time_str} has already passed or is departing now. "
            f"Changes after departure cannot be processed automatically."
        )

    if diff_minutes < company.cutoff_minutes:
        required_hours = company.cutoff_minutes / 60.0
        return False, (
            f"Cut-off policy violation: {company.name} requires changes to be requested at least "
            f"{int(company.cutoff_minutes)} minutes ({required_hours:.1f} hrs) before scheduled time. "
            f"Only {int(diff_minutes)} minutes remain before {scheduled_time_str}."
        )

    return True, "Request satisfies the cut-off window policy."

def check_cab_capacity(cab: CabOption) -> Tuple[bool, str]:
    """
    Checks if the requested cab has at least one seat available.
    """
    if cab.available_seats <= 0:
        return False, (
            f"Cab {cab.cab_id} scheduled for {cab.departure_time} is at full capacity "
            f"({cab.booked_seats}/{cab.capacity} seats occupied)."
        )
    return True, f"Seat available ({cab.available_seats} of {cab.capacity} free)."

