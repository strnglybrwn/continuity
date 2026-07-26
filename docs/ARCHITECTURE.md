# Continuity Architecture

## Purpose

Continuity is a self-hosted digital deadman's switch platform.

In the current implementation, users create heartbeats with a due interval and optional reminder window. The system evaluates due heartbeats, records lifecycle events, and supports secure check-in redemption through one-time links.

## Architecture Overview

The platform is currently a single FastAPI service with a PostgreSQL backing store.

Operationally, workflow orchestration for heartbeat events is handled by an n8n instance in the homelab Docker Swarm.

1. API layer
- Exposes heartbeat CRUD-adjacent operations, event queue endpoints, operations dashboard pages, and check-in confirmation pages.
- Entry point: app/main.py

2. Domain layer
- Enumerates lifecycle and notification concepts.
- Files: app/domain/heartbeat.py, app/domain/notification.py

3. Service layer
- Encapsulates lifecycle evaluation, check-in token issuance/redemption, event queue behavior, and notification rendering.
- Files: app/services/*.py

4. Persistence layer
- SQLAlchemy models and session/engine setup.
- Files: app/persistence/*.py

5. Scheduler
- Optional in-process loop that periodically evaluates active heartbeats.
- File: app/scheduler.py

6. External workflow orchestrator (n8n)
- Polls/consumes heartbeat event queue APIs and executes workflow steps for reminder delivery.
- Reaches Continuity internally at http://api:8000 and is externally published behind Caddy at https://continuity.boardmad.com.
- Externally reachable n8n endpoint is http://n8n.whistler.home.

## Implemented Data Model

The schema is represented by SQLAlchemy models and Alembic migrations.

- heartbeats
	- Owner identity, lifecycle state, interval/reminder settings, due/check-in timestamps.
- heartbeat_checkins
	- Historical check-ins with status, notes, source, and timestamp.
- heartbeat_checkin_tokens
	- One-time token hashes, expiry, redemption timestamp.
- heartbeat_events
	- Event log/queue for reminder, overdue, checked-in, and escalation event types.
- heartbeat_attachments
	- Escalation-only binary attachments (PDF/Office/image) associated with a heartbeat.

Current migration chain:

1. cdbea5bc59b8: create heartbeats
2. e4fc9edd7706: add check-in history
3. 7a62df438921: add check-in tokens
4. 4f4a9a4c7874: add heartbeat events

## Lifecycle Model (Current)

Heartbeat statuses:

- active
- overdue
- paused
- cancelled

Lifecycle rules implemented in app/services/heartbeat_service.py:

1. active heartbeats become overdue when next_due_at <= now.
2. paused/cancelled/overdue states are not auto-transitioned back.
3. check-ins set status to active, update last_checkin_at, and compute next_due_at.
4. reminder_due events are generated during the reminder window.
5. overdue events are generated when an active heartbeat transitions to overdue.
6. checked_in events are generated when a check-in is recorded.

The service deduplicates lifecycle events by (heartbeat_id, event_type, occurred_at).

## API Surface (Current)

Heartbeats:

- POST /heartbeats
- GET /heartbeats
- GET /heartbeats/{heartbeat_id}
- POST /heartbeats/{heartbeat_id}/checkins

Heartbeat events queue:

- GET /heartbeat-events/pending?limit=...
- GET /heartbeat-events/metrics?stale_after_seconds=...
- POST /heartbeat-events/evaluate-due
- POST /heartbeat-events/{event_id}/prepare-reminder
- POST /heartbeat-events/{event_id}/delivered

Operations dashboard:

- GET /ui/heartbeats
- POST /ui/heartbeats/{heartbeat_id}

Check-in web flow:

- GET /checkins/{token}
	- Displays a confirmation form only.
- POST /checkins/{token}
	- Redeems token if valid, else unavailable page.

System:

- GET /health

## Notification Pipeline Status

Implemented today:

1. Reminder message composition is implemented with Jinja templates.
2. Notification message structure includes channel, recipient, subject, text, and HTML body.
3. Event queue endpoints support fetch pending events and mark delivery.
4. Event queue metrics expose stale queue alerts for operations.
5. Dashboard updates support operational edits of owner identity, recipient,
   lifecycle interval/reminder windows, and reminder-window arming.
7. Final escalation payload preparation includes attachment metadata and download paths for n8n to fetch binaries before sending escalation email.

Not yet wired end-to-end:

1. No outbound mail transport exists in this codebase yet.
2. No in-repository event dispatcher/worker currently polls pending events and sends reminders.
3. No integration currently issues check-in tokens as part of reminder dispatch.

Current production integration boundary:

1. Event workflow orchestration is performed by n8n (outside this repository).
2. Continuity exposes event queue and reminder preparation APIs consumed by the n8n flow.
3. n8n sends the reminder via configured mail transport, then acknowledges delivery.

## Runtime Topology (Current)

In production deployment, one API container and one PostgreSQL container run in Docker Swarm, with event workflow automation provided by a separate n8n service in the same homelab environment.

- API enables the scheduler by environment variable.
- Scheduler evaluates due heartbeats on a fixed interval.
- n8n consumes pending events from the API and performs workflow delivery steps.
- Internal service-to-service API endpoint is http://api:8000.
- External HTTPS entrypoint is https://continuity.boardmad.com (via Caddy).
- External n8n entrypoint is http://n8n.whistler.home.

## Security and Reliability Characteristics

Implemented controls:

1. Check-in tokens are stored only as SHA-256 hashes.
2. Token redemption uses row-level locking and one-time use semantics.
3. Token error UX does not disclose whether a token is unknown/expired/used.
4. Scheduler failures are logged and loop continues.

Current constraints:

1. API authentication/authorization is not implemented.
2. Check-in links are bearer-style URLs; delivery channel hardening depends on email transport implementation.
3. Overdue/escalation delivery policy is not yet wired to a transport.
4. Scheduler remains in-process and single-replica oriented.
