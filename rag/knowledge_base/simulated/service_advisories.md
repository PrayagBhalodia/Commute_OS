---
title: Simulated Commute OS Service Advisories
category: service-advisories
region: India
operator: Commute OS simulation
source_url: repository://rag/knowledge_base/simulated/service_advisories.md
source_type: simulated-hackathon-data
license: project-generated
updated_at: 2026-07-15
retrieved_at: 2026-07-15
is_simulated: true
---
# Simulated Service Advisories

## Scope
These advisories exist only to exercise the hackathon disruption flow. They are not current transport status and must always be labelled simulated. Example conditions include a delayed train leg, a cancelled flight leg, a road closure, or unusually heavy rain affecting a ground transfer.

## Agent behavior
When a simulated disruption is triggered, preserve the original booking, identify the affected leg, generate compatible alternatives, compare the old and revised cost, and request approval when required by the autonomy policy.

## Financial reconciliation
Cancellation, rebooking, debit, and refund events must pass through the deterministic booking and wallet agents. A generated explanation does not change transaction state, and duplicate operations must remain blocked by idempotency controls.
