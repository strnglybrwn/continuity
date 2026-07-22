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

After the GitHub Actions workflow completes successfully:

```bash
sudo docker service update \
  --image ghcr.io/strnglybrwn/continuity:latest \
  --with-registry-auth \
  --force \
  continuity_api
```

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
- [ ] Docker Swarm updated
- [ ] Health endpoint verified
- [ ] OpenAPI verified
- [ ] Smoke tests completed

---

# Document History

| Date | Change |
|------|--------|
| 2026-07-22 | Initial deployment guide created. |
