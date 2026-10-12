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


# ---------------------------------------------------------------------------
# Deterministic bounds shared by the off-chain recompute and the on-chain one.
# They are named constants rather than magic numbers so the contract and this
# module cannot drift, and so every limit has both a floor and a ceiling: an
# evidence log with no events proves nothing, and an unbounded one is unbounded
# work for every validator that has to re-hash it. The ceilings mirror the write
# time limits in src/models.py, so a value that could not have been recorded
# cannot be re-derived here either.
# ---------------------------------------------------------------------------
MIN_CASE_FILE_BYTES = 20
MAX_CASE_FILE_BYTES = 1_048_576  # 1 MiB served body
MAX_CHAIN_EVENTS = 256
MAX_DEAL_ID_LEN = 100
MAX_EVENT_TYPE_LEN = 64
MAX_ACTOR_LEN = 128
MAX_SIGNATURE_LEN = 200
MAX_CLIENT_TIMESTAMP_LEN = 64
MAX_TIMESTAMP_LEN = 64
MAX_EVENT_PAYLOAD_BYTES = 32768


class ChainError(Exception):
    """A chain that does not stand up on its own terms.

    Every path here is a pure function of the fetched bytes, so a ChainError is
    fully reproducible by every validator: it is a deterministic evidence failure
    (reported on-chain as CHAIN_MISMATCH), never a transient one, and never the
    self-reported verdict of the case file.
    """


def _field_string(ev: dict, key: str, max_len: int) -> str:
    value = ev.get(key)
    if not isinstance(value, str) or value == "" or len(value) > max_len:
        raise ChainError(f"{key} is not a bounded non-empty string")
    return value


def recompute_head(events, deal_id: str) -> str:
    """Recompute the chain head from raw event dicts, or raise ChainError.

    The contract mirrors this routine byte for byte; `tests/golden/chain_vectors.json`
    is the fixture that keeps the two in lockstep. It trusts none of the case
    file's own verdicts: it re-derives every payload hash and every event hash
    from the primitive fields and walks the linkage from genesis, so an edited,
    reordered, dropped, duplicated or appended event breaks the walk rather than
    being waved through by a `chain_integrity` flag somebody typed into a file.
    """
    if not isinstance(deal_id, str) or deal_id == "" or len(deal_id) > MAX_DEAL_ID_LEN:
        raise ChainError("deal_id is not a bounded non-empty string")
    if not isinstance(events, list):
        raise ChainError("events is not a list")
    if len(events) == 0:
        raise ChainError("empty evidence log")
    if len(events) > MAX_CHAIN_EVENTS:
        raise ChainError("too many events")

    previous = GENESIS
    for index, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ChainError(f"event {index} is not an object")
        if ev.get("previous_event_hash") != previous:
            raise ChainError(f"event {index} breaks the chain linkage")

        actor = _field_string(ev, "actor", MAX_ACTOR_LEN)
        event_type = _field_string(ev, "event_type", MAX_EVENT_TYPE_LEN)
        timestamp = _field_string(ev, "timestamp", MAX_TIMESTAMP_LEN)

        payload = ev.get("payload")
        if not isinstance(payload, dict):
            raise ChainError(f"event {index} payload is not an object")
        try:
            payload_bytes = canonical_json(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ChainError(f"event {index} payload is not canonicalisable: {exc}")
        if len(payload_bytes) > MAX_EVENT_PAYLOAD_BYTES:
            raise ChainError(f"event {index} payload is over the byte ceiling")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        version = ev.get("sig_version")
        signature = ev.get("signature")
        client_timestamp = ev.get("client_timestamp")
        # bool is a subclass of int in Python; reject it so {"sig_version": true}
        # is not silently read as version 1.
        if isinstance(version, bool) or not isinstance(version, int):
            raise ChainError(f"event {index} has an unknown hash version")

        if version == EVENT_HASH_VERSION_LEGACY:
            if signature is not None or client_timestamp is not None:
                raise ChainError(f"event {index} version 1 must not carry a signature")
            event_hash = compute_event_hash(
                deal_id=deal_id,
                actor=actor,
                event_type=event_type,
                payload_hash=payload_hash,
                previous_event_hash=previous,
                timestamp=timestamp,
            )
        elif version == EVENT_HASH_VERSION_SIGNED:
            if not isinstance(signature, str) or signature == "" or len(signature) > MAX_SIGNATURE_LEN:
                raise ChainError(f"event {index} version 2 needs a bounded signature string")
            if client_timestamp is None:
                normalized_client_timestamp = ""
            elif isinstance(client_timestamp, str) and len(client_timestamp) <= MAX_CLIENT_TIMESTAMP_LEN:
                normalized_client_timestamp = client_timestamp
            else:
                raise ChainError(f"event {index} has an out-of-bounds client_timestamp")
            event_hash = compute_event_hash(
                deal_id=deal_id,
                actor=actor,
                event_type=event_type,
                payload_hash=payload_hash,
                previous_event_hash=previous,
                timestamp=timestamp,
                signature=signature,
                client_timestamp=normalized_client_timestamp,
            )
        else:
            raise ChainError(f"event {index} has an unknown hash version")

        if ev.get("event_hash") != event_hash:
            raise ChainError(f"event {index} event hash does not recompute (tampered)")
        previous = event_hash

    return previous
