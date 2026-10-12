"""Generator for tests/golden/chain_vectors.json.

The vectors are the single source of truth that keeps three separate
implementations of the hash chain honest with each other: the off-chain recorder
(`src/hash_chain.py`), the recompute the settlement contract runs inline, and the
exported case file an adjudicator reads. They are produced here from the real
Python implementation, never hand-written, and a regression test re-runs this
module and compares the result to the committed file, so a change to the formula
cannot slip in without the vectors (and therefore the contract) moving too.

Run directly to regenerate:

    .venv-wsl/bin/python -m tests.golden.generate_chain_vectors

Determinism: signing keys are derived from fixed seeds, and every timestamp is a
literal, so re-running produces byte-identical signatures and hashes. No wall
clock and no randomness is consulted.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct

from src.hash_chain import (
    GENESIS,
    EVENT_HASH_VERSION_LEGACY,
    EVENT_HASH_VERSION_SIGNED,
    MAX_CHAIN_EVENTS,
    canonical_event_message,
    canonical_json,
    compute_agreement_hash,
    compute_event_hash,
    compute_payload_hash,
    recompute_head,
    ChainError,
)

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chain_vectors.json")

# Two fixed throwaway keys stand in for the deal parties. Third party for the
# non-party signing case. Never real, never used to protect anything.
def _key(seed: str) -> Account:
    return Account.from_key(hashlib.sha256(seed.encode("utf-8")).hexdigest())


PARTY_A = _key("flight-recorder-vector-party-a")
PARTY_B = _key("flight-recorder-vector-party-b")

DOD = {"success_criteria": "1000 valid records", "deadline": "2026-09-10"}

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _server_ts(i: int) -> str:
    return (BASE_TIME + timedelta(seconds=i)).isoformat()


def _client_ts(i: int) -> str:
    return (BASE_TIME + timedelta(minutes=i)).isoformat()


def _sign(signer: Account, deal_id: str, previous: str, event_type: str, payload_hash: str, client_timestamp: str) -> str:
    message = canonical_event_message(
        deal_id=deal_id,
        previous_event_hash=previous,
        event_type=event_type,
        payload_hash=payload_hash,
        client_timestamp=client_timestamp,
    )
    return signer.sign_message(encode_defunct(text=message)).signature.hex()


def build_event(
    deal_id: str,
    index: int,
    actor: Account,
    event_type: str,
    payload: dict,
    previous: str,
    version: int,
) -> dict:
    """Build one case-file event exactly the way the recorder would store/export it."""
    payload_hash = compute_payload_hash(payload)
    timestamp = _server_ts(index)
    if version == EVENT_HASH_VERSION_SIGNED:
        client_timestamp = _client_ts(index)
        signature = _sign(actor, deal_id, previous, event_type, payload_hash, client_timestamp)
        event_hash = compute_event_hash(
            deal_id=deal_id,
            actor=actor.address,
            event_type=event_type,
            payload_hash=payload_hash,
            previous_event_hash=previous,
            timestamp=timestamp,
            signature=signature,
            client_timestamp=client_timestamp,
        )
    else:
        client_timestamp = None
        signature = None
        event_hash = compute_event_hash(
            deal_id=deal_id,
            actor=actor.address,
            event_type=event_type,
            payload_hash=payload_hash,
            previous_event_hash=previous,
            timestamp=timestamp,
        )
    return {
        "id": index + 1,
        "actor": actor.address,
        "event_type": event_type,
        "payload": payload,
        "payload_hash": payload_hash,
        "previous_event_hash": previous,
        "event_hash": event_hash,
        "timestamp": timestamp,
        "signature": signature,
        "client_timestamp": client_timestamp,
        "sig_version": version,
    }


def build_chain(deal_id: str, steps) -> tuple[list, str]:
    """Walk a list of (actor, event_type, payload, version) into a chained list."""
    events = []
    previous = GENESIS
    for index, (actor, event_type, payload, version) in enumerate(steps):
        ev = build_event(deal_id, index, actor, event_type, payload, previous, version)
        events.append(ev)
        previous = ev["event_hash"]
    return events, previous


def _copy(events):
    return json.loads(json.dumps(events))


def _case_file(deal_id, events, chain_integrity=None):
    return {
        "deal_id": deal_id,
        "definition_of_done": DOD,
        "parties": [PARTY_A.address, PARTY_B.address],
        "events": events,
        "disputes": [{"id": 1, "party": PARTY_A.address, "claim": "test claim", "filed_at": _server_ts(0)}],
        "chain_integrity": chain_integrity if chain_integrity is not None else {"verification": "PASS"},
    }


def _honest_vector(name, deal_id, steps, chain_integrity=None):
    events, head = build_chain(deal_id, steps)
    return {
        "name": name,
        "expect": "MATCH",
        "deal_id": deal_id,
        "anchor": head,
        "agreement_hash": compute_agreement_hash(DOD),
        "case_file": _case_file(deal_id, events, chain_integrity),
        "head": head,
    }


def _mismatch_vector(name, deal_id, events, anchor, chain_integrity=None):
    """A case file whose bytes must NOT recompute to the anchored head.

    `anchor` is the head the deal was really anchored at, so the contract's own
    walk either raises or lands on a different digest. Either outcome is
    CHAIN_MISMATCH; the off-chain and on-chain tests assert as much.
    """
    return {
        "name": name,
        "expect": "CHAIN_MISMATCH",
        "deal_id": deal_id,
        "anchor": anchor,
        "agreement_hash": compute_agreement_hash(DOD),
        "case_file": _case_file(deal_id, events, chain_integrity),
        "head": None,
    }


def build_vectors():
    vectors = []

    # --- Honest chains that must recompute to their own head -----------------
    vectors.append(_honest_vector(
        "legacy_v1_single", "vec_v1_single",
        [(PARTY_A, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_LEGACY)],
    ))
    vectors.append(_honest_vector(
        "legacy_v1_chain", "vec_v1_chain",
        [
            (PARTY_A, "REQUEST", {"task": "scrape"}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "PROGRESS", {"rows": 500}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_LEGACY),
        ],
    ))
    vectors.append(_honest_vector(
        "v2_signed_single", "vec_v2_single",
        [(PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_SIGNED)],
    ))
    vectors.append(_honest_vector(
        "v2_signed_chain", "vec_v2_chain",
        [
            (PARTY_A, "REQUEST", {"task": "scrape"}, EVENT_HASH_VERSION_SIGNED),
            (PARTY_B, "PROGRESS", {"rows": 500}, EVENT_HASH_VERSION_SIGNED),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_SIGNED),
        ],
    ))
    vectors.append(_honest_vector(
        "mixed_v1_then_v2", "vec_mixed",
        [
            (PARTY_A, "REQUEST", {"task": "x"}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "PROGRESS", {"rows": 1}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_SIGNED),
        ],
    ))
    vectors.append(_honest_vector(
        "empty_payload_v2", "vec_empty_payload",
        [(PARTY_A, "PING", {}, EVENT_HASH_VERSION_SIGNED)],
    ))
    vectors.append(_honest_vector(
        "unicode_and_escaped", "vec_unicode",
        [(PARTY_A, "DELIVERY", {"note": "café ✓ “quoted” back\\slash tab\tnew\nline 漢字 🎯"}, EVENT_HASH_VERSION_SIGNED)],
    ))
    vectors.append(_honest_vector(
        "numbers", "vec_numbers",
        [(PARTY_A, "DELIVERY", {"big": 10 ** 30, "neg": -5, "zero": 0, "half": 1.5, "exp": 1e21}, EVENT_HASH_VERSION_SIGNED)],
    ))
    vectors.append(_honest_vector(
        "nested_objects", "vec_nested",
        [(PARTY_A, "DELIVERY", {"outer": {"list": [1, 2, {"deep": "x"}], "arr": [], "empty_obj": {}}, "z": None}, EVENT_HASH_VERSION_SIGNED)],
    ))
    vectors.append(_honest_vector(
        "long_payload_v1", "vec_long",
        [(PARTY_A, "DELIVERY", {"blob": "x" * 30000}, EVENT_HASH_VERSION_LEGACY)],
    ))
    # A lying negative flag: the chain is honest but chain_integrity says FAIL.
    # The contract must ignore the flag entirely and still reach adjudication.
    vectors.append(_honest_vector(
        "honest_chain_with_lying_FAIL_flag", "vec_lying_fail",
        [
            (PARTY_A, "REQUEST", {"task": "y"}, EVENT_HASH_VERSION_SIGNED),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_SIGNED),
        ],
        chain_integrity={"verification": "FAIL", "last_hash": "0" * 64},
    ))

    # --- Adversarial chains that must NOT be treated as valid evidence --------
    base_events, base_head = build_chain(
        "vec_v1_chain",
        [
            (PARTY_A, "REQUEST", {"task": "scrape"}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "PROGRESS", {"rows": 500}, EVENT_HASH_VERSION_LEGACY),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_LEGACY),
        ],
    )

    # Edited payload with a lying PASS flag: change a payload, leave the hash.
    edited = _copy(base_events)
    edited[1]["payload"] = {"rows": 1}
    vectors.append(_mismatch_vector(
        "edited_payload_with_lying_PASS_flag", "vec_v1_chain", edited, base_head,
        chain_integrity={"verification": "PASS", "last_hash": base_head},
    ))

    # Reordered events.
    reordered = [base_events[1], base_events[0], base_events[2]]
    vectors.append(_mismatch_vector("reordered_events", "vec_v1_chain", reordered, base_head))

    # Dropped middle event (the survivor still points at the missing link).
    dropped = [base_events[0], base_events[2]]
    vectors.append(_mismatch_vector("dropped_middle_event", "vec_v1_chain", dropped, base_head))

    # Duplicated event: a copy keeps the original predecessor as its previous.
    duplicated = _copy(base_events)
    duplicated.insert(1, _copy([base_events[0]])[0])
    vectors.append(_mismatch_vector("duplicated_event", "vec_v1_chain", duplicated, base_head))

    # Truncated tail: a shorter but internally consistent chain, anchored head is longer.
    truncated = _copy(base_events)[:-1]
    vectors.append(_mismatch_vector("truncated_tail", "vec_v1_chain", truncated, base_head))

    # Extra event appended after the anchored head: consistent, but the head moved.
    extra_prev = base_head
    extra = _copy(base_events) + [build_event("vec_v1_chain", 3, PARTY_B, "DELIVERY", {"valid": 2000}, extra_prev, EVENT_HASH_VERSION_LEGACY)]
    vectors.append(_mismatch_vector("extra_event_appended_after_anchor", "vec_v1_chain", extra, base_head))

    # Tampered signature field on a signed chain (hash left as it was).
    signed_events, signed_head = build_chain(
        "vec_v2_chain",
        [
            (PARTY_A, "REQUEST", {"task": "scrape"}, EVENT_HASH_VERSION_SIGNED),
            (PARTY_B, "PROGRESS", {"rows": 500}, EVENT_HASH_VERSION_SIGNED),
            (PARTY_B, "DELIVERY", {"valid": 1000}, EVENT_HASH_VERSION_SIGNED),
        ],
    )
    tampered_sig = _copy(signed_events)
    s = tampered_sig[1]["signature"]
    # Flip the final hex character: same length, still a bounded string, but the
    # version 2 hash now covers different bytes than the declared event_hash.
    tampered_sig[1]["signature"] = s[:-1] + ("a" if s[-1] != "a" else "b")
    vectors.append(_mismatch_vector(
        "tampered_signature_field", "vec_v2_chain", tampered_sig, signed_head,
        chain_integrity={"verification": "PASS", "last_hash": signed_head},
    ))

    # Wrong field type: an actor that is not a string.
    bad_type = _copy(base_events)
    bad_type[0]["actor"] = 12345
    vectors.append(_mismatch_vector("wrong_field_type_actor_int", "vec_v1_chain", bad_type, base_head))

    # Unknown hash version.
    bad_version = _copy(base_events)
    bad_version[0]["sig_version"] = 3
    vectors.append(_mismatch_vector("unknown_version", "vec_v1_chain", bad_version, base_head))

    # Empty evidence log.
    vectors.append(_mismatch_vector("empty_events", "vec_v1_chain", [], base_head))

    # Payload over the per-event byte ceiling (internally consistent otherwise).
    big_events, big_head = build_chain(
        "vec_big",
        [(PARTY_A, "DELIVERY", {"blob": "y" * 40000}, EVENT_HASH_VERSION_LEGACY)],
    )
    vectors.append(_mismatch_vector("payload_over_byte_ceiling", "vec_big", big_events, big_head))

    # Event count over the ceiling (one more than MAX_CHAIN_EVENTS).
    flood_steps = [(PARTY_A, "STEP", {"i": i}, EVENT_HASH_VERSION_LEGACY) for i in range(MAX_CHAIN_EVENTS + 1)]
    flood_events, flood_head = build_chain("vec_flood", flood_steps)
    vectors.append(_mismatch_vector("event_count_over_limit", "vec_flood", flood_events, flood_head))

    return vectors


def _validate(vectors):
    """Guard the fixture: every vector must land where it claims, per the real impl."""
    for v in vectors:
        events = v["case_file"]["events"]
        deal_id = v["deal_id"]
        if v["expect"] == "MATCH":
            got = recompute_head(events, deal_id)
            assert got == v["anchor"], f"{v['name']}: honest chain recomputed {got} != anchor {v['anchor']}"
        else:
            try:
                got = recompute_head(events, deal_id)
            except ChainError:
                continue
            assert got != v["anchor"], f"{v['name']}: adversarial chain recomputed to the anchor, not a mismatch"


def main():
    vectors = build_vectors()
    _validate(vectors)
    document = {
        "meta": {
            "canonical_json": "json.dumps(obj, sort_keys=True, separators=(',',':')) with default ensure_ascii=True",
            "payload_hash": "SHA-256(canonical_json(payload)) hexdigest",
            "event_hash_v1": "SHA-256(deal_id|actor|event_type|payload_hash|previous_event_hash|timestamp)",
            "event_hash_v2": "SHA-256(deal_id|actor|event_type|payload_hash|previous_event_hash|timestamp|signature|client_timestamp)",
            "genesis": GENESIS,
            "event_sign_domain": canonical_event_message("d", "p", "t", "h", "c").splitlines()[0],
            "bounds": {
                "MAX_CHAIN_EVENTS": MAX_CHAIN_EVENTS,
            },
        },
        "vectors": vectors,
    }
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    print(f"wrote {len(vectors)} vectors to {OUT_PATH}")


if __name__ == "__main__":
    main()
