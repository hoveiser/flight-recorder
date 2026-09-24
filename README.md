# Flight Recorder

**A tamper-evident evidence layer + on-chain settlement for agent-to-agent deals.**

Built for the [Agent Tank Hackathon](https://portal.genlayer.foundation/agent-tank) — Onchain Justice track.
[Review Submission](https://portal.genlayer.foundation/builders/explorer/flight-recorder?category=agent-tank)

> *"GenEscrow is the judge. Flight Recorder is the black box no one can deny."*

## The Problem

When two agents do business together, disputes happen. But without neutral evidence, resolution depends on who's louder — not who's right.

**Flight Recorder** solves this by recording every event (requests, responses, deliveries, validations) into a hash-chained log that can't be tampered with. When a dispute happens, the **case file** becomes evidence for on-chain adjudication.

**Settlement** is a GenLayer Intelligent Contract that acts as the judge: it reads the case file, verifies its integrity, and uses AI validators to reach a verdict.

## Architecture

**Off-Chain (Flight Recorder):**
- FastAPI + SQLite
- Hash chain (tamper-evident)
- Case file export (GenLayer-ready JSON)

**On-Chain (Settlement):**
- open_deal: lock escrow with agreement hash
- dispute: file dispute with case file hash
- resolve: AI validators adjudicate
- finalize: pay winner based on verdict

**Flow:** Agent creates deal → records events → files dispute → exports case file → Settlement contract reads case file → AI validators reach verdict → payment/refund executed.

### Key Principles

| Layer | Role | Source of Truth |
|-------|------|-----------------|
| Flight Recorder (off-chain) | Evidence witness | Hash chain + case file |
| Settlement (on-chain) | Judge + escrow | Contract state + validator consensus |

**Why off-chain evidence?** Raw payloads are too large for on-chain storage. The hash chain provides tamper evidence; on-chain anchors provide public proof.

**Why on-chain settlement?** Payment requires trustless execution. GenLayer's AI validators provide neutral adjudication without trusting any single party.

## Features

### Off-Chain (Flight Recorder API)

- **Deal creation** with definition-of-done and agreement hash
- **Event recording** into append-only hash chain
- **Hash verification** (tamper detection)
- **Dispute filing** by deal parties
- **Case file export** (GenLayer-ready JSON)

### On-Chain (Settlement Contract)

- **Escrow**: open_deal locks funds with agreement hash
- **Milestone anchoring**: anchor_milestone records chain heads on-chain
- **Dispute filing**: dispute submits case file hash
- **AI adjudication**: resolve uses GenLayer validators to reach verdict
- **Appeal process**: appeal allows loser to contest
- **Finalization**: finalize pays winner based on verdict
- **Timeout release**: timeout_release auto-pays if no dispute

## Quick Start

### 1. Off-Chain Service

    pip install -r requirements.txt
    uvicorn src.main:app --reload

API docs: http://localhost:8000/docs

### 2. Run Tests

    pytest tests/ -v

Expected: **34 passed** (12 off-chain + 22 direct-mode).

## On-Chain Settlement (Studio Next)

The Settlement contract is deployed on GenLayer Studio Next (chain ID `61997`).

- Contract address: `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D`
- Explorer: https://explorer-studio-dev.genlayer.com/address/0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D

Run the end-to-end flow from the repository root:

    npm install
    node scripts/e2e_demo.js

Run the direct Settlement tests:

    pytest tests/direct/test_settlement.py -v

### Deployment history

| Version | Address | What it is |
|---------|---------|------------|
| **v1** | `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35` | Demo-video lifecycle: the first end-to-end run used in the recorded walkthrough. |
| **v2** | `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` | Current on-chain deployment. Carries the live scenarios, including the APPROVED happy path. See `scripts/e2e_results.md` for the raw run output. |
| **v3** | repo HEAD (not redeployed) | Repo-HEAD hardening: payout atomicity, agreement and anchor verification, deterministic time, exception-path retry counter, and a fail-closed timeout. Covered by the direct-mode tests. Deliberately **not** redeployed so the on-chain evidence above stays one continuous history rather than a second, parallel address. |

**Current status:** v3 contract code is merged to main and covered by direct-mode tests (34 passed); the live on-chain instance remains v2 (0x8BC5…) to preserve the on-chain evidence trail. The scheduled v3 redeploy is on the roadmap.

## Versioning

On-chain deployments are numbered D1 (0x4bA3…), D2 (0x8BC5…, live). Code generations are numbered v3 (merged, not redeployed), v4 (hardening + first roadmap items), v5 (product generation). A code generation is not a deployment until it appears in Deployment history.

### 3. Run Demos

    python demo/scraper_dispute.py
    python demo/code_quality_dispute.py

## API Reference

### Off-Chain Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /deals | Create a deal with definition-of-done |
| GET | /deals/{deal_id} | Get deal details |
| POST | /events | Record an event into the hash chain |
| GET | /deals/{deal_id}/events | Get all events for a deal |
| GET | /deals/{deal_id}/verify | Verify hash chain integrity |
| POST | /deals/{deal_id}/seal | Freeze the evidence log, return chain head |
| POST | /deals/{deal_id}/dispute | File a dispute (parties only) |
| GET | /deals/{deal_id}/disputes | Get all disputes |
| GET | /deals/{deal_id}/case-file | Export case file for adjudication |

### Event Types

| Type | Description |
|------|-------------|
| REQUEST | Client sends request |
| RESPONSE | Worker responds |
| DELIVERY | Worker delivers |
| VALIDATION | Client validates |
| STATE_CHANGE | Status change |
| WARNING | Warning event |
| ERROR | Error event |
| PAYMENT_INTENT | Payment intent |
| CUSTOM | Custom event |

### On-Chain Contract Methods

| Method | Type | Description |
|--------|------|-------------|
| open_deal | write.payable | Lock escrow with agreement hash |
| anchor_milestone | write | Record chain head on-chain |
| dispute | write | File dispute with case file hash |
| resolve | write | AI validators adjudicate |
| appeal | write | Loser contests verdict |
| finalize | write | Pay winner |
| timeout_release | write | Auto-pay after timeout |
| get_deal | view | Get deal state |
| get_payouts | view | Get payout history |

### Verdict Types

| Verdict | Meaning | Winner |
|---------|---------|--------|
| APPROVED | Worker fulfilled agreement | Worker gets paid |
| REFUNDED | Worker failed to deliver | Client gets refund |
| EVIDENCE_MISMATCH | Case file was tampered | Client gets refund |
| AGREEMENT_MISMATCH ¹ | Case-file terms are not the anchored agreement hash | Client gets refund |
| ANCHOR_MISMATCH ¹ | Case-file chain head is not the anchored head | Client gets refund |
| UNRESOLVABLE | Too many failed attempts | No payout |
| TIMEOUT | No dispute filed | Worker gets paid |

¹ **v3 onward, repo HEAD.** These two verdicts are added by the hardening work
on the repo HEAD and are covered by the direct-mode test suite. They are not yet
present in the deployed v2 contract address below, which is why the on-chain
evidence stays a continuous v2 record.

## Hash Chain

Each event is linked to the previous one:

    Event 1: previous = GENESIS
    Event 2: previous = Event 1's hash
    Event 3: previous = Event 2's hash

**Tamper detection:**
- Modify any payload → hash chain breaks → verify returns FAIL
- Delete any event → chain has gap → verify returns FAIL

### Evidence seal

The chain is append-only while a deal is live. The moment a dispute is filed the
log **freezes**: `POST /deals/{deal_id}/seal` sets a `sealed` flag on the deal and
returns the current chain head hash — the exact value that gets anchored on-chain
by `dispute`. After that, `POST /events` for the deal is rejected with
**HTTP 409 `Evidence log sealed after dispute`**.

Why: the contract adjudicates against the case-file hash anchored at dispute
time. If events could still be appended afterwards, a party could pad the log
with favourable entries after anchoring, leaving the on-chain hash describing a
record that no longer exists off-chain. Sealing makes the anchored hash final.

Sealing is idempotent — calling it twice returns the same head hash. It freezes
*writes* only: `GET /deals/{deal_id}/verify` and `GET /deals/{deal_id}/case-file`
keep working and the chain still verifies `PASS`.

Both live-demo scripts (`scripts/run_live_scenarios.js`, `scripts/e2e_demo.js`)
call `/seal` immediately before sending the on-chain `dispute` transaction, so
sealing is never a step anyone has to remember.

## Case File Format

    {
      "deal_id": "scraper_deal_001",
      "definition_of_done": {"success_criteria": "1000 valid records"},
      "parties": ["agentA", "agentB"],
      "agreement_hash": "sha256...",
      "events": [...],
      "disputes": [...],
      "chain_integrity": {
        "verification": "PASS",
        "events": 5
      }
    }

## Project Structure

    flight-recorder/
    ├── src/                      # Off-chain evidence service
    │   ├── main.py               # FastAPI app
    │   ├── models.py             # Pydantic models
    │   ├── hash_chain.py         # SHA-256 hash chain logic
    │   └── db.py                 # SQLite database
    ├── contracts/
    │   └── settlement.py         # GenLayer Intelligent Contract
    ├── tests/
    │   ├── test_flight_recorder.py  # Off-chain tests (13 tests)
    │   └── direct/test_settlement.py # Direct-mode tests (21 tests)
    ├── demo/
    │   ├── scraper_dispute.py
    │   └── code_quality_dispute.py
    └── README.md

## Threat model & known limitations
- Unsigned events: the hash chain proves integrity (no later edit), not provenance (who wrote it). A party controlling the logging service could fabricate a consistent log. Mitigation today: the case-file hash is anchored on-chain at dispute and validators re-fetch the served bytes; signed events are on the v4 roadmap.
- Omission: the chain cannot prove an event was NOT skipped. anchor_milestone pins the chain head; periodic auto-anchoring is on the roadmap.
- Concurrency: POST /events is serialized per deal (threading lock + BEGIN IMMEDIATE), so concurrent writes cannot fork the chain; regression-tested by test_concurrent_writes_cannot_fork_chain.
- Seal access: POST /deals/{id}/seal requires a deal-party actor (body field or X-Actor); strangers cannot freeze an opponent's log.
- Prompt injection: validators receive evidence inside data tags with instructions to ignore embedded commands; adversarial case files are regression-tested by test_prompt_injection_does_not_change_verdict.
- Timestamps are service-claimed until anchored; on-chain anchoring provides authoritative order.
- Live on-chain instance is v2; v3/v4 contract code is merged and direct-mode tested, redeploy scheduled (see Versioning and Deployment history).

## Roadmap & open questions

Known gaps, stated plainly rather than discovered later:

- **Ambiguous-dispute benchmark.** Add partial-delivery, conflicting-validation and
  missing-evidence case files with their expected verdicts, and execute them in
  direct mode so the equivalence principle is measured against cases where the
  right answer is genuinely contested, not only the clear-cut ones.
- **Signature-based actor authentication for `/events`.** Event writes are currently
  trust-based (MVP): the caller asserts an `actor` string. Signing events with the
  actor's key would make attribution verifiable rather than claimed.
- **Per-deal write locking or `BEGIN IMMEDIATE` transactions.** The hash chain has a
  concurrency race: two simultaneous `/events` calls for the same deal can both read
  the same previous hash and fork the chain. Serializing writes per deal removes it.
- **Appeal with new evidence.** Today `appeal` re-runs consensus over the *same*
  anchored case file, so it can only produce a different verdict by chance. A real
  appeal would accept a new case-file hash and re-anchor it.
- **Redeploy v3 to Studio Next.** The deployed contract is v2 while the repo HEAD is
  v3, so the hardening (agreement/anchor verification, fail-closed timeout, exception
  retry) is proven by the direct-mode suite but not yet by on-chain execution.
  Deliberately deferred to post-hackathon so the live evidence stays continuous.
- **Browser-executed dispute flow.** Wallet connect, Studio Next chain switch,
  integrated faucet, and in-browser open_deal/dispute/resolve/finalize.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Off-chain API | FastAPI + SQLite |
| On-chain contract | GenLayer SDK v0.19.0rc2 (consensus v0.6) |
| Testing | pytest + genlayer-test (Direct Mode) |
| CI | GitHub Actions |

## License

[MIT](LICENSE) © 2026 hoveiser
