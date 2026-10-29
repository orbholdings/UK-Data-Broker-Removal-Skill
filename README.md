# UK Data Broker Removal Skill

A reusable assistant workflow for UK personal-data removal, direct-marketing objections, verification, evidence logging and periodic rechecks.

The skill helps an assistant research official rights routes, use the minimum matching information, handle broker replies and record what actually happened. It covers residential directories, marketing brokers and source-feed choices, with separate treatment for work contacts, device identifiers, credit-reference data and statutory public records.

## What is included

- `skills/remove-uk-broker-data/SKILL.md`: the operational workflow.
- `references/protocol.md`: scope, timing and first-party sources.
- `references/catalogue.json`: a dated public discovery catalogue, including published Incogni/DeleteMe coverage flags. Inclusion is not proof of a personal record, UK-plan eligibility or a completed removal.
- `references/request-templates.md`: adaptable marketing, supplier, guidance and follow-up requests.
- `references/case-binding.example.json`: an unbound configuration example.
- `scripts/broker_log.py`: an offline JSON case-log validator, event recorder and next-action planner.
- `scripts/test_broker_log.py`: eight regression checks using fictional requests.

## Use

Use your assistant host's supported skill installer with the `skills/remove-uk-broker-data` directory. Provide the assistant with a private case file and explicit authority for the actions and accounts it may use. The Python helper requires Python 3.10 or later and the standard library only.

```sh
python3 skills/remove-uk-broker-data/scripts/broker_log.py validate /path/to/private/removal-log.json
python3 skills/remove-uk-broker-data/scripts/broker_log.py plan /path/to/private/removal-log.json --as-of YYYY-MM-DD
python3 -B skills/remove-uk-broker-data/scripts/test_broker_log.py -v
```

This repository supplies instructions and offline bookkeeping. It does not supply browser, email or scheduling credentials, submit removals by itself, install a system cron job or guarantee that every broker can erase every record. A recurring review needs an authorised scheduler in the assistant's host. Monthly reviews must not resend every pending request or assume permanent inbox permission.

## Keep case data private

Keep populated case bindings, names/contact details, addresses, DOB, device identifiers, requests, replies, identity evidence and verification links outside this repository. Only the empty example binding belongs here. A `.gitignore` helps prevent accidental additions, but review the staged diff before every upload.

Use minimal suppression records when needed to prevent reintroduction. Preserve the distinction between a sent request, verification, processing, suppression, erasure and a broker-confirmed no-record response. A clean web search is not proof of deletion. If a broker names a supplier, verify that supplier's current privacy contact before following the data upstream.

Public route and coverage information is a dated research seed; verify current first-party details before sending personal data. Requests and response timing depend on the actual facts and applicable law.
