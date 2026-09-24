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
   0x8BC572Bec7EAA3C6662a9da3E38b4233a35bF97D
   The explorer shows four finalized lifecycle runs, including a live
   tamper demo: a deliberately wrong case-file hash was anchored,
   validators re-fetched and re-hashed the evidence, detected the
   mismatch, and refunded the client.

2. Browser wallet flow: the TRY A DISPUTE section on the site connects
   MetaMask/Rabby and signs open_deal and dispute from the visitor's own
   wallet. Every write returns its own explorer link. No shared private
   key, no silent gas.

3. Three verification paths on one page: explorer links; pytest tests/ -v
   (expect 34 passed); and a zero-install hash checker that reproduces
   the anchored SHA-256 in your browser, with a tamper toggle.

## Reproduce locally, end to end

    git clone https://github.com/hoveiser/flight-recorder && cd flight-recorder
    pip install -r requirements.txt && npm install
    pytest tests/ -v          # 34 passed
    uvicorn src.main:app      # terminal 1: evidence service
    node scripts/e2e_demo.js  # terminal 2: full on-chain lifecycle

Reference runtime is Python 3.12 (CI); the deployed evidence API runs 3.10
(PythonAnywhere); the suite is green across the supported 3.10–3.14 range.

## Honest boundaries

- v3/v4 contract hardening is merged and covered by the direct-mode suite
  but deliberately not redeployed, so the on-chain evidence stays one
  continuous history (see Deployment history in README).
- Off-chain event recording is served live by the hosted evidence API at
  https://hreicher.pythonanywhere.com; the browser TRY A DISPUTE flow records
  through it. Visitors whose network is geo-blocked by PythonAnywhere (HTTP 451)
  can still run the local Quick Start path (`uvicorn src.main:app`) for the same
  result.
- The browser demo anchors the repo happy_path case file while the deal's own
  agreement is `demo delivery`, so a future resolve of such a browser deal would
  verdict AGREEMENT_MISMATCH — a client refund — rather than adjudicate the
  merits.
- Events are integrity-proofed, not signature-proofed; signed events are
  on the roadmap. Validators re-fetch the served bytes, so a tampered
  case file refunds the client automatically.
- No integrated faucet: visitors fund their own test transactions, which
  is why every on-chain row is a real, independently verifiable run.

## Why two layers

Evidence stays inspectable off-chain; consensus stays distributed
on-chain. The anchored hash and the served case file must agree, or the
deal does not settle. That intersection is the product.
