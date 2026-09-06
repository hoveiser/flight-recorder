import os
import sys
import tempfile

# Add project root to sys.path so 'src' is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set temp DB BEFORE importing app so tests use isolated DB
os.environ["FLIGHT_RECORDER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src import db


@pytest.fixture
def client():
    db.init_db()
    return TestClient(app)


@pytest.fixture
def deal(client):
    """Create a fresh deal for each test"""
    resp = client.post(
        "/deals",
        json={
            "deal_id": "deal1",
            "definition_of_done": {
                "deadline": "2026-09-10T00:00:00Z",
                "success": "1000 valid rows",
            },
            "parties": ["agentA", "agentB"],
        },
    )
    assert resp.status_code == 200
    return resp.json()