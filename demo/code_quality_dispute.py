"""
Demo: Code quality dispute scenario with Flight Recorder + GenEscrow integration
"""
import urllib.request
import json
import time
from datetime import datetime

FLIGHT_RECORDER_URL = "http://localhost:8000"


def api_call(method, path, data=None):
    """Helper: make API call with urllib"""
    url = FLIGHT_RECORDER_URL + path
    headers = {"Content-Type": "application/json"}
    
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode("utf-8")}


def main():
    print("🚀 Flight Recorder + GenEscrow Integration Demo (Code Quality)")
    print("=" * 60)
    
    deal_id = "code_deal_001"
    print(f"\n1️⃣  Creating deal: {deal_id}")
    api_call("POST", "/deals", {
        "deal_id": deal_id,
        "definition_of_done": {
            "deliverable": "Python script for data processing",
            "criteria": "Must pass all tests and follow PEP8"
        },
        "parties": ["client", "freelancer"]
    })
    print("   ✓ Deal created")
    
    print(f"\n2️⃣  Recording work events...")
    
    api_call("POST", "/events", {
        "deal_id": deal_id,
        "actor": "freelancer",
        "event_type": "DELIVERY",
        "payload": {
            "url": "https://github.com/freelancer/script.py",
            "files": ["script.py", "tests.py"],
            "tests_passed": False
        }
    })
    print("   ✓ Code delivered")
    time.sleep(0.3)
    
    api_call("POST", "/events", {
        "deal_id": deal_id,
        "actor": "client",
        "event_type": "VALIDATION",
        "payload": {
            "tests_passed": False,
            "pep8_compliant": False,
            "issues": ["Test failures", "PEP8 violations"]
        }
    })
    print("   ✓ Client validation failed")
    time.sleep(0.3)
    
    print(f"\n3️⃣  Filing dispute...")
    api_call("POST", f"/deals/{deal_id}/dispute", {
        "deal_id": deal_id,
        "party": "client",
        "claim": "Code does not pass tests and violates PEP8 standards"
    })
    print("   ✓ Dispute filed")
    
    print(f"\n4️⃣  Exporting case file...")
    case_file = api_call("GET", f"/deals/{deal_id}/case-file")
    print(f"   ✓ Case file exported")
    
    print(f"\n5️⃣  GenEscrow AI adjudication (simulated)...")
    print("   AI reads case file and evaluates code quality:")
    
    validation = next(e for e in case_file['events'] if e['event_type'] == 'VALIDATION')
    
    if not validation['payload']['tests_passed']:
        print("      - Tests: FAILED ❌")
        print("      - PEP8: VIOLATED ❌")
        print("      - AI Verdict: REFUNDED")
        print("\n6️⃣  GenEscrow refunds to client ✅")
    else:
        print("      - Tests: PASSED ✅")
        print("      - AI Verdict: APPROVED")
        print("\n6️⃣  GenEscrow pays freelancer ✅")
    
    print("\n" + "=" * 60)
    print("💡 Flight Recorder provides tamper-proof evidence for AI judge")
    print("=" * 60)


if __name__ == "__main__":
    main()