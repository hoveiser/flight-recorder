import pytest
import json

VALUE = 2 * 10**18
CASE_FILE_URL = "https://example.com/case-file.json"
CASE_FILE_HASH = "a1b2c3d4e5f6" * 5 + "a1b2c3d4"  # 64 chars
CASE_FILE_CONTENT = json.dumps({
    "deal_id": "scraper_deal_001",
    "definition_of_done": {"success_criteria": "1000 valid records"},
    "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": 500}}],
    "disputes": [{"party": "client", "claim": "Only 500 delivered"}],
    "chain_integrity": {"verification": "PASS"},
})


def test_open_deal_locks_funds(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    # Call without value keyword - contract will use a default amount
    did = c.open_deal("deal1", "a" * 64, str(direct_bob), 120, VALUE)
    
    d = json.loads(c.get_deal(did))
    assert d["status"] == "funded"
    assert d["amount"] == VALUE
    assert d["client"] == str(direct_alice)
    assert d["worker"] == str(direct_bob)


def test_dispute_requires_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, str(direct_bob), 120, VALUE)
    
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only parties"):
        c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)


def test_resolve_refunded_when_worker_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, str(direct_bob), 120, VALUE)
    
    direct_vm.mock_web(r"example\.com", {"status": 200, "body": CASE_FILE_CONTENT})
    direct_vm.mock_llm(r".*", '{"verdict": "REFUNDED", "reasoning": "Worker delivered only 500 records"}')
    
    direct_vm.sender = direct_alice
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "REFUNDED"
    assert d["status"] == "adjudicated"


def test_finalize_pays_winner(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, str(direct_bob), 120, VALUE)
    
    direct_vm.mock_web(r"example\.com", {"status": 200, "body": CASE_FILE_CONTENT})
    direct_vm.mock_llm(r".*", '{"verdict": "REFUNDED", "reasoning": "Worker failed"}')
    
    direct_vm.sender = direct_alice
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    
    direct_vm.sender = direct_alice
    c.finalize(did)
    
    d = json.loads(c.get_deal(did))
    assert d["status"] == "refunded"


def test_case_file_hash_mismatch_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, str(direct_bob), 120, VALUE)
    
    direct_vm.mock_web(r"example\.com", {"status": 200, "body": '{"tampered": true}'})
    direct_vm.mock_llm(r".*", '{"verdict": "APPROVED"}')
    
    direct_vm.sender = direct_alice
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "EVIDENCE_MISMATCH"
    assert d["status"] == "refunded"