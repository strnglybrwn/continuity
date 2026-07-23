# Continuity Development Guide

## Purpose

This guide describes the current local development workflow for Continuity.

It is focused on the implementation state on branch feature/reminder-delivery-content and should be updated as platform wiring progresses.

Production note: event-driven reminder workflows are orchestrated by n8n in the homelab Swarm. n8n reaches the API internally at http://api:8000 and the platform is externally exposed at https://continuity.whistler.home via Caddy.

## Prerequisites

1. Python 3.12+
2. PostgreSQL-compatible target (local or containerized)
3. pip and virtual environment tooling

## Local Environment Setup

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Required Configuration

Configuration uses CONTINUITY_ environment variables.

Important settings:

- CONTINUITY_DATABASE_HOST
- CONTINUITY_DATABASE_PORT
- CONTINUITY_DATABASE_NAME
- CONTINUITY_DATABASE_USER
- CONTINUITY_DATABASE_PASSWORD or CONTINUITY_DATABASE_PASSWORD_FILE
- CONTINUITY_HEARTBEAT_SCHEDULER_ENABLED
- CONTINUITY_HEARTBEAT_SCHEDULER_INTERVAL_SECONDS
- CONTINUITY_LIFECYCLE_DAY_SECONDS
- CONTINUITY_PUBLIC_BASE_URL

Notes:

1. Database password is required at runtime when the first DB session/engine is created.
2. CONTINUITY_LIFECYCLE_DAY_SECONDS supports accelerated testing (for example, 60 seconds per day).

## Database Migration Workflow

Run migrations:

```bash
alembic upgrade head
```

Create a new migration:

```bash
alembic revision --autogenerate -m "describe change"
```

## Running the API

Development run command:

```bash
uvicorn app.main:app --reload
```

The app serves:

- API endpoints under /heartbeats and /heartbeat-events
- check-in web pages under /checkins/{token}
- health endpoint at /health

## Scheduler Behavior in Development

The scheduler is off by default.

Enable it with:

```bash
export CONTINUITY_HEARTBEAT_SCHEDULER_ENABLED=true
export CONTINUITY_HEARTBEAT_SCHEDULER_INTERVAL_SECONDS=300
```

When enabled, it continuously evaluates active heartbeats and records due events/status changes.

## Tests and Quality Gates

Run formatting and lint checks:

```bash
ruff format --check app tests
ruff check app tests
```

Run tests:

```bash
CONTINUITY_DATABASE_PASSWORD=test-password pytest -q
```

Current observation:

Without a test DB password value, one API validation test may fail early during dependency setup because database configuration is resolved before request validation in that execution path.

## High-Value Local Test Scenarios

1. Accelerated lifecycle flow
- Set CONTINUITY_LIFECYCLE_DAY_SECONDS=60
- Create heartbeat
- Wait/simulate due time
- Verify overdue transition and events
- Submit check-in and verify reset

2. Token confirmation flow
- Issue token via service path/integration harness
- GET /checkins/{token} should only show confirmation form
- POST /checkins/{token} should redeem once and reset heartbeat

3. Event queue behavior
- GET /heartbeat-events/pending
- POST /heartbeat-events/{event_id}/prepare-reminder
- POST /heartbeat-events/{event_id}/delivered
- Verify idempotent delivered timestamp behavior
- An empty GET /heartbeat-events/pending response means no reminder/overdue events are queued at that moment.

## MVP Smoke Test Script

Use the smoke test script to exercise the live API integration path used by n8n.

Script location:

- scripts/mvp_reminder_smoke.sh

Default behavior:

1. Calls POST /heartbeat-events/evaluate-due.
2. Reads pending events and selects the first reminder_due event.
3. Calls prepare-reminder for the selected event.
4. Calls delivered for the same event.
5. Writes an evidence JSON file under /tmp.

Optional behavior:

- Set CONTINUITY_CONFIRM_CHECKIN=true to also GET and POST the returned check-in URL, then fetch heartbeat state for reset evidence.

Example run:

CONTINUITY_BASE_URL=https://continuity.whistler.home scripts/mvp_reminder_smoke.sh

Network note:

1. Run the script from an environment that can resolve and reach the target host.
2. From inside a Swarm-connected environment, you can target CONTINUITY_BASE_URL=http://api:8000.

## Current Development Gaps

The following is intentionally not complete yet:

1. Outbound email transport implementation
2. In-repository worker/dispatcher that reads pending events, sends reminder emails, issues tokens, and marks events delivered
3. End-to-end integration test proving reminder delivery to real mail target

Current integration context:

1. Workflow orchestration in production is handled by n8n outside this repository.
2. This repository currently provides the API contracts consumed by that workflow.
