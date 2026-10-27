# Relic App

A desktop chat app for Relic organizations. The layout follows Codex and Claude Code (a window bar, one sidebar,
the chat, panes on the right); the chats follow WeChat and WeCom (avatars, bubbles, quotes, threads).

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
    protocols, episodes. 直接 / 透明 / 秘书优先 set how much it shows.
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

## Open it

```bash
python scripts/relic_app.py
```

It starts the local server in the background (once) and opens the App: the installed application if there is one,
otherwise a Microsoft Edge (or Chrome) app window. `--no-window` only starts the server and prints the address. The
server listens on 127.0.0.1 only, port 39321 or the next free one; `~/.relic/app.json` records the port.

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
under 以后接入; adding one is an entry in `app/harness.py`.

An embedded session is an ordinary session of its harness: it loads the Relic plugin, its hooks enforce the
organization's protocols, and its transcript is where that harness keeps transcripts. It may do what the person's own
harness may do: an embedded Claude Code session runs in permission mode `auto`; an embedded Codex session takes the
mode that matches `sandbox_mode` in the person's Codex `config.toml` (`danger-full-access` → the adapter's
`agent-full-access`). On Windows Codex starts with the same sandbox override as the plugin's runner
(`RELIC_CODEX_WINDOWS_SANDBOX`, unelevated by default). Its seat is configured with `surface: "acp"`; auto-wake hands
its turns to the App (`relic_core.runner.app_turn`), so embedded members are woken only while the App is open. Their
sessions are resumed after the App restarts. The model and effort can be changed on the member's card.

What you write to an embedded member goes straight into its session; its reply comes back as its message to you.
Everything else (members on Claude Code or Codex outside the App) gets your message through Relic: it is read at the
member's next tool call, or the member is woken when its seat has a configured session.

## Names

A member is shown by what it is responsible for, in your language (from its role; a role in another language is named
with one short `claude -p` call). Renaming a member on its card also renames its session where its harness keeps
session names (the Claude Code transcript's title, the Codex thread name).

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
- Tests: `tests/test_app.py` (with `tests/fake_acp_agent.py`, a small ACP agent) and `tests/test_app_panes.py`.
