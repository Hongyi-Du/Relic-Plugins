# Current delivery policy — Amendment 7 responsiveness

Focused Settings capture at 2090f5c (41177859278) finds a real Windows rendering
regression: all seven navigation captions are blank, while icons/body remain.
Raw XAML confirms placeholder widths, layout/surface/draw revisions zero,
IsLoaded=true, queued=true and valid explicit brushes. The macOS/reference
screens show the captions. Files are in
`S:\Codex\Outputs\Relic-native-visual\settings-2090f5c`.
Both extraction receipts retain their real errors (Windows unfinished native
draw evidence; macOS geometry changed during extraction). These are focused
diagnostic images, not successful parity evidence. Windows async preparation /
loaded-state / draw scheduling is corrected by normal-priority short ownership
handoff and coalesced drawing, repairing mounted labels' retired subscription
state, and queuing paint whenever layout invalidates it. Font discovery remains
on the bounded worker. Normal dialog pressure now requires seven actual visible
navigation labels with current successful paint before dismissing Settings or
About; the raw states are retained in navigation_text_ready. Frame extraction
also waits for real submitted surfaces without replacing any evidence. Headless
build passes; runtime screenshots and the 250 ms gate must validate this change.

Changes for the clients: diagnostic-only Windows stack collection can sample
an actual `dialog:` pending UI probe at 100 ms, before a short modal stall ends.
`trigger_details` distinguishes that sampling threshold from the unchanged
250 ms acceptance limit. Early sampling does not append a product error or
start the post-failure timer; normal runs and every resource/coverage gate are
unchanged. Diagnostic runs remain ineligible, with the same three-report,
single-in-flight, five-second/report and fifteen-second total limits.

Changes for the clients (shared REQUESTS.md 5f753ff): the scene-selection
refactor moved a CLI assignment into a validated helper, so the old AST-only
contract lookup raised StopIteration. The test now follows the actual CLI call,
checks its default `all` argument and original full/smoke selection expression;
all existing 672-case assertions stay mandatory. No contract is made optional.

062dcba removes that instrumentation crash: normal Windows pressure 41176785566
completes 175 fixed + 111 random actions over 181.402 s, maximum 192.263 ms,
426.598 MiB and 38 threads, errors empty. Diagnostic-only 41176785876 completes
175 + 123 actions over 180.327 s, max 133.238 ms, with no stack trigger and no
acceptance eligibility. Actual first Settings measure is 35.949 / 54.233 ms in
these two runs. The earlier intermittent 504.908 ms modal measure is not yet
explained by a native stack; these passes do not establish its cause or fix.
Native apps 41176790028 and Python validation 41176790013 pass both systems.

Changes for the clients: Native visual review has an explicitly manual
`diagnostic_scene` input for individual Settings screenshots and real element
extraction. Focused receipts/manifests say acceptance_eligible=false; the full
comparison job does not run for that diagnostic. Default smoke keeps all 22
scenes and full keeps all 56 scenes / 672 cases. No matcher threshold, exception,
or acceptance matrix changes. This permits inspecting the instrumented native
Settings layout without waiting for unrelated scene captures. macOS REQUESTS.md
at d690ec8 reports remaining resize latency and a dark-window bottom-anchor
regression; its inspector-identity and native scroll fixes are merged for CI.

The a9bfd92 instrumentation run 41176231953 exposed a separate regression:
deriving SelectorBar for a measure override caused WinUI's native Style TargetType
check to see Control, throwing 0x800F1000 on Settings. Its actual
app-unhandled.jsonl is retained in candidate-a9bfd92/windows. That derived class
is removed and the original SelectorBar restored; only the outer Grid/StackPanel
timings remain. Headless build passes. This correction is not the original modal
stall fix, and requires CI runtime verification.

Integration repeat **ecd83a1 / CI 41175412099 fails Windows** while opening
Settings: maximum UI delay **566.015 ms**, WM_NULL timeout, **345.605 MiB**,
**38** threads, early stop before the monkey phase. Windows/shared sources are
unchanged from the passing 7c0ff42 result below. Actual timing now attributes
**504.908 ms to dialog.measure**, followed by another 299.787 ms dialog measure;
the nearby GC pauses are only 22.739 + 6.9 ms. The cold DirectWrite worker fix
does not remove this remaining native modal-layout stall. Diagnostic-only
41175880844 is collecting native UI stacks; no acceptance or gate relaxation.
Raw failure artifacts are in
`S:\Codex\Outputs\Relic-native-performance\candidate-ecd83a1\windows`.
Settings navigation/body/content now retain their original native base layout
and add slow-operation subtree timings to distinguish the real modal measure
owner. This is instrumentation, not an asserted fix; headless build passes.

Changes for the clients: ecd83a1 Native apps CI 41175415967 also catches a real
macOS regression: ConversationKeyboardTests.testRealConversationHomeAndEndMoveTheLazyNativeViewport
reports Home offset 8 px instead of 0 +/- 2 (ConversationKeyboardTests.swift:44).
The Mac owner must fix the actual keyboard scroll behavior; do not weaken its
new assertion. Full-window chrome passes, which does not establish keyboard or
performance acceptance. The latest candidates remain unaccepted.
Changes for the clients: merged macOS 78aa8ec, including its actual Home spacer
fix and scoped geometry observation. REQUESTS.md records the preceding resize
failure at 250.741 ms without rounding or exceptions. No additional shared
route/harness request is outstanding; both pressure gates still apply.

Windows/shared measured evidence at **7c0ff4298b04dec8b09fed402cb8fce1a4290d6f**:
normal responsiveness CI **41174728524** passes Windows: **114.259 ms** maximum
UI dispatch, **401.941 MiB** peak RSS, **39** peak threads, all 175 fixed actions
plus 125 observed random clicks over **181.082 seconds**. Error, coverage,
window-probe and growth lists are empty. Steady RSS medians are 325273600 /
308193280 / 316246016 bytes, threads 34 / 33 / 34. The independent diagnostic
repeat **41174728418** completes the same fixed plan and 155 random actions over
180.258 seconds, max 81.218 ms, with no stack trigger; it remains explicitly
ineligible for acceptance. Both actual DirectWrite preparation tests and all
335 Windows tests pass. Native builds/tests/packages **41174728702** and all
four Python validations **41174732279** are green. The 250 ms gate is unchanged.

The same commit's macOS normal run still fails at startup (374.048 ms maximum,
137.063 MiB, 9 threads), so the whole responsiveness workflow is correctly red
and PR #4 remains draft/unmerged. This is not a completed macOS pressure result.
Reports, test receipts and all three unsigned packages are retained under
`S:\Codex\Outputs\Relic-native-performance\candidate-7c0ff42`.
Adaptive-window **41174728519** and whole-window chrome **41174728491** pass both
systems. All eight actual light/dark, 1440x900/1024x700 adaptive-window PNGs were
inspected under `S:\Codex\Outputs\Relic-native-visual\window-7c0ff42`; prepared
Markdown, composer, title-bar controls, wide inspectors and bottom messages are
present. Nothing was installed or launched locally.

Changes for the clients (2026-10-31): merging macOS 76d842f keeps its additional
Markdown block virtualization and actual dialog/scroll completion assertions.
The current REQUESTS.md was read; the earlier shared capture request is resolved
above, and the remaining work is the macOS-owned cold-layout performance fix.
These additional macOS changes require their own integrated CI results.

Cold-font follow-up: normal 39c15ee passes again in CI 41173632395 (111.980 ms,
426.465 MiB, 38 threads; 175 exhaustive + 155 random actions over 180.657 s).
However diagnostic 41173632429 captures a real 429.177 ms first
NativeLabel.DirectWrite.GetLineMetrics on the UI thread, with matching native
ucrtbase/DWrite frames; the helper reports 0 ms suspension. This remaining cold
path cannot be dismissed by the normal pass. Initial NativeLabel layout and
NativePath source/strut shaping now use one bounded background DirectWrite
worker. The exact prepared layout transfers to UI; XAML/D2D/surface drawing
stays on UI, pending lines do not invoke a cold TextBlock fallback, and captures
wait for NativeLabel.PendingPreparations as well as Markdown/rows/paragraphs.
CI regressions compare actual Unicode metrics, baseline/wrapping/ellipsis,
cancellation disposal and queue serialization. Local headless app and test
project compilation passed; new runtime and visual evidence is still required.

Diagnostic validity follow-up: the first native sampler crossed a JIT boundary
and returned non-executable addresses after the valid DWrite frames. The original
artifact is retained unchanged. New captures stop at an invalid instruction page
or out-of-snapshot/non-advancing stack pointer, label the unwind incomplete, and
record rejected addresses separately rather than asserting them as native frames.

Latest Windows result: **02b5940 / CI 41172820210 passes** the full normal
pressure run: 175 exhaustive actions, 129 observed random clicks over 180.725 s,
maximum UI delay **83.942 ms**, peak RSS **453.398 MiB**, peak threads **38**.
All watchdog, coverage, window-probe and growth error lists are empty. The three
steady RSS medians decrease (343404544 / 334342144 / 324845568 bytes), with
32 / 31 / 34 threads. There were 21,084 global layout notifications but only
711 title-bar geometry measurements, directly confirming that unrelated chat
layout no longer repeatedly traverses those native owners. Full-window chrome
CI 41172820214 passes both platforms, and Native apps 41172824208 builds/tests/
packages both. macOS still fails its strict pressure run. This successful
Windows run does not erase the failed samples below or prove their exact stacks.

Shared Python validation at 02b5940 caught three diagnostic labels using the
reserved `settings.*` vocabulary prefix. They are renamed `Settings.*` (matching
NativeLabel/NativePath telemetry naming); no UI string, word-list entry, scanner
rule or allowlist changed. The final candidate must validate that correction.
The diagnostic tool is isolated from shipped clients and disabled in normal
acceptance; its native stack snapshots do not change any gate or coverage.

Windows investigation update: normal instrumented 95391fb fails startup at
526.135 ms (CI 41172272959). Diagnostic-only 41172273041 records 496.444 ms
and captures the UI thread inside UpdateNativeTitleBarLayout's WinRT collection
iterator. Every global LayoutUpdated previously traversed native title-bar
owners and recomputed transforms even for unrelated conversation layout.
The client now marks these bounds dirty only for actual owner size, command,
XamlRoot/DPI, or window presenter changes; completed layout consumes that flag.
Two raw counters in heartbeat/completion record notifications versus actual
measurements. A new strict run and real caption-control captures must validate
this change. The sample establishes redundant work, not the original hang's
exact stack; the unmeasured native modal interval remains under investigation.

Earlier Windows integration repeat (retained failure evidence): the run
at 8d5f1ef (CI 41171258624) failed while opening Settings: maximum UI dispatch
1425.178 ms, WM_NULL timeout, 325.180 MiB peak RSS, 38 threads, early stop.
Its Windows source is identical to the passing e346d03 source below; the pass
must not hide this failure. No settings-page synchronous HTTP/wait or measured
long glyph/GC operation explains that interval yet. Add actual modal template,
measure/arrange and ShowAsync invocation timing and explicit diagnostic-only
managed thread stacks before choosing a fix. The 250 ms gate is unchanged.
The same integration passes builds/tests/packages and all four Python jobs;
those packages remain unaccepted. Mac pressure also fails (420.005 ms startup).

Windows/shared acceptance update (2026-10-31): normal CI **41170556043** at
**e346d033e6ef4aea74c30f9c8ce28c9d7e175354** passes all 175 exhaustive actions
and 130 observed random-click actions over 180.621 seconds, with no scenario,
watchdog, window-hang, resource-growth, or coverage errors. Maximum UI dispatch
delay is **124.198 ms**, peak RSS **451.414 MiB**, and peak threads **39**.
Three steady-window median RSS values are 372.197 / 356.012 / 354.742 MiB,
with 32 / 31 / 31 threads. Reports and raw timings are retained under
`S:\Codex\Outputs\Relic-native-performance\candidate-e346d03\windows`.
The synthetic fixture has 13 organizations, 90 members, 12,310 messages (5,500
in the largest group), 420 tasks, 796 events, 105 episodes, and 156 protocols.
It includes long Markdown and actual SSE/stored-message traffic during the
three-minute monkey phase. No personal store was read or uploaded.

The same source passes Native apps CI 41170559901 (330 Windows and 279 macOS
tests, both packages) and all four Python validation jobs in 41170559903.
Visual review 41169425156 is green as a report-only regression workflow;
required build, Python and responsiveness failures remain blocking.
Windows now yields native presentation between changed panes, uses the native
bottom anchor rather than repeated geometry-driven scrolling, virtualizes
all long lists, coalesces SSE refreshes, and prepares Markdown/ICU boundaries
and state-file writes off the UI thread. Earlier baseline 41161899958 fails
at 926.520 ms with a WM_NULL timeout. That baseline stopped early, so its
311.64 MiB / 35 threads are not a full-duration memory/thread comparison.
There was no dump from the person's original hang: these are reproduced code
contributors and CI evidence, not a claim about that process's exact stack.
macOS still has no full passing pressure run and is owned by its platform session.
PR #4 remains draft, open and unmerged; no local app or installed copy was launched.

Changes for the clients (macOS visual follow-up): actual inspection of all eight
e346d03 adaptive-window images found that **both dark macOS images retain raw
Markdown**, and `macos-zh-CN-dark-1440x900-group.png` has a blank inspector.
The corresponding light images and all four Windows images render correctly.
The green capture result therefore proves chrome/size checks, not settled
content. Mac owner: fix the actual readiness/production rendering path and
retain a regression assertion for prepared visible Markdown and all requested
panes before the full-window screenshot. Evidence is in
`S:\Codex\Outputs\Relic-native-visual\window-e346d03\macos` (CI 41170556047).
These images are not accepted as final, and no required content may be skipped.

Changes for the clients (2026-10-31, shared request resolved): the Windows
full-window failure reported in macOS REQUESTS.md for aa1be2f was an end-anchor
problem. Native ScrollViewer anchoring now follows the actual last row including
its bottom padding, without a geometry-driven ChangeView feedback loop. Both
platforms pass adaptive-window CI 41170556047 and chrome CI 41170556054 at
e346d03; all four Windows light/dark 1440x900 and 1024x700 images were inspected.
The capture still fails if the final conversation offset is over 2 px from the
end. Screenshots are under `S:\Codex\Outputs\Relic-native-visual\window-e346d03`.
This is a visual/scroll result, not a substitute for the strict pressure gate.
Merged macOS through 60d5f1b (background preparation of cold font glyphs);
the prior e346d03 Mac pressure sample still fails at 432.716 ms, so macOS remains
unaccepted. No tolerance or coverage changes were made.

Normal Windows acceptance first passed at dfca953 in CI 41168135315: all 175
exhaustive actions plus 155 real random-click actions over 181.135 seconds,
maximum UI dispatch delay 141.351 ms, peak RSS 442.547 MiB and 37 threads.
The three steady windows had 351.02 / 326.55 / 303.84 MiB median RSS and 32
threads each; all error lists are empty. macOS still failed its startup gate.
This is retained evidence, not the final candidate: another runner at 1d288de
measured NativePath.ICU.boundaries at 419.591 ms alongside a 405.857 ms UI delay.
The Windows parser now runs through one bounded background worker with shared
system ICU module handles; native text capture waits for actual prepared text.
State JSON serialization and atomic file replacement also move off the UI
thread into one latest-only writer per state file, drained on normal close.
New CI regressions cover actual ICU Unicode boundaries/cancellation and slow
state writes, coalescing, draining, and access failures. Normal e346d03 evidence
above verifies these changes with all original limits retained.

Windows evidence update (2026-10-31): diagnostic CI 41166109662 reproduced a
real `LayoutCycleException` in a private conversation. `MessageBubbleLayout`
and `CenteredFractionLayout` alternated infinite and constrained child measures
inside every pass; empty live footers were also used as scroll anchors. Commit
6247e5b uses one actual-width measure and omits only genuinely empty live rows.
The full diagnostic run 41166524688 at 5b6db6a then completed all 175 exhaustive
actions plus 120 actual random-click actions over 180.49 seconds, without an
application error: 100.301 ms maximum UI dispatch delay, 379.266 MiB peak RSS,
38 threads. Its diagnostic flag makes it explicitly ineligible for acceptance.
Normal run 41166524332 retained 88.143 ms but timed out waiting for the member
dialog; the capture previously awaited dismissal if preparation took over two
seconds. It now waits for the real `Opened` event with a bounded timeout before
closing. A new normal run must prove complete coverage; neither result above
is claimed as passing final acceptance. The original user's hang had no dump,
so the reproduced layout cycle is not asserted to be its exact call stack.

Changes for the clients: merged native-macos through 87f7b77, including unchanged
payload suppression, the TextKit measurement regression fix and direct Node
dictionary access. Shared heartbeat reads use Windows FILE_SHARE_DELETE and
atomic writers retry transient file-sharing errors without losing maxima.
Responsiveness limits and the required action/real-pointer coverage are unchanged.

The installed 1e1fc14 hung with real large data. Native responsiveness is now a
required gate before PR #4 can merge. The shared CI harness is being added at
`scripts/performance/`; its fixture is synthetic and never copies personal data.
Changes for the clients: `RELIC_PERF_MANIFEST` selects a CI-only performance run,
separate from `RELIC_VISUAL_MANIFEST` (which deliberately enables costly visual
diagnostics). `RELIC_PERF_OUTPUT` is an isolated state/report directory; the driver
supplies a private `RELIC_HOME`. The manifest carries `fixture` with actual server
port/token/home and `orgs:[{id,members:[name],group_messages}]`, `seconds:180`,
`seed:1729`, `max_ui_stall_ms:250`, and `output`. See the shared harness README
for ready/heartbeat/completion schemas. Start background UI dispatch probes
after framework initialization but before the initial organization load. A
blocked UI must not block heartbeat/failure recording. Exercise every group and
private chat, panes, dialogs, menus, breakpoint resizing, earlier history and a
seeded three-minute interaction loop. No local application launches are allowed.

Changes for the clients (observed random-click evidence): every monkey receipt
in `performance-complete.json.actions` now needs a unique `id:"monkey-<index>"`,
`pointer_target` (nonempty stable identity of the actual control), and
`click_events` (integer >= 1 counted by that control's real click/action handler).
The individual receipt count must equal `random_actions`, with at least two
distinct targets during the full 180 seconds. Windows uses real pointer input
and routed Click events. macOS must dispatch NSWindow mouse events or CGEvent
input and record the native action handler's observation; setting the model or
assigning a synthetic click count does not qualify. All existing latency,
duration, exhaustive coverage and resource gates remain unchanged. The schema
and pure receipt-validation regressions are in `scripts/performance/`.

Reference contract correction: app.js currently requests 1000 messages per
group/private page (lines 519/524), not 50. Both native clients retain that API
page size and use viewport virtualization to avoid constructing that many visual
trees. History uses the server's existing `before` cursor. The observed hang has
no surviving dump, so production thread-growth causes are not yet established.

Changes for the clients (shared requests resolved): the macOS proposed alternate
performance environment names are superseded by `scripts/performance/README.md`:
use `RELIC_PERF_MANIFEST` / `RELIC_PERF_OUTPUT`, never the visual manifest for
performance (visual diagnostics intentionally have extra cost). Keep the current
1000-message API page on both platforms; viewport virtualization handles the
page without eager view construction. Existing `before` responses expose all
older messages. The shared driver now includes the common exhaustive action IDs,
real first-message history checks, 180-second seeded deck, 10 Hz SSE hints and
one stored message every two seconds during the monkey phase. Both clients use
the same fixed 250 ms, memory plateau and thread-growth gates.

Baseline evidence: CI 41161899958 at instrumented 3099eb1 reproduces initial-load
UI blockage: native probe 926.5201 ms maximum, WM_NULL timeout, 311.64 MiB peak
RSS and 35 threads in the short failure sample. This run deliberately retains
pre-fix eager rendering and product diagnostics. The watchdog stopped it after
the first failure plus two seconds; it is not a full-duration resource peak.
The 1e1fc14 visual run 41159591873 had an overall success conclusion but both
native capture jobs retained failure checks. The report-only workflow now uses
step-level continuation and always writes original step outcomes to its artifact
and job summary. Appearance errors remain errors in those reports. Native builds,
Python validation and responsiveness remain separate required checks.

Mac baseline 41162500465 at 6a92a00 failed during startup: retained maximum
1986.742 ms, 133.281 MiB RSS, 8 threads. Like the Windows baseline this is an
early-failure sample, not a three-minute steady-state peak. Windows candidate
0572f10 still fails first-load latency (705.177 ms); it is not a deliverable.
The next diagnostic candidate records CI-only per-operation timings in
`timings.jsonl`, including realized row counts, text layout and actual drawing.
No startup interval, tolerance, or failing action is excluded from the gate.

Changes for the clients (large-list dialog coverage): the shared action deck
now returns to the largest organization before dialogs, and adds two ordinary
`kind:"dialog"` names, `tasks` and `protocols`, after the four existing names.
Open and close the actual existing task/protocol dialog and await its content;
do not substitute a sample view. This exercises the 180-task organization.

# Previous delivery policy — Amendments 5 and 6

Changes for the clients (2026-10-31, adaptive window placement): Windows stores
normal bounds in DIPs relative to a monitor work area, separately from maximized
state, in the per-user `window.json` beside `native-ui.json`. Default is centred
`min(1440x900 DIP, 85% work area)`, minimum `min(960x640 DIP, work area)`.
On a very small work area the minimum takes precedence over the 85% preference;
the window never exceeds the work area. An unavailable monitor or a saved size
that no longer fits falls back to a normal default; valid saved positions clamp
inside the current work area. Windows honors WM_DPICHANGED's suggested rectangle.
The person's 3840x2088 px work area at 150% gives 2160x1350 px (1440x900 DIP),
centred at (840,369), and a 1440x960 px minimum (960x640 DIP).

Changes for the clients (Amendment 6 capture contract): `native-window.yml`
uses the existing full-window driver with `--window-sizing`, preserving the
same four cases, light/dark and 1440x900/1024x700. The manifest adds
`window_units: "dip"` on Windows and `"point"` on macOS; the old titlebar mode
keeps its original physical-pixel Windows contract. Windows converts the
requested logical size using actual window DPI; macOS already uses points.
`window-report.json` and every original `.window-chrome.json` are retained.
The Windows `sizing` receipt records the untouched initial frame, work area,
actual DPI, default/minimum policy and final responsive pane sizes. The macOS
REQUESTS fields `initial_window_frame`, `visible_screen_frame`,
`minimum_window_size`, `inspector_overlay`, and `sidebar_width_pt` are retained
unchanged. No server API change is needed. Screenshots are actual full windows,
not scaled images. 150% screenshots are claimed only if actual window DPI is
144; the scale-independent sizing tests also cover 100/125/150/200%.

The production layout uses the reference's 1180 DIP inspector overlay,
900 DIP hidden title, and 820 DIP compact sidebar breakpoints. Startup closes
the inspector at 1180 DIP and below, as the reference does. Capture dimensions
are applied only behind the existing explicit GitHub Actions capture flags.
Windows custom DirectWrite labels and selectable text now also observe
`UISettings.TextScaleFactorChanged`, remeasure their glyphs and line breaks,
and keep text scaling separate from display DPI. Standard WinUI text controls
retain their native text-scale behavior; the root layout is never bitmap-scaled.
macOS uses AppKit point frames and autosaving, and caps its minimum to the
85% default on unusually small screens. Its startup/frame receipts requested in
`native/macos/REQUESTS.md` are preserved by the shared driver.
The macOS session's Windows startup request at d67957a is fixed in 9a9cdc9:
enumerate the actual DisplayArea vector with Count/index access, avoiding the
unsupported IEnumerable projection that produced E_NOINTERFACE. CI full-window
captures exercise this product startup path before applying capture dimensions.

The person accepted the current native appearance and ended element-parity
iteration. The historical requirements and measurements below remain evidence,
but element differences are now a report-only regression signal, not a release
blocker. No mismatch is relabeled as a match. Native builds/tests, shared Python
validation, packaging and whole-window title-bar captures remain required.
PR #4 stays open and unmerged; Claude owns merge and installation after the
person tries the app. No application or test is run on the person's desktop.

Changes for the clients (whole-window capture contract):
- The new CI workflow is `native-titlebar.yml`; driver is
  `scripts/visual/titlebar_capture.py --client windows|macos --exe ... --output ...`.
- It starts the existing isolated real fixture server and writes the same
  `RELIC_VISUAL_MANIFEST`, plus `RELIC_TITLEBAR_CAPTURE=1` and
  `capture_mode: "whole-window"`. Each process receives one `group` case.
- `width`/`height` are the complete native window's dimensions: 1440x900 or
  1024x700. Both light and dark use zh-CN. Preserve the real OS caption controls.
- Write the original full-window PNG at `output/case.file`, and
  `output/<case.id>.window-chrome.json` with actual window/client bounds, native
  window identity, scale and screenshot method. On macOS use the running app's
  `screencapture -l <window id>`, not ImageRenderer/cacheDisplay. The driver keeps
  actual PNG dimensions, including a native backing-scale factor if applicable.
- Both clients complete with the existing manifest-directory `complete.json` containing
  `{errors: [], count: 1}`. This mode omits element extraction and its IPC;
  it must not wait for a UIA/extraction request. Normal parity capture remains.
- macOS 031aa1a now implements the same manifest-directory completion and
  `.window-chrome.json` protocol directly; no compatibility adaptation is needed.
- The driver supplies language/theme preferences, isolated app state and the
  existing fixture clock. Native clients still use their production group
  selection, controls and title-bar setup. It never launches outside CI.
- The older element-report capture still targets the requested content viewport.
  Windows compensates for `ResizeClient` retaining the former caption height
  by resizing from actual XAML bounds; its viewport assertion is unchanged.
  Whole-window delivery captures continue to use the complete window dimensions.

Shared engine: merged main at 716ab44 (PR #6 wake prompts and receipts).
Changes for the clients (2026-10-31 shared validation request): the runner
integration fixture now retains each real `Popen` handle and waits for process
exit before reading final state or deleting its temporary database. Terminal
state is written before receipt/wake cleanup; it is not an exit notification.
Removed the fixture's cleanup-error suppression. This addresses the Windows
Python 3.11 SQLite WAL sharing violation reported by macOS in REQUESTS; production
receipt/wake ordering and the HTTP contract are unchanged. Tests run only in CI.
The latest macOS requests for additional empty/long parity scenes and more fill
attribution are retained in REQUESTS but are no longer new release work after
Amendment 5. Existing functional changes and their tests remain in the Mac branch.
The pending optional question about resolved font-weight evidence is superseded
by the report-only policy; the underlying comparison data is retained unchanged.
Changes for the clients (native semantic and template observations): Windows now
separates the Raw-only organization avatar container's provider Name from an
independently exposed accessible name. This requires the actual current avatar,
sealed organization row content, both full RuntimeId bindings and UIA parent
relationship; the actual initial, child providers and named parent row remain.
The original provider Name and all identity/exposure observations are retained.
The reader also accepts the exact SDK SelectorBarItem's measured base chain,
current ControlTemplate and complete children as template-only parent paint;
focus, child paint and Composition still require their independent observations.
Neither change rewrites historical missing receipts or changes gate tolerances.

CI status at 81cb4d2: Windows build/tests, shared extraction contracts (970 Python
and 125 JS tests), route/string parity and package validation pass. macOS tests
still fail in complete-message reading order and finite caret readiness; newer
native-macos fixes are being merged for CI. The full 672-case visual run
41151254453 is still running, so no new passing scene count is claimed.
# Native Relic App contract

Changes for the clients (Windows Composition observation): each scene now has an
explicit preparation phase that obtains and retains the actual loaded owners'
backing Visual objects before the existing render/commit/DwmFlush. The baseline
is established afterward; screenshot and getter checkpoints only read retained
objects. Receipts disclose potentially created handoff state and do not claim
unprepared production state, animation samples or final-pixel coverage. Missing,
replaced, unloaded and changed objects remain unknown. XAML clips stay separate.

Windows file-preview scroll correction: selecting a conversation applies its
current column layout before rendering, and ScrollToLatest finishes that current
layout immediately instead of scheduling a 40ms delayed scroll. Actual c8d6311
data showed the delayed action advancing from 209.13 to 232.23 after the file pane
narrowed the chat; the reference retained 209. This fixes the production timing
without changing message padding or capture coordinates. The combined headless
WinUI build passes with zero warnings/errors; fresh CI screenshots are required.

Latest downloaded diagnostic: b611b4f / run 41147774570, 22 scenes with paired
artifacts per platform; strict accepted scenes remain zero. Windows counts are
missing 94, extra 192, text 562, geometry 1243, style 8161, state 322; macOS counts
are missing 46, extra 601, text 0, geometry 550, style 6355, state 1327. This is not
the 672-scene acceptance run. Original JSON/HTML/PNGs are retained at
S:\Codex\Outputs\Relic-native-visual\parity-b611b4f\report-root.

Changes for the clients (observed Windows capture exit): b611b4f still failed
live-tool-output despite individually resolving all three original visible UIA
zero-area errors. The summary also required every raw node diagnostic to vanish,
including offscreen titlebar measurements the observer explicitly retained in
nonvisible_diagnostics. The resolver now respects that existing classification
only with exact per-node receipts and actual IsOffscreen=true; new, unknown,
visible and traversal errors still fail. All original records are retained.
This corrects exit handling, not scene acceptance or the element gate.

Changes for the clients (state-dot boundary measurement): when the existing
actual Ellipse stroke/contour receipt proves one closed, undashed state-dot
boundary, its stroke is represented once in border_* and radius properties.
The duplicate independent vector-stroke fields are nonapplicable, with every
original field retained in ellipse_border.stroke_applicability and raw evidence.
Other kinds, dashed/unknown contours, transformed or additional paint retain
their stroke fields. No element, tolerance or matcher rule is removed.

Windows select arrows now use the theme's primary ink in normal/focused states,
matching the reference's visible control paint instead of the SDK's secondary
glyph brush. Native selection, popup, disabled and keyboard behavior stay native.

Changes for the clients (Windows text prefix quantities): a successful actual
GetText(-1) / SysStringLen receipt now records logical UTF16 length independently
of CompareEndpoints structural position. A null BSTR can therefore have length
zero while its retained structural comparison is -2 and collapsed is false.
The reader validates both quantities independently. It does not rewrite older
raw records or use equal text offsets to invent cross-channel structural range
identity. The headless WinUI build passes; new regression tests run in CI.

Windows paint adjustment: the subgroup badge outline now uses the reference's
measured 1px stroke instead of 1.5px. Its dash/contour and remaining outline
measurements are still independently checked; this change does not certify them.
The current shared contract run f169dc3 (41149878734) passes, including the new
scrollbar diagnostic and actual appearance swatch tests.

Changes for the clients (macOS request, 2026-10-31): the reference extractor now
reads selected state for the actual appearance preference swatch buttons from
their production `on` class. The selector is limited to `.swatches>button.swatch`;
chart legend swatches remain nonselectable. Shared tests exercise actual
drawAppearance/setPrefs/redraw and clicks, including selected/unselected states,
the `/api/prefs` write and unrelated swatches. This resolves the request in
native/macos/REQUESTS.md without erasing native state or changing tolerances.

Changes for the clients (post-capture scrollbar evidence): reference capture now
records a bounded diagnostic of actual pointer hover and gutter PNG responses
after the original scene checkpoints. It retains the exact browser revision,
DOM owner, input calls, geometry/scroll/focus observations and restoration receipt.
The original PNG and canonical elements are unchanged; observed hit bounds stay
diagnostic until real CI evidence is reviewed. Unsupported and failed observations
remain explicit and do not remove any extraction error or parity requirement.

CI status at b611b4f: Windows, shared extraction contracts and package validation
pass. The macOS build/test job fails in MessageReadingOrderTests and
NativeCaretReadinessTests; subsequent native-macos changes address those tests
and require another actual CI run. The obsolete c8d6311 smoke capture is retained
under S:\Codex\Outputs\Relic-native-visual\parity-c8d6311\windows-root.
No scene is accepted by the strict element gate.

Changes for the clients (final Windows frame publication): the actual text-range
observer now ends and publishes its final sidecar atomically before the native
probes receipt reports success. Previously that file was only written later in
VisualCapture.finally, racing the Python reader. Failed scenes retain their
cleanup/publication path; an already published file is not rewritten and failed
writes are not retried implicitly. No timeout or measurement is extended.
The headless WinUI build passes with zero warnings/errors; actual CI capture is
still required. fd6ceb9's independent contract suite also passes (41147536434).

Changes for the clients (informational token state): the Windows reader reuses
the exact sealed OverviewToken template/content identity contract plus actual
no-peer, IsTabStop=false and unfocused observations to distinguish its container
from an interactive control. Only that container's enabled/focused defaults are
nonapplicable; raw values remain in the audit. Real peer/action/focus evidence,
hover, tooltips and each child TextPattern remain independent and unchanged.
The real 35ac04a badge/chip fixture contains no reference expectations. Seven
regression methods include unknown templates, replaced children and real actions.

CI progress: 37e5ae4's independent extraction-contract run 41147326267 passes all
944 Python tests and the reference JavaScript checks. c8d6311's new actual native
capture is still running. No full scene or final element gate is yet accepted.

Changes for the clients (shared CI): native-element-checks.yml now runs on
relevant native branch pushes as well as its unchanged reusable workflow_call.
This runs the same full extraction-contract suite while platform jobs wait for
runners; it does not replace either required native build or the full visual
gate. Direct dispatch was rejected because this reusable workflow is absent
from the default branch; no default-branch change was made.
c8d6311 ran 944 tests with one provenance assertion failure: the effective
geometry source should identify the selected actual COM channel, while the
original source belongs in the immutable audit. The regression now explicitly
checks both original range records and that distinct effective source.

Changes for the clients (observed UIA range geometry): the Windows reader can
select actual in-process public COM doubles for an external zero-area range
only after exact peer/RuntimeId/observer, UTF-16 endpoints/category, HRESULT,
IEEE754, stable object checkpoints, QPC, origin and scale binding. The original
external JSON, values and diagnostics remain immutable and linked in the audit.
35ac04a's last tool line measures 0.4000244140625px through that channel, yielding
client (1117,899,180,0.4000244140625), not the different WinRT y coordinate.
Only individually resolved original geometry errors can clear exit 1; unknown
prefixes, unrelated failures, and all other evidence obligations still fail.
Eleven pure regression methods cover the real capture and corrupted bindings;
they run in CI, not locally.

Changes for the clients (tab configured font weight): an actual SelectorBarItem
label's Run.FontWeight getter can now be read through its existing measured
Tag/ContentPresenter/text-source binding. Three recorded 35ac04a tabs plus six
regression methods reject mismatched owners, incomplete subtrees, forged getters
and partial sources. This supplies configured weight only; no resolved font or
paint value is inferred. The separate proposed font-weight contract clarification
is awaiting the person's answer; the current resolved-weight gate is unchanged.

Changes for the clients (Markdown tables): Windows keeps the table's 6px
vertical margins inside its horizontal scroll wrapper, so surrounding block
margins cannot absorb them. Actual cells now draw complete 1px borders centered
on shared grid lines (half-border negative margin and outer half-border padding),
preserving the measured content origins and total table size. This follows the
reference's collapsed-border layout; the actual new pixels still need CI review.

Latest comparable smoke report: 35ac04a / 41142421196 has 22 paired cases per
platform, not a full acceptance matrix. Windows missing/extra/text/geometry/style/
state are 93/259/632/1283/8560/708, with 76479 extraction errors. macOS counts
are 46/610/0/550/6398/1327, with 26830 extraction errors. No scene passes and no
exception is approved. Unmodified JSON/HTML/PNGs are downloaded under
S:\Codex\Outputs\Relic-native-visual\parity-35ac04a\report-root.
19c2c0f's Windows and shared checks pass; its macOS test exposes metadata before
avatar in the complete production message row. The macOS owner has recorded
the failure; partial isolated passing tests do not replace that regression.

Changes for the clients (conversation action chips): Windows now applies the
actual .chip-btn.on violet background, 45% violet border and foreground to
plain-language/digest actions, including hover. Its two nonselectable labels
use the existing production NativeLabel draw path at the reference's fixed
12.5px/20px metrics; the containing Button retains its real action, focus,
disabled state, tooltip and accessible name. The label and icon observe the
actual ContentPresenter foreground. These are production changes, not capture
substitutions. The headless build passes; new CI pixels/geometry remain required.

CI progress: dfeab56's Windows and macOS builds/tests, static parity and 920
element-contract tests all pass (41143598958). The 35ac04a Windows smoke capture
still fails in live-tool-output: external UIA reports a zero-height final line,
while the newly recorded same-peer in-process COM format range retains its
actual 0.4000244140625px height. Raw records and failures remain intact; this is
not a completed scene or a passed element gate. Latest macOS commits add actual
form focus paint and message metadata reading priority, with no shared request.

Changes for the clients (digest fixture request): the reference digest scene
now seeds its deterministic data, then invokes the existing production
toggleDigest path, updating both renderHead and renderBanner. Previously its
card was open while the header remained stale. A CI-only regression executes
that actual production function and checks the open card/header and saved state
together. Reference app.js/CSS and native selected colors are unchanged.

Changes for the clients (actual Rectangle corners): capture extends the existing
Shape input receipt to exact Rectangle, including the real Stretch and radii.
The reader interprets only measured Fill, nondegenerate circular centered stroke
and unit-translation inputs using the pinned WinUI primitive source. The four
chart legend inputs RadiusX/Y=4 and stroke=1 imply a nominal outer radius 4.5,
not the old default zero. Raw parameters stay intact; unsupported or historical
inputs stay unknown, and no occlusion/dash/pixel obligation is promoted.

CI progress: dfeab56's 920 element-contract tests pass. Recompare 41143059680
preserves the archived 215a313 canonical element JSON, so its counts are unchanged;
it does not rerun native projection or validate new production styles. The older
bdce3ab full run 41141133100 was superseded/cancelled to release runner capacity;
the latest full matrix retains all 672 cases per platform. New capture evidence
is still required before any scene can be called accepted.

Changes for the clients (font weight quantity): verified trimmed NativeLabel
draws can now report the weights of their complete actually submitted glyph/font
set, while original source_span_complete remains false. The additive coverage
receipt rechecks every real run, face and unique wght axis; a completion flag or
face-name set alone cannot establish it. Zero weight tolerance, reference-side
unknown failures and all independent final-PNG/geometry obligations are unchanged.
834a5f5's 914 contract tests exposed three assertions tied to the old error-word
spelling; they now assert the actual unresolved source/font quantity and retained
measurement error instead. No expected unknown result was changed to success.

Changes for the clients (macOS successful-test diagnostics request): the existing
native-macos-draw-diagnostics artifact now uploads on success as well as failure,
so the small actual surface context records are retained. Failed bitmap outputs
still originate only from failed comparisons. The owner added call-boundary
receipts for the 1280x800 rename stall; the shared watchdog stays at its original
deadline and no case is excluded. No cause or resolution is inferred from an
idle main-thread sample alone.

Changes for the clients (current label/font sources): the Windows selector reader
now compares CLR nested FullName (`Outer+Inner`) to the real Type.Name correctly;
215a313's ReferenceVectorIcon caused otherwise valid current tab label bindings
to fail. Independent icons, nested actions and all old identity checks remain.
Trimmed NativeLabel fonts can now come from all actually submitted glyph runs,
including a separately bound real ellipsis inline object. Complete original
source coverage remains false, the omitted suffix is retained, and font weight,
geometry and final PNG coverage keep their independent failures. A reduced real
67ed20d fixture preserves each label's own original frame/object evidence.

Changes for the clients (form accessibility): each native form input now points
through LabeledBy to its actual visible caption; callers pass the exact TextBox
or ComboBox rather than the voice-field wrapper. Caption text and the microphone
peer are unchanged. The reference's voice-enabled composite label names still
include that microphone name and are not yet identical; no name is synthesized
in extraction to conceal this remaining difference.

Changes for the clients (latest macOS requests consumed): the owner reports
239 passing tests at dea54e8 and retains the full bitmap assertion. Its subsequent
message-avatar priority uses the actual source row, and surface context metadata
records the live draw format. System titlebar filter names are diagnostic only;
no undocumented filter is treated as harmless. The owner's 1280x800 rename
timeout and partial language captures remain open measurement failures.

Changes for the clients (native sidebar own paint): the extractor now observes
the exact sealed NativeSidebarRow class, its real current template and unique
ContentPresenter/Content object binding. This closes the local derived-class
contract gap without treating arbitrary derived controls as SDK primitives.
Actual child paint, focus, Composition and historical missing receipts still
have independent checks; seven pure regression cases run only in CI.

Latest full-matrix baseline, 215a313 / workflow 41100560921: the compare job
processed all 672 expected scene names, but Windows had only 668 paired artifact
sets and macOS 634. Both measured/passed counts remain zero. Windows paired
124570 elements with missing/extra/text/geometry/style/state counts
4678/8680/17200/65754/399642/15190 and 2078444 extraction errors. macOS paired
119702 with counts 9118/24328/43/34029/162264/13068 and 577063 extraction errors.
These totals cover a much larger matrix than the earlier 22-case smoke report
and are not a like-for-like regression comparison. Exceptions remain empty.

Changes for the clients (measured Windows style corrections): the two file-header
action icons now retain their button's ink-2 foreground, matching .icon-btn;
the separate leading file glyph retains ink-3. Custom tab/resize hosts explicitly
declare the zero border their authored templates render, and the chat region
paints its own reference bg in both themes. These are production properties,
not substitutions in extraction. Actual 215a313 evidence identified the mismatch.
Small-window message hover/copy captures now ask the actual native scroll
presenter to bring the target row into view before the unchanged visibility
assertion, matching the reference's real hover operation. Subsequent CI must
verify the visual changes and the four previously failing hover/copy cases.
The member model/effort dropdowns explicitly use ink, and 26px form microphones
use a 13px corner radius rather than retaining the 32px variant's 16px radius.

Changes for the clients (same-process UIA ranges): the existing native COM reader
also enumerates actual Format units within each observed visible range, keeping
raw HRESULTs, doubles and document-prefix endpoints. This closes a diagnostic
gap; it does not replace external UIA data or suppress zero-area failures.

Changes for the clients (resumed measurement fixes): Windows tab paint now has
an independent actual Tag/Border.Child identity receipt. Only a coextensive,
unchanged simple surface can supply its owner's measured paint; independent
content and unresolved Composition shadows remain in the evidence and gate.
The inset-shadow reader compares local dimensions to local dimensions and
window bounds to window bounds, and reads a filled Shape's actual Fill rather
than its Stroke. The reduced 67ed20d receipt is a regression fixture; no native
geometry or expected reference values are manufactured. The custom avatar host
now explicitly has zero border thickness because its retained paint owns rings.

Changes for the clients (reference trace boundary): tracing ends directly after
the actual screenshot marker, before supplementary LayerTree/font diagnostics.
Stop/export keeps its original deadline and every loss/error. Later diagnostics
have a separate retained host-clock phase receipt, not fabricated trace markers.
The existing archived paint decode completed all 134 unique SKPs, but text-to-DOM
attribution and final screenshot paint ownership remain unproven; these records
do not replace canonical measurements or satisfy the parity gate.

Resume evidence: native build/test workflow 41100569170 and package workflow
41100569283 passed at 215a313. Its smoke 41100562213 and full 41100560921 both
failed; build success is not element parity. PR #4 remains draft and unmerged.

Changes for the clients (macOS requests consumed): the latest owner branch
records real NSCell paint switches and exact scroll AX focus separately from
the surrounding SwiftUI focus binding, and retains actual layer filter names.
Those observations do not establish generic filter/occlusion semantics or hide
elements. Its search field changes and field-editor observations need the next
merged CI capture. No tolerance, exception or matrix change is accepted.

Changes for the clients (settings surface ownership): only the Windows settings
dialog now uses its real BackgroundElement as the overall light/dark fill. Its
SDK TopOverlay and authored body retain hit testing with transparent brushes.
Navigation fill/right border, sizing, clipping, shadows and dialog lifecycle are
unchanged; other dialogs keep the default behavior. This removes duplicated
production fills rather than hiding their records in the extractor. Both themes
and all sizes still need actual CI verification.

Capture evidence at 67ed20d: both panel scenes satisfy the unchanged readiness
budget and all post-PNG state/event checkpoints; Markdown has no visible error
banner or UIA extraction failure. Live tool output still loses one 0.400024px
text-range height in the external UIA channel. All 132 observer DPI readings are
PMv2, so DPI declaration did not explain that loss. Original values/errors remain.
Both platforms have 22 artifact sets, but zero fully measured/passing scenes.
The older efd2025 full run 41090672407 was superseded after repeated known capture
failures; its artifacts remain and cancellation is not acceptance. The latest
full workflow still requires all 672 cases per platform.

Changes for the clients (macOS shadow regression consumed): 663ced3's 236 tests
exposed 107 changed rounded-edge pixels for a shadowed fill. The owner retained
its prior native fill path for shadowed surfaces, with the unchanged whole-PNG
assertion; owned-image opacity remains unknown there. Passed scoped navigation
priority tests are now applied to message rows without inventory/coordinate
sorting. Both production changes need subsequent captures.

Changes for the clients (actual selected-tab labels): Windows captures the real
SelectorBarItem.Tag / ContentPresenter.Content binding, complete current subtree
and text getters. A single visible text source without nested interactive controls
can belong to its tab even when its selected background/shadow is separate paint.
All backgrounds, shadows, original nodes and unknown measurements are retained.
Historical captures without this receipt are not retroactively filled.

Changes for the clients (anonymous container correspondence): a container can
be paired by its complete already-paired descendant set only when that signature
is unique on both sides, in the same region/kind and nearest paired ancestor,
with at least two independent descendant anchors. A button and its own icon are
one anchor. Geometry/colors do not decide correspondence and still undergo the
same comparisons. This addresses the real d59bede settings nav wrongly paired
to an outer white Grid; two independent native white layers remain extras.

Changes for the clients (one producer experiment, existing payload decoding):
187667e's single 16MiB request produced real multi-megabyte Renderer SKPs. The
headless file-code case has a payload between its PNG clock markers, but trace
loss/discard errors remain. Chromium's three traces overflowed the central buffer
and lost those markers. No canonical font/clip measurement is promoted. CI will
decode the three saved Chromium cases plus the saved headless file-code case,
without recapture or another buffer experiment. The explicit archive mode checks
every original trace payload and alias; decoder reuse requires the same actual
version/revision/platform/DEPS and retained build bytes. Old fixed-count mode is
unchanged. Per-channel attempts and original trace failures stay in the artifact.

Changes for the clients (Windows retained logo clip): the existing production
logo-clip assignment now retains its actual Image, XamlRoot and backing Visual.
Unload invalidates the binding. Authoritative capture reads only those retained
objects and records the revision, current clip/geometry identities and unchanged
properties. It never creates a handoff visual. The reader can measure that bound
contour while keeping final compositor/PNG coverage unknown; every other owner's
unmeasured backing clip still fails. No hardcoded radius supplies a measurement.

Changes for the clients (conversation metadata wrapping): Windows date dividers,
read receipts and historical tool timestamps now use WrapWholeWords, matching
the reference's normal word wrapping outside message bubbles. Actual d59bede
group/private receipts showed emergency word breaking enabled in these native
labels. Font metrics and dimensions are unchanged. The short strings at 1440px
did not visibly split; multi-size CI still has to verify the resulting layout.

Changes for the clients (macOS toolbar/pointer requests consumed): the owner moved
each toolbar badge inside its actual Button label and separately records the
real NSView mouse receiver and that receiver's AX hit. Unknown SwiftUI pointer
ownership stays unknown. These changes still require their own actual captures;
98841c1's 230 Mac tests failed the two earlier content-AX-hit assertions.
The owner superseded its obsolete CI runs without excluding any required case.

Changes for the clients (macOS current-editor request consumed): the shared reader
now accepts appkit-current-field-editor-v3 only with the actual three base-type
observations, retained owner/editor runtime classes and nonempty control class.
The existing strict currentEditor/controlView, value, UTF-16 selection, window,
focus, unique-owner, geometry and independent-paint checks remain mandatory.
V2 behavior is unchanged and V1 remains rejected. Seven synthetic test methods
run in CI; real native captures are still required. The owner's opaque-candidate
diagnostics remove no elements; unknown occlusion still fails the shared gate.

Changes for the clients (Windows placeholder source): NativeTextarea now records
its actual already-applied PlaceholderTextContentPresenter object and the retained
parent chain, with current text, visibility and style before/after readback.
The shared reader uses that part's three text properties only for a proven visible
placeholder of the current empty input. Missing, changed, hidden, occluded or
ambiguous ownership leaves those quantities unknown. Owner configuration, the
raw placeholder and resize Thumb, geometry and all paint failures are preserved.
No template is applied or composition visual created by this read-only capture.

Changes for the clients (macOS navigation evidence): the owner reports actual
98841c1 file header/actions preceding the contents. Outgoing message avatar order
still disagrees; its new mounted test evaluates native navigation priorities
without enabling a production change or sorting by reference coordinates.

Changes for the clients (one producer-buffer hypothesis control): paint-only
diagnostics accept an optional 16MiB producer SMB request, with default zero
preserving the original launch. This uses the fixed Chromium feature parameter,
preserves its observed screenshot feature, and records the actual trace command
line. Actual SMB capacity and lost-packet content identity remain unmeasured.
The central 200MiB buffer, three diagnostic scenes, trace categories and all loss/
attribution failures stay unchanged. This is one causal experiment, not a repair
claim or a new acceptance path; no further parameter sweep is authorized here.

Changes for the clients (observer DPI contract): the out-of-process UIA observer
now explicitly declares PerMonitorV2/asInvoker in its executable manifest. Six
actual native thread-context readings bracket early UIA construction and window
reads. They preserve raw API returns/exceptions and distinguish PMv1 from PMv2;
unknown/non-PMv2 readings fail. This removes dependence on PresentationCore load
timing, not a proven explanation for fractional rectangles becoming zero. No
provider, rectangle, coordinate transform or existing failure is rewritten.
The app and observer headless builds pass; ten mock cases run in CI.

Changes for the clients (panel readiness phase completion): d59bede's real drag
completed at the correct pane geometry while Thumb hover was not yet delivered.
The old after-action assertion still ran before the relocated final settling
wait. It now records that preparation state and performs the same required hover
assertion after the existing bounded wait, before any screenshot baseline.
Subsequent state/event identity comparisons and all time budgets stay unchanged.

Capture evidence at d59bede: settings-navigation-hover now retains actual hover,
hit-test inclusion and the same bounds through after_element_extraction; group
has 24 bound avatar lifetime lookups. Remaining capture failures are live tool
UIA rectangles, panel preparation and Markdown UIA rectangles/application error.
These are partial repairs, not scene acceptance. Browser paint trace still loses
producer packets; both new Chromium variants expose only the old empty Renderer
SKP bytes. No font or ellipsis unknown is cleared on that evidence.

Changes for the clients (macOS banner request consumed): the owner independently
replaced its fixed icon column with native CoreText/CFStringTokenizer intrinsic
flex sizing and SVG meet geometry. It uses actual attributed text and no scene
coordinates. Mounted layout and whole-scene results remain for CI.

Changes for the clients (detail-tab initialization): 55d8eca file-markdown shows
a real InfoBar reporting child collection mutation during measure/arrange.
Its twelve NativePathText receipts are laid-out without fallback failure. The
detail SelectorBar can synchronously publish its initial selection and rebuild
the same parent. A same-selection guard now prevents this code-level reentry,
while real mode changes retain their callbacks. The existing capture error log
also retains caught Exception.ToString after startup; the InfoBar stays visible.
The old artifact lacks the original stack, so CI must confirm the actual cause.

Changes for the clients (macOS request consumed after 98841c1): hosted fill and
actual light/dark bitmap tests pass at 06890e8, and the owner enabled fill images.
Pointer assertions still fail there; later fixes need capture. Message-action
capture now appends its own observation rather than replacing independent
pointer/fill/layer evidence, preserving incomplete receipts and existing errors.

Changes for the clients (private-chat banner flex layout): Windows now uses
actual production text clusters/normal-break boundaries to allocate the icon and
selectable text with two flex-shrink factors of one. The old fixed 15px icon
viewport disagreed with measured reference widths at different languages/sizes.
The production source layout also records DirectWrite GetMetrics/DetermineMinWidth;
its minimum and the ICU-policy minimum remain separate measurements. Failed
measurement retains the old fixed-icon/selectable-text fallback and the failure.
Other icons and path/notice text keep their defaults. Headless build passes;
pure allocation/source-contract tests and actual pixels remain for CI.

Changes for the clients (macOS icon/pointer request consumed): six hosted icon
bitmap tests passed in 41089755638, and the owner enabled the icon backing image.
That run still failed two pointer assertions. The updated tests accept only the
actual NSButton or its exact owned NSButtonCell and retain covered-button negative
checks. Actual NSCell.controlView identity is added, without synthesizing hover.

Changes for the clients (browser paint diagnostic load): tracing retains full
picture/frame exports but omits the category that additionally serializes each
operation as another SKP. Actual 9f11a82 has 705 such references plus 38 complete
picture references and recorded producer packet loss. The 118 unique SKPs were
all decoded, without a missed page glyph payload. The new category receipt does
not claim loss prevention or final-scene attribution; those remain CI questions.
No canonical font, ellipsis measurement or strict comparison is changed.

Changes for the clients (macOS navigation request consumed): actual AX navigation
order is used only when it is an exact object-identity permutation of ordinary
children. Both arrays and the chosen API are retained. No missing, duplicated or
foreign child is accepted, and no ordering is derived from reference geometry.
The owner's current hosted tests and production captures still need CI review.

Changes for the clients (source-derived platform vocabulary): the static scan
now records each original reference key occurrence and its proven source branch.
The reference's four desktop-connection keys exist only inside if(isMac()) and
are still required on macOS; Windows must not add controls absent from its actual
reference. Only a unique, unshadowed canonical platform predicate and explicit
braced branches constrain uses. Unknown syntax, other uses or HTML occurrences
remain dual-platform. The complete original key union, source lines and guards
are retained in native-parity.json. This corrects the former unconditional union
scan; no key exception, dead native reference, route/flow change or element-gate
change is added. Sixteen source-only regression methods run in CI.

Changes for the clients (macOS appearance request consumed at efd2025): owned
label/icon/fill painters now execute the existing drawing in the mounted view's
actual effectiveAppearance. Hosted Aqua/Dark Aqua bitmap tests compare original
and candidate paint and require the themes to differ; no expected colors are
inserted into receipts. Candidate/production and occlusion limits remain intact.

Changes for the clients (report count definitions): the report now separately
counts cases with both JSON/PNG artifact sets and cases with at least one paired
element. Neither count implies readable, complete or matching measurements.
scenes_checked still requires no extraction errors; scenes_passed keeps every
existing strict requirement. Definitions and per-case file-presence receipts
make a 22-case diagnostic run distinguishable from the required 672-case matrix.
Missing captures and failed extraction fixtures exercise these distinctions.

Changes for the clients (profile spoken name): Windows now composes the profile
button name from its actual initials/name/subtitle children. page.me remains the
tooltip, while side.profile remains the visible subtitle. This repairs the real
3a924e7 name mismatch without changing the visible words or avatar label policy.

Changes for the clients (macOS compile repair and isolated paint candidates):
the measured text clip's NSNull/dictionary conditional now has an explicit Any
type, fixing the Swift build error in runs 41088852536 and 41089334759. The owner's
icon/fill backing-image candidates remain disabled in production pending mounted
bitmap tests; no private layer is allowlisted, and occlusion remains unproved.

Changes for the clients (non-mutating composition observation): the Windows
extractor no longer calls GetElementVisual for each element between the PNG and
UIA reads. Fixed WinUI source shows this getter can create handoff visuals and
register transform listeners. Actual 2f4bd19 evidence has newly zero-sized visuals,
an extra dialog-origin offset in UIA, and a later PointerExited while pixels stay
in place. This is a cause candidate, not a proven fix until CI recapture. Without
a production-retained backing Visual binding, Composition clip now explicitly
remains unmeasured and fails. XAML Clip evidence is retained. No offset subtraction,
hover restoration, SDK upgrade, missing-value default or tolerance change occurs.
Three pure regressions cover unknown-versus-absent and the capture API boundary.

Changes for the clients (macOS focus request consumed): the owner added actual
initial focus for the new organization/member, edit-member, session search and
forward-reply dialogs, plus clicked recipient/tool disclosures. Mounted native
responder tests accompany this; current scene state still needs CI verification.

Changes for the clients (avatar object lifetime): the actual PersonPicture now
owns its composition through a private attached dependency property, preserving
the existing paint/template. The capture records every lookup, including absent,
detached or failed values, instead of silently omitting avatars whose managed
weak-key lookup fails. The 3a924e7 tree had 24 PersonPictures and no part receipts;
the exact GC/RCW cause was not observed. Native readback and actual owner/part
identity checks remain mandatory. Headless build passes; CI capture is pending.

Changes for the clients (panel tooltip sequencing): the existing single final
1000ms settling budget now runs after native label render preparation, before
the screenshot baseline. Actual current IsOpen transitions must have their own
Opened/Closed event delivered; an older event cannot prove a reopened tooltip.
No pointer, popup state, baseline comparison or deadline is changed. The actual
2f4bd19 event arrived after its former baseline, causing the strict failure.
Ten synthetic fixture cases cover delivery and timing; CI verifies the capture.

CI status at 55d8eca: both native build/test jobs and shared element contracts
pass; the all-platform static route/key job still fails. No scene has passed the
strict element gate. The obsolete 9b34ccf full run 41078767688 was cancelled after
failed shards, retaining its artifacts; it included the since-repaired macOS
blank-label candidate. The current full run retains all 672 cases per platform.

Changes for the clients (macOS requests consumed after 55d8eca): hosted label
bitmap tests now pass and the owner enabled that implementation for production
capture. Actual visible text-line clipping and passive pointer AX hit-chain
receipts are merged. The pointer receipt does not yet establish CSS-equivalent
hover, and native bitmap unit tests do not establish full-scene acceptance.

Changes for the clients (actual sidebar accessibility): NativeSidebarRow retains
ListViewItem selection/name behavior and implements organization ExpandCollapse
against the same live folded/search state as the arrow. Leaf rows report LeafNode
and reject expansion actions. Chat ItemStatus and unread observations use the
actual retained unread badge and its visible parent chain; detached content stays
unknown. Seven pure action/state cases run in CI; current templates/peers await
capture. Geometry, text and comparison thresholds are unchanged.

Changes for the clients (actual toggle paint ownership): 3a924e7's two Overview
toggle tracks were independently projected as cards, pairing a 32x18 track with
the reference 14x14 thumb and leaving the real thumb extra. Existing retained
parts/full RuntimeId evidence now additionally binds the track's paint to its
toggle owner after exact current closure/geometry/transform checks. The thumb
remains independent, and raw track paint/unknown measurements remain in evidence.
Five negative/ownership regressions run in CI; no scene or tolerance is changed.

Changes for the clients (measured outline coordinate correction): the reference
chart's actual ancestor matrix(1,0,0,1,542,125) was incorrectly treated as changing
outline lengths. The extractor now parses actual computed 2D matrices and accepts
only an exactly identity linear part with finite translation and unchanged other
axis properties. Raw matrices remain recorded. Three Node regression cases cover
translation and rejected scales, rotations, perspective and unavailable APIs.
Unmeasured outline contour/dashes and reference scrollbar properties still fail.

Changes for the clients (organization purpose wrapping): Windows purpose uses
WrapWholeWords to preserve the reference's normal word-break/overflow-wrap rules.
The three-line clamp, ellipsis and click-to-expand behavior are retained.

Changes for the clients (macOS follow-up consumed at 2283588): REQUESTS.md records
that actual 63fc431 still shifted the expanded tool row by 97px. The client now
preserves its real pre-click clip origin after disclosure layout and cancels that
pending restoration on navigation/content changes. Its new native scroll-view
test and label-layer candidate changes are merged; no shared payload is required.
02df6a9 macOS CI still reports seven label-candidate assertions failing. This is
not acceptance evidence and the next capture must verify the newer implementation.

Changes for the clients (actual secretary bubble inset): Windows now paints the
reference's zero-blur inner shadow with a retained native Path produced by D2D
EXCLUDE on the actual rounded padding edge. The former 3px left border is removed;
normal padding is restored. Plain-word bubbles retain their separate 1px border
and the same inset effect, as the production CSS specifies. Ownership receipts
bind the real Border/content/Canvas/Path and operation output. They do not relabel
old border captures or prove final raster contribution; those unknowns still fail.
Six pure geometry/COM ABI and seven reader negative cases run in CI.

Changes for the clients (actual text-provider coordinate repair): f6220c9 binds
the same NativePathText/range through WinRT and COM, but exposes a production
double-clipping offset: y=96+(96-77.6499939), instead of the actual clip y=96.
The provider now uses the un-clipped owner-to-root transform, real local clip
and actual rasterization scale. Its WinRT quantity is RasterizedClient; the SDK
owns screen translation. RangeFromPoint uses the inverse transform. The original
fractional extent is preserved, with no rounding or invented minimum size.
Fifteen pure coordinate cases run in CI; external COM precision loss still fails.

Changes for the clients (reference startup sequencing): capture and paint tracing
share one bounded read-only boot wait. The original stream-populated condition
could precede the production startup loadCc and race the scene hook's request.
The same 30-second wait now also checks actual loaded/items/unread state through
the existing observation hook. It sends no extra requests, retries no load and
retains the existing superseded-request failure. Production reference UI and
loadCc are unchanged. Two Python and three Node regression cases run in CI.

Changes for the clients (actual side-panel region): Windows had attached the
localized Side panel name to its inner scrolling StackPanel, excluding the tabs
and extending below the viewport. The reference names the full aside. The actual
outer pane now uses the existing NativeRegionGrid peer and owns that localized
name; its inner content has no duplicate region name. Border, width and tab/content
layout are retained. This fixes production accessibility ownership rather than
teaching the matcher to pair the wrong region by its expected rectangle.

Changes for the clients (macOS actual hosted-render regression): native-macos
reports that 0d3d681's actual smoke PNGs have blank ReferenceLabel text and null
glyph receipts. It restores the prior production draw path in f538c9d and keeps
the owned-layer approach behind an explicit test-only candidate. Mounted
NSHostingView/cacheDisplay tests now exercise that lifecycle; the prior direct
bitmap tests did not prove it. The original ContentLayer uncertainty remains.
The shared fill contract is also consumed: the same observed fill and layer
arrays are copied into both raw AX and elements.capture_evidence. The live-tool
disclosure scroll guard now survives consecutive layout passes until real content
revision, with actual status-dot ancestry retained. All require new CI captures.

Changes for the clients (remaining hover diagnosis): the existing Windows
settings-hover journal now retains actual receiving/foreground HWNDs, process
and class identities, activation, hit-test flags and popup count at pointer
events/checkpoints. f6220c9 still loses hover with identical cursor coordinates
and XAML bounds; the cause is not established. The observer never changes focus
or restores hover, and the original state gate remains unchanged.
The macOS `CGImage.typeID` compile correction was merged from cc4d1cd, together
with actual model/presentation layer ancestry observations from 238836d.
Layer metadata alone still does not prove final-frame occlusion.

Changes for the clients (measured Windows production layout fixes): message
headers now apply the fixed reference engine's primary-font integer ascent /
descent and floored upper leading to their actual production DirectWrite layout.
The original natural metrics, actual primary face and applied line spacing are
retained. This explains the observed 17.296875 versus 16.25 header height without
scene-specific offsets. Overview modes reuse the existing native segmented
surface with its actual shadow-1. Hierarchy selects restore the reference's
15px content inset (1px border + 10px CSS padding + 4px UA start margin).
The application headless build passes; new layout tests and captures run in CI.

9b34ccf Windows CI now passes both suites: 48 core and 165 capture tests.
f6220c9 macOS job 124139217709 instead fails test compilation at
`OutlineDrawTests.swift:44`: `CGImageGetTypeID()` must use `CGImage.typeID`
under the current Swift SDK. The correction is now merged from cc4d1cd and awaits
CI; the earlier compiler failure is not a passed bitmap/layer assertion.

Changes for the clients (pane-capture preparation boundary): 06b914e retains
an additional actual PointerMoved and an owned ToolTip opening during render /
commit preparation, before the first screenshot. The action checkpoint still
validates and retains its actual gesture/hover/tooltip state. Frame stability
now starts immediately before readback, after that preparation, as it does for
NativeLabel. All subsequent state and event-count equality checks remain exact.
The actual tooltip is included in the native capture and still compares against
the reference; no tooltip is hidden or granted a parity exception.

Changes for the clients (macOS popup-fill shared request): the shared reader
is being added for actual `native_fill_draws`. Please copy the same observation
array already emitted as `ax.native_fill_draws` into
`elements.capture_evidence.native_fill_draws`; obtain it once and reuse it so
the two exports do not observe different frames. Every original field remains
intact, including `occlusion_proven:false`, native/window ancestry, opacity,
submitted draw and current coordinates. When both original arrays are present
the reader checks their equality. Missing local raw evidence remains unavailable;
external artifact links are not treated as if their bytes had been read.
The fill observation alone cannot remove a covered element: final-frame binding
and actual compositing order are still required by the existing occlusion gate.

Changes for the clients (06b914e actual CI results): smoke run 41075263281
contains 22 scene attempts and remains failed with zero accepted scenes.
Windows has six capture failures: settings hover after extraction, three
zero-height UIA text-range cases and two pane-resize state changes. The earlier
settings NativeLabel preparation failure is gone. Both full reports and raw
captures are retained under `S:\Codex\Outputs\Relic-native-visual\parity-06b914e\`.
The obsolete 54d07fc full run 41070217895 was cancelled with its partial evidence
retained to free runners for current commits; it is not a successful matrix.
The 78a9673 Windows paint trace now observes all three real README list items
after the fixture LF correction; trace loss and layer attribution still fail.

The merged macOS request adds actual TextKit-to-CGImage backing-layer receipts
and unchanged bitmap/layer assertions. These are still pending CI confirmation.
Windows core tests passed 48 cases; the capture test project exposed a missing
compile link to NativeGlyphBounds, now corrected. The thread-open action also
refreshes toolbar selection, following the same fix as file/pane navigation.

Changes for the clients (production navigation state): the actual db91b1b
file-code capture showed the Files inspector beside a stale Overview toolbar
selection. OpenFile, SetPane and panel/sidebar toggles now refresh the real
toolbar when changing their corresponding state. Settings navigation and
segmented choices now explicitly name their native SelectorBarItems: the
custom content templates had produced empty actual accessible names.
These changes await verification by the existing capture scenes in CI.

The archived SKP batch run 41074230744 decoded all 118 unique inputs with zero
decoder failures. Its 18 text-bearing inputs belong only to the Browser process;
the Renderer process's nine unique inputs contain no exported text blobs or
typefaces. The original trace loss and missing DOM/final-frame bindings remain.
This diagnostic does not resolve any reference glyph or marker measurement.

Changes for the clients (actual range and empty-outline observations): Windows
now records the successful GetText BSTR pointer/length and verifies a collapsed
prefix before interpreting a null BSTR as offset zero. The existing NativePathText
peer is measured independently through its WinRT and public COM providers;
its frame continuity remains unproved, so no external zero-height error is
suppressed. Abnormal actual glyph bounds retain their original binary32 bits
and HRESULT. Only the same callback run's successful, non-color, zero-figure,
zero-segment outline can establish empty ink; no zero rectangle is substituted.
Pure regression cases run in CI. The application headless build passes locally.
The merged macOS outline/color drawing change and opt-in surface-fill candidate
still require their actual CI bitmap results; neither grants an exception.

Changes for the clients (same real fixture bytes): the 9f11a82 paint capture
found the Windows README contained 14 CRLF pairs while macOS used LF. The file
API preserves those original bytes; the unchanged reference list parser then
created an empty UL on Windows, so there were no actual list-marker candidates.
The shared fixture now writes README.md and review.py with explicit LF on both
platforms. This corrects unequal inputs and the resulting byte-size labels;
it does not edit reference markup, parser, styles or any comparison tolerance.
The actual file bytes are asserted in the existing CI fixture test. Earlier
captures retain their original CRLF files and remain labeled by their commit.

Changes for the clients (independent observer launch): the CI UIA observer now
uses `relic_core.process.creation_flags()` for its existing Popen, with the
actual flags/arguments retained in observer-launch.json. Redirected standard
streams alone did not request CREATE_NO_WINDOW. db91b1b proves that message
hover disappeared during the independent observer interval; the change fixes
that launch omission but does not yet establish the cause of lost hover. The
original 75-second deadline, state checkpoints and failures are unchanged.
The 9f11a82 shared tests exposed three wrong recorded-fixture expectations and
one wrong low-level icon-null assertion. The tests now check the complete
recorded traversal and actual validate_capture failure paths; no acceptance
property, scene, exception or tolerance was altered to satisfy them.

Changes for the clients (actual db91b1b capture and correspondence): smoke run
41070038057 writes its comparison artifacts but fails the strict gate; accepted
scenes remain zero. Windows has seven capture failures (down from nineteen),
and the actual settings PNG now contains its navigation labels. The retained
frame journal shows those seven label Images arranging from 0x0 to their real
sizes while RequestCommitAsync yields. Their initial state is now retained as
preparation, with the immutable capture baseline established after commit/flush
and before any desktop readback. Later membership/revision/geometry comparisons
are unchanged. Actual whitespace glyph runs also returned Infinity/FLT_MAX ink
bounds; those original values remain explicit failures, not zero rectangles.

The macOS 15581b1 chart/recipient pairing request is addressed in the shared
matcher: anonymous elements with equal kind, region, established surrounding
anchors and known matched parent are paired before leftover sequence alignment.
Neither geometry nor style influences that correspondence. Unequal anonymous
groups remain ambiguous; actual late-emitted checkboxes/dividers retain their
reading-order errors and extra native wrappers remain failures. Initial tests
mistakenly assumed those late nodes were absent; the complete recorded traversal
shows them. Eight tests now check those actual identities and separately remove
nodes in explicit synthetic negative cases to verify missing failures. The fixture retains original IDs,
parents and reading order. The newly supplied macOS content_screen_frame is
consumed by the already committed list-marker reader; no origin is inferred.

Changes for the clients (bounded paint diagnostics): the existing archived
743 SKP aliases are all retained and their 118 unique byte sequences are each
decoded in CI, including empty/no-text results and failures. Original process,
thread, flow and trace-loss receipts remain attached. None is promoted to DOM
or final-frame evidence. A separate file-markdown LayerTree diagnostic records
actual drawOval candidates and the complete original transform/clip command
prefixes. Layer-to-DOM ancestry is recorded; oval-to-marker and final screenshot
ownership remain unknown. The acceptance matrix and tolerances are unchanged.

Changes for the clients (actual native list discs): Windows now paints unordered
list markers with its retained XAML Ellipse, using actual primary-face metrics
and the real RichTextBlock baseline. Its raw receipts retain owner/child/window
identities, arrangement, transforms and brush properties; a framework raster
callback and final screenshot ownership remain unproved. macOS list-disc checks
read its actual CGContext callback without deriving geometry from the AX bullet.
Both markers keep the spoken alternative `• ` separate from empty painted text.
The macOS reader needs `content_screen_frame` on the actual marker observation:
`source: actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen`,
`coordinate_space: AppKit screen coordinates (bottom-left)`, the same actual
`window_identity`, and the actual content frame in `bounds`. It does not infer
the screen origin from an AX allocation rectangle. Missing evidence still fails.
Per the macOS request, diagnostic smoke adds `file-markdown` (22 scenes); full
coverage stays 56 scenes times 12 settings, or 672 scenes per platform.

Changes for the clients (observed CI state): 54d07fc Windows build/tests and
113 Node plus 735 Python shared checks pass. macOS still fails its unchanged
glyph bitmap and extra ContentLayer tests; no scene has passed the strict gate.
Archived paint run 41070217380 decodes its first real SKP successfully, but trace
metadata places that SKP in Browser pid 948, not the document Renderer pid 1588.
Its font records cannot be assigned to document elements. The old 63a2abf full
capture run 41066463658 was explicitly canceled because it predates the known
non-finite export fix and occupied capture runners; it is not a passing run.
The replacement full 54d07fc run and db91b1b smoke retain the entire required
scope and unchanged tolerances.

Changes for the clients (decoder compilation): run 41069194779 successfully
builds the pinned Skia library, then the diagnostic translation unit fails on
the incomplete SkFontMgr type used by a null smart-pointer parameter. Including
the actual public definition fixes that compile dependency; it does not create
a fallback font manager. Runtime decoding remains pending.

Changes for the clients (native locale and public provider chain): Windows now
sets FrameworkElement.Language on the actual main root and dialog when loading
the selected `/api/i18n` language, matching the reference's document lang update.
The raw tree retains each actual inherited Language. This corrects a native
configuration omission, not an unmeasured assertion about a rendered font face.
The in-process range probe now follows the same publicly observed
peer-to-Fragment-to-Simple chain as the successful retained identity capture;
the failed direct QI and every HRESULT remain recorded. 20e17bc did not reach
the in-process SAFEARRAY, so the precision-loss layer is still unresolved.

Changes for the clients (actual decoder build): archived paint diagnostic run
41068736846 passes 14 input tests and its pinned source checks. GN generation
succeeds; Ninja finds a missing Expat dependency before compiling. The original
Skia development default enables JPEG gainmaps even with JPEG decoding disabled,
which independently enables XML. The PNG-only diagnostic now disables that
unused feature explicitly. Font/source/frame measurements remain unresolved.

Changes for the clients (latest macOS requests): the actual list-disc paint in
Chromium 156.0.8078.4 is a FillEllipse symbol, not its accessibility bullet text.
The reference extractor now retains the actual AX name and original DOM/text
boxes, identifies the verified builtin symbol branch, and reports unknown
ellipse/rectangle paint geometry separately. Seven pure recorded/synthetic
tests cover that distinction; there is still no measured shape match. The branch also
exports actual rename outline/local-owner contours. Those native contours do
not supply the still-missing reference focus contour. Opaque-dialog occlusion
remains unmeasured and its extra elements remain reported.

Changes for the clients (current failed captures and evidence preservation):
20e17bc Windows build and both test jobs pass, and shared CI passes 106 Node
checks plus 722 Python tests. Its smoke capture nevertheless fails 19 component
checks: non-finite values in the final NativeLabel observer could not serialize,
settings foreground is still missing, and pane hover continuity still changes.
Native raw export now preserves each non-finite value with its JSON pointer,
original numeric format and IEEE bits, while retaining an explicit failure;
it supplies no finite replacement coordinate. Four pure tests cover this path.
NativeLabel paint also resolves its current effective brush instead of trusting
a detached subscription cache and exports the actual foreground sources.
The six failing macOS glyph assertions in run 41064569908 are not repaired by
successful extraction; the merged branch restores its working production draw
path while keeping its stricter extra-layer and pixel checks enabled.

Changes for the clients (real controls and settling): Windows clips the existing
toolbar Image at its actual reference 5 DIP radius, without an extra painted
wrapper. Actual backing Visual/clip/geometry identities and properties are now
retained independently from UIElement.Clip; incomplete transforms and final
presentation remain unmeasured. Search retains its visible search placeholder
and matches the reference's actual labelwrapped accessible name, which comes
from the microphone when voice is enabled. Panel hover captures now explicitly
settle real post-gesture events within the existing 1000 ms budget before the
first baseline. Windows reads the real system hover delay and processes a real
dispatcher turn; the reference records fonts-ready and two real renderer frames.
All later event counts and full-state comparisons remain strict. An actual
native tooltip absent from headless Chromium is still an extra element.

Changes for the clients (isolated browser paint decoding): manual visual paint
mode accepts `paint_archive_run_id` to inspect one original SKP from the existing
Windows Chromium artifact. The independent CI-only tool validates actual browser
revision/official DEPS, builds pinned Skia with the runner's existing compiler,
and records original glyph IDs, positions, font streams and axes without drawing
a substitute screenshot. No canonical measurement, matrix, matcher or tolerance
uses these results. Original trace loss and missing DOM/frame/final-PNG identity
remain failures; actual decoder build and execution are pending CI.

Changes for the clients (button interaction and macOS diagnostics): Windows
button labels, reply summaries, secretary choices, avatar overlays and clickable
overview rows no longer intercept their parent button's pointer action as
selectable text. Ordinary conversation and episode text remains selectable;
session delivery hints retain their own tooltip hit target. Actual CI clicks
must still verify these source fixes. The macOS request in db161d1 is implemented:
failed unit tests upload `.build/draw-diagnostics/**` as
`native-macos-draw-diagnostics`, preserving actual PNGs and source without
changing the existing pixel assertions or acceptance criteria.

Changes for the clients (direct provider diagnostic): CI now independently
queries the same retained peer's public COM TextPattern provider for actual
WinRT ranges whose measured height is between 0 and 1. It records SAFEARRAY
doubles, bit patterns, full RuntimeId, endpoints and lifetime receipts alongside
the unchanged WinRT and external UIA evidence. Unavailable public interfaces
remain unavailable. This diagnostic supplies no canonical geometry, changes no
existing errors, and retains the complete selection/omission list. Seven pure
mock tests run in CI; headless WinUI build passes. Actual three-way results are
still pending, so the integer-conversion location is not claimed as known.

Read the latest macOS request: its direct CGContext glyph change produced no
ink and failed five of 212 tests at e2bc218. The later actual CTFontDrawGlyphs
correction is merged; unchanged pixel equality and no-extra-layer tests must
verify it. Older successful extraction cannot validate those missing glyphs.

Changes for the clients (current mapped text and cell-frame verification):
the shared NativePath reader now checks the actual original-to-paint UTF-16
map, independent source/paint ICU iterators, complete DWrite shaping clusters,
retained line object/parent identities and actual arranged geometry. Canonical
text stays the complete original source. The reference's DOMSnapshot layout.text
is TransformedText, not textBox-clipped visible glyph text; actual 7df43bd soft
wrapping retains a source space outside the two textBoxes. Source, shaping input,
drawn line inputs and still-unmeasured final visible text are separate evidence.
No line concatenation or reference-based normalization supplies missing text.
Thirteen pure/recorded-source tests cover the new contract in CI.

The macOS requested cell AX frame and capture content-screen frame are now
exported by its branch and independently verified in the shared reader. Actual
source strings, cell/window identities, bottom-left basis and exact cell/control
screen geometry are required; the actual topLeft conversion must agree with raw
and canonical window rectangles. Only this dedicated former missing-position
issue is resolved by complete evidence; editor paint and all other gaps remain.
Nine additional tests cover missing, conflicting and foreign frames.

Windows settings navigation retains actual same-color brushes, restores them
at real Loaded/Opened transitions and binds tab/template foreground together.
Unchanged hover notifications no longer redraw seven labels. Actual 099b036
had seven null navigation foregrounds in Appearance, and seven geometry/draw
changes during hover. These changes address observed state handling; the
internal WinUI cause of the initial null value is not asserted. Headless build
passes with zero warnings/errors; fresh capture still must verify the repair.

Changes for the clients (selectable notice text and actual recipient input):
Windows notices now reuse the native selectable text renderer with their own
UI-font 12px/19.2px centered-line policy. The existing path mode keeps its
original font, strut and emergency wrapping. Notice source is retained intact;
normal whitespace is mapped to actual painted UTF-16 intervals. Mouse/keyboard
selection and UIA ranges use real line offsets and original source positions.
Receipts add `text_style`, `source_to_paint`, paint intervals and arranged line
positions; the original `source_slice_matches` stays truthful when false.
The capture additionally binds each painted slice to the actual owner's map.
Final font, glyph visibility, layout and frame failures remain independent.
Thirteen pure policy/source-map/selection tests are added for CI. The assembled
WinUI app builds headlessly with zero warnings/errors; these are not new capture
results. Local test-project build had no restored assets and is left to CI.

Actual 099b036 capture removes the startup regression: Windows completes 15/21,
macOS completes its capture job, and shared tests pass. Windows failures are
settings foreground/draw stability, two UIA fractional text ranges, panel hover
continuity and recipient click timeout. The recipient label was selectable text
inside a Button; its decorative content now routes pointer input to that real
button. Capture retains real hit-test and handled routed-event receipts, still
requiring an actual Click and mounted menu. It never directly calls the picker.

Changes for the clients (actual cell correction supersedes v1): implemented
1097cdf/f462776's `appkit-current-field-editor-v2` shared request. Only the
actual PaddedCell / AXTextField can own the editor; both cell/control object
directions and all currentEditor/window/value/focus checks are required.
The former v1 Control-based proof is rejected. The current `owner_screen_bounds`
is a control-frame measurement; it does not independently measure the cell's
AX screen position. That missing cross-check remains an extraction failure.
Fifteen synthetic tests cover the v2 relation and rejection paths.

Request to macOS: export `native_field_editor.owner_ax_frame` with source
`actual NSTextFieldCell.accessibilityFrame()`, actual `owner_identity`,
`coordinate_space: AppKit screen coordinates (bottom-left)`, and untouched
`bounds` from cell.accessibilityFrame(). Also export `content_screen_frame`
with source `actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen`,
the actual `window_identity` and `bounds` used by the capture's contentScreen.
The shared reader can then cross-check actual cell/control screen geometry and
the raw window-space AX rectangle using an observed coordinate basis. It will
not infer missing positions from matching dimensions.

Windows voice-enabled multiline fields now retain their reference 10px right
padding. Only single-line input reserves 34px for its microphone, matching
app.css `.field input`. Actual light and dark captures show the prior editor
viewport was 430px inside a 476px field, 24px narrower than that CSS rule.
Empty-field evidence establishes this width defect; new long-text wrapping
and final width remain for CI to measure, not assumed from the change.

Changes for the clients (AppKit current field editor): implemented the c40e136 /
64ee673 shared request. The reader independently checks the exact currentEditor
owner/editor identities, actual firstResponder relation, window, raw roles,
class, identifier, value, screen bounds and UTF-16 selection. Both the system
editor and be16164's actual ObservedFieldEditor are checked against their own
recorded class. The retained editor still undergoes the full independent
measurement audit; its failures keep the original source ID under its owner.
No missing style/geometry is filled from the owner, and no extra counterpart
is added to pairing. Twelve synthetic tests cover valid and rejected aliases.

Windows SettingsInput now explicitly paints placeholders opaque #757575,
matching actual reference captures in light and dark themes, instead of the
SDK's translucent default. New-org actual 78c7f6b reference dom-499/505 and
7df43bd dark reference dom-319/325 show [117,117,117,255]; Windows template
xaml-1232/1259 had [0,0,0,158]. Text, selection and layout are unchanged.

The 099b036 shared CI checks pass 106 Node and 685 Python tests. The archived
full strict report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-ca8d997-full-recompare-ae9498c\report`:
672 scene reports / 1344 platform comparisons, zero accepted scenes, empty
exceptions. Its comparison-provenance.json records the older ca8d997 capture
and ae9498c tools separately; this is diagnostic evidence, not final delivery.

Changes for the clients (974c89b startup regression and measurement repair):
the Windows artifact's actual unhandled exception says the PersonPicture Style
cannot target the derived runtime Control (0x800F1000, then 0xC000027B).
All 21 Windows captures failed at startup. The production avatar now retains
an exact native PersonPicture inside a non-UI composition, using a weak-key
object table; it adds no visual wrapper. The v2 capture checks the actual
picture/composition references before and after, as well as all original
template/parent/RuntimeId checks. The retired subclass receives no outline
proof. Headless WinUI build passes with zero warnings/errors; real startup
must still be verified in CI. The macOS requested `Control container only`
wording is restored without weakening child-paint assertions.

Standalone untrimmed NativeLabel text now uses its already captured, complete
production DWrite font-metric advance range, with source/COM/revision/Image
and frame bindings. The former allocation box remains in the evidence.
This corrects allocation-versus-text comparisons seen at actual 78c7f6b
xaml-320/356/374; it does not establish final visible glyph pixels or erase
independent drawing failures. Trimmed/partial/composite labels retain failure.

Diagnostic composition now writes all required scenes even when a capture
fails, marking missing/invalid slots explicitly as NOT A CAPTURE. Original
valid PNG pixels are not resized. Receipt/count/matrix/image failures still
return nonzero; coverage distinguishes diagnostic images from actual captures.
Archived full capture ca8d997, compared by ae9498c in run 41055285619, now
downloads and uploads its full strict report successfully. Its parity gate
fails; the current matrix also requires states absent from that older capture.
This archived comparison is not verification of a newer native binary.

Changes for the clients (recipient activation and 21-case diagnostics): read
the macOS d0d8277 request and append `recipients` after all 20 previous smoke
cases, without changing the full 56-scene / 672-case matrix. Both reference and
Windows now activate the retained production button with actual pointer input;
the reference requires a trusted click, and Windows records its actual Click
sender, current button, flyout and mounted popup items. The macOS production
anchor correction is merged. Source state assignments and direct picker calls
are not substituted for this activation. Fresh captures must verify placement.

Windows settings navigation now draws its seven labels with the existing
NativeLabel production DWrite metrics/half-leading path. This addresses actual
14px label baselines about 4.164px below the reference while retaining 400/600
weights, 22.4px line height and the original SelectorBarItem keyboard/actions.
Hover recolors the current mounted label; actual selection changes replace it.
No exported geometry or fixed Y offset supplies the correction.

Avatar decorations now have explicit production object ownership: the subgroup
outline belongs to its real avatar, and the reply avatar's 24px outer border
belongs to the inner picture. Actual frame bounds/border fields remain raw;
the outline's original stroke and unknown offset/contour are retained. Labels,
images, state dots and cabinet rings are not swallowed by this ownership rule.
Current runtime/template/parent/full-RuntimeId proof is required. Unknown part
identity remains failure. Actual names are unchanged. The assembled WinUI code
builds with zero warnings/errors; new UI effects still require CI capture.

Actual 78c7f6b smoke: Windows 16/20 and macOS 20/20 captures completed. The
Windows settings hover receipt now has the actual target hit, unselected hover
and unchanged Appearance selection at all four checkpoints. Actual toggle
thumbs xaml-866 and xaml-949 have independently bound live originating states;
the path owner retains the actual three source-bound drawing lines. Four
Windows captures still fail: file-code/live-tool-output have original zero-height
COM text rectangles, and both panel resize scenes change state during capture.
The report is at `S:\Codex\Outputs\Relic-native-visual\parity-78c7f6b\report`.
No scene has reached acceptance. Archived full-run transport completed all ZIP
checks in run 41055285619; its one stale workflow-string test assertion is now
updated to verify all 32 actual capture-artifact routes. Full parity still fails.

Changes for the clients (archived-capture recompare): `native-recompare.yml`
can verify the bounded-storage path against all immutable artifacts from a
specified existing capture run without launching new app windows. It still
uses the full current matrix and the unchanged strict matcher. An older run
missing newly required states fails coverage. `comparison-provenance.json`
records the capture run/commits separately from the comparison tool commit;
recomparison is never reported as verification of a newer native binary.
Until the new reusable file is on the default branch, dispatch the existing
`native-visual.yml` with `capture_run_id`; it calls that reusable workflow at
the selected branch revision. The original direct dispatch returned 404 and
did not run. Normal capture dispatch/push keeps every required capture job.

Changes for the clients (full-matrix artifact storage failure): ca8d997 full
run 41038721093 exhausted the comparison runner's disk while downloading raw
capture artifacts; the matcher and final upload had not started. This is an
infrastructure failure, not a completed parity result. Comparison now downloads
one immutable ZIP at a time and reads every member to EOF, checking actual CRC,
size and SHA256. Only PNGs, canonical element JSON, completion receipts and
manifests are expanded for comparison. Complete original raw trees remain in
their original capture artifacts. Both report artifacts include raw-artifacts
JSON/HTML, exact member names and download links; each scene has its own links.
Local elements must match the verified original member bytes. Missing or failed
transport still fails. No scene, measurement failure or tolerance is removed.
Nine pure mocked transport tests and actual bounded-disk CI remain to verify.

The 78c7f6b shared checks pass 106 Node / 631 Python tests. Its native captures
are still running. The de8c4ff smoke report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-de8c4ff\report`; it still requires
all 672 cases and accepts zero. Its diagnostics contain Windows missing 762,
extra 242, text 462, geometry 2008, style 11876, state 1114, kind 8, region 15,
order 920, layout 1640, icon 0 and extraction 30259; macOS missing 76, extra 625,
text 12, geometry 1233, style 8408, state 1211, kind 0, region 2, order 645,
layout 2325, icon 0 and extraction 30574. These are a 20-case diagnostic input,
not a complete acceptance matrix.

Retained path-line failures now preserve their original id/reason/count while
the matcher independently revalidates the full owner/source/parent proof to
locate them on the real source owner. Invalid ownership remains global. Path
owner outline must be independently measured; child outline absence cannot
prove the owner's absence. The sealed Overview toggle also has an exact local
container-only outline receipt; children, focus and Composition remain separate.
No derived type automatically inherits a native primitive's absence proof.

Read the latest macOS requests: actual 5d4f8ea hover receipts, corrected date
spacing and padded segment geometry, input modifier ownership, and nonfinite
TextKit measurement serialization. Nonfinite native slots become null with
their exact paths/spellings retained as unmeasured failures, never zero. These
changes are integrated for the next shared run; actual visual/IME behavior and
remaining input-width differences still need verification.

Changes for the clients (actual de8c4ff results and retained element ownership):
the 20-case smoke captured 15 Windows cases and 20 macOS cases, but accepts
zero scenes. Windows failed settings-navigation-hover, file-code,
live-tool-output, panel-resize-hover and panel-resized. The former hit-test
was incorrectly restricted to the main Grid while the actual item belongs to
a ContentDialog popup; it now uses that retained item's subtree and records
the actual hit objects. Pointer coordinates, hover checks and tolerances are
unchanged. A new capture must verify the correction. Mac capture completion
at this head did not establish the newly added hover scene's actual content.

The actual Windows member-card path receipt has unchanged UTF-16 spans
0..25 / 25..56 / 56..64, with three independently measured NativeLabel draws.
Canonical projection now aggregates those internal drawing lines only after
validating retained object identities, parent chains, current layout revision,
ICU boundaries and complete source spans. The original raw lines, independent
geometry/font receipts and existing unmeasured/extraction errors remain. The
owner layout box never substitutes for glyph geometry. Eleven new pure tests
include a retained actual de8c4ff fixture and await CI.

The production Overview toggle now retains its actual track, shadow and thumb.
Only a noninteractive thumb with a complete current part contract, actual
parent chain and independently bound full RuntimeId may inherit its originating
toggle's four measured state fields. Raw null part states remain in evidence;
hover, other descendants, outline, paint and final-frame gaps are not filled.
Six new pure tests and their recorded/synthetic-labelled fixtures await CI.
The combined WinUI build passed with zero warnings/errors; no app or tests ran
on the person's machine. The preceding shared CI passed 106 Node and 614 Python
tests; those checks do not establish element parity.

Read and integrated the macOS requests through 996116d: the explicit required
settings navigation hover capture, corrected native icon test fixture, actual
conversation keyboard enabled/focused receipts, collapsed date spacing, padded
segment hit regions and production TextKit composer/placeholder glyph capture.
Shared matrix coverage remains 56 scenes / 672 cases per platform, with no
exceptions or tolerance change. Mac own-outline and final-PNG attribution gaps
remain failures. New native-head compilation, tests and captures are required.

Changes for the clients (production cwd text layout): Windows member-card cwd
now uses a selectable native path control. System ICU provides line/grapheme/word
boundaries; actual DWrite clusters and the available allocation select lines,
without source edits, hidden characters or fixture line breaks. Its actual
NativeLabel draws supply hit testing and selection rectangles; mouse/keyboard
selection, localized Copy/Select All and a real TextPattern retain the full source.
A measured failure falls back to the original selectable TextBlock and remains
a failed receipt. Raw `native_path_evidence` / `native_path_line_evidence` bind
actual object references, renderIds and source spans; `.path-layout.json` keeps
the separate production layout inputs. Canonical ownership is not guessed from
matching text. Seven pure policy tests await CI, as do actual line wrapping,
baseline, selection and UIA behavior. The complete WinUI project builds with
zero warnings/errors after the new raw binding and hover capture integration.

The composer now paints the reference's 0/1/2/.06 shadow through the existing
NativeShadowPanel around its real border box, keeping outer margin/MaxWidth on
the wrapper and retaining the same editor/actions. New screenshots must verify
geometry and pixels; existing compositor receipts do not assert raster equality.

Read the macOS conversation-keyboard request: its actual focusable scroll view
and key handling are integrated without projecting a fictitious focus state.
The additional actual icon-own-outline and recursive layer receipts retain
their separate unknown presentation/child drawing duties.

Changes for the clients (new required settings navigation hover scene): the
matrix now has 56 scenes / 672 cases per platform, retaining all previous 55
scenes and adding `settings-navigation-hover` in all sizes, languages and themes.
Open Settings on `appearance`, then physically hover the unselected `notify`
navigation item without clicking; keep Appearance selected and retain that
actual pointer state through PNG and extraction. Reference uses the production
`.settings nav button[data-k="notify"]`; Windows uses the actual
`settings-nav-notify` SelectorBarItem. The macOS owner must implement the same
scene and retain actual hover/selection/geometry receipts. The new row remains
required, with no exclusion while either client is incomplete. Windows now
implements the previously missing hover colors with selection taking priority.

Changes for the clients (macOS actual icon draw request): the shared validator
now binds the new live-CoreGraphics-icon-draw receipt to its actual current
view/window, source path, geometry, color and stroke inputs. Synthetic tests
cover stale and conflicting identities; they are not captured product evidence.
The false presentation-identity field and existing unknown outline/visibility
obligations are preserved. The Mac test-assumption correction and real border
padding change have been merged, with new CI verification still required.

Changes for the clients (actual e469311 Windows capture): group xaml-12 Back and
its xaml-15 arrow are now enabled, with actual foreground [90,88,83,255], matching
the reference request after the startup-history fix. The actual state-dot owner
now carries its new exact Grid/owned-layer contract. These observations do not
make the diagnostic subset pass: 15/19 captures complete; file-code and live-tool
output retain zero-area COM text-rectangle errors, and both resize scenes retain
actual state/event changes. The downloaded raw files are under
`S:\Codex\Outputs\Relic-native-visual\parity-e469311\windows`.

The UIA executable now prints a bounded summary of its actual extraction errors
to stderr while retaining every full error in its JSON and the same failing exit
code. This fixes empty CI failure messages; it does not change extraction or
acceptance. Its headless build passes with zero warnings/errors.

Changes for the clients (strict state-dot annular paint): the Windows projector
can now derive circular border/radius and zero-blur inset parameters from the
actual two owned Ellipses, only when the new exact Grid own-paint contract and
both independent primitive receipts are complete. Geometry and colors come
from those native objects. Historical null contracts still fail, eccentric or
incomplete rings remain unknown, and final PNG/AA/frame equivalence stays a
separate failure. Five pure CI tests cover recorded old inputs, an explicitly
synthetic new contract, actual-color propagation and 19 negative conditions.
Only py_compile and diff-check ran locally; actual CI verification is pending.

Read macOS REQUESTS through 86b52e7: its b63cd2f diagnostic subset retains
measured scroll/typography improvements but still fails the strict full gate.
The following native popup-title padding and member-card border-layout fixes
need their own new captures; they request no shared API or tolerance change.

Changes for the clients (actual e469311 CI feedback): Windows build and both
native test projects pass; shared element-contract tests pass. The Mac job
124030056997 in run 41045973032 executes 186 tests with two failed assertions
in OutlineDrawTests.testTextOutlineContractRequiresItsActualCurrentNativeDrawAndRejectsAdditionalPaint
(lines 27/28). Its actual NSViewBackingLayer and presentation layer each have
one sublayer, so the new text-own-outline contract correctly stays unknown;
the test expected absence. The macOS owner must determine that actual sublayer's
identity and drawing duty before changing the contract or expectation. The raw
CI log is retained at `S:\Codex\Temp\relic-native\macos-e469311.log`.

The efeaf76 actual cwd diagnostic independently measures DWrite emergency-break
mode 2 as two 32-unit lines. System ICU provides opportunities at UTF-16 offsets
0, 2, 11, 25, 56 and 64; using the actual cluster advances and 238px allocation
would choose 25/56/64, matching the reference's three captured spans. This is
a production wrapping direction, not evidence of a rendered replacement. The
original source text, selection/copy behavior and actual font/strut inputs must
survive that change. The diagnostic reports remain downloaded under
`S:\Codex\Outputs\Relic-native-visual\parity-efeaf76\windows`.

Changes for the clients (native build scheduling): read the macOS request to
preserve queued build feedback. The native-apps workflow now keeps its active
per-branch run, including a queued Mac job, while GitHub replaces the next
pending run with the newest push. Every build, test and parity requirement is
unchanged, and the final head still needs its own completed checks.

Changes for the clients (startup navigation history): ca8d997's back arrow was
actually disabled on Windows while the reference could go back; both opacity
chains were 1, and both implementations already used the same disabled color.
Windows Refresh auto-opened its initial organization without recording that
conversation in history. Startup now calls the existing PushHistory after the
first successful organization/chat load, before capture/event subscription.
This restores ordinary first-navigation Back behavior; capture history and the
toolbar template are untouched. The WinUI build passes headlessly; actual
enabled state and arrow paint still require the next capture.

Read native-macos's late-mounted-scroll request: its own production observer
now applies the existing scrollbar style when a later dialog mounts, retaining
current scroll state/instances. It requests no shared API or gate change; its
10px-gutter regression and full captures remain required after integration.

Changes for the clients (actual da6cfd7 build results): run 41044003831 passes
Windows build/package and 33 core plus 107 mock capture tests, macOS build/package
and 183 tests, and the shared 106 Node/577 Python suite. Static vocabulary still
fails its four existing Windows omissions. No visual scene is accepted.

In actual 8767825 capture 41041721349, menu xaml-28 retains the real Group peer,
name, header parent and 140/5/176/28 box; composer xaml-699 retains its real region
at 276/794/824/106. PersonPicture no longer appears in the group own-outline
gaps. Four measured Ellipse state dots retain radius5 from actual native inputs.
The report is downloaded at `S:\Codex\Outputs\Relic-native-visual\parity-8767825\report`.
It remains a failing 19-scene diagnostic subset, with three Windows capture
errors and zero accepted scenes on either platform. The resized-panel capture
happened to complete this time; its earlier observed instability is not resolved.

The next batch records configured FontWeight requests at their actual XAML text
owners and Runs, binding each getter to its raw text/style/node/span. Only this
configured quantity is filled; composite-control defaults cannot stand in for
their child text, and actual resolved faces/weights remain independent unknowns.
Ten focused CI cases cover direct text, actual single-label ownership and rejected
cross-owner/missing/changed inputs. ScrollContentPresenter separately gets an exact
sealed SDK fill/border/content own-paint contract with six focused tests. Its real
scroll clip and every child obligation remain unchanged. The combined WinUI
project builds headlessly with zero warnings/errors; new CI evidence is required.

Read macOS REQUESTS through 237e4b2: the shared menu fixture request is fixed by
000c186 and passes at da6cfd7. Its initial-layout readiness and bounded read-only
text outline receipts require no shared route or tolerance changes. These native
changes are integrated for CI; unknown child/control paint is not inferred from
an owned text span, and final PNG contribution remains a separate obligation.

Changes for the clients (bounded native chip/badge/state-dot ownership): exact
sealed OverviewChipView/OverviewBadgeView now retain their real type chain,
applied template, sole ContentPresenter and actual Content object identities.
NativeStateDotView separately retains its exact Grid type and the actual two
Ellipse layer identities. These contracts describe only parent drawing duties;
child paint, focus, Composition, Shadow and the vacancy-ring CSS equivalence
remain independent obligations. Nine focused CI tests retain historical null
contracts as failures and cover malformed/foreign children and renderer state.
The combined main WinUI project builds headlessly with zero warnings/errors.

Changes for the clients (CI regression correction): efeaf76 shared checks pass
all 106 Node tests and 567 of 568 Python tests. The menu fixture had omitted
its actual parent region, so the existing projector correctly removed the
dangling parent reference. The recorded fixture now includes the original
window/header ancestors and their UIA chain; the parent assertion remains and
additional root/header/full-runtime-ID assertions are included. Production
projection and tolerances are unchanged. CI must rerun the corrected fixture.

The Windows thread-reply summary button now exposes the visible initials of
its actual text avatars, reply count and last-reply label in reading order.
Image avatars contribute no alternate text, matching the reference's empty alt.
This corrects another measured empty UIA name without adding a visible element.

Changes for the clients (bounded cwd line-break diagnostic): ca8d997 still
renders the same member-card path in two Windows lines versus three reference
lines. A CI-only member-card-model probe now reads the actual cwd TextBlock/Run,
Grid allocation, font request and language, then records an independent unpainted
DirectWrite emergency-break layout's line, hit-test and cluster metrics. It also
records the system ICU line boundaries/version when available, using only the
OS DLLs. Raw object identities, text and before/after source state are retained
in `<case>.path-line-break-probe.json`. No fixture widths/breaks, canonical values,
production text or success conditions are supplied by the probe. The production
fix depends on these measurements; this is not a resolved wrapping difference.
The main WinUI project builds headlessly with zero warnings/errors.

Changes for the clients (CI scheduling only): Windows visual captures now run at
most four shards concurrently, complementing the existing macOS limit of two.
The twelve Windows shards, four macOS shards, every scene and every tolerance
remain unchanged. This leaves runner capacity for native builds and checker
feedback instead of queuing all checks behind an entire visual matrix.

Changes for the clients (native-macos requests read through b63cd2f): corrected
the earlier 72f5571 test diagnosis below. lastDraw was present; live CGFloat
metrics failed the projection's Double cast, then the test indexed an empty
projected array. The merged 63aecc0 reads NSNumber and preserves failing unwraps.
The newer b63cd2f production change prevents read-only NSTextView frame changes
from revealing a dormant selection and moving the right pane by 7px. It keeps
explicit scrolling outside frame assignment; its new native regression and
screenshots remain pending. Neither change requests a shared API or exception.
The latest requested complete report still depends on the running full matrix;
the older 41029422171 has no downloadable complete parity-report artifact.

Changes for the clients (real control labels and Run.Text observation): the
Windows hierarchy selectors now retain their actual adjacent label relationship;
the add-member and OverviewLink compound buttons expose their existing visible
localized labels as UIA names. ca8d997 had empty actual names for these controls.
No visual nodes, dimensions or actions were added by this correction.

The actual d7b164c binding experiment succeeded in all 19 isolated CI processes,
including a same-dispatch change and restore. The frame observer now attaches
that channel to each retained production Run through a separate unmounted target.
Every checkpoint checks real Source/DataItem/ParentBinding identities, raw UTF-16,
UI-thread access and the target's unmounted state. Initialization callbacks are
separate; every later callback advances the real source object's revision.
Cleanup unregisters and clears the actual binding with a retained receipt.
Sixteen mock-only cases run in CI. Public-DP gaps and other unobserved properties
remain recorded, and whole-frame continuity is still unproven. The main WinUI
project builds headlessly with zero warnings/errors; actual scene binding awaits CI.

ca8d997 smoke run 41038721343 now completes all 19 macOS captures; Windows still
has four capture errors. Its downloaded report is at
`S:\Codex\Outputs\Relic-native-visual\parity-ca8d997\report`. This is a diagnostic
subset evaluated against the unchanged 660-scene requirement, not full acceptance:
both platforms have zero accepted scenes. Windows counts are missing578,
extra219, text543, geometry1613, style13234, state1130, kind8, region15, order588,
layout1630, icon0, extraction34312; macOS counts are missing55, extra571, text0,
geometry3163, style8070, state1209, kind11, region2, order611, layout2226, icon0,
extraction28257. Exceptions remain empty. The complete ca8d997 matrix is still
running separately in 41038721093.

Changes for the clients (actual ca8d997 results and the next measured batch):
native run 41038729531 passes both Windows and macOS build/test jobs; macOS runs
178 tests without the former scroller recursion crash. Package validation
41038729516 also passes. The separate static vocabulary job still fails on four
macOS-only settings keys absent from the Windows client; no inert key references
or new exceptions have been added. These results do not establish element parity.

Actual ca8d997 Windows smoke captures now retain all three selected settings
segment shadows: xaml-1317/1377/1406 each has one actual DropShadow layer and the
same retained child visual after its real unload/recheck sequence. This verifies
the production reattachment fix for this captured size/language/theme only, not
CSS blur raster equivalence. Its smoke capture still fails four scenes: file-code
and live-tool-output retain unresolved UIA rectangles; panel-resize-hover and
panel-resized retain actual pointer/ToolTip changes during capture. Raw evidence
is downloaded under `S:\Codex\Outputs\Relic-native-visual\parity-ca8d997\windows`.
The reference artifact alongside it contains all 19 `.cc.json` receipts: each
has four checkpoints and zero readiness errors, with actual response ordinals
and values bound to the production closure. Copies uses response 4 after its
real reload. This verifies the requested readiness path in this diagnostic run.

Read native-macos REQUESTS through efa7553: its new typographic-extent note
documents actual showCGGlyphs ascent/descent/baselines and retained insertion
geometry; it requests no additional shared route or checker relaxation. The
different quantities remain explicit in raw evidence and require CI validation.

The next Windows batch gives the existing composer container a real Group peer
through NativeRegionGrid without an extra visual wrapper or changed layout.
Exact SDK PersonPicture containers now report their actual template/child
ownership, with independent child paint obligations preserved. Ellipse outer
radius projection requires actual same-owner circle dimensions, Stroke, Stretch,
rigid transform and unclipped bounds; the recorded 10px/2px circle yields radius
5px through the fixed SDK's centerline geometry. Missing or contradictory
measurements still fail. The main WinUI project builds headlessly with zero
warnings/errors; these new regression cases and captures remain CI work.
The menu region now survives projection only when its actual Panel has a unique,
complete runtime-ID binding to a real UIA Group. The recorded xaml-28/uia-9
fixture retains actual name, bounds and child order; missing/duplicate/foreign
identity or failed observer lifetime cannot promote a layout wrapper. This
repairs missing extraction of an existing region, without adding a visual one.

Subsequent macOS 72f5571 CI 41040938366 fails its new glyph-extent projection test,
followed by an unchecked empty-array index. The actual draw receipt was present;
the CGFloat/Double projection diagnosis and follow-up are recorded above. The
log is saved at `S:\Codex\Temp\relic-native\macos-72f5571.log`; Windows and shared
contracts pass in that run. This newer branch state remains unverified and
must be fixed by the macOS owner before acceptance.

Changes for the clients (macOS measured recursion fix): native-macos 1ecee11
uses the newly retained actual crash stack to fix accessibility registration
reentry in its scroller provider; the previous role-only hypothesis was
insufficient. The branch is merged for CI, retaining the full native thumb and
child-index tests. This is a production recursion fix, not a capture exclusion.

Changes for the clients (fulfilled reference CC-readiness request): every
reference scene awaits the real production loadCc before opening its controls.
Copies/rules await their later real reload and expand via actual summary controls.
The pre-navigation network observer retains actual GET responses and full bytes,
then binds request order/ccAsked, unread/items and loaded state to detached closure
snapshots before/after PNG and extraction. Evidence lives in each .cc.json and
capture_evidence.cc_readiness. No badge or unread value is assigned by capture;
superseded, unknown or changing state fails. Five Node async/source tests and
seven Python observer tests run in CI. The Windows reattachment-shadow fix also
builds headlessly with zero warnings/errors; its rendering is still pending.

Changes for the clients (actual 75fddb6 rendering and macOS crash evidence): the
three historical action cards now measure x342/width720 in private/live-typing/
live-tool-output, matching their reference left edge and width. Both ordinary
chart nodes retain their actual one-layer Composition shadows. Settings selected
segments still lose theirs: measured load1, render1, unload1/2, then IsLoaded=true
with no retained visual. Windows now rechecks real IsLoaded on the next production
UI turn after Unloaded and redraws only when mounted; new screenshots are required.

The requested macOS crash upload produced real evidence in smoke 41035583436:
`S:\Codex\Outputs\Relic-native-visual\parity-75fddb6\macos-crash\Relic-2026-10-30-100041.ips`.
Its faulting main-thread stack contains Attribute -> RelicAXRead ->
ReferenceScroller.accessibilityChildren -> AppKit accessibility child/index
enumeration, with EXC_BAD_ACCESS/SIGSEGV. This is the pre-e5fe085 capture, not proof
that its subsequent role-only fix succeeded. Native-apps d7b164c job124001003474
still exits with signal11 in tests; its log is saved as
`S:\Codex\Temp\relic-native\macos-d7b164c.log`, with no DiagnosticReports file.

Changes for the clients (CC totals, form bounds and measured label ownership):
Windows now uses the server's `/api/cc.unread` for toolbar/card-header counts,
including copies omitted from `items`. Like production `loadCc`, notifications
require a count increase after initial load and the first available unread item;
their shared message receives org/id/title instead of the old incorrect n field.
Five core regression cases cover omitted cards, initial load and count changes.
FormDialog constrains the outer ScrollViewer width so its real scrollbar stays
inside the declared dialog bounds, instead of adding 10px to the whole modal.

The exact sealed NativeLabel parent now reports its actual Panel/unique Image
ownership and current source/revisions. Its own-outline contract requires those
facts and all existing focus/Composition/Shadow checks; the child's independent
paint failures and old null-contract receipts still fail. Seven focused tests
cover rejection paths. A separate CI-only SDK diagnostic tests an unattached
Run.Text OneWay binding with isolated objects. It does not mutate scene Runs,
resolve COM rectangles, or mark frame continuity proven. All main WinUI changes
in this batch build headlessly with zero warnings/errors; CI tests/captures remain
required. At 75fddb6 CI passed 28 core, 91 capture, 101 Node and 540 Python tests.
macOS compiled but its tests again exited with signal 11; no crash report was
found. The latest native-macos branch includes a scroller accessibility fix, whose
actual result is still pending. No element-parity scene is accepted.

Read native-macos REQUESTS at 79b2cf1: the reference CC-load request is fulfilled
above, preserving the actual response/readiness without manufacturing its badge.

Changes for the clients (full report storage and real text ranges): immutable
captured PNG/element/raw-tree files now share storage with the report through
same-filesystem hard links; cross-device copies exclusively create new files.
Existing conflicting output fails instead of overwriting an input link. All
bytes, relative paths, generated HTML/heatmaps and all 660 scenes remain required.
Seven file-system tests plus the matrix fixture check this in CI. Disk usage is
recorded before and after comparison. The a37467a partial artifact stays partial.

The Windows in-process provider probe now independently measures Format ranges
inside each actual visible range using the same endpoint operations as COM.
Original doubles/IEEE754, text, endpoints, operation journals and frame reads are
retained, including problematic ranges and incomplete enumeration. Twelve pure
mock cases exercise the production traversal in CI. This adds missing evidence;
it does not resolve old COM zero-height errors, alter observer exit codes or turn
the unproven Run.Text/frame continuity into success.

Chart nodes now retain normal/hover/keyboard-focus shadow surfaces and the
reference's current-node ring precedence. Actual new render results are pending.

Changes for the clients (new actual failures, not acceptance): d88dda9 settings
captures retain three nonzero selected-tab surfaces but no Composition shadow
layers or hand-in visual on their real shadowHost children. The production
renderer now also draws from its real ArrangeOverride result and caches unchanged
layout/layers. Actual lifecycle counts and child-visual identity are captured;
requested layers never stand in for rendered layers. Rendering remains unverified
until the next CI screenshot. The 8801a7c macOS test still exits with signal 11;
no runner DiagnosticReports files were found by the new upload step. The macOS
follow-up 9aaf342 corrects unboxed CoreText table-tag access and awaits CI.

Full run 41022572258 (a37467a) did not finish report generation: compare job
123981691536 exhausted disk at element_parity.py:1009. Its downloaded directory
`S:\Codex\Outputs\Relic-native-visual\parity-a37467a-full\report` is a partial
failure artifact with no summary/full parity JSON, not a complete matrix report.
The shared storage fix above retains every source file while avoiding duplicate
on-disk copies through same-filesystem evidence links; no scene is exempted.

Changes for the clients (actual tool-card alignment and shape stroke evidence):
Windows historical action cards now use the existing left-aligned width limiter,
so their 720px cap does not center them inside a wider conversation column.
The recorded private/live scenes showed the old 9px/4px horizontal drift.
The Windows normalizer now projects a continuous measured Ellipse stroke into
border fields while retaining its original stroke/foreground evidence. It cannot
substitute Line/Path paint, compound layers, transforms or unknown brushes.
Actual Ellipse layout/Stretch inputs are additionally captured for subsequent
contour measurement; this does not infer a radius from the reference or declare
an unknown contour matched. The recorded-fixture regressions run only in CI.

Changes for the clients (selected tabs and actual CI crash diagnostics): Windows
Overview/Workspace/Files tabs and detail filters now retain a mounted native
surface with the reference's selected 0/1/2px shadow. Selection changes update
the actual surface, text and shadow without replacing the native selector.
Headless build passes with zero warnings/errors; rendered geometry awaits CI.
The macOS request at 9e80f9b is fulfilled: native tests and visual capture upload
existing runner DiagnosticReports .ips/.crash files on failure. No debugger or
local process is launched, and absence of a crash file is reported, not inferred.

Actual 0545cf0 capture verifies both header state dots, leader tags and the real
settings smoke brush. The modal canonical surface retains its independently
verified UIA identity and original host rectangle. Capture is still 15/19 and
the strict element gate remains failed; these measurements do not accept scenes.
At fd4e1fe Windows build/tests/package and shared extractor contracts pass;
macOS release compilation passes but its tests fail. The native-macos follow-up
removes line-layout callback reentry; its runtime result still requires CI.

Changes for the clients (fulfilled a73b570 static-font request): the shared weight
projector now validates the already-bound actual macOS glyph callback's static
OS/2 table receipt, preserving its complete bytes, PostScript identity and parsed
big-endian usWeightClass. Missing/corrupt/conflicting receipts, fvar or nonempty
variation data remain failures. Variable instances still require their actual
wght coordinate. Six regression methods cover 28 malformed static receipts,
actual-draw binding, version/range boundaries and variable/static conflicts;
their parser fixtures are explicitly synthetic. No reference weight is inferred
from native data. The NativeFontWeight table-tag and NativeLineMetrics argument
compile fixes from native-macos 1d6402b are merged after their d88dda9 CI failures.

At d88dda9 the Windows build/package and 28 core plus 79 capture-contract tests
pass in job 123982903720. Shared checks at c099641 pass 101 Node/522 Python tests.
These are implementation checks; the full element-parity gate remains failed.

Changes for the clients (actual chart and resize capture contract): the chart
already owns its full content padding. It now opts out of the second 22px modal
template inset that clipped its close button and shifted all graph coordinates.
Nodes and legend borders use the actual 1px computed border in the 1x reference;
node chips retain their actual 20px line-height. Existing SVG edge widths and
physical dash lengths stay separate; dash/phase equivalence is still unmeasured.

Resize readiness now follows the shared reference's idle-hover/finished-drag
contract. Commit 5e9edf6 had added a Windows-only requirement that the tooltip
must open; actual 7bf2bab normal CaptureLost leaves it closed after the drag.
The collector now accepts independently observed open OR closed identity-bound
tooltip state. Open popups remain visible elements in the full extraction; an
unmeasured state fails. No tooltip is forced open/closed, no new pointer movement
is added, no timeout changes, and later full-state plus all event-count checks
are unchanged. Fifteen no-UI contract test cases cover state/identity conflicts.
Main WinUI headless build passes; this test project's local no-restore build
lacks project.assets.json, so its compilation/tests remain delegated to CI.

Read native-macos REQUESTS at a73b570: an actual static-face OS/2 weight-table
receipt is requested in the shared matcher. It must retain actual-draw/source-span
identity and cannot substitute a requested weight or an unknown variable instance.
That shared implementation is in progress; existing unknowns still fail.

Changes for the clients (prompt CI feedback): the unchanged reference-extractor
and matcher unit commands now live in a reusable workflow, called by both Native
apps and Native visual review. New extractor changes can be checked on the latest
commit without waiting for the preceding screenshot matrix to finish. The visual
comparison still requires this check and every captured scene; this does not turn
unit-test success into element-parity acceptance or remove any capture job.

Changes for the clients (actual settings/forms/member-card controls): Windows
selected settings segments now draw the reference's small production shadow;
form ComboBoxes use the measured 15px selected-text inset while keeping their
native popup and keyboard behavior. Check-rule disclosures limit the real header
hit target to its content width; expanded content still fills the card. The
parent inline line-box difference remains unresolved. Reference form fields have
no clear-text button: the stock TextBox's extra DeleteButton is now a zero-size,
empty, noninteractive template so it cannot overlap the microphone. Member-card
primary actions center their labels. Session/directory fields retain a 12.5px/20px
parent line box around the 11.5px monospace Run; the recorded cwd still needs the
reference's normal/emergency wrapping behavior, not fixture-specific newlines.
Headless build passes. New control rendering awaits CI, with no gate exclusions.

Actual 7bf2bab capture confirms the previous day/message margin fix: private
first message y222.3999939 versus reference y222.390625, both with a 14px gap;
live-typing likewise has a 14px gap. Compact density was not sampled by that
smoke fixture and is not declared validated. Its panel hover still gets an
additional same-coordinate PointerMoved with IsGenerated=false; resized captures
observe CaptureLost before normal DragCompleted and no opened tooltip. Those
capture failures remain recorded, with no event filtering or deadline change.

Changes for the clients (measured modal-surface projection): e5f092b now provides
the real applied-template proof. The Windows extractor validates the current
GetTemplateChild objects, unchanged template revision, UI-thread observation,
complete actual parent paths and authored-content identity before projecting
the modal region from BackgroundElement. Its host/UIA identity and original
full-window host rectangle remain in evidence. The authored content, additional
template backgrounds and detached smoke layer remain separate. A recorded fixture
and 19 corrupted-receipt subcases reject geometry/name-only substitutes. Unknown
ThemeShadow/focus measurements and original extraction errors still fail. This
changes measurement ownership, not any tolerance or approved exception.

Changes for the clients (actual modal backdrop and chat-header elements): the
e5f092b settings capture measures the detached SmokeLayerBackground as black
RGBA (0,0,0,77), despite the dialog-local reference brush. NativeContentDialog
now applies that real brush to its retained template rectangle after opening:
rgba(15,14,12,.32). All Windows ContentDialogs use the same native subclass;
modal focus, commands and dismissal remain the SDK implementation. The actual
live private headers also lacked the reference's 10px state dot and used a
20px/11pt leader badge instead of the 18px/10.5pt tag. Those production controls
now use the same state/colour mapping and tag style as their reference counterparts.
Headless Windows build passes; rendering and element parity still require CI.

Both native builds and native tests at 7bf2bab passed in run 41026270452. Its
static vocabulary gate still fails on the four previously documented macOS-only
harness keys, and the visual matrix remains failing. Merging native-macos through
72cf551 adds its actual font-cascade and native-control accessibility corrections;
REQUESTS.md has no new shared request. No acceptance exception was added.

Changes for the clients (actual private-chat spacing): a37467a keeps the date
line at y190 with 18.4px height, but starts its first message at y230.4 instead
of reference y222.390625. The adjacent day bottom (8px) and message top (14px)
margins collapse in the reference's block flow; StackPanel added them. Windows
now retains only the date margin remainder based on the next real element's
top margin, including compact/continuous-action variants. No fixed position
offset or reference-coordinate adjustment is used.

The a37467a panel hover fails with one extra same-position PointerMoved while
its entire checkpoint state stays equal; the resized case never observes an
open tooltip within the existing deadline. New raw pointer records include
actual IsGenerated, handler QPC and PointerCaptureLost, with NativeLabel phase
boundaries. No event is ignored and neither failure threshold is relaxed.
e5f092b CI passes 101 Node/519 Python checks and the Windows native build;
macOS remains queued at this observation. The whole parity gate remains failed.

Changes for the clients (actual UIA identity conflicts): the Windows projection
now rejects heuristic candidates when a captured owner explicitly has no peer,
or a complete RuntimeId belongs to a different owner/provider. Rejections are
auditable receipts; original provider errors, missing required providers and
unclaimed UIA nodes remain. The real 2e42376 modal fixture proves xaml-1197 owns
uia-7; authored Grid xaml-1205 cannot borrow it because their bounds coincide.
Four CI regressions preserve every original paint and host rectangle.

Settings, Details and Copies now use a native ContentDialog subclass retaining
its protected GetTemplateChild objects, current template revision and actual
parent paths. This is new raw ownership evidence for separating the full-window
host from the actual modal surface. Canonical dialog bounds and unknown shadow
paint have not yet been changed; CI must confirm the real template identities.

The independent paint entry initially returned GitHub HTTP 404 because the new
workflow was not registered on main. The existing manual visual workflow now
supports a separately named paint-only diagnostic call; full/smoke processing
and the full acceptance gate are unchanged. Dispatch 41024085363 succeeded.
Its new Windows LayerTree records exist, but later snapshot commands are not
yet attributed to the original PNG and trace loss remains a failed diagnostic.

Changes for the clients (capture scheduling request, 2475328): macOS full
capture uses max-parallel 2. All four language/theme shards, three viewports,
55 scenes and the 660-case gate are unchanged. A separate manual-only browser
paint workflow reuses the existing real fixture and diagnostic collector for
group/file-code without requiring a native build; it is not an acceptance run.

Changes for the clients (actual narrow details window): the 7df43bd English
dark 1024x700 capture shows native Details content clipped inside a second
22px template inset, with the close control cut off. The existing content-owned
padding option now applies to Details (tasks/protocols/trace/docs), as it already
does to settings and copies. The copies acknowledgement button also supplies
its localized accessible name after composing its actual icon/text children.

Latest integrated macOS REQUESTS also documents real hosted-checkbox and card
surface follow-ups, scroll-position preservation and compound-control naming.
These owner-side changes are merged; no additional shared route was requested.
The full 2cb073c failed report is available locally as documented by that client;
its 660 successful macOS captures still do not constitute a parity pass.

Changes for the clients (actual pseudo quantities): the file-code reading-order
request was already fixed by the source-tree traversal. New 2cb073c evidence
instead showed two different quantities sharing one pseudo node: a CSS inline
box and anonymous LayoutText. The reference extractor now distinguishes them
using actual transformed-text indexes and owned DOMSnapshot textBoxes. Text
fragments must cover each actual UTF-16 source completely, without gaps,
overlaps or cross-row borrowing. CSS boxes never supply text geometry. Twelve
new Node regressions retain the old actual elements and both quantities; missing
or ambiguous evidence still fails. This addresses the macOS REQUESTS finding
without removing line numbers, inventing glyph ink or changing tolerances.

Changes for the clients (measured Windows content fixes): a transcript without
an actual read_by array no longer invents an unread receipt. The copies window
uses its existing content-owned padding, removing the extra 22px per side, and
its summary uses the existing document Markdown typography (13.5px instead of
chat 14px). All underlying messages and action payloads are unchanged.

The resize capture now waits for the retained production tooltip to actually
open before its single baseline, within the existing 1000ms final-hover wait.
Initial hover/drag and all later strict continuity checks remain. Actual
ToolTip/Thumb/Popup identities and Opened/Closed events are retained. The capture
explicitly states tooltip-open readiness, not equivalence to the tooltip-free
headless reference; those visible extras are not waived. No delay, duration,
IsOpen, pointer action, scene count or matching threshold was changed.

Verified e784186 CI: 89 Node/515 Python checks pass. Its Windows capture retains
15/19 completed scenes and all four original failures. For file-code and live
tool output the new frame observer retains 74/159 actual TextBlock owners,
respectively, with zero recorded changes/errors and matching object references
at all four checkpoints. Run.Text has no public dependency-property callback;
this missing notification is retained and its actual getter values are now
recorded as well. No receipt claims full frame or paint continuity.

Changes for the clients (measured 2e42376 product gaps): Windows private/live
session banners now have the reference's native card, information icon, 12.5px
wrapping text and 20px line height instead of a single 11px muted caption.
Settings close is now before pane content in the actual child/keyboard order,
with its overlay z-order retained. The headless build passes; runtime geometry
must be measured by CI. No mismatch is waived by either product change.

The 2e42376 panel hover/resized capture failures have a specific retained cause:
the production WinUI ToolTip opens between checkpoints. Pane/Thumb/pointer
geometry did not change in those receipts. The reference also has a title on
the resize handle; browser-native tooltip evidence is unresolved. The failed
continuity checks are retained, not suppressed or reclassified as passing.

Changes for the clients (TextBlock frame diagnostics): the Windows capture now
retains the actual TextBlock owners before PNG readback, their observable source,
layout, ancestor clip/scroll/transform inputs and dependency-property revisions,
and the same actual owner/peer at each WinRT rectangle read. Both desktop
readback boundaries have checkpoints. Missing property observers, unsupported
values, changed objects, errors and journal overflow are retained. This is a
diagnostic input-state receipt, not a compositor-frame or visibility proof;
no canonical rectangles or previous provider errors are replaced. The headless
build passes; actual timing and retained-object evidence await CI.

Changes for the clients (browser paint diagnostic): actual post-navigation
`DOM.getDocument` and `LayerTree.enable` now precede the existing settling wait.
Layer snapshot requests use only actual returned layer IDs and run after the
original PNG. Raw request/response journals retain missing/zero paint counts,
empty logs and failures. Lifecycle flushing by makeSnapshot means these later
records do not prove that PNG's glyph or scrollbar contribution. Nine new pure
mock tests are scheduled in CI; no canonical measurement or gate is relaxed.

Verified 2e42376 CI: 89 Node and 506 Python element-checker tests pass; Windows
and macOS release builds pass, including 152 macOS tests. Capture/element parity
still fails. The four platform-guarded vocabulary keys remain unresolved.

Changes for the clients (measured text-range precision audit): the Windows
projection retains a supplementary `text_range_precision` receipt from the
actual WinRT and COM journals, revalidating complete RuntimeIds and UTF-16
document-prefix spans. It distinguishes positive subpixel heights transported
as zero from native ranges that already have zero area. Original errors and
all canonical geometry are unchanged; format spans are only source links,
not separately measured WinRT format rectangles. Twelve pure helper and two
projection-preservation tests run in CI. PNG/ancestor-state continuity remains
unproven for 778c96b and is not filled by identity equality.

731f1ef CI passes 89 Node/492 Python checks and Windows 28 core/64 capture
tests. Its macOS build fails at NativeSurfaceGeometry's main-actor call;
native-macos 666b2bf supplies the owner-side correction for the next merge.

Changes for the clients (778c96b actual complete identities): group now has
303 exact XAML-owner/independent-UIA full RuntimeId pairs, file-code 186 and
live-tool-output 306. The target text owners xaml-517/uia-117 and
xaml-970/uia-233 are included. Original provider errors are retained; identity
alone does not prove range visibility or continuity with the final PNG.

The 7df43bd English dark 1024x700 full shard exposed a different zero-range
case: the trimmed sidebar title's WinRT provider itself returns an all-zero
tail range. It is not a wrapped second line or subpixel integerization. Chat
titles now use the same production NativeLabel as row previews, retaining
13.3/550/17.955, single-line ellipsis, complete accessible name and unchanged
row interactions. The headless build passes; actual title geometry and all
unresolved trim/paint measurements still require the next capture.

Changes for the clients (font-weight quantity contract): the shared schema now
keeps actual configured requests separate from actual rendered-face weights.
The original `style.font_weight` is retained with its provider meaning; both
new quantities compare exactly and missing quantities remain failures. The
recorded a3ca2a3 badge proves CSS requested 700 and the native drawn face's
axis was 600, but CDP does not report the reference axis. It is still unknown,
not filled from the Semibold name. Real owned-label evidence requires a unique
matching ID/production-owner/text path; parent and child values cannot be mixed.
Seventeen helper, two matcher and two Node regressions await CI. The full
matrix stays at 660 states per platform.

The latest macOS REQUESTS correction confirms the four vocabulary keys are
macOS-only controls. Its fixed-size checkbox follow-up implements the actual
NSButton accessibility role/state/hit frame after four assertions failed in
run 41014596650; the original assertions stay unchanged in the merged revision.

Changes for the clients (current Mac integration): merged the production
rich-text accessibility range reads, composite ownership and fixed-size switch
binding through native-macos. REQUESTS.md adds no further shared request in
this merge. Those actual native element changes are included in subsequent
shared builds/captures, not counted as a passing parity result.

Changes for the clients (shared icon-button product fix): actual 7df43bd
private-header icons were 16px/left-aligned instead of 18px/centered, and the
settings close icon was 6px left of its reference position. The production
IconButton helper now centers content, uses the reference's ink-2/radius8,
and defaults ordinary icons to 18px. Explicit 16px panel/chart controls and
17px microphone/send icons remain so. The quote cancel uses its actual
reference 14px icon/22px button. Settings theme refresh now retains ink-2
instead of overriding the close icon with Muted. Fresh captures must verify
all affected calls; no extractor or tolerance substitutes for these fixes.

Changes for the clients (exact SDK control paint): Windows outline extraction
now recognizes ten exact core controls whose fixed 1.6.9 renderer paints their
content through separately captured template children. Existing actual focus,
Composition, Shadow and child-completeness checks remain mandatory. This does
not cover TextBoxView, ContentControl, item presenters or arbitrary subclasses,
and never fills a child's unknown outline from its parent. Source evidence and
new negative fixtures are recorded in `docs/native-outline-evidence.md`.

Changes for the clients (measured Windows group controls): the recipient chip
now updates its actual Button automation name with its current localized label.
In a3ca2a3 the visible text matched but the independent UIA name was null. The
group-header task button now uses the reference's 18px centered check icon,
ink-2 foreground and 8px corner radius, preserving its 30px size and action.
The production headless build passes; new runtime evidence remains pending.

The four Windows vocabulary failures are still unresolved: the fixed reference
uses `settings.desktop_connections`, `settings.desktop_probe_hint`,
`settings.claude_desktop_hint` and `settings.desktop_probe` only inside
`if (isMac())` (2007a83 app.js:2555-2572). Its Windows UI has no counterpart;
the Windows server does not execute the macOS desktop probe. Adding those
controls or unused translation references would not establish parity. No
allowlist entry or platform exemption has been added to pass this gate.

Changes for the clients (macOS configured font-weight evidence): merged
5bf9303, retaining the actual attributed input weight separately from the
actual drawn font face/variation. A requested CSS weight and a resolved font
axis are different quantities; the shared reference measurement must retain
both without filling an unmeasured axis from CSS. Existing mismatch checks
remain in force while that shared follow-up is implemented. The preceding
7df43bd macOS release build and 148 tests passed in run 41013183162; the
overall native workflow still fails its Windows vocabulary gate. New fixed-size
checkboxes and separate avatar/badge names also require the next capture.

Changes for the clients (observed provider-lifetime result): a3ca2a3 group held
648 actual observer references. All 391 peer QIs failed before the independent
walk; while the same observer remained alive, 303 succeeded and 88 remained
E_NOINTERFACE, identically for both public outlets. Complete UIA-core RuntimeId
reads now occur in that measured lifetime interval. The before/after diagnostic
is retained. Identity pairing requires the same case/app/observer IDs, actual
retained owners, successful observed release and no hold error, in addition to
the existing exact full-ID, COM, EventsSource and uniqueness requirements.
Unrelated provider errors still fail their own checks even if an ID is measured.

The final XAML snapshot is atomically replaced before the native completion ack.
If observer coordination fails, its exact owned native client is stopped/reaped
before projection, preserving a fixed failed snapshot and the actual cleanup
receipt. New mocked regressions exercise this failure path. The headless build
passes; full core-ID evidence and these new tests await fresh CI.

Changes for the clients (macOS production glyph-range merge): actual TextKit
draw invocations now retain their original attributed ranges without splitting
overlapping shaped clusters. Font projection requires complete callback coverage;
arbitrary substrings and final PNG attribution remain unknown. The owner's
143-test release validation in run 41011131346 predates this new change; its
new comparison against the unsplit production bitmap must pass fresh CI.

Changes for the clients (complete Windows matrix job partition): the cd16413
full Windows jobs reached the existing 45-minute limit; zh-CN/light was cancelled
45m01s after job start while still capturing 1024x700 reference scenes. Windows
full capture is now 12 jobs (four language/theme combinations, three existing
viewports), each containing the same 55 cases. Native/reference metadata and
artifact names include the viewport so merging cannot overwrite another shard.
The full gate still requires all original 660 case IDs. No scene or timeout was
changed; eight new mocked checks verify the exact complete union and paths.
macOS capture partitioning is unchanged.

`a3ca2a3` CI passes 87 Node, 453 Python, 28 Windows core and 64 Windows
capture/layout tests. Its actual Windows capture still fails, while macOS
completed its 19 diagnostic scenes. The WinRT-versus-COM fractional text-range
findings and unresolved cross-layer identity are recorded without waiving any
error in `docs/native-windows-text-range-evidence.md`.

Changes for the clients (macOS mounted-ancestry merge): actual sidebar,
organization and profile child records now retain their native parent
environment and mounted NSView ancestry, restoring order only for a unique
measured parent. Ambiguous ownership remains unknown; reference text/geometry
does not determine native order. The owner's bbe04a3 diagnostic captures 19/19
but still accepts zero full-matrix scenes; its actual composer viewport is
758x26. Their stale font-test API call was corrected without changing its
assertions. These merged changes remain subject to the next complete gate.

Changes for the clients (live observer ownership): the UIA observer now keeps
its actual AutomationElement/root/NativeTextEvidence references alive through
a PID/case-bound ready/release handshake. The native provider probes run before
release. The same 75-second total process deadline includes startup, capture,
handshake and exit; timeout or bad identities fail and preserve original errors.
Mock lifecycle tests cover both processes and the original deadline. Both native
projects pass headless builds. This addresses a gap in the 53aa451 diagnostic:
all 1,564 QIs failed, but the "after" phase ran after observer exit, when the
SDK's weak provider wrapper could already have been released. Nine ListViewItem
EventsSource references also changed and cannot count as unchanged aliases.

The Windows style reader now reads actual Grid and StackPanel border brushes,
edge thicknesses and corner radii before its generic Panel background branch.
Those real properties were previously lost, including the conversation header's
bottom divider. This is an extraction correction; no reference values or
matching thresholds are used to fill paint data.

`27e39b3` CI passes 87 Node and 448 Python tests, Windows build plus 28 core
and 47 capture/layout tests. Its macOS 19-scene capture completed; the Windows
capture and final parity still fail. New observer-lifetime changes require their
own fresh CI, and no diagnostic result is a full 660-state acceptance result.

Changes for the clients (actual WinRT text-range diagnostic): Windows now emits
`*.text-range-provider-probe.json` after the unchanged UIA hand-off and peer
probe. It reads DocumentRange and every GetVisibleRanges result from each real
TextBlock's existing peer, preserving raw double values, UTF-16 source, endpoint
comparisons, actual failures and query times. It supplies no canonical rectangle
or identity and never infers that zero-area text is hidden. Fixed SDK source
shows GetVisibleRanges is computed before ancestor clipping, and this provider's
IsHidden attribute is always false; those two values therefore cannot establish
pixel visibility. The probe distinguishes provider geometry from later COM
transport. Headless build passes; actual diagnostic results remain pending.

Changes for the clients (macOS silent-startup request consumed): `native_process`
now writes the host startup progress marker for macOS as well as Windows,
before Popen. A process that never enters the native lifecycle therefore hits
the existing 90-second progress failure and actual owned-PID stack sampling.
The marker cannot count as an attempted scene. The 1200-second macOS process
deadline, 45-minute job deadline, all three viewport shards and failure
aggregation are unchanged. A wholly mocked lifecycle/clock/process regression
checks sampling before cleanup at the existing deadline; it runs only in CI.
The latest macOS lifecycle startup, shadow padding and split switch/label/knob
changes were merged; their actual full capture validation remains pending.

Changes for the clients (74b14eb actual Windows follow-up): group now has 23
complete-source production label font receipts; trimmed previews still retain
unknown font coverage. The header renderer had retained a single-line mode;
it now uses DirectWrite WHOLE_WORD and the height of its actual measured lines,
matching the reference's ordinary word breaks without emergency splitting.
The extractor reads the actual layout mode, not the requested option. Current
headless build passes. New runtime geometry still needs CI verification.

Six exact sealed local layout/region classes now retain their actual base type,
sealed flag and audited source contract for own-outline evidence. Their focus,
Composition, Shadow and complete direct-child checks remain mandatory, and
children keep independent paint obligations. This adds no generic derived-type
allowance or parity exception. New focused regression cases run in CI.

The 74b14eb Windows diagnostic still captures 15/19 cases. In hover, the actual
tooltip now appears during PNG readback; resized still changes during element
extraction. Both failures remain. Its Windows and reference artifacts were
downloaded before cancelling that superseded workflow's still-queued macOS job
so the current provider diagnostic can run. No full-matrix result is inferred.

Changes for the clients (macOS evidence-shape request consumed): the latest
native-macos merge includes `raw`/`applicable` line-break evidence and explicit
non-text values required by the shared schema. Unknown text modes remain
unknown. The owner's new rename capture waits for the fetched member's actual
AX card before the single real action, fixing an observed pre-load click.
Their 597e113 diagnostic captured 18/19 scenes and still failed parity;
these newly merged fixes require a fresh capture. The reported paragraph ink
measurement is a local paragraph result, not whole-matrix font equivalence.

Changes for the clients (Windows provider timing diagnostic): the Windows
capture now retains its actual owner/peer/EventsSource objects across the
normal independent UIA traversal. `*.provider-probe.json` and its auto-flushed
progress file record both public COM pointer outlets, exact QI HRESULTs and
release outcomes before and after that traversal. This sidecar supplies no
canonical identities and does not change metadata or any failing checks.
The headless build passes. In `74b14eb`, the shared CI checker passes 87 Node
and 443 Python tests; this is checker validation, not element parity.

Changes for the clients (macOS integration follow-up): the new native TextKit
strategy fields, real popup-cell/card/status-dot ownership and composer viewport
fix are merged. The shared checker requires a small evidence-shape follow-up:
`evidence.line_break_configuration` must contain `source`, `owner`, `raw` and
`applicable`. Current macOS `NativeLineBreaks.inspect` emits its API properties
at the top level; please retain those original properties inside `raw` and set
`applicable: true` for the unchanged predicate `bool(text) || kind == "text"`.
For other elements, emit version 1, both strategies null, `applicable: false`
and an explicit `reason`; `raw` may then be empty. Missing actual text modes
still fail. See `docs/native-elements.md` and `line_breaks.py` for the exact
shared contract. The owner's reported 138-test macOS success in 41004901785
predates these newest changes and is not their runtime validation.

Changes for the clients (line-break contract implemented): reference and
Windows now emit the versioned normal/emergency quantities documented in
`docs/native-elements.md`; the matcher requires both and their real owner/raw
configuration. Legacy `wrap` stays diagnostic. macOS must emit the same new
fields from its actual paragraph/container evidence; absent fields keep failing.
All existing text geometry, line-count and truncation requirements remain.

Windows complete-span font projection now accepts only current production
fontFace callbacks with exact source UTF-16/cluster coverage, bound Image/SIS,
readback and frame continuity. In the recorded fcdc0b6 group, four menus and
four untrimmed previews qualify; two genuinely trimmed previews stay unknown.
This measures submitted font identity only. Final PNG contribution, visible
glyph ownership and geometry still retain their independent failures.

The actual 1a016ac Windows diagnostic still completes 15/19 scenes. Its four
message headers report valid TextBlock baselines but remain 16.25px high, so
the prior alignment change alone did not remove the measured offset. Header
labels now use the existing production DirectWrite renderer and its same-layout
first baseline, retaining text, colors, sizes, weights and full Text peers.
The headless build passes; actual screen validation is pending. UIA identity
also remains unproved: 376 existing peers returned E_NOINTERFACE before the
independent UIA walk (795 objects had no peer). A same-peer before/after probe
is being added to distinguish the documented native/inner COM outlet from
provider initialization timing, without guessing IDs or changing metadata.

Changes for the clients (merged macOS actual-font receipt): production
showCGGlyphs callbacks are now bound to their same complete TextKit span,
source/view/container/window and layout. Partial rich spans without callback
source indices stay unknown; independently reshaped fonts remain diagnostic
and do not satisfy the actual-font gate. The owner's reported full 56253c7
artifacts also have zero accepted scenes; no exception was added.

Changes for the clients (separate line-break quantities, implementation in progress):
the shared layout contract will retain legacy `wrap` and separately require
`normal_break_strategy` (`none`, `word`, `break-all`, `character`, `keep-all`) and
`emergency_break_strategy` (`none`, `break-unbreakable`), with
`break_strategy_version: 1`. `evidence.line_break_configuration` must retain the
actual API/CSS source, owner and raw configuration. macOS should project its
actual paragraph/container modes into these independent quantities; unknowns
stay null. Normal word wrapping with emergency long-word breaks is not
character-first wrapping. Existing line count, actual text bounds, truncation
and missing-measurement checks remain; matching strategy names never proves
matching actual line fragments. The implementation is being reviewed and new
captures will be required; older artifacts are not retroactively certified.

The `1a016ac` shared checker now passes 81 Node and 416 Python tests in CI;
the Windows native job passes 28 core and 47 capture/layout/ABI tests. Actual
capture remains pending. Exact Viewbox and ReferenceVectorIcon own-paint
contracts now retain their real child identities; all existing focus, shadow,
Composition and child completeness requirements remain in force. Other runtime
types and active outline paint remain unknown until independently measured.

Changes for the clients (merged macOS wrap-strategy request): native-macos now
retains paragraph and text-container line-break modes separately. Its request
to separate normal wrapping, emergency word breaks and observed line fragments
in the shared schema is under source review; current mismatches stay failed.
The newly merged macOS card/tab owner bindings and shadow test color-space
correction need CI validation. Windows's message-baseline/COM-transfer change
passes a headless build with zero warnings/errors; all new tests run in CI.

Changes for the clients (Windows message baselines and real provider identity):
message headers now align each actual TextBlock.BaselineOffset and preserve both
ascents and descents. Original widths, 6px gaps and wrapping order remain; an
unmeasured baseline stays explicitly unmeasured. The capture records current
metrics and their agreement with the last actual layout. Separately, XAML peers
are marshaled through COM to an MTA worker while the UI dispatcher yields;
complete opaque UIA core RuntimeIds are read twice and compared with the
independent observer. Owner, EventsSource, apartment and release failures remain
unknown. The resulting exact-identity audit does not clear existing UIA errors,
infer hidden text, or replace any canonical field before real CI validation.

Changes for the clients (actual fcdc0b6 diagnostic artifacts): the report and
HTML files are downloaded to `S:\Codex\Outputs\Relic-native-visual\parity-fcdc0b6`.
This is 19 diagnostic inputs evaluated against the unchanged 660-state gate,
not a complete matrix. Both platforms have zero accepted scenes. Windows has
162 missing/202 extra elements, 630 text, 2550 geometry, 13730 style and 1248
state mismatches; macOS has 557/1091, 441, 2483, 8219 and 1230 respectively.
All other mismatch and extraction counts remain in summary.json. No exception
or icon mapping is approved. Windows captures 15/19 scenes: the file-code
document now actually measures 443px wide and its CR/path UIA failures are gone;
one partly clipped conversation event still fails. The registered Markdown
fence now has a complete actual Border/ScrollViewer/TextBlock identity receipt.
Live-tool text and both panel tooltip continuity failures remain unresolved.

Changes for the clients (fcdc0b6 CI and precise remaining failures): Windows
build/tests pass in run 41004469470. macOS completes the 19 diagnostic captures
in 41004462072, while its native test job 123896185086 fails nine assertions
in SurfaceRasterTests.testBoxShadowDoesNotCastASecondShadowFromInteriorContent
(lines 68-71: measured alpha 0.8288107514/0 rather than 1, and final alpha 1
rather than below 0.01). The macOS owner must resolve these actual raster
failures; no tolerances were changed. The shared checker passes 81 Node tests;
one of 408 Python tests exposed its unmocked monotonic clock inside mocked
process cleanup. That test now uses explicit times and checks the exact 89.75s
remaining wait, preserving the real 90s deadline. CI verification is pending.
Windows still lacks four Mac-conditional vocabulary keys; no dead references or
new exceptions were added. The unresolved actual WinUI tooltip continuity issue
is documented in `docs/native-panel-tooltip-capture.md` with fixed-version
source and measured timestamps, not replaced with a longer wait.

Changes for the clients (Windows actual file document layout): the file path
now uses the production DirectWrite label with character ellipsis, unchanged
11px Cascadia Code and full accessible text/tooltip. The code document takes
the actual viewport's remaining width while preserving long-line horizontal
scrolling. The recorded 6183507 document was only 323px inside its 519px parent;
no text ranges, CRs, errors or padding are removed. The headless build passes;
provider behavior still needs CI. The latest macOS REQUESTS checker fixture
failure was corrected in 4f67f67: the malformed-pattern test now retains its
independent absent-outline evidence and still rejects every malformed pattern.

Changes for the clients (macOS viewport sharding implemented): shared capture
now runs multi-size macOS manifests as independent per-viewport processes with
the same fixture/server, output root, case IDs and original order. Each retains
its own manifest, progress, raw completion and owned-process cleanup. Failed
shards do not suppress later sizes. Success counts require an actual unique
captured receipt and both files; partial PNGs never replace missing receipts.
Single-size diagnostic behavior is unchanged. The existing 1200-second process,
90-second progress and workflow deadlines are unchanged. Thirteen mocked
regressions run in CI; local checks are syntax compilation and diff checking.

Changes for the clients (Windows own-outline and actual text quantities):
ordinary exact WinUI primitives now record their own paint contract, actual
focus relationship and app hand-in Composition attachment. Known absence is
scoped to that primitive; derived/compound renderers and related/unknown focus
or attachment paint still fail. NativeLabel now retains six separate measured
geometry quantities, using actual per-callback D2D transform/DPI/unit mode and
the bound Image transform. These go into audit evidence without replacing
unknown canonical text/ellipsis measurements. The headless Windows build passes.

The `6183507` Windows diagnostic completes 15/19 capture cases. Actual sidebar
previews now submit real ellipsis glyphs and have no prior zero-area UIA error.
Code view/partially clipped text ranges and both panel tooltip continuity checks
remain failed. Its artifacts are in `smoke-6183507-windows-zh-light`; the earlier
`d8f74ff` full-gate report (19 diagnostic inputs only) is in `parity-d8f74ff`,
with zero accepted scenes on both systems. Current Mac outline draw receipts
and 133-test build evidence from its REQUESTS are merged; common contour and
dash equivalence still require actual reference measurements.

Changes for the clients (macOS full-run timeout request): the owner measured
147 completed PNG/element pairs before the unchanged 1200-second native process
deadline, with normal 4.623–14.466 second case intervals rather than a stalled
case. The requested shared viewport sharding is being implemented: three
independent 55-case native invocations against the same fixture/server, retaining
every original case ID, error and the existing per-process deadline. The full
660-state gate and tolerances remain unchanged. Compact macOS JSON serialization
is merged; its data is unchanged and actual speedup still needs CI evidence.

Changes for the clients (macOS mounted-toast capture): the owner's latest
Copy capture correction is merged. It waits for the same actual SwiftUI toast
surface/text to mount while the original lifetime runs, then observes that
same toast; no extra Copy or lifetime extension. The owner's `25f57f2`
diagnostic confirms opaque large-window PNGs and both real panel gestures,
with 18/19 native cases complete and the pre-fix Copy mounting failure retained.
New end-to-end validation is still required.

Changes for the clients (pseudo-element coverage correction): the actual d8f74ff
toggle `::after` has both a positive 14x14 DOMSnapshot layout row and a later
zero-area row. The reference used to overwrite the former and omit the visible
white knob. It now retains all rows and accepts only one distinct positive box;
ambiguous or missing geometry fails. The knob is emitted independently, with its
actual 7px radius. Windows now draws its knob as a native rounded surface with
the missing compositor shadow; blur equivalence remains unmeasured and failed.

Windows NativeLabel extraction now records glyph paint before the Panel branch,
and validates the actual current layout's size/weight getters and brush inputs.
Observer association uses object reference identity. Submitted style is distinct
from final visible glyph geometry/presentation, which remain open obligations.
The real ellipsis regression checks actual layout/inline-object/production
renderer glyph callbacks; zero inline layout height is retained rather than
mistaken for absent glyph paint. The final test D2D sink is explicitly mocked.

Changes for the clients (independent outline and measured-icon pairing): the
reference now exports actual computed outline values separately from borders;
the shared matcher requires explicit evidence for absence and retains unknown
contour/dash/phase as failures. Common schema and native obligations are in
`docs/native-outline-evidence.md`. Verified same-region SVG/vector paint content
now anchors icon pairs before sequence fallback, unique identities first, then
repeated identities in actual reading order. This resolves the requested pairing
diagnostic without suppressing missing, extra, kind, order or visual mismatches.
Full native outline coverage and actual active-contour measurement remain open.

Changes for the clients (d8f74ff capture evidence): all 19 Windows-reference
scenes completed; the shared checker passes 69 Node and 359 Python tests in CI.
The group reference logo and actual Windows SVG Image both project independently
to `vector-image-v1`. macOS's actual ordered logo draw parameters are merged in
`5d789e9`; its native build/tests pass in run `41000400641`. Windows's new real
ellipsis tests expose an inline metrics height assumption and remain failed;
the core 28 tests pass. No element-parity acceptance is claimed.

The Windows panel-hover receipt exposed a real delayed empty tooltip: the
resize handles had cached their strings before `/api/i18n` arrived. Their live
labels now refresh with menus/language. Capture waits, with bounded recorded
observations, for actual pointer-release/layout events to establish idle hover;
it never synthesizes another input or forces a visual state. A tooltip that
changes between PNG and extraction remains a failed checkpoint. Custom toggle
and scrollbar page controls explicitly clear unused default gradient borders;
their actual track/thumb paint remains independently recorded.

Changes for the clients (actual sidebar preview trimming): the Windows group and
private preview entry now uses its production DirectWrite layout for CHARACTER
trimming, the real ellipsis inline object, and recorded DrawInlineObject/glyph
callbacks. Its native Text peer and parent row retain the full accessible text;
the actual muted foreground and row tooltip remain. ABI and real layout tests
run only in CI. The headless app build passes; screenshot attribution, projected
font/ellipsis geometry and complete element coverage still require evidence.
The `d8f74ff` diagnostic shared checker passes with the image-byte comparison
integration. The latest macOS outline and measured-icon pairing requests are in
progress; missing/extra/order failures and all tolerances remain unchanged.

Changes for the clients (actual image content comparison): the reference now
collects only the page's actual completed Image responses and retains the real
DOM backend/object identity through PNG and extraction. Windows records its
actual loaded SvgImageSource bytes (68da37d group confirms the 514-byte source,
successful decode and current COM binding). Shared `image_projection.py` rechecks
these receipts before strict SVG decoding into `vector-image-v1`; original bytes,
transport URI and unrelated errors stay in evidence. Unsupported features/formats
fail. The matcher validates the entire representation and compares ordered paint
layers exactly; this is not an icon equivalence mapping. See
`docs/native-image-evidence.md` for the format and macOS draw-receipt obligations.
Integration now awaits CI. The unrelated scrollbar Node fixture slicing regression
has been corrected without suppressing its case.

Changes for the clients (pending outline request): the latest macOS request adds
actual inward dashed outline evidence for subgroup avatars. Common reference
outline capture/comparison is still required; neither border substitution nor
unmeasured dash/curve equivalence is accepted. This request remains open. The
sidebar UIA zero-area diagnosis is recorded in `docs/native-uia-zero-area.md`;
the current provider rectangles are retained as failures while actual production
trimming evidence is implemented.

Changes for the clients (b89f80b runtime): Windows diagnostic `40996427962`
now produces all 19 original PNGs. All 76 actual text-surface readbacks report
`surface-pixels-read`, current draw versions and successful submission; journal
I/O is at most 2.741ms per exported probe. Final PNG attribution is still separate.
The cases remain failed because UIA reports unknown/zero-area text rectangles;
neither those errors nor the scene gate were suppressed. The checker regression
with null runtime type receipts is fixed while preserving unknown raw evidence;
its menu fixture now explicitly supplies the actual template facts it models.

Changes for the clients (SVG source binding and transparent capture regression):
Windows's actual 18px logo Image now decodes the packaged SVG byte stream through
the same SvgImageSource recorded by capture. The receipt preserves source IUnknown
identity, original bytes, stream length, actual load status and failures. It does
not manufacture a glyph or prove final screenshot contribution. Shared SVG paint
decoding is separate. The macOS `9990d4f` transparent-canvas fix is merged; the
shared gate additionally rejects an entirely transparent PNG even if its AX tree
looks valid. Old transparent PNGs stay available as failed evidence.

Changes for the clients (reference scrollbar evidence): every actual scrolling
axis now emits a scrollbar and thumb. The reference stores its actual DOM gutter,
owner and scroll state, plus lossless pixel runs from the original PNG. Gutter,
thumb outer box, hit box and ink envelope are distinct quantities. A uniquely
attributable ink envelope cannot supply the unknown outer/hit box; no scroll-ratio
or transparent-border estimate is used. Unknown thumb geometry/style still fails.
See `docs/native-scrollbar-evidence.md`. Windows and macOS must preserve the same
quantity distinctions when comparing actual template/draw evidence.

Changes for the clients (new image request in b89f80b): the actual loaded brand
image must be compared by measured resource/paint content rather than its random
localhost transport URL. Shared resource-byte/decoded SVG evidence and Windows
SvgImageSource binding are being implemented. macOS's actual NativeLogoView draw
receipt is retained; no image mapping or equivalence exception is approved.

Changes for the clients (verified Copy fix and Windows ABI correction): diagnostic
`40994609011` / `8b5bfce` reference Windows completes all 19 cases. The actual Copy
receipt has all six state checkpoints, successful final clipboard read and no
action errors; both panel gestures also complete. Windows native has no screenshots:
`067eec6` and the following build crash at the COM `GetPixelSize` getter. Its struct
return and `GetPixelFormat` now use the actual COM output-buffer ABI. Three mock
regressions lock that signature and exercise controlled vtable slots; real D2D
readback still awaits CI. A per-case journal flushes actual API stage boundaries
to the OS before native calls, retaining the last successful and pending method
if the process crashes. No final-window pixel identity is inferred.

Changes for the clients (ca134e4 validation): both native build/test jobs pass,
including 128 macOS tests and Windows 28 core plus 9 UIA mock tests. The source
gate still reports the same four Windows vocabulary omissions. The diagnostic
element report remains failed with zero accepted scenes; its native macOS raw
elements are structurally valid now, which does not establish element parity.

Changes for the clients (actual header paint and template ownership): Windows
menus, navigation and CommandBar now have transparent child backgrounds under
the single actual titlebar surface, matching the reference container structure.
Individual button hover/selected paint remains. A native region Grid is not a
templated Control: only captured actual `is_control` and nonnull
`control_template_present` permit template paint ownership. Ordinary child paint
remains independent; absent evidence fails instead of silently absorbing it.

Changes for the clients (bounded reference capture): the original Copy PNG is
now requested while the real toast timer and renderer are running. Immediately
after its reply, the isolated page's actual clock is paused for source collection;
the same toast, message, toolbar, pointer and visible state must still match the
pre-PNG checkpoint. Expiry or replacement fails, with no repeated Copy or extended
timer. `clock_pause.phase` records `after_original_png_before_source_collection`.
Each original reference case has an owned CI browser worker with a 90-second
deadline; timeout/error receipts retain its last pending step and process cleanup,
then the remaining cases are attempted. The shared server/fixture and workflow
deadline remain unchanged. Completion counts come from actual worker receipts.
This addresses the macOS request's confirmed `Page.captureScreenshot` stall;
successful execution still requires new CI evidence. macOS's 55-scene real panel
gesture implementation is merged in `ac1fc0c` and awaits its own capture receipts.

Changes for the clients (1c66b83 CI): the Windows build and its 28 core plus
9 mock UIA tests pass again. macOS runs 127 tests but has four assertions failing
in `SurfaceRasterTests.testComposerDisabledOpacityIsAppliedExactlyOnce`: light
observes about .140819/.140651 versus .105882, dark .740474 versus .687059, with
the original .007843 tolerance retained (`40993300811`, job `123860557319`).
The owner still needs to resolve the actual color/compositing discrepancy.
The four Windows-only missing vocabulary usages remain reported by the source
gate; no dead string references or new allowlist entries were added.

Changes for the clients (window region accessibility): Windows now exposes real
Group peers for the titlebar, organization-tree viewport and conversation region,
with the corresponding `page.titlebar`, `page.tree` and `page.chat` names from
the shared locale. The existing chat ScrollViewer retains its own native Pane
and scroll provider. Projection uses those actual objects and independent UIA
counterparts; painted group backgrounds must not overwrite their region kind.
This fixes missing region semantics without altering their intended layout.

Changes for the clients (latest macOS request): the same paused-clock CDP
screenshot stall is confirmed by full Windows `40987192072` and diagnostic
`40988143838`; the actual Copy and clipboard reads succeeded before the wait.
The shared capture owner is correcting frame/clock sequencing and bounded
case isolation, retaining the original toast identity and failure receipts.
No matrix scene or screenshot requirement is removed.

Changes for the clients (55-state shared matrix): all 53 existing scenes remain,
with `panel-resize-hover` and `panel-resized` added: 660 full cases per platform,
19 diagnostic cases. Start from group/Overview, click the real toolbar toggle if
the panel is closed, then hover its real handle or drag it 64px left in eight
pointer steps. Require width+64, left-64 and unchanged top/height, retaining the
actual pointer and state through PNG/extraction. macOS should implement these
same real actions. The shared scrollbar/scrollbar-thumb kinds now accept actual
track and thumb elements, with required measured orientation and normalized
scroll_position, actual enabled state and unchanged paint requirements. Original
AX/UIA hit rectangles are separate evidence from painted rectangles; viewport
ratios cannot supply thumb paint geometry. See `docs/native-elements.md`.

Changes for the clients (067eec6 CI): Windows build and 28 core plus 9 mock UIA
tests pass. macOS run `40991154738` still fails two SurfaceRasterTests assertions
for disabled composer opacity (observed about .733646, expected .687059 with its
existing .007843 tolerance). This remains for the macOS owner; no test tolerance
or acceptance exception was changed. The b81d45a Python/package matrix passes.

Changes for the clients (actual submitted text surface probe): Windows CI now
reads the current NativeLabel SurfaceImageSource target after the original
production glyph drawing, using the actual BeginDraw atlas offset and observed
pixel format. It copies to a CPU-readable bitmap and exports premultiplied BGRA
bytes, pitch, dimensions, target identity, draw revisions and per-API HRESULTs
under `native-label-surfaces/`. Failures also retain sidecar evidence and fail the
scene. Normal app sessions do not run this probe. The headless build passes, but
actual atlas readback support awaits CI. Surface pixels alone do not prove final
PNG contribution: `presentation_identity_proven` remains false, with no second
layout/render or synthetic screenshot substituted.

Changes for the clients (requests added in macOS b3d2385): the scrollbar track
and thumb kinds and the omitted panel resize control are required coverage work.
The shared owner is implementing their schema and real resize interaction states;
no existing scenario is removed. macOS actual draw receipts remain distinct from
its wider AX hit bounds. Its latest test fixture corrections and explicit
unapproved Install discrepancy have been read; no exception is accepted.

Changes for the clients (native select-arrow request): the macOS request added
in `b666de1` now has a shared raw evidence contract. Each actual visible select
retains its owner box, appearance/direction/zoom/borders, live state, AX record,
pierced UA subtree and actual PNG identity in raw `ua_select_arrow`. The browser's
painted arrow is not assumed absent merely because it has no DOM SVG. Unmeasured
presence/geometry/path/style remain null and explicitly fail coverage. Real
appearance:none and AX-confirmed listboxes are recorded with their actual scope;
customizable base-select paint remains unknown. No source-code arrow constants
are promoted to per-case measurement. The Windows/macOS arrow comparison remains
unresolved until actual paint is attributed and measured.

Changes for the clients (actual Windows paint): the fenced code text now uses
the real nested .9em cascade (11.25px in chat, 10.8px in documents), while its
preformatted container retains its own line spacing. Header/composer chips now
use the final reference rule's opaque card fill, 14px radius, 11px padding,
5px content gap and 4px trailing margin. Search placeholder paint is explicitly
opaque #757575, also confirmed by the older full dark capture. The two-layer
vacant indicator is one real NativeStateDotView with exact current child identity
evidence; both painted layers remain raw. Aggregate shadow equivalence is still
unknown and fails coverage. Headless Windows App and capture builds pass with
zero warnings/errors; CI runtime and fixtures remain required.

Changes for the clients (UIA provider failures): file-code's managed format range
GetBoundingRectangles returns E_UNEXPECTED. Capture now retains the actual text,
endpoints, format movement, API and HRESULT before that read, and continues
independent COM observations. Failed geometry stays null, never an empty measured
array or a value copied from another provider. Shared projection accepts that
nullable failure shape and preserves it as a coverage error. Nine mocked provider
cases are added to the Windows CI test job; no provider root cause is yet proven.

Changes for the clients (38af737 independent evidence): the diagnostic report is
downloaded to `S:/Codex/Outputs/Relic-native-visual/parity-38af737/` from run
`40987219219`. Both platforms still have zero accepted scenes. This 17-case
diagnostic does not replace the 636-case matrix, and every unresolved extraction
and comparison error remains in the report. Windows copies now has a complete
339-node native UIA index without the previous self-cycle. All 17 Windows cases
have actual Rendering/Rendered, compositor commit and DwmFlush receipts, but
these do not alone prove the final frame's glyph-to-pixel association. macOS
retains one group scene geometry-drift failure; its source inspection changed
four mounted views. The native-macos requests merged through `668b1f8` confirm
the shared caret-preservation and aggregate-test fixes are consumed; no new
exceptions or tolerances are requested.

Changes for the clients (reference disclosure projection): real closed HTML
details expose only their first direct summary subtree, including through nested
details. Nonpainted contents remain in raw DOM evidence, with actual open state
and summary ancestry, rather than becoming canonical text from a forced DOMRange.
DOMSnapshot missing string index -1 is now null with its original index retained.
Neither failed font queries nor unknown glyph measurements are filled in.

Changes for the clients (Windows measured layout corrections): the actual
CommandBar template now constrains its ContentRoot and PrimaryItemsControl to
39px and removes the unused overflow column, correcting the measured 4.5px
vertical and 6px horizontal offsets without changing extracted coordinates.
Color swatches paint under their transparent border, retaining the full 24px
disc on hover/press. Single-line form focus keeps the real reference selector's
line-2 border; native focus/caret remain active. CI validation is pending.

Changes for the clients (registered Markdown blocks): Windows records the actual
fenced-code Border, ScrollViewer and TextBlock object identities in production.
Extraction validates current child/content references and rendered ancestry before
classifying that container as code; ordinary painted Borders remain unchanged and
all code text is retained. Invalid registration fails coverage. Inline-code pills
now use their natural font line height and the reference's 7% brush alpha. The
headless Windows build passed with zero warnings/errors; runtime verification is
pending and no tolerance, scene or exception changes were made.

Changes for the clients (38af737 capture results): Windows diagnostic run
`40987219219` saved all 17 canonical PNGs and source records. Every case still
fails UIA extraction, so the successful count remains zero. The older frame
observer timeouts are absent in this receipt. Native apps run `40987197787`
passes Windows but macOS reports six assertions across static-text accessibility
and two TextKit tests (123 tests); those remain for the macOS owner. The four
Windows vocabulary gaps also remain failures, not accepted exceptions.

Changes for the clients (38af737 checker verification): diagnostic workflow
`40987219219` passed 50 Node fixtures and 253 Python fixtures, including real
Text-node font attribution, native surface identity and actual inline sequence
failure cases. Real client captures and the full matrix remain pending; these
fixture results do not prove rendered parity. macOS build run `40985545529`
on the older `34d4c35` reports two assertions in
`ElementCaptureTests.testActualStaticTextValueSuppliesItsNameWithoutPromotingEditableValues`
(AXUnknown and empty Name for the test field). The macOS owner must resolve
that actual test failure on its branch; no shared exception is added.

Changes for the clients (34d4c35 runtime verification): run `40985550458` confirms
the previous Windows pointer-action failures no longer occur. The real textarea
grew by 64px with ten DragStarted/Delta/Completed records and four stable
checkpoints; message Copy retained the actual clipboard, localized toast and
paused/resumed production timer. This does not pass element parity: UIA still
reports unmeasured zero-area text ranges, and eight scenes observed Rendering
without Rendered. The frame observer now requests an actual production redraw
after subscribing; a failed observer preserves PNG/source evidence and still
fails the scene and gate. No missing frame acknowledgement is inferred.

Changes for the clients (reference font attribution): real DOM Text backend IDs
are mapped to frontend IDs and queried individually with CSS.getPlatformFontsForNode.
Each request and result remains auditable. Parent aggregate counts cannot fill a
failed child query. This uses the actual LayoutText shaping data supported by
the captured Chromium build; ellipsis ink and actual weight axes remain unknown.

Changes for the clients (Windows form and navigation): the repeated 22px modal
padding has been removed only for content that already owns its padding. Settings
now has one real vertical SelectorBar and selected item, preventing initial focus
from replacing the requested page. Sidebar row accessibility names derive from
their own mounted labels and update when those labels change; no reference text
is copied into extraction. These changes await new CI captures at all sizes.

Changes for the clients (Windows disclosure accessibility): the customized
Expander template omitted the standard `ExpanderToggleButton` AutomationId.
WinUI's actual ExpanderAutomationPeer uses that ID to replace its header peer
with the header's children; the header event source points back to the Expander.
The missing ID explains the observed self-child RuntimeId in copies. The real
template now retains that platform contract. The extractor still rejects cycles
and records both ends rather than hiding duplicate nodes. CI must verify the fix.

Changes for the clients (6dbdfd8 capture results): Windows and macOS native
build/test jobs in run `40983626194` passed. The independent Windows diagnostic
run `40983620508` attempted all 17 cases; its reference completed all 17, including
Copy toast and textarea resizing. Native evidence remains failed: twelve cases
produced PNG/XAML evidence but UIA extraction failed, and five real pointer
gestures did not reach their required state. This is not a passing matrix.

Changes for the clients (Windows pointer delivery): the actual textarea receipt
showed a changed cursor and DragStarted/DragCompleted but zero DragDelta events.
Capture now sends motion/down/up through Win32 SendInput, including desktop
coordinates and DPI conversion, and records the requested and observed cursor.
It still checks the same production handlers and scene results. No direct UI
state assignment, tolerance change, or fallback pass substitutes for the gesture.
Each case retains its `.pointer-input.json` even when the scene action fails.

Changes for the clients (reference caret and checker assertion): the requests
in `f255c3d` are addressed. Regular Playwright PNG capture preserves the actual
caret with `caret="initial"`. Focus, selection and computed CSS are retained as
context only; unknown caret paint/bounds/blink still fail coverage. The aggregate
failure test checks the current component-prefixed error and nonzero exit without
removing failure assertions. The original 53-state matrix is unchanged.

Changes for the clients (Windows interaction/layout corrections): member-card
model actions and inspector action/link labels no longer select their own text
instead of forwarding button clicks. Body text remains selectable. The person's
read receipt aligns to its message's right edge independently of the thread
button, matching `.msg.mine .body` child alignment. CI still has to verify these
production changes; their source changes are not parity evidence.

Changes for the clients (failed-state diagnostics): Windows now saves an actual
failed-state PNG under `diagnostics/<case-id>.failed.png`. It never substitutes
for the canonical scene or increases the success count. The matcher continues
rejecting unexpected canonical files. macOS `6dbdfd8` currently writes fifteen
`*.before-capture-error.png` siblings, which are therefore reported as unexpected
captures; the macOS owner should place such noncanonical debug images in the
same `diagnostics/` subdirectory while retaining the original case failures.
Run `40983620508` also reports native geometry removals after macOS extraction
and two real action failures; these remain unresolved in that revision.

Changes for the clients (shared checker correction): the macOS request in
`907dcb2` and Windows checker run `40982586850` identify the same stale test
expectations. The lifecycle regression still requires all 53 real manifest
entries to be attempted; its final case is now `new-org-textarea-resized` and
52 succeed after one deliberate mocked failure. No assertion is removed.

Changes for the clients (paused reference Copy toast): actual clipboard reads
now occur before the virtual-time pause and after resume, with their distinct
receipts. Paused checkpoints do not await Async Clipboard. The frozen scene's
PNG comes directly from CDP Page.captureScreenshot, with real viewport and PNG
dimension checks; no toast, caret or pixels are constructed. Durable per-step
receipts identify future stalls. See `native-message-capture.md`; CI runtime
verification is still required.

Changes for the clients (independent capture attempts): `c568f13` stopped inside
the reference Copy-toast clipboard read after pausing virtual time, before either
native application launched. The coordinator now attempts native capture first,
then the matching reference, retaining either side's errors and actual completion
count in `components.json`. An exception on one side does not suppress the other;
existing PNG/JSON file counts are diagnostic only. Canonical scenes, fixture
inputs and all acceptance requirements remain unchanged.

Changes for the clients (macOS integration): `58d0179` merges the native AppKit
textarea handle, real drag receipts and stable geometry snapshots requested
for the shared 53-state matrix. `native-geometry.json` retains actual mounted
view geometry across PNG and AX phases; capture drift is a failure. The source
tree now includes both native gesture implementations; this is not a statement
that the real captures or handle paint match. No additional shared exception
or reference geometry is supplied to the macOS client.

Changes for the clients (Windows UIA performance): actual COM RuntimeId lookup
now builds one raw UIA subtree index per HWND instead of searching the whole
subtree for every text control. Every attachment still checks fresh RuntimeId,
process and exact range identity; empty/duplicate IDs and incomplete enumeration
fail. `<scene>.uia.json.progress.jsonl` flushes actual stage timing and partial
measurements before provider calls, so the unchanged timeout leaves evidence.
No zero-area range or source measurement has been discarded to reduce failures.

Changes for the clients (Windows production textarea): multi-line form fields
retain the real TextBox editor and add a production native Thumb for resizing.
The new scene uses the shared real pointer recipe and observes actual DragDelta
effects. Extraction identifies the handle through the live owner's object
identity, not an expected rectangle or an AutomationId alone. Reference UA-grip
paint remains unknown and the gate continues failing until independently measured.

Changes for the clients (Windows actual text draw): the first four native menu
labels now use one production DirectWrite layout for measurement and drawing
into their visible WinUI surface. The capture preserves the same DrawGlyphRun
callbacks, actual faces/glyphs/advances and successful EndDraw receipt. Ordered
font fallback is applied to that production layout and read back. This first
control is not a complete application typography migration: presentation-frame
synchronization and equal-quantity canonical geometry remain incomplete and
explicitly fail coverage. TextBlock captures also retain actual IsTextTrimmed
separately; neither that state nor a zero-area UIA rectangle proves an ellipsis's
painted box. No unknown glyph measurement is replaced by configured font data.

Changes for the clients (actual Windows brush alpha): XAML capture now keeps
`SolidColorBrush.Color.A * Brush.Opacity` as an unrounded component, matching
the shared computed-color quantity. Original color bytes and brush opacity
remain separately recorded. Raster samples remain independent; alpha tolerance
is still zero. This removes a capture conversion error, not a rendered mismatch.

Changes for the clients (macOS display request): `83ad0e3` merges the client's
real CI display-mode selection and restoration, with `native-display.json`
receipts. The requested 1440x900 client size and all scene sizes remain unchanged.
The shared runner needs further display setup only if actual advertised modes
cannot contain the required window; pending captures must establish that result.

Changes for the clients (textarea resize): the macOS request through `b4575f7`
now has a shared real-input recipe and `new-org-textarea-resized` scene. All
52 earlier scenes remain, giving 53 / 636 full cases per platform and 17
diagnostic smoke cases. `native-resize-evidence.md` specifies the actual corner
drag, unchanged text and stable-state receipts. The UA grip's independently
measured paint/bounds are still unknown and explicitly fail extraction; the
gesture coordinate is never used as a measured grip rectangle.

Changes for the clients (bounded paint diagnostic): the actual `3e5f1a9`
macOS run stalled during the supplementary paint-trace step after canonical
artifacts had uploaded. Each supplementary trace now has a five-minute CI
step limit and durable before/after protocol progress receipts. This does not
limit or remove canonical scenes, change the matcher, or turn missing paint
evidence into a pass; timed-out diagnostics retain partial artifacts and fail.

Changes for the clients (paint diagnostic channel): the actual `3e5f1a9`
trace still loses picture packets and exports no LayerTree events. CI now
retains that diagnostic and additionally captures regular Chromium in new
headless mode via `--channel chromium`, in separate artifacts. The canonical
reference environment and matcher are unchanged; this is an environment
diagnostic, not a replacement measurement. See `native-reference-evidence.md`.

Changes for the clients (macOS stalled-process evidence): the shared capture
now fulfills the request merged in `c568f13`: on the unchanged 90-second
progress failure, CI macOS samples the actual owned native PID for three
seconds, bounded by an eight-second subprocess timeout, before termination.
`native-stall.sample.txt` and `.json` retain the actual stack/output/status.
Sampler success never converts the capture timeout into a pass; Windows,
non-CI execution and server/reference waits do not run this diagnostic.

Changes for the clients (message interaction capture): the macOS request merged
through `02b07e2` is implemented in the shared matrix and Windows capture.
`message-hover` and `message-copy-toast` preserve the prior 50 scenes and extend
the complete matrix to 52 / 624 cases per platform. Diagnostic smoke preserves
its prior 11 and adds the five new member/message interactions (16 cases).
`native-message-capture.md` specifies real pointer/copy/clipboard receipts and
the same toast instance across PNG and element extraction. Reference capture
pauses the actual CDP clock after the real toast appears; Windows pauses its
actual production timer, records monotonic remaining time and resumes it in
finally. macOS must retain its actual timer/clock pause and instance receipts;
capture-only permanent-toast flags or repeated Copy actions are not substitutes.
Composition shadow objects are retained as raw evidence; unmeasured raster/clip
or blur equivalence continues failing extraction.

Changes for the clients (Windows typography): the non-document XAML controls
now request the reference's explicit UI fallback list, including Microsoft
YaHei UI after Segoe, and inherit the selected interface language. The previous
single-family request delegated CJK fallback to Windows and produced different
line breaks in the actual `36fca26` captures. This request change still needs
new capture validation and does not prove actual rendered glyph identities.
TOM document controls keep their separate single-face formatting contract.

Changes for the clients (layout projection): `native-layout-projection.md`
defines the common raw/visible-element/owner evidence contract requested by
macOS. Unknown paint or interaction is not proof of a layout-only wrapper.
The reference now retains two independently evidenced omissions: named AX
navigation with matching DOM semantics, and tabindex-0, AX-focusable scrolling
regions with actual overflow. All prior reference elements and unresolved
scrollbar failures remain; native clients still need independent ownership
proof before any corresponding wrapper projection change.

Changes for the clients (macOS request integration): the member-card editing,
conversation-banner and suggestion-control changes through `edf599a` are merged.
The three requested member-card interaction states are now added to both the
shared matrix and Windows capture, preserving the existing 47 states. The full
matrix is now 50 states / 600 cases per platform. Rename and model editing use
real pointer clicks; avatar hover uses real pointer movement and retains its
actual overlay visibility. Each capture keeps the action receipt; no edit or
hover state is injected into an extractor. The
layout-only-wrapper projection request is under evidence review: null paint or
a generic group role is not proof that a node may be omitted. Raw nodes and
unresolved coverage failures remain retained.

Changes for the clients (reference capture environment and shared requests):
the captured Chromium command line revealed Playwright's default
`--hide-scrollbars`. Both canonical and diagnostic captures now remove only that
default switch, letting the real page's scrollbar CSS render. Earlier reports
retain their original evidence and cannot be treated as a directly comparable
trend. Scrollbar coverage still requires measurement; the switch alone proves
neither presence nor absence. The macOS request about shared scrollbar tests
was fixed in `5bb04e5` (source-expression boundary); no production extractor or
test assertion was removed. Its request about color quantity is resolved by
preserving computed unpremultiplied sRGB float RGBA and independent canvas RGBA8
raster evidence separately; see `native-color-evidence.md`. Native brush values,
alpha comparisons and DeltaE tolerances remain unchanged. Unsupported computed
color serializations still fail extraction. The macOS live states and real animation
clock implementation were merged in `ddf7759` and await CI capture validation.

Changes for the clients (isolated Windows capture): every Windows case now uses
a fresh native process and its own `RELIC_VISUAL_STATE_DIR` for view history,
read state and drafts; the same fixture server remains shared. UIA requests are
bound to that process and case. A crash preserves its logs and fails the run,
but no longer prevents subsequent cases from being attempted. The full matrix
remains 564 cases per platform. The separate diagnostic `smoke` run now includes
all its previous seven scenes plus the file menu, source file, expanded live
tool output and typing; its 11 cases are not acceptance evidence for the full
matrix. Smoke and full captures have separate concurrency groups so diagnostics
cannot replace a pending full run.

Changes for the clients (live capture states, 2026-10-29): the original 44
states remain; `live-busy`, `live-tool-output`, `live-typing` extend the matrix
to 47 states / 564 size-language-theme cases. Before **every** case, POST
`{"scene":"<scene>"}` to `fixture.scene_endpoint` with `X-Relic-Token`; this
clears the prior live fixture and returns the actual `org`, `member` and `live`;
live responses also include `state`, `tool` and `permission`. Reload the organization snapshot before
entering that returned member's private chat, so its real embedded/live state
is loaded. For `live-tool-output`, click the real disclosure whose title is
the returned `tool.title`; require it to remain expanded. Save preparation and
action receipts next to the screenshot. No provider/member session is launched.
For live captures, pause the actual framework animations and seek their clocks
to zero before PNG and element extraction; retain actual clock/state receipts.
Reference screenshots use `animations="allow"` after this explicit pause so
Playwright cannot temporarily cancel and restore the animations. macOS must
freeze its actual animation time axis likewise; inability to do so remains a
state/measurement failure, never a reason to insert constant opacity or exclude
typing dots. Windows uses the production Storyboard capture hook.

Baseline: `2007a83` (PR #1 merge, v0.7.0-beta.1 candidate). The executable clients are
SwiftUI on macOS 14+ arm64 and WinUI 3 / Windows App SDK with .NET 8 on Windows x64.
`plugins/relic` remains the single engine. Neither client instantiates a browser,
HTML renderer, JavaScript runtime, WebView2, or WKWebView. Server-side static files
remain a reference until full native parity is satisfied.

## Acceptance

Changes for the clients (paint diagnostic): Windows/macOS en-US/light CI now
records separate Chromium paint traces for the existing 1440x900 group and
file-code scenes after the normal matrix capture. Raw SKP/trace/layer/font/DOM
artifacts are diagnostic evidence only; no canonical glyph/scrollbar value is
filled from their presence. Missing or dropped trace data is a diagnostic
failure, and unresolved paint measurements continue failing the main gate.
See `native-reference-evidence.md` for the attribution work still required.

Changes for the clients (live rendering coverage): Windows now renders current
turn prompts, tool rows, permission cards, reply bubbles and typing indicators
with native controls matching the reference structure. The current `private`
fixture contains transcript history, not embedded live state, so it does not
verify these branches. `native-windows-live-evidence.md` records the remaining
fixture/state coverage and actual Hub inputs needed; no runtime coverage is
claimed from a successful build or the existing private-chat scene.

Changes for the clients (Windows document evidence): the source preview exports
actual TOM range text, positions, client rectangles, formatting properties and
the complete native story including its final paragraph marker. Source ranges
are projected separately from their real document owner; requested font names
remain provider evidence, with physical face identity still unknown. Native
ImageBrush evidence retains actual bitmap dimensions, placement transforms and
the live BGRA8 premultiplied PixelBuffer (base64/zlib), never a reconstructed
fixture image. Canonical image-pattern paint coverage still fails until those
independent brush representations can be compared with measured placement.

Changes for the clients (reference reading order): extracted reference elements
retain their real IDs, text and measurements while traversal follows the actual
DOM child-node order, with `::marker` / `::before` before children and `::after`
after them. This corrects code line-number ordering and mixed inline text.
Unmatched identities are retained with an extraction error. No counterpart,
measurement, scene or mismatch is removed to correct the traversal.

Changes for the clients (JSON preview and brand vocabulary): `GET /api/fs/read`
now adds `display_text` for `kind == "json"`, using the existing shared JSON
display formatter for JavaScript property order, binary64 numbers and two-space
indentation. Parsing uses only the existing returned text; invalid or truncated
JSON that cannot be parsed stays verbatim. Raw `text`, `path`, `size`, `mtime`,
`truncated` and filesystem authorization are unchanged. Native file previews
consume this additive field instead of platform JSON pretty printers. Both
word lists now provide `common.app_name: "Relic"`, copied from the reference's
literal empty-conversation header in `app.js`. Windows uses that key for the
same header; the reference source and baseline have not been modified.

Changes for the clients (native controls checkpoint): Windows member forms now
have the reference radio cards, field order, real suggestion inputs and session
rows. Sidebar name layout uses the actual available width and preserves
fractional row heights. Receipt/action disclosures retain native Expander
interaction with reference headers, metadata and source panels. The image
preview paints its actual checkerboard brush; source code uses a read-only
native rich-edit document, real tab stops, source-range selection and measured
line positions. Capture waits for that document's actual layout and fails on
initialization errors. These changes require CI validation; missing document
and image-brush measurement evidence still fails the gate.

Changes for the clients (chart capture failure): `b5e68ab` Windows screenshots
failed chart scenes because the viewport was attached to the dialog Grid before
being assigned to its keyboard-focus ContentControl. The viewport now has one
visual owner from construction. This fixes actual native parenting, with the
same chart content and keyboard behavior; no chart case is skipped or retried.

Changes for the clients (member suggestion states): the full matrix keeps the
original 42 scenes and adds `member-host-model-suggestions` and
`member-existing-seat-suggestions`, for 44 scenes / 528 combinations per
platform. Open the real host/existing form, focus its model/seat-name input and
send Down Arrow to the actual native control; do not construct capture-only
menus. Windows identifies those inputs by `member-model` / `member-seat-name`.
macOS must add both scene handlers. Reference capture retains before/after
CDP AX/DOM/target evidence; Chromium's browser-owned Autofill popup is not
presumed present in a page screenshot. Its unmeasured paint/presence/coverage
remain explicit gate failures. Source datalist options are never emitted as
visible counterparts. No original scene or tolerance was removed.

Changes for the clients (`e0bbd64` member-form request): `/api/i18n` now includes
`member.harness_label` with the reference's literal `Harness` in both languages.
This distinguishes that form label from the longer `common.harness` settings
heading. The original keys, payloads and engine behavior remain unchanged.

Changes for the clients (conversation, menus and workspace): Windows now uses
reference-sized native menu presenters/keycaps, compact trajectory rows, the
reference inline-code/path parser, digest/plain disclosures, hover actions and
thread composer. Workspace/file views use sectioned layout, native tree rows,
file metadata, preview/source tabs and selectable source with line numbers.
These are production UI changes awaiting matrix evidence, not a parity claim.
The pending native font measurement work is documented in
`native-windows-font-evidence.md`; font-face evidence remains unknown until the
actual production draw supplies it. No guessed font evidence is accepted.

Changes for the clients (CI checkpoint): `b5e68ab` package validation passed
all four Windows/macOS Python environments in 40963546083. Windows and macOS
native builds/tests passed in 40963545988; the four platform-conditional static
vocabulary differences remain failing while the reference-input question is
pending. Visual 40963539383 passed 21 Node and 124 Python matcher fixtures;
capture/element parity remains a separate, currently failing acceptance gate.

Changes for the clients (measurement audit): active CSS ellipsis no longer
exports a clipped layout range as measured painted text. Unknown standalone
text bounds retain null coordinates; directly measured control boxes remain.
Raw ranges, actual AX fragments and `evidence.clipped_range_envelope` remain
auditable. HTML shows the latter with an explicitly unmeasured dashed outline;
coverage and geometry still fail. See native-reference-evidence.md. Windows
also reconciles a uniquely identical UIA/XAML control whose actual cumulative
opacity is zero, preserving both raw nodes and never hiding provider subtrees.

Changes for the clients (current CI): `ca7ff11` Windows and macOS build/test
jobs passed in 40962107208, but static coverage flags four macOS-only settings
keys removed from Windows to match its reference. No inert strings or new
allowlist entries were added. Package CI found a shared-object alias in the
new rule-display regression and unused `native.speech`; per-rule copying and
removal of the unused vocabulary entry fix those failures for the next run.

Changes for the clients (details and copies): Windows now uses the reference
details dialog dimensions, single top bar, 250px navigation, task and protocol
rows, and native check-rule disclosures. Copies include the organization avatar,
title/count, state colors, complete metadata, inline icon/actions and preserved
disclosure state. This is implementation awaiting CI screenshots, not parity.
The complete `1e3b7c5` failed report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-1e3b7c5\`; both platforms still have
zero fully measured/passing scenes. No exceptions are approved.

Changes for the clients (expanded check examples): normalized check-rule
examples now include additive `call_display` and `call_json` in snapshot and
copy responses. They follow the reference's command/file_path/path priority,
JavaScript truthiness, whitespace normalization and 160 UTF-16-unit clipping;
the tooltip retains the full ordered, two-space JSON. Existing call/expect/note
and stored rules are unchanged. The JSON response encoder escapes lone
surrogates created by the reference-compatible clipping without replacing
Unicode. Pure formatter and mocked response tests run only in CI.

Changes for the clients (`2749a17` ordered JSON request): snapshot protocol rows
in both `protocols` and `inherited_protocols` now include additive
`rules_display`, the two-space display JSON for the same normalized wire rules.
Only check-rule `code`/`examples`/`code_sha256` are omitted from that string;
original rules and command payloads are unchanged. JavaScript array-index key
ordering, Unicode and numeric display are covered by CI regression fixtures.
Both native clients consume this string, with older-server fallbacks still
subject to text comparison. No new route or engine fork is introduced.

Changes for the clients (Windows CI hand-off fix): visual run 40955522655
captured all 126 en-US/dark screenshots but failed one workspace element export
when a shared request-file replacement collided with the observer's read.
Each scene now publishes an immutable request and receipt under
`element-requests/<case>.json` and `element-receipts/<case>.json`. Files remain
audit evidence; the observer does not rename/delete a file another scene reads.
Two pure regression fixtures cover queue publication and scene identity. This
changes capture transport only, with no retries, exclusions or tolerance change.

Changes for the clients (`dc32635` dash request): the shared contract now
requires measured `style.border_styles` (TRBL) and, for visible strokes,
window-pixel `stroke_dash`, `stroke_dash_offset`, `stroke_linecap` and
`stroke_linejoin`. Missing values fail; no exact CSS dashed-border cadence is
invented. Chart nodes require independent `state.current`, not `selected`.
macOS must project its actual `projection.stroke_dash` / stroke properties and
`surface_evidence.border_dash` into these canonical quantities where measured,
retaining raw units and unknown coverage when not measured. See native-elements.md.

Changes for the clients (Windows font evidence): verified WinUI source shows
UIA FontName/FontSize/FontWeight report text dependency properties, not actual
DirectWrite fallback faces. Canonical rendered_fonts now remains unknown;
provider names and cmap coverage are preserved separately. Actual physical-face
measurement is unfinished and fails the gate. Single-run accessible names now
use an unambiguous real UIA owner; multi-run ambiguity is never filled from text.

Changes for the clients (captured failure evidence): `1c3b037` report download
is complete at `S:\Codex\Outputs\Relic-native-visual\parity-1c3b037\`, including
all 504 scene HTML/JSON reports and heatmaps. Windows: 93,032 reference,
90,563 raw native, 8,442 invalid native elements; macOS: 92,536 reference,
100,785 raw native, 5,634 invalid native elements. Both have zero fully measured
or passing scenes. Exact category counts remain in summary.json; no exceptions.
`8210a6c` Windows build/tests and static parity pass, while macOS failed at
SelectableText.swift:71 with ambiguous greatestFiniteMagnitude; native-macos
`e4c559e` already fixes that compiler error and is being integrated. Earlier
visual run 40955522655 has a separate macOS en-US/dark mention capture failure
(empty text, candidates=0, attached=true); the macOS owner must fix it, not skip it.

Changes for the clients (production UI): Windows now follows the reference
settings' 920x640 two-column structure, 340px member card, actual menu avatars /
checkboxes / secondary labels, and the native chart's reference layout algorithm,
legend and toolbar. Hierarchy chart entry/capture passes the actual current org
as focus; global chart menu retains all-organizations behavior. These changes
are awaiting strict CI comparison, not accepted parity. Exact shadows, input
templates, truncation and unresolved measured font faces remain open failures.

Changes for the clients (`34d56cd` font-identity request): the strict matcher
compares complete measured PostScript face sets when both APIs expose them,
retaining exact localized family spellings and every fallback face in the raw
evidence. Incomplete PostScript evidence still requires exact family identity.
Two regression fixtures cover localized family spelling, different/additional
faces and missing identities; numeric font-weight differences remain failures.
Reference extraction records the CSS request/variation properties separately
from actual faces, and preserves AX ellipsis fragments without inventing bounds.
No tolerance, exception or scene exclusion is added.

Changes for the clients (latest CI): `1e3b7c5` Native apps run 40955530985 and
package validation run 40955531002 pass. Its visual run 40955522655 passes the
shared extractor/matcher unit-test job and is capturing the complete matrix.
The preceding `1c3b037` run 40952420862 captured all 504 scenes on both systems
and failed the strict element gate; that report is being downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-1c3b037\`. Captures/builds are not
element acceptance. The Windows empty organization state now follows the
reference stream inset, 70vh placeholder, 18px title and 14px explanation;
pane tabs remain present and idle resize handles have no painted gray strip.

Changes for the clients (verified CI): `ca175df` Native apps run 40954033551
passes Windows Release build and 19 core tests, macOS Release build and 73
XCTest cases, both unsigned native package assemblies, and the static route /
vocabulary / flow gate. This is build/contract evidence, not element acceptance.
The earlier `1c3b037` visual run exposed a tuple-versus-dict mistake in the new
activity fixture test; that test is corrected in `a3d4417` without changing data.

Changes for the clients (`0c93bac` measurement follow-up): reference text
clipping now includes the text's own overflow container and preserves raw
DOMRange geometry separately. Unknown ellipsis-glyph and UA scrollbar paint
geometry is explicitly reported as coverage failure; no missing element is
accepted. CSS requested weight and resolved font-face evidence are recorded
separately. The visual CI adds pure Node fixtures for these production functions.
The exact existing tolerance table and all 504 cases remain unchanged.

Changes for the clients (restart integration): `dffd7c4` full strict evidence is
downloaded to `S:\Codex\Outputs\Relic-native-visual\parity-dffd7c4\`, including
all per-scene JSON, HTML, raw trees and pixel heatmaps. Both platforms still have
zero fully measured/passing scenes. Windows has 93,032 reference elements,
84,268 valid native elements and 8,478 invalid native elements; macOS has 92,536
reference elements, 57,705 valid native elements and 4,639 invalid native elements.
The macOS capture stopped at actual 1058px content width for 1024px cases;
`d4a4e44` responsive correction is merged in `1c3b037`. No exception is approved.

Changes for the clients (projection semantics): preserve raw UIA properties but
only apply enabled/focused to measured interactive or focus-capable elements.
An offscreen node does not prove its subtree invisible: traversal and identity
errors remain failures, even when that node's own non-finite measurements are
nonvisible diagnostics. A primary HWND and its proven WinUI host bridge can own
the same XAML root; actual popups and other visible controls are never removed
merely because they are windows/panes.

Changes for the clients (`0c93bac` requests): the new truncation/scrollbar
coverage and requested-versus-resolved font-weight evidence requests are under
investigation. Existing failures remain failures; there is no font-weight
normalization, scrollbar exclusion or tolerance change. The separate Windows
DrawConversation COM E_FAIL in macOS run 40938288684 is being investigated
against the actual failing line and scene, without opening a local window.

Changes for the clients (CI evidence): `dffd7c4` passes all 67 shared extractor/
matcher regression tests in visual run 40935113052; Windows build/unit tests
also pass in Native apps run 40935124389. Its macOS build succeeds, but
`testCompoundNativeButtonRetainsIndividuallyVisibleLabels` fails at lines
65/75/76: AX error -25208 instead of 0 and both labels absent (job 123664233936).
The macOS owner must fix that test/runtime accessibility setup; it is not an
accepted empty tree. The earlier 03c03a5 matrix completes all four Windows
capture shards after the JSON serialization repair; its older projector still
fails on the missing UIA ControlType, fixed in dffd7c4. Neither run passes the
element gate. Latest downloadable failed baseline is parity-5997153, including
summary.json, full JSON, outlined HTML and heatmaps; no exception is approved.

Changes for the clients (`cc405c1` shared requests): reference evidence now
records actual URL, display mode, navigator standalone flag and navigator
platform. The reference remains browser mode, so its Install button is still
present and its absent native counterpart remains a failure, not an exception.
Fixture activity summaries now use real cwd-relative file inputs, and their
stored numeric activity timestamps are fixed before the server accepts clients.
This fixes `record_activity` using wall time independently of `stores.now()`;
no exported text or API response is rewritten. Workspace file APIs still use
real platform paths and each native app shares its platform's exact fixture.
Vector stroke width is measured in content-window pixels; source width and
actual transform remain in raw evidence. A 1.7-unit stroke scaled from a 24-unit
viewBox to 16px is measured as 1.7 * 16 / 24, without changing any tolerance.

Changes for the clients: the macOS reference-platform request in `26d77529` is
implemented by capturing the unchanged reference on **each** native runner,
against that runner's exact fixture/server. Windows uses `visual/reference`;
macOS uses `visual/reference-macos`. The matcher never rewrites Ctrl/Command,
paths or dates and never falls back from a missing Mac baseline to Windows.
Each report records actual browser/platform and CDP-rendered font evidence.
All 504 cases remain required per native platform; this adds reference captures
and removes none. The reference transport context is reused with storage reset
before each page load after `40930725969` exhausted Windows socket buffers near
the end of en-US/light; the real production views and scene inputs are unchanged.
Windows now uses the reference's actual JS pane defaults (340px / files 520px),
56px chat header with avatar/member count/action chips, and 18px composer radius.
The redundant sidebar chart shortcut is removed; chart access remains in the
reference's menus and hierarchy section. Native Button templates retain native
UIA/keyboard behavior while drawing the reference's flat palette.

Changes for the clients: machine-baseline audit found untested paint fields.
The canonical `native-elements.md` now requires individually measured TRBL border
widths/colors, TL/TR/BR/BL radii, effective opacity, structured shadows and actual
background image/gradient descriptors. No tolerance changed. Missing paint on
both sides is not a match. Raw nonfinite provider geometry must be null with its
exact raw value/path in diagnostics, never fabricated zero or a string number.
The `4db4aa6` matrix failed all Windows shards on nonfinite TextPointer JSON;
the Windows extraction fix retains those gaps and lets the matrix report them.
Its macOS zh-CN/dark shard also failed with `Mention scene did not present the
native member picker` (run 40929014959, job 123642155437); macOS must verify this
capture state in the next run. Other three macOS shards completed, not passed
element parity. UIA providers may omit ControlType: retain that missing evidence
without aborting the complete scene projection.

Changes for the clients: full element runs now finish and retain their failed
reports when a newer commit is pushed; newer visual runs queue. Each report
still names its actual commit, and only final-commit evidence can satisfy the
gate. DOM input/textarea placeholder lines additionally use read-only CDP UA
shadow DOM ranges (`.input-text.json`); absent measurements remain errors.
Reports add small summary.json and per-scene parity JSON alongside the complete
parity-report.json, with unchanged tolerances and no excluded elements/scenes.

Changes for the clients: the macOS `61b2740` question about text-only properties
on painted shapes is resolved in native-elements.md. No-visible-text elements
use null font/layout properties; actual icon/edge foreground remains measured.
DOM and Windows projectors follow this common applicability rule. Missing
measurements on visible labels/placeholder text still fail.

Changes for the clients (element-capture determinism): `capture.py` now passes
`fixture.clock = "2026-10-29T11:02:00Z"` and `RELIC_VISUAL_NOW` to native capture.
Reference Date uses that fixed instant with UTC; native display-date helpers
must use it only when CI visual capture is enabled, retaining real time in
normal operation. File/session fixture mtimes are fixed at 11:00 UTC. All
existing scenes put the pointer outside the content before sampling (no hover
scene is defined yet). This aligns inputs, not output normalization: the
extractors still record actual visible strings and actual hover. macOS should
adopt this timestamp and UTC, and version 1 schema from native-elements.md;
its initial raw AX exporter used pre-contract field names and remains failed
until it emits the agreed measurements. No engine API/payload changed.

Changes for the clients (Amendment 4): [native-elements.md](native-elements.md)
defines version 1 per-scene element JSON, visibility/counting rules, UIA/AX and
render evidence, and the strict 504-case machine gate. The `native-macos`
`43bb8e1` shared contract request is addressed there. Prior native-control/date/
menu/document differences are required fixes, not accepted exceptions. No
exception has been approved; earlier `done` rows remain function inventory only.

Changes for the clients: copies and owned/inherited snapshot protocols now always
include the effective `on_error` for check rules (`allow` when omitted, matching
the engine; explicit `deny` preserved). This removes different client defaults
without changing enforcement or stored records. The omitted-field visual fixture
is retained and pure mocked regressions cover both response paths.

Changes for the clients (latest integration): macOS `952ba3a` is merged, including
its compact Settings rows, exact reference avatar palette, task/copy counts and
mention-popup positioning. Both remaining shared requests are implemented:
Windows buffers JSON POST bodies with a computable Content-Length (including the
authenticated token-renewal retry), preventing chunked bytes from corrupting the
next HTTP/1.1 response. A real loopback keep-alive POST→GET regression is added to
the C# suite for CI. The reference `documents` scene now clicks its production
document row and waits for the real body; Windows selects the corresponding
native ListView row and awaits the same existing document GET. No API changed.
Windows documents use the reference's list/detail columns, task filters include
their counts, and capture input leaves the pointer outside the client between
scenes so stale toolbar hover tooltips cannot cover unrelated pages.
These fixes require the next full visual CI; the earlier failures remain evidence,
not a completed visual gate. Existing sidebar ownership and platform-reason
localization fixes are retained.

Visual review after that integration also replaces the Windows trajectory's
stacked member/filter ComboBoxes with the reference's member list and adjacent
trace column, compact native filter tabs and expandable steps. Protocols use
bold headings, origin/inheritance badges, shaded person summaries and code
surfaces. Member model/effort and environment/permission fields share rows in
reference order; unavailable harness selection explains the required setup.
Dialog primary buttons use the chosen accent instead of the OS default blue.
These are native presentation changes; shared routes and payloads are unchanged.

`e4bb502` passes native builds/tests/parity and all four Python CI jobs. Real
desktop captures now include menus and popovers; the reviewed dark and English
images show them correctly. A subsequent visual fix keeps digest/private-chat
banners below the header instead of scrolling them out of view, and refines
secretary choices, inspector rows and task headings. The harness reports each
Windows case and fails a case stalled for 90 seconds, preserving its receipt
and log for diagnosis. No source route or payload was changed by these edits.

Visual review update: `6391291` passes both native build/test jobs and parity.
The full capture exposed a WinUI 1.6 automation-peer crash before the first
Windows image; CI now opens actual MenuBar items through desktop input and
checks that their native popup is present. Settings rows, empty-state centering,
thread tabs and sidebar organization icons were refined against the downloaded
reference images. This is still an iteration, not visual acceptance.

Visual acceptance was rejected by the person on Windows at `ce34cde`. PR #4
is back in draft. The existing `done` columns describe function implementation
only; they do not certify presentation. The additional required visual gate is
documented in [native-visual.md](native-visual.md).

Changes for the clients (2026-10-29): `scripts/visual/scenes.json` and
`docs/native-visual.md` define the shared CI fixture/capture protocol. Both native
clients consume `RELIC_VISUAL_MANIFEST` only in CI and must capture every real
screen/dialog. Reverse native-key coverage now rejects keys missing from either
shared locale. `composer.voice_title` exists in both lists: the Windows bug was
constructing its label before `/api/i18n` loaded and retaining the raw fallback.
Microphone controls now use an icon with localized accessibility/tooltip text.

Visual note for the macOS owner: `iteration-6/macos/zh-CN-light-1024x700-settings-profile.png`
under `S:\Codex\Outputs\Relic-native-visual` shows avatar, avatar label, hint,
name, name hint and Save as separate full-width Form rows. The reference uses
two horizontal rows: labels/hints on the left, avatar/change and name input on
the right. Please review profile/notify/voice/about against that structure.
Windows now uses those compact rows; no shared strings or payloads changed.
Windows avatar colors now follow `app.js:hue`: unsigned hash starts at 7,
multiplies by 31 per Unicode code point of the member/organization ID, then uses
`[18,30,42,205,222,248,272,300,330,350,190,12]`. HSL is 40%/90% background and
38%/34% text in light mode; 18%/24% and 45%/78% in dark mode (`app.css`).
Mac amendment-3 requests 1/2 are addressed by the new shared manifest and visual
workflow (dispatchable on either branch); request 3 is addressed by reverse-key
tests and the existing shared voice title. Exact manifest fields are documented
in `docs/native-visual.md`; macOS should adopt that format.
The visual workflow assembles a real `.app` bundle before running the macOS
capture; launching a bare SwiftPM executable crashed before any capture. The
first reference captures are available in run `40862157094`. Fixture group
recipients and check-rule copies were corrected after inspecting those images.
Changes for the clients: the member-card reference anchor reported in macOS
REQUESTS.md (run `40866009267`) is fixed to the actual `#chat-head` element.
Reference captures now run on Windows against the exact same fixture/server as
WinUI; macOS receives the same deterministic fixture contents. The matrix and
manifest format are unchanged. Windows CI sets its desktop to 1920x1080 and the
client rejects any actual viewport differing from the requested dimensions.
Run `40864840870` produced all 504 Windows captures; visual review found excess
toolbar/message spacing, wide member forms and detached voice buttons. These
are being corrected; capture success is not visual acceptance. The reverse-key
scan excludes test literals and Swift `list.*` SF Symbol names while retaining
all direct translation lookups and checking dynamic vocabulary families.
For the macOS owner: full run `40864840870`, job `123417024885`, timed out after
1200 seconds in the first zh-CN/light manifest. Its artifact contains 34 PNGs
through `quote`/`recipients`, with no `mention` PNG. `client.log` ends with
`NSSpellServer suggestCompletionsForPartialWordRange timed out`; please inspect
the actual native mention/completion path. The artifact is downloaded under
`S:\Codex\Outputs\Relic-native-visual\iteration-3\macos` for read-only review.
Changes for the clients: six shared `native.color_*` labels (clay, ink, indigo,
blue, rose, amber) now localize accent swatch tooltips; language names come from
the `/api/i18n` `languages` array. Windows message headers/read receipts now sit
outside bubbles, code blocks show every line, and file/workspace actions use
compact native toolbars and selectors. No API payloads changed.
The Windows `DrawSidebar` COM exception reported by macOS for `40868069780`
is fixed: reusable inputs are explicitly removed from their owning containers,
without relying on a detached WinUI element's visual `Parent` property. The
new field wrappers and thread composer follow the same ownership rule.
The platform diagnostic localization request is implemented by
`views.platform_info` on both GET and POST `/api/platform`. Fixed reasons and
missing-provider messages now use the shared lists, while transport state,
unknown provider errors and cached diagnostics remain unchanged. Pure mocked
regression tests are in `tests/test_native_diagnostics.py` (CI only here).
Changes for the clients: the full visual workflow now splits language/theme
variants into four jobs per platform to shorten feedback time. Each native
manifest and its `complete.json` are unchanged. Harness completion receipts are
uniquely named per variant, and composition requires all 504 exact filenames.
The fixture includes real-format Claude transcript files and an existing session
for the trajectory/member-picker views; no session or provider is launched.
The reference `plain` preference reset requested in macOS `REQUESTS.md` is fixed
using the renderer's real `relic.plain.<org>` preference. Windows capture now
includes separate native popup HWNDs by copying the real CI desktop's client
rectangle, and fails menu/mention/recipient/member-card cases if no popup opens.
Older PrintWindow-only menu captures are not acceptance evidence. Member and
recipient controls now use native Flyouts; the member's edit fields start folded.

All reference functionality is required on both systems. The draft PR cannot
leave draft until the per-function inventory is done on both, the route and
vocabulary checks pass, and both platform builds and all test suites are green.
The person's real-window acceptance remains last, after the game. Signing and
notarization remain the person's decisions. No local Python or native tests may
run while the game restriction is active.

## Window and vocabulary

The window order is **organization tree | conversation + composer | Overview /
Workspace / File**. Selection identifies `(organization ID, group or member)`.
The sidebar folds organizations; group chat precedes members. The member list
retains server display names, roles, states, secretary/leader identity and activity.
Overview presents decisions, hierarchy, current work, protocols, and episodes;
details expand without replacing the conversation. Copies is a separate sheet,
reachable beside the organization chart and Settings.

All display strings use the existing `GET /api/i18n?lang=…` response; there is no
new localization route and no forked word list. Native language menus contain
only `zh-CN` and `en-US`. Chinese system locales resolve to Simplified Chinese;
other unsupported locales resolve to English. Explicitly save the resolved
language to `/api/prefs` so server-generated states and notices match. Plural
objects select `one` only for English `n=1`, otherwise `other`. Preserve `{name}`
substitutions. Framework names and user-entered content are not translated.

## Screen/action inventory

Source anchors refer to named functions in `app/static/app.js` and the structural
elements of `app/static/index.html`. Both native clients must use the same order
of actions and server payloads below. Every row is required; there are no deferred features.

| Reference screen / action | Native controls and location | Windows | macOS |
| --- | --- | --- | --- |
| `appbar`, `menus`, `appMenu`, `shortcut`: New org, add existing/member, secretary, history, sidebar/panel, pane selection, font/density/theme, about, help | macOS menu bar/Commands; Windows MenuBar/KeyboardAccelerator; native standard edit menu for cut/copy/paste/select/undo | done | done |
| `orgTree`, `renderSide`, `setFolded`, search, recent chats | Recursive native sidebar, disclosure controls, searchable organizations and current members; unread/recent chat previews; selected group and member rows | done | done |
| `openOrg`, `go`, `renderHead`, `renderBanner` | Shared selection state; native conversation title, member state and permission/waiting banner | done | done |
| `renderStream`, `renderItem`, `renderLive`, `memberItems`, `actsBlock`, `stepRow` | Selectable native text, timestamps, notices, read-by disclosure, history pagination, tool/activity disclosure and live session items | done | done |
| `composerBox`, `toPicker`, `mentionCheck`, `quotedBody` | Native multiline editor, recipient selection and @member dispatch; persistent drafts, recipients and quotes per chat; Enter sends, Shift-Enter inserts a line | done | done |
| `permissionCard`, `decisionCard` | Native action cards; use exact permission option IDs; approve/deny structural requests; open blocked member/task | done | done |
| `renderOrgPane`, `hierarchyBlock` | Native Overview: goal, status, members, tasks/reports, protocol origins and inherited/replaced rules; parent/leader/secretariat/auto-wake and subgroup controls | done | done |
| `drawCopies`, `copyCard`, `checkRulesView`, `ackCopy`, `retireCopy` | Copies sheet, summary/author/status/statistics, expandable code/examples; Got it and confirmed Retire | done | done |
| `orgDialog` | Name → purpose → governance → create; navigate to created organization, then secretary/member setup | done | done |
| `memberDialog` App mode | Name → role → available harness → model → folder → secretary → create; open member conversation | done | done |
| `memberDialog` host mode | Name → role → Claude Code/Codex and supported surface → model/effort → folder/environment → permissions/env → start now or seat only | done | done |
| `memberDialog` existing mode | Search existing sessions by title/folder/id → session selection → seat → role → bind; preserve the complete session object | done | done |
| `openCard`, `seatAction`, `forwardDialog` | Native member detail: rename, avatar, model/effort, edit configuration, fresh/unbind/open session, forwarding, also-in memberships | done | done |
| `openSecretarySetup`, quick-start empty state | Native introductory sheet guiding organization → secretary/member → conversation | done | done |
| `openChart`, `drawChart`, `wireChart` | Native vector edges/cards with pan/zoom/fit; parent and shared-seat relationships, navigate to organization | done | done |
| `openThread`, `renderThread` | Right-pane thread with root/replies and reply composer; preserve `reply_to` | done | done |
| `renderWork`, `fileTree` | Workspace pane: member folder, branch/changes, recent edits, nested file list, system folder opener | done | done |
| `openFile`, `renderFile`, `codeView` | Native text/code/Markdown/image preview, clickable Markdown/local paths and line navigation, truncation/binary state, default-app opener | done | done |
| `requestPlain`, `togglePlainOne`, `toggleDigest`, `askSecretary` | Native plain-words toggle and digest card; async completion updates | done | done |
| `Voice`, `micButton` | Native OS speech input; explicit microphone permission on user action | done | done |
| `openDetails`, `traceView`, `reportBlock` | Native task filters/reports, documents/revisions, protocols/rules, context/trajectory pagination and requests | done | done |
| `drawProfile`, `drawAppearance`, `drawLanguage`, `drawVoice`, `drawNotify`, `drawHarness`, `drawAbout` | Native Settings; language and notification preference first; profile, appearance, voice, adapter install/path/capability and diagnostic actions | done | done |
| `installApp`, `installPage`, PWA manifest/service worker | Replaced by native package installation; no browser install screen in either native App | done | done |

`done` means the native implementation and its payload/control mapping have been
reviewed. It does not mean gate 3 (the person's real-window acceptance) has run.
CI build/test results are the separate gate 2 and must be green for this same PR
head. Source mappings: Windows `MainWindow`, `Navigation`, `SidebarCopies`,
`Conversation`, `ContentViews`, `Members`, `Organization`, `OrganizationChart`,
`FileWorkspace`, `DesktopSettings`, and `Relic.Core`; macOS exact mappings are in
[`native/macos/STATUS.md`](../native/macos/STATUS.md).

### Additional callbacks and flows

These flows are required in addition to every named function below; native
framework event callbacks replace the browser event wiring.

| Reference flow | Native implementation | Windows | macOS |
| --- | --- | --- | --- |
| Selection mouseup toolbar / quoteSelection | Selectable native message text and Copy/Quote context actions; Edit menu selection | done | done |
| Voice.supported / Voice.toggle / Voice.stop | OS speech availability, explicit start/stop, preference and permission handling | done | done |
| Voice.onresult / onerror / onend | Dictation at selection, interim/final text, microphone/network/no-speech errors, focus restoration | done | done |
| Enter / Shift-Enter / IME / mention completion | Native editor intercepts Return only outside composition/completion; Shift-Return newline | done | done |
| EventSource reopen / token rotation | Read app.json and verify the replacement lifecycle, reconnect SSE; retry an unauthenticated write only after token rejection | done | done |
| Resize pointer capture / remembered pane widths | Native split controls, separate File width, persisted visibility and dimensions | done | done |
| Hash navigation / back-forward history | Native `(org, member)` navigation stack; reveal selected organization's ancestors | done | done |
| Native install replaces PWA install / service worker | Per-user Windows installer and SwiftUI Mach-O bundle; retired browser installer returns 410 | done | done |
| Person issues protocol / inherited check rules | `/protocols` accepts weak guidance or strong JSON rules, rationale, trigger, inheritance and summary | done | done |
| Lifecycle close / beforeunload | Client-owned stdin lease and authenticated shutdown; borrowed server survives; no visible console | done | done |
| Native notification click | System notification activates Relic; copy and decision notifications retain the reference preference | done | done |

## HTTP transport and lifecycle

Base URL is strictly `http://127.0.0.1:<port>` from the readiness record. Do not
honor HTTP proxies. JSON is UTF-8. Every client request sends `X-Relic-Token`;
server writes and lifecycle verification require it. The server also validates
the Host header. URL-encode individual path/query values. Errors are JSON
`{error: string}` with a non-2xx status. Never clear drafts or show an approval as
successful before checking the response; a request decision can return HTTP 200
with `status: "failed"` and `error`, which is also a failure.

The shared `plugins/relic/scripts/native_host.py` starts the existing
`scripts/relic_app.py --serve` as a child, with `CREATE_NO_WINDOW` on Windows.
Its single stdout line is the private readiness record:
`{port, pid, token, instance, started, version, state, owned}` (state/started are
optional). A pipe held by the native process is the lifetime lease. EOF closes
only an owned child, through authenticated `/api/shutdown` before a bounded
child-process fallback. The host borrows a verified existing server and never
stops it. It never kills a PID taken from disk. Failed readiness also cleans up
the exact spawned child. Logs stay under the engine's data directory `runs`.

The server's `app.json` is under `relic_core.store.data_home()` (default `~/.relic`,
respecting `RELIC_HOME`). Verify `pid`, `port`, `instance` through `/api/lifecycle`
before use. Do not put tokens in URLs, preferences, diagnostics, or notifications.

`GET /api/events` is SSE (`text/event-stream`): comments are heartbeats; each data
frame is a JSON object. Event types include `orgs`, `org`, `live`, `decision`,
`cc`, `prefs`, `install`, `plain`, `digest`, `shutdown`. `live` includes organization,
member, item and/or status; items can update existing seq/tool IDs. Other events
invalidate corresponding snapshots. Debounce refreshes, preserve selection and
drafts, and refetch after reconnection: this stream has no durable replay cursor.
An in-flight response must not overwrite a newly selected chat.

## Route inventory: GET

`O` denotes an encoded organization ID; `M` an encoded member name. Optional
query values are shown with `?`. Both native clients implement the complete reference surface.

| Route | Request | Response shape / use |
| --- | --- | --- |
| `/api/ping` | none | `{app:"relic",version,pid}`; public discovery, not ownership |
| `/api/lifecycle` | token | `{app,version,pid,port,instance,state:"running" or "stopping"}` |
| `/api/platform` | none | OS/capability object from `platform_support.capabilities`; desktop delivery flags |
| `/api/events` | token | SSE frames described above |
| `/api/orgs` | none | `[{id,name,purpose,governance,status,parent,kind,cabinet,leader,members,…}]` |
| `/api/orgchart` | none | `{orgs:[{id,name,parent,kind,purpose,status,cabinet,governance,leader,leader_display,members,decisions,ex_officio,ended_at}],shared:[{session,harness,seats:[{org,member}]}],cabinet,secretary_general}` |
| `/api/cc` | none | `{items:[{id,org,org_name,protocol_id,title,summary,author_display,approved_display,issued_by,status,org_status,read,rules,stats,activated_at,supersedes,superseded_by,…}],unread}` |
| `/api/harnesses` | none | `[{id,title,vendor,available,program,problem,later,…}]`; show available choices and unavailable reasons |
| `/api/seat-options` | none | `{efforts,claude_modes,codex_sandboxes,claude_models}` string arrays |
| `/api/sessions` | none | `{sessions:[{id,harness,surface,title,cwd,updated,…}],problems:[string]}`; return session unchanged to bind |
| `/api/prefs` | none | prefs plus `{avatar,data,port,version}` |
| `/api/i18n` | `?lang=zh-CN` or `en-US` | `{lang,languages:[{code,name}],strings:{key:string or {one,other}}}`; native menu filters supported languages |
| `/api/avatar[/O/M]` | optional cache version | image bytes or 404 |
| `/api/fs/list` | `?path=absolute` | `{path,parent,entries:[{name,path,dir,size,mtime}],more}`; authorized roots only |
| `/api/fs/read` | `?path=absolute` | `{path,name,size,mtime,kind,text?,truncated?,url?}`; kind text/markdown/json/image/binary |
| `/api/fs/raw` | `?path=absolute` | raw bytes and MIME type; authorized roots only |
| `/api/org/O` | `?lang=` | Snapshot below |
| `/api/org/O/chat` | `?kind=group or private&member=M&limit=200&before=id` | `{items:[message or notice],more}` oldest first; replies are in threads |
| `/api/org/O/thread` | `?root=id` | `{root:message or null,replies:[message]}` |
| `/api/org/O/convo` | `?member=M` | `{steps:[…],total,…}` summarized context; missing session yields `{steps:[],total:0,missing:true}` |
| `/api/org/O/step` | `?member=M&i=index` | one full trajectory step |
| `/api/org/O/transcript` | `?member=M&limit=300&before=index&full=1` | `{steps:[…],total,…}` paged transcript or missing marker |
| `/api/org/O/document` | `?key=` | `{key,body,revision,author,at,…}` or `{missing:true}` |
| `/api/org/O/live` | `?member=M&after=seq` | `{items:[{seq,type,text,id?,title?,status?,options?,…}],status:{state,…} or null}` |
| `/api/org/O/waiting` | `?member=M` | `{waiting:[…],members:[name]}` manual reply forwarding |
| `/api/org/O/workspace` | `?member=M` | `{folder,git:{branch,root,changes},recent:[{path,tool,at}],…}` |
| `/api/org/O/member/M` | none | Member card + `{recent,config,waiting_replies}`; no seat token/session secret |

Snapshot: `{org,members,tasks,protocols,inherited_protocols,replaced_protocols,
requests,episodes,decisions,documents,chats,stamp}`. `org` includes ID/name/purpose,
governance/leader/status/auto_wake, secretary, parent/above/children/subgroups,
kind/cabinet/home/ended_at. Members have name/display/avatar/role, harness/surface
labels, model/effort and editable choices, state/detail/doing, session/agent/parent,
leader/secretary, unread/cwd, embedded/has_transcript, tasks/also_in/ex_officio.
Tasks have id/title/owner/status/evidence/report/done_at. Protocols include
id/title/strength/status/version/author/guidance/rules/trigger, votes/uses,
issued_by/downward/inherit/supersedes/retire_target/check/summary_for_person;
inherited rules add from/from_id, replaced rules add how/by/at/at_id.

Messages have `id,type,from,to,body,at,reply_to,read_by` and optional thread summary
`{count,last_at,people}`. Notices have `id:"e<seq>",type:"notice",text,at,seq`.
Decisions discriminate by `kind`: permission (id/member/title/detail/options),
approval (id/org/request/label/text/reason/status/requester/args), trajectory
(id/member/carrier/requester/reason), wake (member/error), task (id/title/member).

## Route inventory: POST

All bodies are JSON objects. `OK` below is `{ok:true}`. Preserve optional fields
when editing; do not construct a second engine or implement store mutations in
either native language.

| Route | Body | Response |
| --- | --- | --- |
| `/api/shutdown` | `{instance}` | `{stopping:true,instance}`; mismatch 409 |
| `/api/platform` | capability settings | updated capabilities |
| `/api/orgs` | `{name,purpose,governance:"leader" or "peer"}` | `{org_id}` |
| `/api/permission/id` | `{option:exact option ID}` | hub decision acknowledgement |
| `/api/prefs` | changed keys from name/lang/theme/accent/font/density/auto_names/notify/voice/paths | saved prefs; no arbitrary extra keys |
| `/api/avatar` | `{data:data-URL or "",org?,member?}` | `{avatar:URL or null}` |
| `/api/harnesses/id/install` | `{}` | `{started:bool}`; progress via install events |
| `/api/cc/id/read` | `{}` | `{id,read:true}` |
| `/api/cc/id/retire` | `{}` after confirmation | store retirement result; stops inherited rule too |
| `/api/fs/open` | `{path}` | `{opened:path}` |
| `/api/open` | `{what:"data" or "logs"}` | `{opened:path}` |
| `/api/install-window` | `{}` | 410 with native-package installation guidance; opens no window |
| `/api/org/O/send` | `{to:["all"] or member names,body,channel:"group" or "private",reply_to?}` | `{id,to:[resolved recipients]}` |
| `/api/org/O/turn` | `{member,prompt,wake_from?,wake_hop?}` | `{accepted:true}`; runner integration, not normal composer |
| `/api/org/O/members` | `{name,role,harness,model?,mode?,folder?,secretary?}` | created App-managed member / status |
| `/api/org/O/seat` | `{name,role,harness,surface,model,effort,folder,environment,permission,env,start,edit?}` | `{member,config}`; `env` is KEY=VALUE lines |
| `/api/org/O/bind` | `{session:complete session object,member,role}` | `{member}` |
| `/api/org/O/parent` | `{parent:org ID or ""}` | store hierarchy result |
| `/api/org/O/cabinet` | `{on:bool}` | store cabinet result |
| `/api/org/O/leader` | `{member}` | store leader result |
| `/api/org/O/request` | `{request_id,decision:"approve" or "deny",note?}` | request record with status; failed + error must be shown |
| `/api/org/O/close` | `{}` after confirmation | subgroup closure result |
| `/api/org/O/protocols` | protocol proposal fields: title/strength/guidance/trigger/rules/summary_for_person/downward/supersedes as applicable | protocol record, active immediately as person-issued |
| `/api/org/O/secretary` | `{member}` | OK |
| `/api/org/O/fresh` | `{member}` after confirmation | OK; preserves seat, starts a fresh session |
| `/api/org/O/open_session` | `{member}` | OK; opens external host only on explicit user action |
| `/api/org/O/unbind` | `{member}` after confirmation | OK; seat/tasks/protocols retained |
| `/api/org/O/forward` | `{member,to:[names],body}` | forwarding result or OK |
| `/api/org/O/plain` | `{ids:[message IDs]}` (max 200) | explanation results/pending; `plain` events |
| `/api/org/O/digest` | `{refresh:bool}` | digest result/pending; `digest` events |
| `/api/org/O/rename` | `{member,name}` | `{display,synced,note}` |
| `/api/org/O/model` | `{member,model,effort}` | `{model,effort,applied:"now" or "next",…}` |
| `/api/org/O/auto_wake` | `{on:bool}` | OK |
| `/api/org/O/cancel` | `{member}` | OK |
| `/api/org/O/trajectory_answer` | `{request_id,decision,note?,redact?:true}` | trajectory decision result |

## Building without opening windows

Windows (SDK 8; Visual Studio not required):

```powershell
dotnet build native/windows/Relic/Relic.csproj -c Release -p:Platform=x64
```

macOS (macOS 14+, Apple silicon, Xcode command-line tools):

```sh
swift build --package-path native/macos -c release --arch arm64
```

CI runs `dotnet test native/windows/Relic.Core.Tests/Relic.Core.Tests.csproj` and
`swift test --package-path native/macos --arch arm64`; neither test target opens
a native window. The Python suite remains in `validate.yml`, isolated from live
stores. `test_native_host.py` mocks every process/server interaction, including
the Windows creation flags. During the game, all tests run in CI only.

Developer launches (only after the game): set `RELIC_ENGINE_ROOT` to this checkout
and optionally `RELIC_PYTHON` to the Python 3.11+ executable. Production packages
locate the engine adjacent to the Windows executable or inside macOS Resources.
Do not use `dotnet run` or `swift run` for a headless build.

Official build references: [WinUI unpackaged distribution](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app),
[Swift Package targets](https://docs.swift.org/latest/documentation/packagedescription/target/).

## Full reference function inventory

Full v0.6 parity is required. No row is deferred. Each function and flow must be implemented and reviewed on both systems before the PR leaves draft. The static check deliberately fails while any cell is pending. DOM rendering helpers map to native controls, not an HTML renderer.

| Reference function | Native responsibility | Windows | macOS |
| --- | --- | --- | --- |
| `platformInfo@9` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `automaticDelivery@17` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `hostSurfaces@22` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortcutLabel@26` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortcutAction@29` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `absolutePath@46` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `inlineTokens@51` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `append@86` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `h@93` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `icon@148` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `hue@166` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `initial@172` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `dayLabel@179` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `clock@185` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortWhen@186` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `ago@191` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `stateLabel@200` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `taskLabel@204` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `pathLink@207` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `inline@211` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `rich@220` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `mdRun@245` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `quoteBlock@271` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `load@277` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `save@278` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `get@281` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadPlatform@287` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `freshToken@291` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `post@297` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `toast@305` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `lang@313` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `applyPrefs@314` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadPrefs@325` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `setPrefs@329` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `tget@343` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `targ@355` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `t@365` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `tn@369` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadLang@381` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `dname@417` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `roleName@429` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `avatar@432` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `secAvatar@446` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `groupAvatar@452` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `orgBadge@454` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `loadOrgs@460` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `readHash@470` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `writeHash@476` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `openOrg@482` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `refreshSnap@506` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `loadChat@513` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `markSeen@543` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `unreadOf@547` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `scheduleRefresh@554` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `notifyChanges@562` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `liveSlot@576` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `connect@577` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `lastLine@623` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `chatRow@629` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `orgTree@636` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `setFolded@652` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `unfoldTo@656` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderSide@662` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderMe@729` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `pushHist@736` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `goHist@744` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `toggleSide@753` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `go@759` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderAll@769` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderHead@772` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderBanner@802` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `nearBottom@821` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderStream@822` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `watchPlain@853` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `plainState@863` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `requestPlain@868` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `gotPlain@883` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `updatePlain@888` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `togglePlain@896` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `togglePlainOne@904` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `toggleDigest@910` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `loadDigest@916` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `digestCard@927` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `askSecretary@940` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `placeholder@950` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `renderItem@954` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `stripQuote@1013` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `copyText@1014` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `memberItems@1018` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `toolName@1050` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `stepArg@1051` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `actsBlock@1059` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `stepRow@1081` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `liveTurnStart@1102` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `liveItems@1109` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `renderLive@1120` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `permissionCard@1156` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `decide@1161` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `setQuote@1166` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `quotedBody@1174` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeSelBar@1181` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `micButton@1236` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `field@1242` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `composerBox@1249` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `doSend@1264` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `renderComposer@1290` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `toPicker@1312` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `mentionCheck@1331` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `pickMention@1347` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `mentionKey@1357` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeMention@1369` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeMenu@1373` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openMenu@1374` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openContextMenu@1381` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openThread@1400` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `loadThread@1405` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `closeThread@1416` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `renderThread@1417` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `panes@1436` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `setPane@1437` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `togglePanel@1444` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `applyPanelWidth@1450` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `startResize@1454` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `renderPanel@1465` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderWork@1493` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `fileTree@1540` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `fill@1543` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `openFile@1569` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `sizeLabel@1578` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderFile@1579` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `codeView@1602` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderOrgPane@1612` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `hierarchyBlock@1717` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `walk@1720` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `decisionCard@1784` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `scheduleCc@1838` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `loadCc@1839` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `openCopies@1852` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `drawCopies@1859` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `copyState@1874` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `copyCard@1881` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `checkRulesView@1905` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `issuedBy@1922` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `ruleScope@1923` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `exampleText@1933` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `plainRules@1939` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `ackCopy@1942` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `retireCopy@1951` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `closeCard@1964` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `identity@1965` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `pickImage@1972` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `openCard@1986` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `closeLayer@2081` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `scrim@2082` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `harnessList@2088` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `runModes@2094` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `runNotes@2095` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `hostKinds@2102` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `seatOptions@2105` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `memberDialog@2109` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `forwardDialog@2247` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `seatAction@2271` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `openSecretarySetup@2279` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `orgDialog@2288` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `openDetails@2310` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `render@2323` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `countTasks@2402` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `reportBlock@2405` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `traceView@2410` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `fetchMore@2427` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `draw@2434` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `sections@2454` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `openSettings@2458` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `draw@2464` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `setRow@2474` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `segControl@2477` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `toggleControl@2480` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `redraw@2485` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawProfile@2486` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawAppearance@2501` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawLanguage@2510` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawVoice@2525` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawNotify@2533` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawHarness@2545` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `onInstall@2595` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawAbout@2603` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `svgEl@2621` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `protoName@2627` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `openChart@2635` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `applyView@2665` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `clampView@2672` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `fitChart@2677` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `zoomAt@2687` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `zoomBy@2695` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `panBy@2696` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `wireChart@2702` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `loadChart@2772` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `reloadChart@2781` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `redrawChart@2786` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `drawChart@2791` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `menus@2965` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `abBtn@2966` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `renderAppbar@2970` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `openAppMenu@2995` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `menuItem@3003` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `appMenu@3011` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `focusSearch@3060` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `pasteText@3061` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `quoteSelection@3066` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `shortcutsDialog@3075` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `shortcut@3082` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `installApp@3096` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `installPage@3115` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `wire@3130` | Window initialization, quick start, native event wiring and lifecycle | done | done |

## Changes for the clients

- 2026-10-29: Final macOS integration abbb5bb is merged; REQUESTS.md now records every shared request resolved. All 34 screen/callback rows and 214 named functions are done on both platforms. At 028e270, Native apps run 40835859590 passed Windows/macOS builds, client tests, package assembly and the complete parity gate (52 routes, 686 keys, no browser UI). This final integration and its shared Python checks are revalidated by CI before PR readiness; real-window acceptance remains outstanding.


- 2026-10-29: validate.yml now cancels superseded checks per branch, matching native-apps.yml, so simultaneous push/pull_request runs do not keep two identical four-platform matrices queued. Tests still run on each latest branch/PR head.


- 2026-10-29: Implemented the final REQUESTS.md bundle metadata: shared packaging copies native/macos/Resources/Relic.icns and sets CFBundleIconFile, CFBundleDevelopmentRegion=en, CFBundleLocalizations=[en, zh-Hans]. Shared native.episodes is Episode in both lists. Windows uses the unchanged reference PNG in an ICO container. native-install.md now distinguishes macOS Close Window (keep Dock/engine, reopen) from Quit (release owned engine), versus closing the Windows window.


- 2026-10-29: Merged and reviewed native-macos 467fa95: verified credential renewal, quote-only sends, thread-send lock, speech stop and protocol payload/labels now match; their pending implementation rows are done. REQUESTS.md contains no new shared changes. Shared list templates still require macOS implementation and remain enforced by vocabulary CI.
- 2026-10-29: CI also rejects browser controls and HTML/JavaScript rendering calls in native implementation sources. Windows history uses the existing before cursor and merges pages without losing older notices or updated read receipts; expanding the initial limit alone would stop at the server's bounded history window.


- 2026-10-29: Shared panel/open_app entry points now use the same native launcher and propagate a missing native installation as an error. Updated English/Chinese README, Windows/macOS guides and source-package README to distinguish native binary installation from shared plugin installation. The WinUI SDK carries its standard optional WebView2 SDK assemblies; Relic never creates that control or starts its browser runtime. All App rendering remains native.


- 2026-10-29: Merged native-macos through 73a2c49; REQUESTS.md has no new external requests. Its split form addresses the Swift type-check timeout from run 40833893160. Full Python matrix at 258e3d8 passed (40833893150), as did the Windows build/tests/installer job (123314102495).
- 2026-10-29: Expanded vocabulary CI found list.pair/list.middle/list.end missing on both clients. Windows now uses Words.List for people, recipients, copy approvals and rule scopes. macOS owner: replace comma joins in those user-visible lists with the same shared list templates; do not exempt these keys.


- 2026-10-29: Vocabulary coverage now includes keys in ternaries and data-driven arrays, plus real dynamic translation prefixes; the original literal t(...) scan missed these. CI scanner regressions are in tests/test_native_parity.py. Add actual corresponding controls if new missing keys appear; do not add inert lists.
- 2026-10-29: Windows voice now uses Microsoft System.Speech 8.0 / desktop SAPI because Windows.Media.SpeechRecognition requires package identity, unavailable in our Inno/ZIP distribution. It uses the installed en-US or zh-CN recognizer and desktop microphone permission, never a browser. native.voice_hint is corrected; native.voice_language_missing explains the OS language-component prerequisite. See https://learn.microsoft.com/en-us/windows/apps/develop/input/speech-recognition and https://www.nuget.org/packages/System.Speech/8.0.0.
- 2026-10-29: Composer mapping correction: reference permits sending a quote without typed text, stops dictation on send, and locks against duplicate Enter submissions. Windows now does all three. macOS Model.send/sendThread currently reject empty typed text even with quote; please allow quote-only sends, lock thread sends, and stop SpeechInput on successful send/navigation. Keep the existing draft-race protection.


- 2026-10-29: Reviewed the full implementation mappings and marked corresponding rows done (gate 1 only). Gate 2 still requires CI at the latest head; gate 3 remains the person's. macOS freshToken/post/connect remain pending: Client currently stores immutable base/token and reuses them after SSE reconnect. Please reread RELIC_HOME/app.json (default ~/.relic), validate /api/lifecycle against token/pid/instance, update the transport and reconnect events. A POST may retry only the explicit 403 missing-token rejection, never an ambiguous write failure. Windows implements this with mock HTTP regression coverage.
- 2026-10-29: macOS ProtocolForm already exposes strength/rules, but still sends a supersedes field that issue_protocol_as_person ignores. Please remove that misleading input/payload and use shared native.protocol_* labels (including strength/rules/rules_hint) in the same order as Windows. Preserve summary_for_person and inherit; no new engine semantics are requested.
- 2026-10-29: Removed the Edge/Chrome/app-mode launch path. relic_app.py's normal entry launches the native executable and lets it own the server; --serve and explicit headless/lifecycle CLI operations remain. /api/install-window now returns 410 without launching anything. scripts/install.py no longer creates the old macOS shell launcher. Native discovery rejects shell wrappers. No native/macos files were edited by the shared owner.
- 2026-10-29: Merged native-macos through 081c753 and read REQUESTS.md. Requested speech metadata, platform substitutions, Enter/Shift-Enter contract and inventory updates are applied. Last full Python package matrix at 75192db passed in run 40831648376; Windows/macOS native jobs passed in run 40831648315. New changes await CI.


- 2026-10-29: Person-issued protocol form must expose both weak guidance and strong executable rules, using the existing /protocols body (strength, rules, summary_for_person, inherit). Added shared native.protocol_strength, native.protocol_rules, native.protocol_rules_hint. Windows has both modes; macOS owner should apply this contract in its form.
- 2026-10-29: Latest native build jobs at 184b381 passed on Windows/macOS (run 40830357357); parity stayed failing. Python CI found native_package.py missing explicit creationflags at the Inno compiler boundary; it now uses the shared helper, with no local execution.

- 2026-10-29: Merged main at 10b0965 (hook/console fixes); native_host.py now uses relic_core.process.creation_flags. Mock-only native-host tests assert the flags.
- 2026-10-29: Parity substitutions support platform_keys.windows/macos with individual reasons. Browser installer/speech tutorial labels are replaced by native package/OS speech flows; native controls still require real implementations. REQUESTS.md shortcut note: the raised full-reference contract retains Enter=send and Shift-Enter=newline; Cmd-Enter on macOS may be an additional alias. Do not exempt these two labels as browser-only, or change native/macos here.

- 2026-10-29: Merged native-macos through 4f95775. Its speech request is implemented: native.speech, native.speech_permission, native.microphone_permission, native.speech_unavailable are shared /api/i18n keys. Packaging writes both macOS usage-description keys and en.lproj/zh-Hans.lproj/InfoPlist.strings from those lists; native.voice_hint and native.voice_system describe Windows speech. No browser speech implementation is used.
- 2026-10-29: Applied REQUESTS.md inventory corrections: session search, unread/recent chat, persisted drafts/recipients/quotes, read-by disclosure, history paging, Markdown file/line links, rule examples and task evidence. Document payload is body. CI already runs every push; native-macos now gets its own --platform macos parity output, while native-apps requires both.
- 2026-10-29: The parity inventory gate now also rejects pending screen rows in addition to named app.js functions. No row is promoted based on key presence alone.

- 2026-10-29: Full parity replaces phased delivery. `scripts/check_native_parity.py` fails on missing reference routes, literal i18n keys, or pending function rows. Only native implementation source counts. `native/parity-allowlist.json` initially exempts only browser installation. macOS owns `native/macos/**`; requests go in its `REQUESTS.md`; report completed inventory mappings in its `STATUS.md`.
- 2026-10-29: Existing `/api/i18n` remains the vocabulary contract. Person-issued weak protocol form now sends required `rationale` and `trigger`, plus `inherit`. Four `native.protocol_*` labels were added to the shared en-US and zh-CN files.
