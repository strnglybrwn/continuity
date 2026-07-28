# Continuity

Continuity is a self-hosted digital deadman's switch platform.

It tracks scheduled check-ins (heartbeats), raises reminder and overdue events when a check-in is missed, and supports escalation to a nominated contact with optional attachments.

## What the Application Does

Core capabilities:

1. Heartbeat lifecycle management
- Create and track heartbeats for an owner.
- Configure interval, reminder lead time, and escalation timing.
- Move heartbeat states through active and overdue lifecycle phases.

2. Check-in flow
- Generate one-time check-in links.
- Redeem links exactly once.
- Reset heartbeat due timing when check-in is confirmed.

3. Event queue APIs for workflow orchestration
- Publish pending lifecycle events (reminder_due, overdue, escalation_due).
- Provide send-ready payloads for reminder, overdue warning, and escalation notifications.
- Mark events delivered only after successful handling.

4. Escalation attachments
- Store heartbeat-specific escalation attachments.
- Return attachment metadata in escalation payloads.
- Provide attachment content endpoints for workflow download and email attachment delivery.

5. Operations dashboard
- View heartbeat status and lifecycle timeline.
- Edit policy times directly (reminder, overdue, escalation).
- Manage escalation contacts and attachments.

## High-Level Architecture

Continuity is implemented as a FastAPI service with PostgreSQL persistence, and uses n8n as the external workflow orchestrator for email delivery.

### Runtime components

1. continuity_api (FastAPI)
- API endpoints
- dashboard and check-in pages
- optional in-process scheduler

2. continuity_postgres (PostgreSQL)
- heartbeat, check-in, token, event, and attachment data

3. n8n workflow automation
- polls pending events
- prepares payloads
- downloads escalation attachments
- sends emails
- posts delivered acknowledgments

### Layered application design

1. API layer: endpoint contracts and web pages
2. Domain layer: heartbeat and notification concepts
3. Service layer: lifecycle logic, token issuance/redemption, payload preparation
4. Persistence layer: SQLAlchemy models and session/engine wiring
5. Scheduler: periodic due-evaluation loop

## API and Workflow Model (MVP)

Typical event processing sequence:

1. POST /heartbeat-events/evaluate-due
2. GET /heartbeat-events/pending
3. Route by event_type:
- reminder_due -> POST /heartbeat-events/{event_id}/prepare-reminder
- overdue -> POST /heartbeat-events/{event_id}/prepare-overdue
- escalation_due -> POST /heartbeat-events/{event_id}/prepare-escalation
4. For escalation_due, download each attachment from returned content_url_path.
5. Send email.
6. POST /heartbeat-events/{event_id}/delivered after successful send.

## CI/CD and Build Pipeline

GitHub Actions workflow: .github/workflows/ci.yml

### Trigger rules

1. Push to master
2. Push tags matching v*
3. Pull requests targeting master

### Test job (required before publish)

1. Set up Python 3.12
2. Install project dependencies
3. Check formatting:
- ruff format --check app tests
4. Lint:
- ruff check app tests
5. Test:
- CONTINUITY_DATABASE_PASSWORD=my-test-password pytest -v

### Publish job (push events only)

Runs only after Test succeeds.

1. Build multi-platform image - my homelab is made up of a range of silicon
- linux/amd64
- linux/arm64
2. Push image to GHCR with tags:
- latest (default branch)
- sha-<commit>
- semver tags where applicable

## Docker Swarm Deployment

Use the repository deployment script as the supported path:

scripts/deploy_swarm_release.sh --tag sha-<commit>

The script handles:

1. Swarm manager/context validation
2. One-shot alembic migration job
3. Rendering stack file with pinned API image
4. docker stack deploy with registry auth
5. Health verification against the configured URL

### Prerequisites

1. Docker Swarm manager context
2. Stack/network prerequisites available
3. Secret continuity_postgres_password exists
4. CI image already published to GHCR

### Recommended deployment flow

1. Merge to master and push.
2. Wait for GitHub Actions success and image publish.
3. Deploy:

scripts/deploy_swarm_release.sh --tag sha-<commit>

4. Verify:
- GET /health responds healthy
- continuity_api service image is updated
- service tasks are stable

### Deterministic deploy option

For immutable rollouts, deploy by digest:

scripts/deploy_swarm_release.sh --image-ref ghcr.io/strnglybrwn/continuity@sha256:<digest>

## Configuration Overview

Environment variables are prefixed with CONTINUITY_.

Commonly used settings:

1. Database
- CONTINUITY_DATABASE_HOST
- CONTINUITY_DATABASE_PORT
- CONTINUITY_DATABASE_NAME
- CONTINUITY_DATABASE_USER
- CONTINUITY_DATABASE_PASSWORD or CONTINUITY_DATABASE_PASSWORD_FILE

2. Scheduler and lifecycle
- CONTINUITY_HEARTBEAT_SCHEDULER_ENABLED
- CONTINUITY_HEARTBEAT_SCHEDULER_INTERVAL_SECONDS
- CONTINUITY_LIFECYCLE_DAY_SECONDS

3. URL generation
- CONTINUITY_PUBLIC_BASE_URL

## Repository Structure

- app/: FastAPI app, API endpoints, services, templates, persistence
- migrations/: Alembic migrations
- deploy/: Docker Swarm stack file
- scripts/: deploy and operational helper scripts
- docs/: architecture, development, deployment, operations, n8n workflow guidance
- tests/: test suite

## Operational Notes

1. Continuity currently relies on n8n for outbound mail orchestration.
2. Event delivery acknowledgement should only be posted after email send success.
3. Escalation attachments are fetched via the API content endpoint and attached by workflow tooling.
4. Keep production link generation on HTTPS public base URL.

## License

This project is currently published under MIT license.
