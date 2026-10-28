# Tools and configuration reference

[中文](reference.zh-CN.md) · [User guide](guide.en.md)

The exact MCP schemas are exported from the shipped code in [docs/api/relic.json](api/relic.json) (12 tools). Required fields, enums and descriptions in that file are authoritative. The host supplies session identity; never imitate another member by passing an actor override.

## Tools

Claude Code shows the tools as `mcp__plugin_relic_org__*`; Codex shows them as `mcp__relic_org__*`, and so does any session that the Relic App gives the Relic MCP server.

| Tool | Operations and main fields |
| --- | --- |
| `create` | `name`, `purpose`, `member`, optional `role`, `governance: leader|peer`; once a secretariat is marked, a member's `create` becomes a request for the secretary-general |
| `join` | `org_id`, `member`, optional `role`; rejoining a seat replaces its carrier; joining another organization adds a seat and keeps the session's others; joining one it sits in makes that its main seat |
| `status` | Current member's organization, shared state, rules and outstanding work; with `org` naming an organization below, that organization as seen from above |
| `inbox` | Read unread messages of every seat; bounded `wait` in seconds (maximum 600, lower with `RELIC_MAX_WAIT`) |
| `message` | `to: [member names]`, `["all"]` or `["human"]` (the person, who reads it in the Relic App), `body`, optional `episode_id`; `reply_to` answers inside a message's thread (without `to`, the thread's participants get it); `org`: an organization below, or one above to report to (a sender named `<org id>/<member>` is answered with that name in `to`) |
| `work` | `doc_read`, `doc_write`, `task`, `role`, `note`; `task` with status `done` needs `evidence` and a `report` (Markdown, at most 1000 characters); `org`: an organization below, for `task` (a new task needs an owner, one of its members) and `doc_read` |
| `episode` | `open`, `close`, `reflect` |
| `protocol` | `propose`, `vote`, `use`, `list`; `supersedes` / `retire_target` for revisions/retirement (`<org id>/<P#>` for a protocol inherited from above); `inherit: true` (or `downward: true`) makes the organizations below inherit it; `org`: an organization below (`propose` takes effect there at once, `list`), or one above (`use`) |
| `review` | `list`, `approve`; approval refers to a concrete pending `request_id` |
| `trajectory` | `request`, `answer`, `list`; approval-controlled export |
| `group` | `create {name, purpose, leader, parent?, members?}` makes a subgroup; `close {org}` (its leader); `reparent {parent, org?, reason}`, `leader {member, org?, reason}`, `dissolve {org?, reason}` ask to change a formal organization; `approve` / `deny {request_id, note}` (the secretary-general); `list` |
| `panel` | Open the Relic App on the person's screen |

Every tool except `create`, `join` and `panel` also takes `org` naming an organization the session sits in, by id or exact name: the call then acts as the session's member there, and that organization's protocols bind the session's tool calls until its turn ends. `inbox` with such an `org` reads only that seat's messages. A message that reached a seat other than the main one is shown as `[msg 12 · <organization> from <sender>]`. The [user guide](guide.en.md#6-organizations-above-and-below) describes organizations above and below, subgroups, the secretariat and ex officio seats.

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

This is an optional example, not an installed default. Relic maps supported Codex shell calls to `Bash` and patches to `Edit`; every patch path is checked by its path selector. In a session the Relic App runs without Relic hooks, ACP tool calls are mapped the same way (shell commands to `Bash`; edits, deletions and moves to `Edit`; reads to `Read`; searches to `Grep`; fetches to `WebFetch`) and checked when the session asks for permission; an action the session takes without asking cannot be stopped. Hook coverage is host-dependent.

## Environment variables

| Variable | Scope |
| --- | --- |
| `RELIC_HOME` | Data directory, `~/.relic` by default: the organization store and everything else Relic keeps |
| `RELIC_ACP_HOME` | Where the Relic App installs the ACP adapters; `RELIC_HOME/acp` by default |
| `RELIC_ORG`, `RELIC_MEMBER`, `RELIC_ROLE` | Start a session in a seat: the SessionStart hook joins that seat |
| `RELIC_SEAT`, `RELIC_SEAT_TOKEN` | Set by the Relic App for each session it starts: the seat (`<org id>/<member>`) and the token the App stored on the seat for that session. The Relic server answers as the seat's carrier while the token matches; do not set them by hand |
| `RELIC_LANG` | The person's language for task titles and reports; otherwise the App's language setting, then the system language |
| `RELIC_MAX_WAIT` | Lowers the inbox wait maximum; use 50 for the Claude Chat integration (the App uses at most 50 for the Relic server it gives a session) |
| `RELIC_ACTOR` | Dedicated chat MCP configuration only (`claude-chat:<name>`); not a means to impersonate peers |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Windows sandbox for the Codex sessions Relic starts (`unelevated` by default; empty keeps Codex's own choice); host permissions still apply |
| `CODEX_THREAD_ID`, `CODEX_APP_TOOLS_PIPE_PATH` | Supplied by the host, not copied from another session |
| `CODEX_HOME`, `CLAUDE_CONFIG_DIR` | Codex and Claude Code configuration roots; inherited where supported |
| `CODEX_CLI_PATH` | Optional explicit Codex CLI path |

Credentials are not required by the plugin itself. Per-member environment configuration may contain secrets, so treat the local database and backups as private.

## Packaging and host references

The package folder is one local marketplace, `relic-bridge`, with one plugin, `relic`; the marketplace keeps the earlier Bridge name so Bridge installs upgrade in place. The installer writes this computer's Python and paths into the plugin before it registers the folder, so run the installer rather than adding the folder to a host by hand.

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins): local marketplace discovery and plugin manifests.
- [OpenAI submission boundary](https://developers.openai.com/plugins/deploy/submission): hook-dependent packages use manual desktop distribution; this release does not claim universal-directory approval.
- [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference): plugin components and path variables.
- [Claude hooks](https://code.claude.com/docs/en/hooks): command hook input/output and lifecycle.

Host documentation was last checked on 2026-10-24. Host capabilities can change independently of Relic.
