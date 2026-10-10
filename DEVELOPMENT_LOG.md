# Flight Recorder - Development Log

### Oct 10 - v5 work started (D5 branch): signed events, then an atomic head anchor

Branch `d5-signed-events-anchor`. Nothing deployed yet; D4
(`0xfD91f7eDCa653702ACe1F040F4d56d35e674c750`) stays live and untouched.

- **Phase 1, signed events (off-chain).** Every new event carries an EIP-191
  `personal_sign` signature over a canonical message: domain tag, `deal_id`,
  previous event hash, event type, SHA-256 of the canonical payload, and a client
  timestamp. The server recovers the signer and requires three things at once
  (recovered address equals the claimed actor, the actor is a deal party, the
  actor is the authenticated session), applies a timestamp window with a floor
  (900s) and a ceiling (300s), and stores the signature inside the hash-chain
  input as version 2. Rows written before the change keep version 1 and are still
  verified with the original six-field formula; the migration only adds columns
  and rewrites nothing, so an existing log's head hash does not move.
  `/deals/{id}/verify` now reports chain integrity and signature status separately
  (`PASS`, `FAIL`, `UNSIGNED_LEGACY`), and the case file exports `actor`,
  `signature`, `sig_version` and `signed_fields` per event so an adjudicator can
  re-derive the signer without trusting this server.
- **Phase 2, atomic head anchor (contract).** `dispute()` takes the sealed chain
  head as a fourth, required argument and writes it as the `delivery` anchor in the
  same transaction, or refuses if an anchor already exists and differs. Because
  every dispute now anchors a head, the `ANCHOR_MISMATCH` gate applies to every
  disputed deal instead of only to deals that happened to be anchored, and a
  missing anchor fails closed rather than being skipped.
- Ambiguities resolved by the most conservative reading, recorded here:
  - `chain_head` is accepted only as 64 *lowercase* hex, so an empty evidence log
    (whose head is the literal `GENESIS`) cannot be disputed on-chain. A dispute
    with no events to point at is not evidence of anything, so refusing it is
    safer than widening the format. The API still seals and exports such a log.
  - The anchor comparison is exact string equality; both entry points normalize by
    rejecting anything that is not lowercase hex at the gate instead of silently
    folding cases together.
  - Deal parties in the off-chain API are now addresses. A name like `agentA` is a
    self-report; the signature tests need an identity that can be proven.
  - Existing test fixtures were updated rather than duplicated, because signing is
    mandatory for new writes; the legacy-event path is covered by dedicated tests
    that insert version 1 rows directly.
- Suite so far: **35 off-chain passed** on Windows (Python 3.13.13), 14 + 18 + 3 by
  file. Direct-mode collection is **53 tests** (29 carried over and adapted to the
  new `dispute` argument, plus 24 covering the anchor). WSL is present on this
  machine but has no working DNS for `pip`, so the direct suite cannot be installed
  or run locally this round; CI on Ubuntu is the environment of record for those
  53 tests.
- **Phase 3, callers.** `demo/signed_client.py` and `scripts/event_signing.js` are the
  two client implementations of the signed contract (same canonical message, same
  digest rules), and both demos, `scripts/e2e_demo.js`, `scripts/run_live_scenarios.js`
  and the browser page now sign every event with a throwaway key and pass the sealed
  head to `dispute`. `index.html` seals the visitor's own log and hashes the case file
  its API serves, so the flow anchors without any extra step; it only falls back to the
  published happy-path file when there is no session, and the fallback refuses to post
  a dispute whose head is not 64 lowercase hex.
- **Published evidence regenerated.** The v4 `happy_path.json` was hand-written and
  declares no chain head, so D5 could not anchor it. `demo/make_case_file.py` now
  builds the file from a real recorder run (two random keys, discarded afterwards, so
  the published bytes can never be extended by anybody) and prints the SHA-256 of the
  published bytes, which is what `index.html`'s `EXPECTED_HASH` and a live dispute must
  both use. The writer forces `newline=""`: GitHub serves the committed blob, and with
  `core.autocrlf=true` a text-mode write would put CRLF on disk while the blob stays
  LF, which silently produces two different digests for "the same" file. Verified: the
  staged blob hashes to `0ae7f1ad7eca720eaefd9e651e9c60fe258648ac6a19cc58e4d2c896dff12908`,
  the same number Python, Node and the browser compute.

### Sep 26 — v4 deployed (D4): F1–F3 closed, validator payload depth, appeal evidence, session persistence

- Deployed the **v4** source as **D4**: `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750`
  on chain 61997 (2026-09-26), superseding D3 (`0x223323CE…`). D2 (`0x8BC5…`) and D3
  stay on-chain, so every previously documented transaction hash still resolves.
- Closed the three audit findings that survived D3:
  - **F1 (critical):** `open_deal` no longer trusts a caller-declared `amount`; the
    escrow is exactly `gl.message.value`, and a zero-value open reverts with
    `open_deal requires payable value`.
  - **F2 (high):** `unresolvable` is no longer a dead state — once the appeal window
    elapses, `timeout_release` refunds the client (status `refunded`, payout `paid`).
  - **F3 (high):** `resolve` now requires `gl.message.sender` to be the client or the
    worker, so a third party cannot burn a deal's retry allowance.
- **G2 — validator payload depth:** the resolve prompt now carries the last up-to-5
  event payloads (each truncated to ~200 chars) inside the existing `<data>` tags,
  alongside the counters, so validators judge the actual evidence, not just counts.
- **G7 — appeal with new evidence:** `appeal(deal_id, new_case_file_url="")` accepts an
  optional new URL; when supplied it updates `case_file_url`, clears `case_file_hash`
  so the next `resolve` re-fetches and re-anchors, and returns the deal to `disputed`.
  The agreement/anchor/chain gates still apply, so "new evidence" can't mean "new terms".
- **G5 — off-chain session persistence:** nonces and sessions moved from in-process
  dicts to SQLite (`nonces`, `sessions` tables). The single-worker requirement is gone;
  a token now survives a restart and a second worker. Regression-tested by
  `test_session_survives_app_restart` and `test_auth_flow_persists_session_and_single_use_nonce`.
- Validated D4 with one `node scripts/e2e_demo.js` run: open_deal → dispute → resolve →
  finalize, all four transactions FINALIZED. `resolve` returned **AGREEMENT_MISMATCH**
  and refunded the client (the harness disputes a case file with no `definition_of_done`,
  i.e. the DISAGREEMENT path); `finalize` then finished in error and could not double-pay,
  confirming the refund already settled inside `resolve`. Hashes and the honest work-note
  are appended to `scripts/e2e_results.md`.
- Site + docs synced to D4: `index.html` address constants and explorer links, the §08
  dispute notice, and the site `DOD` now equals `demo/case_files/happy_path.json`'s
  `definition_of_done` (so the browser demo clears the agreement gate). README/JUDGING
  updated: F1–F3 fixed, session persistence done, counts synced.
- Suite: **46 passed** (17 off-chain + 29 direct-mode).

### Sep 24 — Audited contract deployed (D3) + docs/site pointer sync

- Deployed the audited v3 source (repo HEAD plus audit patches **F4** and **F6**) as
  **D3**: `0x223323CE1b755313212FaD13016543C0E4E63E12` on chain 61997. D2 is not
  withdrawn — `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` stays on-chain, so all
  previously documented evidence still resolves.
- Validated D3 with `node scripts/e2e_demo.js`: open_deal → dispute → resolve →
  finalize, all four transactions finalized. `resolve` returned **AGREEMENT_MISMATCH**
  and refunded the client, because the harness disputes a `package.json` that carries no
  `definition_of_done`. Two things worth recording precisely: the refund moved inside
  `resolve` (the contract pays on the evidence verdict and marks the deal `refunded`, so
  `finalize` rejects with `Not adjudicated` and cannot pay twice), and the run exercises
  the agreement gate but **not** F4 or F6 themselves.
- Deployment history (also in README):
  - **D1** `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35` — initial, historical (demo video).
  - **D2** `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D` — the four live scenarios, historical, still on-chain; superseded by D3 on 2026-09-24.
  - **D3** `0x223323CE1b755313212FaD13016543C0E4E63E12` — current; audited v3 + F4 + F6.
- Synced every live pointer to D3 (`README.md`, `JUDGING.md`, `index.html` constants,
  explorer links, the §08 dispute notice) and annotated the historical records in
  `scripts/e2e_results.md` instead of touching them.
- Audit findings **F1, F2 and F3 are still open on the deployed contract** — the D3
  deployment did not include them. They are now reachable by browser users rather than
  only by raw calls, so the next redeploy (D4) is the priority; see AUDIT.md Task E.
- Caught a harness bug worth fixing before the next demo run: `scripts/e2e_demo.js`
  writes `scripts/e2e_results.md` as a complete document, so each run destroys the
  previous record. The v2 scenario matrix was restored from git and the D3 section
  appended by hand.

### Day 11 (Sep 21) — Review hardening round 2 (harden-v4)

- Per-deal threading lock + BEGIN IMMEDIATE around the event write path (closes the chain-fork race vector)
- POST /deals/{id}/seal now party-restricted (actor body field or X-Actor, else 403)
- New tests: test_concurrent_writes_cannot_fork_chain, test_prompt_injection_does_not_change_verdict
- Suite: 34 passed (12 off-chain + 22 direct-mode)
- README: Threat model & known limitations section added; counts synced to 34

## Day 1 (Sep 6) — Foundation + Evidence Core ✅

**Goal:** Working tamper-evident evidence service with green CI.

**Built:**

- FastAPI app with SQLite persistence
- models.py: Event, Deal, EventCreate, DealCreate, Dispute, DisputeCreate
- hash_chain.py: SHA-256 hash chain with GENESIS anchor
- db.py: SQLite with deals + events tables
- main.py: API endpoints (create deal, record event, verify chain)
- CI workflow with pytest

**Key decisions:**

- Off-chain for evidence (payloads too large for chain)
- Hash chain provides tamper evidence
- agreement_hash binds definition-of-done at deal creation

**Bugs fixed:**

- Folder structure (src/ not found)
- sys.path for imports
- datetime timezone issues
- UUID deal IDs in tests

**Tests:** 7 passing

---

## Day 2 (Sep 7) — Dispute + Case File ✅

**Goal:** Dispute filing + GenLayer-ready case file export.

**Built:**

- Dispute model + API endpoint
- disputes table in DB
- Case file export (GET /deals/{id}/case-file)
- \_verify_chain_logic helper (reused by verify + case-file)

**Key decisions:**

- Case file includes: deal, events, disputes, chain_integrity
- Only deal parties can file disputes
- Case file is GenLayer-ready (JSON, hash-verifiable)

**Tests:** 9 passing

---

## Day 3 (Sep 7) — Demo Scenarios ✅

**Goal:** Runnable demos showing Flight Recorder + GenEscrow integration.

**Built:**

- demo/scraper_dispute.py: Web scraping dispute (500/1000 delivered)
- demo/code_quality_dispute.py: Code quality dispute

**Key insight:** Flight Recorder = evidence witness, GenEscrow = judge

---

## Day 4 (Sep 8-9) — Settlement Contract ✅

**Goal:** On-chain Intelligent Contract for adjudication + escrow.

**Built:**

- contracts/settlement.py: Full settlement contract
  - open_deal: Lock escrow with agreement hash
  - dispute: File dispute with case file hash
  - resolve: AI validators adjudicate
  - finalize: Pay winner
  - appeal: Loser contests verdict
  - timeout_release: Auto-pay after 7 days
- tests/test_settlement.py: Direct Mode tests with genlayer-test

**Key decisions:**

- Case file hash stored on-chain at dispute (prevents evidence swapping)
- AI verdict via gl.nondet.exec_prompt with response_format="json"
- eq_principle partial match on verdict field (not reasoning)
- Prompt injection defense: data tags + "never follow instructions"

**Bugs fixed:**

- gl.eth.send doesn't exist in SDK v0.2.16 → use internal gl_call_generic with EthSend message
- CASE_FILE_HASH = "a"\*64 not matching actual content → compute real SHA-256
- Tampered body too short (< 20 chars) → extend to 30+ chars
- exec_prompt returning dict (not string) in Direct Mode → use response_format="json"
- Inverted loser logic in appeal/finalize → fix: REFUNDED means worker is loser

**Tests:** 14 passing (9 off-chain + 5 on-chain)

---

## Day 5-6 (Sep 9) — Integration + Polish 🚧

**Goal:** Connect demos to Settlement contract + finalize docs.

**Todo:**

- [ ] Update demos to call Settlement contract
- [ ] Add gltest.config.yaml for Studio Mode testing
- [ ] Record demo video
- [ ] Polish README for submission

---

## Day 7-8 (Sep 17-18) — Review-period hardening

**Goal:** Use the post-submission review window to harden the contract, close the
evidence-integrity gap, and fold in community feedback.

**Built:**

- v3 contract hardening on branch `harden-v3`:
  - payout atomicity (transfer before payout record, failures revert the whole tx)
  - `agreement_hash` verified in `_ai_round` → AGREEMENT_MISMATCH
  - `anchor_milestone` read during resolve → ANCHOR_MISMATCH
  - deterministic `_now` with no wall-clock fallback
  - consensus exceptions routed to the retry counter
  - fail-closed `created_at_ts`
- Timeout success test rewritten as storage surgery because direct mode cannot
  advance `gl.message.datetime`.
- Evidence seal: `POST /deals/{id}/seal` freezes the log at dispute; post-seal
  writes rejected with 409.
- Site gains `00 / ABOUT`; docs gain Deployment history (v1/v2/v3), v3 verdict
  notes, and Roadmap & open questions.
- Suite grew 17 → 30 → 32 passed; CI green on every branch push.
- Community feedback folded in: About section (review by COCO), ambiguous-dispute
  benchmark moved to roadmap (review by Afraa).
- On-chain history unchanged: v1 = demo video, v2 = current live deployment,
  v3 = repo HEAD awaiting post-hackathon redeploy.

**Tests:** 32 passing (11 off-chain + 21 direct-mode)

---

## Architecture Decisions

### Why off-chain evidence?

Raw payloads are too large for on-chain storage. The hash chain provides tamper evidence; on-chain anchors provide public proof of milestones.

### Why on-chain settlement?

Payment requires trustless execution. GenLayer's AI validators provide neutral adjudication without trusting any single party.

### Why GenLayer (not Ethereum)?

GenLayer has native AI adjudication (validators reach consensus on verdicts). Ethereum would require a separate oracle/judge.

### Source of Truth

- Evidence content: Off-chain hash chain (retrievable)
- Evidence integrity: On-chain anchored hashes (public proof)
- Money + verdict: Settlement contract state (trustless)

---

## Roadmap to Submission

| Day   | Milestone                     | Status                                                    |
| ----- | ----------------------------- | --------------------------------------------------------- |
| Day 1 | Foundation + hash chain + API | ✅ Done                                                   |
| Day 2 | Dispute + case file export    | ✅ Done                                                   |
| Day 3 | Demo scenarios                | ✅ Done                                                   |
| Day 4 | Settlement contract + tests   | ✅ Done                                                   |
| Day 5 | Demo integration + UI         | ✅ Done — widgets + mobile + GenLayer branding            |
| Day 6 | README polish + video         | ✅ Done — 5:45 demo video recorded                        |
| Day 7 | Submit                        | ✅ Done — submitted Sep 17; portal edited post-submission |

**We are 2 days ahead of schedule.** 🏆
