import pytest
import json
import types
import re as _re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VALUE = 2 * 10**18
NOW = "2026-09-10T12:00:00Z"
LATER = "2026-09-10T14:00:00Z"

CASE_FILE_URL = "https://example.com/case-file.json"
CASE_FILE_CONTENT = json.dumps({
    "deal_id": "scraper_deal_001",
    "definition_of_done": {"success_criteria": "1000 valid records"},
    "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": 500}}],
    "disputes": [{"party": "client", "claim": "Only 500 delivered"}],
    "chain_integrity": {"verification": "PASS"},
})
CASE_FILE_HASH = "a1b2c3d4e5f6" * 5 + "a1b2c3d4"  # 64 chars

_web_mocks = {}
_llm_mocks = {}
_prompts = []
_eth_sends = []


class FakeAddress:
    def __init__(self, value):
        if isinstance(value, bytes):
            self.hex = "0x" + value.hex()
        elif isinstance(value, str):
            self.hex = value.lower() if value.startswith("0x") else "0x" + value.lower()
        else:
            self.hex = str(value)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.hex.lower() == other.lower()
        if hasattr(other, "hex"):
            return self.hex.lower() == other.hex.lower()
        return False

    def __str__(self):
        return self.hex


class FakeWebResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.status = status
        self.body = body.encode("utf-8") if isinstance(body, str) else body


class FakeGlCallResult:
    def get(self):
        return None


class _Return:
    def __init__(self, calldata):
        self.calldata = calldata


def _reset():
    _web_mocks.clear()
    _llm_mocks.clear()
    del _prompts[:]
    del _eth_sends[:]


def _mock(status, body):
    return {"status": status, "body": body}


def _msg(sender, value=0, dt=NOW):
    import genlayer.gl as gl
    gl.message = types.SimpleNamespace(sender_address=FakeAddress(sender), value=value)
    gl.message_raw = {"datetime": dt}


def _patch_runtime():
    import genlayer
    import genlayer.gl as gl
    import genlayer.gl._internal.gl_call as gl_call

    gl.wasi = types.SimpleNamespace(get_self_balance=lambda: 10**30)

    def fake_gl_call_generic(payload, cb):
        if isinstance(payload, dict) and "EthSend" in payload:
            _eth_sends.append(payload["EthSend"])
        return FakeGlCallResult()

    gl_call.gl_call_generic = fake_gl_call_generic
    genlayer.Address = FakeAddress
    gl.eq_principle = types.SimpleNamespace(strict_eq=lambda fn: fn())

    def fake_run_nondet_unsafe(leader_fn, validator_fn):
        lead = leader_fn()
        ret = _Return(lead)
        agreed = validator_fn(ret)
        if not agreed:
            return {"verdict": "UNVERIFIABLE", "reasoning": "validator disagreement"}
        return lead

    gl.vm = types.SimpleNamespace(run_nondet_unsafe=fake_run_nondet_unsafe, Return=_Return)

    class FakeWeb:
        @staticmethod
        def get(url):
            for pattern, resp in _web_mocks.items():
                if _re.search(pattern, url):
                    return FakeWebResponse(resp["status"], resp["body"])
            return FakeWebResponse(404, "Not Found")

    class FakeNondet:
        web = FakeWeb()

        @staticmethod
        def exec_prompt(prompt):
            _prompts.append(prompt)
            for pattern, resp in _llm_mocks.items():
                if _re.search(pattern, prompt):
                    return resp
            return '{"verdict": "UNVERIFIABLE", "reasoning": "no mock"}'

    gl.nondet = FakeNondet()


def _deploy(direct_deploy):
    c = direct_deploy("contracts/settlement.py", sdk_version="v0.2.16")
    import genlayer
    if not hasattr(c, "deals"):
        c.deals = genlayer.TreeMap[str, str]()
    _patch_runtime()
    return c


def _hex(b):
    return "0x" + b.hex()


def test_open_deal_locks_funds(direct_vm, direct_deploy, direct_alice, direct_bob):
    _reset()
    _msg(direct_alice, VALUE)
    c = _deploy(direct_deploy)
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "funded"
    assert d["amount"] == VALUE
    assert d["client"] == _hex(direct_alice)
    assert d["worker"] == _hex(direct_bob)


def test_dispute_requires_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    _reset()
    _msg(direct_alice, VALUE)
    c = _deploy(direct_deploy)
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120)
    _msg(direct_charlie, 0)
    with pytest.raises(AssertionError) as e:
        c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    assert "Only parties" in str(e.value)


def test_resolve_refunded_when_worker_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    _reset()
    _msg(direct_alice, VALUE)
    c = _deploy(direct_deploy)
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120)
    _msg(direct_alice, 0)
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    _web_mocks[r"example\.com"] = _mock(200, CASE_FILE_CONTENT)
    _llm_mocks[r".*"] = '{"verdict": "REFUNDED", "reasoning": "Worker delivered only 500 records"}'
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "REFUNDED"
    assert d["status"] == "adjudicated"


def test_finalize_pays_winner(direct_vm, direct_deploy, direct_alice, direct_bob):
    _reset()
    _msg(direct_alice, VALUE)
    c = _deploy(direct_deploy)
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120)
    _msg(direct_alice, 0)
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    _web_mocks[r"example\.com"] = _mock(200, CASE_FILE_CONTENT)
    _llm_mocks[r".*"] = '{"verdict": "REFUNDED", "reasoning": "Worker failed"}'
    c.resolve(did)
    _msg(direct_alice, 0, dt=LATER)
    c.finalize(did)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "refunded"
    assert len(_eth_sends) == 1
    assert _eth_sends[0]["value"] == VALUE
    assert str(_eth_sends[0]["address"]) == _hex(direct_alice)


def test_case_file_hash_mismatch_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    _reset()
    _msg(direct_alice, VALUE)
    c = _deploy(direct_deploy)
    did = c.open_deal("deal1", "a" * 64, _hex(direct_bob), 120)
    _msg(direct_alice, 0)
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    _web_mocks[r"example\.com"] = _mock(200, '{"tampered": true}')
    _llm_mocks[r".*"] = '{"verdict": "APPROVED"}'
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "EVIDENCE_MISMATCH"
    assert d["status"] == "refunded"