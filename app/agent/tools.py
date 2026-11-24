"""
Agent Tools for MoveInSync Shift Change Agent.
All tools strictly scope their operations to the injected company_id and employee_id.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from app import database
from app.policy import check_cutoff_rule, check_cab_capacity
from app.config import get_current_time

def get_my_roster_tool(company_id: str, employee_id: str) -> Dict[str, Any]:
    """Fetches the scheduled roster for the authenticated employee only."""
    try:
        roster = database.get_employee_roster(company_id, employee_id)
        if not roster:
            return {
                "success": False,
                "error": "No scheduled roster found for your account today."
            }
        return {
            "success": True,
            "roster": roster.model_dump()
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Unable to access roster records at this moment."
        }

def check_cab_options_tool(company_id: str, route: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves available cab slots strictly within the employee's company."""
    try:
        cabs = database.get_available_cabs(company_id, route)
        return {
            "success": True,
            "cabs": [
                {
                    "cab_id": c.cab_id,
                    "departure_time": c.departure_time,
                    "route": c.route,
                    "available_seats": c.available_seats,
                    "capacity": c.capacity
                }
                for c in cabs
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Unable to fetch cab options at this moment."
        }

def request_shift_change_tool(
    company_id: str,
    employee_id: str,
    target_time: str,
    current_time_override: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Evaluates policy, checks cab capacity, and applies shift change or escalates to manager.
    Rules are verified in deterministic Python code prior to any database mutation.
    """
    now = current_time_override or get_current_time()

    # 1. Fetch Company Policy & Employee Roster
    company = database.get_company(company_id)
    if not company:
        return {"status": "ERROR", "message": "Company configuration not found."}

    roster = database.get_employee_roster(company_id, employee_id)
    if not roster:
        return {
            "status": "REJECTED",
            "message": "You do not have an active roster today to change."
        }

    original_time = roster.scheduled_time

    # 2. Check Cut-Off Policy Rule
    cutoff_ok, cutoff_msg = check_cutoff_rule(company, original_time, now)
    if not cutoff_ok:
        # Cutoff rule violated: Escalate to manager
        req = database.create_shift_change_request(
            company_id=company_id,
            employee_id=employee_id,
            original_time=original_time,
            requested_time=target_time,
            cab_id=None,
            status="PENDING_APPROVAL",
            reason=cutoff_msg
        )
        return {
            "status": "PENDING_APPROVAL",
            "request_id": req.request_id,
            "original_time": original_time,
            "requested_time": target_time,
            "reason": cutoff_msg,
            "escalated": True,
            "message": (
                f"{cutoff_msg}\n"
                f"Your request has been escalated to your transport manager for approval "
                f"(Request ID: {req.request_id}). You will be notified once reviewed."
            )
        }

    # 3. Check Cab Options & Capacity at target_time
    all_cabs = database.get_available_cabs(company_id, route=roster.route)
    matching_cabs = [c for c in all_cabs if c.departure_time == target_time]

    if not matching_cabs:
        # No cab scheduled at this exact time, provide alternatives
        available_slots = [
            f"{c.departure_time} ({c.available_seats} seats left)"
            for c in all_cabs if c.available_seats > 0
        ]
        return {
            "status": "CAB_UNAVAILABLE",
            "message": (
                f"No cab is scheduled at {target_time} on route {roster.route}. "
                f"Available slots are: {', '.join(available_slots) if available_slots else 'None'}."
            )
        }

    target_cab = matching_cabs[0]
    cap_ok, cap_msg = check_cab_capacity(target_cab)
    if not cap_ok:
        # Cab is full: Suggest nearest slot with free seats
        available_cabs = [c for c in all_cabs if c.available_seats > 0]
        nearest_slots = [f"{c.departure_time} ({c.available_seats} seats left)" for c in available_cabs]
        return {
            "status": "CAB_FULL",
            "message": (
                f"{cap_msg} "
                f"Nearest available slot(s): {', '.join(nearest_slots) if nearest_slots else 'No open cabs today'}."
            )
        }

    # 4. Seat is available and Cutoff passed -> Book seat and confirm change
    booked = database.book_cab_seat(company_id, target_cab.cab_id)
    if not booked:
        return {
            "status": "CAB_FULL",
            "message": f"Seat on cab {target_cab.cab_id} at {target_time} was just taken. Please select another slot."
        }

    # Update roster
    database.update_roster_time(company_id, employee_id, target_time, target_cab.cab_id)

    # Record confirmed request
    req = database.create_shift_change_request(
        company_id=company_id,
        employee_id=employee_id,
        original_time=original_time,
        requested_time=target_time,
        cab_id=target_cab.cab_id,
        status="CONFIRMED",
        reason="Requested within policy and seat confirmed"
    )

    return {
        "status": "CONFIRMED",
        "request_id": req.request_id,
        "original_time": original_time,
        "new_time": target_time,
        "cab_id": target_cab.cab_id,
        "route": target_cab.route,
        "message": (
            f"Your drop has been successfully changed from {original_time} to {target_time} "
            f"(Cab: {target_cab.cab_id}, Route: {target_cab.route}). Confirmed!"
        )
    }
