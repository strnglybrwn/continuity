# Heartbeat Escalation Model Plan

## Purpose

Define and sequence the next feature slice for escalation behavior when a heartbeat remains unchecked after reminder and overdue stages.

This plan is implementation-focused and intended for execution on branch feature/heartbeat-escalation-model.

## Status (updated)

Phases 1 and 2 (schema, service logic, event emission) are complete and tested.

Phase 3 (API and templates) is complete:

1. `prepare-escalation` endpoint implemented and tested (`POST /heartbeat-events/{event_id}/prepare-escalation`).
2. Escalation templates (`escalation_notification.txt/html`) implemented.
3. API tests added for success/404/409 cases.

An additional stage not covered by the original scope of this plan was identified and implemented alongside Phase 3: a second, more urgent **overdue-warning** notification sent to the heartbeat owner (not the escalation contact) when a heartbeat becomes overdue, ahead of any escalation-contact notification. This closes a gap where the owner previously received a reminder before the due date but no distinct notice once the heartbeat actually lapsed. It is now documented as in-scope below (see "Overdue-Warning Stage").

Phase 4 (dashboard and operations) has not been started.

## Scope

In scope:

1. Escalation policy data model.
2. Escalation event generation and deduplication.
3. Escalation payload preparation endpoint(s).
4. Overdue-warning payload preparation endpoint (owner-facing, added during Phase 3 implementation).
5. Dashboard visibility for escalation state.
6. Operational metrics and runbook updates.
7. Tests and rollout plan.

Out of scope for first iteration:

1. Multi-step escalation chains across many contacts.
2. External policy engine.
3. Per-recipient transport provider routing logic.

## Current Baseline

Already present in code:

1. Event enum contains escalation_due.
2. Event queue model and pending/delivered lifecycle exist.
3. Scheduler evaluates reminders and overdue transitions.
4. n8n integration already handles reminder_due event flow.

Implemented since original baseline:

1. Escalation policy fields persisted on heartbeats (escalation_enabled, escalation_delay_days, escalation_contact_name, escalation_contact_email).
2. Scheduler path emits both OVERDUE (owner warning) and ESCALATION_DUE (contact notification) events.
3. `prepare-overdue` and `prepare-escalation` payload contracts implemented.
4. Escalation and overdue-warning service/API tests added.

## Overdue-Warning Stage

A heartbeat that lapses past its due date now emits an `OVERDUE` event in addition to the existing `ESCALATION_DUE` event. The `OVERDUE` event is prepared via `prepare_overdue_notification` / `POST /heartbeat-events/{event_id}/prepare-overdue`, which:

1. Issues a fresh check-in token and check-in URL, so the owner can still resolve the situation directly from this notice.
2. Conditionally includes escalation contact name and computed escalation deadline in the notification content, only when `escalation_enabled` is true and a contact email is configured.
3. Sends to the heartbeat owner (not the escalation contact).

This sits between the pre-due REMINDER_DUE notice and the ESCALATION_DUE notice to the escalation contact, giving the owner a final, more urgent chance to check in before the nominated contact is notified.

## Target Behavior

Escalation should occur when all of the following are true:

1. Heartbeat is overdue.
2. Escalation is enabled for the heartbeat.
3. Overdue age exceeds escalation delay.
4. A matching escalation_due event has not already been emitted for that escalation window.

Reset behavior:

1. Any successful check-in clears active escalation condition.
2. Future escalation can occur again only after a new overdue cycle.

## Proposed Data Model Changes

Add heartbeat-level policy fields:

1. escalation_enabled: bool (default false)
2. escalation_delay_days: int (default 1, min 1)
3. escalation_contact_name: string nullable
4. escalation_contact_email: string nullable

Validation rules:

1. If escalation_enabled=true then contact name/email are required.
2. escalation_delay_days must be less than or equal to interval_days.
3. Escalation contact email must allow normal email validation.

Migration notes:

1. Add nullable columns first with safe defaults.
2. Backfill defaults for existing rows.
3. Add check constraints after backfill if needed.

## Domain and Service Changes

1. Add escalation evaluation helper in heartbeat service.
2. Extend due-evaluation path to emit escalation_due events.
3. Reuse existing event dedupe pattern by heartbeat_id + event_type + occurred_at.
4. Add escalation timestamp computation from overdue transition or next_due_at anchor.

## API Contract Changes

### Heartbeat CRUD and Dashboard

1. Include escalation fields in heartbeat response schema.
2. Extend dashboard edit form to support escalation settings.

### Events API

1. Pending endpoint already includes event_type and can return escalation_due.
2. Escalation payload preparation endpoint implemented as its own route for clarity and stricter validation:
   - `POST /heartbeat-events/{event_id}/prepare-escalation`
3. Overdue-warning payload preparation endpoint implemented the same way:
   - `POST /heartbeat-events/{event_id}/prepare-overdue`
4. Keep delivered acknowledgment unchanged.

Preferred contract:

1. Keep reminder, overdue-warning, and escalation preparation endpoints separate for strict validation and easier n8n branching. (Implemented as described.)

## Notification Content

Escalation templates (implemented):

1. app/templates/escalation_notification.txt
2. app/templates/escalation_notification.html

Overdue-warning templates (implemented):

1. app/templates/heartbeat_overdue_warning.txt
2. app/templates/heartbeat_overdue_warning.html

Escalation payload fields (implemented, informational only — see Open Decision #4):

1. event_id
2. heartbeat_id
3. owner_name
4. escalation_contact_name
5. escalation_contact_email
6. subject / text_body / html_body

Overdue-warning payload fields (implemented):

1. event_id
2. heartbeat_id
3. owner_name
4. owner_email
5. subject / text_body / html_body
6. checkin_url

## Scheduler and Operations

Scheduler:

1. Evaluate escalation_due in the same evaluation loop.
2. Log count of emitted escalation events.

Metrics (implemented):

1. Queue metrics extended with pending_overdue_total and pending_escalation_due_total.
2. Stale metrics extended with stale_overdue_total and stale_escalation_due_total; stale_pending_alert now trips if any of the three event types (reminder, overdue, escalation) is stale.

Runbook:

1. Add operator actions for escalation backlog.
2. Document expected n8n escalation branch sequence.

## n8n Workflow Extension

Add escalation branch after pending events fetch:

1. Filter event_type == escalation_due.
2. Call prepare escalation payload endpoint.
3. Send escalation notification to escalation contact.
4. Mark event delivered only after successful send.

Add overdue-warning branch alongside it:

1. Filter event_type == overdue.
2. Call prepare-overdue payload endpoint.
3. Send overdue-warning notification to the heartbeat owner.
4. Mark event delivered only after successful send.

See docs/N8N_WORKFLOW.md for the node-by-node description.

## Testing Strategy

Unit/service tests:

1. Escalation eligibility calculations.
2. Escalation event deduplication across repeated evaluations.
3. Check-in reset prevents duplicate escalation in same cycle.
4. Overdue-warning and escalation notification builders (subject/template/recipient/HTML-escaping) — implemented in tests/test_notification_service.py.
5. prepare_overdue_notification and prepare_escalation_notification success/rejection paths — implemented in tests/test_heartbeat_event_service.py.

API tests:

1. Escalation fields validation in create/update paths.
2. Pending endpoint includes escalation_due events.
3. Prepare escalation endpoint success and error codes — implemented.
4. Prepare overdue endpoint success and error codes — implemented.
5. Metrics endpoint response includes new pending/stale fields for overdue and escalation — implemented.

Scheduler tests:

1. Emission when overdue threshold exceeded.
2. No emission before threshold.
3. Logging and metrics checks.

UI tests:

1. Dashboard shows escalation settings.
2. Form validation and persistence behavior.

## Implementation Phases

Phase 1: Schema and models — Complete.

1. Add migration.
2. Update SQLAlchemy model.
3. Update Pydantic schemas.

Phase 2: Service logic and event emission — Complete.

1. Add escalation evaluation path.
2. Add event creation and dedupe logic.
3. Add service tests.

Phase 3: API and templates — Complete.

1. Add prepare-escalation endpoint. Done.
2. Add escalation templates and notification rendering. Done.
3. Add API tests. Done.
4. (Added during this phase) Add prepare-overdue endpoint, templates, and tests for the owner-facing overdue-warning stage. Done.

Phase 4: Dashboard and operations — Not started.

1. Add dashboard escalation editing controls.
2. Extend metrics and runbooks.
3. Add UI and scheduler test coverage.

## Acceptance Criteria

1. Escalation policy fields can be configured and validated.
2. escalation_due is emitted only when policy threshold is crossed.
3. Escalation payload preparation returns complete send-ready content.
4. n8n can deliver and acknowledge escalation events via existing delivered flow.
5. Ruff and pytest pass.

## Open Decisions

1. Should escalation delay be measured from next_due_at or first overdue event time? **Resolved:** measured from `next_due_at` (see `heartbeat_escalation_at()`).
2. Should escalation be one-time per overdue cycle or repeat at interval? **Resolved:** one-time per overdue cycle, using the existing event dedupe pattern; a new escalation can only occur after a fresh overdue cycle following a check-in.
3. Should escalation contact be one person in v1 or multiple recipients? **Resolved:** single contact in v1 (`escalation_contact_name` / `escalation_contact_email` are singular fields).
4. Should escalation payload include direct check-in action link for contact use? **Resolved (this session, needs user confirmation):** No. The escalation-contact notification is informational only, with no check-in link or token issued — it only informs the contact that the owner has missed check-ins and asks them to check on the owner's wellbeing. The owner-facing overdue-warning notification (a separate, new stage) does include a check-in link, since that recipient is the one who can actually resolve it.

