# Operational payloads

All session operations bind the caller to the host's session metadata / `CODEX_THREAD_ID`. Do not pass an arbitrary sender ID. `org_context` exposes the authoritative roster, leader, authorization, object IDs and current revisions.

## Runtime and formation

For a native SubAgent organization, read [the native runtime reference](native-subagents.md). The actual root calls `org_organize start` with a fresh `request_id` and `data:{runtime:"native_subagents",execution_mode:"native",name,task,new_members}`. The root is enrolled with reflection enabled and no task-specific protocol. It must then call the host's real `collaboration.spawn_agent`; the server only returns the persisted org and join instructions. Each actual child joins itself with `data:{runtime:"native_subagents",join_org:org_id}` and its own fresh request ID. Host identity and root ancestry are verified; payload IDs do not authorize impersonation. A complete formation receipt covers root enrollment, not host spawning or task completion.

Independent desktop chat formation retains `data:{name,task,new_members,include_current,members,leader,governance,execution_mode,delivery_mode,project_id}` with `execution_mode` of `quiet` or `desktop`. It creates user-owned chats through the desktop host. These are a separate runtime, and native organizations cannot switch to desktop execution. Both runtimes retain their own request IDs; `status` uses the same ID and `data:{}`. Never create a new request to conceal an unknown host outcome.

## Shared work

`org_work` accepts `{org_id, operation, data}`. Example data:

```json
{"key":"release-plan","body":"...","expected_revision":0}
```

Use `document_write` to create (revision 0) or update. `task_update` accepts `title`, `owner`, `status`, `evidence`; updating an existing task needs `task_id` and `expected_revision`. Status is `open`, `working`, `blocked`, `done` or `cancelled`. `done` needs `evidence: ["..."]`.

`episode_open`: `{title,participants:[thread_id]}`; participants default to the caller. A member can have one explicitly open episode. `episode_close`: `{episode_id,outcome,summary,evidence:[str]}`. Outcome is `success`, `failure`, `partial`, `cancelled` or `observed`. The owner or leader closes it. `episode_reflect`: `{episode_id,body}`; each participant records their own reflection.

## Messaging and meeting

`org_message` accepts `{org_id,operation,data}`. `send` data:

```json
{"body":"Please inspect proposal proto_... and record your own comment and vote.","recipients":["actual-selected-thread-id"],"idempotency_key":"fresh-uuid","reply_to":"msg_..."}
```

`episode_id` links work messages or meeting contributions to their episode. Participants may reference a closed work episode as provenance; a closed meeting rejects new contributions, so use a separate work message for later results. `ack` uses `{message_id}`. `dispatch` uses `{}` and dispatches only the caller's pending messages. A claimed `sending` or `uncertain` delivery is never automatically resent; inspect the destination through host `read_thread` if necessary. A failed transport is not completed communication. `org_context` retains the body for recipients to read.

For `runtime:"native_subagents"`, `send` and `dispatch` expose `native_outbox` routes. Use `org_context.native` to inspect authenticated IDs, canonical agent paths, inbox and outbox. Call the actual returned `collaboration.send_message` route, or its `collaboration.followup_task` route when an idle child must resume; do not call both for one envelope. The root has no followup route. These routes do not deliver by themselves, and native messages remain pending until the real recipient acknowledges. Use host agent inspection rather than desktop `read_thread` to inspect a native member. Do not substitute native member IDs into desktop chat delivery or start a quiet worker for native organizations.

`org_call`: `{org_id,agenda,participants:[thread_id],rounds:3}`. This creates an episode, invites others and limits each participant to 1-6 contributions as chosen. It does not collect responses synchronously. Read the shared message transcript and continue when replies arrive. Close through `episode_close`.

In explicitly selected `desktop` (individual delivery) mode only, if the direct desktop bridge is unavailable but native host tools are available, use `send_message_to_thread` with the selected destination's exact thread/host IDs and this prompt. Quiet mode keeps messages queued; do not bypass its batching or notification setup:

```text
$relic-organization receive
{"org_id":"...","message_id":"...","to":"..."}
Read org_context to validate the authorization and retrieve this message, then acknowledge it once.
```

Recipient acknowledgment becomes the durable receipt. Leave uncertain native delivery status unchanged until a recipient acknowledges; do not forge a receipt. The destination must share the same local organization database. Cloud and remote-host sessions are not supported in this version.

## Weak coordination protocols

`org_protocol propose` takes `{episode_id,title,rationale,strength:"weak",trigger,scope,guidance,evidence:[refs],supersedes?}`. Guidance includes the responsibilities and repeatable steps agreed in current work. No blocking `rules` are accepted. The author must participate in the source episode; a closed episode also needs that author's reflection. An open episode may establish an agreement before its later reflection.

`agree {protocol_id,body}` records only the calling member's acceptance and discussion. The proposal becomes active when the configured quorum including the leader agrees. No separate formal ballot or adoption call is needed for this path. Existing comment/vote/adopt also works. Agreement does not imply actual use or a successful task.

For both strengths, `record_use {protocol_id,version,idempotency_key,work_unit,outcome,note,evidence:[refs]}` saves the real member's report. `outcome` is `followed`, `deviated`, or `inapplicable`; evidence must refer to completed work, not a future plan. The same member/key and identical content return the same record; changed content under that key is rejected. Use references bind the exact active version. Records are member-reported evidence, not automatic execution attestations. `org_context.protocol_activity` separates lifetime use records/work units from enforcement events in the requested event range.

Revisions use `supersedes`, keeping the old version active until agreement/adoption. Retirement preserves history. Weak/strong changes use a new version; strong replacements still require strong governance. Legacy records with no strength are strong. Weak protocols never enter the tool gate or satisfy strong peer-review requirements.

An unregistered shared agreement used in work can still be a protocol. Registration provides durable discovery and measurement; it is not the definition of a protocol. Retrospective host analysis must identify original messages/documents/use evidence without creating fake member approvals or historical use records.

## Strong executable protocols

`org_protocol` accepts `{org_id,operation,data}`. A `propose` example:

```json
{
  "episode_id":"ep_...",
  "title":"Review this release command before publication",
  "rationale":"The episode exposed a release coordination failure; exact command review fixes this boundary.",
  "rules":[{
    "tools":["Bash"],
    "input_contains":["git push"],
    "effect":"require_peer_review",
    "reason":"A different member reviews the exact publication command."
  }]
}
```

This is an optional example, not a preinstalled rule. `tools` uses glob patterns against the native tool name and short MCP name; shell `exec_command` normalizes to `Bash`. `input_contains` is a case-insensitive AND over serialized arguments; `argument_equals` maps dotted argument paths to exact values. Optional `members` limits the rule to selected IDs. These are explicit selectors, not semantic understanding of every equivalent shell command. Use actual host tool names and test both matching and nonmatching calls.

`comment`: `{protocol_id,body}`. `vote`: `{protocol_id,vote:"approve"|"reject",reason}`. `adopt`: `{protocol_id}`; leader only, recorded discussion and quorum. `leader_with_peer` needs leader + one other (one approval for a one-member organization); `majority` needs leader + more than half the roster. `retire`: `{protocol_id,reason}`, leader only. Human panel retirement is also available.

An amendment passes the same `propose` payload with `supersedes: "current-active-protocol-id"`. A proposal's rules are immutable; change them by proposing another version. Votes bind to the proposal, never to mutable prose.

`org_context.protocol_activity` summarizes recorded execution evidence over `after_event` (default: all retained events). Per-protocol fields distinguish `enforcement_attempts`, `blocked_attempts`, `allowed_attempts`, `preflight_checks`, and `operation_errors_after_allow`; `review_receipts` is the lifetime receipt total. Recent decisions include source (server/hook/preflight), exact action hash, protocol snapshots/versions, argument field hashes, nonprivate key/revision, episode/turn/tool-use IDs and nearby same-member event status. A preflight denial is not a prevented execution. A server denial is retained even when the rejected operation rolls back. Legacy wrapper events are excluded from counts. Older unlogged calls cannot be reconstructed as zero blocks. Raw commands, source and prompts remain in their original chat, reachable by the actor through the action/context references.

`org_review` check: `{org_id,operation:"check",data:{tool:"Bash",arguments:{command:"git push origin main"},subject:"selected-member-id"}}` returns an exact `action_hash` and gate decision. Another member records a review: `{org_id,operation:"record",data:{protocol_id,subject,tool,arguments,evidence:["inspected artifact X and validation Y"]}}`. The receipt expires after one hour. Modifying arguments or adopting a revised protocol invalidates it. This records a member's evidence-backed judgment; it is not independent CI attestation.

## Installation boundary

The plugin packages a local MCP server and local hooks. The desktop bridge adapts the installed built-in `codex-app-tools` server; it does not copy its source or expose arbitrary host calls. Trust hooks through the Codex UI before relying on automatic context, episode collection or blocking. Native SubAgent identity does not establish hook coverage of every collaboration tool. Report enforcement only for the actual server-gated or hook-gated operation supported by evidence. If trust is unavailable, MCP shared work and native messaging can still operate, but universal tool blocking and automatic episodes are unverified.
