import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set temp DB BEFORE importing app
os.environ["FLIGHT_RECORDER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient
from src.main import app
from src import db

TEST_SESSION = "test-session"


class SessionClient(TestClient):
    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        path = str(url).split("?")[0]
        needs_session = method.upper() == "POST" and (path == "/events" or path.rstrip("/").endswith("/seal"))
        if needs_session and not any(key.lower() == "authorization" for key in headers):
            headers["Authorization"] = f"Bearer {TEST_SESSION}"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def client():
    db.init_db()
    # Seed the shared test session through the same SQLite-backed store the app
    # uses, so tests exercise the real persistence path and survive a reload.
    db.store_session(
        TEST_SESSION,
        "agentA",
        datetime.now(timezone.utc) + timedelta(days=1),
    )
    return SessionClient(app)


@pytest.fixture
def deal(client):
    """Create a fresh deal with unique ID for each test"""
    unique_id = f"deal_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/deals",
        json={
            "deal_id": unique_id,
            "definition_of_done": {
                "deadline": "2026-09-10T00:00:00Z",
                "success": "1000 valid rows",
            },
            "parties": ["agentA", "agentB"],
        },
    )
    assert resp.status_code == 200
    return resp.json()