# Tools and configuration reference

v0.7.1-beta.1 (plugin 0.18.1-beta.1) shares check/Reply rules, Copies and person-issued protocols across Windows
and macOS Apple silicon. Opening an older store adds `activity.paths`: an irreversible automatic schema migration
with no automatic downgrade. Back up before upgrading; restore that backup to roll back.

[中文](reference.zh-CN.md) · [User guide](guide.en.md)

The exact MCP schemas are exported from the shipped code in [docs/api/relic.json](api/relic.json) (12 tools). Required fields, enums and descriptions in that file are authoritative. The host supplies session identity; never imitate another member by passing an actor override.

## Tools

Claude Code shows the tools as `mcp__plugin_relic_org__*`; Codex shows them as `mcp__relic_org__*`, and so does any session that the Relic App gives the Relic MCP server.

| Tool | Operations and main fields |
| --- | --- |
| `create` | `name`, `purpose`, `member`, optional `role`, `governance: leader|peer`; once a secretariat is marked, a member's `create` becomes a request for the secretary-general |
| `join` | `org_id`, `member`, optional `role`; rejoining a seat replaces its carrier; joining another organization adds a seat and keeps the session's others; joining one it sits in makes that its main seat |
| `status` | Current member's organization, shared state, rules and outstanding work; with `org` naming an organization below, that organization as seen from above; naming one above, a read-only view of it (purpose, members and roles, protocol titles, open tasks, documents) |
| `inbox` | Read unread messages of every seat; bounded `wait` in seconds (maximum 600, lower with `RELIC_MAX_WAIT`); `message_id` rereads one addressed message, read or unread, and ignores `wait`. An empty inbox lists open assigned tasks. |
| `message` | `to: [member names]`, `["all"]` or `["human"]` (the person, who reads it in the Relic App), `body`, optional `episode_id`; `reply_to` answers inside a message's thread (without `to`, the thread's participants get it); `org`: an organization below yours, or one above it to report to: the one right above yours first (past it the message still goes through, and its result names the first choice) (a sender named `<org id>/<member>` is answered with that name in `to`); with `to: ["human"]`, `recommend` (and `within` minutes, at most 60, and `executor`) makes it a question that runs out: if the person has not written to you by then, the executor gets one notice to go ahead with the recommendation. While the person is away from the computer (no keyboard or mouse for 10 minutes, or the screen locked, and nothing typed to a member or in the Relic App meanwhile) a question does not wait: the result says to go ahead now, and an open one goes ahead once the person leaves; a plain message to `human` says in its result that nobody reads it now. The person's words a message quotes verbatim get Relic's check under it (`[Relic check W<n>]`: when and in which seat's session the person typed them) |
| `work` | `doc_read`, `doc_write`, `task`, `role`, `note`, `drive` (off with `until`: a time, `6h`, `quota:codex` or `idle`; without it Relic asks every 2 hours whether the reason is still there), `said` (`query`, `limit`, `hours`: what the person typed into the sessions of seats in your organization and the ones below it); `task` with status `done` needs `evidence` and a `report` (Markdown, at most 1000 characters); `org`: an organization below, for `task` (a new task needs an owner, one of its members) and `doc_read`; an organization above, at any depth, for `doc_read` only |
| `episode` | `open`, `close`, `reflect` |
| `protocol` | `propose`, `vote`, `use`, `list`; `supersedes` / `retire_target` for revisions/retirement (`<org id>/<P#>` for a protocol inherited from above); `inherit: true` (or `downward: true`) makes the organizations below inherit it; `org`: an organization below (`propose` takes effect there at once, `list`), or one above (`use`) |
| `review` | `list`, `approve`; `approve` refers to a concrete pending `request_id` and lets another member's call through once after you checked it (`note`: what you checked). Relic asks the reviewers of a new request at once; nobody approves their own call |
| `trajectory` | `request`, `answer`, `list`; approval-controlled export |
| `group` | `create {name, purpose, leader, parent?, members?}` makes a subgroup; `close {org}` (its leader); `reparent {parent, org?, reason}`, `leader {member, org?, reason}`, `dissolve {org?, reason}` ask to change a formal organization; `approve` / `deny {request_id, note}` (the secretary-general); `list` |
| `panel` | Open the Relic App on the person's screen |

Every tool except `create`, `join` and `panel` also takes `org` naming an organization the session sits in, by id or exact name: the call then acts as the session's member there, and that organization's protocols bind the session's tool calls until its turn ends. `inbox` with such an `org` reads only that seat's messages. A message that reached a seat other than the main one is shown as `[msg 12 · <organization> from <sender>]`. The [user guide](guide.en.md#6-organizations-above-and-below) describes organizations above and below, subgroups, the secretariat and ex officio seats.

For example, `inbox {"message_id": 3784, "org": "org_example"}` returns that message's full text only if it was
addressed to the session's seat there. Without `org`, every held seat is eligible. Missing or unaddressed ids return
an error. An empty inbox is not an empty task list: check `status`. Hook output is limited to 9500 characters;
only whole delivered messages are marked read, and previews/omissions remain available through `inbox`.
An explicit `org` that names a held seat selects that identity even above the main organization, including replies.
Replies to cross-organization participants remain in that seat's thread and also reach those participants in their
own organizations; omitting `to` includes them along with local thread participants.

Codex's hook configuration is separate from Claude's: the installer supplies `commandWindows` with PowerShell's
call operator for quoted interpreter paths. The hook caps output at 9500 characters; Codex uses
`additionalContextLimit: 0` to deliver that already-bounded context without another preview cut.

Example shared document:

```json
{"op":"doc_write","key":"interface","body":"The report uses UTF-8.","expected_revision":0}
```

Example message:

```json
{"to":["reviewer"],"body":"Please review the interface document and return your findings."}
```

A strong rule's `effect` is `deny`, `require_review`, `require_before`, or `check`. Selectors include `tools`, `input_contains`, `path_glob`, `members`, `roles`, `except_members`, and `except_roles`. A `require_before` rule uses `before:{tools,input_contains}`. A rule stops one call, never the work: a call a rule sends to review gets a request, Relic asks the members who can approve it at once, and one approval lets that exact call through once; a call a rule denies has no request and is done another way. Nobody approves their own call. A proposal uses a closed episode on which its author reflected. Under leader governance, adoption normally needs the leader and another member; peer governance uses majority approval. Read actual current governance in `status`.

A `check` rule runs a program its members wrote before every call it covers. It must name its `tools` (not every tool) and carries `code` (Python using the standard library only, defining `check(call)` that returns `{"decision": "allow" | "deny" | "review", "reason": "..."}`; a deny or a review needs a reason), `examples` (2 to 12 `{call, expect, note?}` the rule covers, at least one `allow` and one `deny` or `review`; every one runs when the protocol is proposed and has to come out as expected) and `on_error` (`allow`, the default, or `deny`: what happens to the call when the program times out, raises, answers something invalid or crashes). A protocol with a check rule needs `summary_for_person`, a description in the person's language. `call` holds `tool`, `input`, `member`, `role`, `harness`, `org_id`, `org_name`, `protocol_id`, `protocol_title`, `recent` (the member's latest 20 tool calls in the organization, newest first), `last_edit_at`/`last_edit_ts` and `now`/`now_ts`. The program runs in a process of its own (`-I -S -X utf8`, 3 seconds, 8 KB of answer, a temporary folder, almost no environment; on Windows a job object ends what it starts and caps its memory at 512 MB). That is not a security boundary: members read the code with `protocol op=list protocol_id=<P#>` before they vote, the code's sha256 recorded at proposal is compared before every run, and the person can retire the protocol at once from the Relic App. Such a protocol takes effect by the organization's vote and is copied to the person (see the [guide](guide.en.md), section 5). Plugin versions before 0.16.0 treat `check` as `require_review`.

A rule may name `Reply` instead of tools (`tools: ["Reply"]`, effect `check` or `deny`, no other tool and no `path_glob`): it judges the reply that ends a member's turn, the text the person reads, when the turn ends. Its call is `{"tool": "Reply", "input": {"text": ...}}`, and a program on it answers allow or deny. A reply that breaks it sends the member back once to write it again. The person can also issue a protocol in any organization directly (the Relic App's `POST /api/org/<org id>/protocols`): it takes effect at once with no vote, binds the organizations below when inherited, and only the person can retire it.

```json
{"effect":"deny","tools":["Edit","Write"],"path_glob":"src/api/*","except_roles":["api-owner"],"reason":"Coordinate API changes with its owner."}
```

This is an optional example, not an installed default. Relic maps supported Codex shell calls to `Bash` and patches to `Edit`; every patch path is checked by its path selector. In a session the Relic App runs without Relic hooks, ACP tool calls are mapped the same way (shell commands to `Bash`; edits, deletions and moves to `Edit`; reads to `Read`; searches to `Grep`; fetches to `WebFetch`) and checked when the session asks for permission; an action the session takes without asking cannot be stopped. Hook coverage is host-dependent.

## Environment variables

| Variable | Scope |
| --- | --- |
| `RELIC_HOME` | Data directory, `~/.relic` by default: the organization store and everything else Relic keeps |
| `RELIC_ACP_HOME` | ACP installation root; `RELIC_HOME/acp` by default. The built-in locked pair uses `adapters/<lockfile-hash>` below it; an existing legacy installation remains a fallback |
| `RELIC_PYTHON_PATH` | Explicit native arm64 Python 3.11+ for the macOS `install.command` launcher |
| `RELIC_NODE_PATH`, `RELIC_NPM_PATH` | Explicit Node/npm executables; App-managed members require Node 22+, native arm64 on macOS |
| `RELIC_ORG`, `RELIC_MEMBER`, `RELIC_ROLE` | Start a session in a seat: the SessionStart hook joins that seat |
| `RELIC_SEAT`, `RELIC_SEAT_TOKEN` | Set by the Relic App for each session it starts: the seat (`<org id>/<member>`) and the token the App stored on the seat for that session. The Relic server answers as the seat's carrier while the token matches; do not set them by hand |
| `RELIC_LANG` | The person's language for task titles and reports; otherwise the App's language setting, then the system language |
| `RELIC_MAX_WAIT` | Lowers the inbox wait maximum; use 50 for the Claude Chat integration (the App uses at most 50 for the Relic server it gives a session) |
| `RELIC_ACTOR` | Dedicated chat MCP configuration only (`claude-chat:<name>`); not a means to impersonate peers |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Windows sandbox for the Codex sessions Relic starts (`unelevated` by default; empty keeps Codex's own choice); host permissions still apply |
| `RELIC_CLAUDE_DESKTOP_ENABLED` | `1` opts into macOS Claude Desktop delivery when no saved enablement setting exists. A supported CLI probe, recent public Desktop Stop observations and per-delivery receipts are still required |
| `CODEX_THREAD_ID`, `CODEX_APP_TOOLS_PIPE_PATH` | Supplied by the host, not copied from another session. On macOS the endpoint must be a private same-user Unix socket and pass the required-tools probe |
| `CODEX_HOME`, `CLAUDE_CONFIG_DIR` | Codex and Claude Code configuration roots; inherited where supported |
| `CODEX_CLI_PATH` | Optional explicit Codex CLI path |
| `CLAUDE_CODE_EXECUTABLE` | Optional explicit Claude Code executable path |

Credentials are not required by the plugin itself. Per-member environment configuration may contain secrets, so treat the local database and backups as private.

## Application lifecycle (development branch)

`python3 -X utf8 scripts/open_app.py` starts or opens the server for the selected `RELIC_HOME`. Use `--no-window` to
start without opening a browser, `--status` to read JSON status without starting a server, `--stop` to shut down the
authenticated instance, and `--restart` to stop/start it while reusing its port when available. `--port` selects a
preferred port. On Windows use `python` in place of `python3`.

One server owns each data directory. Stop/restart verify the instance and ownership lock rather than killing the PID
in `app.json`; an older or unverified server is refused. Closing the browser leaves the server running. Shutdown
cleans up owned sessions/processes without deleting organizations. For macOS launcher installation and data-preserving
removal, see the [macOS guide](macos.en.md).

`python3 scripts/doctor.py --probe-desktop` explicitly checks desktop capabilities without sending messages. Status
reads do not initiate probes. macOS Codex/ChatGPT delivery needs a successful host bridge handshake and host
authorization. Claude Desktop needs explicit enablement, Claude Code 2.1.224+ verified by the probe and recent public
Desktop Stop evidence for its target seat; exact peer/receipt checks still apply to each send. These capabilities are
conditional, and the current machine's acceptance blockers are recorded in [validation](validation.md).

## Packaging and host references

The package folder is one local marketplace, `relic-bridge`, with one plugin, `relic`; the marketplace keeps the earlier Bridge name so Bridge installs upgrade in place. The installer writes this computer's Python and paths into the plugin before it registers the folder, so run the installer rather than adding the folder to a host by hand.

- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins): local marketplace discovery and plugin manifests.
- [OpenAI submission boundary](https://developers.openai.com/plugins/deploy/submission): hook-dependent packages use manual desktop distribution; this release does not claim universal-directory approval.
- [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference): plugin components and path variables.
- [Claude hooks](https://code.claude.com/docs/en/hooks): command hook input/output and lifecycle.

Host documentation was last checked on 2026-10-24. Host capabilities can change independently of Relic.
