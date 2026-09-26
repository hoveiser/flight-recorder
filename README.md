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

Expected: **46 passed** (17 off-chain + 29 direct-mode).

### 3. Run Demos

With the off-chain service from step 1 still running:

    python demo/scraper_dispute.py
    python demo/code_quality_dispute.py

Each script records a full deal lifecycle (events → seal → verify) against the local API.

## On-Chain Settlement (Studio Next)

The Settlement contract is deployed on GenLayer Studio Next (chain ID `61997`).

- Contract address: `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` (v4 / D4, deployed 2026-09-26)
- Explorer: https://explorer-studio-dev.genlayer.com/address/0xfD91f7eDCa653702ACe1F040F4d56d35e674c750
- Previous deployments: `0x223323CE1b755313212FaD13016543C0E4E63E12` (audited v3 / D3) and `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` (v2 / D2) — both still on-chain and verifiable; the transaction hashes documented in `scripts/e2e_results.md` and on the site belong to them.

Run the end-to-end flow from the repository root:

    npm install
    node scripts/e2e_demo.js

Run the direct Settlement tests:

    pytest tests/direct/test_settlement.py -v

### Deployment history

| Version           | Address                                      | What it is                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **v1**            | `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35` | Demo-video lifecycle: the first end-to-end run used in the recorded walkthrough.                                                                                                                                                                                                                                                                                                                                                                                  |
| **v2**            | `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` | Superseded by `0x223323CE…` on 2026-09-24; see Deployment history. Remains on-chain as historical evidence and carries the four live scenarios, including the APPROVED happy path. See `scripts/e2e_results.md` for the raw run output.                                                                                                                                                                                                                           |
| **v3-audit** (D3) | `0x223323CE1b755313212FaD13016543C0E4E63E12` | Superseded by **v4 / D4** on 2026-09-26; remains on-chain and verifiable. Repo-HEAD hardening: payout atomicity, agreement and anchor verification, deterministic time, exception-path retry counter, and a fail-closed timeout — plus audit patches **F4** (anchor is immutable once written) and **F6** (agreement digest accepted in both Python and browser canonical forms). Findings **F1, F2 and F3 were still open here**; they are fixed in v4. Validated with `scripts/e2e_demo.js`: open_deal → dispute → resolve = `AGREEMENT_MISMATCH` refund → payout. |
| **v4** (D4)       | `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` | **Current on-chain deployment** (2026-09-26). Everything in v3-audit plus the three findings that survived it — **F1** (escrow is exactly `gl.message.value`, never caller-declared), **F2** (an `unresolvable` deal is refunded by `timeout_release` once the appeal window closes) and **F3** (only a party can `resolve`) — plus validator payload depth (resolve sees the last ≤5 event payloads, not just counters) and appeal-with-new-evidence. Validated with `scripts/e2e_demo.js`: open_deal → dispute → resolve → finalize, all four FINALIZED. |

**Current status:** the v4 contract is live at `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` (D4). The v2 (`0x8BC5…`) and audited v3 (`0x223323CE…`) contracts are **not** deleted or forked — they stay on-chain, so every transaction hash referenced in this README, `JUDGING.md`, `scripts/e2e_results.md` and `index.html` still resolves to a real record. What changed is only _which_ address new writes go to. Test coverage is 46 (17 off-chain + 29 direct-mode); a full security and correctness audit of the contract is in [AUDIT.md](AUDIT.md). Audit findings **F1, F2 and F3 are now fixed in the deployed v4 contract** — see Threat model below and Task E in AUDIT.md.

## Versioning

On-chain deployments are numbered D1 (0x4bA3…), D2 (0x8BC5…, superseded), D3 (0x2233…, superseded), D4 (0xfD91…, live). Code generations are numbered v3 (the audited hardening deployed as D3), v4 (F1/F2/F3 fixes + validator payload depth + appeal evidence, now deployed as D4), v5 (product generation). A code generation is not a deployment until it appears in Deployment history.

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

¹ **Deployed since D3 (`0x223323CE…`, 2026-09-24) and carried into the current D4
(`0xfD91f7…`, 2026-09-26).** These two verdicts come from the hardening work and are covered by
the direct-mode test suite; they execute on-chain. The earlier D2 (`0x8BC5…`) deployment does not
have them, which is why the older on-chain evidence stays a continuous D2 record. Concretely: a
deal whose anchored case file carries terms other than the deal's own agreement is adjudicated on
the case file's terms by D2, but comes back AGREEMENT_MISMATCH and is refunded by D3/D4 — the D3
validation run exercised exactly that path (`scripts/e2e_results.md`). The D4 browser demo instead
anchors the repo `happy_path` case file with a matching agreement, so it clears this gate and is
adjudicated on the merits.

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
    │   ├── test_flight_recorder.py  # Off-chain tests (14 tests)
    │   ├── test_agreement_hash_canonicalization.py  # Cross-runtime hash tests (3 tests)
    │   └── direct/test_settlement.py # Direct-mode tests (29 tests)
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
- Live on-chain instance is D4 (`0xfD91f7…`): the audited v3 hardening plus audit patches F4 and F6, and now the F1, F2 and F3 fixes. D2 (`0x8BC5…`) and D3 (`0x223323CE…`) remain on-chain as historical evidence. The findings below are recorded with their current status.
- **Escrow amount is caller-declared, not value-derived (audit CRITICAL) — FIXED in D4.**
  Previously `open_deal` took an `amount` and only fell back to `gl.message.value` when it was
  zero, so a caller could record more escrow than it sent and later withdraw that larger figure
  from the contract's shared balance. The deployed v4 contract ignores any caller-declared amount
  and sets escrow to exactly `gl.message.value` (a zero-value open reverts with
  `open_deal requires payable value`). Fixed in D4 (`0xfD91f7…`); the D2/D3 contracts still on-chain
  carry the old behaviour. See AUDIT.md F1.
- **`unresolvable` dead state + unauthenticated `resolve` (audit HIGH) — FIXED in D4.**
  Previously, after three failed resolve attempts the escrow could no longer be moved by any method
  (`dispute`, `resolve`, `appeal`, `finalize` and `timeout_release` all gated on other statuses), so
  funds locked instead of settling; and `resolve` was unauthenticated, letting a third party spend a
  deal's retry allowance deliberately. In v4, `timeout_release` refunds an `unresolvable` deal once
  the appeal window closes, and `resolve` requires the sender to be the client or the worker.
  Fixed in D4 (`0xfD91f7…`). See AUDIT.md F2/F3.
- **`anchor_milestone` overwrites an existing anchor (audit HIGH) — FIXED since D3.** A re-posted
  milestone with a _different_ head is now rejected, so the anchored chain head a case file is
  checked against is immutable once written. Fixed in D3 (`0x223323CE…`) and carried into D4; the D2
  contract still on-chain overwrites. See AUDIT.md F4.
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
- **Appeal with new evidence — DONE (D4).** `appeal(deal_id, new_case_file_url="")` now accepts an
  optional new URL; when supplied it updates `case_file_url`, clears `case_file_hash` so the next
  `resolve` re-fetches and re-anchors, and returns the deal to `disputed`. The agreement/anchor/chain
  gates still apply, so "new evidence" cannot mean "new terms".
- **Redeploy v3 to Studio Next — DONE (D3, `0x223323CE…`, 2026-09-24; since superseded by D4).**
  The audited v3 hardening plus patches F4 and F6 was deployed and validated by a full
  `scripts/e2e_demo.js` lifecycle whose `resolve` returned `AGREEMENT_MISMATCH` and
  refunded the client (`scripts/e2e_results.md`).
- **Deploy F1, F2 and F3 as D4 — DONE (`0xfD91f7…`, 2026-09-26).** The three findings that survived
  D3 are now fixed on-chain: escrow is exactly `gl.message.value` (F1), an `unresolvable` deal is
  refunded by `timeout_release` once the appeal window closes (F2), and `resolve` requires a party
  (F3). Validated by a full `scripts/e2e_demo.js` lifecycle. See AUDIT.md Task E.
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

- **Multi-worker safe (single worker no longer required).** Nonces and sessions are persisted
  in SQLite (`nonces`, `sessions` tables in `src/db.py`) rather than in-process dictionaries, so a
  token survives a restart and is honoured by any worker sharing the same database file.
  Regression-tested by `test_session_survives_app_restart`.
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
