# Round report: v6 (D6), the settlement contract recomputes the hash chain

Date: 2026-10-12. Branch `d6-chain-recompute`, PR #7 (merged to `main` as `be0154b`), tagged
`v6-d6`, deployed as **D6** on studio-dev (chain 61997). The prior round report (v5 / D5) is
preserved at [ROUND_REPORT_round5.md](ROUND_REPORT_round5.md). Every number and hash in this file
was produced by a command run this round; where a check could not be run on this machine it is
stated plainly instead of glossed.

---

## 0. What this round set out to close

Finding **F5** (medium) and its narrowed restatement **F23**: the settlement contract used to
trust two things the case file says about itself. `resolve` gated on `chain_integrity.verification`,
a PASS/FAIL flag read straight out of the fetched JSON, and it compared the anchored delivery head
only against `chain_integrity.last_hash`, the head the same untrusted file declared for itself. The
case file is the artifact a disputing party chooses to point at, so any party could write
`"verification": "PASS"` into a fabricated log. That gate bound to nothing.

D6 removes the reliance: the contract now recomputes the event hash chain itself, from genesis, and
pays only when its own digest equals the delivery head anchored on-chain at dispute time. No
self-reported field influences a verdict any more.

---

## 1. What was built

### The canonical formula (single source of truth)

Defined once in `src/hash_chain.py` and mirrored byte for byte inside the contract. `tests/golden/
chain_vectors.json` pins it: the vectors are produced by the real Python implementation, and the
contract's output must equal them exactly.

- Canonical JSON: `json.dumps(obj, sort_keys=True, separators=(",", ":"))`, default
  `ensure_ascii=True`. Keys sorted recursively, no whitespace, every non-ASCII char escaped as
  `\uXXXX`. This is the exact byte string that is hashed. The HTTP transport is different and is
  not confused with the digest input: Starlette serves the body with `ensure_ascii=False`, but the
  contract parses it back to a dict and re-canonicalizes with `ensure_ascii=True`, reproducing the
  recorder's digest for unicode payloads. The vectors carry unicode, escaped quotes, backslashes and
  newlines to prove that round trip.
- Payload hash: `SHA-256(canonical_json(payload))`, 64 lowercase hex. The contract re-derives it; it
  never trusts a declared `payload_hash`.
- Event hash base string (fields concatenated with `|`, not canonicalized):
  `deal_id | actor | event_type | payload_hash | previous_event_hash | timestamp`.
  - Version 1 (legacy, unsigned): the base six fields only; `signature` and `client_timestamp` must
    be null/absent.
  - Version 2 (signed): the base six plus `| signature | client_timestamp`, where `client_timestamp`
    contributes the empty string when absent. The signature bytes live inside the chain: swap them
    and the event hash stops matching the anchored head.
- Chain linkage (`recompute_head`): start at `previous = "GENESIS"`; for each event in array order
  require `previous_event_hash == previous`, re-derive `payload_hash`, compute the event hash for its
  version, require it equals the declared `event_hash`, then advance. The head is the last event
  hash. An empty list has no 64-hex head, so it can never match an anchor.
- Version selection is taken from the structural `sig_version` (must be exactly integer 1 or 2 and
  agree with the presence of `signature`), never from `chain_integrity`. Lying about `sig_version`
  only produces a hash that agrees with nothing.

### The contract change (`contracts/settlement.py`)

- `resolve` (in `_ai_round`) fetches the served body, then:
  1. Floor: empty or under 20 bytes is `UNREACHABLE` (a retry, not a verdict).
  2. Ceiling: over `MAX_CASE_FILE_BYTES` (1 MiB) is `CHAIN_MISMATCH`, checked before hashing so an
     oversized body is never re-hashed or re-parsed.
  3. `MISMATCH` if the fetched digest is not the `case_file_hash` anchored at dispute.
  4. `AGREEMENT_MISMATCH` if the case file's `definition_of_done` does not re-hash to the
     `agreement_hash` the client pre-committed (both Python and browser canonical forms accepted, the
     F6 fix, unchanged).
  5. `ANCHOR_MISMATCH` if no delivery head was ever anchored (fails closed).
  6. `CHAIN_MISMATCH` if `_recompute_head` returns None, or its head is not the anchored delivery
     head.
  7. Only then does the LLM adjudicate the merits.
- `chain_integrity`, its `verification` flag and its declared `last_hash` are no longer read and no
  longer appear in the validator prompt; the prompt carries a `chain_verification` tag that states
  the contract's own result.
- `EVIDENCE_VERDICTS` dropped `TAMPERED` and added the discrete `CHAIN_MISMATCH`. Like every
  evidence label it requires exact validator consensus, and it shares `ANCHOR_MISMATCH`'s fund
  outcome: full escrow refunded to the client, payout written before the status so a failed transfer
  reverts the whole transaction.

### Bounds (floor and ceiling on every window)

Named constants shared by the off-chain recompute and mirrored in the contract: case file body 20 to
1 MiB; event count 1 to `MAX_CHAIN_EVENTS` (256); per-field ceilings `deal_id` 100 (matches
`open_deal`), `event_type` 64, `actor` 128, `signature` 200, `client_timestamp` 64, `timestamp` 64;
per-payload canonical UTF-8 at most 32768 bytes. Every string field must be a non-empty string of
the right type or it is a `CHAIN_MISMATCH`.

### Hardening shipped alongside (`src/main.py`, `src/db.py`)

`POST /api/auth/logout` deletes the caller's bearer token via `db.delete_session`, so a leaked or
shared session is cut short instead of living out its seven-day expiry. It is idempotent and returns
the same body for a missing, unknown or presented token, so it cannot be used to probe whether a
session exists, and it only ever deletes the token it is shown.

---

## 2. Golden vectors and tests

`tests/golden/chain_vectors.json` holds 23 vectors generated by `tests/golden/
generate_chain_vectors.py`:

- 11 MATCH: legacy single/chain, signed single/chain, mixed v1-then-v2, empty-payload v2, unicode and
  escaped quotes, numbers, nested objects, long v1 payload, and an honest chain carrying a lying FAIL
  flag (the flag must not change the outcome).
- 12 CHAIN_MISMATCH: edited payload with a lying PASS flag, reordered events, dropped middle event,
  duplicated event, truncated tail, extra event appended after the anchor, tampered signature field,
  wrong field type (integer actor), unknown hash version, empty events, payload over the byte
  ceiling, and event count over the limit.

They are asserted off-chain in `tests/test_chain_vectors.py` and driven through the actual deployed
contract source in direct mode in `tests/direct/test_chain_recompute.py` (23 vectors plus the
oversize-before-parsing guard and the missing-anchor fail-closed guard = 25 collected).
`tests/test_case_files.py` guards that every published case file under `demo/case_files/` recomputes
to its own declared head, so a data edit cannot quietly desynchronize the anchor. `.gitattributes`
pins LF endings so the byte-exact hash stays byte-exact across checkouts.

Test totals run this session:

    direct  (GENVM_VERSION=v0.6.0-rc6):   80 passed      (test_settlement 55 + test_chain_recompute 25)
    off-chain:                             93 passed, 12 skipped
    total:                                173 passed, 12 skipped

The 12 skips are off-chain vector checks that only apply to a self-consistent chain; the adversarial
vectors intentionally have no head to match and are asserted as mismatches instead.

CI on PR #7 head `3fbf57c`: 173 passed, 12 skipped, green. CI on `main` after merge (`be0154b`):
green. GitHub Pages: build and deployment succeeded.

---

## 3. Deployment and live evidence (studio-dev chain 61997)

- D6 contract: `0x51A54D74e86159482F2E57b8d4744c7Ba44D7043`
- Deploy tx: `0x2edb7e3e78f45b50866fc0a1b41326a7091a4033889fc9c126616687a59edb9a`
- Contract source at the deployed commit and at `main` is identical: sha256
  `bc2f9b5c039e524d474fc228d8dde25d5e29611f26e2e3457f0a9579687947e1`
- Published case file `demo/case_files/happy_path.json`: body digest
  `0ae7f1ad7eca720eaefd9e651e9c60fe258648ac6a19cc58e4d2c896dff12908`, honest chain head
  `33d588cbd07c6949b41f87cce222c9dcce66bebb4cae5130e1523bab79643771`. The contract recomputes this
  file to exactly that head, so an honest dispute against it clears the new gate.
- D5 (`0xc93007ac…`), D4 (`0xfD91f7…`), D3 (`0x223323CE…`) and D2 (`0x8BC5…`) stay on-chain and
  untouched. Every transaction hash referenced anywhere in the repo still resolves on its own
  deployment.

Live runs (all transaction hashes read back through the explorer JSON API before being recorded;
details appended to `scripts/e2e_results.md`):

- `scripts/adversarial_live.js`: 12 cases, 12 pass, no unexpected on-chain state, exit 0. This
  includes the two new D6 cases. The headline one, `chain_mismatch_refunds`, opens a fresh deal,
  serves the real public happy-path file, then disputes against a different anchor (`HEAD_B`); the
  contract recomputes the served chain to `33d588…`, sees it does not equal the anchored head, and
  refunds the client under `CHAIN_MISMATCH`. Verified FINALIZED on the explorer.
- `scripts/e2e_demo.js`: exit 0 against D6. It landed on an `AGREEMENT_MISMATCH` refund, not an
  APPROVED payment, because its case-file URL points at a static TypeScript artifact that carries no
  `definition_of_done`, so the agreement gate refuses it. That is the correct deterministic outcome;
  the path is documented rather than presented as a success.

Limitation reported honestly, not hidden: a fully honest live `APPROVED` that reaches the LLM round
could not be completed on studio-dev this session. `open_deal` and `dispute` finalized
(`0x82a6cc…` and `0x313d69…`), but `resolve` failed at `sim_estimateTransactionFees`: the studio-dev
simulator cannot estimate the fee for a `resolve` that calls the model. The recompute and the
`CHAIN_MISMATCH` refund (which decide before any LLM call) are proven live; the merits-based
`APPROVED` remains proven only in direct mode, which exercises the leader path and does not by itself
prove validator agreement.

---

## 4. Security round (Phase 6)

Requested tooling, and what actually ran this round:

| scan | command / attempt | result |
| --- | --- | --- |
| npm audit | `npm audit` and `npm audit --omit=dev` | ran clean, found 0 vulnerabilities |
| bandit | `pip install bandit` | could not run: DNS resolution for `files.pythonhosted.org` fails, PyPI unreachable from this environment |
| pip-audit | same network path | could not run for the same reason; `requirements.txt` is byte-for-byte unchanged since the earlier run that reported no known vulnerabilities |
| gitleaks | binary not installed and no network to fetch it | manual equivalent run: `.env` is untracked; every unique blob across all revisions scanned for `ghp_`, `github_pat_`, `AKIA`, `xox[baprs]-`, PEM private-key blocks and AWS secrets with no hits; the only embedded key is the documented public devnet test key in `gltest.config.yaml` (F21); `GENLAYER_PRIVATE_KEY` and `ACCOUNT_PRIVATE_KEY_1` appear only as `process.env` reads, never as literals |
| Qoder cloud L2 / L3 tiers | not run | these tiers did not run on this plan |

The AUDIT.md "D6 rescan (this round)" table records exactly this. No new `urlopen`, subprocess, exec
or eval surface was added this round (verified against the diff): the new code is a pure hash
recompute plus one `DELETE FROM sessions`.

Contract adversarial review of the D6 resolve gate (the always-on rule before declaring done):
- State machine: only the verdict set changed; no new status or transition. Matrix 1 in AUDIT.md
  reflects it.
- Liveness: `CHAIN_MISMATCH` moves funds out immediately (full refund to client); it introduces no
  stuck state. The `unresolvable` recovery via `timeout_release` is unchanged.
- Races: no new competing transition; the recompute is a deterministic pure function, so the leader
  and every validator reach the same label and there is no ordering hazard.
- Accounting: the refund pays exactly the locked `amount`, payout before status write, double-refund
  blocked by the disputed-only gate.
- Input validation: floor and ceiling on body size, event count and every string field; `sig_version`
  must be the exact integer 1 or 2 and agree with signature presence.
- Consensus safety: `CHAIN_MISMATCH` is a discrete label needing exact consensus, derived from the
  bytes and not from a self-report; missing anchor fails closed; prompt injection surface narrowed by
  removing `chain_integrity` from the prompt.

GenVM linter: `genvm-lint check` AST lint passed (3 checks). The SDK-semantic validate step could not
load the pinned `py-genlayer` runner tarball offline; contract correctness is covered instead by the
80 passing direct-mode tests, the green CI, and a D6 deployment that reached FINALIZED.

Residual, stated plainly and documented in AUDIT.md, README and JUDGING.md: the GenVM contract runtime
exposes no ecrecover. A version 2 signature is embedded inside the hash (tampering with it breaks the
head), but the contract cannot recover the signer on-chain, so per-event signature verification stays
off-chain and at the API write gate. A party that fabricates an entirely self-consistent chain and
disputes against its own fabricated head is not caught by recomputation alone. The independent
guarantees are the on-chain delivery anchor both parties are bound to (immutable, mutual since D5)
and the write-time signature checks the recorder enforces. Signatures prove who wrote an event, not
that the event is true about the work.

---

## 5. Files changed this round

- `contracts/settlement.py`: recompute gate, `CHAIN_MISMATCH`, bounds, prompt, removed `TAMPERED`.
- `src/hash_chain.py`: bounds constants, `ChainError`, `recompute_head()`.
- `src/db.py`, `src/main.py`, `tests/test_session_logout.py`: session logout / token revocation.
- `tests/golden/generate_chain_vectors.py`, `tests/golden/chain_vectors.json`,
  `tests/test_chain_vectors.py`, `tests/direct/test_chain_recompute.py`, `tests/test_case_files.py`.
- `tests/direct/test_settlement.py`: fixtures rebuilt on real chains; the self-attestation tests
  repurposed to assert the contract ignores the flags and the declared head.
- `.gitattributes`: LF pinning.
- `scripts/adversarial_live.js`: D6 header/URL, `openFreshDeal` helper, two live recompute cases.
- `scripts/run_live_scenarios.js`: comment update.
- `scripts/e2e_results.md`: D6 adversarial and honest-partial results appended.
- `CONTRACT_ADDRESS.txt`: D6.
- Docs: `README.md`, `JUDGING.md`, `index.html`, `AUDIT.md`, `DEVELOPMENT_LOG.md`.

---

## 6. What is done, and what is still open

Closed this round:
- F5 and F23: the contract recomputes the chain; self-reported integrity no longer gates a verdict.
- Session token revocation now exists (the "no revocation for a leaked token" gap is closed for the
  practical case; the deeper per-event key or epoch model stays future work).

Still open, on purpose and documented:
- On-chain per-event signature verification: blocked by the absence of ecrecover in the contract
  runtime. Fallback is the mutual immutable anchor plus write-time checks.
- The self-consistent fabricated chain anchored to its own fabricated head is not caught by
  recompute alone.
- A fully honest live `APPROVED` through the LLM round: blocked this session by the studio-dev fee
  estimator; proven in direct mode (leader path) only. Validator agreement for that path is the item
  to re-confirm against a studio-dev that can estimate the resolve fee.
- Ambiguous-dispute benchmark (partial delivery, conflicting validation, missing evidence) and
  periodic auto-anchoring while a deal is live remain on the roadmap.
