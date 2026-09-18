"""Direct-mode tests for the Settlement contract (SDK v0.19 RC).

These run the real contract source through gltest's direct loader, so every
branch below exercises the same code path production uses.
"""
import json
import hashlib
import datetime

from tests.direct.conftest import mock_json_llm, to_hex

CONTRACT_PATH = "contracts/settlement.py"
VALUE = 2 * 10**18

# The off-chain recorder commits SHA-256(canonical_json(definition_of_done)) as
# the agreement hash (src/hash_chain.compute_agreement_hash). The contract
# recomputes that digest over the case file's own definition_of_done, so the
# fixture must canonicalize exactly the same way.
DOD = {"success_criteria": "1000 valid records"}
AGREEMENT_HASH = hashlib.sha256(
    json.dumps(DOD, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()

# Head of the off-chain event chain, as reported by chain_integrity.last_hash
# and anchored on chain by anchor_milestone().
CHAIN_HEAD = "b" * 64
CASE_FILE_URL = "https://example.com/case-file.json"
TAMPERED_CONTENT = '{"tampered": true, "rows": 999}'


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(ts: int) -> str:
    """Format a unix timestamp the way gl.message.datetime reports block time."""
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _case_file(*, dod=None, chain=None, delivered=500) -> str:
    return json.dumps({
        "deal_id": "scraper_deal_001",
        "definition_of_done": DOD if dod is None else dod,
        "events": [{"id": 1, "event_type": "DELIVERY", "payload": {"valid": delivered}}],
        "disputes": [{"party": "client", "claim": "Only 500 delivered"}],
        "chain_integrity": {"verification": "PASS", "last_hash": CHAIN_HEAD} if chain is None else chain,
    })


CASE_FILE_CONTENT = _case_file(delivered=500)
CASE_FILE_HASH = _sha(CASE_FILE_CONTENT)
FULFILLED_CONTENT = _case_file(delivered=1000)
FULFILLED_HASH = _sha(FULFILLED_CONTENT)


def _mock_case(vm, body, status=200):
    vm.mock_web(r"example\.com", {"status": status, "body": body})


def _open(c, vm, client, worker):
    """Open a deal whose agreement hash really matches the case file terms."""
    vm.sender = client
    return c.open_deal("deal1", AGREEMENT_HASH, to_hex(worker), 120, VALUE)


def test_open_deal_locks_funds(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    did = c.open_deal("deal1", AGREEMENT_HASH, to_hex(direct_bob), 120, VALUE)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "funded"
    assert d["amount"] == VALUE
    assert d["client"].lower() == to_hex(direct_alice).lower()
    assert d["worker"].lower() == to_hex(direct_bob).lower()


def test_dispute_requires_party(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only parties"):
        c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)


def test_resolve_refunded_when_worker_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "REFUNDED", "reasoning": "Only 500 delivered"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "REFUNDED"
    assert d["status"] == "adjudicated"


def test_finalize_pays_winner(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
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


def test_resolve_approved_when_worker_delivers(direct_vm, direct_deploy, direct_alice, direct_bob):
    """APPROVED branch: matching hash + LLM approves the worker."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
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
    did = _open(c, direct_vm, direct_alice, direct_bob)
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


# ---------------------------------------------------------------------------
# Deterministic evidence failures. None of these may reach the LLM: the point
# is that the contract refuses to adjudicate on evidence it cannot trust.
# ---------------------------------------------------------------------------


def test_case_file_hash_mismatch_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    """The served bytes are not the ones whose hash was anchored at dispute."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    _mock_case(direct_vm, TAMPERED_CONTENT)
    # No LLM mock is registered on purpose: reaching the model here is a bug.
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "EVIDENCE_MISMATCH"
    assert d["status"] == "refunded"
    payouts = json.loads(c.get_payouts())
    assert len(payouts) == 1
    assert payouts[0]["to"].lower() == to_hex(direct_alice).lower()


def test_agreement_mismatch_when_terms_rewritten(direct_vm, direct_deploy, direct_alice, direct_bob):
    """A party cannot swap the acceptance criteria and submit a matching hash.

    This is the attack the agreement_hash check exists for: the case file
    bytes hash correctly, but the definition_of_done inside them is not the
    one open_deal() committed to.
    """
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    rewritten = _case_file(dod={"success_criteria": "Deliver 10 records"})
    _mock_case(direct_vm, rewritten)
    c.dispute(did, CASE_FILE_URL, _sha(rewritten))
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "AGREEMENT_MISMATCH"
    assert d["status"] == "refunded"


def test_tampered_chain_refunds(direct_vm, direct_deploy, direct_alice, direct_bob):
    """A case file whose own integrity check FAILED is not evidence."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    body = _case_file(chain={"verification": "FAIL", "last_hash": CHAIN_HEAD})
    _mock_case(direct_vm, body)
    c.dispute(did, CASE_FILE_URL, _sha(body))
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "TAMPERED_EVIDENCE"
    assert d["status"] == "refunded"


def test_missing_definition_of_done_refunds(direct_vm, direct_deploy, direct_alice, direct_bob):
    """A case file with no terms at all cannot be adjudicated."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    body = _case_file(dod={})
    _mock_case(direct_vm, body)
    c.dispute(did, CASE_FILE_URL, _sha(body))
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "AGREEMENT_MISMATCH"
    assert d["status"] == "refunded"


# ---------------------------------------------------------------------------
# anchor_milestone is not decoration: once a delivery head is anchored, the
# case file must still agree with it or the settlement refuses to pay.
# ---------------------------------------------------------------------------


def test_anchor_mismatch_refunds(direct_vm, direct_deploy, direct_alice, direct_bob):
    """History rewritten after the anchor was posted is rejected."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    c.anchor_milestone(did, "delivery", CHAIN_HEAD)

    rewritten = _case_file(chain={"verification": "PASS", "last_hash": "c" * 64})
    _mock_case(direct_vm, rewritten)
    c.dispute(did, CASE_FILE_URL, _sha(rewritten))
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "ANCHOR_MISMATCH"
    assert d["status"] == "refunded"


def test_anchor_match_allows_adjudication(direct_vm, direct_deploy, direct_alice, direct_bob):
    """A case file that still matches the anchor proceeds normally."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    c.anchor_milestone(did, "delivery", CHAIN_HEAD)

    _mock_case(direct_vm, FULFILLED_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "Delivered"})
    c.dispute(did, CASE_FILE_URL, FULFILLED_HASH)
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "APPROVED"
    assert d["status"] == "adjudicated"


def test_unreachable_case_file_retries_then_unresolvable(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Three transient fetch failures settle as unresolvable, not as a payout."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    direct_vm.mock_web(r"example\.com", {"status": 503, "body": ""})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    for _ in range(3):
        c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "UNRESOLVABLE"
    assert d["status"] == "unresolvable"
    assert json.loads(c.get_payouts()) == []


def test_appeal_reruns_and_is_final(direct_vm, direct_deploy, direct_alice, direct_bob):
    """The loser may appeal once; the second verdict is final."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "REFUNDED", "reasoning": "Short"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)

    direct_vm.sender = direct_bob  # worker lost, so the worker appeals
    c.appeal(did)
    assert json.loads(c.get_deal(did))["status"] == "disputed"

    # gltest matches the FIRST registered mock, so the round-one LLM response
    # has to be cleared before the appeal round can return a different verdict.
    direct_vm.clear_mocks()
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "APPROVED", "reasoning": "Actually delivered"})
    c.resolve(did)
    d = json.loads(c.get_deal(did))
    assert d["verdict"] == "APPROVED"
    assert d["status"] == "adjudicated"
    assert d["appeals_used"] == 1
    assert d["reasoning"].startswith("FINAL appeal")


def test_appeal_requires_loser(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    _mock_case(direct_vm, CASE_FILE_CONTENT)
    mock_json_llm(direct_vm, r"adjudicator", {"verdict": "REFUNDED", "reasoning": "Short"})
    c.dispute(did, CASE_FILE_URL, CASE_FILE_HASH)
    c.resolve(did)
    direct_vm.sender = direct_alice  # client won; the client may not appeal
    with direct_vm.expect_revert("Only loser may appeal"):
        c.appeal(did)


def test_timeout_release_requires_seven_days(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Escrow cannot be released early just because no dispute was filed."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Timeout not reached"):
        c.timeout_release(did)


def test_timeout_release_pays_worker_after_seven_days(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Past the timeout the worker is paid — the escrow is not trapped."""
    c = direct_deploy(CONTRACT_PATH)
    did = _open(c, direct_vm, direct_alice, direct_bob)
    created_at = json.loads(c.get_deal(did))["created_at_ts"]
    warp_to = _iso(created_at + 86400 * 8)
    direct_vm.warp(warp_to)
    direct_vm.sender = direct_bob
    c.timeout_release(did)
    d = json.loads(c.get_deal(did))
    assert d["status"] == "released"
    assert d["verdict"] == "TIMEOUT"
    assert d["payout_status"] == "paid"
    payouts = json.loads(c.get_payouts())
    assert len(payouts) == 1
    assert payouts[0]["to"].lower() == to_hex(direct_bob).lower()
