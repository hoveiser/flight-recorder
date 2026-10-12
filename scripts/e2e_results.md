# Live E2E Results

Contract: `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D`
Network: GenLayer Studio Next (chain 61997)
Explorer: <https://explorer-studio-dev.genlayer.com/address/0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D>

> Every run in the first part of this file is historical: it executed on the v2
> deployment above, superseded by `0x223323CE…` on 2026-09-24. The v2 contract is still
> on-chain, so each hash below still resolves. The current deployment's own run is in
> the last section.

Run with:

```
node scripts/run_live_scenarios.js            # every scenario
node scripts/run_live_scenarios.js --happy    # happy path only
node scripts/run_live_scenarios.js --anchor   # off-chain anchor only
node scripts/run_live_scenarios.js --timeout  # 7-day lock check only
node scripts/run_live_scenarios.js --mismatch # evidence-mismatch refund only
SCENARIOS=mismatch node scripts/run_live_scenarios.js   # same, via env flag
```

## Scenario Matrix

| Scenario                     | Deal | Status / verdict                           | Payout          | Notes                                                             |
| ---------------------------- | ---: | ------------------------------------------ | --------------- | ----------------------------------------------------------------- |
| 1 / Happy path               |    4 | `released` / `APPROVED`                    | Worker: 0.1 GEN | Full lifecycle: dispute → AI resolve → finalize                   |
| 1 / Happy path (earlier run) |    1 | `released` / `APPROVED`                    | Worker: 0.1 GEN | Same case file, same verdict                                      |
| 2 / Off-chain anchor         |    2 | `funded`; `delivery` milestone anchored    | None            | Chain head written on-chain and readable back                     |
| 3 / Timeout release          |    3 | `funded`; early release correctly rejected | None            | `Timeout not reached (7 days)` — escrow lock enforced             |
| 4 / Evidence mismatch        |    5 | `refunded` / `EVIDENCE_MISMATCH`           | Client: 0.1 GEN | Wrong case-file hash anchored on-chain; refunded inside `resolve` |

### Why the happy path now resolves to APPROVED

`gl.nondet.web.render(url, mode="text")` does **not** return the file bytes. It returns
a normalized text rendering, so its SHA-256 can never match the hash of the original
file that was committed in `dispute`. The contract now hashes the raw response body
returned by `gl.nondet.web.get(url)`.

Measured on-chain for `demo/case_files/happy_path.json`:

| Source                                    | Bytes | SHA-256                                                            | Matches dispute hash |
| ----------------------------------------- | ----: | ------------------------------------------------------------------ | -------------------- |
| `gl.nondet.web.get(url).body` (raw bytes) |  1363 | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7` | Yes                  |
| `gl.nondet.web.render(url, mode="text")`  |  1095 | `ae4972090e56fcbf6df9f1938cdbd03b87e8f2f13c0293d0e597a856631b10dc` | No                   |

The rendering step strips 268 bytes of JSON indentation, which is exactly why every
earlier attempt ended in `EVIDENCE_MISMATCH`. Hashing raw bytes makes the on-chain
check reproduce the same digest a user computes locally with `sha256sum`.

## Transactions

| Scenario | Method             | Status              | TX hash                                                              | Explorer                                                                                                               |
| -------- | ------------------ | ------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1        | `open_deal`        | FINALIZED           | `0x833a8910198c84928b23c5cb756ffe906e920a0d3f139b87c5a9447006a07260` | [View](https://explorer-studio-dev.genlayer.com/tx/0x833a8910198c84928b23c5cb756ffe906e920a0d3f139b87c5a9447006a07260) |
| 1        | `dispute`          | FINALIZED           | `0x571095fb0b6eeeace5e1b7a7ad12d1c7a6f9cd997ef1fa3bb217e6a65167758c` | [View](https://explorer-studio-dev.genlayer.com/tx/0x571095fb0b6eeeace5e1b7a7ad12d1c7a6f9cd997ef1fa3bb217e6a65167758c) |
| 1        | `resolve`          | FINALIZED           | `0xd581386fc82c0fe07e760e5bb2ef0fa922b30892d36c4a5384855abaedba4de8` | [View](https://explorer-studio-dev.genlayer.com/tx/0xd581386fc82c0fe07e760e5bb2ef0fa922b30892d36c4a5384855abaedba4de8) |
| 1        | `finalize`         | FINALIZED           | `0x847ed870335849c9d3c04225239e18aa669ea4065b48a42dbfaf8d049e2b61c9` | [View](https://explorer-studio-dev.genlayer.com/tx/0x847ed870335849c9d3c04225239e18aa669ea4065b48a42dbfaf8d049e2b61c9) |
| 2        | `open_deal`        | FINALIZED           | `0x576d72ba2d0d29a66470999ce1058d5654570b192457e3d97dcc2e07dee21cac` | [View](https://explorer-studio-dev.genlayer.com/tx/0x576d72ba2d0d29a66470999ce1058d5654570b192457e3d97dcc2e07dee21cac) |
| 2        | `anchor_milestone` | FINALIZED           | `0x6d87f4edb69d24e05367163de8a9dc83d7f3dc15fa630d281d63b6e6a7cc1cd5` | [View](https://explorer-studio-dev.genlayer.com/tx/0x6d87f4edb69d24e05367163de8a9dc83d7f3dc15fa630d281d63b6e6a7cc1cd5) |
| 3        | `open_deal`        | FINALIZED           | `0x38128f22cab6d8260f32b97a2332ecabbe4722c033014f7023ec38560b52cf37` | [View](https://explorer-studio-dev.genlayer.com/tx/0x38128f22cab6d8260f32b97a2332ecabbe4722c033014f7023ec38560b52cf37) |
| 3        | `timeout_release`  | FINALIZED; rejected | `0x19ca7d54d49cc5c75435e5d9fd9f4e1d9f9d60521a082a0e36a966efdb70e13d` | [View](https://explorer-studio-dev.genlayer.com/tx/0x19ca7d54d49cc5c75435e5d9fd9f4e1d9f9d60521a082a0e36a966efdb70e13d) |
| 4        | `open_deal`        | FINALIZED           | `0x417dbcfa30c854b8b97851aa5f21c40f553cf396d3eab7cd2289cd926e2c06b0` | [View](https://explorer-studio-dev.genlayer.com/tx/0x417dbcfa30c854b8b97851aa5f21c40f553cf396d3eab7cd2289cd926e2c06b0) |
| 4        | `dispute`          | FINALIZED           | `0x9795d8e51ae9086884109343da6c7c3891eac1f26b7f18ff69e1e845505de371` | [View](https://explorer-studio-dev.genlayer.com/tx/0x9795d8e51ae9086884109343da6c7c3891eac1f26b7f18ff69e1e845505de371) |
| 4        | `resolve`          | FINALIZED           | `0x535b7200c4565845abdb8ae1caf59c03390abc860536be4545075d88c1e33ac9` | [View](https://explorer-studio-dev.genlayer.com/tx/0x535b7200c4565845abdb8ae1caf59c03390abc860536be4545075d88c1e33ac9) |

## Verdict Detail (Deal 4)

| Field            | Value                                                                                                                                                                                                       |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `case_file_hash` | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7`                                                                                                                                          |
| `verdict`        | `APPROVED`                                                                                                                                                                                                  |
| `status`         | `released`                                                                                                                                                                                                  |
| `fetch_failures` | `0`                                                                                                                                                                                                         |
| Reasoning        | Validators agreed: APPROVED. The case file shows no disputes, chain integrity passed, and no evidence of failed delivery or unmet acceptance criteria, so fulfillment is supported by the available record. |

## Verdict Detail (mismatch deal)

Deal 5 (`mismatch_live_001`) is the tamper path, demonstrated live. The evidence
served is the **real** public case file — the same URL and bytes as the happy
path — but the hash committed in `dispute` is deliberately wrong.

| Field                                               | Value                                                                                             |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `case_file_url`                                     | `https://raw.githubusercontent.com/hoveiser/flight-recorder/main/demo/case_files/happy_path.json` |
| `case_file_hash` served (true SHA-256 of the bytes) | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7`                                |
| `case_file_hash` anchored at dispute time           | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf8`                                |
| Difference                                          | Final hex character flipped (`…cf7` → `…cf8`)                                                     |
| `verdict`                                           | `EVIDENCE_MISMATCH`                                                                               |
| `status`                                            | `refunded`                                                                                        |
| `fetch_failures`                                    | `0`                                                                                               |
| Refund                                              | Client `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E` receives `100000000000000000` wei (0.1 GEN)   |
| Reasoning                                           | `Case file hash mismatch`                                                                         |

Validators' reasoning: `_ai_round` hashes the raw response body and compares it
against `case_file_hash` before any other check. The stored hash (`…cf8`) is not
the digest of the fetched file (`…cf7`), so every validator independently lands
on `MISMATCH` — a verdict derived from the bytes, not from the model, which is
why it must agree exactly. `resolve` maps `MISMATCH` to the public label
`EVIDENCE_MISMATCH`, pays the client through `_payout`, and sets
`status = "refunded"`.

Two consequences worth stating explicitly:

- **The refund happens inside `resolve`, not in `finalize`.** There is no
  fourth transaction for this deal. `finalize` only ever pays out an
  `adjudicated` deal, and an evidence verdict never reaches that status.
- **No appeal is offered.** Retrying the same bytes cannot change a hash, so
  `appeals_used` stays `0` and the escrow is returned immediately.

## Off-Chain Anchor (Deal 2)

The FastAPI service recorded `REQUEST`, `DELIVERY`, and `VALIDATION` events, producing
chain head `182864792556b44b73774e954652066cbe4cae82bdc4e9aba3b94dc2061d59ba`. That
chain head was written on-chain with `anchor_milestone` and read back from
`get_deal(2).milestones.delivery`, confirming the on-chain anchor matches the
off-chain log.

## Balance

The deployer address `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E` holds
`29496341696499963493` wei, or `29.496341696499963493 GEN`, after running all
scenarios on this contract (including the mismatch run).

---

# Validation run on audited contract 0x223323CE… (2026-09-24)

Contract: `0x223323CE1b755313212FaD13016543C0E4E63E12` (D3)
Network: GenLayer Studio Next (chain 61997)
Explorer: <https://explorer-studio-dev.genlayer.com/address/0x223323CE1b755313212FaD13016543C0E4E63E12>
Harness: `node scripts/e2e_demo.js`

This deployment is repo-HEAD v3 plus the two audit patches that were applied on the
`audit-contract` branch: **F4** (`anchor_milestone` refuses to overwrite an existing
anchor) and **F6** (the agreement digest is accepted in both the Python `ensure_ascii`
form and the browser form).

## Deal

| Field               | Value                                                                                           |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| `external_deal_id`  | `demo_scraper_001`                                                                              |
| `agreement_hash`    | `aaaaaaaa…` (64 × `a`, the harness placeholder)                                                 |
| `amount`            | `100000000000000000` wei (0.1 GEN), taken from the attached value                               |
| `worker`            | `0x1111111111111111111111111111111111111111`                                                    |
| `appeal_window_sec` | `300`                                                                                           |
| `case_file_url`     | `https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json`                      |
| `case_file_hash`    | `2828c1d269bd9c80d634131ec107ac69f1cfc3bf1f98d24c112c825c8acd7902`                              |
| `verdict`           | `AGREEMENT_MISMATCH`                                                                            |
| `status`            | `refunded`                                                                                      |
| `payout_status`     | `paid`                                                                                          |
| Reasoning           | `Case file has no definition_of_done`                                                           |
| Payout              | Client `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E` receives `100000000000000000` wei (0.1 GEN) |

## Transactions

| Step | Method      | TX hash                                                              | Explorer                                                                                                               |
| ---- | ----------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1    | `open_deal` | `0x15759b9b259727beabedbd99ba6b50bcb6b091ac242ddd168ededc86bea3bbee` | [View](https://explorer-studio-dev.genlayer.com/tx/0x15759b9b259727beabedbd99ba6b50bcb6b091ac242ddd168ededc86bea3bbee) |
| 2    | `dispute`   | `0x55b5e64665ddbf18fb986d264eaee035169c5f7f91c5b0b24ce019f14ea8123d` | [View](https://explorer-studio-dev.genlayer.com/tx/0x55b5e64665ddbf18fb986d264eaee035169c5f7f91c5b0b24ce019f14ea8123d) |
| 3    | `resolve`   | `0x18b2afe34a8e55757e36bd989910640be42d7122feda7b5533e7d83de6638ccf` | [View](https://explorer-studio-dev.genlayer.com/tx/0x18b2afe34a8e55757e36bd989910640be42d7122feda7b5533e7d83de6638ccf) |
| 4    | `finalize`  | `0x15487c172424da305f5c75ead1a15f478951b5c7413688511760c3888e906b7e` | [View](https://explorer-studio-dev.genlayer.com/tx/0x15487c172424da305f5c75ead1a15f478951b5c7413688511760c3888e906b7e) |

Total fees spent: `300761265600041408` wei.

## Why the verdict is AGREEMENT_MISMATCH

`e2e_demo.js` points `dispute` at the **TypeScript `package.json`** rather than the
project case file. That file is fetchable and hashable, so the evidence layer accepts
it — but a `package.json` carries no `definition_of_done`, so the contract cannot
recompute the deal's terms from it. The agreement gate returns `DISAGREEMENT`, which
`resolve` publishes under the public label `AGREEMENT_MISMATCH` and refunds the client.
The verdict therefore comes from the shape of the evidence, not from an LLM opinion:
no prompt was ever answered for this deal.

On the v2 contract the same four calls would have gone differently: v2 has no agreement
gate, so validators would have read the fetched `package.json` and adjudicated on its
content, and the escrow could have been released to the worker on evidence that never
contained the deal's terms. This run is the clearest on-chain contrast between the two
generations.

## What this run does and does not prove

- **It does prove** the v3 agreement gate executes on-chain and routes to a client
  refund, and that a deal can be opened, disputed, resolved and drained of escrow
  against the new address.
- **It does not prove F4.** `e2e_demo.js` never calls `anchor_milestone`, so the
  re-anchoring path is untouched by this run; F4 is covered only by the direct-mode
  suite.
- **It does not prove F6.** The non-ASCII digest fix matters when a
  `definition_of_done` exists and its two canonical forms differ. Here the case file
  had no `definition_of_done` at all, so the digest comparison was never reached.
- **It does not exercise F1.** `open_deal` was called with four positional arguments and
  the amount came from the attached value, which is the safe path.
- **The refund moved in `resolve`, not in `finalize`.** `resolve` pays through
  `_payout` and sets `status = "refunded"` in the same transaction; `finalize` requires
  `status == "adjudicated"` and raises `Not adjudicated` otherwise, so the fourth
  transaction cannot move funds — `get_payouts()` shows exactly one entry for this deal.

## A note on how this file is produced

`scripts/e2e_demo.js` rewrites `scripts/e2e_results.md` in full on every run, so the
harness replaces the record it is supposed to append to. The v2 scenario matrix above
was restored from git after such a rewrite, and this section was added by hand. Any
future run of the demo will clobber both.

---

# Validation run on v4 contract 0xfD91f7… (2026-09-26)

Contract: `0xfD91f7eDCa653702ACe1F040F4d56d35e674c750` (v4, CURRENT)
Network: GenLayer Studio Next (chain 61997)
Explorer: <https://explorer-studio-dev.genlayer.com/address/0xfD91f7eDCa653702ACe1F040F4d56d35e674c750>
Harness: `node scripts/e2e_demo.js` (single run)

v4 is repo-HEAD plus the audit follow-ups shipped in one redeploy: **F1** (escrow is
exactly `gl.message.value`; the caller-declared `amount` argument is gone), **F2**
(`timeout_release` recovers an `unresolvable` deal to the client after the appeal
window), **F3** (`resolve` is party-gated), **G2** (validators now see the last ≤5
event payloads, not just counters) and **G7** (`appeal` accepts a new case-file URL as
new evidence). This run uses the same harness as the v3-audit run, so the contrast is
like-for-like.

## Deal

| Field               | Value                                                                                           |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| `external_deal_id`  | `demo_scraper_001`                                                                              |
| `agreement_hash`    | `aaaaaaaa…` (64 × `a`, the harness placeholder)                                                 |
| `amount`            | `100000000000000000` wei (0.1 GEN) — taken from the attached value, which is the F1 guarantee    |
| `worker`            | `0x1111111111111111111111111111111111111111`                                                    |
| `appeal_window_sec` | `300`                                                                                           |
| `case_file_url`     | `https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json`                      |
| `case_file_hash`    | `2828c1d269bd9c80d634131ec107ac69f1cfc3bf1f98d24c112c825c8acd7902`                              |
| `verdict`           | `AGREEMENT_MISMATCH`                                                                            |
| `status`            | `refunded`                                                                                      |
| `payout_status`     | `paid`                                                                                          |
| Reasoning           | `Case file has no definition_of_done`                                                           |
| Payout              | Client `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E` receives `100000000000000000` wei (0.1 GEN) |

## Transactions

| Step | Method      | TX hash                                                              | Execution result       | Explorer                                                                                                               |
| ---- | ----------- | -------------------------------------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1    | `open_deal` | `0xc8356fe3f422ccbf157ddaa8a73d14b3598b51057b6ec3d4aa75af49c18a8c19` | `FINISHED_WITH_RETURN` | [View](https://explorer-studio-dev.genlayer.com/tx/0xc8356fe3f422ccbf157ddaa8a73d14b3598b51057b6ec3d4aa75af49c18a8c19) |
| 2    | `dispute`   | `0x9bf8c33a561c2b23785acd78e49239dba617522a67c0129df6f8fa63fd366085` | `FINISHED_WITH_RETURN` | [View](https://explorer-studio-dev.genlayer.com/tx/0x9bf8c33a561c2b23785acd78e49239dba617522a67c0129df6f8fa63fd366085) |
| 3    | `resolve`   | `0xa5e3f0f31f31e7ac19afe0795e3c303f7ef5f7fdcc326400a8a535527d2f026e` | `FINISHED_WITH_RETURN` | [View](https://explorer-studio-dev.genlayer.com/tx/0xa5e3f0f31f31e7ac19afe0795e3c303f7ef5f7fdcc326400a8a535527d2f026e) |
| 4    | `finalize`  | `0xc516bea64ab8bcb136e0f61af24e964a52f5b259a07ca16d897185aa8292b25c` | `FINISHED_WITH_ERROR`  | [View](https://explorer-studio-dev.genlayer.com/tx/0xc516bea64ab8bcb136e0f61af24e964a52f5b259a07ca16d897185aa8292b25c) |

Total fees spent: `300761265600041408` wei.

## Which steps did real work (honest note)

All four transactions reached `FINALIZED`, but finalization is a consensus-lifecycle
state, not a measure of whether the call changed anything. The execution result and the
emitted messages — read back with `getTransaction` — tell the real story:

- **`open_deal`, `dispute`, `resolve` → `FINISHED_WITH_RETURN` (real work).**
  `open_deal` locked exactly `100000000000000000` wei from the attached value (F1:
  there is no longer a caller-declared `amount` that could inflate it). `dispute`
  anchored the case-file URL and hash. `resolve` ran the evidence gate, found the
  fetched `package.json` carries no `definition_of_done`, returned `AGREEMENT_MISMATCH`
  and **emitted the refund transfer** — its message list is
  `[{ recipient: 0xE68c…c95E, value: 100000000000000000 }]`. This is the transaction
  that actually moved the escrow.
- **`finalize` → `FINISHED_WITH_ERROR` (no work).** Its message list is empty (`[]`).
  `resolve` had already driven the deal to the terminal `refunded` state and paid the
  client, so `finalize`'s guard (`status` must be `adjudicated`) raised `Not adjudicated`
  and execution reverted. `get_deal(1)` is byte-identical before and after this call and
  `get_payouts()` holds exactly one entry. The fourth transaction is on-chain and paid a
  fee, but it moved no funds and changed no state.

This is the same shape as the v3-audit run: the evidence refund happens inside
`resolve`, and `finalize` is a no-op on an already-settled deal.

## What this run does and does not prove

- **It does prove F1 on-chain.** The stored `amount` equals the attached value
  (`100000000000000000` wei) with no caller-supplied amount in the call, and the refund
  paid back exactly that value.
- **It does prove** the agreement gate still routes a term-less case file to a client
  refund on the v4 address, and that a deal can be opened, disputed, resolved and
  drained of escrow against it.
- **It does not exercise F2, F3, G2 or G7.** The harness never drives a deal to
  `unresolvable` (F2), never calls `resolve` from a non-party (F3), disputes a
  `package.json` with no events so the new payload depth is never reached (G2), and
  never appeals (G7). Those four are covered by the direct-mode suite in
  `tests/direct/test_settlement.py`, not by this run.


---

# E2E demo run 2026-10-10T22:08:40.617Z
# Settlement E2E Demo Summary

- Contract: 0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1
- Network: studio-dev
- Worker: 0x1111111111111111111111111111111111111111
- On-chain deal: 4 (demo_scraper_1791670000220), anchored delivery head 0a0320cd936e154dd87ca0cffacdff4e65d63568dc06c4fc0c6ee7919f338c63
- Off-chain deal: demo_scraper_1791670040310 (2 signed events, sealed at 0a0320cd936e154dd87ca0cffacdff4e65d63568dc06c4fc0c6ee7919f338c63)
- Case file: https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json
- Note: this static case file carries no definition_of_done, so the expected
  outcome is the DISAGREEMENT path (labeled AGREEMENT_MISMATCH) refunding the
  client inside resolve(). It exercises the pipeline, not a happy verdict.
- Finalize: not needed, resolve() already settled the deal (status refunded)
- Final deal: {"client": "0x3de43AA2f7162c80af98abe78222aE0Cdf83c506", "worker": "0x1111111111111111111111111111111111111111", "external_deal_id": "demo_scraper_1791670000220", "agreement_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "amount": 100000000000000000, "status": "refunded", "milestones": {"delivery": "0a0320cd936e154dd87ca0cffacdff4e65d63568dc06c4fc0c6ee7919f338c63"}, "verdict": "AGREEMENT_MISMATCH", "verdict_at": 1791670084, "appeal_window_sec": 300, "appeals_used": 0, "fetch_failures": 0, "case_file_hash": "2828c1d269bd9c80d634131ec107ac69f1cfc3bf1f98d24c112c825c8acd7902", "payout_status": "paid", "created_at_ts": 1791670002, "case_file_url": "https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json", "reasoning": "Case file has no definition_of_done"}
- Final payouts: [{"to": "0x3de43AA2f7162c80af98abe78222aE0Cdf83c506", "amount": 100000000000000000}, {"to": "0x3de43AA2f7162c80af98abe78222aE0Cdf83c506", "amount": 100000000000000000}, {"to": "0x3de43AA2f7162c80af98abe78222aE0Cdf83c506", "amount": 100000000000000000}]
- Total fees spent: 200761275200031056 wei

## Transactions

| Step | TX hash | Explorer | Fee (wei) |
| --- | --- | --- | ---: |
| open_deal | 0x7c0e0d59bfb21086b0971c67e04889ce6d0909ad19b76ef916b1cd3a19f30951 | https://explorer-studio-dev.genlayer.com/tx/0x7c0e0d59bfb21086b0971c67e04889ce6d0909ad19b76ef916b1cd3a19f30951 | 100000000000010352 |
| dispute | 0x20a2795c8012f38a88d9b0aeb4b668d0cf91ba8aa8eca26a49e5e05111ca9fcf | https://explorer-studio-dev.genlayer.com/tx/0x20a2795c8012f38a88d9b0aeb4b668d0cf91ba8aa8eca26a49e5e05111ca9fcf | 100000000000010352 |
| resolve | 0xb36dac933c5665116f4802fd657ab4d438b8797448d841913dd490429f575e67 | https://explorer-studio-dev.genlayer.com/tx/0xb36dac933c5665116f4802fd657ab4d438b8797448d841913dd490429f575e67 | 761275200010352 |

---

# Adversarial live run against D5, 2026-10-10

Contract D5: `0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1` on studio-dev (chain 61997).
Script: `node scripts/adversarial_live.js` (re-runnable; it opens a fresh deal each run).

Roles: the deal client is the project .env throwaway key (the account that deployed D5),
the counterparty is the publicly committed GenLayer devnet test key that already lives in
`gltest.config.yaml`, and the stranger is a key derived from a fixed seed so the run is
reproducible. The stranger is funded with test GEN by the client, because being refused
still costs the caller a transaction fee.

How refusal is measured rather than assumed: on this chain a contract that raises still
ends `statusName FINALIZED` with `result_name MAJORITY_AGREE` (the validators agreed on
the outcome), and the transaction record carries no revert string. The field that
separates an accepted write from a refused one is `txExecutionResultName`:
FINISHED_WITH_RETURN when the method ran, FINISHED_WITH_ERROR when it raised. Every case
below therefore asserts two things: the call did not execute, and the deal did not move.
The guard is the whole deal read back field by field against the state captured a moment
before the attempt. The exact rejection message for each guard is asserted in the
direct-mode suite, where expect_revert() can see the string.

Every transaction hash in this table was checked against the explorer JSON API
(`https://explorer-studio-dev.genlayer.com/api/transactions/{hash}`) by the run itself; the
explorer column is what that API reported. The first run of this script (deal 5) is not used
as evidence here: one case was marked failed by a stale snapshot in the harness rather than
by the contract, and the fixed harness was re-run. The deals those runs left open were
settled afterwards (`node scripts/settle_open_deals.js 2 5 6`), and all three landed on
AGREEMENT_MISMATCH and refunded the client: these runs open their deals with an agreement
hash of 64 zeros, so the case file's own terms can never match what was committed. That is
the demo's arrangement, not a contract fault, and it is the ordering the direct-mode tests
assert: the agreement gate runs before the anchor gate.

| case | actor | call | wanted | contract guard (asserted in direct mode) | tx | execution | explorer | result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_deal | client | open_deal | success | n/a (setup) | `0x0eab0b12a415dae0286cb5e0d9fac539310bb42395bfe452d6231fd3ff7f63d0` | FINISHED_WITH_RETURN | FINALIZED | pass |
| missing_head | worker | dispute | revert | chain_head must be 64 lowercase hex characters | `0x70987cba135cad9af59713d42c6be81890f79aaf53f27a0e8c7f50290a86a192` | FINISHED_WITH_ERROR | FINALIZED | pass |
| non_party_dispute | stranger | dispute | revert | Only parties | `0xae0e1e5ab6d616b82febf6e654fea52345c81b7d9a9e194d5f39d6d8330343d8` | FINISHED_WITH_ERROR | FINALIZED | pass |
| anchor_head_a | worker | anchor_milestone | success | n/a (setup: the counterparty anchors first) | `0x8ebccfab1a56935e2654ac7b74db6313373e33ebe5687e1576777830a3bdde46` | FINISHED_WITH_RETURN | FINALIZED | pass |
| wrong_head_after_anchor | client | dispute | revert | ANCHOR_MISMATCH: chain head does not match the anchored delivery head | `0x258fb81851604fd57b28fae1e3ae486e3bfab5859b8d3eecc2724cd44e4a072c` | FINISHED_WITH_ERROR | FINALIZED | pass |
| anchor_overwrite | worker | anchor_milestone | revert | Milestone already anchored | `0x052327a79c59999e6f94c8cfb36ae8b398d28ca6e4be0e58a0b0a8031073ef1c` | FINISHED_WITH_ERROR | FINALIZED | pass |
| finalize_out_of_order | client | finalize | revert | Not adjudicated | `0x46703902d492f3590a4eddc5b0c351eefb371f6fb753d1b3676f522be2e9bbb6` | FINISHED_WITH_ERROR | FINALIZED | pass |
| resolve_by_stranger | stranger | resolve | revert | Only parties can resolve | `0xe707c55468d98bc8323ce0082a628574b8584e106cb186b33f7d36d1cb892790` | FINISHED_WITH_ERROR | FINALIZED | pass |
| zero_value_open_deal | client | open_deal | revert | open_deal requires payable value | `0xb354bd22fd4fe1987eb8954e736f15f3a6e46bf2cf8171d2a6a5c2f75325ea1b` | FINISHED_WITH_ERROR | FINALIZED | pass |
| honest_dispute_with_anchored_head | client | dispute | success | n/a (the head that is on record is accepted) | `0x7c9f1f3c9102e1efbbaebde2597040291ba90288bca5cce45bf4e2d696c520b1` | FINISHED_WITH_RETURN | FINALIZED | pass |

## Settling the deals those runs left open

`node scripts/settle_open_deals.js 2 5 6`. Each hash below was read back from the
explorer JSON API by the script itself, and the deal state was re-read after every
transaction rather than inferred from the transaction status.

| deal | why it was open | call | tx | explorer | outcome |
| --- | --- | --- | --- | --- | --- |
| 2 | opened by the second e2e run before that script looked its deal id up, so its dispute went to deal 1 and this one stayed funded | dispute | `0x93d3efd48881cde9186824318aee4c5f0fdee1a102f9ae6fa3b3a7c1f2e598b3` | FINALIZED | status disputed, delivery anchor written from the head that run had sealed |
| 2 | | resolve | `0x5d7ac9b27ea4ab8211f02656b360ec100a97687b5c9cac3a841e5c3dba3313db` | FINALIZED | AGREEMENT_MISMATCH, refunded, payout paid ("Case file has no definition_of_done") |
| 5 | adversarial run 1, left disputed after its honest dispute | resolve | `0x01b8686bafde54e4fdb9ad9deb1f5cef83dba5b3ba68e5d717cd1c2466c73619` | FINALIZED | AGREEMENT_MISMATCH, refunded, payout paid ("Case file terms do not match the anchored agreement") |
| 6 | adversarial run 2 (the recorded run), left disputed on purpose | resolve | `0x940c0fb5103df00977bf3fb9395d6f1fa711f509c48b020ea090be2880019e26` | FINALIZED | AGREEMENT_MISMATCH, refunded, payout paid |

After this, every deal on D5 is in a settled state and no test escrow is locked: `get_payouts()`
returns six refunds of 100000000000000000 wei, all to `0x3de43AA2f7162c80af98abe78222aE0Cdf83c506`.


---

# E2E demo run 2026-10-12T10:40:03.828Z
# Settlement E2E Demo Summary

- Contract: 0x51A54D74e86159482F2E57b8d4744c7Ba44D7043
- Network: studio-dev
- Worker: 0x1111111111111111111111111111111111111111
- On-chain deal: 3 (demo_scraper_1791801482764), anchored delivery head da22a5db81035c54bbee3c6aec0a526d8addef31dcf1877b478581724f88ae98
- Off-chain deal: demo_scraper_1791801523123 (2 signed events, sealed at da22a5db81035c54bbee3c6aec0a526d8addef31dcf1877b478581724f88ae98)
- Case file: https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json
- Note: this static case file carries no definition_of_done, so the expected
  outcome is the DISAGREEMENT path (labeled AGREEMENT_MISMATCH) refunding the
  client inside resolve(). It exercises the pipeline, not a happy verdict.
- Finalize: not needed, resolve() already settled the deal (status refunded)
- Final deal: {"client": "0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E", "worker": "0x1111111111111111111111111111111111111111", "external_deal_id": "demo_scraper_1791801482764", "agreement_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "amount": 100000000000000000, "status": "refunded", "milestones": {"delivery": "da22a5db81035c54bbee3c6aec0a526d8addef31dcf1877b478581724f88ae98"}, "verdict": "AGREEMENT_MISMATCH", "verdict_at": 1791801563, "appeal_window_sec": 300, "appeals_used": 0, "fetch_failures": 0, "case_file_hash": "2828c1d269bd9c80d634131ec107ac69f1cfc3bf1f98d24c112c825c8acd7902", "payout_status": "paid", "created_at_ts": 1791801484, "case_file_url": "https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json", "reasoning": "Case file has no definition_of_done"}
- Final payouts: [{"to": "0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E", "amount": 100000000000000000}, {"to": "0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E", "amount": 100000000000000000}]
- Total fees spent: 200761272800031056 wei

## Transactions

| Step | TX hash | Explorer | Fee (wei) |
| --- | --- | --- | ---: |
| open_deal | 0x6f40ba1bc9bb314225b879ee7666170af2b734fe0f9a79acb53c86f542b05027 | https://explorer-studio-dev.genlayer.com/tx/0x6f40ba1bc9bb314225b879ee7666170af2b734fe0f9a79acb53c86f542b05027 | 100000000000010352 |
| dispute | 0x2086e11c894842da7b945779d9e15935c2c6eb3d53842053f830ed9bfbac500b | https://explorer-studio-dev.genlayer.com/tx/0x2086e11c894842da7b945779d9e15935c2c6eb3d53842053f830ed9bfbac500b | 100000000000010352 |
| resolve | 0x3f55f3eb51f7cdd20c3a3eb632e86fb681aa2309363c614b8afded9c9322002b | https://explorer-studio-dev.genlayer.com/tx/0x3f55f3eb51f7cdd20c3a3eb632e86fb681aa2309363c614b8afded9c9322002b | 761272800010352 |

## D6 live adversarial run (Oct 12, 2026), contract `0x51A54D74e86159482F2E57b8d4744c7Ba44D7043`

This deployment closes F5: `resolve()` recomputes the event hash chain itself and
pays only when its own digest equals the delivery head anchored at dispute. It no
longer reads `chain_integrity.verification` or the case file's declared head.

Deploy tx `0x2edb7e3e78f45b50866fc0a1b41326a7091a4033889fc9c126616687a59edb9a` ->
FINALIZED, `to` = the D6 address above. Verified through the explorer JSON API
(`GET /api/transactions/{hash}`), not just the RPC the script polls.

Run with: `node scripts/adversarial_live.js`. Case file served to the validator
network: the published `demo/case_files/happy_path.json` (digest
`0ae7f1ad7eca720eaefd9e651e9c60fe258648ac6a19cc58e4d2c896dff12908`, declared head
`33d588cbd07c6949b41f87cce222c9dcce66bebb4cae5130e1523bab79643771`). A party, and
the publicly committed GenLayer devnet test key, plays the counterparty.

Summary: 12 cases, 12 passed, 0 failed, 0 state problems. Every transaction was
confirmed FINALIZED by the explorer and its execution result checked
(FINISHED_WITH_RETURN means the method ran, FINISHED_WITH_ERROR means the guard
reverted it), and each deal's on-chain state was read back after every attempt.

| case | actor | call | wanted | on-chain guard result | execution | result |
| --- | --- | --- | --- | --- | --- | --- |
| open_deal | client | open_deal | success | deal 1 funded | FINISHED_WITH_RETURN | pass |
| missing_head | worker | dispute | revert | chain_head must be 64 lowercase hex characters | FINISHED_WITH_ERROR | pass |
| non_party_dispute | stranger | dispute | revert | Only parties | FINISHED_WITH_ERROR | pass |
| anchor_head_a | worker | anchor_milestone | success | delivery anchored | FINISHED_WITH_RETURN | pass |
| wrong_head_after_anchor | client | dispute | revert | ANCHOR_MISMATCH at dispute time | FINISHED_WITH_ERROR | pass |
| anchor_overwrite | worker | anchor_milestone | revert | Milestone already anchored | FINISHED_WITH_ERROR | pass |
| finalize_out_of_order | client | finalize | revert | Not adjudicated | FINISHED_WITH_ERROR | pass |
| resolve_by_stranger | stranger | resolve | revert | Only parties can resolve | FINISHED_WITH_ERROR | pass |
| zero_value_open_deal | client | open_deal | revert | open_deal requires payable value | FINISHED_WITH_ERROR | pass |
| honest_dispute_with_anchored_head | client | dispute | success | head on record accepted | FINISHED_WITH_RETURN | pass |
| chain_anchor_wrong_head | client | dispute | success | anchors a head the events cannot produce | FINISHED_WITH_RETURN | pass |
| chain_mismatch_refunds | client | resolve | success | recomputed head != anchor -> CHAIN_MISMATCH, refunded | FINISHED_WITH_RETURN | pass |

The D6-specific pair, on a separate deal opened against the happy-path agreement:

- `chain_anchor_wrong_head` tx `0x05ac01b3d1c2c063ef926a9ebfe6b8af80bf0ca94ea6427da78aabdb60178708`:
  dispute serves the public happy path but anchors `HEAD_B` (`b` * 64), a head the
  events do not produce. On-chain state after: `status` disputed,
  `milestones.delivery` = `HEAD_B`. Verified FINALIZED.
- `chain_mismatch_refunds` tx `0x1b7a43ad5b493de2cdc6b3b3889b4cfbb5ca1935c2453844536d9e891e9ed1eb`:
  resolve re-fetches the file, recomputes the chain (head `33d588cb...`), sees it
  does not equal the anchored `HEAD_B`, and lands on `verdict`
  `CHAIN_MISMATCH`, `status` `refunded`, `payout_status` `paid` to the client.
  `get_payouts()` recorded the refund. This is F5 caught live: the contract did
  the hashing itself and refused to pay on a head mismatch, with the model never
  consulted. Verified FINALIZED.

Scope note, stated honestly: the structural tamper variants (edited payload with
a lying PASS flag, reordered events, dropped middle event, truncated tail, extra
event appended after the anchored head, duplicated event, tampered signature
field, wrong field type, unknown version, oversized body, event-count ceiling)
are each proven deterministically by the golden vectors run through this same
contract source in direct mode (`tests/direct/test_chain_recompute.py`, 23
vectors). Reproducing them live would mean hosting mutated case files on a URL
the validator network can fetch, which is out of scope for this run; the live run
above exercises the anchor-versus-recompute decision end to end on real
validator-fetched bytes.

### Honest open and dispute on D6 (partial), resolve blocked by a chain quirk

`SCENARIOS=happy node scripts/run_live_scenarios.js` opened a deal
(`0x82a6ccd5b19ded2a9766361831563c9ee0d4fbd6ac2adf423e4d12c36ecad3ec`, FINALIZED)
and disputed the public happy path anchoring its real head `33d588cb...`
(`0x313d690aaa8e56e72fbc792d3858add45df3c1a398d7d1edc1055f5078072957`, FINALIZED),
both verified through the explorer JSON API. The resolve step then failed before
submission with `sim_estimateTransactionFees: execution failed`: studio-dev cannot
simulate the fee of a resolve that reaches the LLM round, so the harness's
estimate-first path aborts. This is an environment limitation of this round's
live run, not a contract behavior: a resolve that returns before the model (the
CHAIN_MISMATCH case above) estimates and executes fine. That the honest chain
still clears the new recompute gate is proven deterministically by the MATCH
golden vectors run through this same contract source in direct mode and in CI
(`tests/direct/test_chain_recompute.py`, all 11 honest vectors land on APPROVED).

