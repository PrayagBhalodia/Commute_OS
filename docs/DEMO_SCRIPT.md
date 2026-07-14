# Conversational DMOS Demo

## Preparation

~~~powershell
.\.venv\Scripts\python.exe -m rag.ingest
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000/docs.

## Walkthrough

1. Call POST /chat/message:

   ~~~json
   {
     "user_id": "demo-chat",
     "message": "Plan a trip from Ahmedabad to Jio Institute tomorrow with one suitcase. Prefer the fastest route."
   }
   ~~~

2. Point out the ranked options, compact state, and safe journey_planned and
   waiting_for_consent events. No booking has occurred.

3. Ask a policy question using the returned session_id:

   ~~~json
   {
     "session_id": "RETURNED_SESSION_ID",
     "user_id": "demo-chat",
     "message": "How early should I reach the airport and what about baggage?"
   }
   ~~~

4. Show local citations from the airport and baggage knowledge documents.

5. Select an option with the message: Select option 1.

6. Demonstrate the approval boundary with a non-consenting message. The wallet
   and booking records remain unchanged.

7. Top up the simulated wallet explicitly: Top up INR 10000.

8. Book explicitly: Confirm booking. Only now does the deterministic booking
   tool execute.

9. Repeat Confirm booking and show that the duplicate is blocked.

10. Retrieve and delete the session with the session endpoints.

## Disclaimer

All operator inventory, bookings, top-ups, debits, refunds, disruptions, and
reconciliation in this demo are simulated. No real transport booking or
financial transaction occurs.
