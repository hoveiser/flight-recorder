"""Shared client for the demo scripts: log in with a throwaway key and sign every event.

The recorder only accepts a write whose EIP-191 signature comes back to the
claimed actor, that actor is one of the deal's parties, and that actor is the
address behind the session token. So a demo that wants to append events needs a
key, a login, and a signature per event, exactly like a real agent.

The keys here are derived from fixed seed strings, so they are deterministic,
throwaway, and carry no funds: they exist to exercise the signed path locally
against `http://localhost:8000`.
"""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_defunct

DOMAIN_TAG = "flight-recorder-event-v1"


def key_from_seed(seed: str):
    """A deterministic throwaway key, with no secret material in the repo."""
    return Account.from_key(hashlib.sha256(seed.encode("utf-8")).hexdigest())


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def event_message(deal_id: str, previous_event_hash: str, event_type: str,
                  digest: str, client_timestamp: str) -> str:
    return "\n".join(
        [DOMAIN_TAG, deal_id, previous_event_hash, event_type, digest, client_timestamp]
    )


GENESIS = "GENESIS"


class Recorder:
    """Talks to the off-chain API as one or more identified parties."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.tokens: dict[str, str] = {}

    def _call(self, method: str, path: str, data=None, token: str | None = None):
        url = self.base_url + path
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> HTTP {e.code}: {e.read().decode('utf-8')}")

    def call(self, method: str, path: str, data=None, token: str | None = None):
        """Public entry point for the endpoints this client does not wrap."""
        return self._call(method, path, data, token)

    def login(self, key) -> str:
        """Prove ownership of `key` once and keep the session token."""
        address = key.address
        if address in self.tokens:
            return self.tokens[address]
        nonce = self._call("POST", "/api/auth/nonce")["nonce"]
        signature = key.sign_message(encode_defunct(text=nonce)).signature.hex()
        session = self._call(
            "POST", "/api/auth/verify",
            {"address": address, "signature": signature, "nonce": nonce},
        )
        self.tokens[address] = session["session_token"]
        return session["session_token"]

    def head(self, deal_id: str) -> str:
        events = self._call("GET", f"/deals/{deal_id}/events")
        return events[-1]["event_hash"] if events else GENESIS

    def record(self, key, deal_id: str, event_type: str, payload: dict,
               previous_event_hash: str | None = None) -> dict:
        """Append one signed event as `key`'s address.

        The signature covers the head this event is being appended to, so a
        client that lost a race has to re-read the head and sign again; that is
        the client's job, not the server's, and it is why the chain cannot fork.
        """
        digest = payload_hash(payload)
        previous = previous_event_hash or self.head(deal_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        message = event_message(deal_id, previous, event_type, digest, timestamp)
        signature = key.sign_message(encode_defunct(text=message)).signature.hex()
        return self._call(
            "POST", "/events",
            {
                "deal_id": deal_id,
                "actor": key.address,
                "event_type": event_type,
                "payload": payload,
                "signature": signature,
                "client_timestamp": timestamp,
            },
            token=self.login(key),
        )

    def seal(self, key, deal_id: str) -> str:
        """Freeze the log and return the head that a dispute must anchor."""
        result = self._call(
            "POST", f"/deals/{deal_id}/seal", {"actor": key.address},
            token=self.login(key),
        )
        return result["chain_head"]
