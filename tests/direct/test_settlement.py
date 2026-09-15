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
