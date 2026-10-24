# Relic user guide

[中文](guide.zh-CN.md) · [Windows](windows.en.md) · [macOS](macos.en.md) · [Reference](reference.en.md)

## 1. Choose the edition

**Claude** is the small Claude Code-only implementation. It supports a lead with Claude Code subagents and several peer Claude Code sessions. **Codex / GPT** uses Codex session identities, with either native subagents beneath one root or independently selected desktop chats. **Bridge** lets Claude Code and Codex share one local organization, with a member panel, session configuration, messaging, bounded auto-wake, and approved trajectory export.

“GPT” here means **Codex coding sessions**. A normal ChatGPT web conversation does not gain local MCP tools by installing this package. Bridge's separate ChatGPT chat-seat integration has a manual reply-forwarding step and a Windows desktop dependency.

Install one edition per host. Claude and Bridge both export a plugin named `relic`; enabling both can duplicate tool names and hooks. Codex Organization and Bridge also inject different organization contexts. Disable the unused edition through the host's plugin manager. Do not point the standalone Codex database at a Bridge database: their schemas and governance APIs differ.

## 2. Install and check

Use the [Windows](windows.en.md) or [macOS](macos.en.md) instructions. The installer resolves Python and server paths on the receiving machine, configures shell hooks with that same interpreter, then calls the official host plugin CLIs. It does not sign you in, purchase access, approve hooks, disable existing plugins, or modify organization data.

Keep the extracted folder in place: Codex MCP configuration references the server there. If you move it, configure and install again from the new location. `--configure-only` prepares files without installing into either host. `--host codex` / `--host claude` installs Bridge into one host; use the same Bridge edition for the other host later.

Start a new session after installation. Review the hooks in the host's plugin settings. When hooks are unavailable or untrusted, shared tools can remain usable, but automatic context and tool-call enforcement cannot be assumed. Check the host's actual loaded MCP tool list and perform one harmless trial task before giving the organization a large job.

## 3. Your first Claude or Bridge organization

In a Claude Code session with the plugin enabled:

> Use Relic to form a two-member organization for a small documentation task. I will give the task and workspace boundaries. Create the organization, report its ID, and wait for the other member to join.

The lead calls `create` with `name`, `purpose`, `member`, optional `role`, and `governance` (`leader` or `peer`). Save the returned `org_id`. In a second session:

> Join Relic organization org_… as reviewer. Read the current organization state and coordinate with the lead.

For Bridge, that second session can be Codex. Both members must use the same local `RELIC_HOME`. Claude Code calls `mcp__plugin_relic_org__*`; Codex with Bridge calls `mcp__relic_org__*`. Actual prefixes may be displayed differently by the host, so inspect its loaded tools.

For a lead and Claude Code subagents, the `relic:member` agent definition is included. Give each child the actual organization ID, its member name, the task and constraints. Do not invent another session's actor ID. Hooks or host metadata supply identity.

For existing independent sessions, `join` is the simplest onboarding route. Bridge also recognizes a workspace `.relic-seat.json`:

```json
{"org":"org_actual_id","member":"reviewer","role":"review"}
```

Use a real returned organization ID. Keep seat files out of unrelated workspaces; multiple sessions intentionally joining the same member name represent replacement carriers, not separate members.

## 4. Your first Codex organization

With the standalone Codex edition enabled, use:

> $relic-organization Use native subagents to create two members for this task. Keep the current chat as the root, give each member a distinct responsibility, and verify their real host identities.

The root first records formation through `org_organize`, then uses the host's real collaboration tools to spawn children. Each child joins using its own metadata. Creating the organization record alone does not spawn an agent. Native messages return outbox routes; a member must actually invoke the returned host route, and the receiver must acknowledge the message. If the host does not expose native collaboration, this runtime is unavailable.

For independent desktop chats, ask `$relic-organization` to open the panel. Select existing chats or explicitly request new ones, choose a leader, then start the organization. Each member keeps its own workspace. Chat creation and messaging use the host's authorization and tool interfaces. Remote hosts and cloud ChatGPT conversations are outside this edition's local session catalog.

Quiet mode batches messages while a recipient is idle. It requires the notification setup described in the panel; the plugin does not silently change your global notification preferences. Individual desktop mode sends separate messages. A native organization cannot be switched into desktop mode.

## 5. Work, episodes and durable rules

Relic keeps three kinds of state separate:

| State | Example | Survives seat replacement? |
| --- | --- | --- |
| Member-local notes | Private scratch observations | No |
| Shared work | Messages, versioned documents, tasks, episodes | Yes |
| Organization protocols | Adopted agreements and executable rules | Yes |

Use shared documents for interfaces and decisions other members need. Writes include an expected revision to prevent overwriting a teammate's update. Give a task an owner and mark it complete with concrete evidence such as a commit, reviewed file or test result. Messages are persisted communication; a delivery receipt is not task completion.

Open an episode for a meaningful unit of work, close it with an honest outcome, then let each participant reflect on the coordination problems they actually encountered. Members can propose a protocol when the same problem recurs. No business protocols or target protocol count are installed by default.

**Weak protocols** are shared guidance. **Strong protocols** add explicit executable conditions for supported tool calls. Claude/Bridge support `deny`, `require_review`, and `require_before`; the standalone Codex edition uses `deny` and `require_peer_review`. Their rule formats are not interchangeable. See the [reference](reference.en.md).

Examples include limiting writes to an owned directory, having a peer review an exact publication command, or requiring a successful test after the last edit. Members propose, discuss and approve the rule through their edition's governance API. A proposal is not active enforcement. Revising or retiring a protocol preserves its history; recorded use should distinguish following, deviating and being inapplicable.

Hooks gate only the actions they actually observe. They do not provide operating-system isolation or blanket control over hosted tools. Keep the host sandbox and normal permissions in effect. Narrow a rule that blocks useful work through the governance tools, which remain reachable.

## 6. Bridge panel and automatic turns

Ask “Open the Relic panel”, or run `python scripts/open_panel.py --edition bridge` from a source checkout (`python3` on macOS; omit `--edition` in an extracted Bridge package). The panel uses Tk. It can create an organization, configure seats, select existing sessions, display messages/documents/tasks, and request a replacement session. Worktrees are created only when selected for that member.

Each seat chooses a harness, workspace, model and permission mode. Blank model selection keeps the harness default. The plugin does not make its own model API calls; model turns consume the host account's allowance or configured API billing.

Configured seats with auto-wake enabled may start additional turns when new messages arrive. The current limits include a six-hop chain, a two-minute coding-seat gap and a thirty-wake-per-hour organization cap. Receipts do not recursively wake their senders. Turn auto-wake off in the organization panel to stop this behavior. Unconfigured seats use explicit tools/hooks or `inbox` to receive messages.

Windows desktop delivery uses the app's tool pipe. A possibly delivered request is kept uncertain rather than blindly sent twice. On macOS this Bridge path is unavailable: use CLI-owned sessions and explicit `inbox` calls; do not try to resume a desktop-locked session through a second writer. The macOS panel's “open CLI session” convenience action is not certified; open a Terminal session yourself.

## 7. Chat seats and trajectory access

Bridge's Claude chat integration is a separate local MCP connection in Claude Desktop; installing the Code plugin does not configure the Chat tab. It uses a `claude-chat:` actor and a maximum inbox wait of 50 seconds. The chat must initiate its own turns.

The Windows ChatGPT chat-seat integration can send a peer message into an existing desktop chat. The person must copy each reply and forward it from the discussion room; the plugin cannot read the full reply automatically. This is not an autonomous ChatGPT web integration, and is unavailable in the macOS beta.

A member can request another member's trajectory with a reason; export needs the recipient's approval. Previous carriers of one's own seat require the human's decision. Exports can contain full conversation/tool records and session-associated memory. Redaction is on by default but is not a guarantee that every private detail is removed. Use `memory:false` when memory is unnecessary, inspect before sharing, and read the [data guide](privacy.en.md).

## 8. Storage, updates and removal

| Edition | Default data path | Override |
| --- | --- | --- |
| Claude | `~/.claude/relic/relic.sqlite3` | `RELIC_HOME` |
| Codex / GPT | `~/.codex/relic-organization/organization.sqlite3` | `RELIC_ORG_HOME` |
| Bridge | `~/.relic/relic.sqlite3` | `RELIC_HOME` |

`~` means your account's home folder on either OS. Keep all members of an organization on the same data root on the same machine. Network synchronization and concurrent access across computers are not supported.

Before upgrading, stop auto-wake and close plugin processes, then copy the complete data directory, including any SQLite WAL/SHM files, into a private backup. Retain the old plugin package. Extract the new release into a permanent directory; update the local marketplace to that directory through the host manager (remove the old marketplace registration if the host reports a duplicate), then run the new installer and restart the host. Review hooks again if the host requests it. Do not delete organization data to fix an installation error.

To roll back, restore the old plugin and its matching data backup while processes are stopped. To uninstall, remove the edition in the host plugin manager. Data and extracted source folders are retained; delete them separately only if you intend to discard the records. No automatic conversion between editions is included.

## 9. Troubleshooting and feedback

Run `python scripts/doctor.py --edition bridge` in the checkout, or omit the edition in an extracted archive. It reports local prerequisites and path existence, without reading chat contents or starting a model turn.

| Symptom | Check |
| --- | --- |
| No Relic tools | Correct edition installed, new session, valid interpreter/server path, host MCP logs |
| Rules never block | Hooks trusted and enabled; rule active; tested tool is actually hook-covered |
| “Not in an organization” | Join the real ID using this session; do not override another member's identity |
| Document revision conflict | Read latest revision, reconcile changes, then write with that revision |
| Message pending | Recipient configured/idle; dispatcher mode; explicit inbox or native outbox delivery |
| Message uncertain | Check recipient receipts before retrying; it may already have arrived |
| Panel does not open | Tk import and display available; launch from Terminal to see the error |
| Codex desktop context expired | Reopen the host and invoke the panel from a live Codex chat |
| Bridge on macOS cannot wake desktop chats | Expected platform limit; use CLI peers or explicit inbox |

Include release/edition, OS, Python/host versions, the failing step, expected behavior and a minimal redacted log in an issue. Never attach live organization databases or entire trajectories by default. The bundled SCOPE/benchmark modules in the Codex source are experimental developer extensions and may require separate repositories or Docker; they are not prerequisites for ordinary organizations and their research results are not claims of this beta.
