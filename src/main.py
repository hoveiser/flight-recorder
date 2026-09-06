from fastapi import FastAPI, HTTPException
from datetime import datetime, timezone
from . import db
from .models import EventCreate, Event, DealCreate, Deal
from .hash_chain import (
    compute_payload_hash,
    compute_event_hash,
    compute_agreement_hash,
    GENESIS,
)

app = FastAPI(title="Flight Recorder", version="0.1.0")

db.init_db()


@app.post("/deals", response_model=Deal)
def create_deal(deal_in: DealCreate):
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
def record_event(event_in: EventCreate):
    deal = db.get_deal(event_in.deal_id)
    if deal is None:
        raise HTTPException(404, "Deal not found")

    last = db.get_last_event(event_in.deal_id)
    previous_hash = last.event_hash if last else GENESIS

    payload_hash = compute_payload_hash(event_in.payload)
    timestamp = datetime.now(timezone.utc)
    event_hash = compute_event_hash(
        deal_id=event_in.deal_id,
        actor=event_in.actor,
        event_type=event_in.event_type,
        payload_hash=payload_hash,
        previous_event_hash=previous_hash,
        timestamp=timestamp.isoformat(),
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
    )
    db.save_event(event)
    return event


@app.get("/deals/{deal_id}/events", response_model=list[Event])
def get_events(deal_id: str):
    if db.get_deal(deal_id) is None:
        raise HTTPException(404, "Deal not found")
    return db.get_events(deal_id)


@app.get("/deals/{deal_id}/verify")
def verify_chain(deal_id: str):
    """Verify hash chain integrity"""
    if db.get_deal(deal_id) is None:
        raise HTTPException(404, "Deal not found")
    events = db.get_events(deal_id)
    if not events:
        return {"deal_id": deal_id, "verification": "PASS", "events": 0}

    expected_prev = GENESIS
    for i, ev in enumerate(events):
        if ev.previous_event_hash != expected_prev:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: previous hash mismatch",
                "events": len(events),
            }
        recomputed = compute_event_hash(
            deal_id=ev.deal_id,
            actor=ev.actor,
            event_type=ev.event_type,
            payload_hash=ev.payload_hash,
            previous_event_hash=ev.previous_event_hash,
            timestamp=ev.timestamp.isoformat(),
        )
        if recomputed != ev.event_hash:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: hash mismatch (tampered)",
                "events": len(events),
            }
        expected_prev = ev.event_hash

    return {
        "deal_id": deal_id,
        "verification": "PASS",
        "genesis_hash": events[0].event_hash,
        "last_hash": events[-1].event_hash,
        "events": len(events),
    }