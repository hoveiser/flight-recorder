# Judging Guide — Flight Recorder

A two-minute, fully verifiable overview for judges.

## What this is

Flight Recorder is a tamper-evident evidence layer for deals between AI
agents, paired with an on-chain intelligent contract that adjudicates
disputes with AI validators.

- Off-chain witness: every deal event is appended to a SHA-256 hash chain
  (FastAPI + SQLite), and since D5 every event is **signed** by the party that
  wrote it (EIP-191 `personal_sign` over the deal id, the previous hash, the event
  type, the payload digest and a bounded client timestamp). Any later edit breaks
  the chain visibly, and any write in somebody else's name fails to recover to it.
- On-chain judge: a GenLayer Intelligent Contract locks escrow at
  open_deal, anchors the case-file hash **and the sealed chain head** at dispute,
  re-fetches and re-hashes the served evidence during consensus, and pays the winner
  at finalize. No central arbiter.

## Live right now (click, don't trust)

1. Contract on GenLayer Studio Next (network `studio-dev`), chain 61997:
   0x51A54D74e86159482F2E57b8d4744c7Ba44D7043
   This is the v6 deployment (D6, 2026-10-12). What it changes: `resolve` no longer trusts
   anything the case file says about its own integrity. The contract recomputes the event hash
   chain from genesis with the recorder's own canonical serialization, re-derives every
   `payload_hash` and `event_hash`, and pays only when its own recomputed head equals the sealed
   chain head that `dispute` anchored on-chain. `chain_integrity.verification` and the declared
   head are ignored and no longer reach the validator prompt; a mismatch, a malformed or over-size
   case file, or an unknown hash version returns the discrete `CHAIN_MISMATCH` refund (the
   `TAMPERED` verdict is gone). D5's atomic head anchor stays: `dispute` takes the sealed chain
   head as a required fourth argument (64 lowercase hex) and writes it as the `delivery` anchor,
   or reverts if a different head is already on record, so the anchor is mutual and immutable, and
   `ANCHOR_MISMATCH` fails closed when no anchor exists. Fund-moving verdicts require exact
   validator consensus. Its validation runs are 23 golden hash-chain vectors driven through the
   contract in direct mode, a full lifecycle (`open_deal` → signed events → seal → `dispute` →
   `resolve`), and twelve adversarial cases including a live `CHAIN_MISMATCH` refund; all are
   listed with explorer links in `scripts/e2e_results.md`, and every hash there was read back from
   the explorer's own JSON API first.

   1a. Previous deployments, still on-chain and verifiable:
   0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1 (v5 / D5, 2026-10-10, the atomic head anchor),
   0xfD91f7eDCa653702ACe1F040F4d56d35e674c750 (v4 / D4, 2026-09-26),
   0x223323CE1b755313212FaD13016543C0E4E63E12 (audited v3 / D3) and
   0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D (v2 / D2).
   The v2 explorer shows the finalized transactions of four scenario runs on this
   address, including a live tamper demo: a deliberately wrong case-file hash was
   anchored, validators re-fetched and re-hashed the evidence, detected the mismatch,
   and refunded the client. Nothing was moved or rewritten when a new deployment came
   in. All five addresses are live, and each documented transaction says which one it
   ran on.

2. Browser wallet flow: the TRY A DISPUTE section on the site connects
   MetaMask/Rabby and signs open_deal and dispute from the visitor's own
   wallet, against the current v6 contract above. Every off-chain event the
   page records is signed by the connected address with `personal_sign`, and the
   dispute step seals the visitor's own log and anchors that head, so no extra
   step is needed to produce on-chain evidence. Every write returns its own
   explorer link. No shared private key, no silent gas.

3. Three verification paths on one page: explorer links; pytest tests/ -v
   (expect 173 passed, 12 skipped: 93 off-chain plus 80 direct-mode contract tests); and a
   zero-install hash checker that reproduces the anchored SHA-256 in your
   browser, with a tamper toggle.

## Reproduce locally, end to end

    git clone https://github.com/hoveiser/flight-recorder && cd flight-recorder
    pip install -r requirements.txt && npm install
    pytest tests/ -v          # 173 passed (CI); the off-chain half on Windows, direct mode needs Linux/macOS
    uvicorn src.main:app      # terminal 1: evidence service
    node scripts/e2e_demo.js  # terminal 2: full on-chain lifecycle

Reference runtime is Python 3.12 (CI); the deployed evidence API runs 3.10
(PythonAnywhere); the suite is green across the supported 3.10–3.14 range.

## Honest boundaries

- The v6 contract is deployed (D6, `0x51A54D…`, 2026-10-12). D5 (`0xc93007ac…`) added the atomic
  head anchor, and D4 (`0xfD91f7…`) carried the audited v3 hardening (incl. F4 and F6) plus fixes
  for the three findings that survived it (F1, F2 and F3); all of those are still true of D6.
  F1, F2 and F3 stay closed; the API and caller audit findings are F16 to F24 in
  [AUDIT.md](AUDIT.md), with the severity, the evidence, the fix and the covering test named for
  each.
- What D6 closed, stated plainly: the self-reported-chain gap (F5 and F23) is gone. `resolve` now
  recomputes the chain from the events and pays only when its own digest equals the delivery head
  anchored on-chain, so a case file's self-declared head and its `chain_integrity.verification`
  flag bind nothing and no longer reach the validator prompt. The residual is honest and small:
  the GenVM runtime has no ecrecover, so a version 2 signature is embedded in the hash (tampering
  with it breaks the head) but the contract cannot recover the signer on-chain, and a party that
  fabricates a fully self-consistent chain and disputes against its own fabricated head is not
  caught by recomputation alone. The independent guarantees are the on-chain anchor both parties
  were bound to and the write-time signature checks the API enforces. Signatures prove *who wrote
  an event*, not that the event is true.
- Off-chain event recording is served live by the hosted evidence API at
  https://hreicher.pythonanywhere.com; the browser TRY A DISPUTE flow records
  through it. The hosted instance must be pulled and reloaded after this branch is
  merged, otherwise it still runs the pre-signing code and refuses nothing.
  Visitors whose network is geo-blocked by PythonAnywhere (HTTP 451) can still run the
  local Quick Start path (`uvicorn src.main:app`) for the same result.
- The browser demo anchors the repo happy_path case file, regenerated from a real
  recorder run by `demo/make_case_file.py`, with a definition_of_done that matches the
  deal's own agreement, so the deployed contract's agreement gate is cleared, and its honest
  signed chain recomputes to the declared head `33d588cb…`, so D6's recompute gate is cleared too;
  the deal is adjudicated on the merits rather than refused as AGREEMENT_MISMATCH or
  CHAIN_MISMATCH. In the browser flow the visitor records and seals their own log, so the head they
  anchor is the one the contract recomputes from it.
- Contract and API audit: findings, severities, the two coverage matrices and the
  redeploy recommendation are in [AUDIT.md](AUDIT.md). Direct-mode tests require
  Linux/macOS (gltest cannot run its fd-0 message injection on Windows), so
  `pytest tests/` on Windows reports the off-chain half green and errors on the
  direct half; CI is the authoritative full run.
- Events written before D5 carry no signature and are reported as `UNSIGNED_LEGACY`
  by `GET /deals/{id}/verify` rather than treated as proven. New writes are refused
  without a signature.
- No integrated faucet: visitors fund their own test transactions, which
  is why every on-chain row is a real, independently verifiable run.

## Why two layers

Evidence stays inspectable off-chain; consensus stays distributed
on-chain. The anchored hash, the anchored head and the served case file must all
agree, or the deal does not settle. That intersection is the product.
