# Continuity Roadmap

## Current Snapshot (2026-07-28)

This document tracks milestone progress from the currently implemented platform state.

## Product Goal

Deliver a trustworthy digital deadman's switch where:

1. A reminder notification is sent to the user when due.
2. The user confirms they are safe through a secure check-in link.
3. The heartbeat resets and evidence is retained.

## MVP Milestone Definition

MVP is complete when all of the following are demonstrably true in a testable workflow:

1. Reminder email delivery is successfully executed to a real inbox (or controlled mail sink).
2. The delivered reminder includes a valid one-time check-in link.
3. User confirmation redeems token exactly once.
4. Heartbeat status/due date reset is observable through API/state.
5. Delivery and check-in lifecycle evidence is queryable.

## Status by Capability

Completed:

1. Heartbeat lifecycle domain model and state transitions.
2. Persistent storage for heartbeats, check-ins, check-in tokens, and events.
3. Scheduler-based due evaluation and event creation.
4. Reminder notification rendering (text + HTML templates).
5. Check-in confirmation web UX and one-time token redemption semantics.
6. Event queue endpoints for pending events and delivered acknowledgment.
7. CI pipeline for lint/test and multi-platform image publishing.
8. Operations dashboard for heartbeat verification, inline heartbeat settings updates, heartbeat creation, and heartbeat deletion.
9. Reminder queue metrics and stale alerting runbook support.
10. Scripted Swarm deployment flow with migration-first release process.
11. n8n-based end-to-end reminder and overdue dispatch wiring from pending events through delivered acknowledgment.
12. Escalation policy execution path for escalation_due events, including escalation email preparation.
13. Escalation attachment retrieval and delivery path for workflow-driven escalation notifications.
14. Dashboard schedule edit behavior now clears stale undelivered lifecycle queue events when policy timing changes.

In progress:

1. Optional in-repo dispatcher/worker loop as an alternative to external n8n orchestration.

Not started or not complete:

1. First-class outbound email transport abstraction and provider configuration.
2. End-to-end integration test that proves reminder email -> click -> reset across real components.
3. End-to-end integration test coverage for escalation attachment delivery across workflow boundaries.
4. Authn/authz for API surfaces.

Escalation planning reference:

1. See docs/ESCALATION_MODEL_PLAN.md for phased implementation scope, contracts, and acceptance criteria.

## MVP Execution Plan (Next Step After Review)

Phase 1: Keep external workflow path healthy (operational baseline)

1. Optional: add an in-repo dispatch worker/service loop that:
	- reads GET /heartbeat-events/pending
	- for reminder_due events calls POST /heartbeat-events/{event_id}/prepare-reminder
	- sends via configured mail transport
	- marks event delivered only on successful send

Note: production currently satisfies dispatch operationally via n8n workflow orchestration,
including reminder_due, overdue, and escalation_due processing. In-repo dispatch remains optional.

Phase 2: Add integration testing harness

1. Use local mail sink (for example MailHog/Mailpit) in dev.
2. Add test that validates message subject/body and included check-in link.
3. Add test that exercises GET/POST confirmation and verifies heartbeat reset.

Phase 3: Capture MVP evidence

1. Record API/event state before reminder.
2. Capture delivered message evidence.
3. Confirm one-time token consumption behavior.
4. Record post-check-in heartbeat state reset.

## Immediate Acceptance Criteria for "MVP Today"

Status: Operationally achieved via API + n8n workflow path; formal automated end-to-end proof is still pending.

1. Demonstrate one real reminder delivery.
2. Complete one successful confirmation click-through.
3. Show heartbeat next_due_at moved forward after confirmation.
4. Show supporting event/check-in records persisted.

## Recently Resolved (July 2026)

1. Fixed dashboard regression where policy-time edits could leave stale timeline/next-action entries by clearing pending undelivered lifecycle queue events after schedule changes.
2. Added dedupe protection for heartbeat lifecycle events at the database level with a unique constraint migration.
3. Hardened n8n escalation attachment handling to support variable binary keys instead of assuming a fixed key, preventing silent no-attachment sends.
4. Published repository-level onboarding/docs updates (README and workflow import artifacts) for current architecture and deployment flow.

## Risks to Watch

1. Duplicate sends under retries or multi-consumer concurrency.
2. Delivered marking before actual transport success.
3. Link expiry window mismatch with user expectations.
4. Scheduler and dispatcher timing interactions in accelerated test mode.
