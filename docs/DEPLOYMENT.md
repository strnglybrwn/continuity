# Continuity Deployment Guide

## Purpose

This document defines the supported deployment and release process for the Continuity platform.

It is maintained alongside the source code and should be updated whenever the deployment architecture, release workflow or operational procedures change.

---

# Deployment Principles

The following principles govern all deployments.

- Git is the single source of truth.
- GitHub Actions is the only supported mechanism for producing release container images.
- Release images are never built or pushed manually.
- Every deployed image must originate from a successful CI build.
- Docker Swarm deployments consume images published to GitHub Container Registry (GHCR).
- All production deployments are reproducible from source control.

---

# Release Workflow

```
Feature Branch
      │
      ▼
Local Development
      │
      ▼
Local Testing
      │
      ▼
Commit
      │
      ▼
Merge to master
      │
      ▼
Push to GitHub
      │
      ▼
GitHub Actions
    • Ruff Format Check
    • Ruff Lint
    • Pytest
    • Multi-platform Build
    • Publish to GHCR
      │
      ▼
Docker Swarm Service Update
      │
      ▼
Deployment Verification
```

---

# CI/CD Pipeline

The GitHub Actions workflow performs:

- Source checkout
- Python dependency installation
- Ruff formatting validation
- Ruff linting
- Pytest execution
- Multi-platform Docker build
- Publication to GitHub Container Registry

Supported platforms:

- linux/amd64
- linux/arm64

---

# Docker Swarm Deployment

The Swarm stack definition is version-controlled at
[`deploy/stack.yml`](../deploy/stack.yml). It is the single source of truth
for the `continuity` stack (the `api` and `postgres` services, secrets,
networks, and volumes). Do not maintain a separate copy of this file outside
the repository.

The stack references the image by tag through the `CONTINUITY_IMAGE_TAG`
variable, defaulting to `latest`. Deployments should pin an explicit,
immutable tag produced by GitHub Actions (`sha-<commit>` or a semver tag)
rather than relying on `latest`, so the running stack always matches a known
commit.

## First-time setup

These prerequisites are created once per Swarm host and are not part of the
stack file:

```bash
docker secret create continuity_postgres_password -
docker network create --driver overlay --attachable edge
```

## 1. Run database migrations

Migrations are applied via a one-shot service using the same image that is
about to be deployed, before the `api` service is updated:

```bash
export CONTINUITY_IMAGE_TAG=sha-<commit>

docker service create \
  --name continuity_migrate \
  --network continuity_backend \
  --secret continuity_postgres_password \
  --env CONTINUITY_DATABASE_HOST=postgres \
  --env CONTINUITY_DATABASE_PORT=5432 \
  --env CONTINUITY_DATABASE_NAME=continuity \
  --env CONTINUITY_DATABASE_USER=continuity \
  --env CONTINUITY_DATABASE_PASSWORD_FILE=/run/secrets/continuity_postgres_password \
  --restart-condition none \
  --with-registry-auth \
  "ghcr.io/strnglybrwn/continuity:${CONTINUITY_IMAGE_TAG}" \
  alembic upgrade head

docker service logs -f continuity_migrate
docker service rm continuity_migrate
```

Confirm the migration logs show a successful `alembic upgrade head` before
proceeding.

## 2. Deploy the stack

```bash
export CONTINUITY_IMAGE_TAG=sha-<commit>

docker stack deploy \
  -c deploy/stack.yml \
  --with-registry-auth \
  continuity
```

`docker stack deploy` reconciles the running services against the stack
file, so this both creates the stack on first use and applies rolling
updates thereafter. There is no separate `docker service update --force`
step when the tag actually changes; it is only needed to force a
re-pull when redeploying the same tag.

---

# Deployment Verification

Verify the running API.

```bash
curl -k https://continuity.whistler.home/health
```

Verify published endpoints.

```bash
curl -k https://continuity.whistler.home/openapi.json \
| jq '.paths | keys'
```

Verify service status.

```bash
sudo docker service ps continuity_api
```

---

# Rollback

Rollback to the previous working deployment.

```bash
sudo docker service rollback continuity_api
```

If the rolled-back version depends on a database schema that a subsequent
migration already changed, a forward-fix migration is required; Alembic
migrations are not automatically reversed by a service rollback.

---

# Common Issues

## exec format error

### Cause

A single-architecture image has been deployed to a node with a different processor architecture.

### Resolution

Do not manually build or push release images.

Merge into `master`, allow GitHub Actions to publish the multi-platform image, then redeploy.

---

# Release Checklist

- [ ] Working tree clean
- [ ] Feature branch merged into master
- [ ] GitHub Actions passed
- [ ] Multi-platform image published
- [ ] `CONTINUITY_IMAGE_TAG` set to the published tag (not `latest`)
- [ ] Migration job run and logs confirmed clean
- [ ] Docker Swarm stack deployed
- [ ] Health endpoint verified
- [ ] OpenAPI verified
- [ ] Smoke tests completed

---

# Document History

| Date | Change |
|------|--------|
| 2026-07-23 | Updated external verification endpoint hostname to continuity.whistler.home and aligned docs with Caddy exposure. |
| 2026-07-22 | Version-controlled `deploy/stack.yml`, added pre-deploy migration job, and pinned image tag rollout. |
| 2026-07-22 | Initial deployment guide created. |
