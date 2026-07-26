# Continuity Operations Guide

## Purpose

This guide documents day-2 operations for the platform in its current implementation state.

For release/deploy process details, see docs/DEPLOYMENT.md.

## Runtime Components

Current production stack components:

1. continuity_api (FastAPI service)
2. continuity_postgres (PostgreSQL)
3. n8n workflow service (event orchestration and reminder workflow execution)
4. Heartbeat verifier dashboard served by the API at /ui/heartbeats

The API process may run the in-process scheduler if CONTINUITY_HEARTBEAT_SCHEDULER_ENABLED=true.

Access topology:

1. Internal API endpoint for in-swarm workflow calls: http://api:8000
2. External HTTPS endpoint through Caddy: https://continuity.boardmad.com
3. External n8n endpoint: http://n8n.whistler.home

## Health and Readiness

Primary health endpoint:

- GET /health

Expected response fields:

- status
- application
- version
- environment
- timestamp

Swarm service healthcheck also probes /health locally inside the API container.

## Core Operational Flows

1. Heartbeat evaluation loop
- Periodically evaluates active heartbeats.
- Generates reminder_due and overdue events.
- Persists status transitions.

2. Pending events queue
- Consumers can fetch undelivered events from GET /heartbeat-events/pending.
- Operators can inspect queue health from GET /heartbeat-events/metrics.
- For reminder events, n8n calls POST /heartbeat-events/{event_id}/prepare-reminder to obtain a one-time check-in URL and send-ready email content.
- Consumers should call POST /heartbeat-events/{event_id}/delivered after successful handling.
- In production, this consumer/orchestrator role is implemented by n8n workflows.
- An empty response from /heartbeat-events/pending means there are currently no undelivered lifecycle events, not necessarily that no heartbeats exist.

Metrics response highlights:

- pending_total
- pending_reminder_due_total
- oldest_pending_occurred_at
- oldest_pending_age_seconds
- stale_pending_alert
- stale_reminder_due_total

stale_pending_alert is computed from stale_after_seconds (default from CONTINUITY_HEARTBEAT_PENDING_ALERT_SECONDS).

Expected n8n reminder sequence:

1. POST /heartbeat-events/evaluate-due
2. GET /heartbeat-events/pending
3. Select event_type=reminder_due
4. POST /heartbeat-events/{event_id}/prepare-reminder
5. Send email using returned recipient/subject/body/checkin_url
6. POST /heartbeat-events/{event_id}/delivered only after successful send

## n8n API Contract (MVP)

This section defines the current request/response contract expected by n8n workflows.

1. List pending events

Request:

GET /heartbeat-events/pending?limit=100

Example response item:

{
	"id": "42f3bc53-c44c-4dd3-904d-2cab432a90dd",
	"heartbeat_id": "f8180bd0-813d-4535-8e48-c6bb86877f9a",
	"event_type": "reminder_due",
	"occurred_at": "2026-07-23T10:00:00Z",
	"delivered_at": null,
	"created_at": "2026-07-23T10:00:00Z",
	"owner_name": "Scott",
	"owner_email": "scott@example.com"
}

2. Prepare reminder payload

Request:

POST /heartbeat-events/{event_id}/prepare-reminder

Success response:

{
	"event_id": "42f3bc53-c44c-4dd3-904d-2cab432a90dd",
	"heartbeat_id": "f8180bd0-813d-4535-8e48-c6bb86877f9a",
	"owner_name": "Scott",
	"owner_email": "scott@example.com",
	"subject": "Continuity check-in reminder",
	"text_body": "Hi Scott, ...",
	"html_body": "<!doctype html>...",
	"checkin_url": "https://continuity.boardmad.com/checkins/<token>"
}

Error responses:

- 404: event not found
- 409: event already delivered
- 400: invalid event type or invalid configuration

3. Acknowledge successful delivery

Request:

POST /heartbeat-events/{event_id}/delivered

Success response:

{
	"id": "42f3bc53-c44c-4dd3-904d-2cab432a90dd",
	"heartbeat_id": "f8180bd0-813d-4535-8e48-c6bb86877f9a",
	"event_type": "reminder_due",
	"occurred_at": "2026-07-23T10:00:00Z",
	"delivered_at": "2026-07-23T10:01:33Z",
	"created_at": "2026-07-23T10:00:00Z"
}

Operational rule:

- n8n must only call /delivered after the email send stage succeeds.

## n8n Workflow Wiring Checklist

This checklist captures the remaining integration work to fully wire the reminder-triggered check-in flow.

Implementation reference:

1. See docs/N8N_WORKFLOW.md for exact node names, HTTP configuration, and expressions.

1. Trigger and poll
- Configure a scheduled n8n trigger.
- Add HTTP request node: GET /heartbeat-events/pending?limit=100.

2. Filter and iterate
- Filter for event_type == reminder_due.
- Iterate one event at a time.

3. Prepare reminder payload
- Add HTTP request node: POST /heartbeat-events/{event_id}/prepare-reminder.
- Fail the item on 400/404/409 and branch to error handling.

4. Send email
- Use owner_email as recipient.
- Use subject/text_body/html_body returned by prepare-reminder.
- Preserve event_id and heartbeat_id in workflow context.

5. Acknowledge delivery
- On successful email send only, call POST /heartbeat-events/{event_id}/delivered.
- Do not acknowledge on failed send attempts.

6. Optional confirmation evidence
- Track checkin_url in n8n execution metadata for auditability.
- Optionally notify operators with event_id, recipient, and timestamp.

7. Failure handling
- Add retry policy for transient HTTP/mail errors.
- Route hard failures to alerting (email/Slack/etc.).
- Keep failed events unacknowledged so they remain pending for retry.

3. Check-in confirmation
- Users open GET /checkins/{token}, then explicitly confirm by POST.
- Valid token redemption records check-in and resets heartbeat due date.

4. Dashboard-based heartbeat administration
- Operators can open GET /ui/heartbeats to view heartbeat status, due/reminder
	timing, and queue context.
- Per heartbeat, operators can update:
	- owner name
	- recipient email
	- interval days
	- reminder days
- Operators can arm reminder due now to force reminder window entry for testing.
- Validation rule: reminder_days must be less than interval_days.

## Logging and Diagnostics

Application logging is configured at INFO level.

Key scheduler logs:

- Successful evaluation summary: evaluated and changed counts.
- Exception trace when heartbeat evaluation fails.

Operational checks:

```bash
docker service ps continuity_api
docker service logs continuity_api
docker service logs continuity_postgres
```

Daily reminder queue smoke/alert check:

```bash
scripts/daily_reminder_healthcheck.sh
```

Environment overrides:

- CONTINUITY_BASE_URL (default: https://continuity.boardmad.com)
- CONTINUITY_STALE_AFTER_SECONDS (default: 3600)
- CONTINUITY_EVALUATE_FIRST (default: true)

Script behavior:

- Calls POST /heartbeat-events/evaluate-due (optional)
- Calls GET /heartbeat-events/metrics
- Exits non-zero (code 3) when stale_pending_alert=true

Recommended daily operator sequence:

1. Run scripts/daily_reminder_healthcheck.sh.
2. If stale alert is raised, inspect /heartbeat-events/metrics and n8n runs.
3. Confirm scheduler evaluation with POST /heartbeat-events/evaluate-due.
4. Verify dashboard state at /ui/heartbeats for high-priority heartbeats.

## Runbook: Stalled Reminder Processing

Symptoms:

1. Overdue/reminder events appear in pending endpoint and do not move to delivered.
2. No user reminder emails are observed.

Current likely causes:

1. n8n workflow polling or execution issue.
2. n8n connectivity issue to internal API endpoint http://api:8000.
3. Reminder delivery stage failure in n8n before delivery acknowledgment is posted.

Immediate operator action:

1. Confirm scheduler is enabled and creating events.
2. Confirm pending queue growth via GET /heartbeat-events/pending.
3. Confirm n8n workflows are running and reaching http://api:8000 successfully.
4. Confirm n8n posts delivery acknowledgments to POST /heartbeat-events/{event_id}/delivered only after successful send.
5. If troubleshooting from outside the Swarm network, verify n8n service availability at http://n8n.whistler.home.

## Runbook: Deployed API Image Drift

Symptoms:

1. Migration service runs with a new image but continuity_api remains on an older digest.
2. /health is green but expected code changes are not visible.

Diagnosis commands:

```bash
docker service inspect continuity_api --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}'
docker service ps continuity_api --no-trunc
docker service ls --format 'table {{.Name}}\t{{.Replicas}}\t{{.Image}}' | rg '^continuity_(api|migrate|postgres)'
```

Resolution:

1. Resolve the intended image digest from GHCR.
2. Re-run deployment with digest pinning:

```bash
scripts/deploy_swarm_release.sh \
	--image-ref ghcr.io/strnglybrwn/continuity@sha256:<digest>
```

3. Re-check continuity_api image digest and /health.

## Runbook: Check-in Link Rejected

Symptoms:

- POST /checkins/{token} renders the unavailable page.

Expected causes:

1. Token unknown
2. Token expired
3. Token already used
4. Token orphaned from deleted heartbeat

Important behavior:

- The UI intentionally does not disclose which cause occurred.

## Capacity and Scaling Notes (Current)

1. Scheduler is in-process and single-replica oriented today.
2. Event queue is DB-backed and can support external consumers.
3. Multi-replica API with scheduler enabled in every replica requires leader/election or singleton scheduling strategy before scale-out.

## Security Notes (Current)

1. Check-in token hashes are persisted, not raw tokens.
2. Database password should be supplied via secret file in production.
3. API endpoints currently have no auth boundary; deploy behind trusted network controls until auth is implemented.
