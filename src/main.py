import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from . import db
from .models import (
    EventCreate,
    Event,
    DealCreate,
    Deal,
    DisputeCreate,
    Dispute,
    ADDRESS_PATTERN,
    NONCE_MAX_LENGTH,
    SIGNATURE_MAX_LENGTH,
)
from .hash_chain import (
    compute_payload_hash,
    compute_event_hash,
    compute_agreement_hash,
    canonical_event_message,
    canonical_json,
    EVENT_SIGN_DOMAIN,
    EVENT_HASH_VERSION_SIGNED,
    GENESIS,
)

app = FastAPI(title="Flight Recorder", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# Nonces and sessions are persisted in SQLite (db.store_nonce/get_nonce/
# delete_nonce and db.store_session/get_session), not in process memory. A
# worker restart — or a second uvicorn worker — therefore no longer drops
# active agent sessions, and a consumed nonce stays consumed across processes.

# How far the client-supplied event timestamp may drift from server time. Both
# bounds are enforced: without the past bound a signed event from last month
# could be replayed into the chain today, and without the future bound a party
# could date its own evidence ahead of everything else and keep doing it for
# ever. A window with only a ceiling is not a window.
EVENT_TIMESTAMP_MAX_PAST_SECONDS = 900
EVENT_TIMESTAMP_MAX_FUTURE_SECONDS = 300

_deal_write_locks: dict[str, threading.Lock] = {}
_deal_write_locks_guard = threading.Lock()


def _deal_write_lock(deal_id: str) -> threading.Lock:
    with _deal_write_locks_guard:
        lock = _deal_write_locks.get(deal_id)
        if lock is None:
            lock = threading.Lock()
            _deal_write_locks[deal_id] = lock
        return lock


class SealBody(BaseModel):
    actor: Optional[str] = None


class AuthVerify(BaseModel):
    # Bound before any cryptographic work: recovering a signer from an unbounded
    # blob is work that anybody can hand to the server for free.
    address: Annotated[str, Field(pattern=ADDRESS_PATTERN)]
    signature: Annotated[str, Field(min_length=64, max_length=SIGNATURE_MAX_LENGTH)]
    nonce: Annotated[str, Field(min_length=1, max_length=NONCE_MAX_LENGTH)]


# Byte budgets for the free-form parts of a write. The text fields have their own
# limits in models.py; these cover the nested dictionaries, which are what an
# agent actually fills in. A payload is hashed, stored and later re-hashed by
# validators, so an unbounded one is unbounded work for everyone downstream.
MAX_EVENT_PAYLOAD_BYTES = 32768
MAX_EVENT_METADATA_BYTES = 8192
MAX_DEFINITION_OF_DONE_BYTES = 8192


def _bounded_json_size(value: dict, limit: int, field: str) -> None:
    """Refuse a caller-supplied dictionary that is too large to be evidence.

    Measured on the canonical encoding, because that is the exact byte string the
    server hashes: counting the dict's Python repr would accept a payload whose
    digest input is bigger than the limit claims.
    """
    try:
        rendered = canonical_json(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{field} is not JSON-serialisable")
    if len(rendered.encode("utf-8")) > limit:
        raise HTTPException(400, f"{field} is larger than {limit} bytes")


def _require_session(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing session token")
    token = authorization.split(" ", 1)[1].strip()
    record = db.get_session(token)
    now = datetime.now(timezone.utc)
    if record is None or record["expires_at"] < now:
        raise HTTPException(401, "Invalid or expired session")
    return record["address"]


def _parse_client_timestamp(raw: str) -> datetime:
    """Parse the signed client timestamp; it must be an absolute UTC instant.

    A naive timestamp has no agreed meaning (is it the server's zone? the
    caller's?), and the drift window would then depend on where the request was
    built. Rejecting it is the conservative reading.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(400, "client_timestamp is required for signed events")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise HTTPException(400, "client_timestamp is not ISO-8601")
    if parsed.tzinfo is None:
        raise HTTPException(400, "client_timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _verify_event_signature(
    event_in: EventCreate,
    deal: Deal,
    previous_hash: str,
    payload_hash: str,
    session_address: str,
) -> datetime:
    """Bind the write to a key the party actually controls, and return the time
    that key asserted.

    Three separate things must line up, and each one closes a different attack:
    the recovered signer must be the claimed actor (otherwise the actor field is
    a self-report), the actor must be a party to this deal (otherwise a key that
    is valid somewhere else is being used here), and the actor must be the
    authenticated session (otherwise a session logs writes onto someone else's
    record). The signed message carries the deal id, the previous hash, the
    event type, the payload digest and the client timestamp, so replaying a
    signature into another deal or another chain position changes what is being
    recovered and fails the first check.
    """
    if not event_in.signature:
        raise HTTPException(400, "signature is required: events must be signed by their actor")
    client_ts = _parse_client_timestamp(event_in.client_timestamp or "")

    now = datetime.now(timezone.utc)
    if client_ts > now + timedelta(seconds=EVENT_TIMESTAMP_MAX_FUTURE_SECONDS):
        raise HTTPException(400, "client_timestamp is too far in the future")
    if client_ts < now - timedelta(seconds=EVENT_TIMESTAMP_MAX_PAST_SECONDS):
        raise HTTPException(400, "client_timestamp is too old")

    message = canonical_event_message(
        deal_id=event_in.deal_id,
        previous_event_hash=previous_hash,
        event_type=event_in.event_type,
        payload_hash=payload_hash,
        client_timestamp=event_in.client_timestamp.strip(),
    )
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=event_in.signature
        )
    except Exception:
        raise HTTPException(400, "signature is not a valid EIP-191 personal_sign")

    if recovered.lower() != event_in.actor.lower():
        raise HTTPException(403, "signature does not match the claimed actor")
    if event_in.actor.lower() not in {p.lower() for p in deal.parties}:
        raise HTTPException(403, "actor is not a party to this deal")
    if event_in.actor.lower() != session_address.lower():
        raise HTTPException(403, "actor does not match the authenticated session")
    return client_ts


@app.post("/api/auth/nonce")
def auth_nonce():
    nonce = f"Flight Recorder login {secrets.token_hex(16)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.store_nonce(nonce, expires_at)
    return {"nonce": nonce, "expires_at": expires_at.isoformat()}


@app.post("/api/auth/verify")
def auth_verify(body: AuthVerify):
    expires_at = db.get_nonce(body.nonce)
    now = datetime.now(timezone.utc)
    if expires_at is None or expires_at < now:
        raise HTTPException(401, "Nonce missing or expired")
    try:
        recovered = Account.recover_message(encode_defunct(text=body.nonce), signature=body.signature)
    except Exception:
        raise HTTPException(401, "Invalid signature")
    if recovered.lower() != body.address.lower():
        raise HTTPException(401, "Signature does not match address")
    db.delete_nonce(body.nonce)
    token = secrets.token_urlsafe(32)
    session_expires = now + timedelta(days=7)
    db.store_session(token, recovered, session_expires)
    return {"session_token": token, "expires_at": session_expires.isoformat()}


@app.post("/deals", response_model=Deal)
def create_deal(deal_in: DealCreate):
    _bounded_json_size(deal_in.definition_of_done, MAX_DEFINITION_OF_DONE_BYTES, "definition_of_done")
    if db.get_deal(deal_in.deal_id) is not None:
        raise HTTPException(409, "Deal already exists")
    deal = Deal(
        deal_id=deal_in.deal_id,
        definition_of_done=deal_in.definition_of_done,
        parties=deal_in.parties,
        agreement_hash=compute_agreement_hash(deal_in.definition_of_done),
        created_at=datetime.now(timezone.utc),
    )
    db.save_deal(deal)
    return deal


@app.get("/deals/{deal_id}", response_model=Deal)
def get_deal(deal_id: str):
    deal = db.get_deal(deal_id)
    if deal is None:
        raise HTTPException(404, "Deal not found")
    return deal


@app.post("/events", response_model=Event)
def record_event(event_in: EventCreate, authorization: Optional[str] = Header(default=None)):
    session_address = _require_session(authorization)
    _bounded_json_size(event_in.payload, MAX_EVENT_PAYLOAD_BYTES, "payload")
    _bounded_json_size(event_in.metadata, MAX_EVENT_METADATA_BYTES, "metadata")
    with _deal_write_lock(event_in.deal_id):
        deal = db.get_deal(event_in.deal_id)
        if deal is None:
            raise HTTPException(404, "Deal not found")
        if deal.sealed:
            # The case file that was anchored on-chain must stay byte-identical to
            # the one validators fetch, so the log freezes at dispute time. Without
            # this, a party could append favourable events after anchoring and make
            # the on-chain hash describe a record that no longer exists off-chain.
            raise HTTPException(409, "Evidence log sealed after dispute")

        last = db.get_last_event(event_in.deal_id)
        previous_hash = last.event_hash if last else GENESIS

        payload_hash = compute_payload_hash(event_in.payload)
        _verify_event_signature(event_in, deal, previous_hash, payload_hash, session_address)
        timestamp = datetime.now(timezone.utc)
        client_timestamp = event_in.client_timestamp.strip()
        signature = event_in.signature.strip()
        event_hash = compute_event_hash(
            deal_id=event_in.deal_id,
            actor=event_in.actor,
            event_type=event_in.event_type,
            payload_hash=payload_hash,
            previous_event_hash=previous_hash,
            timestamp=timestamp.isoformat(),
            signature=signature,
            client_timestamp=client_timestamp,
        )

        event = Event(
            id=0,
            deal_id=event_in.deal_id,
            actor=event_in.actor,
            event_type=event_in.event_type,
            payload=event_in.payload,
            metadata=event_in.metadata,
            payload_hash=payload_hash,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            timestamp=timestamp,
            signature=signature,
            client_timestamp=client_timestamp,
            sig_version=EVENT_HASH_VERSION_SIGNED,
        )
        db.save_event(event)
        return event


@app.get("/deals/{deal_id}/events", response_model=list[Event])
def get_events(deal_id: str):
    if db.get_deal(deal_id) is None:
        raise HTTPException(404, "Deal not found")
    return db.get_events(deal_id)


@app.post("/deals/{deal_id}/seal")
def seal_deal(
    deal_id: str,
    body: Optional[SealBody] = None,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
    authorization: Optional[str] = Header(default=None),
):
    """Freeze the evidence log and return the head hash that must be anchored.

    Idempotent: sealing an already-sealed deal succeeds and returns the same
    head hash. Call this immediately before sending the on-chain dispute so the
    anchored hash describes a log that can no longer change.
    """
    session_address = _require_session(authorization)
    deal = db.get_deal(deal_id)
    if deal is None:
        raise HTTPException(404, "Deal not found")

    actor = (body.actor if body is not None else None) or x_actor
    if not actor or actor not in deal.parties:
        raise HTTPException(
            403,
            "Only a deal party (client or worker) may seal the evidence log",
        )
    # The seal freezes the log that gets anchored on-chain, so it needs the same
    # binding as an event write: whoever seals must be the authenticated session,
    # not merely someone who can name a party. Without this a stolen or shared
    # session token could freeze another party's evidence at any moment.
    if actor.lower() != session_address.lower():
        raise HTTPException(403, "actor does not match the authenticated session")

    db.seal_deal(deal_id)
    last = db.get_last_event(deal_id)
    last_hash = last.event_hash if last else GENESIS
    return {
        "deal_id": deal_id,
        "sealed": True,
        "chain_head": last_hash,
        "events": len(db.get_events(deal_id)),
    }


@app.post("/deals/{deal_id}/dispute", response_model=Dispute)
def file_dispute(deal_id: str, dispute_in: DisputeCreate, authorization: Optional[str] = Header(default=None)):
    """Record a party's claim in the case file.

    This write used to be the one unauthenticated write left in the API: it checked
    that `party` was on the deal, but `party` is just a string the caller types, so
    anyone could have written a claim into anyone's evidence record. A dispute is
    evidence, so it carries the same binding as an event: a session, the party named
    must be on the deal, and that party must be the session's own address.
    """
    session_address = _require_session(authorization)
    deal = db.get_deal(deal_id)
    if deal is None:
        raise HTTPException(404, "Deal not found")
    if dispute_in.party not in deal.parties:
        raise HTTPException(403, "Only a party to the deal may file a dispute")
    if dispute_in.party.lower() != session_address.lower():
        raise HTTPException(403, "party does not match the authenticated session")

    dispute = Dispute(
        id=0,
        deal_id=deal_id,
        party=dispute_in.party,
        claim=dispute_in.claim,
        filed_at=datetime.now(timezone.utc),
    )
    db.save_dispute(dispute)
    return dispute


@app.get("/deals/{deal_id}/disputes", response_model=list[Dispute])
def get_disputes(deal_id: str):
    if db.get_deal(deal_id) is None:
        raise HTTPException(404, "Deal not found")
    return db.get_disputes(deal_id)


def _verify_event_signature_record(ev: Event) -> str:
    """Recover the signer of a stored event and say what it proves.

    Returns PASS, FAIL, or UNSIGNED_LEGACY. Re-deriving the address from the
    signature is what makes the chain more than an append-only file the server
    owns: a row can be checked against the key that wrote it even after the
    actor field and the hash are read straight out of SQLite.
    """
    if ev.sig_version != EVENT_HASH_VERSION_SIGNED or not ev.signature:
        return "UNSIGNED_LEGACY"
    message = canonical_event_message(
        deal_id=ev.deal_id,
        previous_event_hash=ev.previous_event_hash,
        event_type=ev.event_type,
        payload_hash=ev.payload_hash,
        client_timestamp=ev.client_timestamp or "",
    )
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=ev.signature
        )
    except Exception:
        return "FAIL"
    if recovered.lower() != ev.actor.lower():
        return "FAIL"
    deal = db.get_deal(ev.deal_id)
    if deal is None or ev.actor.lower() not in {p.lower() for p in deal.parties}:
        return "FAIL"
    return "PASS"


def _verify_chain_logic(deal_id: str) -> dict:
    """Internal logic: returns dict (not JSONResponse)

    Chain integrity and signature status are reported separately. A log can be
    internally consistent (every hash recomputes) and still contain writes nobody
    authorized, and the reverse is true as well; collapsing the two into one
    verdict would hide which of the two guarantees is missing.
    """
    if db.get_deal(deal_id) is None:
        raise HTTPException(404, "Deal not found")

    events = db.get_events(deal_id)

    if not events:
        return {
            "deal_id": deal_id,
            "verification": "PASS",
            "signature_status": "PASS",
            "signatures": {"events": 0, "signed": 0, "legacy": 0, "failed": 0},
            "events": 0,
        }

    expected_prev = GENESIS
    signature_results = []
    for i, ev in enumerate(events):
        if ev.previous_event_hash != expected_prev:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: previous hash mismatch",
                "events": len(events),
            }

        actual_payload_hash = compute_payload_hash(ev.payload)
        if actual_payload_hash != ev.payload_hash:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: payload hash mismatch (tampered)",
                "events": len(events),
            }

        recomputed = compute_event_hash(
            deal_id=ev.deal_id,
            actor=ev.actor,
            event_type=ev.event_type,
            payload_hash=ev.payload_hash,
            previous_event_hash=ev.previous_event_hash,
            timestamp=ev.timestamp.isoformat(),
            signature=ev.signature,
            client_timestamp=ev.client_timestamp,
        )
        if recomputed != ev.event_hash:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: event hash mismatch (tampered)",
                "events": len(events),
            }
        signature_results.append(_verify_event_signature_record(ev))
        expected_prev = ev.event_hash

    signature_status = _aggregate_signature_status(signature_results)
    return {
        "deal_id": deal_id,
        "verification": "PASS",
        "genesis_hash": events[0].event_hash,
        "last_hash": events[-1].event_hash,
        "hash_version": events[-1].sig_version,
        "signature_status": signature_status,
        "signatures": {
            "events": len(events),
            "signed": sum(1 for r in signature_results if r == "PASS"),
            "legacy": sum(1 for r in signature_results if r == "UNSIGNED_LEGACY"),
            "failed": sum(1 for r in signature_results if r == "FAIL"),
        },
        "events": len(events),
    }


def _aggregate_signature_status(results: list[str]) -> str:
    """One verdict for the whole log: FAIL beats UNSIGNED_LEGACY beats PASS."""
    if "FAIL" in results:
        return "FAIL"
    if "UNSIGNED_LEGACY" in results:
        return "UNSIGNED_LEGACY"
    return "PASS"


@app.get("/deals/{deal_id}/verify")
def verify_chain(deal_id: str):
    """Verify hash chain integrity and event signatures - public endpoint"""
    result = _verify_chain_logic(deal_id)
    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/deals/{deal_id}/case-file")
def get_case_file(deal_id: str):
    """Export a complete case file for adjudication (GenLayer-ready)"""
    deal = db.get_deal(deal_id)
    if deal is None:
        raise HTTPException(404, "Deal not found")

    events = db.get_events(deal_id)
    disputes = db.get_disputes(deal_id)
    verification = _verify_chain_logic(deal_id)  # Now returns dict!

    return {
        "deal_id": deal_id,
        "definition_of_done": deal.definition_of_done,
        "agreement_hash": deal.agreement_hash,
        "parties": deal.parties,
        "created_at": deal.created_at.isoformat(),
        "events": [
            {
                "id": ev.id,
                "actor": ev.actor,
                "event_type": ev.event_type,
                "payload": ev.payload,
                "payload_hash": ev.payload_hash,
                "previous_event_hash": ev.previous_event_hash,
                "event_hash": ev.event_hash,
                "timestamp": ev.timestamp.isoformat(),
                # What the actor authorized, and the proof it authorized it, so
                # an adjudicator can re-derive the signer without trusting this
                # server. `signed_fields` repeats the exact message inputs in the
                # order the signature covers them.
                "signature": ev.signature,
                "client_timestamp": ev.client_timestamp,
                "sig_version": ev.sig_version,
                "signature_status": _verify_event_signature_record(ev),
                "signed_fields": {
                    "domain": EVENT_SIGN_DOMAIN,
                    "deal_id": ev.deal_id,
                    "previous_event_hash": ev.previous_event_hash,
                    "event_type": ev.event_type,
                    "payload_hash": ev.payload_hash,
                    "client_timestamp": ev.client_timestamp,
                },
            }
            for ev in events
        ],
        "disputes": [
            {
                "id": d.id,
                "party": d.party,
                "claim": d.claim,
                "filed_at": d.filed_at.isoformat(),
            }
            for d in disputes
        ],
        "chain_integrity": verification,
    }