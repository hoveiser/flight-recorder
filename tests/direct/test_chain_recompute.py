"""Direct-mode coverage for the D6 contract-side chain recomputation (F5).

The settlement contract now hashes the event chain itself and refuses to
adjudicate unless its own digest matches the delivery head anchored on-chain.
These tests push every golden vector through the real contract source, so the
on-chain recompute must agree with `src/hash_chain.recompute_head` to the byte,
including unicode, numbers and the version 1 / version 2 formulas.
"""
import hashlib
import json
import os

import pytest

from tests.direct.conftest import mock_json_llm, to_hex

CONTRACT_PATH = "contracts/settlement.py"
VALUE = 2 * 10**18
CASE_FILE_URL = "https://example.com/case-file.json"

VECTORS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "golden", "chain_vectors.json"
)

with open(VECTORS_PATH, encoding="utf-8") as _handle:
    VECTORS = json.load(_handle)["vectors"]

VECTOR_IDS = [v["name"] for v in VECTORS]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mock_case(vm, body, status=200):
    vm.mock_web(r"example\.com", {"status": status, "body": body})


def _instance(c):
    return object.__getattribute__(c, "_instance")


def _deal_record(c, deal_id) -> dict:
    return json.loads(_instance(c).deals[str(deal_id)])


def _write_deal_record(c, deal_id, record: dict) -> None:
    _instance(c).deals[str(deal_id)] = json.dumps(record)


def _serve(vm, case_file):
    """Serialize the case file the way the recorder serves it: literal UTF-8."""
    body = json.dumps(case_file, ensure_ascii=False)
    _mock_case(vm, body)
    return body


@pytest.mark.parametrize("vector", VECTORS, ids=VECTOR_IDS)
def test_contract_matches_every_golden_vector(direct_vm, direct_deploy, direct_alice, direct_bob, vector):
    """The contract's recompute must equal the vector exactly, both directions.

    An honest vector recomputes to its anchored head and is judged by the model;
    an adversarial vector is refused with CHAIN_MISMATCH and refunded to the
    client, which is the same fund outcome as ANCHOR_MISMATCH. No adversarial
    vector is ever allowed to reach the model.
    """
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    direct_vm.value = VALUE
    did = c.open_deal("deal1", vector["agreement_hash"], to_hex(direct_bob), 120)
    direct_vm.value = 0

    body = _serve(direct_vm, vector["case_file"])

    if vector["expect"] == "MATCH":
        mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "chain recomputed"})
        direct_vm.sender = direct_alice
        c.dispute(did, CASE_FILE_URL, _sha(body), vector["anchor"])
        c.resolve(did)
        d = json.loads(c.get_deal(did))
        assert d["verdict"] == "APPROVED", vector["name"]
        assert d["status"] == "adjudicated", vector["name"]
    else:
        # No LLM mock on purpose: reaching the model on a refusable chain is a bug.
        direct_vm.sender = direct_alice
        c.dispute(did, CASE_FILE_URL, _sha(body), vector["anchor"])
        c.resolve(did)
        d = json.loads(c.get_deal(did))
        assert d["verdict"] == "CHAIN_MISMATCH", vector["name"]
        assert d["status"] == "refunded", vector["name"]
        payouts = json.loads(c.get_payouts())
        assert len(payouts) == 1
        assert payouts[0]["to"].lower() == to_hex(direct_alice).lower()
        assert payouts[0]["amount"] == VALUE


def test_oversized_case_file_is_refused_before_parsing(direct_vm, direct_deploy, direct_alice, direct_bob):
    """A body over MAX_CASE_FILE_BYTES is CHAIN_MISMATCH, not a retry."""
    c = direct_deploy(CONTRACT_PATH)
    did_open = _open(c, direct_vm, direct_alice, direct_bob)
    big_body = json.dumps({"pad": "z" * 1_100_000})
    _mock_case(direct_vm, big_body)
    direct_vm.sender = direct_alice
    c.dispute(did_open, CASE_FILE_URL, _sha(big_body), "b" * 64)
    c.resolve(did_open)
    d = json.loads(c.get_deal(did_open))
    assert d["verdict"] == "CHAIN_MISMATCH"
    assert d["status"] == "refunded"


def test_missing_delivery_anchor_fails_closed(direct_vm, direct_deploy, direct_alice, direct_bob):
    """With no anchored head there is nothing independent to check against.

    The public dispute() always writes the delivery anchor, so this state is
    unreachable through the API. The gate is still exercised here by surgically
    removing the anchor from storage: the contract must fail closed (refund),
    never adjudicate on evidence it cannot tie to an anchor.
    """
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    body = _serve_from_chain(c, direct_vm, direct_alice, direct_bob, did)
    # Anchor a head, then delete it from storage to simulate the unreachable
    # no-anchor state.
    record = _deal_record(c, did)
    record["milestones"] = {}
    _write_deal_record(c, did, record)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "ANCHOR_MISMATCH"
    assert d["status"] == "refunded"
    del body  # referenced only for clarity of the served-file flow


def _open(c, vm, client, worker):
    vm.sender = client
    vm.value = VALUE
    try:
        return c.open_deal("deal1", _agreement_hash(), to_hex(worker), 120)
    finally:
        vm.value = 0


def _agreement_hash():
    dod = {"success_criteria": "1000 valid records", "deadline": "2026-09-10"}
    return hashlib.sha256(
        json.dumps(dod, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _serve_from_chain(c, vm, client, worker, did):
    """Dispute `did` against the first honest vector so an anchor is written."""
    honest = next(v for v in VECTORS if v["name"] == "legacy_v1_chain")
    body = _serve(vm, honest["case_file"])
    mock_json_llm(vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "x"})
    vm.sender = client
    c.dispute(did, CASE_FILE_URL, _sha(body), honest["anchor"])
    return body
