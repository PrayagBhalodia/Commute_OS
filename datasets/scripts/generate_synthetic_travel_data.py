"""Deterministically generate Commute OS English/Hinglish training examples."""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

from datasets.scripts.common import SYSTEM_MESSAGE, validate_record, write_jsonl


WORKFLOWS: list[dict[str, Any]] = [
    {"key": "local_commute", "intent": "journey_planning", "en": "Plan my commute from Andheri to BKC for 9 AM, fastest route.", "hi": "Kal 9 baje tak Andheri se BKC pahuchna hai, fastest route batao.", "reply_en": "I have the route and deadline. I will compare the fastest valid options.", "reply_hi": "Route aur deadline mil gaya. Main fastest valid options compare karta hoon.", "tool": "plan_journey", "slots": {"origin": "Andheri", "destination": "BKC", "appointment_time": "tomorrow 09:00", "priority": "time"}},
    {"key": "school", "intent": "journey_planning", "en": "I need to take my child from Powai to school, but I have not decided which branch.", "hi": "Powai se bacche ko school le jana hai, par kaunsi branch decide nahi hai.", "reply_en": "Which school branch should I use as the destination?", "reply_hi": "Destination ke liye kaunsi school branch use karun?", "action": "ask_clarifying_question", "missing": ["destination"]},
    {"key": "office", "intent": "journey_planning", "en": "Get me from Koramangala to Electronic City before 10 AM.", "hi": "Koramangala se Electronic City 10 baje se pehle pahucha do.", "reply_en": "Would you like the fastest, cheapest, or most comfortable route?", "reply_hi": "Fastest, cheapest, ya comfortable route mein kya prefer karoge?", "action": "ask_clarifying_question", "slots": {"origin": "Koramangala", "destination": "Electronic City", "appointment_time": "10:00"}, "missing": ["priority"]},
    {"key": "airport", "intent": "airport_transfer", "en": "Plan home to Mumbai Airport for a 6 PM flight with one suitcase.", "hi": "Ghar se Mumbai Airport jana hai 6 PM flight ke liye, ek suitcase hai.", "reply_en": "Should I use your current location for home or would you like to enter it?", "reply_hi": "Home ke liye current location use karun ya aap manually enter karoge?", "action": "ask_location_choice", "slots": {"destination": "Mumbai Airport", "luggage_count": 1}, "missing": ["origin"]},
    {"key": "interstate", "intent": "journey_planning", "en": "Show options from Ahmedabad to Mumbai tomorrow.", "hi": "Kal Ahmedabad se Mumbai jane ke saare options dikhao.", "reply_en": "I will compare valid road, rail, and flight combinations.", "reply_hi": "Main road, train aur flight ke valid combinations compare karta hoon.", "tool": "plan_journey", "slots": {"origin": "Ahmedabad", "destination": "Mumbai", "appointment_time": "tomorrow"}},
    {"key": "international", "intent": "journey_planning", "en": "I have an international flight from Delhi but did not mention the departure time.", "hi": "Delhi se international flight hai, departure time abhi nahi bataya.", "reply_en": "What is the flight departure date and time?", "reply_hi": "Flight ka departure date aur time kya hai?", "action": "ask_clarifying_question", "missing": ["appointment_time"]},
    {"key": "return", "intent": "journey_planning", "en": "Ahmedabad to Jio Institute tomorrow, and keep the return on the same day.", "hi": "Kal Ahmedabad se Jio Institute jana hai, return bhi same day rakhna.", "reply_en": "I will include a same-day return while comparing the options.", "reply_hi": "Options compare karte waqt same-day return bhi include karunga.", "tool": "plan_journey", "slots": {"origin": "Ahmedabad", "destination": "Jio Institute", "return_required": True}},
    {"key": "group", "intent": "journey_planning", "en": "We are four people travelling from Pune to Mumbai.", "hi": "Hum chaar log Pune se Mumbai travel kar rahe hain.", "reply_en": "I will search with four passengers and show suitable options.", "reply_hi": "Main four passengers ke hisaab se suitable options dikhaunga.", "tool": "plan_journey", "slots": {"origin": "Pune", "destination": "Mumbai", "passenger_count": 4}},
    {"key": "elderly", "intent": "journey_planning", "en": "I am travelling with my parents; avoid too many transfers.", "hi": "Parents ke saath travel kar raha hoon, zyada transfers mat rakhna.", "reply_en": "What are the origin and destination? I will prioritize fewer transfers and comfort.", "reply_hi": "Origin aur destination batao; main fewer transfers aur comfort prioritize karunga.", "action": "ask_clarifying_question", "missing": ["origin", "destination"]},
    {"key": "accessibility", "intent": "accessibility_request", "en": "I need a wheelchair-accessible journey from Delhi Airport to Connaught Place.", "hi": "Delhi Airport se Connaught Place wheelchair accessible journey chahiye.", "reply_en": "I will prioritize accessible transfers, but operator assistance must be verified before travel.", "reply_hi": "Main accessible transfers prioritize karunga, lekin operator assistance travel se pehle verify karni hogi.", "tool": "plan_journey", "slots": {"origin": "Delhi Airport", "destination": "Connaught Place", "accessibility": "wheelchair"}},
    {"key": "children", "intent": "journey_planning", "en": "Two adults and two children need to reach Bengaluru Airport by 5 AM.", "hi": "Do adults aur do bacchon ko Bengaluru Airport 5 AM tak pahuchna hai.", "reply_en": "Where will the journey start?", "reply_hi": "Journey kahan se start hogi?", "action": "ask_clarifying_question", "missing": ["origin"]},
    {"key": "luggage", "intent": "journey_planning", "en": "I have two suitcases from Ahmedabad to Mumbai Airport.", "hi": "Ahmedabad se Mumbai Airport jana hai aur do suitcases hain.", "reply_en": "I will include two bags when composing the journey.", "reply_hi": "Journey compose karte waqt do bags include karunga.", "tool": "plan_journey", "slots": {"origin": "Ahmedabad", "destination": "Mumbai Airport", "luggage_count": 2}},
    {"key": "cheapest", "intent": "journey_planning", "en": "Show the cheapest way from Pune to Hyderabad.", "hi": "Pune se Hyderabad ka sabse sasta option batao.", "reply_en": "I will rank valid options by cost.", "reply_hi": "Main valid options ko cost ke hisaab se rank karta hoon.", "tool": "plan_journey", "slots": {"origin": "Pune", "destination": "Hyderabad", "priority": "cost"}},
    {"key": "fastest", "intent": "journey_planning", "en": "I need to reach quickly; spending a little more is fine.", "hi": "Jaldi pahuchna hai, paise thode zyada chalenge.", "reply_en": "What are your origin and destination?", "reply_hi": "Aapka origin aur destination kya hai?", "action": "ask_clarifying_question", "slots": {"priority": "time"}, "missing": ["origin", "destination"]},
    {"key": "safest", "intent": "journey_planning", "en": "Find a safer late-night route from Delhi Airport to Noida.", "hi": "Delhi Airport se Noida ka safer late-night route dekho.", "reply_en": "I will compare recognized operators and minimize isolated transfers.", "reply_hi": "Main recognized operators compare karke isolated transfers kam rakhunga.", "tool": "plan_journey", "slots": {"origin": "Delhi Airport", "destination": "Noida", "priority": "safety"}},
    {"key": "eco", "intent": "journey_planning", "en": "Prefer metro or train for a lower-impact journey from Delhi to Gurgaon.", "hi": "Delhi se Gurgaon ke liye metro ya train wala eco-friendly route chahiye.", "reply_en": "I will prioritize rail-based options where the route supports them.", "reply_hi": "Jahan possible hoga main rail-based options prioritize karunga.", "tool": "plan_journey", "slots": {"origin": "Delhi", "destination": "Gurgaon", "priority": "eco"}},
    {"key": "comfortable", "intent": "journey_planning", "en": "Comfort matters more than saving a few hundred rupees.", "hi": "Kuch hundred rupees bachane se zyada comfort important hai.", "reply_en": "Tell me the origin and destination so I can compare comfortable options.", "reply_hi": "Origin aur destination batao, phir comfortable options compare karunga.", "action": "ask_clarifying_question", "slots": {"priority": "comfort"}, "missing": ["origin", "destination"]},
    {"key": "missed_connection", "intent": "disruption", "en": "I missed my connection; find the next valid route.", "hi": "Connection miss ho gaya, next valid route dekho.", "reply_en": "I will inspect the active trip and generate alternatives without changing the booking yet.", "reply_hi": "Main active trip check karke alternatives banaunga, booking abhi change nahi hogi.", "tool": "trigger_disruption", "slots": {"reason": "missed_connection"}},
    {"key": "flight_cancel", "intent": "disruption", "en": "My flight was cancelled. What will you do now?", "hi": "Flight cancel ho gayi toh ab kya karoge?", "reply_en": "I will preserve the original booking, generate alternatives, and explain any cost change before approval.", "reply_hi": "Main original booking preserve karke alternatives aur cost change approval se pehle explain karunga.", "tool": "trigger_disruption", "slots": {"reason": "flight_cancelled"}},
    {"key": "train_delay", "intent": "disruption", "en": "The train is late; check an alternative.", "hi": "Train late hai, alternate dekho.", "reply_en": "I will check alternatives for the affected leg and will not rebook without the required approval.", "reply_hi": "Affected leg ke alternatives check karunga aur required approval ke bina rebook nahi karunga.", "tool": "trigger_disruption", "slots": {"reason": "train_delay"}},
    {"key": "road_closure", "intent": "disruption", "en": "The airport road is closed; reroute me.", "hi": "Airport road band hai, mujhe reroute karo.", "reply_en": "I will generate a revised route and keep the original booking state auditable.", "reply_hi": "Main revised route banaunga aur original booking state auditable rahegi.", "tool": "trigger_disruption", "slots": {"reason": "road_closure"}},
    {"key": "heavy_rain", "intent": "disruption", "en": "Heavy rain may delay my airport transfer.", "hi": "Heavy rain ki wajah se airport transfer delay ho sakta hai.", "reply_en": "I can add contingency and replan, but current weather must come from a live source.", "reply_hi": "Main contingency add karke replan kar sakta hoon, current weather live source se aayega.", "tool": "trigger_disruption", "slots": {"reason": "heavy_rain"}},
    {"key": "wallet_low", "intent": "wallet", "en": "My wallet balance is insufficient for this journey.", "hi": "Is journey ke liye wallet balance kam hai.", "reply_en": "I can check the balance and explain the shortfall; I will not top up without an amount and approval.", "reply_hi": "Main balance aur shortfall bata sakta hoon; amount aur approval ke bina top-up nahi hoga.", "tool": "get_wallet_balance", "slots": {}},
    {"key": "refund", "intent": "refund_policy", "en": "How will my refund work after cancellation?", "hi": "Cancellation ke baad refund kaise milega?", "reply_en": "I will retrieve the applicable guidance. A refund is complete only when the cancellation and wallet tools succeed.", "reply_hi": "Main applicable guidance retrieve karunga. Refund tabhi complete hai jab cancellation aur wallet tools success dein.", "tool": "search_knowledge", "slots": {"category": "cancellation-refund-guidance"}},
    {"key": "booking_consent", "intent": "booking", "en": "I reviewed the final journey. Confirm booking and debit the wallet.", "hi": "Final journey review kar liya. Booking confirm karo aur wallet debit karo.", "reply_en": "I will submit the confirmed itinerary once and report the tool result.", "reply_hi": "Main confirmed itinerary ek baar submit karke tool result bataunga.", "tool": "confirm_booking", "consent": True, "state": "confirmed", "slots": {"user_confirmed": True}},
    {"key": "booking_no_consent", "intent": "booking", "en": "That route looks okay.", "hi": "Ye route theek lag raha hai.", "reply_en": "Nothing is booked yet. Please explicitly confirm if you approve the journey and wallet debit.", "reply_hi": "Abhi booking nahi hui. Journey aur wallet debit approve ho toh explicitly confirm karo.", "action": "ask_booking_consent", "consent": True, "state": "waiting_for_consent"},
    {"key": "manual", "intent": "autonomy", "en": "Keep everything manual and ask before every booking change.", "hi": "Sab manual rakho aur har booking change se pehle pucho.", "reply_en": "Manual mode selected. I will present options and wait for explicit approval.", "reply_hi": "Manual mode selected. Main options dikha kar explicit approval ka wait karunga.", "action": "update_autonomy", "slots": {"autonomy": "manual"}},
    {"key": "smart", "intent": "autonomy", "en": "Use smart approval but ask before spending money.", "hi": "Smart approval use karo, par paise spend karne se pehle puchna.", "reply_en": "Smart approval selected. Financial actions still require your explicit approval.", "reply_hi": "Smart approval selected. Financial actions ke liye explicit approval phir bhi chahiye.", "action": "update_autonomy", "slots": {"autonomy": "smart_approval"}},
    {"key": "full_auto", "intent": "autonomy", "en": "Use full-auto for disruptions, but do not book this new trip yet.", "hi": "Disruptions ke liye full-auto use karo, par nayi trip abhi book mat karna.", "reply_en": "Full-auto disruption handling is selected. New bookings still require explicit consent.", "reply_hi": "Full-auto disruption handling selected. New booking ke liye explicit consent phir bhi chahiye.", "action": "update_autonomy", "slots": {"autonomy": "full_auto"}},
    {"key": "policy", "intent": "policy_question", "en": "How early should I reach the airport with checked baggage?", "hi": "Checked baggage ke saath airport kitna early pahuchna chahiye?", "reply_en": "I will retrieve airport and baggage guidance and cite the sources.", "reply_hi": "Main airport aur baggage guidance sources ke saath retrieve karunga.", "tool": "search_knowledge", "slots": {"category": "airport-transfer-guidance"}},
    {"key": "unsupported", "intent": "unsupported", "en": "Can you renew my passport?", "hi": "Kya tum mera passport renew kar sakte ho?", "reply_en": "I cannot renew passports. I can help plan travel to the relevant office or explain the next journey step.", "reply_hi": "Main passport renew nahi kar sakta. Relevant office tak journey plan karne mein help kar sakta hoon.", "action": "safe_unsupported_response"},
    {"key": "ambiguous_place", "intent": "journey_planning", "en": "Take me from MG Road to the airport.", "hi": "MG Road se airport le chalo.", "reply_en": "Which city is MG Road in, and which airport do you mean?", "reply_hi": "MG Road kaunsi city mein hai aur kaunsa airport chahiye?", "action": "ask_clarifying_question", "missing": ["origin_city", "destination_airport"]},
    {"key": "invalid_deadline", "intent": "journey_planning", "en": "Reach Mumbai yesterday at 9 AM.", "hi": "Mumbai kal se pehle 9 AM pahuchna tha.", "reply_en": "That deadline is in the past. What future date and time should I use?", "reply_hi": "Ye deadline past mein hai. Kaunsa future date aur time use karun?", "action": "ask_valid_deadline", "missing": ["appointment_time"]},
    {"key": "no_route", "intent": "journey_planning", "en": "No route was found for my constraints.", "hi": "Mere constraints ke liye koi route nahi mila.", "reply_en": "I can relax the deadline, mode, or transfer constraints. Which one may I change?", "reply_hi": "Deadline, mode, ya transfer constraints relax kar sakta hoon. Kya change karun?", "action": "offer_constraint_relaxation", "state": "needs_input"},
    {"key": "partial_failure", "intent": "booking_failure", "en": "The first leg booked but the second leg failed.", "hi": "Pehla leg book ho gaya par second leg fail ho gaya.", "reply_en": "I will preserve confirmations, stop duplicate charges, reconcile the wallet, and present recovery options.", "reply_hi": "Main confirmations preserve karke duplicate charges rokunga, wallet reconcile karke recovery options dikhaunga.", "action": "explain_partial_failure", "state": "reconciliation_required"},
    {"key": "reconcile", "intent": "disruption", "en": "Reroute the cancelled leg and explain the price difference.", "hi": "Cancelled leg ko reroute karo aur price difference samjhao.", "reply_en": "I will generate alternatives and show the old cost, new cost, and wallet adjustment before approval.", "reply_hi": "Main alternatives ke saath old cost, new cost aur wallet adjustment approval se pehle dikhaunga.", "tool": "trigger_disruption", "slots": {"reason": "cancelled_leg"}},
]


def _tool(name: str | None, slots: dict[str, Any]) -> dict[str, Any] | None:
    if not name:
        return None
    arguments: dict[str, Any] = {"user_id": "user-example"}
    if name == "plan_journey":
        arguments.update({
            "goal_text": "See user message",
            "origin": slots.get("origin"),
            "destination": slots.get("destination"),
            "appointment_time": slots.get("appointment_time"),
            "return_required": slots.get("return_required"),
            "passenger_count": slots.get("passenger_count", 1),
            "luggage_count": slots.get("luggage_count", 0),
            "max_options": 5,
        })
        arguments = {key: value for key, value in arguments.items() if value is not None}
    elif name == "confirm_booking":
        arguments.update({"trip_id": "trip-example", "itinerary_id": "itin-example", "user_confirmed": True})
    elif name == "trigger_disruption":
        arguments.update({"trip_id": "trip-example", "reason": slots.get("reason", "reported_disruption"), "severity": "medium", "auto_rebook": False})
    elif name == "search_knowledge":
        arguments = {"query": "See user message", "category": slots.get("category"), "top_k": 4}
        arguments = {key: value for key, value in arguments.items() if value is not None}
    return {"name": name, "arguments": arguments}


def generate_records(variants: int = 2) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for workflow in WORKFLOWS:
        for language, user_key, reply_key in (
            ("english", "en", "reply_en"),
            ("hinglish", "hi", "reply_hi"),
        ):
            for variant in range(max(1, variants)):
                suffix = "" if variant == 0 else " Please keep it concise."
                if language == "hinglish" and variant:
                    suffix = " Short mein batao."
                identifier = hashlib.sha256(
                    f"{workflow['key']}|{language}|{variant}".encode()
                ).hexdigest()[:16]
                slots = dict(workflow.get("slots", {}))
                record = {
                    "id": f"synthetic-{identifier}",
                    "language": language,
                    "domain": "travel",
                    "task": "tool_calling" if workflow.get("tool") else "journey_dialogue",
                    "messages": [
                        {"role": "system", "content": SYSTEM_MESSAGE},
                        {"role": "user", "content": workflow[user_key] + suffix},
                        {"role": "assistant", "content": workflow[reply_key]},
                    ],
                    "intent": workflow["intent"],
                    "slots": slots,
                    "required_missing_fields": workflow.get("missing", []),
                    "expected_action": workflow.get("action", "call_tool"),
                    "expected_tool": _tool(workflow.get("tool"), slots),
                    "consent_required": workflow.get("consent", False),
                    "safe_execution_state": workflow.get("state", "tool_requested" if workflow.get("tool") else "respond"),
                    "source": "synthetic_commute_os",
                    "license": "project-generated",
                    "quality_score": 0.92 if variant == 0 else 0.88,
                    "scenario_group": workflow["key"],
                    "quality_metadata": {"generator": "deterministic_template", "variant": variant, "llm_used": False},
                }
                records.append(validate_record(record))
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", type=int, default=2)
    parser.add_argument("--output", default="datasets/interim/synthetic.jsonl")
    args = parser.parse_args()
    records = generate_records(args.variants)
    write_jsonl(__import__("pathlib").Path(args.output), records)
    print(f"Generated {len(records)} English/Hinglish records without an LLM.")


if __name__ == "__main__":
    main()
