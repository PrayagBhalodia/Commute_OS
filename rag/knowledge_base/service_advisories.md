# Service Advisories

## Scope
This document explains how to handle advisories; it does not contain live service status. Timetables, platform changes, traffic, weather, strikes, closures, prices, and seat availability are time-sensitive and must not be stored as durable RAG facts.

## Verification
Use an approved live operator or transport data source when one is configured. Identify the source and observation time. If no live source is available, state that limitation and avoid presenting historical guidance as current status.

## Response
When a disruption is reported, preserve the original booking state, identify the affected leg, generate alternatives through the deterministic orchestrator, and request approval where required. Refunds and rebooking must pass through the booking and wallet agents.
