"""
Evaluation Runner for MoveInSync Shift-Change Agent.
Reads eval/eval_set.jsonl, executes each test case against the API/agent,
updates the actual and pass fields, and prints a formatted summary.
"""
import json
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token
from app.database import init_db

client = TestClient(app)

def run_eval():
    eval_file = os.path.join(os.path.dirname(__file__), "eval_set.jsonl")
    if not os.path.exists(eval_file):
        print(f"Error: {eval_file} not found.")
        return

    # Reset DB to ensure fresh, consistent seed data for evaluation run
    init_db(force_reset=True)

    with open(eval_file, "r") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    passed_count = 0
    total_count = len(cases)
    updated_cases = []

    print("\n" + "="*80)
    print(f"  MoveInSync Shift-Change Request Agent - Evaluation Run")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(f"{'ID':<10} | {'Expected':<22} | {'Actual Status/Reply':<25} | {'Result':<8}")
    print("-" * 80)

    for case in cases:
        case_id = case["id"]
        inp = case["input"]
        expected = case["expected"]

        # Generate JWT for the test user
        token = create_access_token(
            employee_id=inp["employee_id"],
            company_id=inp["company_id"]
        )

        # Call chat API
        response = client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": inp["message"]}
        )

        res_data = response.json()
        status = res_data.get("status", "UNKNOWN")
        reply = res_data.get("reply", "")

        is_passed = False
        actual_summary = status

        if expected == "STATUS_OK" and status == "OK":
            is_passed = True
        elif expected == status:
            is_passed = True
        elif expected in reply:
            is_passed = True
            actual_summary = f"Found '{expected}'"

        if is_passed:
            passed_count += 1
            result_str = "PASS"
        else:
            result_str = "FAIL"

        case["actual"] = actual_summary
        case["pass"] = is_passed
        updated_cases.append(case)

        print(f"{case_id:<10} | {expected:<22} | {actual_summary[:25]:<25} | {result_str:<8}")

    # Write updated cases back to eval_set.jsonl
    with open(eval_file, "w") as f:
        for c in updated_cases:
            f.write(json.dumps(c) + "\n")

    print("=" * 80)
    print(f"  Summary: {passed_count}/{total_count} cases passed ({(passed_count/total_count)*100:.1f}%)")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_eval()
