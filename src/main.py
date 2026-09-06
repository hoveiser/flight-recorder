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
        # Check previous link
        if ev.previous_event_hash != expected_prev:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: previous hash mismatch",
                "events": len(events),
            }
        
        # Check payload integrity (recompute payload_hash from current payload)
        actual_payload_hash = compute_payload_hash(ev.payload)
        if actual_payload_hash != ev.payload_hash:
            return {
                "deal_id": deal_id,
                "verification": "FAIL",
                "reason": f"Event {i}: payload hash mismatch (tampered)",
                "events": len(events),
            }
        
        # Recompute event hash
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
                "reason": f"Event {i}: event hash mismatch (tampered)",
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
