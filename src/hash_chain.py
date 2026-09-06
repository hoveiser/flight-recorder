import hashlib
import json


def canonical_json(obj: dict) -> str:
    """Stable JSON serialization (sorted keys) so hashes are reproducible"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_payload_hash(payload: dict) -> str:
    """Hash the payload content"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_event_hash(
    deal_id: str,
    actor: str,
    event_type: str,
    payload_hash: str,
    previous_event_hash: str,
    timestamp: str,
) -> str:
    """Hash = SHA-256(dealId + actor + eventType + payloadHash + previousEventHash + timestamp)"""
    data = (
        deal_id
        + "|"
        + actor
        + "|"
        + event_type
        + "|"
        + payload_hash
        + "|"
        + previous_event_hash
        + "|"
        + timestamp
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_agreement_hash(definition_of_done: dict) -> str:
    """Hash the locked definition of done"""
    return hashlib.sha256(canonical_json(definition_of_done).encode("utf-8")).hexdigest()


GENESIS = "GENESIS"