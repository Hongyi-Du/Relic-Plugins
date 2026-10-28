# Relic user guide

**Current public release: Windows only. macOS is not released and awaits real Mac testing.**

[中文](guide.zh-CN.md) · [Windows](windows.en.md) · [macOS](macos.en.md) · [Reference](reference.en.md)

## 1. What Relic is

Relic is one product in one package: the **Relic plugin** for Claude Code and Codex, and the **Relic App**. The plugin gives a Claude Code or Codex session the Relic tools and hooks, so the session can form or join an organization. The App is a desktop chat for your organizations and the bridge between their members: members can run inside it as Claude Code or Codex sessions, and the App brings Relic into those sessions itself. Every member of an organization uses the same local store, whatever host it runs on. Organizations can stand above and below one another, and one session can sit in several of them (section 6).

“GPT” members here are **Codex coding sessions**. A ChatGPT conversation does not gain Relic tools by installing this package; a ChatGPT chat in the desktop app can hold a seat, with a manual reply-forwarding step (section 8).

v0.2.0-beta.1 had three editions: Relic Claude, Relic Codex / GPT and Relic Bridge. They are merged: Bridge became Relic. If you used one of them, read [section 10](#10-coming-from-an-earlier-edition).

## 2. Install and check

Use the [Windows installation guide](windows.en.md). The [macOS document](macos.en.md) is an unreleased development draft. The installer resolves Python and server paths on the receiving machine and configures the plugin's MCP server and shell hooks with that same interpreter. Then, for each host, it calls the official host plugin CLI: `<cli> plugin marketplace add <folder>`, then `claude plugin install relic@relic-bridge` or `codex plugin add relic@relic-bridge`. In Claude Code it first disables the earlier editions that register the same tool names (`relic@relic-claude`, `relic@relic-local`; best effort). On Windows it makes a desktop shortcut named Relic that opens the App. It does not sign you in, purchase access, download anything, call a model, approve hooks or modify organization data.

Keep the extracted folder in place: the plugin's MCP configuration and the shortcut point to files there. If you move it, run the installer again from the new location. `--host` chooses the hosts: `auto` (the default) installs into every host whose CLI is found; `claude`, `codex` or `both` names them, and a named host that is not installed stops the installer with an error; `none` changes no host and leaves you with the App alone. `--configure-only` prepares the folder without changing any host or making a shortcut, `--no-shortcut` skips the shortcut, and `--open` opens the App when the installation is done.

Members that run in the Relic App get Relic from the App, so their host needs no plugin. For other Claude Code and Codex sessions, including your own, start a new session after installation and review the hooks in the host's plugin settings. When hooks are unavailable or untrusted, shared tools can remain usable, but automatic context and tool-call enforcement cannot be assumed. Check the host's actual loaded MCP tool list and perform one harmless trial task before giving the organization a large job.

## 3. Your first organization

In a Claude Code or Codex session with the plugin enabled:

> Use Relic to form a two-member organization for a small documentation task. I will give the task and workspace boundaries. Create the organization, report its ID, and wait for the other member to join.

The lead calls `create` with `name`, `purpose`, `member`, optional `role`, and `governance` (`leader` or `peer`). Save the returned `org_id`. Once you have marked a secretariat (section 6), `create` returns a request id instead: the organization is made, with the lead in it, when the secretary-general or you approve the request. In a second session, Claude Code or Codex:

> Join Relic organization org_… as reviewer. Read the current organization state and coordinate with the lead.

Both members must use the same local `RELIC_HOME`. Claude Code calls `mcp__plugin_relic_org__*`; Codex calls `mcp__relic_org__*`. Actual prefixes may be displayed differently by the host, so inspect its loaded tools.

In the Relic App, New organization creates an organization and Add member adds its members (section 4).

For a lead and Claude Code subagents, the `relic:member` agent definition is included. Give each child the actual organization ID, its member name, the task and constraints. Do not invent another session's actor ID. Hooks or host metadata supply identity. A Codex subagent works inside its parent's seat.

For existing independent sessions, `join` is the simplest onboarding route. A session started with `RELIC_ORG` and `RELIC_MEMBER` (optionally `RELIC_ROLE`) in its environment takes that seat when it starts, and so does a session whose workspace has a `.relic-seat.json`:

```json
{"org":"org_actual_id","member":"reviewer","role":"review"}
```

Use a real returned organization ID. Keep seat files out of unrelated workspaces; multiple sessions intentionally joining the same member name represent replacement carriers, not separate members. A session that joins another organization keeps the seats it already holds: one session can sit in several organizations (section 6).

## 4. Adding members in the Relic App

Add member (in the sidebar, the Overview pane, or File → Add member…) offers three ways for a member to run:

- **Run in the App**: the App hosts the member's session. Choose Claude Code or Codex, a model and a folder (by default `~/.relic/workspaces/<org>/<member>`); the member can also be made the organization's secretary. It takes its seat, reads the organization and waits for its task.
- **Command line or desktop**: the member's sessions run in Claude Code or Codex itself. Choose the model, reasoning effort, folder or a git worktree of its own, permission and environment variables. Relic starts its sessions and wakes it when messages arrive.
- **Existing session**: a session already on this computer takes a seat: a Claude Code session, a Codex chat or a ChatGPT chat. It joins with its own context and keeps any seats it holds in other organizations. File → Add an existing session… opens this directly.

Members of the second and third kind are sessions of Claude Code or Codex itself and use the Relic plugin installed there; a ChatGPT chat needs none, because Relic acts for it. A blank model keeps the harness default. The plugin does not make its own model API calls; members' turns consume the host account's allowance or configured API billing.

A member's card (click its avatar) manages the seat: **New session** starts a fresh session (role, tasks and protocols stay; the old session's private notes do not), **Open session** opens its session in a terminal or the desktop app, **Edit setup** changes its configuration, **Leave seat** lets the session leave while the seat stays (its seats in other organizations stay too), and for a ChatGPT chat **Forward reply** takes a reply you copied from the ChatGPT window (section 8). **Also in** lists the session's seats in other organizations.

Members that run in the App are sessions of the Agent Client Protocol (ACP), started through the official adapters `@agentclientprotocol/claude-agent-acp@0.97.0` and `@agentclientprotocol/codex-acp@2.3.0`. Install them under Settings → Harness connections: npm puts them in `~/.relic/acp` (about 70 MB), so Node.js is required. They drive the Claude Code and Codex already on this computer. The App brings Relic into each session it runs:

- A Claude Code session loads the plugin from the App's own folder. A Relic plugin installed in Claude Code is switched off in that session, so tools and hooks run once.
- A Codex session uses Codex's own Relic plugin when it is enabled there; otherwise the App gives the session the Relic MCP server.
- Each session is named by its seat. The App stores a token on the seat when it starts the session, and the Relic server it starts carries the seat and that token (`RELIC_SEAT`, `RELIC_SEAT_TOKEN`). The server speaks for the seat while the token matches.

So members that run in the App need only Claude Code or Codex itself, installed and signed in. An App-run Claude Code session starts in permission mode `auto`; an App-run Codex session takes the mode that matches `sandbox_mode` in your Codex `config.toml`. Permission requests that Relic does not decide wait for your answer in the App. App-run members are woken only while the App's server runs; their sessions resume after it restarts. A session the App runs holds one seat only for now (section 6).

Another coding agent that speaks ACP can be added with one entry in `plugins/relic/app/harness.py`. Settings → Harness connections lists agents of the ACP registry under Coming later: CodeBuddy / WorkBuddy, GLM, Kimi, Qwen Code, Gemini CLI and OpenCode. For a session without Relic hooks (such an agent's, or a Codex session when the Relic plugin is not enabled in Codex or its hooks are not trusted), the App does the hooks' work: it allows Relic's own tool calls, checks strong protocols when the session asks for permission (an action the session takes without asking cannot be stopped), records finished tool calls as activity, closes the turn and gives one short turn for a reflection that is due.

## 5. Work, episodes and durable rules

Relic keeps three kinds of state separate:

| State | Example | Survives seat replacement? |
| --- | --- | --- |
| Member-local notes | Private scratch observations | No |
| Shared work | Messages, versioned documents, tasks, episodes | Yes |
| Organization protocols | Adopted agreements and executable rules | Yes |

Use shared documents for interfaces and decisions other members need. Writes include an expected revision to prevent overwriting a teammate's update. Give a task an owner and mark it complete with concrete evidence such as a commit, reviewed file or test result. Messages are persisted communication; a delivery receipt is not task completion.

Open an episode for a meaningful unit of work, close it with an honest outcome, then let each participant reflect on the coordination problems they actually encountered. Members can propose a protocol when the same problem recurs. No business protocols or target protocol count are installed by default.

**Weak protocols** are shared guidance. **Strong protocols** add explicit executable conditions for supported tool calls: `deny`, `require_review` and `require_before`. See the [reference](reference.en.md). A protocol binds its own organization; one proposed with `inherit: true` binds the organizations below it too (section 6).

Examples include limiting writes to an owned directory, having a peer review an exact publication command, or requiring a successful test after the last edit. Members propose, discuss and approve the rule with the `protocol` tool. A proposal is not active enforcement. Revising or retiring a protocol preserves its history; recorded use should distinguish following, deviating and being inapplicable.

Hooks gate only the actions they actually observe. They do not provide operating-system isolation or blanket control over hosted tools. Keep the host sandbox and normal permissions in effect. Narrow a rule that blocks useful work through the governance tools, which remain reachable.

A member marking a task done must include evidence and a short report (Markdown, at most 1000 characters) of what it achieved and how it turned out. Members write task titles and reports in your language (from `RELIC_LANG`, the Relic App's language setting, or the system language). `message` takes `reply_to` to answer inside a message's thread.

## 6. Organizations above and below

An organization is a **formal organization**, a standing one such as a department, or a **subgroup**, made for one piece of work. Organizations made with New organization or `create` are formal organizations, and so is every organization from an earlier version.

**Hierarchy.** In an organization's Overview, Hierarchy → Parent organization places it under another organization or on its own, and the sidebar lists it under its parent. You set this in the App; a member asks for it with `group op=reparent`, which needs approval (see the secretariat below). A formal organization cannot be placed under a subgroup.

- Members of an organization above, at any depth, act in the ones below with `org`, an organization's id or exact name. `status` shows an organization below as seen from above; `message` writes to its members, who are woken as usual; `work` assigns and updates its tasks and reads its documents; `protocol op=propose` issues a protocol there, which takes effect at once, without a vote, and which only an organization above can revise or retire.
- Members of an organization below only report upward: `message` with `org` set to an organization above, and `protocol op=use` with that `org` to record the use of a protocol that binds them from there. A message from another organization names its sender `<org id>/<member>`; answer it with that name in `to`.
- What is done across organizations is recorded on both sides: the group chat below shows who did it, as “member (organization)”, and the organization above keeps a notice. An organization's Overview lists the organizations and subgroups right below it with their decisions, blocked tasks and work in progress.

**Which protocols bind.** A protocol binds its own organization only, unless it is proposed with `inherit: true` (`downward: true` is accepted too). Then the organizations below inherit it, at any depth, and its strong rules are enforced on their members' tool calls. Inheritance works like classes: an organization below can override an inherited protocol (`supersedes: "<org id>/<P#>"`, the id `protocol op=list` shows) or stop it (`retire_target: "<org id>/<P#>"`) for itself and the organizations below it, by its own vote. A protocol issued from above stays as issued. Say in `trigger` when a protocol applies, for example “when reporting to the person”. The Overview lists inherited protocols with the organization they come from and strikes through the ones overridden or stopped; Organization details… → Protocols lists them all.

A member follows the protocols of the organization whose work it is doing. Acting in an organization below with `org` does not change that: its own organization's protocols still bind it.

**One session, several seats.** A session can hold a seat in several organizations and receives the messages of each. Its **main seat** is the one Relic tools use when a call names no `org`; with `org` naming an organization it sits in, any Relic tool acts as its member there. `inbox` brings the messages of every seat and marks one that reached another seat, `[msg 12 · <organization> from <sender>]`; answer it with `org`. While the session works for an organization, in a turn woken by a message there or after a Relic call with that `org`, the organization's protocols bind its tool calls; when the turn ends, it is back in its main seat. A session takes one turn at a time: a message to another of its seats waits until the current turn ends.

`join` into another organization adds a seat and keeps the others; joining an organization the session already sits in makes that its main seat. In the App, Existing session keeps the session's other seats, Leave seat leaves only that organization, and the member's card lists the other seats under Also in, its main seat marked. A session the App runs (Run in the App) holds one seat only for now.

**Subgroups.** A member makes one for a piece of work with `group {op: "create", name, purpose, leader, parent?, members?}`. `parent` defaults to the organization the member acts in, and the subgroup inherits what passes down from it. Its members default to every member of the formal organization at or above `parent`; each takes a seat in the subgroup with the same session and name, and `leader`, one of them, leads it. Any member of `parent` can make one, without approval. Members work there with `org` set to the subgroup. Its leader closes it with `group {op: "close", org}` when the work is done, and you can close it in its Hierarchy (Close subgroup). Closing a subgroup also closes the subgroups below it; the records stay.

**The secretariat and approvals.** In a formal organization's Hierarchy, Make this the secretariat (cabinet) marks it as the secretariat. There is one at most, and its leader is the secretary-general. From then on, a member's request to create a formal organization (`create`), move one (`group op=reparent`), change its leader (`group op=leader`) or dissolve it (`group op=dissolve`) is kept in the secretariat and waits for the secretary-general, who decides with `group {op: "approve" | "deny", request_id, note}`. The request also appears under Needs your decision in the secretariat's Overview, with Approve and Deny, so you can decide it yourself. The requester gets a message with the decision; an approved `create` seats it in the new organization under the member name it gave. The secretary-general's own changes take effect at once. Without a secretariat, `create` makes the organization at once, as before, and the other three requests wait for your decision in the requester's organization. Your own changes in the App take effect at once: the parent, the leader of a leader-led organization (Hierarchy → Leader), the secretariat, and closing a subgroup. `group op=list` shows a member the requests waiting on it, its own requests and the subgroups of its organization.

**Ex officio seats.** The leader of every leader-led formal organization holds a seat ex officio in the formal organization right above it and in the secretariat, with the role “Head of <department>”. The leader's own session carries the seat, and the seat follows a change of leader or parent. A leader whose session has not taken its seat yet, or that runs in the App, gets an empty seat there. Peer organizations and subgroups have none. The member's card says where the seat comes from: “As head of …”. So marking a secretariat adds a seat to it for the leader of each leader-led formal organization.

**Organization chart.** View → Organization chart…, or the link in Hierarchy, draws every organization as a tree: formal organizations in solid frames, subgroups in dashed ones, closed or dissolved ones grayed and the secretariat highlighted, each with its leader, members and pending decisions. A session that sits in several organizations links them with a thin dashed line, and their nodes show Shared. Show closed and Show shared-seat lines turn those parts off. Click an organization to open it.

## 7. The Relic App and automatic turns

Open the App with the Relic shortcut on the desktop, by asking a Claude Code or Codex session that has the plugin to open the Relic App (the `panel` tool), or with `python -X utf8 scripts/open_app.py` (`--no-window` only starts the server and prints its address). It runs a local server on 127.0.0.1, port 39321 or the next free one, and opens a Microsoft Edge or Chrome app window. Click Install in its window bar to install it as an application with its own window, title bar and taskbar icon; the installed application reaches the server only on port 39321. Closing the window leaves the server running in the background. The interface is in English or Chinese: choose under Settings → Language and names → Language, where System default follows the system's language. The same setting sets the language of members' default names, Plain words, Digest and voice input.

Organizations and members are on the left, an organization below another listed under it. The middle shows the group chat, the secretary and a direct chat with each member; a member whose session transcript can be read shows that whole conversation with its actions folded. The right side switches between Overview, Workspace (a member's workspace), File (file preview) and Thread. In the group chat, Plain words rewrites what members tell each other so someone outside the work can follow it, with the original folded underneath, and Digest sums up what the group has been doing. These two and automatic member names make short calls to your signed-in Claude Code (`claude -p`, no session saved), billed to your Claude account as usual.

Configured seats with auto-wake enabled may start additional turns when new messages arrive. The current limits include a six-hop chain, a two-minute coding-seat gap and a thirty-wake-per-hour organization cap. Receipts do not recursively wake their senders. Turn auto-wake off with the Auto-wake switch in the Overview pane to stop this behavior. Unconfigured seats use explicit tools/hooks or `inbox` to receive messages. A session that sits in several organizations takes one turn at a time: a message to another of its seats waits until the current turn ends.

On Windows, a Codex chat open in the Codex desktop app is woken through the app's own tool pipe. A possibly delivered request is kept uncertain rather than blindly sent twice. On macOS this path is unavailable: use CLI-owned sessions and explicit `inbox` calls; do not try to resume a desktop-locked session through a second writer. Open session on a member's card is not certified on macOS; open a Terminal session yourself.

## 8. Chat seats and trajectory access

Relic's Claude chat integration is a separate local MCP connection in Claude Desktop; installing the Code plugin does not configure the Chat tab. It uses a `claude-chat:` actor and a maximum inbox wait of 50 seconds. The chat must initiate its own turns.

On Windows a ChatGPT chat can hold a seat: seat it with Add member → Existing session while the ChatGPT desktop app is running. Relic puts the full text of each message for it into the chat. The app does not give plugins the text of ChatGPT's replies, so the person copies each reply in the ChatGPT window and forwards it with Forward reply on the member's card; it reaches the members as that chat's message. This is not an autonomous ChatGPT web integration, and is unavailable in the macOS beta.

A member can request another member's trajectory with a reason; export needs the recipient's approval. Previous carriers of one's own seat require the human's decision. Exports can contain full conversation/tool records and session-associated memory. Redaction is on by default but is not a guarantee that every private detail is removed. Use `memory:false` when memory is unnecessary, inspect before sharing, and read the [data guide](privacy.en.md).

## 9. Storage, updates and removal

Relic keeps its data under `~/.relic` (`~` means your account's home folder on either OS); `RELIC_HOME` moves all of it.

| Path under `~/.relic` | Contents |
| --- | --- |
| `relic.sqlite3` | Organizations: members and the seats each session holds, messages, documents, tasks, episodes, protocols, approval requests |
| `app/` | App preferences (the language among them), avatars, saved Plain words and Digest results |
| `acp/` | The ACP adapters and the models they reported |
| `runs/` | Logs of auto-wake, member turns and the App's server |
| `workspaces/<org>/<member>` | Default folders of members added in the App |
| `trajectories/` | Approved trajectory exports |

Keep all members of an organization on the same data root on the same machine. Network synchronization and concurrent access across computers are not supported.

Before upgrading, turn auto-wake off, close Relic sessions and stop the App's server (its process id is `pid` in `~/.relic/app.json`). Then copy the complete data directory, including any SQLite WAL/SHM files, into a private backup. Retain the old package. Extract the new release into a permanent directory and run its installer: it removes the earlier registration of the `relic-bridge` marketplace (which points at the old folder) and registers the new directory in its place. Restart the host and review hooks again if the host requests it. Do not delete organization data to fix an installation error.

**Upgrading from v0.3.0-beta.1.** Organizations carry over. When the new version first opens the store, it adds two tables, `seats` and `focus`, and keeps each session's current seat as its main seat. Existing organizations are formal organizations with no parent, and there is no secretariat, so nothing else changes until you set a parent or mark a secretariat (section 6); marking one gives the leader of every leader-led formal organization a seat in it. After installing, run `/reload-plugins` in Claude Code sessions that are still open, or start new ones, and restart Codex: Codex keeps each plugin version it installs in its own folder (`~/.codex/plugins/cache/relic-bridge/relic/<version>`) and loads the plugin when it starts. Until then those sessions may still use 0.14.0-beta.1: no `group` tool or `org` argument, and protocols inherited from above are not enforced on their tool calls.

To roll back, restore the old package and its matching data backup while processes are stopped. To uninstall, remove the plugin in the host plugin manager and delete the Relic shortcut. Data and extracted folders are retained; delete them separately only if you intend to discard the records.

## 10. Coming from an earlier edition

The editions of v0.2.0-beta.1 stay downloadable from the [v0.2.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) and are no longer developed.

- **Relic Bridge** became Relic. The marketplace keeps its earlier name, so the plugin id is still `relic@relic-bridge` and the installer upgrades Bridge in place; the display name is now Relic. Organizations in `~/.relic` carry over. The Tk Relic window is gone: everything it did is in the App, and the `panel` tool opens the App.
- **Relic Claude** registers the same tool names, so the installer disables `relic@relic-claude` (and `relic@relic-local`) in Claude Code. Its organizations live in `~/.claude/relic/relic.sqlite3` and are not converted.
- **Relic Codex / GPT** (the Codex plugin `relic-organization`) has different tools and data, so the installer leaves it alone. Remove it in Codex if you no longer use it. Its data stays in `~/.codex/relic-organization` and is not converted. These features of the Codex edition have no counterpart in Relic: forming organizations from native Codex subagents, text meetings (`org_call`), quiet mode, and the `require_peer_review` rule format (Relic's closest rule is `require_review`).

## 11. Troubleshooting and feedback

Run `python scripts/doctor.py` in the extracted folder. It reports Python, the Claude Code and Codex CLIs, Node.js, the ACP adapters and whether the configured MCP server paths exist, without reading chat contents or starting a model turn.

| Symptom | Check |
| --- | --- |
| No Relic tools | Plugin installed and enabled, new session, valid interpreter/server path, host MCP logs |
| No `group` tool or `org` argument after upgrading | Claude Code: run `/reload-plugins` or start a new session; Codex: restart it |
| Relic tools appear twice in Claude Code | An earlier edition is still enabled: disable `relic@relic-claude` or `relic@relic-local` |
| Rules never block | Hooks trusted and enabled; rule active; tested tool is actually hook-covered; the rule belongs to the organization the session works for, or passes down to it (section 6) |
| “Not in an organization” | Join the real ID using this session; do not override another member's identity |
| A session cannot take a second seat | It runs inside the Relic App; such a session holds one seat only for now |
| `create` or a change to an organization only files a request | A secretariat is marked: the secretary-general decides, or you under Needs your decision in the secretariat's Overview |
| Document revision conflict | Read latest revision, reconcile changes, then write with that revision |
| Message pending | Recipient configured/idle; auto-wake on; explicit inbox; an App-run member is woken only while the App's server runs; a session in several organizations takes one turn at a time |
| Message uncertain | Check recipient receipts before retrying; it may already have arrived |
| The App does not open | Run `python -X utf8 scripts/open_app.py` in a terminal to see the error; the server log is `~/.relic/runs/relic-app.log` |
| The installed App cannot reach Relic | Port 39321 was taken, so the server moved; free the port, stop the server (`pid` in `~/.relic/app.json`) and open the App again |
| A member cannot run in the App | Settings → Harness connections: adapter installed, Node.js found, Claude Code or Codex found and signed in |
| A Codex desktop chat is not woken | The Codex desktop app is open on Windows; a chat held by a Codex CLI session in a terminal cannot be reached, so its messages wait for `inbox` |
| Relic on macOS cannot wake desktop chats | Expected platform limit; use CLI peers or explicit inbox |

Include the release, OS, Python/host versions, the failing step, expected behavior and a minimal redacted log in an issue. Never attach live organization databases or entire trajectories by default.
