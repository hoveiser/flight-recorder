# Flight Recorder - Development Log

### Oct 12 - v6 work started (D6 branch): the contract recomputes the hash chain

Branch `d6-chain-recompute`. D5 (`0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1`,
studio-dev chain 61997) stays live and untouched, along with D1 to D4.

This round closes F5 and F23: the settlement contract no longer trusts the case
file's self-attested `chain_integrity.verification` flag or its self-declared
head. It recomputes the chain itself and refuses to adjudicate unless its own
computation agrees with the head anchored on-chain at dispute time.

#### Canonical serialization and hash formula (the single source of truth)

Everything below is defined once in `src/hash_chain.py` and mirrored byte for
byte inside the contract. `tests/golden/chain_vectors.json` pins it: the
contract's output must equal the vectors exactly, and the vectors are produced
by the real Python implementation, not hand-written.

Canonical JSON (`canonical_json`): `json.dumps(obj, sort_keys=True,
separators=(",", ":"))` with the default `ensure_ascii=True`. That means keys
are sorted recursively, there is no whitespace after `,` or `:`, and every
non-ASCII character is escaped as a `\uXXXX` sequence. This is the exact byte
string that is hashed. It is deliberately the escaped form: the off-chain
recorder computed every stored `payload_hash` with it. The transport is
different and must not be confused with the digest input. The case file is
served by Starlette with `ensure_ascii=False` (literal UTF-8), but the contract
parses that body back into a Python dict and re-canonicalizes it with
`ensure_ascii=True`, so it reproduces the recorder's digest for unicode
payloads. The golden vectors carry unicode, escaped quotes, backslashes and new
lines precisely to prove that round trip.

Payload hash (`compute_payload_hash`): `SHA-256(canonical_json(payload))`,
lowercase hex, 64 characters. The contract never trusts a case file's declared
`payload_hash`; it re-derives it from the payload object.

Event hash (`compute_event_hash`). Let `|` be the single ASCII vertical bar,
used as a separator over the raw field strings (the fields are concatenated, not
canonicalized). The base input is always:

```
deal_id | actor | event_type | payload_hash | previous_event_hash | timestamp
event_hash = SHA-256(that string), lowercase hex
```

Version 1 (legacy, unsigned): the base six fields, exactly as above, and
nothing else. The row must have `signature = null` (or the key absent) and
`client_timestamp = null` (or absent).

Version 2 (signed): the base six fields plus the signature and the client
timestamp, appended with two more separators:

```
deal_id | actor | event_type | payload_hash | previous_event_hash | timestamp | signature | client_timestamp
```

where `client_timestamp` contributes the empty string when it is absent
(`client_timestamp or ""`). The signature bytes therefore live inside the chain:
swap them and the event hash stops matching the anchored head, even though the
contract cannot itself recover the signer (there is no ecrecover inside the
GenVM contract runtime; see the limitation note below).

Version selection on the contract side is taken from `sig_version` (1 or 2), a
structural field, never from `chain_integrity`. A `sig_version` that is not
exactly the integer 1 or 2, or that disagrees with the presence of `signature`
(a version 1 row carrying a signature, or a version 2 row without one), is a
CHAIN_MISMATCH. Because the recomputed event hash is also compared against each
declared `event_hash` and the recomputed head against the anchored head, lying
about `sig_version` cannot forge a match: it only produces a hash that agrees
with nothing.

Chain linkage (`recompute_head`). Start at `previous = "GENESIS"`. For each event
in array order: require `event.previous_event_hash == previous`; re-derive
`payload_hash` from the payload; compute the event hash with the version's
formula; require it to equal the declared `event_hash`; then set
`previous = event_hash`. The head is the last event hash. An empty event list has
no head (the literal `GENESIS` is not a 64-hex digest), so it cannot match an
anchor and is a CHAIN_MISMATCH.

The signed message an actor signs per event (EIP-191 `personal_sign`, domain tag
`flight-recorder-event-v1`) is a newline-join of: domain, deal_id,
previous_event_hash, event_type, payload_hash, client_timestamp. That is the
signature the contract embeds into the version 2 hash; it is not itself verified
on-chain.

#### Deterministic bounds (floor and ceiling, both sides)

Named constants shared by the off-chain recompute and mirrored in the contract,
so a party cannot hand the validators unbounded work and so every window has both
ends:
- Case file body: at least `MIN_CASE_FILE_BYTES` (20, already an UNREACHABLE floor)
  and at most `MAX_CASE_FILE_BYTES` (1 MiB; over the ceiling is CHAIN_MISMATCH).
- Event count: at least 1 and at most `MAX_CHAIN_EVENTS` (256).
- Per string field ceilings: deal_id 100 (matches `open_deal`), event_type 64,
  actor 128, signature 200, client_timestamp 64, timestamp 64. Each must be a
  non-empty string of the right type or it is a CHAIN_MISMATCH.
- Per payload: canonicalized UTF-8 at most `MAX_EVENT_PAYLOAD_BYTES` (32768),
  matching the recorder's write-time bound.

#### On-chain signature verification is not possible this round (limitation)

The GenVM contract runtime exposes no secp256k1 or ecrecover. The off-chain SDK
has `Account.recover_message`, but it is not importable from inside a contract,
which sees only a restricted standard library (the contract already relies on
`json`, `hashlib`, `datetime`). So the contract embeds each version 2 signature
into the chain hash (tampering with it breaks the head) but cannot recover the
signer address itself. Event signatures remain verifiable off-chain from the
exported case file, and the API enforces them at write time (recovered signer
equals the claimed actor, the actor is a deal party, and the actor is the
authenticated session). This is stated plainly in the README threat model and in
AUDIT.md rather than papered over.

#### D6 shipped (deployment, evidence, hardening)

- Contract change landed in `contracts/settlement.py`: `resolve` calls a pure
  `_recompute_head` (mirroring `src/hash_chain.recompute_head`) and pays only
  when its own digest equals the anchored delivery head. `TAMPERED` is removed
  from `EVIDENCE_VERDICTS`; the new discrete `CHAIN_MISMATCH` shares
  `ANCHOR_MISMATCH`'s refund outcome and needs exact validator consensus. The
  validator prompt no longer carries `chain_integrity` or the declared head, and
  an over-`MAX_CASE_FILE_BYTES` body is refused before parsing.
- Golden vectors landed: `tests/golden/chain_vectors.json` (23 vectors, 11 MATCH
  and 12 CHAIN_MISMATCH) generated by `tests/golden/generate_chain_vectors.py`,
  asserted off-chain in `tests/test_chain_vectors.py` and driven through the
  contract source in `tests/direct/test_chain_recompute.py`.
- `tests/test_case_files.py` guards that every published case file under
  `demo/case_files/` recomputes to its declared head, so a data edit cannot
  quietly desynchronize the anchor; `.gitattributes` pins LF endings.
- Deployed D6 `0x51A54D74e86159482F2E57b8d4744c7Ba44D7043` on studio-dev chain
  61997 (deploy tx `0x2edb7e3e78f45b50866fc0a1b41326a7091a4033889fc9c126616687a59edb9a`,
  verified FINALIZED through the explorer JSON API). D5 and earlier stay on-chain.
- Live proof (`scripts/adversarial_live.js`, 12/12 pass, explorer-verified): a
  real `CHAIN_MISMATCH` refund, the honest path still paying, and the prior
  refusals. A fully honest live `APPROVED` that reaches the LLM round could not
  complete because studio-dev fails to estimate the fee for such a `resolve`;
  that limitation is recorded in `scripts/e2e_results.md`, not hidden.
- Security round: `npm audit` and `npm audit --omit=dev` ran clean (0
  vulnerabilities); a manual git-history secret scan found nothing (only the
  documented public devnet test key). `bandit` and `pip-audit` could not be
  re-run this round because PyPI is unreachable from this environment (DNS
  resolution for `files.pythonhosted.org` fails); `gitleaks` was not installable.
  The Qoder cloud L2/L3 tiers did not run on this plan. All of this is stated
  honestly in the AUDIT.md "D6 rescan" table.
- Hardening: `POST /api/auth/logout` deletes the bearer token
  (`src/db.delete_session`), so a leaked or shared session is cut short instead
  of living out its seven-day expiry; covered by `tests/test_session_logout.py`.
- Test totals this session: direct 80 passed, off-chain 93 passed / 12 skipped
  (173 total). CI on PR #7 was green before the logout tests; the final CI run
  is the authoritative full count.

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
- **Phase 4, CI.** Branch pushed and PR #6 opened. The first two runs were red on all
  53 direct tests with `FileNotFoundError: runner py-genlayer:5jycge... not under
  trees-v2/v0.6.0-rc9`: `genlayer-test` resolves the GenVM release as "the latest
  GitHub release" unless `GENVM_VERSION` is set, and `genvm-manager` v0.6.0-rc9
  (published Oct 8) no longer ships the runner hash that `contracts/settlement.py`
  pins in its `Depends` header. The suite had passed on Sep 26 because the latest
  release then was v0.6.0-rc6. The fix pins `GENVM_VERSION=v0.6.0-rc6` on the CI test
  step; the contract header pin is untouched, so D5 runs on the same runner as D4 and
  no dependency version changed. Read from the package source that `resolve_version()`
  returns the env value before it queries the network and that the pytest plugin leaves
  `sdk_version` unset, so nothing overrides it.
  Green on `cded8aa`: **88 passed, 0 failed** in 27.59s (53 direct-mode, 35 off-chain).
  Final head of the branch, `5dd34c8`: **105 passed, 0 failed** in 27.20s
  (55 direct-mode, 50 off-chain: 14 recorder, 18 signing, 15 hardening, 3 canonicalization).
- **Phase 5, D5 and live proof.** Deployed **D5**: `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1`
  on chain 61997 (deploy tx
  `0xee4f5955ecded5fd6d7ea493fb21dc79e2a6ba8aa5a853d6df457cb2ee10d500`, verified through the
  explorer JSON API: FINALIZED, `to_address` is the new contract). D1 to D4 untouched; D4's
  address was copied out of `CONTRACT_ADDRESS.txt` before the deploy overwrote it. The final
  step of the deploy script, `getContractSchema`, fails with a studio-dev backend error
  (`psycopg2.ProgrammingError: can't adapt type 'dict'`) after the address is written; reads and
  writes on the contract work, so this is a node-side bug and is recorded rather than worked
  around. `scripts/e2e_demo.js` ran the full lifecycle on D5 with signed events and a sealed
  head, and `scripts/adversarial_live.js` ran ten adversarial cases (10/10 passed) with every
  hash read back from the explorer.
- Two facts learned by measuring rather than assuming, both now encoded in the scripts:
  - A GenLayer transaction that the contract refuses still ends `statusName FINALIZED` with
    `result_name MAJORITY_AGREE`. Only `txExecutionResultName` separates `FINISHED_WITH_RETURN`
    from `FINISHED_WITH_ERROR`, and the transaction record carries no revert string, so the
    exact rejection messages are asserted in direct mode while the live run asserts refusal
    plus "the deal did not move".
  - A write's fee is not one number: `estimateTransactionFees()` returns about 0.1 GEN while
    `estimateTransactionFeesForWrite()` priced `resolve` on D5 at 761268000010352 wei. The
    recorded `fee-profile.json` allocation names a recipient from another contract, and the
    node rejects an allocation that does not match a message the transaction actually produces
    (`MessageNoMatchingAllocation`), so `e2e_demo.js` now asks the node to price `resolve` and
    keeps the profile only as a fallback.
- **Phase 6, security review.** Scans that ran and what they said are in AUDIT.md: L2
  lightweight review (0 findings), bandit (3 medium B310 to 0 medium after F19), pip-audit
  (no known vulnerabilities), `npm audit` (0 vulnerabilities), and a grep-based secret scan of
  the tree and of all 107 revisions (no secret values; `.env` was never committed). Findings
  F16 to F24 are recorded there, and each gap the coverage matrices exposed got a regression
  test: `tests/test_api_hardening.py` (15 tests) for the API, two new direct tests for the
  `anchor_milestone` party gate and the closed set of milestone names. Suite is now 50
  off-chain and 55 direct-mode collected.
- The most consequential of those is **F16**: `POST /deals/{id}/dispute` used to accept a
  typed-in `party` with no session at all, so anyone could write a claim into anyone's evidence
  record. It now carries the same binding as an event write. Fixing it raised a second issue,
  **F18**: putting input bounds on the response models would have made every row written before
  the bounds unreadable, which would turn hardening into data loss, so input types and response
  types are now separate and a test proves pre-D5 history still exports.
- **Phase 7, docs.** README, JUDGING.md and `index.html` were taken through a
  claims-versus-reality pass against D5: deployment history and versioning list D5 and mark
  D4 superseded, the API reference gained the auth column, the event fields, the byte limits,
  the timestamp bounds and an event-signing section, the case file sample is the shape the
  recorder actually exports today, and the site's verdict table now lists all four evidence
  verdicts. Three specific corrections rather than additions:
  - The README said `dispute()` anchors the case-file hash *not* the chain head, and that the
    browser flow never anchors. Since D5 the dispute anchors both, and the browser flow does
    anchor; the paragraph now says so and states the consequence (an empty log cannot be
    disputed).
  - The site's hash-checker caption credited the digest to "deal 4 of the previous v2
    deployment (dispute tx 0x571095fb…)". That transaction anchored the *old hand-written* case
    file, whose bytes are no longer what `main` serves, so the caption now describes what the
    check actually does and `EXPECTED_HASH` was regenerated with the file.
  - "Studio Next" and "studio-dev" were used interchangeably. The product name stays GenLayer
    Studio Next; the network is studio-dev (chain 61997), and that is now stated once and used
    consistently. The stale "do not upgrade before the hackathon deadline" instruction is gone,
    replaced by the actual rule (no major dependency or Python changes in a feature round) plus
    the `GENVM_VERSION` pin and why it exists.
  - `flight_recorder.db` was already in `.gitignore` and `git ls-files` shows no database
    tracked, so no untracking was needed; verified rather than assumed.

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
