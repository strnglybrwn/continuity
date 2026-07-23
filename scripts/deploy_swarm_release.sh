#!/usr/bin/env bash
set -euo pipefail

# Deploy a specific Continuity image to Docker Swarm, including migrations.
# Supports either:
# 1) --image-ref ghcr.io/strnglybrwn/continuity@sha256:<digest>
# 2) --tag sha-<commit>

STACK_NAME="${STACK_NAME:-continuity}"
VERIFY_URL="${VERIFY_URL:-https://continuity.whistler.home/health}"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/strnglybrwn/continuity}"
DATABASE_HOST="${DATABASE_HOST:-${STACK_NAME}_postgres}"
BACKEND_NETWORK="${BACKEND_NETWORK:-}"

IMAGE_REF=""
IMAGE_TAG=""

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy_swarm_release.sh --image-ref <image-ref>
  scripts/deploy_swarm_release.sh --tag <image-tag>

Options:
  --image-ref  Full image reference, e.g.
               ghcr.io/strnglybrwn/continuity@sha256:...
  --tag        Image tag published by CI, e.g. sha-6a9ebc3

Environment overrides:
  STACK_NAME   Docker stack name (default: continuity)
  VERIFY_URL   Health endpoint to verify (default: https://continuity.whistler.home/health)
  IMAGE_REPO   Container repository (default: ghcr.io/strnglybrwn/continuity)
  DATABASE_HOST Database host used by migration job (default: <STACK_NAME>_postgres)
  BACKEND_NETWORK Overlay network used by migration job (auto-detected when unset)

Notes:
  - Run this on a Docker Swarm manager host.
  - Requires secret continuity_postgres_password to exist.
  - Requires network continuity_backend to exist.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-ref)
      IMAGE_REF="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -n "$IMAGE_REF" && -n "$IMAGE_TAG" ]]; then
  echo "Use either --image-ref or --tag, not both." >&2
  exit 2
fi

if [[ -z "$IMAGE_REF" && -z "$IMAGE_TAG" ]]; then
  echo "You must provide --image-ref or --tag." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not installed." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  cat <<'EOF' >&2
Cannot connect to Docker daemon.

Actions:
1. Start Docker Desktop (or ensure dockerd is running).
2. If targeting a remote engine, export DOCKER_HOST for that daemon.
3. Re-run this script from a Swarm manager host/context.
EOF
  exit 1
fi

SWARM_STATE="$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo unknown)"
IS_MANAGER="$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo false)"

if [[ "$SWARM_STATE" != "active" ]]; then
  echo "Docker Swarm is not active for the current Docker context (state: $SWARM_STATE)." >&2
  echo "Use a Swarm-enabled context/host, then re-run." >&2
  exit 1
fi

if [[ "$IS_MANAGER" != "true" ]]; then
  echo "Current Docker node is not a Swarm manager (ControlAvailable=false)." >&2
  echo "Run this script on a manager node or switch Docker context to a manager." >&2
  exit 1
fi

if [[ -n "$IMAGE_TAG" ]]; then
  IMAGE_REF="${IMAGE_REPO}:${IMAGE_TAG}"
fi

if [[ -z "$BACKEND_NETWORK" ]]; then
  POSTGRES_SERVICE="${STACK_NAME}_postgres"
  if docker service inspect "$POSTGRES_SERVICE" >/dev/null 2>&1; then
    NETWORK_ID="$(docker service inspect "$POSTGRES_SERVICE" --format '{{with index .Spec.TaskTemplate.Networks 0}}{{.Target}}{{end}}' 2>/dev/null || true)"
    if [[ -n "$NETWORK_ID" ]]; then
      BACKEND_NETWORK="$(docker network inspect "$NETWORK_ID" --format '{{.Name}}' 2>/dev/null || true)"
    fi
  fi

  if [[ -z "$BACKEND_NETWORK" ]]; then
    if docker network inspect "${STACK_NAME}_continuity_backend" >/dev/null 2>&1; then
      BACKEND_NETWORK="${STACK_NAME}_continuity_backend"
    elif docker network inspect continuity_backend >/dev/null 2>&1; then
      BACKEND_NETWORK="continuity_backend"
    fi
  fi
fi

if [[ -z "$BACKEND_NETWORK" ]]; then
  BACKEND_NETWORK="continuity_backend"
  echo "Creating missing overlay network: ${BACKEND_NETWORK}"
  docker network create --driver overlay --attachable "$BACKEND_NETWORK" >/dev/null
fi

MIGRATE_SERVICE_NAME="${STACK_NAME}_migrate_$(date +%s)"
TMP_STACK_FILE="$(mktemp)"
trap 'rm -f "$TMP_STACK_FILE"' EXIT

echo "Using image: $IMAGE_REF"
echo "Using migration network: $BACKEND_NETWORK"
echo "Using migration database host: $DATABASE_HOST"

echo "Rendering stack file with pinned api image..."
awk -v image_ref="$IMAGE_REF" '
  BEGIN { in_api = 0 }
  /^  api:$/ { in_api = 1; print; next }
  in_api && /^  [a-zA-Z0-9_-]+:$/ { in_api = 0 }
  in_api && /^    image:/ { print "    image: " image_ref; next }
  { print }
' deploy/stack.yml > "$TMP_STACK_FILE"

echo "Running database migrations..."
docker service create \
  --name "$MIGRATE_SERVICE_NAME" \
  --network "$BACKEND_NETWORK" \
  --secret continuity_postgres_password \
  --env CONTINUITY_DATABASE_HOST="$DATABASE_HOST" \
  --env CONTINUITY_DATABASE_PORT=5432 \
  --env CONTINUITY_DATABASE_NAME=continuity \
  --env CONTINUITY_DATABASE_USER=continuity \
  --env CONTINUITY_DATABASE_PASSWORD_FILE=/run/secrets/continuity_postgres_password \
  --restart-condition none \
  --with-registry-auth \
  "$IMAGE_REF" \
  alembic upgrade head >/dev/null

docker service logs -f "$MIGRATE_SERVICE_NAME"
docker service rm "$MIGRATE_SERVICE_NAME" >/dev/null

echo "Deploying stack ${STACK_NAME}..."
docker stack deploy \
  -c "$TMP_STACK_FILE" \
  --with-registry-auth \
  "$STACK_NAME"

echo "Verifying health at ${VERIFY_URL}..."
curl -kfsS --max-time 20 "$VERIFY_URL" | cat

echo
echo "Deployment complete."
