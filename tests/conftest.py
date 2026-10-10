import os
import sys
import hashlib
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set temp DB BEFORE importing app
os.environ["FLIGHT_RECORDER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient
from src.main import app
from src import db
from src.hash_chain import GENESIS, canonical_event_message, compute_payload_hash

# Throwaway keys only. Two of them are the deal parties, the third one never
# appears in any deal's party list, so it can stand in for "a valid signature
# from somebody who has no business here".
#
# They are derived from a fixed seed rather than created at random: the same
# addresses must come out of every import of this module (pytest imports the
# rootdir conftest under one name and a test module can import it under
# another), and no key material belongs in the repository either way.
def _throwaway_account(seed: str) -> Account:
    return Account.from_key(hashlib.sha256(seed.encode("utf-8")).hexdigest())


PARTY_A = _throwaway_account("flight-recorder-test-party-a")
PARTY_B = _throwaway_account("flight-recorder-test-party-b")
OUTSIDER = _throwaway_account("flight-recorder-test-outsider")

KEYS = {k.address.lower(): k for k in (PARTY_A, PARTY_B, OUTSIDER)}


def account_for(address: str) -> Account:
    """Look up the throwaway key for an address, so a fixture can say "sign as
    the party this session belongs to" without hard-coding which one it is."""
    return KEYS[address.lower()]

SESSION_LIFETIME = timedelta(days=1)


def token_for(address: str) -> str:
    """A session token bound to `address`, seeded through the real store.

    Sessions live in SQLite exactly as they do in production, so binding an
    actor to a session is tested against the persistence path rather than a
    mock. One token per address keeps the fixture honest: a request carries the
    identity of whoever holds the key, not a shared "test" identity that could
    claim to be anybody.
    """
    token = f"session-{address.lower()}"
    db.store_session(token, address, datetime.now(timezone.utc) + SESSION_LIFETIME)
    return token


class SessionClient(TestClient):
    """TestClient that authenticates as one address.

    The Authorization header is filled in automatically for the endpoints that
    require a session, so a test cannot accidentally exercise an unauthenticated
    path while it is trying to test an authorized one.
    """

    def __init__(self, application, address: str, **kwargs):
        super().__init__(application, **kwargs)
        self.address = address
        self.token = token_for(address)

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        path = str(url).split("?")[0]
        needs_session = method.upper() == "POST" and (
            path == "/events" or path.rstrip("/").endswith("/seal")
        )
        if needs_session and not any(key.lower() == "authorization" for key in headers):
            headers["Authorization"] = f"Bearer {self.token}"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def sign_event(
    signer: Account,
    deal_id: str,
    previous_event_hash: str,
    event_type: str,
    payload: dict,
    client_timestamp: str,
) -> str:
    """The EIP-191 signature an actor must present with a write."""
    message = canonical_event_message(
        deal_id=deal_id,
        previous_event_hash=previous_event_hash,
        event_type=event_type,
        payload_hash=compute_payload_hash(payload),
        client_timestamp=client_timestamp,
    )
    return signer.sign_message(encode_defunct(text=message)).signature.hex()


def event_body(
    signer: Account,
    deal_id: str,
    event_type: str,
    payload: dict,
    *,
    previous_event_hash: str = GENESIS,
    actor: str | None = None,
    client_timestamp: str | None = None,
    signature: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build an /events body, with every signed field overridable separately.

    Each keyword is the handle a test needs to attack exactly one binding:
    `actor` for a claim that does not match the signer, `previous_event_hash`
    for a replay at another position, `client_timestamp` for a stale or future
    clock, and `signature` for a signature made over a different payload or deal.
    """
    ts = client_timestamp or datetime.now(timezone.utc).isoformat()
    if signature is None:
        signature = sign_event(signer, deal_id, previous_event_hash, event_type, payload, ts)
    body = {
        "deal_id": deal_id,
        "actor": actor or signer.address,
        "event_type": event_type,
        "payload": payload,
        "signature": signature,
        "client_timestamp": ts,
    }
    if metadata is not None:
        body["metadata"] = metadata
    return body


class Recorder:
    """Signs and posts events the way a real client has to: read the head, sign
    against it, post, and retry if somebody else appended in the meantime."""

    def __init__(self, client: SessionClient):
        self.client = client

    def head(self, deal_id: str) -> str:
        resp = self.client.get(f"/deals/{deal_id}/events")
        events = resp.json() if resp.status_code == 200 else []
        return events[-1]["event_hash"] if events else GENESIS

    def post(
        self,
        deal_id: str,
        event_type: str = "REQUEST",
        payload: dict | None = None,
        *,
        signer: Account | None = None,
        session: SessionClient | None = None,
        **overrides,
    ):
        client = session or self.client
        key = signer or account_for(client.address)
        payload = {"i": 0} if payload is None else payload
        body = event_body(
            key,
            deal_id,
            event_type,
            payload,
            previous_event_hash=overrides.pop("previous_event_hash", None) or self.head(deal_id),
            **overrides,
        )
        return client.post("/events", json=body)

    def post_retrying(
        self,
        deal_id: str,
        event_type: str = "REQUEST",
        payload: dict | None = None,
        *,
        signer: Account | None = None,
        session: SessionClient | None = None,
        attempts: int = 20,
    ):
        """Post under contention: a rejected position is re-signed against the
        head that actually won, which is what a correct client must do."""
        last = None
        for _ in range(attempts):
            last = self.post(deal_id, event_type, payload, signer=signer, session=session)
            if last.status_code == 200:
                return last
        raise AssertionError(f"event never accepted: {last.status_code} {last.text}")


@pytest.fixture
def client():
    db.init_db()
    return SessionClient(app, PARTY_A.address)


@pytest.fixture
def client_b(client):
    """A second authenticated session for the other party."""
    return SessionClient(app, PARTY_B.address)


@pytest.fixture
def deal(client):
    """Create a fresh deal with unique ID for each test.

    Parties are addresses, because that is what a signature can prove: a label
    like "agentA" is only a self-report.
    """
    unique_id = f"deal_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/deals",
        json={
            "deal_id": unique_id,
            "definition_of_done": {
                "deadline": "2026-09-10T00:00:00Z",
                "success": "1000 valid rows",
            },
            "parties": [PARTY_A.address, PARTY_B.address],
        },
    )
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def recorder(client):
    return Recorder(client)
