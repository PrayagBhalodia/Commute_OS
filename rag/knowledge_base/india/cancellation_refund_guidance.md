---
title: Cancellation and Refund Guidance
category: cancellation-refund-guidance
region: India
operator: Multiple transport operators
source_url: https://contents.irctc.co.in/en/eticketCancel.html
source_type: authoritative-source-summary
license: attributed-summary
updated_at: 2026-07-15
retrieved_at: 2026-07-15
is_simulated: false
---
# Cancellation and Refund Guidance

## Eligibility
Refund eligibility and deductions depend on the operator, fare conditions, booking status, cause of cancellation, and time remaining before travel. Operator-caused disruption can follow different rules from voluntary cancellation. Current conditions must be checked against the booked fare and operator policy.

## Safe transaction behavior
Policy retrieval is not a refund calculation or transaction. Commute OS must use booking and wallet tools for its simulated cancellation and reconciliation. It may report completion only after the tools return success, and it must preserve references and ledger entries for auditability.

## Timing
Refund processing can take longer than cancellation confirmation because payment providers and operators reconcile separately. The assistant should distinguish cancellation accepted, refund initiated, and refund received rather than treating them as the same state.
