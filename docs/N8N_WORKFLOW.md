# n8n Workflow Build Spec (Reminder / Overdue-Warning / Escalation Flow)

## Goal

Build one n8n workflow that:

1. Triggers on a schedule and evaluates due heartbeats
2. Polls Continuity for pending heartbeat events
3. Branches by event_type: reminder_due, overdue, escalation_due
4. Prepares the matching payload (with a one-time check-in URL for reminder_due and overdue; no check-in URL for escalation_due)
5. Sends the matching email (to the owner for reminder_due/overdue, to the escalation contact for escalation_due)
6. Marks event delivered only after successful send
7. Optionally reports queue staleness from /heartbeat-events/metrics for operator alerting

Three event types now flow through this workflow:

- `reminder_due` — sent to the owner ahead of the due date. Includes a check-in link.
- `overdue` — sent to the owner once the heartbeat has lapsed (a second, more urgent warning). Includes a check-in link, and conditionally mentions the escalation contact/deadline if escalation is enabled.
- `escalation_due` — sent to the nominated escalation contact once the escalation delay has elapsed. Informational only, no check-in link (the contact cannot check in on the owner's behalf).

## Import File

An import-ready workflow JSON is provided at:

- docs/N8N_WORKFLOW_IMPORT.json

After importing:

1. Set environment variables in n8n.
2. Attach SMTP credentials to the Email - Send Reminder node.
3. Activate the workflow.

## Environment Variables (n8n)

Create these variables in n8n:

1. CONTINUITY_API_BASE_URL
- Preferred public value: https://continuity.boardmad.com
- Internal Swarm value: http://api:8000
- Use the public value when n8n runs outside the Docker Swarm network.
- Use the internal value when n8n runs on the same overlay network as the api service.

2. CONTINUITY_NOREPLY_FROM
- Example: continuity@whistler.home

3. CONTINUITY_PENDING_LIMIT
- Example: 50

## Workflow Metadata

1. Workflow Name
- Continuity MVP - Reminder Dispatch

2. Active
- true

3. Timezone
- Use server timezone or UTC

## Node-by-Node Specification

### Node 1

1. Name
- Trigger - Every 5 Minutes

2. Type
- Schedule Trigger

3. Key config
- Trigger Interval: Every X
- Value: 5
- Unit: Minutes

4. Output
- Single empty item to start execution

### Node 2

1. Name
- HTTP - Evaluate Due Heartbeats

2. Type
- HTTP Request

3. Key config
- Method: POST
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/evaluate-due
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000

4. Expected response
- {"evaluated": <int>, "changed": <int>}

### Node 3

1. Name
- HTTP - List Pending Events

2. Type
- HTTP Request

3. Key config
- Method: GET
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/pending
- Send Query Parameters: true
- Query Parameters:
  - limit: {{$env.CONTINUITY_PENDING_LIMIT || 100}}
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000

4. Expected response
- JSON array of event objects

### Node 4

1. Name
- Code - Expand Event Array

2. Type
- Code

3. Language
- JavaScript

4. Code
```javascript
const payload = $json;
if (!Array.isArray(payload)) {
  return [];
}

return payload.map((event) => ({ json: event }));
```

5. Purpose
- Convert array response into one n8n item per event

### Node 5

1. Name
- Switch - Route By Event Type

2. Type
- Switch

3. Condition
- Mode: Rules
- Value: {{$json.event_type}}
- Output 0 (reminder_due): equals reminder_due
- Output 1 (overdue): equals overdue
- Output 2 (escalation_due): equals escalation_due

4. Fallback
- No fallback output connected — any other event_type ends the branch intentionally.

### Node 6a

1. Name
- HTTP - Prepare Reminder Payload

2. Type
- HTTP Request

3. Key config
- Method: POST
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/{{$json.id}}/prepare-reminder
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000
- Continue On Fail: false

4. Expected response fields used downstream
- event_id
- heartbeat_id
- owner_name
- owner_email
- subject
- text_body
- html_body
- checkin_url

### Node 6b

1. Name
- HTTP - Prepare Overdue-Warning Payload

2. Type
- HTTP Request

3. Key config
- Method: POST
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/{{$json.id}}/prepare-overdue
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000
- Continue On Fail: false

4. Expected response fields used downstream
- event_id
- heartbeat_id
- owner_name
- owner_email
- subject
- text_body
- html_body
- checkin_url

### Node 6c

1. Name
- HTTP - Prepare Escalation Payload

2. Type
- HTTP Request

3. Key config
- Method: POST
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/{{$json.id}}/prepare-escalation
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000
- Continue On Fail: false

4. Expected response fields used downstream
- event_id
- heartbeat_id
- owner_name
- escalation_contact_name
- escalation_contact_email
- subject
- text_body
- html_body

Note: no checkin_url field — the escalation-contact email is informational only and does not carry a check-in action link.

### Node 7a

1. Name
- Email - Send Reminder

2. Type
- Email Send

3. Key config
- Credentials: your SMTP credential
- From Email: {{$env.CONTINUITY_NOREPLY_FROM}}
- To Email: {{$json.owner_email}}
- Subject: {{$json.subject}}
- Text: {{$json.text_body}}
- HTML: {{$json.html_body}}
- Continue On Fail: false

4. Operational rule
- This node must succeed before delivery is acknowledged

### Node 7b

1. Name
- Email - Send Overdue Warning

2. Type
- Email Send

3. Key config
- Credentials: your SMTP credential
- From Email: {{$env.CONTINUITY_NOREPLY_FROM}}
- To Email: {{$json.owner_email}}
- Subject: {{$json.subject}}
- Text: {{$json.text_body}}
- HTML: {{$json.html_body}}
- Continue On Fail: false

4. Operational rule
- This node must succeed before delivery is acknowledged

### Node 7c

1. Name
- Email - Send Escalation Notice

2. Type
- Email Send

3. Key config
- Credentials: your SMTP credential
- From Email: {{$env.CONTINUITY_NOREPLY_FROM}}
- To Email: {{$json.escalation_contact_email}}
- Subject: {{$json.subject}}
- Text: {{$json.text_body}}
- HTML: {{$json.html_body}}
- Continue On Fail: false

4. Operational rule
- This node must succeed before delivery is acknowledged

### Node 8

1. Name
- HTTP - Mark Event Delivered

2. Type
- HTTP Request

3. Key config
- Method: POST
- URL: {{$env.CONTINUITY_API_BASE_URL}}/heartbeat-events/{{$json.event_id}}/delivered
- Response Format: JSON
- Timeout: 30000
- Retry On Fail: true
- Max Tries: 3
- Wait Between Tries: 2000
- Continue On Fail: false

4. Output
- Delivered event payload (contains delivered_at)

### Node 9

1. Name
- Code - Execution Summary

2. Type
- Code

3. Language
- JavaScript

4. Code
```javascript
return [
  {
    json: {
      workflow: 'Continuity MVP - Reminder Dispatch',
      event_id: $json.id,
      heartbeat_id: $json.heartbeat_id,
      delivered_at: $json.delivered_at,
      status: 'delivered'
    }
  }
];
```

5. Purpose
- Produce compact execution output for run history and optional logging

## Connections (Exact)

1. Trigger - Every 5 Minutes -> HTTP - Evaluate Due Heartbeats
2. HTTP - Evaluate Due Heartbeats -> HTTP - List Pending Events
3. HTTP - List Pending Events -> Code - Expand Event Array
4. Code - Expand Event Array -> Switch - Route By Event Type
5. Switch - Route By Event Type (reminder_due) -> HTTP - Prepare Reminder Payload
6. Switch - Route By Event Type (overdue) -> HTTP - Prepare Overdue-Warning Payload
7. Switch - Route By Event Type (escalation_due) -> HTTP - Prepare Escalation Payload
8. HTTP - Prepare Reminder Payload -> Email - Send Reminder
9. HTTP - Prepare Overdue-Warning Payload -> Email - Send Overdue Warning
10. HTTP - Prepare Escalation Payload -> Email - Send Escalation Notice
11. Email - Send Reminder -> HTTP - Mark Event Delivered
12. Email - Send Overdue Warning -> HTTP - Mark Event Delivered
13. Email - Send Escalation Notice -> HTTP - Mark Event Delivered
14. HTTP - Mark Event Delivered -> Code - Execution Summary
15. Switch - Route By Event Type (no match) -> no connection

All three email-send nodes converge on the same HTTP - Mark Event Delivered node, since every prepare-* response includes event_id.

## Error Handling Pattern

Use workflow-level error handling plus node retries.

1. Keep Continue On Fail disabled for the Switch node and all HTTP/Email nodes in each branch.
2. Keep retries enabled on HTTP nodes.
3. If any Email - Send node fails, do not mark delivered.
4. Let the event remain pending so a later run can retry.

## Verification Checklist

After activation, confirm the following with one event of each type:

1. HTTP - Prepare Reminder Payload / Prepare Overdue-Warning Payload returns checkin_url; HTTP - Prepare Escalation Payload does not include a checkin_url.
2. Reminder and overdue-warning emails are sent to owner_email; escalation emails are sent to escalation_contact_email.
3. HTTP - Mark Event Delivered succeeds and sets delivered_at for each event type.
4. Event no longer appears in GET /heartbeat-events/pending.
5. Reminder and overdue-warning check-in links open the confirmation page.
6. Escalation email contains no check-in link (informational only, by design).

## Optional Second Workflow (Failure Alerts)

If desired, create a second workflow using Error Trigger:

1. Trigger: Error Trigger
2. Node: Email Send or Slack
3. Include fields in alert:
- workflow name
- failed node name
- execution URL
- error message

## Optional Queue Health Workflow

Add a lightweight scheduled workflow that:

1. Calls GET /heartbeat-events/metrics?stale_after_seconds=<threshold>
2. Evaluates stale_pending_alert
3. Sends operator alert when true

This mirrors the script behavior in scripts/daily_reminder_healthcheck.sh and helps
keep queue health visible even if the reminder dispatch flow is temporarily paused.

## Trigger Troubleshooting (When Nothing Runs)

If the workflow appears to do nothing, check these in order.

1. Workflow activation
- Confirm the workflow toggle is Active.
- Confirm Schedule Trigger is enabled and connected to HTTP - List Pending Events.

2. Trigger cadence and timezone
- Temporarily change schedule to every 1 minute for testing.
- Confirm n8n instance timezone and workflow timezone are aligned.

3. Test-run bypass
- Click Test Workflow or Execute Workflow from the editor.
- Confirm Node 2 (HTTP - Evaluate Due Heartbeats) executes first.
- Confirm Node 3 (HTTP - List Pending Events) executes after Node 2.

4. API base URL correctness
- Confirm CONTINUITY_API_BASE_URL points to Continuity API, not n8n UI.
- Correct values:
  - https://continuity.boardmad.com
  - http://api:8000
- If Node 2 cannot resolve api, use the public Continuity hostname instead.

5. Pending event availability
- If Node 3 returns an empty array, the workflow will appear idle.
- Confirm reminder_due events exist in GET /heartbeat-events/pending.

6. Data shape check
- Confirm Node 3 returns JSON array, so Code - Expand Event Array emits items.
- If Node 3 returns object/error text, Node 4 outputs zero items.

7. Filter branch check
- Confirm event_type exactly equals reminder_due, overdue, or escalation_due in Switch - Route By Event Type.
- Any other event_type falls through with no connection and ends intentionally.

8. Execution log inspection
- Open Executions and inspect latest run.
- Identify first node with zero items or error and fix forward from there.
