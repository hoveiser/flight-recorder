"""
Demo: Code quality dispute scenario with Flight Recorder + GenEscrow integration

Events are signed by the party that made them, and the log is sealed before the
dispute, so the head that gets anchored on-chain describes a record that can no
longer change.
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
FREELANCER = key_from_seed("flight-recorder-demo-freelancer")


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
    print("Flight Recorder + GenEscrow Integration Demo (Code Quality)")
    print("=" * 60)

    deal_id = "code_deal_001"
    print(f"\n1. Creating deal: {deal_id}")
    created = api_call("POST", "/deals", {
        "deal_id": deal_id,
        "definition_of_done": {
            "deliverable": "Python script for data processing",
            "criteria": "Must pass all tests and follow PEP8",
        },
        "parties": [CLIENT.address, FREELANCER.address],
    })
    if "agreement_hash" not in created:
        raise SystemExit(f"could not create deal (is the API running?): {created}")
    print("   Deal created")

    print("\n2. Recording work events...")

    recorder.record(FREELANCER, deal_id, "DELIVERY", {
        "url": "https://github.com/freelancer/script.py",
        "files": ["script.py", "tests.py"],
        "tests_passed": False,
    })
    print(f"   Code delivered (signed by {FREELANCER.address[:10]}...)")
    time.sleep(0.3)

    recorder.record(CLIENT, deal_id, "VALIDATION", {
        "tests_passed": False,
        "pep8_compliant": False,
        "issues": ["Test failures", "PEP8 violations"],
    })
    print("   Client validation failed")
    time.sleep(0.3)

    print("\n3. Sealing the log and filing a dispute...")
    chain_head = recorder.seal(CLIENT, deal_id)
    print(f"   Evidence log sealed at chain_head: {chain_head}")
    api_call("POST", f"/deals/{deal_id}/dispute", {
        "deal_id": deal_id,
        "party": CLIENT.address,
        "claim": "Code does not pass tests and violates PEP8 standards",
    })
    print("   Dispute filed")

    print("\n4. Exporting case file...")
    case_file = api_call("GET", f"/deals/{deal_id}/case-file")
    integrity = case_file["chain_integrity"]
    print("   Case file exported")
    print(f"      - Chain integrity: {integrity['verification']}")
    print(f"      - Signature status: {integrity['signature_status']}")

    print("\n5. GenEscrow AI adjudication (simulated)...")
    print("   AI reads case file and evaluates code quality:")

    validation = next(e for e in case_file["events"] if e["event_type"] == "VALIDATION")

    if not validation["payload"]["tests_passed"]:
        print("      - Tests: FAILED")
        print("      - PEP8: VIOLATED")
        print("      - AI Verdict: REFUNDED")
        print("\n6. GenEscrow refunds to client")
    else:
        print("      - Tests: PASSED")
        print("      - AI Verdict: APPROVED")
        print("\n6. GenEscrow pays freelancer")

    print("\n" + "=" * 60)
    print("Flight Recorder provides tamper-proof, signer-attributable evidence")
    print("for an AI judge.")
    print("=" * 60)


if __name__ == "__main__":
    main()
