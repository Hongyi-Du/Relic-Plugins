# Responsiveness acceptance, Amendment 9

All execution is CI-only, with synthetic stores. The existing large fixture is
retained; `person-shape` adds the reported 14-organization store distribution.
No human message content is read into a fixture or artifact.

## Installed 1e1fc14 findings

The sidebar's ItemClick does route other organizations/chats to Select; no
current-organization-only restriction was found. MainWindow.cs:204 returned
immediately when Refresh was busy, so Select's await (:262) did not mean the
requested chat had rendered. It then forced root.UpdateLayout on the old tree.
Refresh :244 rebuilt every region for any successful event refresh. The chat
was a plain StackPanel (MainWindow.cs:31): Conversation.cs:327–357 constructed
the complete 1,000-message page on the UI thread. NativeLabel.cs:283–288 and
:495–502 also queued repeated drawing on root changes and every Arrange.
Those are verified source defects; the person's missing dump does not identify
a unique cause for all 209 threads or the 2.5 GB working set. Current bounded
preparation, dirty checks, virtualized rows and navigation completion checks
must be proven by the actual click/idle/switch gates below.

## Shared native manifest v2

The runner starts a fresh native process for each phase, always in this order:
`open-every-chat`, `switch-chats`, `idle`, `workflows`, `history`, `monkey`.
Each phase produces its own `responsiveness-report.json`, including failures;
the aggregate fails if any phase fails or is absent. An earlier functional
failure must not suppress later phases. A native crash is recorded explicitly.

The manifest retains `output`, `fixture`, `seconds`, `seed`, `plan`, `monkey`,
and `max_ui_stall_ms`; it adds `version: 2` and `phase`. Native completion must
echo `phase` and `seed`. Only `monkey` runs the randomized deck for `seconds`
(at least 180). Other phases finish after `plan` without starting that deck.
`performance-ready.json` also includes `phases_version: 2`; the driver rejects
an older client before it accidentally repeats the entire legacy monkey run
for each independent phase. This is an explicit failure, never a skipped pass.

| Phase | Native behavior / receipt |
| --- | --- |
| `open-every-chat` | A reverse tour of every organization header (`kind: "organization"`), then every separate group and private chat row. Actual sidebar clicks; no direct model-selection substitution. Each action records `click_events >= 1`, `latest_visible: true`, and `open_ms <= 1000`, from actual input to real latest content drawn in the selected chat. A genuinely empty chat requires the actual empty state. Sidebar realization/positioning is reported separately. |
| `switch-chats` | One complete warm-up tour (`warmup: true`), then exactly 200 switches (`warmup: false`, `switch_index: 0..199`). Same real-click/content/one-second assertions. Heartbeats identify `switch:<index>` while each measured switch runs, so the external process monitor measures resource plateaus. |
| `idle` | Wait for real conversation readiness, then set heartbeat action to `idle-measure` and leave it untouched for at least 12 seconds. Completion includes an action with `idle_seconds >= 10`. The external runner measures actual process CPU over a full ten seconds, not a self-reported percentage. |
| `workflows` | Existing pane, resize, menu and dialog coverage, with group selections preserving the original context. |
| `history` | Existing production-input paging and actual first/last message checks. Original page sizes, reading-anchor checks and deadlines remain. |
| `monkey` | Existing seeded real-pointer randomized deck for at least 180 seconds, with live synthetic messages and SSE events. Original distinct-target/input receipts remain. |

All phases retain the 250 ms main-thread limit, 1 GiB RSS and 160-thread limits.
Idle CPU must be below 2 percent of **one core** over ten seconds. Resource
reports retain raw samples and medians, including idle and successive blocks
of the 200 switches, so startup cache allocation is distinguished from growth.
After a complete warm-up tour, the four 50-switch RSS medians must stay within
32 MiB and thread medians within two threads. During idle, the ending median
may grow by no more than 1 MiB and no threads over the beginning median. Raw
values remain available for review. The fixture pauses only its own synthetic
event producer during idle; the app's background behavior remains active.
These are additional checks; they do not replace the complete history or
monkey requirements. Missing native v2 support fails explicitly.

## Changes for the clients

- 2026-11-02: Both clients must consume `phase`, echo it in their completion,
  implement the real-click open/switch phase and idle marker/receipt above.
  The Windows/shared session owns the manifest, aggregation and external
  process measurements; the macOS session owns its native input/readiness.
  No shared HTTP route or payload change is required.
- The chosen name is `switch-chats` (the Mac request called it `switch-200`).
  Chosen action timing is `open_ms`; include the independent expected and
  actual visible IDs in the action receipt. `fixture.profile` identifies the
  data set. Idle is a single `kind: "idle", seconds: 12` plan action, with
  `idle_seconds` in its result. Extra platform diagnostics are welcome, but
  these shared field names are required. Each chat plan includes independently
  generated `latest_message_id` and `expected_empty`; the fixture also exposes
  `latest_group_message_id` / `latest_private_message_ids` for organization
  clicks needed to reveal a private chat. These expectations are not copied
  from the client's currently displayed model.
