"""Regression tests for the hardening findings closed in the D5 round.

Each test names the finding it exists for, so the matrix in AUDIT.md can point at
a test instead of at a paragraph. They are kept apart from the feature suites
because they are about the API's guards rather than its behaviour. Finding numbers
continue the numbering already used in AUDIT.md (F1 to F15 are the v3 audit), so
these are F16 upward.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src import db
from src.models import Deal, Event
from tests.conftest import PARTY_A, PARTY_B, OUTSIDER, SessionClient, event_body

# The demo clients are part of the shipped surface (they are what an evaluator
# runs), so their own guards get tested here rather than left to luck.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo"))


# F16: the off-chain dispute record was the last write in the API that trusted a
# typed-in identity instead of a session.
def test_dispute_requires_a_session(client, deal):
    anon = TestClient(app)
    resp = anon.post(
        f"/deals/{deal['deal_id']}/dispute",
        json={"deal_id": deal["deal_id"], "party": PARTY_A.address, "claim": "not delivered"},
    )
    assert resp.status_code == 401
    assert client.get(f"/deals/{deal['deal_id']}/disputes").json() == []


def test_dispute_party_must_be_the_authenticated_session(client, deal):
    """PARTY_A's session cannot file a dispute in PARTY_B's name."""
    resp = client.post(
        f"/deals/{deal['deal_id']}/dispute",
        json={"deal_id": deal["deal_id"], "party": PARTY_B.address, "claim": "spoken for"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "party does not match the authenticated session"
    assert client.get(f"/deals/{deal['deal_id']}/disputes").json() == []


def test_dispute_by_a_party_session_still_works(client_b, deal):
    resp = client_b.post(
        f"/deals/{deal['deal_id']}/dispute",
        json={"deal_id": deal["deal_id"], "party": PARTY_B.address, "claim": "only half delivered"},
    )
    assert resp.status_code == 200
    disputes = client_b.get(f"/deals/{deal['deal_id']}/disputes").json()
    assert [d["party"] for d in disputes] == [PARTY_B.address]


def test_dispute_rejects_a_signer_who_is_not_a_party(client, deal):
    """A real session for an address that is on no part of this deal."""
    stranger = SessionClient(app, OUTSIDER.address)
    resp = stranger.post(
        f"/deals/{deal['deal_id']}/dispute",
        json={"deal_id": deal["deal_id"], "party": OUTSIDER.address, "claim": "x"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Only a party to the deal may file a dispute"
    assert client.get(f"/deals/{deal['deal_id']}/disputes").json() == []


# F17: every caller-supplied field is bounded before it is hashed, recovered or
# stored. An unbounded field is work the server accepts for free.
def test_oversized_event_payload_is_refused(recorder, deal, client):
    resp = recorder.post(deal["deal_id"], "DELIVERY", {"blob": "x" * 40000})
    assert resp.status_code == 400
    assert "payload is larger than" in resp.json()["detail"]
    assert client.get(f"/deals/{deal['deal_id']}/events").json() == []


def test_oversized_event_metadata_is_refused(recorder, deal, client):
    resp = recorder.post(deal["deal_id"], "DELIVERY", {"rows": 1}, metadata={"blob": "y" * 12000})
    assert resp.status_code == 400
    assert "metadata is larger than" in resp.json()["detail"]
    assert client.get(f"/deals/{deal['deal_id']}/events").json() == []


def test_oversized_definition_of_done_is_refused(client):
    resp = client.post(
        "/deals",
        json={
            "deal_id": "big_dod",
            "definition_of_done": {"criteria": "z" * 9000},
            "parties": [PARTY_A.address],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("definition_of_done is larger than")


def test_deal_id_longer_than_the_contract_allows_is_refused(client):
    """The contract asserts len(deal_id) <= 100; the API must not accept what the
    contract will later refuse, or evidence exists that can never be judged."""
    resp = client.post(
        "/deals",
        json={"deal_id": "d" * 101, "definition_of_done": {"a": 1}, "parties": [PARTY_A.address]},
    )
    assert resp.status_code == 422


def test_parties_must_be_addresses(client):
    """A name cannot be proven, and a party list of names is what made the old
    actor field a self-report."""
    resp = client.post(
        "/deals",
        json={"deal_id": "named_parties", "definition_of_done": {"a": 1}, "parties": ["client", "worker"]},
    )
    assert resp.status_code == 422
    assert db.get_deal("named_parties") is None


def test_too_many_parties_is_refused(client):
    resp = client.post(
        "/deals",
        json={
            "deal_id": "crowd",
            "definition_of_done": {"a": 1},
            "parties": [PARTY_A.address] * 25,
        },
    )
    assert resp.status_code == 422


def test_oversized_dispute_claim_is_refused(client, deal):
    resp = client.post(
        f"/deals/{deal['deal_id']}/dispute",
        json={"deal_id": deal["deal_id"], "party": PARTY_A.address, "claim": "a" * 2001},
    )
    assert resp.status_code == 422
    assert client.get(f"/deals/{deal['deal_id']}/disputes").json() == []


def test_oversized_signature_is_refused_before_any_recovery(recorder, deal, client):
    body = event_body(PARTY_A, deal["deal_id"], "DELIVERY", {"rows": 1})
    body["signature"] = "0" * 4000
    resp = client.post("/events", json=body)
    assert resp.status_code == 422
    assert client.get(f"/deals/{deal['deal_id']}/events").json() == []


def test_login_rejects_a_malformed_address_and_an_oversized_nonce(client):
    resp = client.post(
        "/api/auth/verify",
        json={"address": "not-an-address", "signature": "0" * 130, "nonce": "n"},
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/auth/verify",
        json={"address": PARTY_A.address, "signature": "0" * 130, "nonce": "n" * 500},
    )
    assert resp.status_code == 422


# F18: bounds on input must not turn into data loss. Rows written before a limit
# existed stay readable, otherwise hardening the API silently deletes history.
def test_history_written_before_the_limits_still_reads(client):
    deal_id = "legacy_hardening"
    db.save_deal(Deal(
        deal_id=deal_id,
        definition_of_done={"success": "1000 rows"},
        parties=["client", "worker"],
        agreement_hash="0" * 64,
        created_at=datetime.now(timezone.utc),
    ))
    db.save_event(Event(
        id=0,
        deal_id=deal_id,
        actor="client",
        event_type="REQUEST",
        payload={"request": "legacy"},
        metadata={},
        payload_hash="1" * 64,
        previous_event_hash="GENESIS",
        event_hash="2" * 64,
        timestamp=datetime.now(timezone.utc),
        sig_version=1,
    ))

    assert client.get(f"/deals/{deal_id}").status_code == 200
    events = client.get(f"/deals/{deal_id}/events")
    assert events.status_code == 200
    assert events.json()[0]["actor"] == "client"
    case = client.get(f"/deals/{deal_id}/case-file")
    assert case.status_code == 200
    assert case.json()["parties"] == ["client", "worker"]


# F19: the demo client is handed FLIGHT_RECORDER_URL from the environment. A tool
# that opens any scheme it is given is a file reader with extra steps.
def test_demo_client_refuses_a_non_http_url():
    from signed_client import api_url

    assert api_url("http://localhost:8000", "/deals") == "http://localhost:8000/deals"
    assert api_url("https://recorder.example", "/deals").startswith("https://recorder.example/")
    with pytest.raises(SystemExit):
        api_url("file:///tmp", "/deals")
    with pytest.raises(SystemExit):
        api_url("gopher://example", "/deals")
