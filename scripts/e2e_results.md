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
