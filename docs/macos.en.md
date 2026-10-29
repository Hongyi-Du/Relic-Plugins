# macOS Apple silicon guide — v0.7.1-beta.1

**v0.7.1-beta.1 (plugin 0.18.1-beta.1) merges HaochenGu's macOS port with v0.6.0.** Windows and macOS share one
feature source and release version. This unsigned source candidate includes the Relic App and Claude Code/Codex
plugin; Python, Node.js and signed-in hosts are external prerequisites. HaochenGu's real-Mac observations were made
before this merge on the v0.4.1-based port. Merged automated results and remaining live acceptance are tracked in
the [validation record](validation.md); the earlier v0.4.1-macos prerelease is historical; v0.7.0 uses one release line.

[中文](macos.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

The macOS target is **Apple silicon**, with native **arm64 Python 3.11+**. Intel Macs and translated Rosetta runtimes
are outside the support target. The installer rejects an x86 Python. Members running inside the App also require
native **arm64 Node.js 22+** and npm. Install and sign in to Claude Code and/or Codex; the adapters use these external
CLIs, and optional bundled native dependencies are omitted.

`bash install.command` selects native Python from PATH or common Apple-silicon Homebrew locations;
`RELIC_PYTHON_PATH` selects an explicit interpreter. Executable discovery also checks `~/.local/bin`, Homebrew,
Volta and installed nvm versions. Use `CODEX_CLI_PATH`, `CLAUDE_CODE_EXECUTABLE`, `RELIC_NODE_PATH` or
`RELIC_NPM_PATH` to choose a particular installation. An invalid explicit path fails instead of selecting another
program. The App's harness settings can select the executable used by its members.

The two built-in ACP adapters have a committed npm lockfile. Installation uses the locked pair in
`RELIC_ACP_HOME/adapters/<lockfile-hash>` (by default below `~/.relic/acp`), with a readiness marker after a successful
install. Existing installations at the legacy ACP location remain a fallback. Updating the lockfile creates a separate
adapter directory; it does not overwrite the old pair in place.

## Installation and lifecycle

Extract `relic-macos-v0.7.1-beta.1.zip` (or the equivalent `.tar.gz`) into a permanent folder. From that folder:

```sh
bash install.command --host none --open
```

`--host none --open` prepares and opens the App without registering the plugin in a host. In **Settings → Harness
connections**, install the ACP adapters, then create an organization and add members with **Run in the App**.
Give each member an explicit task to begin work. For independent plugin sessions, use `--host claude`,
`--host codex` or `--host both`, then restart the host and review/trust its hooks. The default `--host auto` registers
with the CLIs it finds. `--configure-only` prepares the package without changing host settings or creating a launcher.

The installer creates **`~/Applications/Relic.app`**, a Finder launcher that points to this folder and the selected
Python. Keep the folder in place. `--no-shortcut` skips the launcher; `bash install.command --remove-launcher` removes
only a launcher created by Relic and preserves host registrations and organization data. Reinstalling from a new
permanent folder updates the managed launcher. This locally generated launcher is not a signed distribution bundle.

For the following commands, `python3` must be the same native arm64 Python 3.11+ selected during installation.
If your shell selects another version, use the selected interpreter's full path instead. `--open` above uses the
installer's selected interpreter automatically.

```sh
python3 -X utf8 scripts/open_app.py --status
python3 -X utf8 scripts/open_app.py --stop
python3 -X utf8 scripts/open_app.py --restart
python3 -X utf8 scripts/open_app.py --no-window
```

There is one server per `RELIC_HOME`. Status does not start it; stop and restart authenticate the saved server
instance and wait for its ownership lock to be released. Restart reuses the port when available. An older or
unverified server is not stopped using a saved PID alone. Closing the browser window leaves the server running.
Stopping the server cleans up the sessions and processes it owns; organization data remains on disk.

All participating hosts must use the same `~/.relic` or explicit `RELIC_HOME`. Before replacing a package, stop its
server and back up the data directory. Opening an existing store adds the activity-path column when missing and
preserves existing records; historical records without structured paths retain the legacy interpretation. For host
removal, marketplace paths and rollback, see the [user guide](guide.en.md#9-storage-updates-and-removal).

**The automatic `activity.paths` migration is irreversible by Relic and has no automatic downgrade.** Switching
back to older code does not undo it; restore a pre-upgrade backup to roll back.

## Shared v0.6.0 features

Check programs, Copies, Stop-hook rules on `Reply`, and protocols issued by the person
(`POST /api/org/<id>/protocols`) are shared on both systems. The sidebar folds organization subtrees; the organization
chart supports dragging, zooming and fitting. Reply enforcement requires the host to load the Stop hook.
See the [reference](reference.en.md) for details.

## Current capabilities

| Feature | Prerelease behavior and validation |
| --- | --- |
| CLI tools and hooks | Organizations, messages, documents, tasks and governance share the local store; enforcement requires the host to load the hooks |
| App-managed ACP members | In HaochenGu's pre-merge v0.4.1 test, a signed-in Claude Code writer and Codex reviewer completed tasks, exchanged messages and revised a shared document; explicit task prompts were needed after the startup wait instruction |
| Browser App | Finds Edge/Chrome app bundles or opens the default browser; Safari/Chromium interaction, clipboard, IME and trackpad acceptance remain incomplete |
| Finder and Terminal | Native file/folder opening and interactive session launcher implemented; failures are reported; interactive acceptance remains incomplete |
| Protocol paths | Uses recorded absolute/resolved paths, NUL-delimited Git paths, macOS Unicode normalization and the target volume's case behavior; symlink aliases are checked and Windows matching is preserved |
| Codex Desktop and ChatGPT seats | Unix-socket transport implemented; available only after the host-provided private socket passes its required-tools handshake and the host authorizes the request |
| Claude Desktop automatic turns | Implemented behind explicit enablement, a supported CLI probe and observed public Desktop Stop hooks; exact peer and completion receipt are required for each delivery |

A GUI-configured seat never silently changes to a CLI writer. Existing Code sessions can participate manually
through their installed tools/hooks and `inbox` while automatic delivery is unavailable. Turn off Auto-wake in the
Overview pane to keep all member turns manual.

## Desktop capability checks

Run ordinary diagnostics with `python3 scripts/doctor.py`. An explicit
`python3 scripts/doctor.py --probe-desktop` checks the available desktop contracts without sending a chat message.
The App also exposes capability checks in its settings. Reading status alone does not probe the host.

**Codex/ChatGPT:** the bridge accepts only the endpoint supplied by the host, or its remembered copy, and validates
a private socket owned by the current user. A successful required-tools handshake is bound to that socket's identity;
replacing the socket invalidates the proof. The macOS framing was confirmed from the installed host, but the live host
closed the handshake during HaochenGu's pre-merge validation attempt. Delivery therefore remains unavailable on this tested setup.
Opening a chat with Relic loaded and allowing its host-authorized bridge is a prerequisite; an app-server connection
does not substitute for that bridge.

**Claude Desktop:** enable delivery explicitly in Relic settings (or set `RELIC_CLAUDE_DESKTOP_ENABLED=1` before a saved
setting exists), select **Claude Code 2.1.224+**, and run the capability probe. Complete a manual Desktop turn in an
existing GUI-configured Relic seat with its public Stop hook loaded. The recorded observation must still be recent,
and each target seat needs its own observation. The route then still checks the exact peer and matching completion
receipt; an ambiguous send is not retried as a fresh delivery. An earlier probe used **2.1.92**, below the required
version. The later organization test used **2.1.286**, but did not validate the Desktop route; its enablement, public
Stop observations and receipts remain unverified. The CLI version requirement is specific to this desktop route.

## Tested scope and known limitations

HaochenGu's pre-merge v0.4.1 signed-in organization smoke test completed the writer and reviewer tasks, bidirectional messages, a shared
document revision and a stale-revision rejection. It required explicit human task prompts after a startup wait
instruction. It does not establish fully autonomous startup, hierarchy or all governance enforcement. The extracted
ZIP separately passed installation, diagnostics, server status, restart and stop checks with an isolated data directory.

Browser acceptance remains incomplete: Chrome automation was unavailable, the in-app browser timed out, and a Safari
attempt hung and was aborted. Finder/Terminal interaction, clipboard, English/Chinese input, trackpad behavior and
permission-denial flows have not all been validated interactively. Real-host cancellation/resume/sleep and the full
governance/hierarchy workflow also remain outside the completed smoke test. Desktop delivery requires the host checks
above and is not validated on this setup. Merged Windows/macOS CI results are recorded in [validation](validation.md).

This release is a source installation package with a locally generated launcher; it is unsigned and not notarized.
No signing or notarization is claimed for this prerelease.
