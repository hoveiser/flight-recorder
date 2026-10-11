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
   0xc93007ac5f62E6f9785B425A612bdAc1E2b245F1
   This is the v5 deployment (D5, 2026-10-10). What it adds on-chain: `dispute` now
   takes the sealed chain head as a required fourth argument (64 lowercase hex) and
   writes it as the deal's `delivery` anchor in the same transaction. If a head is
   already on record the new one must equal it or the whole call reverts, so the
   anchor is mutual and immutable rather than whichever party posted last. That makes
   `ANCHOR_MISMATCH` a gate on every disputed deal instead of only on pre-anchored
   ones, and it fails closed when no anchor exists. Its validation runs are a full
   lifecycle (`open_deal` → signed events → seal → `dispute` → `resolve` → refund) and
   ten adversarial cases; both are listed with explorer links in
   `scripts/e2e_results.md`, and every hash there was read back from the explorer's
   own JSON API first.

   1a. Previous deployments, still on-chain and verifiable:
   0xfD91f7eDCa653702ACe1F040F4d56d35e674c750 (v4 / D4, 2026-09-26),
   0x223323CE1b755313212FaD13016543C0E4E63E12 (audited v3 / D3) and
   0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D (v2 / D2).
   The v2 explorer shows the finalized transactions of four scenario runs on this
   address, including a live tamper demo: a deliberately wrong case-file hash was
   anchored, validators re-fetched and re-hashed the evidence, detected the mismatch,
   and refunded the client. Nothing was moved or rewritten when a new deployment came
   in. All four addresses are live, and each documented transaction says which one it
   ran on.

2. Browser wallet flow: the TRY A DISPUTE section on the site connects
   MetaMask/Rabby and signs open_deal and dispute from the visitor's own
   wallet, against the current v5 contract above. Every off-chain event the
   page records is signed by the connected address with `personal_sign`, and the
   dispute step seals the visitor's own log and anchors that head, so no extra
   step is needed to produce on-chain evidence. Every write returns its own
   explorer link. No shared private key, no silent gas.

3. Three verification paths on one page: explorer links; pytest tests/ -v
   (expect 105 passed: 50 off-chain plus 55 direct-mode contract tests); and a
   zero-install hash checker that reproduces the anchored SHA-256 in your
   browser, with a tamper toggle.

## Reproduce locally, end to end

    git clone https://github.com/hoveiser/flight-recorder && cd flight-recorder
    pip install -r requirements.txt && npm install
    pytest tests/ -v          # 105 passed (CI); 50 on Windows, direct mode needs Linux/macOS
    uvicorn src.main:app      # terminal 1: evidence service
    node scripts/e2e_demo.js  # terminal 2: full on-chain lifecycle

Reference runtime is Python 3.12 (CI); the deployed evidence API runs 3.10
(PythonAnywhere); the suite is green across the supported 3.10–3.14 range.

## Honest boundaries

- The v5 contract is deployed (D5, `0xc93007ac…`, 2026-10-10). D4 (`0xfD91f7…`)
  carried the audited v3 hardening (incl. F4 and F6) plus fixes for the three
  findings that survived it (F1, F2 and F3), and those are all still true of D5.
  F1, F2 and F3 stay closed; this round's audit findings are F16 to F24 in
  [AUDIT.md](AUDIT.md), with the severity, the evidence, the fix and the covering
  test named for each.
- What is still open, stated plainly: the contract compares the anchored chain head
  with the head the case file declares for itself. It does not recompute the chain
  from the events. D5 makes that head immutable, forces both parties to agree to one
  before any adjudication, and seals the log so it cannot grow afterwards, but a case
  file that lies about its own head consistently with the anchored digest still passes
  this gate (F5 and F23). Closing it means the contract hashing each link itself, which
  is the next round's work. Signatures prove *who wrote an event*, not that the event
  is true.
- Off-chain event recording is served live by the hosted evidence API at
  https://hreicher.pythonanywhere.com; the browser TRY A DISPUTE flow records
  through it. The hosted instance must be pulled and reloaded after this branch is
  merged, otherwise it still runs the pre-signing code and refuses nothing.
  Visitors whose network is geo-blocked by PythonAnywhere (HTTP 451) can still run the
  local Quick Start path (`uvicorn src.main:app`) for the same result.
- The browser demo anchors the repo happy_path case file, regenerated from a real
  recorder run by `demo/make_case_file.py`, with a definition_of_done that matches the
  deal's own agreement, so the deployed contract's agreement gate is cleared and the
  deal is adjudicated on the merits rather than refused as AGREEMENT_MISMATCH.
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
