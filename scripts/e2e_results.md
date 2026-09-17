# Live E2E Results

Contract: `0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D`
Network: GenLayer Studio Next (chain 61997)
Explorer: <https://explorer-studio-dev.genlayer.com/address/0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D>

Run with:

```
node scripts/run_live_scenarios.js            # all three scenarios
node scripts/run_live_scenarios.js --happy    # happy path only
node scripts/run_live_scenarios.js --anchor   # off-chain anchor only
node scripts/run_live_scenarios.js --timeout  # 7-day lock check only
```

## Scenario Matrix

| Scenario | Deal | Status / verdict | Payout | Notes |
| --- | ---: | --- | --- | --- |
| 1 / Happy path | 4 | `released` / `APPROVED` | Worker: 0.1 GEN | Full lifecycle: dispute → AI resolve → finalize |
| 1 / Happy path (earlier run) | 1 | `released` / `APPROVED` | Worker: 0.1 GEN | Same case file, same verdict |
| 2 / Off-chain anchor | 2 | `funded`; `delivery` milestone anchored | None | Chain head written on-chain and readable back |
| 3 / Timeout release | 3 | `funded`; early release correctly rejected | None | `Timeout not reached (7 days)` — escrow lock enforced |

### Why the happy path now resolves to APPROVED

`gl.nondet.web.render(url, mode="text")` does **not** return the file bytes. It returns
a normalized text rendering, so its SHA-256 can never match the hash of the original
file that was committed in `dispute`. The contract now hashes the raw response body
returned by `gl.nondet.web.get(url)`.

Measured on-chain for `demo/case_files/happy_path.json`:

| Source | Bytes | SHA-256 | Matches dispute hash |
| --- | ---: | --- | --- |
| `gl.nondet.web.get(url).body` (raw bytes) | 1363 | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7` | Yes |
| `gl.nondet.web.render(url, mode="text")` | 1095 | `ae4972090e56fcbf6df9f1938cdbd03b87e8f2f13c0293d0e597a856631b10dc` | No |

The rendering step strips 268 bytes of JSON indentation, which is exactly why every
earlier attempt ended in `EVIDENCE_MISMATCH`. Hashing raw bytes makes the on-chain
check reproduce the same digest a user computes locally with `sha256sum`.

## Transactions

| Scenario | Method | Status | TX hash | Explorer |
| --- | --- | --- | --- | --- |
| 1 | `open_deal` | FINALIZED | `0x833a8910198c84928b23c5cb756ffe906e920a0d3f139b87c5a9447006a07260` | [View](https://explorer-studio-dev.genlayer.com/tx/0x833a8910198c84928b23c5cb756ffe906e920a0d3f139b87c5a9447006a07260) |
| 1 | `dispute` | FINALIZED | `0x571095fb0b6eeeace5e1b7a7ad12d1c7a6f9cd997ef1fa3bb217e6a65167758c` | [View](https://explorer-studio-dev.genlayer.com/tx/0x571095fb0b6eeeace5e1b7a7ad12d1c7a6f9cd997ef1fa3bb217e6a65167758c) |
| 1 | `resolve` | FINALIZED | `0xd581386fc82c0fe07e760e5bb2ef0fa922b30892d36c4a5384855abaedba4de8` | [View](https://explorer-studio-dev.genlayer.com/tx/0xd581386fc82c0fe07e760e5bb2ef0fa922b30892d36c4a5384855abaedba4de8) |
| 1 | `finalize` | FINALIZED | `0x847ed870335849c9d3c04225239e18aa669ea4065b48a42dbfaf8d049e2b61c9` | [View](https://explorer-studio-dev.genlayer.com/tx/0x847ed870335849c9d3c04225239e18aa669ea4065b48a42dbfaf8d049e2b61c9) |
| 2 | `open_deal` | FINALIZED | `0x576d72ba2d0d29a66470999ce1058d5654570b192457e3d97dcc2e07dee21cac` | [View](https://explorer-studio-dev.genlayer.com/tx/0x576d72ba2d0d29a66470999ce1058d5654570b192457e3d97dcc2e07dee21cac) |
| 2 | `anchor_milestone` | FINALIZED | `0x6d87f4edb69d24e05367163de8a9dc83d7f3dc15fa630d281d63b6e6a7cc1cd5` | [View](https://explorer-studio-dev.genlayer.com/tx/0x6d87f4edb69d24e05367163de8a9dc83d7f3dc15fa630d281d63b6e6a7cc1cd5) |
| 3 | `open_deal` | FINALIZED | `0x38128f22cab6d8260f32b97a2332ecabbe4722c033014f7023ec38560b52cf37` | [View](https://explorer-studio-dev.genlayer.com/tx/0x38128f22cab6d8260f32b97a2332ecabbe4722c033014f7023ec38560b52cf37) |
| 3 | `timeout_release` | FINALIZED; rejected | `0x19ca7d54d49cc5c75435e5d9fd9f4e1d9f9d60521a082a0e36a966efdb70e13d` | [View](https://explorer-studio-dev.genlayer.com/tx/0x19ca7d54d49cc5c75435e5d9fd9f4e1d9f9d60521a082a0e36a966efdb70e13d) |

## Verdict Detail (Deal 4)

| Field | Value |
| --- | --- |
| `case_file_hash` | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7` |
| `verdict` | `APPROVED` |
| `status` | `released` |
| `fetch_failures` | `0` |
| Reasoning | Validators agreed: APPROVED. The case file shows no disputes, chain integrity passed, and no evidence of failed delivery or unmet acceptance criteria, so fulfillment is supported by the available record. |

## Off-Chain Anchor (Deal 2)

The FastAPI service recorded `REQUEST`, `DELIVERY`, and `VALIDATION` events, producing
chain head `182864792556b44b73774e954652066cbe4cae82bdc4e9aba3b94dc2061d59ba`. That
chain head was written on-chain with `anchor_milestone` and read back from
`get_deal(2).milestones.delivery`, confirming the on-chain anchor matches the
off-chain log.

## Balance

The deployer address `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E` holds
`29496625500999965962` wei, or `29.496625500999965962 GEN`, after running all
scenarios on this contract.