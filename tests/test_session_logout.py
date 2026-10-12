"""Session logout / token revocation (D6 hardening).

A login session lives for seven days unless something shortens it. Logout must
actually revoke the token in the store so the very next authorized write is
refused, without disturbing the signed-event flow (recording an event only reads
a session; it never creates one).
"""
import hashlib

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from src import db
from src.main import app


def _account(seed):
    return Account.from_key(hashlib.sha256(seed.encode("utf-8")).hexdigest())


def _login(client, seed):
    actor = _account(f"logout-{seed}")
    nonce = client.post("/api/auth/nonce").json()["nonce"]
    signature = actor.sign_message(encode_defunct(text=nonce)).signature.hex()
    session = client.post(
        "/api/auth/verify",
        json={"address": actor.address, "signature": signature, "nonce": nonce},
    ).json()
    return session["session_token"]


def test_logout_revokes_the_session_immediately():
    client = TestClient(app)
    token = _login(client, "revoke")
    assert db.get_session(token) is not None, "login should store a live session"

    # Before logout the token authenticates: a session-gated route gets past the
    # 401 and only fails because the deal does not exist (404), not the session.
    before = client.post("/deals/does-not-exist/seal", headers={"Authorization": f"Bearer {token}"})
    assert before.status_code == 404

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    assert logout.json() == {"logged_out": True}

    assert db.get_session(token) is None, "logout must delete the stored session"
    after = client.post("/deals/does-not-exist/seal", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401, "a revoked token must no longer authenticate"


def test_logout_is_idempotent_and_does_not_leak():
    client = TestClient(app)
    # No header, and an unknown token, both succeed with the same body so the
    # endpoint cannot be used to probe whether a session exists.
    assert client.post("/api/auth/logout").json() == {"logged_out": True}
    unknown = client.post("/api/auth/logout", headers={"Authorization": "Bearer not-a-real-token"})
    assert unknown.status_code == 200
    assert unknown.json() == {"logged_out": True}


def test_logout_touches_only_the_presented_token():
    client = TestClient(app)
    token_a = _login(client, "a")
    token_b = _login(client, "b")
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})
    assert db.get_session(token_a) is None
    assert db.get_session(token_b) is not None, "logging out one session must not revoke another"
