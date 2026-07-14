# Cancellation and Refund Policies

## General principles
Refund eligibility depends on the operator, fare conditions, cancellation time, and service status. Convenience fees, payment fees, and some promotional fares may be non-refundable. Policy guidance is not a live refund quote.

## DMOS safeguards
In this prototype, cancellations and refunds are simulated by deterministic booking and wallet agents. The conversational layer must call registered tools and may report success only when the tool returns success. It must never write directly to the wallet or booking databases.

## Disruptions
Operator-caused cancellations can have different rules from voluntary cancellation. Preserve booking references and receipts. When an itinerary is rebooked, the system reconciles the old and new simulated costs through the wallet ledger so every debit and refund remains auditable.
