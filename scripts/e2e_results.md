# Live E2E Results

Contract: `0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35`  
Network: GenLayer Studio Next (chain 61997)

## Scenario Matrix

| Scenario | Deal | Status / verdict | Payout | Error |
| --- | ---: | --- | --- | --- |
| 0 / Original refunded lifecycle | 1 | `refunded` / `EVIDENCE_MISMATCH` | Client: 0.1 GEN | None |
| 1 / Happy path run | 4 | `refunded` / `EVIDENCE_MISMATCH` | Client: 0.1 GEN | None; validator result was `MISMATCH` because fetched case-file hash differed |
| 1 / Happy path retry | 7 | `refunded` / `EVIDENCE_MISMATCH` | Client: 0.1 GEN | Exact validator reasoning: `Case file hash mismatch` |
| 2 / Off-chain anchor | 5 | `funded`; `delivery` milestone anchored and verified | None | None |
| 3 / Timeout release | 6 | `funded`; early release correctly rejected | None | `Timeout not reached (7 days)`; 7-day escrow lock enforced |

## Transactions

| Scenario | Method | Status | TX hash | Explorer |
| --- | --- | --- | --- | --- |
| 0 | `open_deal` | FINALIZED | `0x3f524038bade95409d05f1b611774fdaac120e685204a1a266b159c132ca56af` | [View](https://explorer-studio-dev.genlayer.com/tx/0x3f524038bade95409d05f1b611774fdaac120e685204a1a266b159c132ca56af) |
| 0 | `dispute` | FINALIZED | `0xfdca5bce6f4826a1dc53c4fd4d10ba75361064900ee81bb19d806debca41e8d5` | [View](https://explorer-studio-dev.genlayer.com/tx/0xfdca5bce6f4826a1dc53c4fd4d10ba75361064900ee81bb19d806debca41e8d5) |
| 0 | `resolve` | FINALIZED | `0x05b82cbb7ce17e4ce664dc5cac038eb4c8cac613c6ea344c49b429a5031ff558` | [View](https://explorer-studio-dev.genlayer.com/tx/0x05b82cbb7ce17e4ce664dc5cac038eb4c8cac613c6ea344c49b429a5031ff558) |
| 0 | `finalize` | FINALIZED | `0xc8a18748628da2aebdc5046b4ef283cb17f7fe2e23ef4f3938b06701d142bfcf` | [View](https://explorer-studio-dev.genlayer.com/tx/0xc8a18748628da2aebdc5046b4ef283cb17f7fe2e23ef4f3938b06701d142bfcf) |
| 1 | `open_deal` | FINALIZED | `0x0aecff57f43e76acfba2367a1404dc0409725552f452a4077be760e8babecddb` | [View](https://explorer-studio-dev.genlayer.com/tx/0x0aecff57f43e76acfba2367a1404dc0409725552f452a4077be760e8babecddb) |
| 1 | `dispute` | FINALIZED | `0xe5a168ba5ffe686124811987db988a67638f8cfb2a9e8cfba7058dc526ac5b48` | [View](https://explorer-studio-dev.genlayer.com/tx/0xe5a168ba5ffe686124811987db988a67638f8cfb2a9e8cfba7058dc526ac5b48) |
| 1 | `resolve` | FINALIZED | `0x35b58a3496e94482dd3c420215be350565a1273822e1925df3eb7a91a91511ab` | [View](https://explorer-studio-dev.genlayer.com/tx/0x35b58a3496e94482dd3c420215be350565a1273822e1925df3eb7a91a91511ab) |
| 2 | `open_deal` | FINALIZED | `0x46537bae9b40b1246cfd49f1775abde79bab2338d981617414c0fe227f847971` | [View](https://explorer-studio-dev.genlayer.com/tx/0x46537bae9b40b1246cfd49f1775abde79bab2338d981617414c0fe227f847971) |
| 2 | `anchor_milestone` | FINALIZED | `0xa01c838cd2746a809f8b0b362ec10a10a17b8b60743e6a7aaf2ab0c57887c711` | [View](https://explorer-studio-dev.genlayer.com/tx/0xa01c838cd2746a809f8b0b362ec10a10a17b8b60743e6a7aaf2ab0c57887c711) |
| 3 | `open_deal` | FINALIZED | `0xf2e2912525a436095a8a4d6e2e2b918e0a4d1801f97ced5235ecb17883b93ef2` | [View](https://explorer-studio-dev.genlayer.com/tx/0xf2e2912525a436095a8a4d6e2e2b918e0a4d1801f97ced5235ecb17883b93ef2) |
| 3 | `timeout_release` | FINALIZED; rejected | `0x2ed7b3619a97e64ec226a073f0103aae9948ff2ad166174c6149a1f6a59c64e7` | [View](https://explorer-studio-dev.genlayer.com/tx/0x2ed7b3619a97e64ec226a073f0103aae9948ff2ad166174c6149a1f6a59c64e7) |
| 1 retry | `open_deal` | FINALIZED | `0x2ba050ebed9c4d6788237eeaa1320bb6b21b58de0afb94f1c57d5145fcd47f1a` | [View](https://explorer-studio-dev.genlayer.com/tx/0x2ba050ebed9c4d6788237eeaa1320bb6b21b58de0afb94f1c57d5145fcd47f1a) |
| 1 retry | `dispute` | FINALIZED | `0xcdddcc65df7719b9559226d81886965294a4a8e0721de3307278bb0f1db3d456` | [View](https://explorer-studio-dev.genlayer.com/tx/0xcdddcc65df7719b9559226d81886965294a4a8e0721de3307278bb0f1db3d456) |
| 1 retry | `resolve` | FINALIZED | `0x32636e6b80f21734dff0f6d602db8a6085f582e4ae2dfa5e30dae6d990e0606f` | [View](https://explorer-studio-dev.genlayer.com/tx/0x32636e6b80f21734dff0f6d602db8a6085f582e4ae2dfa5e30dae6d990e0606f) |

## Happy Path Retry Details

| Source | SHA-256 | Bytes |
| --- | --- | ---: |
| Local `demo/case_files/happy_path.json` | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7` | 1363 |
| Fetched raw URL response | `ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7` | 1363 |

The hashes and byte counts matched exactly. Deal 7 nevertheless finalized as `refunded` / `EVIDENCE_MISMATCH`; validator reasoning was exactly `Case file hash mismatch`. No second retry was attempted.

## Balance

The deployer address used by the original live proof, `0xE68c0b64Bf1554801832d98Eb3B1597F8905c95E`, had `29898376970499983540` wei, or `29.898376970499983540 GEN`, remaining after these runs.