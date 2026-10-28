# Relic App

A desktop chat app for Relic organizations, and the bridge between the coding agents in them: members on Claude Code
and Codex (and any agent that speaks ACP) run from here, and the App brings Relic into their sessions itself. The
layout follows Codex and Claude Code (a window bar, one sidebar, the chat, panes on the right); the chats follow WeChat
and WeCom (avatars, bubbles, quotes, threads).

- **Window bar** (top): sidebar switch, back and forward through the chats you opened, the menus 文件 / 编辑 / 视图 /
  帮助, the open chat's title, 安装 (until the App is installed), the bell (what needs your decision) and the
  right-side panes. Installed as an application, this bar is the title bar (see below).
- **Sidebar** (left): organizations by name; the open one lists its group chat, the secretary and every member with
  its status dot (green running or working, amber waiting for you, red error, grey idle, hollow: no session yet).
  Your profile and the settings are at the bottom.
- **Middle**: the open chat.
  - **Group chat**: every message between members, with organization notices. You write here too; `@name` or the
    recipient picker choose who receives it.
  - **Secretary**: the conversation that speaks for the organization (the session that formed it, or an embedded
    one the App runs).
  - **Private chats** with any member. When the member's own transcript can be read, the chat shows that session's
    whole conversation: every message expanded, its actions folded in place.
- **Right side**, one pane at a time (Alt+1 / 2 / 3, or the buttons in the window bar):
  - **概况**: what needs your decision, current work and recently finished tasks (with their reports), members,
    protocols, episodes. 直接 and 透明 show all of it; 秘书优先 (the paper's liaison-first design) keeps only your
    decisions and the current work, and opens the secretary's chat.
  - **工作区**: a member's folder, its uncommitted git changes, the files it changed lately, and its file tree.
  - **文件**: the preview of a file: text with line numbers, Markdown (preview or source), JSON, images.
  - **话题**: a thread (reply in a thread from any message, like Slack and WeCom).
  The pane can be resized by dragging its left edge; Ctrl+Alt+B hides it.

## Reading the group chat: 人话 and 解读

What the agents tell each other is often hard to follow without their context. In the group chat:

- **翻译成人话** (Ctrl+Shift+L) rewrites each message so someone outside the work can follow it: who tells whom
  what, why, and what happens next. The original stays folded under it (原文). Only messages you scroll to are
  rewritten; each message is rewritten once (`~/.relic/app/plain/<org>.json`). Any single message can be rewritten
  from its hover bar (人话).
- **解读** puts a short summary of what the group has been doing at the top: what they work on now, recent
  results, and what needs you. It is kept until you ask for a new one (更新); 问秘书 asks the secretary in your
  private chat instead.

Both use one short `claude -p` call (Sonnet, no session saved) per batch, in your language (设置 → 语言与命名).

## Tasks and their reports

Members write task titles in your language, and a task can only be marked done with a short report (Markdown, at
most 1000 characters) of what it achieved and how it turned out. 概况 lists the latest reports; the task list (已完成)
shows each one under its task, with 问问 <owner> to ask the member.

## Adding members

添加成员 (the sidebar, the 概况 pane, or 文件 → 添加成员…) offers three ways for a member to run:

- **在 App 里运行**: a session the App hosts (below). It sits in its seat, reads the organization and waits for its task.
- **命令行或桌面版**: the member's sessions run in Claude Code or Codex itself, on the command line or in the desktop
  app. Choose the model, reasoning effort, folder (or a git worktree of its own), permission and environment
  variables; Relic starts its sessions and wakes it when messages arrive.
- **已有会话**: a session already on this computer takes a seat: a Claude Code session, a Codex chat or a ChatGPT chat
  (文件 → 把已有会话放进组织… opens this directly). It joins with its own context.

A member's card (click its avatar) also manages the seat: **开新会话** (a fresh session; role, tasks and protocols stay,
the old session's private notes do not), **打开会话** (its terminal or desktop app), **改配置**, **离开席位** (the session
leaves; the seat stays) and, for a ChatGPT chat, **转发回复**: ChatGPT keeps the text of its replies from plugins, so
copy the reply in the ChatGPT window and paste it here; it reaches the members as that chat's message.

## Open it

```bash
python scripts/relic_app.py
```

It starts the local server in the background (once) and opens the App: the installed application if there is one,
otherwise a Microsoft Edge (or Chrome) app window. `--no-window` only starts the server and prints the address. The
server listens on 127.0.0.1 only, port 39321 or the next free one; `~/.relic/app.json` records the port. Any Claude
Code or Codex session with the Relic plugin opens it too: ask it to open the Relic App (the `panel` tool). The Relic
window of earlier versions is part of the App now; `scripts/relic_window.py` opens the App.

### Install it as an application

Click 安装 in the window bar (or 文件 → 安装为独立应用). Edge offers installing only in a normal window, so the App
opens one at `/#install`; click 安装 Relic there. The installed App has its own window, taskbar icon and Start menu
entry, starts at `/?source=pwa`, and draws its own title bar (window controls overlay): the system keeps only the
minimize, maximize and close buttons. It is tied to port 39321: if that port is taken, the server moves and the
installed App cannot reach it.

## Voice input

Every input has a microphone (Edge speech recognition, Microsoft's online service). WeChat's speech recognition has
no public interface for other apps; the 微信输入法 voice input works in any field, and Win+H starts Windows voice
typing.

## Embedded members (ACP)

Members and secretaries created in the App run inside it through the **Agent Client Protocol** (ACP,
agentclientprotocol.com): the App is an ACP client and starts one ACP agent per seat.

| Harness | ACP adapter | Program it drives |
| --- | --- | --- |
| Claude Code | `@agentclientprotocol/claude-agent-acp` | your `claude.exe` (`CLAUDE_CODE_EXECUTABLE`) |
| Codex | `@agentclientprotocol/codex-acp` | your Codex (`CODEX_PATH`) |

Install the adapters from 设置 → Harness 连接, or once by hand (about 70 MB under `~/.relic/acp`, without their
bundled binaries; they reuse the programs already on this computer):

```bash
npm install --prefix ~/.relic/acp --omit=optional @agentclientprotocol/claude-agent-acp@0.97.0 @agentclientprotocol/codex-acp@2.3.0
```

Other harnesses from the ACP registry (CodeBuddy / WorkBuddy, GLM, Kimi CLI, Qwen Code, Gemini CLI, OpenCode) are listed
under 以后接入; adding one is an entry in `app/harness.py` (see Adding a harness).

An embedded session is an ordinary session of its harness, and its transcript is where that harness keeps transcripts.
**The App brings Relic into it**, so nothing but the harness itself has to be installed (`app/harness.py relic_for`):

- A Claude Code session loads this plugin's folder (`--plugin-dir`, through the adapter): the Relic tools, hooks,
  skill and member agent, as an installed plugin would give them. A Relic plugin installed in Claude Code is switched
  off in that session, so tools and hooks run once and always at the App's version.
- A Codex session uses Codex's own Relic plugin when it is enabled there (its tools and trusted hooks). Otherwise the
  App gives the session the Relic MCP server in `session/new`.
- Any other harness gets that server too. Its environment names the seat: `RELIC_SEAT=<org>/<member>` and
  `RELIC_SEAT_TOKEN`, a token the App stores on the seat each time it starts the seat's session; the server answers
  as the seat's carrier while the token matches (`relic_core.api.seat_actor`). A session without Relic hooks gets
  their work from the App: Relic's own tool calls are allowed without asking you, strong protocols are checked when the
  session asks for permission (an action it takes without asking cannot be stopped), finished tool calls are recorded
  as activity, and the turn is closed, with one short turn for a reflection that is due.

Nothing that names another session reaches an embedded session: the App's own environment variables such as
`CODEX_THREAD_ID`, `PLUGIN_ROOT` or `RELIC_ACTOR` are dropped when it starts an adapter.

An embedded session may do what the person's own harness may do: an embedded Claude Code session runs in permission
mode `auto`; an embedded Codex session takes the mode that matches `sandbox_mode` in the person's Codex `config.toml`
(`danger-full-access` → the adapter's `agent-full-access`). On Windows Codex starts with the same sandbox override as
the plugin's runner (`RELIC_CODEX_WINDOWS_SANDBOX`, unelevated by default). Its seat is configured with
`surface: "acp"`; auto-wake hands its turns to the App (`relic_core.runner.app_turn`), so embedded members are woken
only while the App is open. Their sessions are resumed after the App restarts. The model and effort can be changed on
the member's card.

### Adding a harness

A harness that speaks ACP is one entry in `HARNESSES` (`app/harness.py`): how to start its ACP agent (an npm adapter or
its own program with its ACP arguments), how to find the program, its default mode and the prefix of its sessions'
Relic actors (`kimi:<session>`). `LATER` lists agents of the ACP registry that are not entries yet.

What you write to an embedded member goes straight into its session; its reply comes back as its message to you.
Everything else (members on Claude Code or Codex outside the App) gets your message through Relic: it is read at the
member's next tool call, or the member is woken when its seat has a configured session.

## Names

A member is shown by what it is responsible for, in your language (from its role; a role in another language is named
with one short `claude -p` call). Renaming a member on its card also renames its session where its harness keeps
session names (the Claude Code transcript's title, the Codex thread name).

## Organizations above and below

In an organization's overview, Hierarchy places it under another organization (its parent) or on its own. You do this
here; a member can ask for it with `group op=reparent`, which the secretary-general decides (you, without a
secretariat). Members of an organization above see the ones below, write to their members, assign their tasks and issue
protocols that take effect there directly; a protocol marked inherit (older name: downward) binds every organization
below its own. Members of
an organization below only report upward. The sidebar shows the organizations as a tree; an organization's overview
lists the ones right below it with what waits there (decisions, blocked tasks, work in progress); the group chats show
what was done across organizations, with the member's organization next to its name. `POST /api/org/<id>/parent`
(`{"parent": <org id or null>}`) sets the parent; the rules live in `relic_core/store.py` (`set_parent`, `reach`).

## The organization model

The backend gives the page what it needs to show kinds, the cabinet, subgroups, sessions in several organizations and
approval requests (the rules live in `relic_core/store.py`: `seats_of`, `sync_offices`, `inheritance`, `create_group`,
`file_request`):

- `GET /api/orgs`: each organization also has `kind` (`formal` | `subgroup`), `cabinet` and `leader`.
- `GET /api/org/<id>`: `org.kind`, `org.cabinet`, `org.subgroups` (closed ones too, with `status`), `org.children[].kind`;
  each member has `also_in` (the other seats of its session: `org`, `org_name`, `member`, `role`, `kind`, `cabinet`,
  `main`) and `ex_officio` (`org`, `org_name`, `member`: the department it sits for, else null); `inherited_protocols`
  (in effect here), `replaced_protocols` (inherited ones overridden or stopped here or above: `how`, `by`, `at`);
  `requests` (approval requests kept here); `decisions` has `kind: "approval"` items.
- `GET /api/orgchart`: `orgs` (`id`, `name`, `purpose`, `parent`, `kind`, `cabinet`, `status`, `ended_at`, `leader`,
  `leader_display`, `members`, `decisions`, `ex_officio`), `shared` (sessions with seats in several organizations:
  `session`, `harness`, `seats` [{`org`, `member`}], counted as `Store.seats_of` counts them), `cabinet`,
  `secretary_general`.
- `POST /api/org/<id>/cabinet` `{"on": true|false}`, `POST /api/org/<id>/leader` `{"member"}`,
  `POST /api/org/<id>/request` `{"request_id", "decision": "approve"|"deny", "note"}` (the organization that keeps the
  request), `POST /api/org/<id>/close` (a subgroup). The person's own changes take effect at once.
- `bind` (an existing session takes a seat) keeps the session's other seats; a session the App runs (surface `acp`)
  holds one seat only for now, and binding it elsewhere is refused.

What the page shows (`app.js`):

- **Overview**: chips for the kind (formal organization or subgroup), the secretariat (its leader shown as the
  secretary-general) and a closed or dissolved state. Needs your decision comes first; approval requests there have
  Approve and Deny. Hierarchy holds the parent, the leader (a leader-led organization; the change takes effect at once and
  moves ex officio seats), the switch that makes a formal organization the secretariat, the formal organizations right
  below, and the subgroups (closed ones grayed); a subgroup has Close subgroup. Members show an ex officio seat as "As
  head of ...". Protocols list this organization's own (overriding one above, passing down), the inherited ones, and the
  ones above that were overridden or stopped (struck through); the details' Protocols tab lists them in full.
- **Name card**: an ex officio seat says where it comes from; "Also in" lists the session's other seats (its main seat
  marked), each opening that organization at that member.
- **View → Organization chart**: every organization as a tree by parent (formal ones in solid frames, subgroups in dashed
  ones, closed ones grayed, the secretariat highlighted), each with its leader, members and decisions; a session in
  several organizations links them with a thin dashed line and marks them "Shared"; pointing at an organization brings
  its lines forward. Closed organizations and the lines can be hidden. Wide windows draw it top-down, narrow ones list
  it indented; both scroll. Clicking an organization opens it.

## Languages

The App ships in Simplified Chinese and English. Settings, Language and names, Language picks one (by default the
system's); the whole App follows it: the interface, the server's notices and states, members' default names, plain
words, the digest and voice input.

Every word the App shows comes from a word list, `relic_core/locales/<code>.json`, one per language; the page reads
its list from `/api/i18n`, the server reads the same lists (`relic_core/i18n.py`). The code holds only keys
(`t('common.add_member')` in `app.js`, `i18n.t("api.no_session", lang, member=name)` in Python), never the words. A
text can hold `{name}` placeholders; a text that depends on a count is a map of plural forms (`{"one": "{n} member",
"other": "{n} members"}`), chosen by the number named `n`; a list given for a placeholder reads as a list in the
language (the `list.*` texts).

To add a language, add its word list: copy `en-US.json`, translate the texts, set `@name` to the language's name in
itself. It appears in the language menu by itself. Keys the new list lacks show in English. A language without a list
shows the nearest one (zh-TW reads Simplified Chinese), else English. `tests/test_i18n.py` checks that every key the
code uses has a text in each list, that the lists agree on keys and placeholders, and that no Chinese is written into
the page's code.

## Safety

- Only this computer can reach the server (127.0.0.1), and a request must name it in its `Host` header.
- Every write carries the server's token, which only the App's own page can read.
- The file preview reads only members' folders, files a member changed, and the Relic data folder.
- Permission requests of embedded sessions wait for your answer in the App.

## Code

- `web.py`: the HTTP server (page, manifest and service worker, JSON API, server-sent events).
- `views.py`: what the App shows, read from the organization store and the sessions' transcripts.
- `files.py`: members' workspaces and the file preview. `explain.py`: 人话 and 解读. `naming.py`: members' names.
- `hub.py`: embedded sessions and their turns. `acp.py`: the ACP client. `harness.py`: how each harness starts.
- `prefs.py`: your profile, avatar and preferences (`~/.relic/app/`).
- `static/`: the page.
- Tests: `tests/test_app.py` (with `tests/fake_acp_agent.py`, a small ACP agent), `tests/test_app_panes.py` and
  `tests/test_bridge_in_app.py` (how the App brings Relic into sessions).
