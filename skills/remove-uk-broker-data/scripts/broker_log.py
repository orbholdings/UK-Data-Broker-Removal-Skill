#!/usr/bin/env python3
"""Private evidence log helper. No network, browser, mail or Library operations."""
import argparse
import calendar
from datetime import date, timedelta
import json
from pathlib import Path
import os
import tempfile

STATUSES = {
    "not_attempted", "draft", "awaiting_verification", "processing",
    "needs_info", "browser_blocked", "suppression_confirmed",
    "erasure_confirmed", "no_record_confirmed", "reappeared", "rejected"
}
CONFIRMED = {"suppression_confirmed", "erasure_confirmed", "no_record_confirmed"}

def iso(value):
    return date.fromisoformat(value)

def add_months(start, months=1):
    start = iso(start) if isinstance(start, str) else start
    year, month0 = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(year, month0 + 1,
                min(start.day, calendar.monthrange(year, month0 + 1)[1]))

def working_day(day, holidays=()):
    holidays = set(holidays)
    while day.weekday() >= 5 or day.isoformat() in holidays:
        day += timedelta(days=1)
    return day

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def validate(case):
    if case.get("schema_version") != 1:
        raise ValueError("Expected schema_version 1")
    requests = case.get("requests")
    if not isinstance(requests, list):
        raise ValueError("requests must be an array")
    ids = set()
    for request in requests:
        rid = request.get("id")
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError("Request IDs must be non-empty and unique")
        ids.add(rid)
        if not request.get("broker_id") or not request.get("scope"):
            raise ValueError("Every request needs broker_id and explicit scope")
        if request.get("status") not in STATUSES:
            raise ValueError("Unsupported request status: " + str(request.get("status")))
        for key in ("submitted_on", "received_on", "identity_completed_on",
                    "verified_on", "confirmed_on", "last_checked_on"):
            if request.get(key):
                iso(request[key])
        if request.get("status") in CONFIRMED and not request.get("confirmation_evidence"):
            raise ValueError("Confirmed outcomes require broker evidence")
        if request.get("extension_months", 0) not in (0, 2):
            raise ValueError("Only zero or a documented two-month extension is supported")
        if request.get("extension_months") and not (
            request.get("extension_reason") and request.get("extension_notified_on")
        ):
            raise ValueError("An extension needs its reason and notice date")
    events = case.get("events", [])
    eids = [e.get("event_id") for e in events]
    if any(not x for x in eids) or len(set(eids)) != len(eids):
        raise ValueError("Event IDs must be non-empty and unique")
    return {"valid": True, "requests": len(requests), "events": len(events)}

def deadline(request, holidays=(), holidays_verified=False):
    if request.get("response_deadline_applicable") is False:
        return None
    start = (request.get("identity_completed_on") or request.get("received_on")
             or request.get("submitted_on"))
    if not start:
        return None
    extension = request.get("extension_months", 0)
    baseline = working_day(add_months(start), holidays)
    if extension:
        if iso(request["extension_notified_on"]) > baseline:
            raise ValueError("Late extension notice needs manual legal review")
    due = working_day(add_months(start, 1 + extension), holidays)
    return {
        "date": due.isoformat(),
        "basis": start,
        "provisional": not (
            holidays_verified and request.get("clock_start_confirmed", False)
        ),
        "note": "Calendar-month baseline; review identity, verification, applicable law and holiday facts."
    }

def plan(case, as_of, holidays=(), holidays_verified=False):
    validate(case)
    today = iso(as_of)
    actions = []
    for request in case["requests"]:
        status = request["status"]
        due = deadline(request, holidays, holidays_verified)
        action = {
            "request_id": request["id"],
            "broker_id": request["broker_id"],
            "status": status,
            "priority": request.get("priority", 3),
            "deadline": due,
            "overdue": bool(due and iso(due["date"]) < today and status not in CONFIRMED),
            "automatic_resubmission": False
        }
        if status == "awaiting_verification":
            action["next_step"] = "Complete the verified broker email/phone confirmation; do not submit a duplicate request."
        elif status == "needs_info":
            action["next_step"] = "Obtain missing facts or use a verified general privacy route; never invent form answers."
            action["missing"] = request.get("missing_fields", [])
        elif status == "browser_blocked":
            action["next_step"] = "Respect the recorded browser block; use an authorised independent continuation or report it."
        elif status in CONFIRMED:
            action["next_step"] = "Recheck relevant public exposure; do not repeat a confirmed suppression without reappearance evidence."
            action["overdue"] = False
        elif status == "processing":
            action["next_step"] = "Check relevant broker reply and stated processing window; follow up when justified."
        elif status == "draft":
            action["next_step"] = "Verify recipient, current connection and valid send authority; send the reviewed draft if permitted."
            action["deadline"] = None
            action["overdue"] = False
        elif status == "reappeared":
            action["next_step"] = "Validate the recurrence evidence and prior scope, then prepare an authorised follow-up."
        elif status == "rejected":
            action["next_step"] = "Review the reason and retained scope; prepare an evidence-backed challenge where appropriate."
        else:
            action["next_step"] = "Verify first-party route and relevance/matching evidence before any disclosure."
        actions.append(action)
    return {
        "as_of": as_of,
        "email_access_scope": case.get("authorization", {}).get("email_access_scope", "unconfirmed"),
        "actions": sorted(actions, key=lambda a: (not a["overdue"], a["priority"], a["request_id"])),
        "limits": "A plan performs no removals and sends no messages. Monthly cadence does not monitor intervening days."
    }

def record(case, event):
    validate(case)
    required = {"event_id", "request_id", "type", "date", "evidence"}
    if not required <= set(event):
        raise ValueError("Event lacks required fields")
    iso(event["date"])
    evidence = event["evidence"]
    if not isinstance(evidence, dict) or not evidence.get("kind") or not evidence.get("summary"):
        raise ValueError("Evidence needs a kind and non-empty summary")
    existing = next((e for e in case.get("events", [])
                     if e["event_id"] == event["event_id"]), None)
    if existing:
        if existing != event:
            raise ValueError("Event ID collision with different contents")
        return False
    request = next((r for r in case["requests"] if r["id"] == event["request_id"]), None)
    if request is None:
        raise ValueError("Unknown request ID")
    kind, day = event["type"], event["date"]
    final = {
        "suppression_confirmed": "suppression_confirmed",
        "erasure_confirmed": "erasure_confirmed",
        "no_record_confirmed": "no_record_confirmed"
    }
    if kind == "request_submitted":
        if request["status"] not in {"not_attempted", "draft", "reappeared"}:
            raise ValueError("A pending/closed request cannot be blindly resubmitted")
        if evidence["kind"] not in {"submission_receipt", "sent_message"}:
            raise ValueError("Submission needs a receipt or sent-message evidence")
        request.setdefault("first_submitted_on", day)
        request["submitted_on"] = day
        request["status"] = "processing"
        request.setdefault("submission_history", []).append({"date": day, "evidence": evidence})
    elif kind in final:
        if not request.get("submitted_on") or evidence["kind"] != "broker_response":
            raise ValueError("A confirmed outcome needs an earlier submission and explicit broker-response evidence")
        request.update(status=final[kind], confirmed_on=day, confirmation_evidence=evidence)
    elif kind == "search_checked":
        request["last_checked_on"] = day
        request["last_search_observation"] = evidence
    elif kind == "reappearance_found":
        if evidence["kind"] != "live_listing" or request["status"] not in CONFIRMED:
            raise ValueError("Reappearance requires a confirmed prior outcome and actual listing evidence")
        request.update(status="reappeared", reappeared_on=day, reappearance_evidence=evidence)
    elif kind == "listing_found":
        if evidence["kind"] != "live_listing":
            raise ValueError("A match requires actual listing evidence")
        request.update(last_checked_on=day, matching_evidence=evidence)
    elif kind == "verification_required":
        if not request.get("submitted_on"):
            raise ValueError("Verification cannot imply a submission")
        request["status"] = "awaiting_verification"
    elif kind == "verification_completed":
        if evidence["kind"] != "verification_receipt" or not request.get("submitted_on"):
            raise ValueError("Verification needs a submitted request and a verification receipt")
        request.update(status="processing", verified_on=day)
    elif kind == "identity_supplied":
        if not request.get("submitted_on"):
            raise ValueError("Identity completion needs an existing request")
        request["identity_completed_on"] = day
    elif kind == "response_received":
        request["last_response_on"] = day
        request["last_response_evidence"] = evidence
    elif kind == "refusal_received":
        if evidence["kind"] != "broker_response":
            raise ValueError("Refusal requires broker-response evidence")
        request.update(status="rejected", last_response_on=day, last_response_evidence=evidence)
    elif kind == "draft_created":
        if request["status"] not in {"not_attempted", "draft", "needs_info"}:
            raise ValueError("Cannot overwrite pending or confirmed state with a draft")
        request["status"] = "draft"
    elif kind == "blocked":
        request["blocker"] = evidence
        if request["status"] in {"not_attempted", "draft", "needs_info", "browser_blocked"}:
            request["status"] = "browser_blocked"
    elif kind == "facts_needed":
        request["missing_fields"] = event.get("missing_fields", [])
        if request["status"] not in CONFIRMED:
            request["status"] = "needs_info"
    else:
        raise ValueError("Unsupported event type: " + str(kind))
    case.setdefault("events", []).append(event)
    case["updated_on"] = day
    validate(case)
    return True

def save(path, case):
    path = Path(path)
    # Create the replacement with private permissions. Library identity belongs to
    # the enclosing pack; do not copy user credentials or unrelated file metadata.
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(case, stream, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "plan", "record"])
    parser.add_argument("case")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--holidays")
    parser.add_argument("--event-file")
    args = parser.parse_args()
    case = load(args.case)
    holidays = []
    if args.holidays:
        source = load(args.holidays)
        if not source.get("jurisdiction") or not source.get("verified_on"):
            raise ValueError("Holiday metadata needs jurisdiction and verified_on")
        holidays = source["dates"]
        for day in holidays:
            iso(day)
    if args.command == "validate":
        result = validate(case)
    elif args.command == "plan":
        result = plan(case, args.as_of, holidays, bool(args.holidays))
    else:
        if not args.event_file:
            parser.error("record requires --event-file")
        changed = record(case, load(args.event_file))
        if changed:
            save(args.case, case)
        result = {"changed": changed, **validate(case)}
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc))
