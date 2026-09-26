# Judging Guide — Flight Recorder

A two-minute, fully verifiable overview for judges.

## What this is

Flight Recorder is a tamper-evident evidence layer for deals between AI
agents, paired with an on-chain intelligent contract that adjudicates
disputes with AI validators.

- Off-chain witness: every deal event is appended to a SHA-256 hash chain
  (FastAPI + SQLite). Any later edit breaks the chain visibly.
- On-chain judge: a GenLayer Intelligent Contract locks escrow at
  open_deal, anchors the case-file hash at dispute, re-fetches and
  re-hashes the served evidence during consensus, and pays the winner
  at finalize. No central arbiter.

## Live right now (click, don't trust)

1. Contract on GenLayer Studio Next, chain 61997:
   0xfD91f7eDCa653702ACe1F040F4d56d35e674c750
   This is the v4 deployment (D4, 2026-09-26): the audited v3 hardening (incl. F4/F6)
   plus the three findings that survived it — F1 (escrow is exactly gl.message.value,
   never caller-declared), F2 (an `unresolvable` deal is refunded by timeout_release
   once the appeal window closes), F3 (only a party can resolve) — and validator payload
   depth (resolve now sees the last ≤5 event payloads, not just counters). Its validation
   run is a full lifecycle — open_deal → dispute → resolve → refund — with the explorer
   transactions listed in `scripts/e2e_results.md`.

   1a. Previous deployment, still on-chain and verifiable:
   0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D
   The explorer shows the finalized transactions of four scenario runs on this address,
   including a live tamper demo: a deliberately wrong case-file hash was anchored,
   validators re-fetched and re-hashed the evidence, detected the mismatch, and
   refunded the client. One deal completed the whole lifecycle (open_deal →
   dispute → resolve → finalize); the other scenarios demonstrate the anchor and
   the early-timeout rejection. Superseded by 0x223323CE… (v3) on 2026-09-24, itself
   superseded by the current v4 (0xfD91f7…) on 2026-09-26; the evidence was not moved or
   rewritten — all three addresses are live and independently checkable.

2. Browser wallet flow: the TRY A DISPUTE section on the site connects
   MetaMask/Rabby and signs open_deal and dispute from the visitor's own
   wallet, against the current v4 contract above. Every write returns its own
   explorer link. No shared private key, no silent gas.

3. Three verification paths on one page: explorer links; pytest tests/ -v
   (expect 46 passed); and a zero-install hash checker that reproduces
   the anchored SHA-256 in your browser, with a tamper toggle.

## Reproduce locally, end to end

    git clone https://github.com/hoveiser/flight-recorder && cd flight-recorder
    pip install -r requirements.txt && npm install
    pytest tests/ -v          # 46 passed
    uvicorn src.main:app      # terminal 1: evidence service
    node scripts/e2e_demo.js  # terminal 2: full on-chain lifecycle

Reference runtime is Python 3.12 (CI); the deployed evidence API runs 3.10
(PythonAnywhere); the suite is green across the supported 3.10–3.14 range.

## Honest boundaries

- The v4 contract is deployed (D4, `0xfD91f7…`, 2026-09-26): the audited v3 hardening
  (incl. F4 and F6) plus fixes for the three findings that survived it — F1, F2 and F3.
  The v3 (`0x223323CE…`) and v2 (`0x8BC5…`) contracts remain on-chain, and the four v2
  scenario runs are still verifiable in the explorer; the deployment history in README
  spells out which evidence lives where. F1, F2 and F3 are now closed in the deployed
  contract; the remaining limitations are listed under Threat model in README.
- Off-chain event recording is served live by the hosted evidence API at
  https://hreicher.pythonanywhere.com; the browser TRY A DISPUTE flow records
  through it. Visitors whose network is geo-blocked by PythonAnywhere (HTTP 451)
  can still run the local Quick Start path (`uvicorn src.main:app`) for the same
  result.
- The browser demo now anchors the repo happy_path case file with a definition_of_done
  that matches the deal's own agreement, so the deployed contract's agreement gate is
  cleared and the deal is adjudicated on the merits rather than refused as
  AGREEMENT_MISMATCH. (Earlier the site's DOD did not match happy_path, so a resolve came
  back AGREEMENT_MISMATCH and refunded the client — that is what the D3 validation run
  shows.) The v2 deployment did not compare the two at all.
- Contract audit: findings, severities and the redeploy recommendation are in
  [AUDIT.md](AUDIT.md). Direct-mode tests require Linux/macOS (gltest cannot run
  its fd-0 message injection on Windows), so `pytest tests/` on Windows reports
  the 17 off-chain tests green and errors on the 29 direct ones; CI is the
  authoritative full run.
- Events are integrity-proofed, not signature-proofed; signed events are
  on the roadmap. Validators re-fetch the served bytes, so a tampered
  case file refunds the client automatically.
- No integrated faucet: visitors fund their own test transactions, which
  is why every on-chain row is a real, independently verifiable run.

## Why two layers

Evidence stays inspectable off-chain; consensus stays distributed
on-chain. The anchored hash and the served case file must agree, or the
deal does not settle. That intersection is the product.
