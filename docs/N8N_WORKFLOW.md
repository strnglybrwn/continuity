# n8n Workflow Build Spec (MVP Reminder Flow)

## Goal

Build one n8n workflow that:

1. Triggers on a schedule and evaluates due heartbeats
2. Polls Continuity for pending heartbeat events
3. Selects reminder_due events
4. Prepares reminder payload and one-time check-in URL
5. Sends reminder email
6. Marks event delivered only after successful send

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
- Preferred public value: https://continuity.whistler.home
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
- IF - Is Reminder Due Event

2. Type
- If

3. Condition
- Left Value: {{$json.event_type}}
- Operation: equals
- Right Value: reminder_due

4. True branch
- Continue flow

5. False branch
- End (no action)

### Node 6

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

### Node 7

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
4. Code - Expand Event Array -> IF - Is Reminder Due Event
5. IF - Is Reminder Due Event (true) -> HTTP - Prepare Reminder Payload
6. HTTP - Prepare Reminder Payload -> Email - Send Reminder
7. Email - Send Reminder -> HTTP - Mark Event Delivered
8. HTTP - Mark Event Delivered -> Code - Execution Summary
9. IF - Is Reminder Due Event (false) -> no connection

## Error Handling Pattern

Use workflow-level error handling plus node retries.

1. Keep Continue On Fail disabled for nodes 5, 6, and 7.
2. Keep retries enabled on HTTP nodes.
3. If Email - Send Reminder fails, do not mark delivered.
4. Let the event remain pending so a later run can retry.

## Verification Checklist

After activation, confirm the following with one reminder event:

1. HTTP - Prepare Reminder Payload returns checkin_url.
2. Email is sent to owner_email with expected subject/body.
3. HTTP - Mark Event Delivered succeeds and sets delivered_at.
4. Event no longer appears in GET /heartbeat-events/pending.
5. Reminder email check-in link opens confirmation page.

## Optional Second Workflow (Failure Alerts)

If desired, create a second workflow using Error Trigger:

1. Trigger: Error Trigger
2. Node: Email Send or Slack
3. Include fields in alert:
- workflow name
- failed node name
- execution URL
- error message

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
  - https://continuity.whistler.home
  - http://api:8000
- If Node 2 cannot resolve api, use the public Continuity hostname instead.

5. Pending event availability
- If Node 3 returns an empty array, the workflow will appear idle.
- Confirm reminder_due events exist in GET /heartbeat-events/pending.

6. Data shape check
- Confirm Node 3 returns JSON array, so Code - Expand Event Array emits items.
- If Node 3 returns object/error text, Node 4 outputs zero items.

7. Filter branch check
- Confirm event_type exactly equals reminder_due in IF - Is Reminder Due Event.
- Any other event_type follows false branch and ends intentionally.

8. Execution log inspection
- Open Executions and inspect latest run.
- Identify first node with zero items or error and fix forward from there.
