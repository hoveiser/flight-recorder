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
- **Signed event recording** into an append-only hash chain: every new event carries an
  EIP-191 signature by the actor that wrote it
- **Identity binding**: the server requires that the recovered signer is the claimed actor,
  that the actor is a party to the deal, and that the actor owns the session token
- **Hash verification** (tamper detection) and a separate **signature status** verdict
- **Dispute filing** by deal parties, authenticated like every other write
- **Case file export** (GenLayer-ready JSON) carrying each event's signature and the fields it
  covers, so an adjudicator can re-derive the signer without trusting this server

### On-Chain (Settlement Contract)

- **Escrow**: open_deal locks funds with agreement hash; the escrow is exactly the attached
  value, and a zero-value open is refused
- **Milestone anchoring**: anchor_milestone records a chain head on-chain, and only the first
  one for a milestone stands
- **Dispute filing**: dispute submits the case file hash AND the sealed chain head, and writes
  that head as the delivery anchor in the same transaction. If an anchor already exists the
  head must equal it, or the whole call reverts.
- **AI adjudication**: resolve uses GenLayer validators to reach a verdict; evidence verdicts
  (mismatch, tampering, anchor mismatch) are decided from the fetched bytes with exact
  consensus, and the anchor gate applies to every disputed deal
- **Appeal process**: appeal allows the loser to contest, optionally with a new case file URL
- **Finalization**: finalize pays the winner based on the verdict
- **Timeout release**: timeout_release auto-pays the worker if no dispute was filed, and
  refunds the client once an unresolvable deal's appeal window has closed

## Quick Start

### 1. Off-Chain Service

    pip install -r requirements.txt
    uvicorn src.main:app --reload

API docs: http://localhost:8000/docs

### 2. Run Tests

    pytest tests/ -v

Expected: **105 passed** (50 off-chain + 55 direct-mode). The 29 direct-mode tests that
existed before this round are still there, adapted to the new required `dispute` argument,
and 26 more cover signing, the anchor and its races. Direct mode needs Linux or macOS (gltest
cannot inject its fd-0 message on Windows), so on Windows the off-chain half runs locally and
CI on Ubuntu is the authoritative full run.

### 3. Run Demos

With the off-chain service from step 1 still running:

    python demo/scraper_dispute.py
    python demo/code_quality_dispute.py

Each script logs in with a throwaway key per party, records a full deal lifecycle (signed
events → seal → dispute → verify) against the local API, and prints the sealed chain head that
the dispute anchors. `FLIGHT_RECORDER_URL` points them at another recorder if needed.

## On-Chain Settlement (studio-dev)

The Settlement contract is deployed on GenLayer Studio Next, whose network is `studio-dev`
(chain ID `61997`, RPC `https://studio-dev.genlayer.com/api`). Throughout this repository the
environment is called studio-dev.

- Contract address: `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1` (v5 / D5, deployed 2026-10-10)
- Explorer: https://explorer-studio-dev.genlayer.com/address/0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1
- Previous deployments, all still on-chain and verifiable: `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` (v4 / D4), `0x223323CE1b755313212FaD13016543C0E4E63E12` (audited v3 / D3), `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` (v2 / D2) and `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35` (v1 / D1). The transaction hashes documented in `scripts/e2e_results.md` and on the site belong to the deployment they were run against, and each row says which.

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
| **v4** (D4)       | `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` | Superseded by **v5 / D5** on 2026-10-10; remains on-chain and verifiable. Everything in v3-audit plus the three findings that survived it: **F1** (escrow is exactly `gl.message.value`, never caller-declared), **F2** (an `unresolvable` deal is refunded by `timeout_release` once the appeal window closes) and **F3** (only a party can `resolve`), plus validator payload depth (resolve sees the last ≤5 event payloads, not just counters) and appeal-with-new-evidence. Validated with `scripts/e2e_demo.js`: open_deal → dispute → resolve → finalize, all four FINALIZED. |
| **v5** (D5)       | `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1` | **Current on-chain deployment** (2026-10-10). The atomic head anchor: `dispute(deal_id, case_file_url, case_file_hash, chain_head)` takes the sealed chain head as a required fourth argument (64 lowercase hex) and writes it as the `delivery` anchor in the same transaction, or reverts if a different head is already on record. The anchor can never be overwritten, `ANCHOR_MISMATCH` now gates every disputed deal instead of only pre-anchored ones, and a missing anchor fails closed. Fund-moving verdicts still require exact consensus on the discrete labels. Deployed with `node scripts/deploy_contract.js` (deploy tx `0xee4f5955ecded5fd6d7ea493fb21dc79e2a6ba8aa5a853d6df457cb2ee10d500`). Validated with `scripts/e2e_demo.js` on deal 4 and with ten adversarial cases in `scripts/adversarial_live.js` (10/10, every hash verified against the explorer JSON API); see `scripts/e2e_results.md`. |

**Current status:** the v5 contract is live at `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1` (D5). The earlier contracts are **not** deleted or forked. D1 to D4 stay on-chain, so every transaction hash referenced in this README, `JUDGING.md`, `scripts/e2e_results.md` and `index.html` still resolves to a real record. What changed is only _which_ address new writes go to. Test coverage is 105 (50 off-chain + 55 direct-mode); a full security and correctness audit of the contract is in [AUDIT.md](AUDIT.md). Findings **F1, F2 and F3 were fixed in v4 and are still fixed in D5**; this round adds **F16 to F24** from the API and caller audit, and the honest limitation about the case file's self-reported chain is documented as **F23** in [AUDIT.md](AUDIT.md).

## Versioning

On-chain deployments are numbered D1 (`0x4bA3…`), D2 (`0x8BC5…`, superseded), D3 (`0x2233…`, superseded), D4 (`0xfD91…`, superseded) and D5 (`0xc930…`, live). Code generations are numbered v3 (the audited hardening deployed as D3), v4 (F1/F2/F3 fixes, validator payload depth and appeal evidence, deployed as D4) and v5 (signed events off-chain plus the atomic head anchor on-chain, deployed as D5). A code generation is not a deployment until it appears in Deployment history, and a deployment is not "current" until its address is in the line above.

## API Reference

### Off-Chain Endpoints

"Session" means the `Authorization: Bearer <token>` header from the two `/api/auth` endpoints.
Every write that changes the evidence record requires one, and the identity it names must be
the session's own address.

| Method | Endpoint                   | Auth     | Description                                              |
| ------ | -------------------------- | -------- | -------------------------------------------------------- |
| POST   | /api/auth/nonce            | none     | Get a login nonce (expires after 5 minutes, single use)   |
| POST   | /api/auth/verify           | signature | Prove a key and get a session token (valid 7 days)       |
| POST   | /deals                     | none     | Create a deal; parties must be addresses, see limits below |
| GET    | /deals/{deal_id}           | none     | Get deal details                                         |
| POST   | /events                    | session  | Record a **signed** event into the hash chain             |
| GET    | /deals/{deal_id}/events    | none     | Get all events for a deal                                |
| GET    | /deals/{deal_id}/verify    | none     | Verify the chain, and report signature status separately  |
| POST   | /deals/{deal_id}/seal      | session  | Freeze the evidence log, return the chain head            |
| POST   | /deals/{deal_id}/dispute   | session  | File a dispute (the named party must be the session)      |
| GET    | /deals/{deal_id}/disputes  | none     | Get all disputes                                         |
| GET    | /deals/{deal_id}/case-file | none     | Export case file for adjudication (this is what validators fetch) |

`POST /deals/{deal_id}/seal` and `POST /deals/{deal_id}/dispute` apply the same rule as an
event write: the actor or party named in the body must equal the authenticated session address,
so a shared or stolen session token cannot freeze or accuse on someone else's record.

#### Event request fields

| Field             | Required | Notes |
| ----------------- | -------- | ----- |
| `deal_id`         | yes      | up to 100 characters, the same ceiling the contract enforces |
| `actor`           | yes      | an Ethereum address (`0x` + 40 hex); it must be a party and must be the session |
| `event_type`      | yes      | up to 64 characters, see Event Types |
| `payload`         | no       | dict, at most 32 KiB measured on the canonical encoding that is hashed |
| `metadata`        | no       | dict, at most 8 KiB |
| `signature`       | yes      | EIP-191 `personal_sign` over the canonical event message, below |
| `client_timestamp`| yes      | ISO-8601 with a UTC offset; must be within the window |

The timestamp window has both a floor and a ceiling, as named constants in `src/main.py`:
`EVENT_TIMESTAMP_MAX_PAST_SECONDS = 900` and `EVENT_TIMESTAMP_MAX_FUTURE_SECONDS = 300`. A
window with only one bound is not a window: without the floor a signed event from last month
could be replayed today, and without the ceiling a party could date its own evidence ahead of
everything else, forever.

### Event signing

Every event written from here on carries a signature. The signed message is plain text, joined
by newlines, and it binds the write to one position in one deal's chain:

    flight-recorder-event-v1      # domain tag, so a login signature can never be an event signature
    <deal_id>
    <previous_event_hash>         # GENESIS for the first event
    <event_type>
    <sha256 of the canonical payload>
    <client_timestamp>

The server recovers the signer with `eth_account` and requires three things at once: recovered
address equals the claimed actor, the actor is a party to the deal, and the actor is the
authenticated session. Because the deal id and the previous hash are inside the signed text,
replaying a signature into another deal or another position changes what is recovered and fails
the first check rather than succeeding quietly.

The signature is stored and folded into the event hash, which is why the hash formula has two
versions. `sig_version` 1 is the original six-field formula and 2 adds the signature and client
timestamp. Rows written before this change keep version 1, are verified with the formula they
were written under, and are never rewritten: an existing log's head hash does not move when the
migration adds its columns. `GET /deals/{id}/verify` reports the two things separately,
`verification` for the chain and `signature_status` as `PASS`, `FAIL` or `UNSIGNED_LEGACY`, and
the case file carries each event's `signature`, `client_timestamp`, `sig_version` and the exact
`signed_fields`, so anybody can re-derive the signer without trusting this server.

Clients that implement the same message: `demo/signed_client.py` (Python) and
`scripts/event_signing.js` (Node), plus the browser helpers in `index.html`. They produce
byte-identical digests: canonical JSON is sorted-key, separator-compacted and ASCII-escaped on
all three sides.

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

| Method           | Type          | Description                                                              |
| ---------------- | ------------- | ------------------------------------------------------------------------ |
| open_deal        | write.payable | Lock escrow with agreement hash; the escrow is exactly the attached value |
| anchor_milestone | write         | Record a chain head on-chain, first one for a milestone only              |
| dispute          | write         | File a dispute with the case-file hash **and the sealed chain head**, which becomes the immutable delivery anchor in the same transaction |
| resolve          | write         | AI validators adjudicate; only a party may call it                        |
| appeal           | write         | Loser contests, optionally pointing at a new case file URL                |
| finalize         | write         | Pay the winner of an adjudicated deal                                     |
| timeout_release  | write         | Auto-pay the worker after 7 days undisputed, or refund an unresolvable deal once its appeal window has closed |
| get_deal         | view          | Get deal state                                                            |
| get_payouts      | view          | Get payout history                                                        |

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

Note precisely what reaches the chain now. `dispute()` anchors **two** things in one
transaction: the case-file hash, and the sealed chain head passed as its fourth argument,
which becomes the deal's `delivery` milestone. That anchor is written once and never moved:
if a head is already on record the new one must equal it or the entire call reverts, so
neither party can pick the anchor after seeing the other's. `anchor_milestone()` remains for
staking a head before a dispute exists, under the same write-once rule.

The head being anchored is the head that `/seal` returned, and the API refuses any further
event for a sealed deal, so the anchored value cannot describe a log that grew later. One
consequence is worth stating: because a head must be 64 lowercase hex, an evidence log with
no events at all (whose head is the literal `GENESIS`) cannot be disputed on-chain.

Why it matters: the contract adjudicates against both the case-file hash and the anchored
head. If events could still be appended after anchoring, a party could pad the log with
favourable entries and leave the on-chain hash describing a record that no longer exists
off-chain. Sealing makes the anchored hash final, and the atomic anchor makes the head
mutual and immutable.

Sealing is idempotent — calling it twice returns the same head hash. It freezes
_writes_ only: `GET /deals/{deal_id}/verify` and `GET /deals/{deal_id}/case-file`
keep working and the chain still verifies `PASS`.

Both live-demo scripts (`scripts/run_live_scenarios.js`, `scripts/e2e_demo.js`) and the
browser flow call `/seal` immediately before sending the on-chain `dispute` transaction, so
sealing is never a step anyone has to remember.

## Case File Format

This is the real shape exported today, from the published
`demo/case_files/happy_path.json` (regenerate it with `python demo/make_case_file.py` against
a recorder, never by hand):

    {
      "deal_id": "demo_happy_002",
      "definition_of_done": {"success_criteria": "...", "acceptance": "..."},
      "parties": ["0x62F4e023b1d1e68a86E153829704610C007175Fb", "0x..."],
      "agreement_hash": "056b9e2e...",
      "events": [
        {
          "id": 1,
          "actor": "0x...",
          "event_type": "REQUEST",
          "payload": {"seq": 0, "request": "..."},
          "payload_hash": "sha256...",
          "previous_event_hash": "GENESIS",
          "event_hash": "sha256...",
          "timestamp": "2026-10-10T19:13:00.782712+00:00",
          "signature": "0x... (EIP-191 personal_sign by the actor)",
          "client_timestamp": "2026-10-10T19:12:54.582009+00:00",
          "sig_version": 2,
          "signature_status": "PASS",
          "signed_fields": {
            "domain": "flight-recorder-event-v1",
            "deal_id": "demo_happy_002",
            "previous_event_hash": "GENESIS",
            "event_type": "REQUEST",
            "payload_hash": "sha256...",
            "client_timestamp": "2026-10-10T19:12:54.582009+00:00"
          }
        }
      ],
      "disputes": [],
      "chain_integrity": {
        "verification": "PASS",
        "signature_status": "PASS",
        "signatures": {"events": 4, "signed": 4, "legacy": 0, "failed": 0},
        "hash_version": 2,
        "events": 4,
        "genesis_hash": "sha256...",
        "last_hash": "33d588cb..."
      }
    }

`chain_integrity.last_hash` is the head a dispute must anchor, and `verification` and
`signature_status` are deliberately two answers: a chain can be internally consistent and
still contain unsigned legacy rows, or carry valid signatures over an edited link.

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
    │   ├── test_signed_events.py    # Signature and replay tests (18 tests)
    │   ├── test_api_hardening.py    # API guard tests, findings F16-F19 (15 tests)
    │   ├── test_agreement_hash_canonicalization.py  # Cross-runtime hash tests (3 tests)
    │   └── direct/test_settlement.py # Direct-mode tests (55 tests)
    ├── demo/
    │   ├── signed_client.py         # Python client that logs in and signs every event
    │   ├── make_case_file.py        # Regenerates the published case file from a real run
    │   ├── scraper_dispute.py
    │   └── code_quality_dispute.py
    ├── scripts/
    │   ├── event_signing.js         # Node equivalent of signed_client.py
    │   ├── wallet_key.js            # Reads the throwaway key from .env, never prints it
    │   ├── explorer_verify.js       # Verifies a tx hash against the explorer JSON API
    │   ├── adversarial_live.js      # Ten adversarial cases against the live contract
    │   ├── settle_open_deals.js     # Settles deals a run left behind
    │   └── deploy_contract.js, e2e_demo.js, run_live_scenarios.js
    └── README.md

## Threat model & known limitations

- **Unsigned events: closed for new events, still true for old ones.** The hash chain proves
  integrity (no later edit), not provenance (who wrote it). Since D5 every new event carries an
  EIP-191 `personal_sign` signature by its actor over a message that binds the domain tag, the
  deal id, the previous event hash, the event type, the payload digest and a client timestamp,
  and the server requires that the recovered signer is the claimed actor, that the actor is a
  party, and that the actor owns the session token. Rows written before the change have no
  signature: `GET /deals/{id}/verify` reports them as `UNSIGNED_LEGACY` instead of pretending
  they are proven, and the case file says so per event. A party that controls the logging
  service still cannot fabricate an event in another party's name without their key.
- **Actor binding: closed.** Writes used to trust the `actor` / `party` / `X-Actor` string the
  caller typed. Every write that touches the evidence record (`POST /events`,
  `POST /deals/{id}/seal`, `POST /deals/{id}/dispute`) now requires a session and rejects a body
  that names anybody else, so a shared or stolen token cannot log onto someone else's record or
  freeze or accuse on their behalf.
- **Omission:** the chain cannot prove an event was NOT skipped. The seal plus the head anchored
  by the dispute pin the log at one point in time and make it immutable afterwards; periodic
  auto-anchoring while a deal is still live is on the roadmap.
- **Self-reported chain, still open (F5 and F23):** the contract compares the anchored head with
  the head the case file declares for itself. It does not recompute the chain from the events.
  D5 makes that head immutable and forces both parties to agree to one before any adjudication,
  and the recorder seals the log so it cannot grow afterwards, but a case file that lies about
  its own head consistently with the anchored digest still passes this gate. Closing it means the
  contract hashing each link itself, which is the next round's work. See AUDIT.md F5 and F23.
- **Timestamps:** the client timestamp is now bounded in both directions (900s of past drift, 300s
  into the future) and is inside the signed message, so it cannot be re-dated after the fact.
  Server receipt time is still the ordering the chain records; the on-chain anchor is what makes
  the head authoritative.
- **Concurrency:** `POST /events` is serialized per deal (threading lock + `BEGIN IMMEDIATE`), so
  concurrent writes cannot fork the chain; regression-tested by
  `test_concurrent_writes_cannot_fork_chain`.
- **Input limits:** every caller-supplied field is bounded before it is hashed, recovered or
  stored, and `deal_id` shares the contract's own 100-character ceiling so the API never accepts
  evidence the contract will refuse. Bounds apply to input; stored rows keep their old shape, so
  history written before a limit is still readable.
- **CORS** is `allow_origins=["*"]` with no credential support, and the API authenticates by
  bearer token rather than cookie: a browser on another origin can read public evidence (which is
  the point, validators must fetch it too) but cannot act as a party without that party's key.
- **Prompt injection:** validators receive evidence inside data tags with instructions to ignore
  embedded commands; adversarial case files are regression-tested by
  `test_prompt_injection_does_not_change_verdict`.
- Live on-chain instance is **D5** (`0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1`): the atomic head
  anchor in `dispute`. D4 (`0xfD91f7…`) carries the audited v3 hardening plus F4 and F6 and the F1,
  F2 and F3 fixes; D2 (`0x8BC5…`) and D3 (`0x223323CE…`) remain on-chain as historical evidence.
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
- **Actor attribution: DONE (D5).** `POST /events`, `/seal` and `/dispute` require a session
  token from a wallet-signed login, and every event body now carries an EIP-191 signature by its
  actor over the deal id, the previous hash, the event type, the payload digest and a bounded
  client timestamp. A session alone is no longer enough: the identity named in the body has to
  be the session, and the signature has to recover to it.
- **Signed events as the write path: DONE (D5).** New writes are refused without a signature
  (`HTTP 400`), and pre-existing unsigned rows are reported as `UNSIGNED_LEGACY` rather than
  silently trusted or rewritten.
- **Recompute the chain inside the contract (F5, F23).** The last step that turns the evidence
  layer from self-attested into independently verified: `resolve` would hash each link of the
  exported log itself instead of reading `chain_integrity` out of the file it is judging.
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
- **Deploy the head anchor as D5: DONE (`0xc93007ac…`, 2026-10-10).** `dispute` requires the
  sealed chain head and writes it as the immutable `delivery` anchor in the same transaction;
  `ANCHOR_MISMATCH` gates every disputed deal and fails closed when no anchor exists. Validated
  by a full `scripts/e2e_demo.js` lifecycle and ten adversarial live cases. See AUDIT.md and
  `scripts/e2e_results.md`.
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
**3.10 – 3.14**. Dependencies stay pinned to what works across that range: no major
dependency upgrades and no Python version change as part of a feature round. The GenVM
runner the contract names is pinned in CI through `GENVM_VERSION` (see
`.github/workflows/ci.yml`), because an unpinned "latest" release breaks the direct suite
for a reason that has nothing to do with the contract.

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
