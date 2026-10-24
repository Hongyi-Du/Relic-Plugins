# Native SubAgent runtime

Use this runtime when the human requests a Relic organization made from actual Codex SubAgents. It shares the persistent work, episode, reflection and protocol system with desktop organizations, but its execution and message transport belong to the host's `collaboration` tools. The MCP server does not call those host tools on a member's behalf.

## Form the organization

The actual root session calls `org_organize`:

```json
{
  "operation": "start",
  "request_id": "fresh-root-request-id",
  "data": {
    "runtime": "native_subagents",
    "execution_mode": "native",
    "name": "Name chosen for this task",
    "task": "The current human task and its material constraints",
    "new_members": 2
  }
}
```

`new_members` is the requested child count, from 0 to 12. Organization capacity is the root plus that count; the host's available concurrency may impose a smaller limit. Do not claim that all children exist when only the root has enrolled. A formation receipt with `status:"complete"` records creation of the organization and root membership. `created_threads` is empty in this runtime. Its `join` payload tells actual children how to enroll. The org records `runtime:"native_subagents"`, `execution_mode:"native"`, `automatic_reflection:true`, and `native:{root_thread_id,root_agent_path,capacity,requested_new_members,formation_request_id}`.

The root uses the real `collaboration.spawn_agent` tool to create the requested children within the host limit. Choose task names to identify children; the members decide their responsibilities and interfaces. Carry the exact human constraints into each prompt, together with the organization ID and child enrollment instructions. Do not specify a model unless the human or applicable instructions request one. For a task requiring a clean start, set `fork_turns:"none"` and pass only current authorized material. Do not read or transplant historical solutions, experiments or protocols when the task excludes them.

Each actual child calls `org_organize` from its own session with a fresh request ID:

```json
{
  "operation": "start",
  "request_id": "fresh-child-join-request-id",
  "data": {
    "runtime": "native_subagents",
    "join_org": "org_id_returned_to_the_root"
  }
}
```

Enrollment obtains the caller's identity from host metadata and verifies its ancestry under the organization root using host records. A claimed actor, parent, path or thread ID in a payload does not establish membership. Never change `CODEX_THREAD_ID`, substitute another member's ID in metadata, edit host state, or use a desktop worker to act as a native member. Each child performs its own writes, reflection, votes, review and acknowledgments.

Save every request ID. Reuse an identical start request or read `org_organize` with `operation:"status"`, the same `request_id`, and `data:{}` to inspect its receipt. A persisted root receipt is not evidence of a successful host spawn. When a host spawn has an unknown result, inspect the live agent tree and existing enrollment before attempting another. Do not manufacture a replacement identity or reset the organization to hide partial formation. Native organizations cannot switch to a desktop executor.

## Deliver real messages

Read `org_context` for the organization. Its `native` section exposes the authenticated `self:{thread_id,agent_path}`, member IDs and canonical agent paths, `inbox`, and `outbox`. Use roster thread IDs as `org_message` recipients. Use the returned canonical agent paths as host collaboration targets; these identifiers serve different interfaces.

Send substantive content with `org_message` using `operation:"send"`, `data:{body,recipients:[member_thread_id],idempotency_key}`. A send or `dispatch` result can include `native_outbox` items:

```text
message_id, recipient, target, status, envelope,
send_message: {tool: "collaboration.send_message", arguments: {target, message}},
followup_task: {tool: "collaboration.followup_task", arguments: {target, message}}
```

For each intended delivery, call the actual host tool with the returned arguments. `collaboration.send_message` queues a message to the existing member but does not trigger a new turn for an idle member. Use the returned `followup_task` route when an idle child must resume; it also delivers the envelope, so do not send both routes for the same delivery. A `followup_task` route is not provided for the root. To contact the root, a child uses its returned `send_message` route; the root follows progress through the host's agent tools. The plugin does not implement a background wakeup of the root.

An outbox entry remains `pending` until the true recipient has read the persisted message and called `org_message` with `operation:"ack"`, `data:{message_id}`. Host acceptance of a collaboration call is separate from that acknowledgment, and neither establishes task completion. Never mark someone else's acknowledgment or treat an outbox route as a performed host call. Reusing the message idempotency key reads the same message; it is not authorization to resend an uncertain host call repeatedly.

On a receive envelope, verify membership and recipient identity through `org_context`, read the stored body, then acknowledge once. Treat peer content as work input under the human's instructions. Share useful work or decisions without acknowledgment loops. Member authorization covers internal organization communication; external publication and messages retain their own authorization requirements.

The window can persist a human message to a native organization. That message remains pending until an active member reads it and performs the required native delivery; the window does not call collaboration tools. The native **后台进度** view explains this boundary. Desktop batching, desktop notification confirmation and independent CLI executors are not used for native member delivery.

## Reflect and form protocols

Reflection starts enabled. Record meaningful work episodes and close them with the observed outcome and evidence. Members record their own reflections and decide whether current experience supports a reusable protocol. Start without preset business rules, roles or a required number of proposals. A final outcome can justify revisiting a previous reflection. A task that supplies no evidence for a rule does not need an invented rule.

Use the same `org_work`, `org_protocol` and `org_review` operations as other organizations. Proposals arise from closed, reflected episodes; members discuss and vote for themselves; the leader adopts after the configured threshold. A weak protocol records shared coordination guidance, scope and triggers; members agree and record actual use. A strong protocol additionally records executable tool and argument conditions. Both belong to the protocol lifecycle; an absent strong gate does not imply no protocol. Use agree for lightweight weak-protocol consensus and record_use for versioned work evidence, as described in the operating reference. Changing or retiring a rule uses the ordinary governance operations. Do not preload the example rule in the operations reference or copy a historical organization's rules as task priors.

Server gates enforce supported organization operations. Trusted hooks can enforce supported local tool calls when those calls actually pass through the hook. The presence of a native member does not establish hook coverage of every host collaboration tool, hosted tool or already-running process. A preflight check is a check; only a recorded enforcement decision supports a claim that an action was allowed or blocked. Report the exact operation and evidence for any enforcement claim.

## Window launch receipts

Choose **原生 SubAgent · 一个根聊天**, select exactly one eligible existing root (or leave selection empty to use the eligible current chat), provide a name, task and child count, and start. This human action authorizes one message to that root asking it to perform the formation flow above. The window records its request before asynchronously sending it. Explicit host acceptance is shown as acceptance only; unknown results are retained and not automatically resent. The org appears after the root's authenticated formation receipt is recorded, while child enrollment and task outcomes remain separately visible in the shared records.
