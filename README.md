# Flight Recorder

**A tamper-evident evidence layer + on-chain settlement for agent-to-agent deals.**

Built for the [Agent Tank Hackathon](https://portal.genlayer.foundation/agent-tank) — Onchain Justice track.
[Review Submission](https://portal.genlayer.foundation/builders/explorer/flight-recorder?category=agent-tank)

> _"GenEscrow is the judge. Flight Recorder is the black box no one can deny."_

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

| Layer                       | Role             | Source of Truth                      |
| --------------------------- | ---------------- | ------------------------------------ |
| Flight Recorder (off-chain) | Evidence witness | Hash chain + case file               |
| Settlement (on-chain)       | Judge + escrow   | Contract state + validator consensus |

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

Expected: **37 passed** (15 off-chain + 22 direct-mode).

### 3. Run Demos

With the off-chain service from step 1 still running:

    python demo/scraper_dispute.py
    python demo/code_quality_dispute.py

Each script records a full deal lifecycle (events → seal → verify) against the local API.

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

| Version | Address                                      | What it is                                                                                                                                                                                                                                                                                                                   |
| ------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **v1**  | `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35` | Demo-video lifecycle: the first end-to-end run used in the recorded walkthrough.                                                                                                                                                                                                                                             |
| **v2**  | `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` | Current on-chain deployment. Carries the live scenarios, including the APPROVED happy path. See `scripts/e2e_results.md` for the raw run output.                                                                                                                                                                             |
| **v3**  | repo HEAD (not redeployed)                   | Repo-HEAD hardening: payout atomicity, agreement and anchor verification, deterministic time, exception-path retry counter, and a fail-closed timeout. Covered by the direct-mode tests. Deliberately **not** redeployed so the on-chain evidence above stays one continuous history rather than a second, parallel address. |

**Current status:** v3 contract code is merged to main and covered by direct-mode tests (37 passed); the live on-chain instance remains v2 (0x8BC5…) to preserve the on-chain evidence trail. The scheduled v3 redeploy is on the roadmap. A full security and correctness audit of the contract is in [AUDIT.md](AUDIT.md).

## Versioning

On-chain deployments are numbered D1 (0x4bA3…), D2 (0x8BC5…, live). Code generations are numbered v3 (merged, not redeployed), v4 (hardening + first roadmap items), v5 (product generation). A code generation is not a deployment until it appears in Deployment history.

## API Reference

### Off-Chain Endpoints

| Method | Endpoint                   | Description                                |
| ------ | -------------------------- | ------------------------------------------ |
| POST   | /deals                     | Create a deal with definition-of-done      |
| GET    | /deals/{deal_id}           | Get deal details                           |
| POST   | /events                    | Record an event into the hash chain        |
| GET    | /deals/{deal_id}/events    | Get all events for a deal                  |
| GET    | /deals/{deal_id}/verify    | Verify hash chain integrity                |
| POST   | /deals/{deal_id}/seal      | Freeze the evidence log, return chain head |
| POST   | /deals/{deal_id}/dispute   | File a dispute (parties only)              |
| GET    | /deals/{deal_id}/disputes  | Get all disputes                           |
| GET    | /deals/{deal_id}/case-file | Export case file for adjudication          |

### Event Types

| Type           | Description          |
| -------------- | -------------------- |
| REQUEST        | Client sends request |
| RESPONSE       | Worker responds      |
| DELIVERY       | Worker delivers      |
| VALIDATION     | Client validates     |
| STATE_CHANGE   | Status change        |
| WARNING        | Warning event        |
| ERROR          | Error event          |
| PAYMENT_INTENT | Payment intent       |
| CUSTOM         | Custom event         |

### On-Chain Contract Methods

| Method           | Type          | Description                      |
| ---------------- | ------------- | -------------------------------- |
| open_deal        | write.payable | Lock escrow with agreement hash  |
| anchor_milestone | write         | Record chain head on-chain       |
| dispute          | write         | File dispute with case file hash |
| resolve          | write         | AI validators adjudicate         |
| appeal           | write         | Loser contests verdict           |
| finalize         | write         | Pay winner                       |
| timeout_release  | write         | Auto-pay after timeout           |
| get_deal         | view          | Get deal state                   |
| get_payouts      | view          | Get payout history               |

### Verdict Types

| Verdict              | Meaning                                             | Winner             |
| -------------------- | --------------------------------------------------- | ------------------ |
| APPROVED             | Worker fulfilled agreement                          | Worker gets paid   |
| REFUNDED             | Worker failed to deliver                            | Client gets refund |
| EVIDENCE_MISMATCH    | Case file was tampered                              | Client gets refund |
| AGREEMENT_MISMATCH ¹ | Case-file terms are not the anchored agreement hash | Client gets refund |
| ANCHOR_MISMATCH ¹    | Case-file chain head is not the anchored head       | Client gets refund |
| UNRESOLVABLE         | Too many failed attempts                            | No payout          |
| TIMEOUT              | No dispute filed                                    | Worker gets paid   |

¹ **v3 onward, repo HEAD.** These two verdicts are added by the hardening work
on the repo HEAD and are covered by the direct-mode test suite. They are not yet
present in the deployed v2 contract address below, which is why the on-chain
evidence stays a continuous v2 record. In particular, a browser demo deal whose
case file carries terms other than the deal's own agreement is adjudicated on
the case file's terms by the deployed v2 — it does **not** come back
AGREEMENT_MISMATCH until v3 is redeployed.

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
returns the current chain head hash. After that, `POST /events` for the deal is
rejected with **HTTP 409 `Evidence log sealed after dispute`**.

Note precisely what reaches the chain: `dispute()` anchors the **case-file hash**,
not the chain head. The chain head returned by `/seal` only becomes on-chain
evidence if a party sends a separate `anchor_milestone(deal_id, "delivery",
chain_head)` transaction — which `scripts/run_live_scenarios.js` does and the
browser flow does not.

Why: the contract adjudicates against the case-file hash anchored at dispute
time. If events could still be appended afterwards, a party could pad the log
with favourable entries after anchoring, leaving the on-chain hash describing a
record that no longer exists off-chain. Sealing makes the anchored hash final.

Sealing is idempotent — calling it twice returns the same head hash. It freezes
_writes_ only: `GET /deals/{deal_id}/verify` and `GET /deals/{deal_id}/case-file`
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
    │   ├── test_flight_recorder.py  # Off-chain tests (12 tests)
    │   ├── test_agreement_hash_canonicalization.py  # Cross-runtime hash tests (3 tests)
    │   └── direct/test_settlement.py # Direct-mode tests (22 tests)
    ├── demo/
    │   ├── scraper_dispute.py
    │   └── code_quality_dispute.py
    └── README.md

## Threat model & known limitations

- Unsigned events: the hash chain proves integrity (no later edit), not provenance (who wrote it). A party controlling the logging service could fabricate a consistent log. Mitigation today: writes require a wallet-signed session, and the case-file hash is anchored on-chain at dispute and validators re-fetch the served bytes; per-event signatures remain on the roadmap.
- Omission: the chain cannot prove an event was NOT skipped. anchor_milestone pins the chain head; periodic auto-anchoring is on the roadmap.
- Concurrency: POST /events is serialized per deal (threading lock + BEGIN IMMEDIATE), so concurrent writes cannot fork the chain; regression-tested by test_concurrent_writes_cannot_fork_chain.
- Seal access: POST /deals/{id}/seal requires a deal-party actor (body field or X-Actor); strangers cannot freeze an opponent's log.
- Prompt injection: validators receive evidence inside data tags with instructions to ignore embedded commands; adversarial case files are regression-tested by test_prompt_injection_does_not_change_verdict.
- Timestamps are service-claimed until anchored; on-chain anchoring provides authoritative order.
- Live on-chain instance is v2; v3/v4 contract code is merged and direct-mode tested, redeploy scheduled (see Versioning and Deployment history).
- **Escrow amount is caller-declared, not value-derived (audit CRITICAL, present in the
  deployed v2 as well as repo HEAD).** `open_deal` takes `amount` and only falls back to
  `gl.message.value` when it is zero, so a caller can record more escrow than it sent and
  later withdraw that larger figure from the contract's shared balance. Every first-party
  caller (browser and both scripts) omits the argument and is unaffected. See AUDIT.md F1.
- **`unresolvable` is a dead state (audit HIGH).** After three failed resolve attempts the
  escrow can no longer be moved by any method — `dispute`, `resolve`, `appeal`, `finalize`
  and `timeout_release` all gate on other statuses — so funds lock instead of settling.
  `resolve` is also unauthenticated, which lets a third party spend a deal's retry
  allowance deliberately. See AUDIT.md F2/F3.
- **`anchor_milestone` overwrites an existing anchor (audit HIGH).** Re-posting a milestone
  with a _different_ head silently replaces it, so the anchored chain head a case file is
  checked against is not immutable. See AUDIT.md F4.
- **`chain_integrity.verification` in a case file is self-attested (audit MEDIUM).** The
  contract reads the PASS/FAIL flag out of the same untrusted JSON whose hash it was given,
  so that one check proves the file claims integrity, not that it has any. The on-chain
  anchor and the agreement hash are the checks that bind it. See AUDIT.md F5.
- Direct-mode tests need Linux/macOS: gltest's loader replaces fd 0 with a temp file and
  unlinks it while still open, which Windows rejects (`WinError 32`). Run them in the
  codespace or CI.

## Roadmap & open questions

Known gaps, stated plainly rather than discovered later:

- **Ambiguous-dispute benchmark.** Add partial-delivery, conflicting-validation and
  missing-evidence case files with their expected verdicts, and execute them in
  direct mode so the equivalence principle is measured against cases where the
  right answer is genuinely contested, not only the clear-cut ones.
- **Actor attribution is session-verified (wallet-signed login since v5); per-event
  cryptographic signatures remain on the roadmap.** `POST /events` and `/seal`
  require a session token, so a caller proves control of an address before writing.
  The event body itself is still unsigned, so a replayed session could post under
  that address; signing each payload with the actor's key closes the gap.
- **Appeal with new evidence.** Today `appeal` re-runs consensus over the _same_
  anchored case file, so it can only produce a different verdict by chance. A real
  appeal would accept a new case-file hash and re-anchor it.
- **Redeploy v3 to Studio Next.** The deployed contract is v2 while the repo HEAD is
  v3, so the hardening (agreement/anchor verification, fail-closed timeout, exception
  retry) is proven by the direct-mode suite but not yet by on-chain execution.
  Deliberately deferred to post-hackathon so the live evidence stays continuous.
- **Hosted evidence API — DONE.** The off-chain recorder now runs on
  PythonAnywhere (`https://hreicher.pythonanywhere.com`), which `index.html`
  targets for `github.io` hosts, so visitors can complete the whole lifecycle
  without cloning the repo. The local path (`uvicorn src.main:app`) remains for
  offline use and for networks PythonAnywhere geo-blocks (HTTP 451).
- **Integrated faucet.** Visitors currently fund their own test transactions from the
  Studio Next faucet, which is why every on-chain row is a real independently
  verifiable run. Wiring a faucet into the page would lower the barrier for judges
  without changing that property.

## Runtime compatibility

The reference runtime is **Python 3.12** (what CI runs); the supported range is
**3.10 – 3.14**. Dependencies are held to what works across that range — do not
upgrade them or chase a newer Python before the hackathon deadline.

| Environment               | Python      | Status                                 |
| ------------------------- | ----------- | -------------------------------------- |
| Codespace                 | 3.14        | tested-green                           |
| CI (GitHub Actions)       | 3.12        | reference runtime                      |
| PythonAnywhere web worker | 3.10        | deployed-live                          |
| Supported range           | 3.10 – 3.14 | `pytest tests/` green across the range |

## Hosting the evidence API (PythonAnywhere)

The off-chain recorder is served on PythonAnywhere's free tier through an
a2wsgi WSGI shim.

- **Single worker (required).** Nonces and sessions live in in-process
  dictionaries (`_nonces`, `_sessions` in `src/main.py`), so the web app must run
  as a single worker. Multiple workers or a restart would strand a token issued
  by one process and reject it in another.
- **Session model.** `POST /api/auth/nonce` issues a single-use nonce (deleted on
  a successful `verify`); `POST /api/auth/verify` recovers the signer with
  `eth_account` and mints a Bearer token valid for **7 days**. The browser keeps
  the token in `localStorage`, so any XSS on the page could read it — there is no
  refresh or server-side revocation.
- **CORS.** `allow_origins=["*"]` with headers echoing `authorization,
content-type`; a preflight `OPTIONS` returns 200 with those headers (verified
  against the app). The wildcard is safe here only because the token is not a
  cookie and is not sent automatically cross-site — it is read from the page's own
  `localStorage`.
- **Actor binding (known limitation).** A valid Bearer token lets its holder post
  any `actor` string to `/events`, and seal `/deals/{id}/seal` with any actor that
  is a deal party: the session proves an address logged in but does not bind the
  event's `actor` to that address. Per-event signatures (roadmap) are the fix.
- **Storage durability.** SQLite lives at `/home/<user>/flight_recorder.db`. That
  path survives web-app reloads and code deploys, but not a PythonAnywhere
  account reset, which clears the home directory.
- **Geo-restriction.** PythonAnywhere's free tier returns HTTP 451 to some client
  networks. Visitors who see 451 from the hosted API can still run the whole flow
  through the local Quick Start (`uvicorn src.main:app`).

### Redeploy after a push

On the PythonAnywhere bash console:

    cd flight-recorder && git pull

then **Web tab → Reload**. The Web-tab reload is what restarts the WSGI process.

## Tech Stack

| Component         | Technology                               |
| ----------------- | ---------------------------------------- |
| Off-chain API     | FastAPI + SQLite                         |
| On-chain contract | GenLayer SDK v0.19.0rc2 (consensus v0.6) |
| Testing           | pytest + genlayer-test (Direct Mode)     |
| CI                | GitHub Actions                           |

## License

[MIT](LICENSE) © 2026 hoveiser
