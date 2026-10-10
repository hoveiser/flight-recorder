"""
Demo: Scraper dispute scenario with Flight Recorder + GenEscrow integration

Every event is signed. The recorder binds each write to the address that signed
it, so this script logs in with two throwaway keys (the client and the worker)
and appends each party's events under its own session.
"""
import json
import os
import time
import urllib.request
import urllib.error

from signed_client import Recorder, key_from_seed

FLIGHT_RECORDER_URL = os.environ.get("FLIGHT_RECORDER_URL", "http://localhost:8000")

# Throwaway, deterministic, unfunded. Demo identities only.
CLIENT = key_from_seed("flight-recorder-demo-client")
WORKER = key_from_seed("flight-recorder-demo-worker")


def api_call(method, path, data=None):
    """Helper for the two endpoints that are not identity-bound."""
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
    recorder = Recorder(FLIGHT_RECORDER_URL)
    print("Flight Recorder + GenEscrow Integration Demo")
    print("=" * 60)

    # 1. Create deal. Parties are addresses, because that is what a signature
    # can prove about them.
    deal_id = "scraper_deal_001"
    print(f"\n1. Creating deal: {deal_id}")
    deal = api_call("POST", "/deals", {
        "deal_id": deal_id,
        "definition_of_done": {
            "success_criteria": "1000 valid product records",
            "deadline": "2026-09-10T00:00:00Z",
        },
        "parties": [CLIENT.address, WORKER.address],
    })
    if "agreement_hash" not in deal:
        raise SystemExit(f"could not create deal (is the API running?): {deal}")
    print(f"   Deal created with agreement_hash: {deal['agreement_hash'][:16]}...")

    # 2. Simulate work events, each signed by the party that performed it.
    print("\n2. Recording work events...")

    recorder.record(WORKER, deal_id, "STATE_CHANGE", {"status": "work_started"})
    print(f"   Work started (signed by {WORKER.address[:10]}...)")
    time.sleep(0.3)

    recorder.record(WORKER, deal_id, "DELIVERY", {
        "url": "https://example.com/delivery.json",
        "total_records": 1000,
        "valid_records": 500,
        "invalid_records": 500,
    })
    print("   Delivery submitted (1000 total, 500 valid)")
    time.sleep(0.3)

    recorder.record(CLIENT, deal_id, "VALIDATION", {
        "validation_result": "FAILED",
        "expected": 1000,
        "actual": 500,
        "issue": "50% of records are invalid",
    })
    print("   Validation failed")
    time.sleep(0.3)

    # 3. Seal the log, then file the dispute. Sealing first is what makes the
    # head below final: nothing can be appended after the case file is anchored.
    print("\n3. Sealing the evidence log and filing a dispute...")
    chain_head = recorder.seal(CLIENT, deal_id)
    print(f"   Evidence log sealed at chain_head: {chain_head}")

    api_call("POST", f"/deals/{deal_id}/dispute", {
        "deal_id": deal_id,
        "party": CLIENT.address,
        "claim": "Worker delivered only 500 valid records instead of 1000. "
                 "Contract requires 1000 valid records.",
    })
    print(f"   Dispute filed by {CLIENT.address[:10]}...")
    print("   On-chain this is dispute(deal_id, case_file_url, case_file_hash, chain_head);")
    print("   the head above is the fourth argument, written as the delivery anchor")
    print("   in the same transaction as the dispute itself.")

    # 4. Export case file
    print("\n4. Exporting case file...")
    case_file = api_call("GET", f"/deals/{deal_id}/case-file")
    integrity = case_file["chain_integrity"]
    print(f"   Case file exported:")
    print(f"      - {len(case_file['events'])} events recorded")
    print(f"      - {len(case_file['disputes'])} dispute(s) filed")
    print(f"      - Chain integrity: {integrity['verification']}")
    print(f"      - Signature status: {integrity['signature_status']}")
    print(f"      - Declared head: {integrity['last_hash']}")

    # 5. Simulate GenEscrow adjudication
    print("\n5. GenEscrow adjudication (simulated)...")
    print("   GenEscrow reads case file and evaluates:")

    delivery_event = next(e for e in case_file["events"] if e["event_type"] == "DELIVERY")
    delivered = delivery_event["payload"]["valid_records"]
    required = case_file["definition_of_done"]["success_criteria"]

    print(f"      - Required: {required}")
    print(f"      - Delivered: {delivered} valid records")

    if delivered < 1000:
        print("      - Verdict: REFUNDED")
        print("      - Reason: Worker failed to meet delivery criteria")
        print("\n6. GenEscrow executes refund to client")
    else:
        print("      - Verdict: APPROVED")
        print("      - Reason: Worker met delivery criteria")
        print("\n6. GenEscrow releases payment to worker")

    # 6. Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("   - Flight Recorder: recorded every event, signed by the party that made it")
    print("   - Case file: exported for adjudication, with each signature reproducible")
    print("   - GenEscrow: made a verdict based on that evidence")
    print("   - Outcome: refund to client (evidence-based)")
    print("\nThis demo shows how Flight Recorder + GenEscrow create")
    print("a complete dispute resolution stack:")
    print("   - Flight Recorder = witness (evidence)")
    print("   - GenEscrow = judge (verdict)")
    print("=" * 60)


if __name__ == "__main__":
    main()
