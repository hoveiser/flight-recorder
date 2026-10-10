"""Build demo/case_files/happy_path.json from a real recorder run.

The published happy-path case file is evidence the contract fetches, so it has to
come from the same code path an actual dispute uses: create a deal, append signed
events, seal, export. Hand-writing it (the v4 file was hand-written) is how the
case file ended up with no chain head at all, which D5 cannot anchor.

The keys are random and thrown away at the end of the run. Nothing here can be
re-signed later, which is the point: the published bytes are a fixed record.

Usage: start the recorder, then
    FLIGHT_RECORDER_URL=http://localhost:8000 python demo/make_case_file.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eth_account import Account
from signed_client import Recorder

DEAL_ID = "demo_happy_002"
DOD = {
    "success_criteria": "Deliver 1000 validated product records with no duplicate IDs and a complete summary report",
    "acceptance": "Client verifies the delivered dataset and report",
}
API_BASE = os.environ.get("FLIGHT_RECORDER_URL", "http://localhost:8000")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_files", "happy_path.json")

SCRIPT = [
    ("REQUEST", {"request": "Collect and validate 1000 product records"}),
    ("RESPONSE", {"accepted": True, "estimated_records": 1000}),
    ("DELIVERY", {"records_delivered": 1000, "duplicate_ids": 0, "summary_report": "complete"}),
    ("VALIDATION", {"success": True, "records_accepted": 1000, "validation_note": "All acceptance criteria fulfilled"}),
]


def main():
    # Random, unfunded, discarded once the file is written.
    client = Account.create()
    worker = Account.create()
    recorder = Recorder(API_BASE)

    created = recorder.call(
        "POST", "/deals",
        {"deal_id": DEAL_ID, "definition_of_done": DOD, "parties": [client.address, worker.address]},
    )
    for index, (event_type, payload) in enumerate(SCRIPT):
        key = client if event_type in ("REQUEST", "VALIDATION") else worker
        recorder.record(key, DEAL_ID, event_type, {"seq": index, **payload})

    head = recorder.seal(client, DEAL_ID)
    case_file = recorder.call("GET", f"/deals/{DEAL_ID}/case-file")

    integrity = case_file["chain_integrity"]
    assert integrity["verification"] == "PASS", integrity
    assert integrity["signature_status"] == "PASS", integrity
    assert integrity["last_hash"] == head, (integrity, head)

    # newline="" keeps the bytes exactly as written: no platform line ending.
    # GitHub serves the committed blob, so the digest that a dispute anchors and
    # the one index.html compares against are only the same number when the file
    # on disk already uses the LF endings that end up in the blob.
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(case_file, indent=2, sort_keys=True) + "\n")

    digest = hashlib.sha256(open(OUT_PATH, "rb").read()).hexdigest()
    print(f"wrote {OUT_PATH}")
    print(f"  events={len(case_file['events'])} head={head}")
    print(f"  agreement_hash={created['agreement_hash']}")
    print(f"  sha256 of the published bytes: {digest}")
    print("  (this digest is what a dispute must anchor as case_file_hash)")
    print("  the two signing keys were random and are now discarded, so these")
    print("  bytes cannot be re-signed or extended by anybody, including this script")


if __name__ == "__main__":
    main()
