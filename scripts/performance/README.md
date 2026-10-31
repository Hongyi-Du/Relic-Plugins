# Native responsiveness contract

This harness runs only in GitHub Actions. It creates its own synthetic store;
it never reads or copies `~/.relic`, and never launches a provider/member session.
Use `python scripts/performance/run.py --client windows|macos --exe ... --output ...`.
The driver exports `RELIC_PERF_MANIFEST`, `RELIC_PERF_OUTPUT`, `RELIC_HOME`,
`RELIC_ENGINE_ROOT`, `RELIC_PYTHON`, and isolated native-state/config directories.

The manifest is JSON, version 1:

```
{version:1, client:"windows", output:"...", seconds:180, seed:1729,
 max_ui_stall_ms:250, fixture:{home,port,token,instance,pid,workspace,
 orgs:[{id,members:["secretary",...],group_messages:5500}],counts:{...}},
 plan:[{id,kind,...}], monkey:[{id,kind,...},...]}
```

`plan` is the deterministic exhaustive phase. The client must execute every row
through the same production controls/commands as ordinary interaction, recording
the actual result. `monkey` is a seeded repeating action deck; run it for at least
`seconds` after the exhaustive phase, not for a fixed small number of actions.
Kinds and fields:

- `group`: `org`; select the organization's group conversation.
- `private`: `org`, `member`; select that member's private conversation.
- `pane`: `pane` is `overview`, `workspace`, or `files`.
- `resize`: `width`, `height` are logical DIP/point sizes; the normal minimum
  applies. Sizes cross the 1180 inspector breakpoint (1440, 1180, 1024, 960).
- `menu`: `name` is `file`, `edit`, `view`, or `help`; open and dismiss it.
- `dialog`: `name` is `settings`, `about`, `neworg`, `member`, `tasks`, or
  `protocols`; open and dismiss it without committing changes or starting
  sessions. The deck returns to the largest organization for these dialogs.
- `scroll-history`: `org`; repeatedly scroll upward and fetch older pages until
  the actual first historical message is reachable, then return to the latest.
  The result must include `pages_loaded`, `oldest_message_id`, and
  `history_complete`. Merely scrolling the first page is not completion.

Native monitoring starts as soon as the UI dispatcher/window exists, before
initial organization rendering. A single background worker posts at most one UI
probe at a time, approximately every 50 ms. It must continue publishing even if
the UI is stuck. Write files atomically into `output`:

- `performance-ready.json`: `{pid,unix_ms}`; identifies the real process.
- `heartbeat.json`: `{unix_ms,sequence,pings,max_ui_stall_ms,
  pending_since_unix_ms,action}`. Use epoch milliseconds; pending is 0 when no
  probe awaits dispatch. The max measures actual UI probe round-trip latency.
- `performance-complete.json`: `{actions:[{id,kind,target,elapsed_ms,passed,...}],
  errors:[],max_ui_stall_ms,random_seconds,random_actions,seed}`. Include every
  exhaustive plan id; do not record synthetic successes or bypass production
  rendering in performance mode. `random_actions` is a count.

Every monkey action has a unique `id:"monkey-<index>"` and must also include
`pointer_target:"<actual control identity>"` and `click_events:<integer >= 1>`.
`click_events` is the number observed by the actual target control's native
click/action event handler during that action. It is not a count of requested
input injections or a constant assigned after changing the model. Dispatch real
pointer input (Windows pointer injection; macOS NSWindow mouse events or CGEvent)
and wait for the actual control to handle it. Keep the production action outcome
and native click receipt together. Use stable target identities, such as
`sidebar`, `files`, or `help-menu`, rather than per-action unique labels.
The count of individual monkey receipts must equal `random_actions`; each must
have a nonempty target and an observed click, and the full 180-second phase must
click at least two distinct targets. Pure model navigation does not satisfy this
requirement. These click checks supplement the unchanged exhaustive action,
duration, 250 ms UI latency, and resource-growth gates.

The driver samples RSS, CPU seconds, and thread count using psutil. On Windows it
also records `IsHungAppWindow` and a bounded WM_NULL response probe against the
owned process's top-level window. It fails on any UI probe over 250 ms, a native
error, incomplete action coverage, fewer than 180 random seconds, a hung window,
or an unresponsive watchdog. A first failure retains at least two additional
seconds of observations before the owned process is stopped, giving a failed
baseline actual stall/resource numbers rather than just a missing-file error.

On Windows, the shared JSON snapshot reader opens with `CreateFileW` and
`FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE`. It then transfers the
handle to Python's managed file object and closes it after reading. This lets
native heartbeat/completion writers and the synthetic `live-updates.json`
producer atomically replace snapshots while the watchdog holds the old snapshot
open; ordinary read opens can block replacement because rename requires delete
sharing. This is reader/writer coordination, not a heartbeat grace-period change.
The share flags and handle ownership have mock-only CI regressions. See the
[Microsoft CreateFile sharing contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
Windows atomic replacement can still briefly leave the path pending deletion:
run 41165740664 recorded `PermissionError` reading `heartbeat.json`. Only that
Windows read error is retried, at most ten attempts with 2 ms between attempts
(18 ms of scheduled waiting). Persistent denial still raises and fails the run;
missing/incomplete snapshots keep their existing behavior. Mock regressions
cover transient success, persistent failure, and the unchanged non-Windows path.

Resource gates are fixed before the baseline: peak RSS <= 1 GiB, peak threads
<= 160. After exhaustive actions have warmed the content, three consecutive
30-second median windows must not grow by more than 32 MiB each (memory) or
4 threads each (threads). These limits detect sustained growth rather than a
single normal cache allocation. All raw samples and computed medians are kept.
The main process and owned descendants are sampled separately; native process
values are the gate, and child-process values remain diagnostic evidence.

The fixture contains 13 organizations, 42 members in its busiest organization,
four members in each of the other 12, a 5,500-message group, three 1,250-message
groups, long Markdown messages, private messages for every seat, 420 tasks,
hundreds of notices, and protocol/episode records. It exercises the real server
and store, including SSE hints at a bounded 10 Hz burst rate during exhaustive
actions. Once heartbeat `action` starts with `random` or `monkey`, the same one
producer switches to continuous 10 Hz hints and inserts one genuine synthetic
message every two seconds. `live_updates` retains actual published/stored counts.
This monkey-phase addition was fixed before the first passing candidate and
does not affect the initial-load baseline. The driver removes its trigger on
cleanup; no thread is created per message. A fixed random seed controls content
and action order.

`native-responsiveness.yml` runs candidate measurements as a required job.
Its `mode=baseline` workflow-dispatch input labels a pre-fix measurement but does
not weaken the gate or turn failures green. Run it on the instrumented pre-fix
commit to compare the same fixture and policy with the candidate. Artifacts
contain synthetic data and receipts only. Product packaging remains in the
existing `Native apps` workflow.

An explicit `--diagnostic` option (workflow-dispatch `diagnostic: true`, default
false) keeps observing a failed native process for up to **30 seconds** after
the first violation, instead of the normal two seconds. This can expose a later
crash and preserve its stack after an initial UI stall. It changes only that
post-failure observation window: all violations remain in the report and every
250 ms violation still fails. Process exit or a completed native receipt ends
observation earlier. Automatic push runs never enable it.

Diagnostic reports always include `diagnostic: true`, `acceptance_eligible: false`,
`failure_observation_seconds: 30`, and `passed: false`; the command exits with
failure even if it observed no product violations. Their workflow/artifact names
are marked diagnostic. A diagnostic result is never acceptance evidence and its
longer-window memory/thread peaks cannot be compared directly with the normal
two-second failure baseline. Ordinary candidate and baseline measurements keep
`diagnostic: false`, a two-second failure window, and all original strict gates.
