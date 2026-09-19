import json
from src import db


def test_create_deal(client):
    resp = client.post(
        "/deals",
        json={
            "deal_id": "d1",
            "definition_of_done": {"success": "1000 rows"},
            "parties": ["a", "b"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deal_id"] == "d1"
    assert len(body["agreement_hash"]) == 64


def test_duplicate_deal_rejected(client):
    payload = {
        "deal_id": "dup",
        "definition_of_done": {"x": 1},
        "parties": ["a"],
    }
    assert client.post("/deals", json=payload).status_code == 200
    assert client.post("/deals", json=payload).status_code == 409


def test_event_requires_deal(client):
    resp = client.post(
        "/events",
        json={"deal_id": "missing", "actor": "a", "event_type": "REQUEST"},
    )
    assert resp.status_code == 404


def test_record_events_and_chain(client, deal):
    deal_id = deal["deal_id"]
    for i, etype in enumerate(["REQUEST", "RESPONSE", "DELIVERY"]):
        resp = client.post(
            "/events",
            json={
                "deal_id": deal_id,
                "actor": "agentA" if i != 2 else "agentB",
                "event_type": etype,
                "payload": {"seq": i},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["event_hash"]) == 64

    events = client.get(f"/deals/{deal_id}/events").json()
    assert len(events) == 3
    assert events[0]["previous_event_hash"] == "GENESIS"
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    assert events[2]["previous_event_hash"] == events[1]["event_hash"]


def test_verify_chain_pass(client, deal):
    deal_id = deal["deal_id"]
    for i in range(3):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "a", "event_type": "REQUEST", "payload": {"i": i}},
        )
        assert resp.status_code == 200
    resp = client.get(f"/deals/{deal_id}/verify")
    body = resp.json()
    assert body["verification"] == "PASS"
    assert body["events"] == 3


def test_tamper_detection(client, deal):
    deal_id = deal["deal_id"]
    for i in range(3):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "a", "event_type": "REQUEST", "payload": {"i": i}},
        )
        assert resp.status_code == 200

    events = client.get(f"/deals/{deal_id}/events").json()
    second_event_id = events[1]["id"]

    conn = db.get_conn()
    conn.execute(
        "UPDATE events SET payload = ? WHERE id = ?",
        (json.dumps({"i": 999, "evil": True}), second_event_id),
    )
    conn.commit()
    conn.close()

    resp = client.get(f"/deals/{deal_id}/verify")
    body = resp.json()
    assert body["verification"] == "FAIL"


def test_delete_event_breaks_chain(client, deal):
    deal_id = deal["deal_id"]
    for i in range(3):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "a", "event_type": "REQUEST", "payload": {"i": i}},
        )
        assert resp.status_code == 200

    events = client.get(f"/deals/{deal_id}/events").json()
    second_event_id = events[1]["id"]

    conn = db.get_conn()
    conn.execute(
        "DELETE FROM events WHERE id = ?",
        (second_event_id,),
    )
    conn.commit()
    conn.close()

    resp = client.get(f"/deals/{deal_id}/verify")
    body = resp.json()
    assert body["verification"] == "FAIL"


def test_dispute_requires_party(client, deal):
    deal_id = deal["deal_id"]
    resp = client.post(
        f"/deals/{deal_id}/dispute",
        json={"deal_id": deal_id, "party": "stranger", "claim": "I want money"},
    )
    assert resp.status_code == 403


def test_dispute_and_case_file(client, deal):
    deal_id = deal["deal_id"]

    # Record some events
    for i in range(2):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "agentA", "event_type": "REQUEST", "payload": {"i": i}},
        )
        assert resp.status_code == 200

    # File a dispute
    resp = client.post(
        f"/deals/{deal_id}/dispute",
        json={"deal_id": deal_id, "party": "agentA", "claim": "AgentB delivered only 500 rows"},
    )
    assert resp.status_code == 200

    # Get case file
    resp = client.get(f"/deals/{deal_id}/case-file")
    assert resp.status_code == 200
    case = resp.json()

    assert case["deal_id"] == deal_id
    assert len(case["events"]) == 2
    assert len(case["disputes"]) == 1
    assert case["disputes"][0]["party"] == "agentA"
    assert case["chain_integrity"]["verification"] == "PASS"
    assert case["definition_of_done"]["success"] == "1000 valid rows"


def test_seal_freeze_and_head_hash(client, deal):
    deal_id = deal["deal_id"]
    for i in range(2):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "agentA", "event_type": "DELIVERY", "payload": {"i": i}},
        )
        assert resp.status_code == 200

    events = client.get(f"/deals/{deal_id}/events").json()
    expected_head = events[-1]["event_hash"]

    resp = client.post(f"/deals/{deal_id}/seal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sealed"] is True
    assert body["chain_head"] == expected_head
    assert body["events"] == 2
    assert client.get(f"/deals/{deal_id}").json()["sealed"] is True

    # Idempotent: sealing again returns the same frozen head.
    again = client.post(f"/deals/{deal_id}/seal")
    assert again.status_code == 200
    assert again.json()["chain_head"] == expected_head

    # The seal is what makes the anchored hash final: further appends are
    # rejected with 409 and must not land in the log.
    rejected = client.post(
        "/events",
        json={"deal_id": deal_id, "actor": "agentA", "event_type": "DELIVERY", "payload": {"i": 99}},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Evidence log sealed after dispute"
    assert len(client.get(f"/deals/{deal_id}/events").json()) == 2

    assert client.post("/deals/nope/seal").status_code == 404


def test_sealed_deal_chain_still_verifies(client, deal):
    deal_id = deal["deal_id"]
    for i in range(3):
        resp = client.post(
            "/events",
            json={"deal_id": deal_id, "actor": "agentA", "event_type": "REQUEST", "payload": {"i": i}},
        )
        assert resp.status_code == 200

    assert client.post(f"/deals/{deal_id}/seal").status_code == 200

    # Sealing freezes writes; it must not break verification or case-file export.
    resp = client.get(f"/deals/{deal_id}/verify")
    body = resp.json()
    assert body["verification"] == "PASS"
    assert body["events"] == 3

    resp = client.get(f"/deals/{deal_id}/case-file")
    assert resp.status_code == 200
    case = resp.json()
    assert case["chain_integrity"]["verification"] == "PASS"
    assert len(case["events"]) == 3