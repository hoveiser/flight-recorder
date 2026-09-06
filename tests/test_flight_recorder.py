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

    # Get the SECOND event's actual ID (not hardcoded)
    events = client.get(f"/deals/{deal_id}/events").json()
    second_event_id = events[1]["id"]

    # Tamper: mutate the second event's payload directly in the DB
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

    # Get the SECOND event's actual ID (not hardcoded)
    events = client.get(f"/deals/{deal_id}/events").json()
    second_event_id = events[1]["id"]

    # Delete the second event -> chain gap
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
