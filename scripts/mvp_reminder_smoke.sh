#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${CONTINUITY_BASE_URL:-https://continuity.whistler.com}"
LIMIT="${CONTINUITY_PENDING_LIMIT:-100}"
EVENT_ID="${CONTINUITY_EVENT_ID:-}"
CONFIRM_CHECKIN="${CONTINUITY_CONFIRM_CHECKIN:-false}"
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

if [[ "$EVALUATE_FIRST" == "true" ]]; then
  echo "Evaluating due heartbeats before polling events..."
  evaluation_json="$(api_post "/heartbeat-events/evaluate-due")"
  echo "Evaluation result: $(echo "$evaluation_json" | jq -c '.')"
fi

if [[ -z "$EVENT_ID" ]]; then
  echo "Fetching pending events..."
  pending_json="$(api_get "/heartbeat-events/pending?limit=$LIMIT")"

  EVENT_ID="$(echo "$pending_json" | jq -r '.[] | select(.event_type == "reminder_due") | .id' | head -n1)"

  if [[ -z "$EVENT_ID" || "$EVENT_ID" == "null" ]]; then
    echo "No reminder_due event found in pending queue." >&2
    echo "Tip: set CONTINUITY_EVENT_ID to target a specific event." >&2
    exit 2
  fi
fi

echo "Selected event_id: $EVENT_ID"

echo "Preparing reminder payload..."
prepare_json="$(api_post "/heartbeat-events/$EVENT_ID/prepare-reminder")"

heartbeat_id="$(echo "$prepare_json" | jq -r '.heartbeat_id')"
checkin_url="$(echo "$prepare_json" | jq -r '.checkin_url')"
owner_email="$(echo "$prepare_json" | jq -r '.owner_email')"
subject="$(echo "$prepare_json" | jq -r '.subject')"

echo "Prepared reminder for heartbeat_id: $heartbeat_id"
echo "Recipient: $owner_email"
echo "Subject: $subject"
echo "Check-in URL: $checkin_url"

before_heartbeat_json="$(api_get "/heartbeats/$heartbeat_id")"

checkin_get_status=""
checkin_post_status=""
after_heartbeat_json=""

if [[ "$CONFIRM_CHECKIN" == "true" ]]; then
  echo "Running check-in confirmation flow..."

  checkin_get_status="$(curl -sS -o /tmp/continuity_checkin_get.html -w "%{http_code}" "$checkin_url")"
  checkin_post_status="$(curl -sS -o /tmp/continuity_checkin_post.html -w "%{http_code}" -X POST "$checkin_url")"

  after_heartbeat_json="$(api_get "/heartbeats/$heartbeat_id")"

  echo "Check-in GET status: $checkin_get_status"
  echo "Check-in POST status: $checkin_post_status"
fi

echo "Marking event as delivered..."
delivered_json="$(api_post "/heartbeat-events/$EVENT_ID/delivered")"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
evidence_file="/tmp/continuity_mvp_smoke_${timestamp}.json"

jq -n \
  --arg base_url "$BASE_URL" \
  --arg event_id "$EVENT_ID" \
  --arg heartbeat_id "$heartbeat_id" \
  --arg checkin_url "$checkin_url" \
  --arg confirm_checkin "$CONFIRM_CHECKIN" \
  --arg checkin_get_status "$checkin_get_status" \
  --arg checkin_post_status "$checkin_post_status" \
  --argjson prepare "$prepare_json" \
  --argjson delivered "$delivered_json" \
  --argjson before_heartbeat "$before_heartbeat_json" \
  --argjson after_heartbeat "${after_heartbeat_json:-null}" \
  '{
    base_url: $base_url,
    event_id: $event_id,
    heartbeat_id: $heartbeat_id,
    checkin_url: $checkin_url,
    confirm_checkin: ($confirm_checkin == "true"),
    checkin_get_status: (if $checkin_get_status == "" then null else ($checkin_get_status | tonumber) end),
    checkin_post_status: (if $checkin_post_status == "" then null else ($checkin_post_status | tonumber) end),
    before_heartbeat: $before_heartbeat,
    after_heartbeat: $after_heartbeat,
    prepare_reminder_response: $prepare,
    delivered_response: $delivered
  }' > "$evidence_file"

echo "Smoke test complete."
echo "Evidence written to: $evidence_file"
