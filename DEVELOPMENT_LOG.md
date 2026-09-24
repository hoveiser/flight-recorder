# Flight Recorder — Development Log

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
- _verify_chain_logic helper (reused by verify + case-file)

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
- CASE_FILE_HASH = "a"*64 not matching actual content → compute real SHA-256
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

| Day | Milestone | Status |
|-----|-----------|--------|
| Day 1 | Foundation + hash chain + API | ✅ Done |
| Day 2 | Dispute + case file export | ✅ Done |
| Day 3 | Demo scenarios | ✅ Done |
| Day 4 | Settlement contract + tests | ✅ Done |
| Day 5 | Demo integration + UI | ✅ Done — widgets + mobile + GenLayer branding |
| Day 6 | README polish + video | ✅ Done — 5:45 demo video recorded |
| Day 7 | Submit | ✅ Done — submitted Sep 17; portal edited post-submission |

**We are 2 days ahead of schedule.** 🏆