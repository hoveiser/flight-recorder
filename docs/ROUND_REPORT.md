# Round report: v5 (D5), signed events and an atomic chain-head anchor

Date: 2026-10-10. Branch `d5-signed-events-anchor`, PR #6, deployed as **D5** on studio-dev
(chain 61997). Every number and hash in this file was produced by running something; where a
check could not be run on this machine it is stated instead of glossed.

---

## 1. What was built

**Evidence layer (off-chain): every event is signed.**

A new event carries an EIP-191 `personal_sign` signature by its actor over a canonical message
that binds: the domain tag `flight-recorder-event-v1`, `deal_id`, the previous event hash, the
event type, SHA-256 of the canonical payload, and a client timestamp. The server recovers the
signer with `eth_account` and requires all three of: recovered address equals the claimed actor,
the actor is a party to the deal, the actor equals the authenticated session address.
`POST /deals/{id}/seal` follows the same actor == session rule. The timestamp window is bounded
in both directions by named constants (`EVENT_TIMESTAMP_MAX_PAST_SECONDS = 900`,
`EVENT_TIMESTAMP_MAX_FUTURE_SECONDS = 300`). The signature is stored and folded into the event
hash as version 2; rows written before the change keep version 1 and are still verified with the
original formula, never rewritten (additive idempotent migration). `GET /deals/{id}/verify`
reports `verification` and `signature_status` separately (`PASS` / `FAIL` / `UNSIGNED_LEGACY`),
and the case file exports `actor`, `signature`, `client_timestamp`, `sig_version`,
`signature_status` and `signed_fields` per event. Per-deal write serialization (thread lock plus
`BEGIN IMMEDIATE`) was kept.

**Judge layer (on-chain): the chain head is anchored atomically.**

`dispute(deal_id, case_file_url, case_file_hash, chain_head)` now requires the sealed head as a
fourth argument, validated as 64 lowercase hex. In the same transaction it either writes that
head as the `delivery` anchor or, if one exists, requires exact equality and reverts with
`ANCHOR_MISMATCH`. A revert stores nothing, so there is no half-applied dispute. Only a party may
dispute, the existing status gates and no-double-dispute rule are unchanged, and
`_ai_round`'s anchor gate now fails closed when no anchor exists instead of skipping the check.
Fund-moving verdicts still require exact consensus on the discrete labels; no new nondeterminism
was added.

**Callers.** Both Python demos, `scripts/e2e_demo.js`, `scripts/run_live_scenarios.js` and the
browser page sign every event with throwaway keys and pass the sealed head, so the visitor flow
anchors with no extra step. The published happy-path case file was regenerated from a real
recorder run (the hand-written v4 file declared no chain head at all and could not be anchored
under this change).

**Hardening from the security review.** The off-chain dispute write is now authenticated
(F16), every caller-supplied field is bounded (F17), bounds do not break stored history (F18),
the demo clients refuse non-http URLs (F19), and the live scripts no longer mistake a decided
transaction for a successful one (F20).

---

## 2. Files changed

Off-chain service: `src/main.py`, `src/models.py`, `src/db.py`, `src/hash_chain.py`.
Contract: `contracts/settlement.py`.
Tests: `tests/conftest.py`, `tests/test_flight_recorder.py`, `tests/test_signed_events.py` (new),
`tests/test_api_hardening.py` (new), `tests/direct/test_settlement.py`.
Callers: `demo/signed_client.py` (new), `demo/make_case_file.py` (new), `demo/scraper_dispute.py`,
`demo/code_quality_dispute.py`, `scripts/event_signing.js` (new), `scripts/wallet_key.js` (new),
`scripts/explorer_verify.js` (new), `scripts/adversarial_live.js` (new),
`scripts/settle_open_deals.js` (new), `scripts/e2e_demo.js`, `scripts/run_live_scenarios.js`,
`scripts/deploy_contract.js`, `index.html`, `demo/case_files/happy_path.json`.
CI and docs: `.github/workflows/ci.yml`, `README.md`, `JUDGING.md`, `AUDIT.md`,
`DEVELOPMENT_LOG.md`, `CONTRACT_ADDRESS.txt`, `scripts/e2e_results.md`, `docs/ROUND_REPORT.md`.

Commits on the branch: `7faf740` (phase 1), `41bc470` (phase 2), `7221de8` (phase 3),
`cded8aa` (CI GenVM pin), `77e55ca` (log), `644a6e0` (phases 5 and 6), `5dd34c8` (phase 7).

---

## 3. PR and CI

- PR: https://github.com/hoveiser/flight-recorder/pull/6 (base `main`)
- CI on `cded8aa`: **success**, `88 passed, 0 failed` in 27.59s (53 direct + 35 off-chain)
- CI on the final head `5dd34c8`: **success**, **105 passed, 0 failed** in 27.20s
- The first two runs of the branch failed on all 53 direct tests for an environment reason:
  `genlayer-test` resolves the GenVM release as "the latest GitHub release", and
  `genvm-manager` v0.6.0-rc9 (published Oct 8) no longer ships the runner hash the contract pins
  in its `Depends` header. `GENVM_VERSION=v0.6.0-rc6` is now pinned on the CI test step. No
  dependency version changed and the contract's own pin is untouched, so D5 runs on the same
  runner as D4.

---

## 4. Test counts, per suite and environment

| suite | file | count | environment | result |
| --- | --- | --- | --- | --- |
| recorder | `tests/test_flight_recorder.py` | 14 | Windows, Python 3.13.13 | passed |
| signed events | `tests/test_signed_events.py` | 18 | Windows, Python 3.13.13 | passed |
| API hardening | `tests/test_api_hardening.py` | 15 | Windows, Python 3.13.13 | passed |
| agreement canonicalization | `tests/test_agreement_hash_canonicalization.py` | 3 | Windows, Python 3.13.13 | passed |
| **off-chain total** | | **50** | Windows, Python 3.13.13 | `50 passed` in 4.65s |
| contract, direct mode | `tests/direct/test_settlement.py` | 55 | CI, Ubuntu, Python 3.12.15 | passed |
| **all** | | **105** | CI (authoritative) | `105 passed, 0 failed` in 27.20s |

Baseline at the start of the round was 46 (17 off-chain + 29 direct-mode). The 29 existing
direct tests were adapted to the new required `dispute` argument and kept their expectations;
26 direct tests and 33 off-chain tests are new this round.

Direct mode cannot run on this Windows machine: WSL `Ubuntu-24.04` is present but `pip` fails
with `Temporary failure in name resolution` for PyPI inside and outside the sandbox, so
genlayer-test cannot be installed there. CI on Ubuntu is the environment of record for those
55 tests, which is what the brief allows.

---

## 5. D5

- **D5: `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1`** on studio-dev (chain 61997), deployed
  2026-10-10 with `node scripts/deploy_contract.js`.
- D1 `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35`, D2 `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D`,
  D3 `0x223323CE1b755313212FaD13016543C0E4E63E12` and D4 `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750`
  were not touched. D4's address was copied out of `CONTRACT_ADDRESS.txt` before the deploy
  overwrote it.
- Explorer JSON API used for verification:
  `https://explorer-studio-dev.genlayer.com/api/transactions/{hash}` (the Blockscout-style
  `/api/v2/...` paths 404 on this explorer). Wrapped in `scripts/explorer_verify.js`; every hash
  below was read back through it before being written into this file or `scripts/e2e_results.md`.
- The deploy script's final `getContractSchema` call fails with a studio-dev backend error
  (`psycopg2.ProgrammingError: can't adapt type 'dict'`) after the address is written. The
  deployment itself is fine: the contract accepts writes and reads, as every run below shows.

---

## 6. Transactions and what each one proves

### Deployment and setup

| tx | what it proves |
| --- | --- |
| `0xee4f5955ecded5fd6d7ea493fb21dc79e2a6ba8aa5a853d6df457cb2ee10d500` | D5 deployed. Explorer: FINALIZED, `to_address` is the new contract, `from_address` is the project's throwaway `.env` account `0x3de43AA2f7162c80af98abe78222aE0Cdf83c506`. |
| `0x4c7e1809b70e62b8b97c7773bd7bc3a3b0f7eaee31fe9784f8ea5ab303b4b86f` | Test-GEN top-up (2 GEN) of that account after the deploy fee left it at 0.0999 GEN. Not evidence; recorded because the round spent money. |
| `0xde1177cd2b94212c0d3978727f6100203451453c5321e5e61955add1be695b57` | Second top-up (3 GEN) before the adversarial run. Same note. |

### e2e lifecycle on D5

| tx | what it proves |
| --- | --- |
| `0xc078d4fc539c2db0873e43a7bbd3a148b7f3dc8792678955d503da4df0ef8a26` | `open_deal` (deal 1) funded with 0.1 GEN escrow. |
| `0x6baed45dcf207b67007d581cddb1e5b8d7fd2127f5abd2ac339a16362034a355` | **The first atomic anchor on D5.** A dispute of a log whose events were signed and sealed at `986752236833a5adf67a95716e53783d1489684f4195b364d445bd0d69b19f6c` wrote that head as `milestones.delivery` in the same transaction. Read back from the chain: deal 1 carries it. |
| `0x1b0194f0ae6bd26b82fe766de6c105a2572de667bd263a1077655ed8f66db3ab` | **A second dispute with a different head was refused.** Deal 1 was already anchored at `986752...`; this dispute carried `3b36423aa4e54a8de73df29802092b9c3dbf7137c80ecf5264c5b48c7f3ed371` and ended `txExecutionResultName FINISHED_WITH_ERROR`, and the anchor stayed where it was. (The script of the moment misread this as a success; that blindness is finding F20 and is fixed.) |
| `0x9cdc703262f2670f4f5e3f39c5a23d859a02b16ebdf9aceab78a89694ad60423` | `open_deal` (deal 3), third e2e run. |
| `0xe121b0c449c10b1ea6a4b1ecfea261dc3b7cbf7bf5673357f1bb28af3d03298c` | dispute of deal 3, anchored its own sealed head. |
| `0x3006bd650eb2f33da743d135876aa8f990f4b8df7ebcdc731e6f5bae7733b5fd` | resolve of deal 3: AGREEMENT_MISMATCH, refund executed inside resolve. |
| `0xcf0c9da68bac5e068ade71b0c31b6df9dd02a2c6e0bfae7b530927e5cf1acfda` | **finalize after an evidence refund is refused** (`FINISHED_WITH_ERROR`): a settled deal cannot be paid twice. |
| `0x7c0e0d59bfb21086b0971c67e04889ce6d0909ad19b76ef916b1cd3a19f30951` | `open_deal`, the clean fourth e2e run (deal 4). |
| `0x20a2795c8012f38a88d9b0aeb4b668d0cf91ba8aa8eca26a49e5e05111ca9fcf` | dispute of deal 4, anchoring `0a0320cd936e154dd87ca0cffacdff4e65d63568dc06c4fc0c6ee7919f338c63`, the head returned by sealing two signed events. Read back: `milestones.delivery` equals exactly that. |
| `0xb36dac933c5665116f4802fd657ab4d438b8797448d841913dd490429f575e67` | resolve of deal 4: `status refunded`, `verdict AGREEMENT_MISMATCH`, `payout_status paid`, one refund of 0.1 GEN to the client. This run's case file is the static TypeScript `package.json`, which carries no `definition_of_done`, so the expected outcome is the refund path, not a happy verdict. |

### Adversarial run (`scripts/adversarial_live.js`, deal 6, 10 cases, 10 passed, 0 state problems)

Every row was asserted twice: the call did not execute (or executed, where success was the
point) and the deal did not move, field by field, against the state read immediately before the
attempt.

| case | tx | outcome |
| --- | --- | --- |
| open_deal (setup) | `0x0eab0b12a415dae0286cb5e0d9fac539310bb42395bfe452d6231fd3ff7f63d0` | executed, deal 6 funded at 0.1 GEN |
| dispute with a missing head | `0x70987cba135cad9af59713d42c6be81890f79aaf53f27a0e8c7f50290a86a192` | refused, deal unchanged |
| dispute by a non-party | `0xae0e1e5ab6d616b82febf6e654fea52345c81b7d9a9e194d5f39d6d8330343d8` | refused, deal unchanged |
| counterparty anchors first | `0x8ebccfab1a56935e2654ac7b74db6313373e33ebe5687e1576777830a3bdde46` | executed, `delivery = a...a` |
| dispute with a different head after that anchor | `0x258fb81851604fd57b28fae1e3ae486e3bfab5859b8d3eecc2724cd44e4a072c` | refused; status still `funded`, anchor unmoved, no case-file hash stored |
| attempt to overwrite the anchor | `0x052327a79c59999e6f94c8cfb36ae8b398d28ca6e4be0e58a0b0a8031073ef1c` | refused, anchor still `a...a` |
| finalize out of order | `0x46703902d492f3590a4eddc5b0c351eefb371f6fb753d1b3676f522be2e9bbb6` | refused, deal unchanged |
| resolve by a stranger | `0xe707c55468d98bc8323ce0082a628574b8584e106cb186b33f7d36d1cb892790` | refused, `fetch_failures` not burned |
| zero-value open_deal | `0xb354bd22fd4fe1987eb8954e736f15f3a6e46bf2cf8171d2a6a5c2f75325ea1b` | refused, and the contract holds no new deal id |
| honest dispute with the anchored head | `0x7c9f1f3c9102e1efbbaebde2597040291ba90288bca5cce45bf4e2d696c520b1` | executed; deal 6 `disputed`, anchor `a...a`, `case_file_hash = 0ae7f1ad7eca720eaefd9e651e9c60fe258648ac6a19cc58e4d2c896dff12908` |

### Settling the deals the runs left open (`scripts/settle_open_deals.js`)

| tx | what it proves |
| --- | --- |
| `0x93d3efd48881cde9186824318aee4c5f0fdee1a102f9ae6fa3b3a7c1f2e598b3` | dispute of deal 2, executed; the anchor came from the head that run had sealed |
| `0x5d7ac9b27ea4ab8211f02656b360ec100a97687b5c9cac3a841e5c3dba3313db` | resolve of deal 2, AGREEMENT_MISMATCH, refunded |
| `0x01b8686bafde54e4fdb9ad9deb1f5cef83dba5b3ba68e5d717cd1c2466c73619` | resolve of deal 5 (the first adversarial run's deal), AGREEMENT_MISMATCH, refunded |
| `0x940c0fb5103df00977bf3fb9395d6f1fa711f509c48b020ea090be2880019e26` | resolve of deal 6, AGREEMENT_MISMATCH, refunded |

After this, `get_payouts()` on D5 returns six refunds of 100000000000000000 wei, all to the
`.env` account, and no deal on D5 holds locked escrow.

### Evidence published

`demo/case_files/happy_path.json` is now generated from a real recorder run by
`demo/make_case_file.py` with two random keys that were discarded afterwards, so the published
bytes cannot be extended or re-signed by anybody, including that script. Its declared head is
`33d588cbd07c6949b41f87cce222c9dcce66bebb4cae5130e1523bab79643771`, its agreement hash is
`056b9e2e236328d4d5b269b5d35e5f94017ee4dcf238e056c943caf96857dae4`, and the bytes served by
GitHub hash to `0ae7f1ad7eca720eaefd9e651e9c60fe258648ac6a19cc58e4d2c896dff12908`. That digest
was confirmed equal by three independent implementations (Python `hashlib`, Node `crypto`, the
browser's Web Crypto through `EXPECTED_HASH`, plus .NET `SHA256` over the fetched response) and
by the committed blob itself. The writer pins LF line endings for exactly this reason: with
`core.autocrlf=true` a text-mode write puts CRLF on disk while the blob stays LF, which silently
produces two different digests for the same file.

---

## 7. Security review: what ran, what it found, what was fixed

Scans actually executed:

| scan | result |
| --- | --- |
| L2 lightweight review (`qodersec review --layer=l2`) | completed, **0 findings** |
| L3 deep review | **not run**: offered before each of the two pushes in this round, and skipped on both on purpose |
| Full cloud scan of the repository | not run (this round used the local reviews and the manual tooling below) |
| bandit (`-r src contracts demo tests scripts -ll`) | 3 medium (B310, `urlopen` in the demo clients) before the fix, **0 medium and 0 high after**. With all severities: 270 low, every one `B101 assert_used` inside tests, left as is |
| pip-audit (`-r requirements.txt --no-deps`) | **No known vulnerabilities found** |
| npm audit (prod and dev) | **found 0 vulnerabilities** across 221 installed packages |
| secret scan, working tree | `git grep` for key/token/secret/password patterns and for 40+ character hex strings: no secret values. Hits are documentation, contract and event addresses, signatures inside the published case file, and the devnet test key already committed in `gltest.config.yaml` |
| secret scan, git history | same patterns over all 107 revisions: 3 hits, all the same help string in `scripts/wallet_key.js`. `git log --all -- .env` is empty, so `.env` has never been committed |
| gitleaks | not installed on this machine; no binary download was attempted. The grep scans above are the substitute the brief allows |
| CORS | `allow_origins=["*"]`, `allow_credentials` at its default `False`, auth by bearer token rather than cookie: F22, accepted and documented |
| SQL | all queries in `src/db.py` are parameterized (`?`); the only string-built statements are the additive `ALTER TABLE` migrations, which build no user input |
| Input size limits | were missing (F17), now enforced; error messages were checked and expose no internals (no `detail=str(exception)` anywhere in `src/`, and no exception handler that leaks a traceback) |
| `.gitignore` | `.env`, `*.db`, `flight_recorder.db`, `node_modules/`, caches and venvs are ignored; `git ls-files` confirms no database and no `.env` tracked |

Findings, with status (full text, evidence and covering test in `AUDIT.md`):

| ID | severity | summary | status |
| --- | --- | --- | --- |
| F16 | high | `POST /deals/{id}/dispute` accepted a typed-in `party` with no session, so anyone could write a claim into anyone's evidence record | **fixed**, 4 regression tests |
| F17 | medium | no bound on any caller-supplied field (payload, metadata, definition_of_done, claim, signature, client_timestamp, deal_id, nonce) | **fixed**, 8 regression tests |
| F18 | medium | applying those bounds to the response models would have made pre-existing rows unreadable | **fixed** by separating input and response types, 1 regression test |
| F19 | low | demo clients would open a non-http `FLIGHT_RECORDER_URL` | **fixed**, 1 regression test |
| F20 | medium | `e2e_demo.js` hardcoded deal id 1 and read any FINALIZED transaction as success, which reported a wrong result twice on this round's live runs | **fixed** (deal lookup, revert detection, anchor assertion) |
| F21 | info | the repo commits the GenLayer devnet test key | documented, used deliberately as the adversary |
| F22 | info | CORS wildcard without credentials, bearer-token auth | accepted, documented |
| F23 | medium | the contract compares the anchored head with the head the case file declares; it does not recompute the chain | **open on purpose** (this is F5's remaining half) |
| F24 | low | an empty evidence log cannot be disputed on-chain, because `GENESIS` is not 64 lowercase hex | accepted, documented |

Coverage matrices were written for every contract method against every deal status and role,
and every endpoint against authenticated party, authenticated stranger and unauthenticated
(`AUDIT.md`). Building them found two untested gates on `anchor_milestone` (the party check and
the closed set of milestone names), and both now have direct tests:
`test_anchor_milestone_is_not_for_a_stranger`,
`test_anchor_milestone_refers_only_to_the_three_known_milestones`.

---

## 8. What was not done

- **L3 deep security review**: offered before both pushes, skipped both times by choice. It can
  still be run on the merged commit.
- **Full cloud scan of the repository**: not requested by this round's plan and not run.
- **gitleaks**: not available on this machine; the documented grep substitute covered the tree
  and all 107 revisions.
- **Direct-mode tests locally**: WSL could not install the dependencies (DNS failure for PyPI in
  this environment), so they ran on CI instead. The result is the same count and a real run, not
  an assumption.
- **`scripts/run_live_scenarios.js` against D5**: not executed live this round. Two reasons,
  recorded rather than hidden: its `happy` and `mismatch` scenarios need a case file whose
  `CASE_FILE_URL` the validators can fetch from the merged branch (the branch's own raw URL works
  for `adversarial_live.js`, which is the same evidence, and that ran), and each plain write
  costs about 0.1 GEN, so four more scenarios would have spent roughly the remaining test budget.
  The `anchor` scenario's behaviour (signed events, seal, anchor, dispute with the same head) is
  covered on-chain by the e2e and adversarial runs above.
- **Phase 9, headless browser test of `index.html`**: not done. It needs a wallet extension
  holding test GEN and a user to approve `personal_sign` prompts, which cannot be honestly
  automated here. It is in the manual checklist below instead.

---

## 9. Open limitations, stated plainly

1. **F5 / F23.** The contract reads the chain head the case file declares for itself. It does
   not recompute the chain from the events, so a case file that lies about its own head
   consistently with the anchored digest still passes. D5 narrowed this (immutable anchor, both
   parties bound to one head before any adjudication, log sealed so it cannot grow afterwards)
   but did not close it. Closing it means hashing each link inside `resolve`.
2. **Signatures prove who wrote an event, not that the event is true.** A party can sign a false
   claim about its own delivery; the chain and the signature make that claim attributable and
   immutable, which is what the evidence layer can actually promise.
3. **Legacy rows are unsigned.** Events written before this change are reported as
   `UNSIGNED_LEGACY`; they are neither upgraded nor silently trusted.
4. **No revocation for a leaked session token.** A session lasts 7 days and is proof of
   possession of the key. Until the seal, a leaked key means a writable log.
5. **`deploy_contract.js` cannot finish its own schema read** on studio-dev today because of the
   node-side `psycopg2` bug above; the deployment succeeds regardless. Worth re-checking next
   round before adding anything that depends on that call.
6. **The first adversarial run's harness bug** (a case marked failed by a stale snapshot rather
   than by the contract) is why its transactions are listed as supplementary rather than as the
   recorded evidence; the corrected harness's run is the one quoted in `scripts/e2e_results.md`.

---

## 10. Manual checklist

1. **PythonAnywhere**: `git pull` in the app checkout and reload the web app. Until this is done
   the hosted recorder still runs the pre-signing code, which means it will accept unsigned
   events and the browser page's signed events will fail against it. This is the single most
   important manual step of the round.
2. **Merge PR #6**: this round's last step is to merge it (after CI is green on the final
   commit). Check that the merge commit landed on `main` and that the GitHub Pages build
   republished the page.
3. **GitHub Pages**: confirm the deployed page shows D5 (`0xc93007…`) and that the hash checker
   reports MATCH against `0ae7f1ad...` once `main` serves the regenerated case file.
4. **Phase 9 (optional, not done here)**: in a real browser with MetaMask or Rabby on chain
   61997, funded from the studio-dev faucet, walk the TRY A DISPUTE steps: connect, open a deal,
   record a signed event, seal and dispute, then check the explorer links and deal 5's
   `milestones.delivery`. Save the log or screenshots under `docs/evidence`.
5. **If you want the L3 deep review**: run `/security-scan` and pick the deep option; it reviews
   the committed changes since the last review point.
6. **Next round's one real gap**: F5/F23, recomputing the chain inside the contract. Everything
   else this round did was in service of that step.
