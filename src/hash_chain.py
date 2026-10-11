import hashlib
import json
from typing import Optional

# Domain tag of the EIP-191 message an actor signs per event. Changing this
# string changes what a valid signature proves, so it is versioned: events
# written before signing existed carry no signature at all and are verified with
# the v1 hash formula (see compute_event_hash).
EVENT_SIGN_DOMAIN = "flight-recorder-event-v1"

# Hash-chain layout versions. 1 = no signature, no client timestamp. 2 = the
# signature and the client-supplied timestamp are part of the hash input, so a
# tampered signature cannot be swapped out without breaking the chain.
EVENT_HASH_VERSION_LEGACY = 1
EVENT_HASH_VERSION_SIGNED = 2


def canonical_json(obj: dict) -> str:
    """Stable JSON serialization (sorted keys) so hashes are reproducible"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_payload_hash(payload: dict) -> str:
    """Hash the payload content"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def canonical_event_message(
    deal_id: str,
    previous_event_hash: str,
    event_type: str,
    payload_hash: str,
    client_timestamp: str,
) -> str:
    """The exact text an actor must sign with personal_sign.

    Everything that could be changed by a replay is inside the signed bytes:
    the domain tag pins the purpose (a login signature can never be reused as an
    event signature), `deal_id` stops an event being replayed into another deal,
    `previous_event_hash` stops it being replayed at another position in the
    chain, and `payload_hash` plus `client_timestamp` stop the payload or the
    clock being edited after the fact.
    """
    return "\n".join(
        [
            EVENT_SIGN_DOMAIN,
            deal_id,
            previous_event_hash,
            event_type,
            payload_hash,
            client_timestamp,
        ]
    )


def compute_event_hash(
    deal_id: str,
    actor: str,
    event_type: str,
    payload_hash: str,
    previous_event_hash: str,
    timestamp: str,
    signature: Optional[str] = None,
    client_timestamp: Optional[str] = None,
) -> str:
    """Hash = SHA-256(dealId + actor + eventType + payloadHash + previousEventHash + timestamp).

    Signed (version 2) events append the signature and the client timestamp, so
    the record of who authorized an event is part of the chain rather than an
    annotation next to it. Unsigned (version 1) events keep the original six
    fields byte for byte; their stored hashes must stay reproducible or every
    event written before signing existed would verify as tampered.
    """
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
    if signature is not None:
        data = data + "|" + signature + "|" + (client_timestamp or "")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_agreement_hash(definition_of_done: dict) -> str:
    """Hash the locked definition of done"""
    return hashlib.sha256(canonical_json(definition_of_done).encode("utf-8")).hexdigest()


GENESIS = "GENESIS"