"""Off-chain guard for the golden hash-chain vectors.

These vectors are the contract between three implementations of the same chain:
the recorder that writes events, the settlement contract that recomputes them,
and the exported case file an adjudicator reads. This suite does not touch the
contract; it locks the reference behavior the contract is required to match, and
it fails loudly if the formula in `src/hash_chain.py` drifts away from the
committed fixture.
"""
import json
import os

import pytest

from src.hash_chain import ChainError, recompute_head
from tests.golden.generate_chain_vectors import build_vectors

VECTORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "chain_vectors.json")


def _load():
    with open(VECTORS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _outcome(events, deal_id):
    """Return the head the contract would land on, or 'CHAIN_MISMATCH'."""
    try:
        head = recompute_head(events, deal_id)
    except ChainError:
        return "CHAIN_MISMATCH"
    return head


def _expect_label(vector):
    events = vector["case_file"]["events"]
    deal_id = vector["deal_id"]
    try:
        head = recompute_head(events, deal_id)
    except ChainError:
        return "CHAIN_MISMATCH"
    return "MATCH" if head == vector["anchor"] else "CHAIN_MISMATCH"


VECTORS = _load()["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_each_vector_lands_as_declared(vector):
    """The real implementation must agree with the vector's own expectation.

    Honest vectors recompute to exactly their anchored head; adversarial ones
    either raise or land somewhere else. This is the contract the settlement
    contract is held to in the direct-mode suite.
    """
    assert _expect_label(vector) == vector["expect"], vector["name"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_honest_vectors_recompute_field_by_field(vector):
    """Every event hash and payload hash in an honest chain is self-consistent.

    The recompute already walks this; here we additionally assert the head is a
    64-character lowercase digest, so an honest vector is always anchorable.
    """
    if vector["expect"] != "MATCH":
        pytest.skip("adversarial vector has no consistent head to check")
    head = recompute_head(vector["case_file"]["events"], vector["deal_id"])
    assert head == vector["anchor"]
    assert len(head) == 64
    assert all(c in "0123456789abcdef" for c in head)


def test_committed_fixture_is_reproducible_from_the_implementation():
    """Regenerating the vectors from `build_vectors` equals the committed file.

    If someone edits the formula, the digest or the serialization without
    regenerating the fixture, this test names it before the contract can drift.
    """
    regenerated = build_vectors()
    assert regenerated == VECTORS


def test_chain_integrity_flag_is_ignored_in_both_directions():
    """A PASS flag on a broken chain changes nothing, and a FAIL flag on an
    honest chain changes nothing. The contract reads the events, not the flag.
    """
    lying_pass = next(v for v in VECTORS if v["name"] == "edited_payload_with_lying_PASS_flag")
    assert lying_pass["case_file"]["chain_integrity"]["verification"] == "PASS"
    assert _expect_label(lying_pass) == "CHAIN_MISMATCH"

    lying_fail = next(v for v in VECTORS if v["name"] == "honest_chain_with_lying_FAIL_flag")
    assert lying_fail["case_file"]["chain_integrity"]["verification"] == "FAIL"
    assert _outcome(lying_fail["case_file"]["events"], lying_fail["deal_id"]) == lying_fail["anchor"]
