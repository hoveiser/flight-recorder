"""
Demo: Scraper dispute scenario with Flight Recorder + GenEscrow integration
"""
import urllib.request
import urllib.error
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
    print("🚀 Flight Recorder + GenEscrow Integration Demo")
    print("=" * 60)
    
    # 1. Create deal
    deal_id = "scraper_deal_001"
    print(f"\n1️⃣  Creating deal: {deal_id}")
    deal = api_call("POST", "/deals", {
        "deal_id": deal_id,
        "definition_of_done": {
            "success_criteria": "1000 valid product records",
            "deadline": "2026-09-10T00:00:00Z"
        },
        "parties": ["agentA", "agentB"]
    })
    print(f"   ✓ Deal created with agreement_hash: {deal['agreement_hash'][:16]}...")
    
    # 2. Simulate work events
    print(f"\n2️⃣  Recording work events...")
    
    api_call("POST", "/events", {
        "deal_id": deal_id,
        "actor": "agentB",
        "event_type": "STATE_CHANGE",
        "payload": {"status": "work_started", "timestamp": datetime.utcnow().isoformat()}
    })
    print("   ✓ Work started")
    time.sleep(0.3)
    
    api_call("POST", "/events", {
        "deal_id": deal_id,
        "actor": "agentB",
        "event_type": "DELIVERY",
        "payload": {
            "url": "https://example.com/delivery.json",
            "total_records": 1000,
            "valid_records": 500,
            "invalid_records": 500
        }
    })
    print("   ✓ Delivery submitted (1000 total, 500 valid)")
    time.sleep(0.3)
    
    api_call("POST", "/events", {
        "deal_id": deal_id,
        "actor": "agentA",
        "event_type": "VALIDATION",
        "payload": {
            "validation_result": "FAILED",
            "expected": 1000,
            "actual": 500,
            "issue": "50% of records are invalid"
        }
    })
    print("   ✓ Validation failed")
    time.sleep(0.3)
    
    # 3. File dispute
    print(f"\n3️⃣  Filing dispute...")
    api_call("POST", f"/deals/{deal_id}/dispute", {
        "deal_id": deal_id,
        "party": "agentA",
        "claim": "Worker delivered only 500 valid records instead of 1000. Contract requires 1000 valid records."
    })
    print("   ✓ Dispute filed by agentA")
    
    # 4. Export case file
    print(f"\n4️⃣  Exporting case file...")
    case_file = api_call("GET", f"/deals/{deal_id}/case-file")
    print(f"   ✓ Case file exported:")
    print(f"      - {len(case_file['events'])} events recorded")
    print(f"      - {len(case_file['disputes'])} dispute(s) filed")
    print(f"      - Chain integrity: {case_file['chain_integrity']['verification']}")
    
    # 5. Simulate GenEscrow adjudication
    print(f"\n5️⃣  GenEscrow adjudication (simulated)...")
    print("   GenEscrow reads case file and evaluates:")
    
    delivery_event = next(e for e in case_file['events'] if e['event_type'] == 'DELIVERY')
    delivered = delivery_event['payload']['valid_records']
    required = case_file['definition_of_done']['success_criteria']
    
    print(f"      - Required: {required}")
    print(f"      - Delivered: {delivered} valid records")
    
    if delivered < 1000:
        print(f"      - Verdict: REFUNDED ❌")
        print(f"      - Reason: Worker failed to meet delivery criteria")
        print(f"\n6️⃣  GenEscrow executes refund to client ✅")
    else:
        print(f"      - Verdict: APPROVED ✅")
        print(f"      - Reason: Worker met delivery criteria")
        print(f"\n6️⃣  GenEscrow releases payment to worker ✅")
    
    # 6. Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   - Flight Recorder: ✅ Recorded all events tamper-proof")
    print(f"   - Case file: ✅ Exported for adjudication")
    print(f"   - GenEscrow: ✅ Made verdict based on evidence")
    print(f"   - Outcome: ✅ Refund to client (evidence-based)")
    print("\n💡 This demo shows how Flight Recorder + GenEscrow create")
    print("   a complete dispute resolution stack:")
    print("   - Flight Recorder = witness (evidence)")
    print("   - GenEscrow = judge (verdict)")
    print("=" * 60)


if __name__ == "__main__":
    main()