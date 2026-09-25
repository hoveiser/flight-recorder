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
   0x223323CE1b755313212FaD13016543C0E4E63E12
   This is the audited v3 deployment: it carries the settlement hardening plus audit
   patches F4 (anchor cannot be overwritten) and F6 (agreement digest accepted in both
   the Python and the browser canonical form). Its validation run is a full lifecycle —
   open_deal → dispute → resolve → refund — with the explorer transactions listed in
   `scripts/e2e_results.md`.

   1a. Previous deployment, still on-chain and verifiable:
   0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D
   The explorer shows the finalized transactions of four scenario runs on this address,
   including a live tamper demo: a deliberately wrong case-file hash was anchored,
   validators re-fetched and re-hashed the evidence, detected the mismatch, and
   refunded the client. One deal completed the whole lifecycle (open_deal →
   dispute → resolve → finalize); the other scenarios demonstrate the anchor and
   the early-timeout rejection. Superseded by 0x223323CE… on 2026-09-24; the evidence
   was not moved or rewritten — both addresses are live and independently checkable.

2. Browser wallet flow: the TRY A DISPUTE section on the site connects
   MetaMask/Rabby and signs open_deal and dispute from the visitor's own
   wallet, against the current audited contract above. Every write returns its own
   explorer link. No shared private key, no silent gas.

3. Three verification paths on one page: explorer links; pytest tests/ -v
   (expect 37 passed); and a zero-install hash checker that reproduces
   the anchored SHA-256 in your browser, with a tamper toggle.

## Reproduce locally, end to end

    git clone https://github.com/hoveiser/flight-recorder && cd flight-recorder
    pip install -r requirements.txt && npm install
    pytest tests/ -v          # 37 passed
    uvicorn src.main:app      # terminal 1: evidence service
    node scripts/e2e_demo.js  # terminal 2: full on-chain lifecycle

Reference runtime is Python 3.12 (CI); the deployed evidence API runs 3.10
(PythonAnywhere); the suite is green across the supported 3.10–3.14 range.

## Honest boundaries

- The v3 contract is deployed (D3, `0x223323CE…`, 2026-09-24) and carries audit patches
  F4 and F6. The v2 contract remains on-chain, and its four scenario runs are still
  verifiable in the explorer; the deployment history in README spells out which
  evidence lives where. Audit findings F1, F2 and F3 are still open in the deployed
  contract and are listed under Threat model in README.
- Off-chain event recording is served live by the hosted evidence API at
  https://hreicher.pythonanywhere.com; the browser TRY A DISPUTE flow records
  through it. Visitors whose network is geo-blocked by PythonAnywhere (HTTP 451)
  can still run the local Quick Start path (`uvicorn src.main:app`) for the same
  result.
- The browser demo anchors the repo happy_path case file while the deal's own
  agreement is `demo delivery`. The **deployed contract now compares the two**, so
  resolving such a deal refuses on the merits with AGREEMENT_MISMATCH and refunds the
  client — that is exactly what the D3 validation run shows. The previous v2 deployment
  did not compare them and would have adjudicated the case file's own terms.
- Contract audit: findings, severities and the redeploy recommendation are in
  [AUDIT.md](AUDIT.md). Direct-mode tests require Linux/macOS (gltest cannot run
  its fd-0 message injection on Windows), so `pytest tests/` on Windows reports
  the 15 off-chain tests green and errors on the 22 direct ones; CI is the
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
