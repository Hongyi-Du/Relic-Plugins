# Tools and configuration reference

[中文](reference.zh-CN.md) · [User guide](guide.en.md)

The exact MCP schemas are exported from the shipped code in [Claude](api/claude.json), [Codex](api/codex.json), and [Bridge](api/bridge.json). Required fields, enums and descriptions in those files are authoritative. The host supplies session identity; never imitate another member by passing an actor override.

## Claude and Bridge

| Tool | Operations and main fields |
| --- | --- |
| `create` | `name`, `purpose`, `member`, optional `role`, `governance: leader|peer` |
| `join` | `org_id`, `member`, optional `role`; rejoining a seat replaces its carrier |
| `status` | Current member's organization, shared state, rules and outstanding work |
| `inbox` | Read unread messages; Bridge adds bounded `wait` in seconds (maximum 600) |
| `message` | `to: [member names]` or `["all"]`, `body`, optional `episode_id`; in Bridge, `reply_to` answers inside a message's thread (without `to`, the thread's participants get it) |
| `work` | `doc_read`, `doc_write`, `task`, `role`, `note`; in Bridge, `task` with status `done` needs `evidence` and a `report` (Markdown, at most 1000 characters) |
| `episode` | `open`, `close`, `reflect` |
| `protocol` | `propose`, `vote`, `use`, `list`; `supersedes` / `retire_target` for revisions/retirement |
| `review` | `list`, `approve`; approval refers to a concrete pending `request_id` |
| `panel` | Bridge only: open Tk organization window |
| `trajectory` | Bridge only: `request`, `answer`, `list`; approval-controlled export |

Example shared document:

```json
{"op":"doc_write","key":"interface","body":"The report uses UTF-8.","expected_revision":0}
```

Example message:

```json
{"to":["reviewer"],"body":"Please review the interface document and return your findings."}
```

A strong rule's `effect` is `deny`, `require_review`, or `require_before`. Selectors include `tools`, `input_contains`, `path_glob`, `members`, `roles`, `except_members`, and `except_roles`. A `require_before` rule uses `before:{tools,input_contains}`. A proposal uses a closed episode on which its author reflected. Under leader governance, adoption normally needs the leader and another member; peer governance uses majority approval. Read actual current governance in `status`.

```json
{"effect":"deny","tools":["Edit","Write"],"path_glob":"src/api/*","except_roles":["api-owner"],"reason":"Coordinate API changes with its owner."}
```

This is an optional example, not an installed default. Bridge maps supported Codex shell calls to `Bash` and patches to `Edit`; every patch path is checked by its path selector. Hook coverage is host-dependent.

## Standalone Codex / GPT

| Tool | Purpose |
| --- | --- |
| `org_discover`, `org_panel` | Discover local sessions; open member selection panel |
| `org_organize` | `start` / `status`, `request_id`, `data`; native or desktop formation |
| `org_context` | Current executor's authorized state, native inbox/outbox and protocol activity |
| `org_message` | `send`, `ack`, `dispatch`, `list`; edition-specific `data` payload |
| `org_work` | Versioned documents, tasks, episodes, reflections and member-local notes |
| `org_call` | Bounded text meeting with agenda, participants and 1–6 contribution rounds |
| `org_protocol` | Propose, agree/comment/vote/adopt, record use, revise, retire |
| `org_review` | Check a proposed action or record another member's exact-action review |
| `org_benchmark` | Optional developer integration; separate benchmark resources required |
| `org_scope_evolution` | Experimental developer registry for governed patch/scope overlays |

Most operations use `{org_id,operation,data}`. Read the shipped [operations](https://github.com/Hongyi-Du/Relic-Plugins/blob/main/editions/codex/plugins/relic-organization/skills/relic-organization/references/operations.md) and [native subagents](https://github.com/Hongyi-Du/Relic-Plugins/blob/main/editions/codex/plugins/relic-organization/skills/relic-organization/references/native-subagents.md) references for nested payloads and receipt semantics.

```json
{"operation":"start","request_id":"a-fresh-request-id","data":{"runtime":"native_subagents","execution_mode":"native","name":"Docs team","task":"Review the documentation","new_members":2}}
```

This records formation; actual host spawning follows separately. For uncertain outcomes, reuse the same request and key rather than issuing a new request. Native delivery remains pending until the actual recipient acknowledges.

Codex strong rules support `deny` and `require_peer_review`, with `tools`, optional `members`, `input_contains`, and `argument_equals`. Review receipts bind the exact arguments and protocol version, expire after one hour, and cannot be self-approved. Weak protocols have guidance, trigger and scope instead of blocking rules. A leader and required peers agree before activation; review the current governance setting rather than assuming a quorum.

## Environment variables

| Variable | Scope |
| --- | --- |
| `RELIC_HOME` | Claude / Bridge data directory; do not mix standalone Claude and Bridge stores |
| `RELIC_ORG_HOME` | Standalone Codex data directory |
| `RELIC_ORG`, `RELIC_MEMBER`, `RELIC_ROLE` | Explicit peer-seat startup for Claude/Bridge |
| `CODEX_THREAD_ID`, `CODEX_APP_TOOLS_PIPE_PATH` | Supplied by the host, not copied from another session |
| `CODEX_HOME` | Codex configuration root; inherited where supported |
| `CODEX_CLI_PATH` | Optional explicit Codex CLI path |
| `RELIC_MAX_WAIT` | Bridge inbox maximum; use 50 for the Claude Chat integration |
| `RELIC_ACTOR` | Dedicated standalone chat MCP configuration only; not a means to impersonate peers |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Bridge runner's Windows sandbox choice; host permissions still apply |
| `RELIC_CODEX_APP_SERVER`, `CODEX_MCP_NODE_PATH` | Advanced standalone Codex desktop adapter overrides |
| `RELIC_ORGANIZATIONBENCH_PATH` | Optional external developer benchmark checkout |

Credentials are not required by the plugin itself. Per-member environment configuration may contain secrets, so treat the local database and backups as private.

## Packaging and host references

Each edition is a local marketplace. The release installer prepares the machine-specific MCP and hook paths before registration. Do not install the unconfigured repository root as a single marketplace.

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins): local marketplace discovery and plugin manifests.
- [OpenAI submission boundary](https://developers.openai.com/plugins/deploy/submission): hook-dependent packages use manual desktop distribution; this release does not claim universal-directory approval.
- [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference): plugin components and path variables.
- [Claude hooks](https://code.claude.com/docs/en/hooks): command hook input/output and lifecycle.

Documentation checked for this release on 2026-10-24. Host capabilities can change independently of Relic.
