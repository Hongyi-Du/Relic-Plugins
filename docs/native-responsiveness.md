# Responsiveness acceptance, Amendment 9

All execution is CI-only, with synthetic stores. The existing large fixture is
retained; `person-shape` adds the reported 14-organization store distribution.
No human message content is read into a fixture or artifact.

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

| Phase | Native behavior / receipt |
| --- | --- |
| `open-every-chat` | One group and each private chat of every organization. Actual sidebar clicks; no direct model-selection substitution. Each action records `click_events >= 1`, `latest_visible: true`, and `open_ms <= 1000`, from actual input to real latest content drawn in the selected chat. A genuinely empty chat requires the actual empty state. Sidebar realization/positioning is reported separately. |
| `switch-chats` | One complete warm-up tour (`warmup: true`), then exactly 200 switches (`warmup: false`, `switch_index: 0..199`). Same real-click/content/one-second assertions. Heartbeats identify `switch:<index>` while each measured switch runs, so the external process monitor measures resource plateaus. |
| `idle` | Wait for real conversation readiness, then set heartbeat action to `idle-measure` and leave it untouched for at least 12 seconds. Completion includes an action with `idle_seconds >= 10`. The external runner measures actual process CPU over a full ten seconds, not a self-reported percentage. |
| `workflows` | Existing pane, resize, menu and dialog coverage, with group selections preserving the original context. |
| `history` | Existing production-input paging and actual first/last message checks. Original page sizes, reading-anchor checks and deadlines remain. |
| `monkey` | Existing seeded real-pointer randomized deck for at least 180 seconds, with live synthetic messages and SSE events. Original distinct-target/input receipts remain. |

All phases retain the 250 ms main-thread limit, 1 GiB RSS and 160-thread limits.
Idle CPU must be below 2 percent of **one core** over ten seconds. Resource
reports retain raw samples and medians, including idle and successive blocks
of the 200 switches, so startup cache allocation is distinguished from growth.
These are additional checks; they do not replace the complete history or
monkey requirements. Missing native v2 support fails explicitly.

## Changes for the clients

- 2026-11-02: Both clients must consume `phase`, echo it in their completion,
  implement the real-click open/switch phase and idle marker/receipt above.
  The Windows/shared session owns the manifest, aggregation and external
  process measurements; the macOS session owns its native input/readiness.
  No shared HTTP route or payload change is required.
