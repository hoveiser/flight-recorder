# Flight Recorder

**A tamper-evident evidence layer + on-chain settlement for agent-to-agent deals.**

Built for the [Agent Tank Hackathon](https://agenttank.com) — Onchain Justice track.

> *"GenEscrow is the judge. Flight Recorder is the black box no one can deny."*

## The Problem

When two agents do business together, disputes happen. But without neutral evidence, resolution depends on who's louder — not who's right.

**Flight Recorder** solves this by recording every event (requests, responses, deliveries, validations) into a hash-chained log that can't be tampered with. When a dispute happens, the **case file** becomes evidence for on-chain adjudication.

**Settlement** is a GenLayer Intelligent Contract that acts as the judge: it reads the case file, verifies its integrity, and uses AI validators to reach a verdict.

## Architecture

**Off-Chain (Flight Recorder):**
- FastAPI + SQLite
- Hash chain (tamper-evident)
- Case file export (GenLayer-ready JSON)

**On-Chain (Settlement):**
- open_deal: lock escrow with agreement hash
- dispute: file dispute with case file hash
- resolve: AI validators adjudicate
- finalize: pay winner based on verdict

**Flow:** Agent creates deal → records events → files dispute → exports case file → Settlement contract reads case file → AI validators reach verdict → payment/refund executed.

### Key Principles

| Layer | Role | Source of Truth |
|-------|------|-----------------|
| Flight Recorder (off-chain) | Evidence witness | Hash chain + case file |
| Settlement (on-chain) | Judge + escrow | Contract state + validator consensus |

**Why off-chain evidence?** Raw payloads are too large for on-chain storage. The hash chain provides tamper evidence; on-chain anchors provide public proof.

**Why on-chain settlement?** Payment requires trustless execution. GenLayer's AI validators provide neutral adjudication without trusting any single party.

## Features

### Off-Chain (Flight Recorder API)

- **Deal creation** with definition-of-done and agreement hash
- **Event recording** into append-only hash chain
- **Hash verification** (tamper detection)
- **Dispute filing** by deal parties
- **Case file export** (GenLayer-ready JSON)

### On-Chain (Settlement Contract)

- **Escrow**: open_deal locks funds with agreement hash
- **Milestone anchoring**: anchor_milestone records chain heads on-chain
- **Dispute filing**: dispute submits case file hash
- **AI adjudication**: resolve uses GenLayer validators to reach verdict
- **Appeal process**: appeal allows loser to contest
- **Finalization**: finalize pays winner based on verdict
- **Timeout release**: timeout_release auto-pays if no dispute

## Quick Start

### 1. Off-Chain Service

    pip install -r requirements.txt
    uvicorn src.main:app --reload

API docs: http://localhost:8000/docs

### 2. Run Tests

    pytest tests/ -v

### 3. Run Demos

    python demo/scraper_dispute.py
    python demo/code_quality_dispute.py

## API Reference

### Off-Chain Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /deals | Create a deal with definition-of-done |
| GET | /deals/{deal_id} | Get deal details |
| POST | /events | Record an event into the hash chain |
| GET | /deals/{deal_id}/events | Get all events for a deal |
| GET | /deals/{deal_id}/verify | Verify hash chain integrity |
| POST | /deals/{deal_id}/dispute | File a dispute (parties only) |
| GET | /deals/{deal_id}/disputes | Get all disputes |
| GET | /deals/{deal_id}/case-file | Export case file for adjudication |

### Event Types

| Type | Description |
|------|-------------|
| REQUEST | Client sends request |
| RESPONSE | Worker responds |
| DELIVERY | Worker delivers |
| VALIDATION | Client validates |
| STATE_CHANGE | Status change |
| WARNING | Warning event |
| ERROR | Error event |
| PAYMENT_INTENT | Payment intent |
| CUSTOM | Custom event |

### On-Chain Contract Methods

| Method | Type | Description |
|--------|------|-------------|
| open_deal | write.payable | Lock escrow with agreement hash |
| anchor_milestone | write | Record chain head on-chain |
| dispute | write | File dispute with case file hash |
| resolve | write | AI validators adjudicate |
| appeal | write | Loser contests verdict |
| finalize | write | Pay winner |
| timeout_release | write | Auto-pay after timeout |
| get_deal | view | Get deal state |
| get_payouts | view | Get payout history |

### Verdict Types

| Verdict | Meaning | Winner |
|---------|---------|--------|
| APPROVED | Worker fulfilled agreement | Worker gets paid |
| REFUNDED | Worker failed to deliver | Client gets refund |
| EVIDENCE_MISMATCH | Case file was tampered | Client gets refund |
| UNRESOLVABLE | Too many failed attempts | No payout |
| TIMEOUT | No dispute filed | Worker gets paid |

## Hash Chain

Each event is linked to the previous one:

    Event 1: previous = GENESIS
    Event 2: previous = Event 1's hash
    Event 3: previous = Event 2's hash

**Tamper detection:**
- Modify any payload → hash chain breaks → verify returns FAIL
- Delete any event → chain has gap → verify returns FAIL

## Case File Format

    {
      "deal_id": "scraper_deal_001",
      "definition_of_done": {"success_criteria": "1000 valid records"},
      "parties": ["agentA", "agentB"],
      "agreement_hash": "sha256...",
      "events": [...],
      "disputes": [...],
      "chain_integrity": {
        "verification": "PASS",
        "events": 5
      }
    }

## Project Structure

    flight-recorder/
    ├── src/                      # Off-chain evidence service
    │   ├── main.py               # FastAPI app
    │   ├── models.py             # Pydantic models
    │   ├── hash_chain.py         # SHA-256 hash chain logic
    │   └── db.py                 # SQLite database
    ├── contracts/
    │   └── settlement.py         # GenLayer Intelligent Contract
    ├── tests/
    │   ├── test_flight_recorder.py  # Off-chain tests (9 tests)
    │   └── test_settlement.py    # On-chain tests (5 tests)
    ├── demo/
    │   ├── scraper_dispute.py
    │   └── code_quality_dispute.py
    └── README.md

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Off-chain API | FastAPI + SQLite |
| On-chain contract | GenLayer SDK v0.2.16 |
| Testing | pytest + genlayer-test (Direct Mode) |
| CI | GitHub Actions |

## License

MIT