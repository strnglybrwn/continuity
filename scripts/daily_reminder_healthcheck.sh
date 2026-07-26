#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${CONTINUITY_BASE_URL:-https://continuity.boardmad.com}"
STALE_AFTER_SECONDS="${CONTINUITY_STALE_AFTER_SECONDS:-3600}"
EVALUATE_FIRST="${CONTINUITY_EVALUATE_FIRST:-true}"

require_tool() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required tool: $name" >&2
    exit 1
  fi
}

require_tool curl
require_tool jq

api_get() {
  local path="$1"
  curl -fsS "$BASE_URL$path"
}

api_post() {
  local path="$1"
  curl -fsS -X POST "$BASE_URL$path"
}

echo "Using API base URL: $BASE_URL"

echo "Stale alert threshold: ${STALE_AFTER_SECONDS}s"

if [[ "$EVALUATE_FIRST" == "true" ]]; then
  evaluation_json="$(api_post "/heartbeat-events/evaluate-due")"
  echo "Evaluation: $(echo "$evaluation_json" | jq -c '.')"
fi

metrics_json="$(api_get "/heartbeat-events/metrics?stale_after_seconds=${STALE_AFTER_SECONDS}")"

pending_total="$(echo "$metrics_json" | jq -r '.pending_total')"
pending_reminder_due_total="$(echo "$metrics_json" | jq -r '.pending_reminder_due_total')"
stale_pending_alert="$(echo "$metrics_json" | jq -r '.stale_pending_alert')"
stale_reminder_due_total="$(echo "$metrics_json" | jq -r '.stale_reminder_due_total')"
oldest_pending_age_seconds="$(echo "$metrics_json" | jq -r '.oldest_pending_age_seconds')"

echo "Pending events: $pending_total"
echo "Pending reminder_due events: $pending_reminder_due_total"
echo "Oldest pending age seconds: $oldest_pending_age_seconds"
echo "Stale reminder_due events: $stale_reminder_due_total"

if [[ "$stale_pending_alert" == "true" ]]; then
  echo "ALERT: stale pending reminder events detected" >&2
  exit 3
fi

echo "Reminder queue healthcheck passed"
