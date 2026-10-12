"""Regression guard for the published demo case files.

The D6 contract recomputes the chain itself, so a hand-written or drifted case
file that declares a head its events do not produce is now refusable evidence
(CHAIN_MISMATCH). These files ship as honest demo data and are served live (the
browser fallback, the run_live_scenarios happy path), so they must recompute to
exactly the head they declare. If anybody edits a payload, a signature or a hash
here, this test fails before a dispute can strand on a broken anchor.
"""
import glob
import json
import os

import pytest

from src.hash_chain import (
    GENESIS,
    EVENT_HASH_VERSION_SIGNED,
    ChainError,
    compute_payload_hash,
    recompute_head,
)

CASE_FILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo", "case_files"
)
CASE_FILES = sorted(glob.glob(os.path.join(CASE_FILE_DIR, "*.json")))


def _case_files():
    found = []
    for path in CASE_FILES:
        with open(path, encoding="utf-8") as handle:
            found.append((os.path.basename(path), json.load(handle)))
    return found


PUBLISHED = _case_files()
NAMES = [name for name, _ in PUBLISHED]


@pytest.mark.parametrize("name,case_file", PUBLISHED, ids=NAMES)
def test_published_case_file_recomputes_to_its_declared_head(name, case_file):
    """The contract's recompute lands on the head the file claims."""
    head = recompute_head(case_file["events"], case_file["deal_id"])
    declared = case_file["chain_integrity"]["last_hash"]
    assert head == declared, f"{name}: recomputed {head} != declared {declared}"


@pytest.mark.parametrize("name,case_file", PUBLISHED, ids=NAMES)
def test_published_case_file_links_from_genesis(name, case_file):
    """Every event chains to its predecessor and re-derives its own payload hash."""
    previous = GENESIS
    for index, ev in enumerate(case_file["events"]):
        assert ev["previous_event_hash"] == previous, f"{name} event {index} linkage"
        assert ev["sig_version"] == EVENT_HASH_VERSION_SIGNED, f"{name} event {index} not signed"
        assert compute_payload_hash(ev["payload"]) == ev["payload_hash"], f"{name} event {index} payload hash"
        previous = ev["event_hash"]


@pytest.mark.parametrize("name,case_file", PUBLISHED, ids=NAMES)
def test_published_case_file_survives_a_lying_integrity_flag(name, case_file):
    """The chain stands on its events, not on the self-reported flag.

    Flipping chain_integrity.verification to FAIL changes nothing about the
    recomputation: the contract reads the events, so the honest head is the same.
    """
    case_file["chain_integrity"]["verification"] = "FAIL"
    head = recompute_head(case_file["events"], case_file["deal_id"])
    assert head == case_file["chain_integrity"]["last_hash"]


def test_edited_payload_is_now_detectable():
    """Tampering with a payload breaks the recompute (the F5 attack surface)."""
    _, case_file = PUBLISHED[0]
    events = json.loads(json.dumps(case_file["events"]))
    events[0]["payload"] = {"tampered": True}
    with pytest.raises(ChainError):
        recompute_head(events, case_file["deal_id"])
