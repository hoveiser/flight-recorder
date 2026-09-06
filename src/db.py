import sqlite3
import json
from datetime import datetime
from typing import Optional
from .models import Event, Deal


DB_PATH = "flight_recorder.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT PRIMARY KEY,
            definition_of_done TEXT NOT NULL,
            parties TEXT NOT NULL,
            agreement_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            metadata TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            previous_event_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
        )
        """
    )
    conn.commit()
    conn.close()


def save_deal(deal: Deal):
    conn = get_conn()
    conn.execute(
        "INSERT INTO deals (deal_id, definition_of_done, parties, agreement_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            deal.deal_id,
            json.dumps(deal.definition_of_done),
            json.dumps(deal.parties),
            deal.agreement_hash,
            deal.created_at.isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_deal(deal_id: str) -> Optional[Deal]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM deals WHERE deal_id = ?", (deal_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return Deal(
        deal_id=row["deal_id"],
        definition_of_done=json.loads(row["definition_of_done"]),
        parties=json.loads(row["parties"]),
        agreement_hash=row["agreement_hash"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def save_event(event: Event):
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (deal_id, actor, event_type, payload, metadata, payload_hash, previous_event_hash, event_hash, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event.deal_id,
            event.actor,
            event.event_type,
            json.dumps(event.payload),
            json.dumps(event.metadata),
            event.payload_hash,
            event.previous_event_hash,
            event.event_hash,
            event.timestamp.isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_last_event(deal_id: str) -> Optional[Event]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM events WHERE deal_id = ? ORDER BY id DESC LIMIT 1",
        (deal_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_event(row)


def get_events(deal_id: str) -> list[Event]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE deal_id = ? ORDER BY id ASC", (deal_id,)
    ).fetchall()
    conn.close()
    return [_row_to_event(r) for r in rows]


def _row_to_event(row) -> Event:
    return Event(
        id=row["id"],
        deal_id=row["deal_id"],
        actor=row["actor"],
        event_type=row["event_type"],
        payload=json.loads(row["payload"]),
        metadata=json.loads(row["metadata"]),
        payload_hash=row["payload_hash"],
        previous_event_hash=row["previous_event_hash"],
        event_hash=row["event_hash"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )