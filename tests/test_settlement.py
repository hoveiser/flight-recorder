import pytest
import json

VALUE = 2 * 10**18
CASE_FILE_URL = "https://example.com/case-file.json"
CASE_FILE_HASH = "a" * 64  # Exactly 64 chars (SHA-256 hex)
CASE_FILE_CONTENT = json.dumps({
    "deal_id": "scraper_deal_001",
    "definition_of_done": {"success_criteria": "1000 valid records"},
    "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": 500}}],
    "disputes": [{"party": "client", "claim": "Only 500 delivered"}],
    "chain_integrity": {"verification": "PASS"},
})


def _hex(addr_bytes):
    """Convert bytes to hex string with 0x prefix (matching GenLayer Address format)"""
    return "0x" + addr_bytes.hex()


def test_open_deal_locks_funds(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120, VALUE)
    
    d = json.loads(c.get_deal(did))
    assert d["status"] == "funded"
    assert d["amount"] == VALUE
    assert d["client"].lower() == _hex(direct_alice).lower()
    assert d["worker"].lower() == _hex(direct_bob).lower()


def test_dispute_requires_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120, VALUE)
    
    direct_vm.sender = direct_charlie
    with pytest.raises(Exception) as exc_info:
        c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    assert "Only parties" in str(exc_info.value)


def test_resolve_refunded_when_worker_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120, VALUE)
    
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
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120, VALUE)
    
    direct_vm.mock_web(r"example\.com", {"status": 200, "body": CASE_FILE_CONTENT})
    direct_vm.mock_llm(r".*", '{"verdict": "REFUNDED", "reasoning": "Worker failed"}')
    
    direct_vm.sender = direct_alice
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    
    d = json.loads(c.get_deal(did))
    assert d["status"] == "adjudicated"
    assert d["verdict"] == "REFUNDED"


def test_case_file_hash_mismatch_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120, VALUE)
    
    direct_vm.mock_web(r"example\.com", {"status": 200, "body": '{"tampered": true}'})
    direct_vm.mock_llm(r".*", '{"verdict": "APPROVED"}')
    
    direct_vm.sender = direct_alice
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "EVIDENCE_MISMATCH"
    assert d["status"] == "refunded"