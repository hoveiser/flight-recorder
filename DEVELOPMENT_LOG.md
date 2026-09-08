# Development Log — Flight Recorder

## Project intent

This project is being built as a GenLayer-aligned MVP in the Onchain Justice track.

The core idea is:

- record evidence in a tamper-evident way
- create a dispute workflow from that evidence
- verify integrity of the chain
- prepare the settlement layer for final adjudication

This is not yet a fully autonomous on-chain justice system; it is a disciplined MVP path toward that model.

---

## Milestone Roadmap

### Milestone 1 — Foundation and Core Evidence Layer

Status: Completed

Goal:

- establish the repository structure
- set up CI and local app infrastructure
- build a tamper-evident event log

Completed work:

- repo initialized with FastAPI + SQLite
- Pydantic models created
- hashing logic implemented in hash_chain.py
- db layer built for deals and events
- endpoints created for deals and event recording
- CI workflow added
- initial test suite passed

Validation:

- pytest green for the evidence layer
- integrity of event chain verified

Key output:

- append-only evidence log with hash chaining

---

### Milestone 2 — Dispute Workflow and Case File

Status: Completed

Goal:

- allow a dispute claim to be filed against a deal
- package evidence into a case file for later review

Completed work:

- disputes table and logic implemented
- create dispute endpoint added
- case file export assembled from chain + dispute metadata
- verification helper used for built-in integrity checking
- tests expanded for dispute/case-file behavior

Validation:

- dispute creation tested
- case file generation tested
- tamper detection and unlink detection validated

Key output:

- a dispute-ready evidence package that can be handed to an adjudicator or settlement layer

---

### Milestone 3 — Demo Scenarios and Product Framing

Status: Completed

Goal:

- show realistic examples of the product in use
- make the project understandable outside the codebase

Completed work:

- scraper dispute demo added
- code quality dispute demo added
- local scenario simulations prepared for use through the API

Validation:

- demo scripts compile successfully
- scenarios run locally against the app

Key output:

- real-world examples that explain the product in a hackathon context

---

### Milestone 4 — Settlement / Adjudication Contract

Status: In progress

Goal:

- formalize the settlement decision layer as a direct-mode contract test flow
- prepare the system for real adjudication logic instead of only local evidence review

Current work:

- settlement contract being implemented
- direct mode tests being added
- logic expected to interpret dispute evidence and enforce final decision state

Validation target:

- direct-mode contract tests pass
- settlement logic is deterministic and explainable

Key output:

- a minimal adjudication contract that can sit beside or on top of the evidence layer

---

## Day-by-Day Record

### Day 1

Objective:

- establish the foundation and evidence recording flow

Done:

- repo setup
- FastAPI app scaffolded
- SQLite persistence designed
- deal/event models created
- hash chain introduced
- initial verification implemented
- first test suite passed

Result:

- the project had a valid evidence backbone and tamper-evident record structure

---

### Day 2

Objective:

- add dispute handling and case file generation

Done:

- dispute endpoint added
- case file builder added
- dispute tables integrated
- verification logic improved
- tests expanded to include dispute and chain break behavior

Result:

- the project could now file and export a dispute case from the event chain

---

### Day 3

Objective:

- validate the concept with realistic demos

Done:

- scraper-based dispute scenario
- code-quality dispute scenario
- local integration examples for product storytelling

Result:

- concept became understandable, concrete, and demo-friendly

---

### Day 4 (today)

Objective:

- advance from evidence/dispute workflow into settlement logic

Done so far:

- settlement contract path is now in focus
- direct-mode contract tests are being added
- core idea is moving from local evidence validation to adjudication logic

Current bottleneck:

- the system still sits mostly in a local/off-chain evidence layer
- the settlement decision must be explicitly framed as the next step, not as a finished claim

Expected finish for today:

- settlement contract logic implemented
- direct-mode tests written and passing
- daily log updated with actual validation status

---

## Guardrails for the project

These are the most important things to keep in mind while moving forward.

### 1) Keep the boundary honest

Do not overclaim that the project is already a full on-chain justice system if the current implementation is still mostly local evidence processing and dispute recording.

The correct framing is:

- evidence integrity layer: built
- dispute workflow: built
- on-chain adjudication foundation: in progress

### 2) Keep the source of truth explicit

There must be a clear distinction between:

- evidence record
- dispute record
- settlement decision
- final adjudication result

This matters for both technical design and hackathon narrative.

### 3) Validate early, validate often

Each milestone should end with a concrete output:

- API test passes
- chain integrity passes
- case file exports correctly
- direct-mode settlement tests pass

### 4) The product story matters as much as the code

For submission, the project needs:

- a short architecture explanation
- a clean README
- a clear demo flow
- a simple story for why this matters in GenLayer

### 5) Do not confuse local proofs with final settlement

A hash chain proves tamper evidence.
It does not automatically equal a final, socially or cryptographically enforced verdict.
The settlement layer is the bridge from evidence to adjudication.

---

## Daily Working Template

Use this format for future updates:

### Day X

- Goal:
- Done:
- Validation:
- Blocker / risk:
- Next step:

---

## Completion Target for Today

By the end of Day 4, the project should ideally have:

- [ ] settlement contract logic implemented
- [ ] direct-mode tests passing
- [ ] current architecture documented honestly
- [ ] all major milestone updates recorded in this log
- [ ] next-day deliverables clearly listed

---

## Summary

The project has already passed the first three key milestones:

- foundation
- evidence recording
- dispute and case-file logic

Today is the transition point into the fourth milestone:

- settlement / adjudication contract and validation

This is a correct and healthy progression for the Onchain Justice track.
