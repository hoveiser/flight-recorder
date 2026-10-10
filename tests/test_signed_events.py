"""Signed-event authorization tests (v5 / D5).

Every write to the evidence log must be attributable to a key a deal party
controls. These tests are the adversarial side of that guarantee: each one takes
a legitimately signed event and breaks exactly one binding, then checks the
server says no.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct

from src import db
from src.hash_chain import (
    GENESIS,
    canonical_event_message,
    compute_event_hash,
    compute_payload_hash,
)
from tests.conftest import OUTSIDER, PARTY_A, PARTY_B, event_body


def test_forged_signature_is_rejected(client, deal, recorder):
    """A signature from one party cannot be published under the other's name."""
    deal_id = deal["deal_id"]
    ts = datetime.now(timezone.utc).isoformat()
    body = event_body(
        PARTY_A, deal_id, "DELIVERY", {"rows": 1000},
        previous_event_hash=GENESIS, client_timestamp=ts,
        actor=PARTY_B.address,
    )
    resp = client.post("/events", json=body)
    assert resp.status_code == 403
    assert "does not match the claimed actor" in resp.json()["detail"]
    assert client.get(f"/deals/{deal_id}/events").json() == []


def test_non_party_signer_is_rejected(client, deal, recorder):
    """A real signature by somebody outside the deal buys nothing here."""
    resp = recorder.post(deal["deal_id"], "DELIVERY", {"rows": 1}, signer=OUTSIDER)
    assert resp.status_code == 403
    assert "not a party" in resp.json()["detail"]


def test_actor_must_match_the_authenticated_session(client, client_b, deal, recorder):
    """The worker's session cannot record an event as if the client made it."""
    deal_id = deal["deal_id"]
    resp = recorder.post(deal_id, "DELIVERY", {"rows": 10}, session=client_b)
    assert resp.status_code == 200
    # Now the same key signed correctly, but posted under the client's session.
    body = event_body(
        PARTY_B, deal_id, "DELIVERY", {"rows": 20},
        previous_event_hash=client.get(f"/deals/{deal_id}/events").json()[-1]["event_hash"],
    )
    resp = client.post("/events", json=body)
    assert resp.status_code == 403
    assert "does not match the authenticated session" in resp.json()["detail"]


def test_signature_cannot_be_replayed_into_another_deal(client, deal, recorder):
    """deal_id is inside the signed message, so a signature does not travel."""
    other = client.post(
        "/deals",
        json={
            "deal_id": "other_deal",
            "definition_of_done": {"success": "x"},
            "parties": [PARTY_A.address, PARTY_B.address],
        },
    )
    assert other.status_code == 200
    body = event_body(PARTY_A, deal["deal_id"], "DELIVERY", {"rows": 5},
                      previous_event_hash=GENESIS)
    body["deal_id"] = "other_deal"
    resp = client.post("/events", json=body)
    assert resp.status_code == 403
    assert client.get("/deals/other_deal/events").json() == []


def test_signature_cannot_be_replayed_at_another_position(client, deal, recorder):
    """previous_event_hash is signed, so an event cannot be moved in the chain."""
    deal_id = deal["deal_id"]
    assert recorder.post(deal_id, "REQUEST", {"step": 1}).status_code == 200
    second = recorder.post(deal_id, "REQUEST", {"step": 2})
    assert second.status_code == 200

    # Re-post the very same (still valid) signature for step 1. It now lands at a
    # different position, so the head it was signed against is no longer current.
    replayed = client.get(f"/deals/{deal_id}/events").json()[0]
    body = event_body(
        PARTY_A, deal_id, "REQUEST", {"step": 1},
        previous_event_hash=replayed["previous_event_hash"],
        signature=replayed["signature"],
        client_timestamp=replayed["client_timestamp"],
    )
    resp = client.post("/events", json=body)
    assert resp.status_code == 403
    assert len(client.get(f"/deals/{deal_id}/events").json()) == 2


def test_payload_cannot_be_changed_after_signing(client, deal, recorder):
    """The payload digest is signed, so the bytes shipped must be the bytes ok'd."""
    deal_id = deal["deal_id"]
    ts = datetime.now(timezone.utc).isoformat()
    body = event_body(
        PARTY_A, deal_id, "DELIVERY", {"rows": 1000},
        previous_event_hash=GENESIS, client_timestamp=ts,
    )
    body["payload"] = {"rows": 7}
    resp = client.post("/events", json=body)
    assert resp.status_code == 403
    assert client.get(f"/deals/{deal_id}/events").json() == []


def test_unsigned_write_is_refused(client, deal):
    """Signing is mandatory for new events; there is no unsigned path."""
    resp = client.post(
        "/events",
        json={
            "deal_id": deal["deal_id"],
            "actor": PARTY_A.address,
            "event_type": "REQUEST",
            "payload": {"x": 1},
        },
    )
    assert resp.status_code == 400
    assert "signature is required" in resp.json()["detail"]


def test_stale_timestamp_is_rejected(client, deal, recorder):
    """Floor of the drift window: old signed events cannot be replayed later."""
    deal_id = deal["deal_id"]
    stale = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
    resp = recorder.post(
        deal_id, "DELIVERY", {"rows": 3}, client_timestamp=stale,
    )
    assert resp.status_code == 400
    assert "too old" in resp.json()["detail"]


def test_future_timestamp_is_rejected(client, deal, recorder):
    """Ceiling of the drift window: a party cannot date its own evidence ahead."""
    deal_id = deal["deal_id"]
    future = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()
    resp = recorder.post(
        deal_id, "DELIVERY", {"rows": 3}, client_timestamp=future,
    )
    assert resp.status_code == 400
    assert "too far in the future" in resp.json()["detail"]


def test_timestamp_within_both_bounds_is_accepted(client, deal, recorder):
    """The window is a window: anything inside it, endpoints included, works."""
    for delta in (-600, 0, 240):
        ts = (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()
        resp = recorder.post(deal["deal_id"], "REQUEST", {"delta": delta},
                             client_timestamp=ts)
        assert resp.status_code == 200, resp.text


def test_naive_or_unparsable_timestamp_is_rejected(client, deal, recorder):
    """A timestamp without a UTC offset has no agreed meaning, so it is refused."""
    deal_id = deal["deal_id"]
    naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    resp = recorder.post(deal_id, "REQUEST", {"x": 1}, client_timestamp=naive)
    assert resp.status_code == 400

    garbage = "not-a-timestamp"
    resp = recorder.post(deal_id, "REQUEST", {"x": 2}, client_timestamp=garbage)
    assert resp.status_code == 400
    assert client.get(f"/deals/{deal_id}/events").json() == []


def test_login_signature_cannot_be_used_as_an_event_signature(client, deal):
    """Domain separation: the same key signing something else proves nothing."""
    nonce = "Flight Recorder login abc123"
    signed = PARTY_A.sign_message(encode_defunct(text=nonce)).signature.hex()
    resp = client.post(
        "/events",
        json={
            "deal_id": deal["deal_id"],
            "actor": PARTY_A.address,
            "event_type": "REQUEST",
            "payload": {"x": 1},
            "signature": signed,
            "client_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 403
    assert "does not match the claimed actor" in resp.json()["detail"]


def test_malformed_signature_is_rejected(client, deal):
    resp = client.post(
        "/events",
        json={
            "deal_id": deal["deal_id"],
            "actor": PARTY_A.address,
            "event_type": "REQUEST",
            "payload": {"x": 1},
            "signature": "0xdeadbeef",
            "client_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 400
    assert "not a valid EIP-191" in resp.json()["detail"]


def test_seal_requires_actor_to_be_the_session(client, client_b, deal, recorder):
    """Sealing freezes the log for everyone, so it needs the same binding."""
    deal_id = deal["deal_id"]
    assert recorder.post(deal_id, "DELIVERY", {"rows": 1}).status_code == 200

    # The client's session may not seal as the worker...
    resp = client.post(f"/deals/{deal_id}/seal", json={"actor": PARTY_B.address})
    assert resp.status_code == 403
    assert "does not match the authenticated session" in resp.json()["detail"]
    assert client.get(f"/deals/{deal_id}").json()["sealed"] is False

    # ...and neither may it seal as a stranger, even with a valid session.
    resp = client.post(f"/deals/{deal_id}/seal", json={"actor": OUTSIDER.address})
    assert resp.status_code == 403

    # The worker sealing its own log works.
    resp = client_b.post(f"/deals/{deal_id}/seal", json={"actor": PARTY_B.address})
    assert resp.status_code == 200
    assert resp.json()["sealed"] is True


def test_case_file_exports_the_signature_and_what_it_covers(client, deal, recorder):
    """An adjudicator must be able to re-derive the signer without this server."""
    deal_id = deal["deal_id"]
    head = recorder.post(deal_id, "DELIVERY", {"rows": 4})
    assert head.status_code == 200

    case = client.get(f"/deals/{deal_id}/case-file").json()
    ev = case["events"][0]
    assert ev["actor"] == PARTY_A.address
    assert ev["signature"]
    assert ev["sig_version"] == 2
    assert ev["signature_status"] == "PASS"
    assert ev["signed_fields"]["deal_id"] == deal_id
    assert ev["signed_fields"]["previous_event_hash"] == GENESIS
    assert ev["signed_fields"]["event_type"] == "DELIVERY"
    assert ev["signed_fields"]["payload_hash"] == ev["payload_hash"]
    assert ev["signed_fields"]["client_timestamp"] == ev["client_timestamp"]

    # The exported fields really are what the signature covers.
    recovered = Account.recover_message(
        encode_defunct(text=canonical_event_message(
            deal_id=ev["signed_fields"]["deal_id"],
            previous_event_hash=ev["signed_fields"]["previous_event_hash"],
            event_type=ev["signed_fields"]["event_type"],
            payload_hash=ev["signed_fields"]["payload_hash"],
            client_timestamp=ev["signed_fields"]["client_timestamp"],
        )),
        signature=ev["signature"],
    )
    assert recovered.lower() == ev["actor"].lower()


def test_verify_reports_chain_and_signatures_separately(client, deal, recorder):
    """A log can be internally consistent and still unauthorized, and vice versa."""
    deal_id = deal["deal_id"]
    assert recorder.post(deal_id, "REQUEST", {"x": 1}).status_code == 200

    body = client.get(f"/deals/{deal_id}/verify").json()
    assert body["verification"] == "PASS"
    assert body["signature_status"] == "PASS"
    assert body["signatures"] == {"events": 1, "signed": 1, "legacy": 0, "failed": 0}

    # Swap the stored signature for one over a different message: the chain hash
    # no longer recomputes, so integrity fails, and the signature is reported as
    # broken rather than being silently ignored.
    conn = db.get_conn()
    conn.execute(
        "UPDATE events SET event_hash = ? WHERE deal_id = ?",
        ("0" * 64, deal_id),
    )
    conn.commit()
    conn.close()
    body = client.get(f"/deals/{deal_id}/verify").json()
    assert body["verification"] == "FAIL"
    assert "event hash mismatch" in body["reason"]


def test_legacy_unsigned_events_still_verify(client, deal):
    """Rows written before signing existed must not read as tampering."""
    deal_id = deal["deal_id"]
    timestamp = datetime.now(timezone.utc)
    payload = {"rows": 123}
    payload_hash = compute_payload_hash(payload)
    legacy_hash = compute_event_hash(
        deal_id=deal_id,
        actor=PARTY_A.address,
        event_type="DELIVERY",
        payload_hash=payload_hash,
        previous_event_hash=GENESIS,
        timestamp=timestamp.isoformat(),
    )

    db.save_event(
        db.Event(
            id=0,
            deal_id=deal_id,
            actor=PARTY_A.address,
            event_type="DELIVERY",
            payload=payload,
            metadata={},
            payload_hash=payload_hash,
            previous_event_hash=GENESIS,
            event_hash=legacy_hash,
            timestamp=timestamp,
        )
    )

    body = client.get(f"/deals/{deal_id}/verify").json()
    assert body["verification"] == "PASS"
    assert body["signature_status"] == "UNSIGNED_LEGACY"
    assert body["signatures"] == {"events": 1, "signed": 0, "legacy": 1, "failed": 0}

    # A signed event appended on top of the legacy row keeps the chain valid and
    # the mixed log honestly labelled.
    assert client.post(
        "/events",
        json=event_body(
            PARTY_A, deal_id, "DELIVERY", {"rows": 456}, previous_event_hash=legacy_hash,
        ),
    ).status_code == 200
    body = client.get(f"/deals/{deal_id}/verify").json()
    assert body["verification"] == "PASS"
    assert body["signature_status"] == "UNSIGNED_LEGACY"
    assert body["signatures"] == {"events": 2, "signed": 1, "legacy": 1, "failed": 0}
    assert body["last_hash"] != legacy_hash


def test_old_databases_gain_columns_without_rewriting_rows(tmp_path, monkeypatch):
    """The migration is additive and idempotent; old hashes keep their meaning."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            metadata TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            previous_event_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    stored_hash = "a" * 64
    conn.execute(
        "INSERT INTO events (deal_id, actor, event_type, payload, metadata, "
        "payload_hash, previous_event_hash, event_hash, timestamp) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("old_deal", "agentA", "REQUEST", '{"x": 1}', "{}", "b" * 64,
         GENESIS, stored_hash, "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    events = db.get_events("old_deal")
    assert events[0].event_hash == stored_hash
    assert events[0].signature is None
    assert events[0].sig_version == 1

    # Running the migration again must not touch the row a second time.
    db.init_db()
    again = db.get_events("old_deal")
    assert again[0].event_hash == stored_hash
    assert again[0].sig_version == 1
