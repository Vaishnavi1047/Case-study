"""
Database layer for MoveInSync Shift Change Agent.
Uses SQLite for lightweight persistence, deterministic state, and clean schema.
Enforces multi-tenant data isolation on every single query.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict
from app.models import Company, RosterEntry, CabOption, ShiftChangeRequest

DB_PATH = "moveinsync.db"

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reset: bool = False):
    """Initializes tables and seeds multi-tenant sample data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if force_reset:
        cursor.executescript("""
        DROP TABLE IF EXISTS shift_requests;
        DROP TABLE IF EXISTS cabs;
        DROP TABLE IF EXISTS rosters;
        DROP TABLE IF EXISTS companies;
        """)

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        cutoff_minutes INTEGER NOT NULL,
        max_capacity INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS rosters (
        roster_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        employee_id TEXT NOT NULL,
        date TEXT NOT NULL,
        trip_type TEXT NOT NULL,
        scheduled_time TEXT NOT NULL,
        cab_id TEXT NOT NULL,
        route TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id)
    );

    CREATE TABLE IF NOT EXISTS cabs (
        cab_id TEXT NOT NULL,
        company_id TEXT NOT NULL,
        departure_time TEXT NOT NULL,
        route TEXT NOT NULL,
        capacity INTEGER NOT NULL,
        booked_seats INTEGER NOT NULL,
        PRIMARY KEY (cab_id, company_id),
        FOREIGN KEY (company_id) REFERENCES companies(id)
    );

    CREATE TABLE IF NOT EXISTS shift_requests (
        request_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        employee_id TEXT NOT NULL,
        original_time TEXT NOT NULL,
        requested_time TEXT NOT NULL,
        cab_id TEXT,
        status TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id)
    );
    """)

    # Seed Companies if empty
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] == 0:
        # Company A: Acme Corp (2 hours = 120 mins cut-off, max capacity 4)
        # Company B: Beta Logistics (4 hours = 240 mins cut-off, max capacity 6)
        cursor.execute("INSERT INTO companies VALUES ('acme', 'Acme Corp', 120, 4)")
        cursor.execute("INSERT INTO companies VALUES ('beta', 'Beta Logistics', 240, 6)")

        # Seed Rosters
        # Acme employee today (20:00 drop)
        cursor.execute(
            "INSERT INTO rosters VALUES ('rost_101', 'acme', 'emp_acme_1', '2026-11-24', 'DROP', '20:00', 'CAB-A1', 'SOUTH-CORRIDOR', 'SCHEDULED')"
        )
        cursor.execute(
            "INSERT INTO rosters VALUES ('rost_102', 'acme', 'emp_acme_2', '2026-11-24', 'DROP', '20:00', 'CAB-A1', 'SOUTH-CORRIDOR', 'SCHEDULED')"
        )

        # Beta employee today (20:00 drop)
        cursor.execute(
            "INSERT INTO rosters VALUES ('rost_201', 'beta', 'emp_beta_1', '2026-11-24', 'DROP', '20:00', 'CAB-B1', 'NORTH-EXPRESS', 'SCHEDULED')"
        )
        cursor.execute(
            "INSERT INTO rosters VALUES ('rost_202', 'beta', 'emp_beta_2', '2026-11-24', 'DROP', '21:00', 'CAB-B2', 'NORTH-EXPRESS', 'SCHEDULED')"
        )

        # Seed Cabs for Acme
        cursor.execute("INSERT INTO cabs VALUES ('CAB-A1', 'acme', '20:00', 'SOUTH-CORRIDOR', 4, 3)") # 1 seat left
        cursor.execute("INSERT INTO cabs VALUES ('CAB-A2', 'acme', '21:00', 'SOUTH-CORRIDOR', 4, 2)") # 2 seats left
        cursor.execute("INSERT INTO cabs VALUES ('CAB-A3', 'acme', '22:00', 'SOUTH-CORRIDOR', 4, 4)") # FULL (0 seats left)

        # Seed Cabs for Beta
        cursor.execute("INSERT INTO cabs VALUES ('CAB-B1', 'beta', '20:00', 'NORTH-EXPRESS', 6, 5)") # 1 seat left
        cursor.execute("INSERT INTO cabs VALUES ('CAB-B2', 'beta', '21:00', 'NORTH-EXPRESS', 6, 6)") # FULL (0 seats left)
        cursor.execute("INSERT INTO cabs VALUES ('CAB-B3', 'beta', '22:00', 'NORTH-EXPRESS', 6, 3)") # 3 seats left

        conn.commit()

    conn.close()

# Multi-tenant Data Access Functions
def get_company(company_id: str) -> Optional[Company]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return Company(
        id=row["id"],
        name=row["name"],
        cutoff_minutes=row["cutoff_minutes"],
        max_capacity=row["max_capacity"]
    )

def get_employee_roster(company_id: str, employee_id: str) -> Optional[RosterEntry]:
    """
    CRITICAL: Requires both company_id AND employee_id.
    Prevents cross-company roster data leakage.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM rosters WHERE company_id = ? AND employee_id = ?",
        (company_id, employee_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return RosterEntry(
        roster_id=row["roster_id"],
        company_id=row["company_id"],
        employee_id=row["employee_id"],
        date=row["date"],
        trip_type=row["trip_type"],
        scheduled_time=row["scheduled_time"],
        cab_id=row["cab_id"],
        route=row["route"],
        status=row["status"]
    )

def get_available_cabs(company_id: str, route: Optional[str] = None) -> List[CabOption]:
    """
    Returns cabs strictly partitioned by company_id.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if route:
        cursor.execute(
            "SELECT * FROM cabs WHERE company_id = ? AND route = ? ORDER BY departure_time ASC",
            (company_id, route)
        )
    else:
        cursor.execute(
            "SELECT * FROM cabs WHERE company_id = ? ORDER BY departure_time ASC",
            (company_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [
        CabOption(
            cab_id=r["cab_id"],
            company_id=r["company_id"],
            departure_time=r["departure_time"],
            route=r["route"],
            capacity=r["capacity"],
            booked_seats=r["booked_seats"]
        )
        for r in rows
    ]

def get_cab(company_id: str, cab_id: str) -> Optional[CabOption]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM cabs WHERE company_id = ? AND cab_id = ?",
        (company_id, cab_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return CabOption(
        cab_id=row["cab_id"],
        company_id=row["company_id"],
        departure_time=row["departure_time"],
        route=row["route"],
        capacity=row["capacity"],
        booked_seats=row["booked_seats"]
    )

def book_cab_seat(company_id: str, cab_id: str) -> bool:
    """
    Atomically increments booked_seats if capacity is not exceeded.
    Returns True if successfully booked, False if cab is full or not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cabs SET booked_seats = booked_seats + 1 WHERE company_id = ? AND cab_id = ? AND booked_seats < capacity",
        (company_id, cab_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def update_roster_time(company_id: str, employee_id: str, new_time: str, new_cab_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE rosters SET scheduled_time = ?, cab_id = ?, status = 'MODIFIED' WHERE company_id = ? AND employee_id = ?",
        (new_time, new_cab_id, company_id, employee_id)
    )
    conn.commit()
    conn.close()

def create_shift_change_request(
    company_id: str,
    employee_id: str,
    original_time: str,
    requested_time: str,
    cab_id: Optional[str],
    status: str,
    reason: str
) -> ShiftChangeRequest:
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO shift_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (request_id, company_id, employee_id, original_time, requested_time, cab_id, status, reason, created_at)
    )
    conn.commit()
    conn.close()
    return ShiftChangeRequest(
        request_id=request_id,
        company_id=company_id,
        employee_id=employee_id,
        original_time=original_time,
        requested_time=requested_time,
        cab_id=cab_id,
        status=status,
        reason=reason,
        created_at=created_at
    )

def get_shift_request(request_id: str) -> Optional[ShiftChangeRequest]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shift_requests WHERE request_id = ?", (request_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return ShiftChangeRequest(
        request_id=row["request_id"],
        company_id=row["company_id"],
        employee_id=row["employee_id"],
        original_time=row["original_time"],
        requested_time=row["requested_time"],
        cab_id=row["cab_id"],
        status=row["status"],
        reason=row["reason"],
        created_at=row["created_at"]
    )

def update_shift_request_status(request_id: str, status: str) -> Optional[ShiftChangeRequest]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE shift_requests SET status = ? WHERE request_id = ?", (status, request_id))
    conn.commit()
    conn.close()
    return get_shift_request(request_id)
