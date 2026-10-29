"""Offline regression checks using fictional requests only."""
import copy
import unittest

import broker_log


def case(status="not_attempted", **fields):
    request = {"id": "example-request", "broker_id": "example-controller", "scope": "Fictional email-matching marketing request", "status": status, **fields}
    return {"schema_version": 1, "authorization": {"email_access_scope": "not_authorised"}, "requests": [request], "events": []}


def event(kind, event_id="example-event", evidence_kind="sent_message", **fields):
    return {"event_id": event_id, "request_id": "example-request", "type": kind, "date": "2026-10-29", "evidence": {"kind": evidence_kind, "summary": "Fictional evidence for an offline regression check."}, **fields}


class BrokerLogTests(unittest.TestCase):
    def test_calendar_month_clamps_and_moves_weekend(self):
        self.assertEqual(broker_log.add_months("2024-01-31").isoformat(), "2024-02-29")
        self.assertEqual(broker_log.add_months("2026-01-31").isoformat(), "2026-02-28")
        self.assertEqual(broker_log.deadline({"submitted_on": "2026-10-29"})["date"], "2026-11-30")

    def test_verified_holiday_calendar_is_explicit(self):
        request = {"received_on": "2026-09-29", "clock_start_confirmed": True}
        result = broker_log.deadline(request, holidays=["2026-10-29"], holidays_verified=True)
        self.assertEqual(result["date"], "2026-10-30")
        self.assertFalse(result["provisional"])
        self.assertTrue(broker_log.deadline(request)["provisional"])

    def test_activated_registration_has_no_pending_response_clock(self):
        obj = case("processing", submitted_on="2026-01-01", response_deadline_applicable=False)
        action = broker_log.plan(obj, "2026-10-29")["actions"][0]
        self.assertIsNone(action["deadline"])
        self.assertFalse(action["overdue"])

    def test_duplicate_event_is_idempotent_and_pending_resend_rejected(self):
        obj = case()
        submitted = event("request_submitted")
        self.assertTrue(broker_log.record(obj, submitted))
        self.assertFalse(broker_log.record(obj, copy.deepcopy(submitted)))
        with self.assertRaises(ValueError):
            broker_log.record(obj, event("request_submitted", event_id="duplicate-submission"))
        self.assertEqual(len(obj["events"]), 1)

    def test_confirmation_needs_submission_and_broker_evidence(self):
        with self.assertRaises(ValueError):
            broker_log.record(case(), event("suppression_confirmed", evidence_kind="broker_response"))
        obj = case("processing", submitted_on="2026-10-29")
        with self.assertRaises(ValueError):
            broker_log.record(obj, event("suppression_confirmed", evidence_kind="search_result"))
        broker_log.record(obj, event("suppression_confirmed", evidence_kind="broker_response"))
        self.assertEqual(obj["requests"][0]["status"], "suppression_confirmed")
        self.assertNotEqual(obj["requests"][0]["status"], "erasure_confirmed")

    def test_search_absence_does_not_confirm_no_record(self):
        obj = case()
        broker_log.record(obj, event("search_checked", evidence_kind="search_observation"))
        self.assertEqual(obj["requests"][0]["status"], "not_attempted")
        self.assertNotIn("confirmation_evidence", obj["requests"][0])

    def test_sent_proof_without_acceptance_is_not_completed_identity(self):
        obj = case("processing", submitted_on="2026-10-29")
        broker_log.record(obj, event("facts_needed", missing_fields=["Broker acceptance of proportionate proof"]))
        self.assertEqual(obj["requests"][0]["status"], "needs_info")
        self.assertNotIn("identity_completed_on", obj["requests"][0])

    def test_failed_recheck_preserves_confirmed_outcome(self):
        obj = case("processing", submitted_on="2026-10-29")
        broker_log.record(obj, event("suppression_confirmed", event_id="confirmation", evidence_kind="broker_response"))
        broker_log.record(obj, event("blocked", event_id="blocked-recheck", evidence_kind="browser_block"))
        self.assertEqual(obj["requests"][0]["status"], "suppression_confirmed")
        self.assertIn("confirmation_evidence", obj["requests"][0])


if __name__ == "__main__":
    unittest.main()
