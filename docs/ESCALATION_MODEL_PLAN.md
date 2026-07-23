# Heartbeat Escalation Model Plan

## Purpose

Define and sequence the next feature slice for escalation behavior when a heartbeat remains unchecked after reminder and overdue stages.

This plan is implementation-focused and intended for execution on branch feature/heartbeat-escalation-model.

## Scope

In scope:

1. Escalation policy data model.
2. Escalation event generation and deduplication.
3. Escalation payload preparation endpoint(s).
4. Dashboard visibility for escalation state.
5. Operational metrics and runbook updates.
6. Tests and rollout plan.

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

Missing today:

1. No escalation policy persisted on heartbeats.
2. No scheduler path that emits escalation_due.
3. No prepare-escalation payload contract.
4. No escalation-specific tests or operational runbook steps.

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
2. Add escalation payload preparation endpoint, either:
   - POST /heartbeat-events/{event_id}/prepare-escalation
   - or extend prepare-reminder to support escalation_due (less preferred for clarity)
3. Keep delivered acknowledgment unchanged.

Preferred contract:

1. Keep reminder and escalation preparation endpoints separate for strict validation and easier n8n branching.

## Notification Content

Add escalation templates:

1. app/templates/escalation_notification.txt
2. app/templates/escalation_notification.html

Payload fields should include:

1. event_id
2. heartbeat_id
3. owner_name
4. escalation_contact_name
5. escalation_contact_email
6. overdue_since
7. checkin_context_url (if applicable)

## Scheduler and Operations

Scheduler:

1. Evaluate escalation_due in the same evaluation loop.
2. Log count of emitted escalation events.

Metrics:

1. Extend queue metrics with escalation_due pending count.
2. Add stale escalation metric if overdue queue stalls.

Runbook:

1. Add operator actions for escalation backlog.
2. Document expected n8n escalation branch sequence.

## n8n Workflow Extension

Add escalation branch after pending events fetch:

1. Filter event_type == escalation_due.
2. Call prepare escalation payload endpoint.
3. Send escalation notification to escalation contact.
4. Mark event delivered only after successful send.

## Testing Strategy

Unit/service tests:

1. Escalation eligibility calculations.
2. Escalation event deduplication across repeated evaluations.
3. Check-in reset prevents duplicate escalation in same cycle.

API tests:

1. Escalation fields validation in create/update paths.
2. Pending endpoint includes escalation_due events.
3. Prepare escalation endpoint success and error codes.

Scheduler tests:

1. Emission when overdue threshold exceeded.
2. No emission before threshold.
3. Logging and metrics checks.

UI tests:

1. Dashboard shows escalation settings.
2. Form validation and persistence behavior.

## Implementation Phases

Phase 1: Schema and models

1. Add migration.
2. Update SQLAlchemy model.
3. Update Pydantic schemas.

Phase 2: Service logic and event emission

1. Add escalation evaluation path.
2. Add event creation and dedupe logic.
3. Add service tests.

Phase 3: API and templates

1. Add prepare-escalation endpoint.
2. Add escalation templates and notification rendering.
3. Add API tests.

Phase 4: Dashboard and operations

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

1. Should escalation delay be measured from next_due_at or first overdue event time?
2. Should escalation be one-time per overdue cycle or repeat at interval?
3. Should escalation contact be one person in v1 or multiple recipients?
4. Should escalation payload include direct check-in action link for contact use?
