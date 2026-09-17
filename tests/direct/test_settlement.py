"""Direct-mode tests for the Settlement contract (SDK v0.19 RC)."""
import json
import hashlib

from tests.direct.conftest import mock_json_llm, to_hex

CONTRACT_PATH = "contracts/settlement.py"
VALUE = 2 * 10**18

CASE_FILE_CONTENT = json.dumps({
    "deal_id": "scraper_deal_001",
    "definition_of_done": {"success_criteria": "1000 valid records"},
    "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": 500}}],
    "disputes": [{"party": "client", "claim": "Only 500 delivered"}],
    "chain_integrity": {"verification": "PASS"},
})
CASE_FILE_HASH = hashlib.sha256(CASE_FILE_CONTENT.encode("utf-8")).hexdigest()
CASE_FILE_URL = "https://example.com/case-file.json"
TAMPERED_CONTENT = '{"tampered": true, "rows": 999}'

FULFILLED_CONTENT = json.dumps({
    "deal_id": "scraper_deal_001",
    "definition_of_done": {"success_criteria": "1000 valid records"},
    "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": 1000}}],
    "disputes": [{"party": "client", "claim": "Quality below bar"}],
    "chain_integrity": {"verification": "PASS"},
})
FULFILLED_HASH = hashlib.sha256(FULFILLED_CONTENT.encode("utf-8")).hexdigest()


def _mock_case(vm, body):
    vm.mock_web(r"example\.com", {"status": 200, "body": body})


def test_open_deal_locks_funds(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "funded"
    assert d["amount"] == VALUE
    assert d["client"].lower() == to_hex(direct_alice).lower()
    assert d["worker"].lower() == to_hex(direct_bob).lower()


def test_dispute_requires_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only parties"):
        c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)


def test_resolve_refunded_when_worker_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "REFUNDED", "reasoning": "Only 500 delivered"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "REFUNDED"
    assert d["status"] == "adjudicated"


def test_finalize_pays_winner(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "REFUNDED", "reasoning": "Worker failed"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    direct_vm.sender = direct_bob
    c.finalize(did)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "refunded"
    payouts = json.loads(c.get_payouts())
    assert len(payouts) == 1
    assert payouts[0]["to"].lower() == to_hex(direct_alice).lower()


def test_case_file_hash_mismatch_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    _mock_case(direct_vm, TAMPERED_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "EVIDENCE_MISMATCH"
    assert d["status"] == "refunded"


def test_resolve_approved_when_worker_delivers(direct_vm, direct_deploy, direct_alice, direct_bob):
    """APPROVED branch: matching hash + LLM approves the worker."""
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    _mock_case(direct_vm, FULFILLED_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "1000 records delivered"})
    c.dispute(did, CASE_FILE_URL, FULFILLED_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "APPROVED"
    assert d["status"] == "adjudicated"


def test_finalize_approved_pays_worker(direct_vm, direct_deploy, direct_alice, direct_bob):
    """release path: APPROVED then finalize pays the worker, not the client."""
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    _mock_case(direct_vm, FULFILLED_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "Delivered"})
    c.dispute(did, CASE_FILE_URL, FULFILLED_HASH)
    c.resolve(did)
    # The client is the losing party after APPROVED, so the client is the one
    # allowed to accept the verdict before the appeal window closes.
    direct_vm.sender = direct_alice
    c.finalize(did)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "released"
    payouts = json.loads(c.get_payouts())
    assert len(payouts) == 1
    assert payouts[0]["to"].lower() == to_hex(direct_bob).lower()


def test_timeout_release_requires_seven_days(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Escrow cannot be released early just because no dispute was filed."""
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, to_hex(direct_bob), 120, VALUE)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Timeout not reached"):
        c.timeout_release(did)
