## A7 update: field-scoped observation for all model presentation state

432e6d2 / 41186072130 FAILS startup at 269.412 ms, 154.719 MiB, 9 threads.
The cold composer is now 32.521 ms and first identity batch 85.228 ms; failure
is inside a cold conversation row, with only two mounted rows. Message body
construction now has its own queued display turn, separate from author/avatar
controls; plain/original disclosure state lives with that body. The final text,
spacing, order and actions stay the same. Added observational layout scopes
for message columns and Markdown to distinguish native layout from admission
scope time. All pending/actual-visible-content and watchdog checks stay intact.
432e6d2 Python validation 41186072131 passes all platforms. Its Mac full-window
and adaptive captures pass; the Windows jobs 41186072111 / 41186072110 fail
full-window collection and require the shared owner to inspect their reports.

dedf7bd / 41185011711 catches a shadow-rendering regression: the broad dialog
blur becomes too light without non-linear raster composition. Restore the
original drawingGroup path for blur radii above 1 pt, retaining native layer
composition only for the small control shadows (composer/selected tabs).
The real pixel-profile test and expected colors/tolerances remain unchanged.
The same run still catches the append assertion addressed in ce1b203.

dedf7bd / 41185011763 clears startup but FAILS at action-0052:group;
maximum 280.410 ms, peak 197.141 MiB and 8 threads. The first failed work
snapshot has message-identities active and only two message rows mounted.
Its 50 composer mounts peak at 146.209 ms, while identity admission peaks
at 312.977 ms (scope durations include the yield). Reduce each identity batch
from 50 to 25, keeping the full API page, all history, and actual readiness
checks. This needs strict measurement; no timing/resource limit is changed.

0b23163 / 41184737749 finishes 299 tests with two failures in the actual
long-Markdown viewport regression: appending message 51 leaves it invisible
with a 1322 pt bottom gap. Initial latest content and the subsequent Home / new
message while reading / End checks pass. A source revision that adds no older
identity batches previously had no deferred scroll request after ForEach updated.
It now issues one cancellable request after a layout turn, respecting current
user-follow intent and the retained history anchor. The existing assertions and
strict runtime checks remain unchanged and must validate this correction.
Latest shared branch 63b688d is merged; no shared API change is requested.

3ddf641 / 41184293168 independently fails startup at 380.810 ms (134.672 MiB,
8 threads). The cold composer scope lasts 465.279 ms before any editor text or
inline command label exists, so text-measure caching cannot explain this one.
Surface shadows no longer force a drawingGroup offscreen raster; they use native
compositingGroup with the same shape, colors, radii, shadow offsets and extents.
This is a performance hypothesis requiring fresh strict measurement and visual
review; no style-test expectation or tolerance is changed. Diagnostic startup
sampling is extended from 3 to 8 seconds to include the late composer mount.
Diagnostic mode remains ineligible for acceptance and its 250 ms limit stays.

a7698a6 / 41183942102 remains a functional FAIL, despite max 221.131 ms,
201.547 MiB and 9 threads: after 61 completed actions the group viewport is
blank, with 1016 data rows and zero mounted message probes. Its retained image
confirms this; the native offset is stranded between top/bottom estimates.
The scrollPosition binding and explicit ScrollViewReader requests no longer
compete for the virtual list's anchor: explicit actual-row targets alone now
maintain initial/End placement and restore the previous first row through
each staged history insertion. Each batch settles before the next cold mount.
No direct native clip forcing or test-only repair is added. Unit/pressure and
all visible-content checks still need to validate this correction.

0fe7715 / 41183716190 passes startup and reaches action-0043 (return to the
largest group), then FAILS at 285.890 ms, 188.422 MiB, 8 threads. The active
scope is still message-identities. RichText was admitting paragraphs on its
own 32 ms timer while the shared queue admitted rows; both could invalidate
the same native layout turn. Parsed Markdown block admission now uses the
same cancellable queue as rows/panes/editor. Parsing stays on its background
actor, all text remains readable during staging, and the strict gate remains.

Source inspection found an additional concrete append bug in staged admission:
`rows.suffix(presentedRowCount)` temporarily removes the visible first row when
a message appends, until the asynchronous count catches up. Its missing identity
invalidates the native reading anchor. Admission now retains the first admitted
row's stable ID; new messages extend that range without removing existing rows.
Prepending history admits older rows in batches of 50 and does not request the
next API page until all of the existing page is admitted. The actual Home / new
message / End regression covers preserving a person's history-reading position.

7b3dbca / 41183087326 moves the cold composer below the threshold (183.980 ms
mount scope) but still FAILS during message identity admission (353.158 ms UI
max; 158.375 MiB, 9 threads). Per-turn identity admission is reduced from 200
to 50; the API pages and total retained messages are unchanged. Its mounted
test now passes initial final-paragraph visibility but fails append-following:
geometry corrections can falsely clear followsBottom. Conversation follow
intent now changes only for scoped keyboard commands and this NSScrollView's
didLiveScrollNotification (documented by Apple as user-initiated, including
legacy wheels), not lazy layout estimates. A native notification/viewport test
checks sender isolation, detachment and actual bottom distance; the mounted
long-conversation test also appends while reading history and requires no jump.
The diagnostic composer.measure identifier is renamed editor-measure so it
cannot be mistaken for a user-facing vocabulary key; word-list tests stay intact.

392c658 / 41182594829 remains a strict FAIL at 251.645 ms (143.172 MiB,
9 threads); no rounding exemption. Its composer measure cache performs four
actual measurements totaling 0.246 ms, but the enclosing cold composer mount
still takes 288.017 ms. Editor and inline command controls now enter the same
bounded native mount queue separately instead of materializing together.
All controls remain present and the readiness gate includes both mount tasks.

be19670 / 41182085087 narrows the mounted long-Markdown regression: append
and Home/End now pass, but the initial viewport is 740 pt above the bottom and
the final paragraph is absent. Initial/follow-latest anchoring now observes only
the actual last row's size as staged Markdown finishes, not the lazy document's
estimated total height. The unchanged test requires the final paragraph and new
message to actually intersect the native clip view. Strict 41182085049 still
fails startup (380.216 ms, 130.047 MiB, 9 threads); diagnostic 41182272749 reaches
action-0021 but is ineligible (298.758 ms). Its retained native stacks identify
repeated MessageColumns/Markdown child measurement during cold layout; the
composer cache is an independent reduction, not a proven fix for that stall.

00df02b / 41181961617 still fails the startup watchdog (completed maximum
565.435 ms; 151.750 MiB, 9 threads). UI-work scopes include composer mounting
and message identity admission. 41182272749 is an explicit diagnostic run to
obtain its native stack and is never acceptance eligible. Source inspection
also found MentionEditor allocating and laying out a fresh TextKit graph on
every repeated size proposal, and resetting unchanged native text attributes.
The editor now caches at most eight widths for its current text/font/paragraph
and applies attributes only when content/style changes. Tests exercise changed
drafts, resize, font scale and mutable paragraph styles. This does not establish
that the startup issue is resolved; the unchanged strict run is still required.

868e7d0's failure-window.png proves the conversation is actually blank, despite
the measured bottom gap being zero (1063 rows, no mounted message probe).
The nested vertical lazy Markdown stack is now replaced by a staged ordinary
VStack inside each virtualized message, so a message supplies actual paragraph
height to its parent. This hypothesis still needs the mounted-text test and
strict pressure run. 5b01fb9 separately fails the unchanged startup watchdog at
389.489 ms; no passing latency claim is made. Pressure captures now use the
existing CI-only CaptureDisplay, because the default 1024-wide runner silently
constrained the requested 1440x900 window. Every resize records and verifies the
actual window dimensions; no product display or sizing behavior is changed.

149dfa8 / 41180797049 exposes a real long-Markdown regression: after appending
a new message, the actual mounted native text is absent. Its stronger pressure
readiness also fails at startup (41180797022, max 203.643 ms, no visible-row
acceptance); e7af7eb has a separate 255.084 ms startup failure. Earlier partial
latency results do not prove complete visible content. End now targets the
actual last message identity, with the trailing 24 pt inside that row, instead
of an independently realized empty footer. The strict visibility and endpoint
assertions stay. 868e7d0 retains functional-failure window/probe evidence before
teardown; current fixes still await CI and must not be called accepted.

2b5f3f1 / 41180176219 completes the first 5,500-message history through real
scrolling: 23 pages, oldest ID 1, top and bottom gaps both 0 pt. It then FAILS
the second history's End-position assertion. No 250 ms violation: max 199.357 ms,
231.063 MiB, 10 threads. Native apps 41180176413 passes 297 Mac tests, including
the new actual Home-triggered HTTP paging test. Current End/send/follow actions
also bind the explicit `end` row identity so later lazy Markdown layout retains
that target. The real keyboard test now uses a fixture-scale long Markdown row.
Readiness additionally requires an actual visible conversation row for nonempty
data, and final pressure receipts retain UI-work gauges even on functional errors.

6c908a7 passes Native apps 41179607619 (296 macOS tests), four Python jobs
41179607585 and chrome 41179607550 (four bottom gaps 0 pt). Strict pressure
41179607578 no longer exceeds 250 ms: maximum 147.828 ms, 203.438 MiB, 10 threads.
It still FAILS: the strengthened history test finds that Home did not trigger
the production pager, so history and monkey coverage remain incomplete. The
pager incorrectly required the previous followsBottom state to be false even
when geometry proved the viewport was at the top. That guard is removed and
explicit Home updates following intent. A real NSHostingView + HTTP fixture
test exercises the production scroll observer without directly calling loadOlder.

34679cc passes Native apps 41178185656 (295 macOS tests), all four Python
validations 41178185542 and full-window chrome 41178185519 (bottom gap 0 pt in
all four cases). Strict pressure 41178185506 still FAILS macOS on member dialog
action-0163: 416.724 ms, 196.656 MiB, 9 threads. Windows passes in that run.
The previous 6027644 reached history before failing at 401.188 ms.

Model now uses Observation for each field while retaining EnvironmentObject
injection compatibility. Member/settings/detail form state therefore no longer
broadcasts invalidation to unrelated message/tree views. A mounted native view
test counts actual body evaluations while these dialogs change, then verifies
that a real new message still updates it. This is not yet a pressure pass.

The macOS history scenario now relies exclusively on the production scroll
observer to fetch earlier pages. The previous harness also called loadOlder
directly after Home, which could mask a broken UI pager and overlap its real
request. All history cases, first-message IDs, page sizes and watchdog limits
remain unchanged; final actual top and bottom gaps must now also be <= 2 pt.

## Shared request: restore the full-matrix contract test after diagnostic selection refactor

Resolved upstream by 8395e17; merging 959744e includes that correction.

At shared 2090f5c, Native element extraction contracts 41177925958 fails
`MatrixReportTests.test_full_matrix_requires_exact_672_cases`:
`scripts/visual/test_element_parity.py:640`, `StopIteration`. Its AST check
expects a direct assignment to `scenes` in capture.main; 69e4205 moved selection
behind the diagnostic helper. The other 982 tests pass. Please update the
structural assertion to inspect the actual default call/helper and still prove
exactly 672 full cases and the unchanged smoke matrix. Do not relax the matrix
or mark this contract non-blocking. This also blocks Native apps 41177925769.
macOS 6027644 passes its 294 tests and all four adaptive-window captures, with
actual bottom gap 0 pt in each; wide dark and narrow light images were inspected.

## A7 update: 0771470 native tests pass; resize still fails

Follow-up 6027644 / 41177719485 passes startup and every resize, then fails
action-0171 history scrolling: 401.188 ms maximum, 217.453 MiB RSS, 11 threads.
Current fix scopes history/messages/row projection to an Observable conversation
value rather than invalidating the complete Model on each 200-message page.
The real mounted conversation test now also checks a newly appended message
appears and remains at the bottom. CI still required; no full pressure pass.

Native apps 41176708889 is green at 0771470 (294 macOS tests). Strict pressure
41176708932 reaches action-0167 (1440 to 1180 width), then FAILS: 346.257 ms,
188.656 MiB peak RSS, 9 threads. No monkey phase or resource plateau was reached.
Its full-window job 41176708887 passes existing checks, but inspection found
the newest Markdown/code block clipped in the wide dark screenshot. The new
capture assertion checks the actual conversation's bottom gap, and the real
Home/End test now checks initial placement with asynchronous Markdown as well.

Current changes preserve the inspector's structural identity when it changes
between inline and overlay layout, and bind the conversation's native scroll
position to its row identity. These require fresh CI; no passing pressure
result is claimed. Shared native-apps 062dcba is included. Raw evidence remains
under `S:\Codex\Outputs\Relic-native-visual\responsiveness-0771470\macos`.

## A7 update: pressure now reaches resize; geometry invalidation fix

7d45b97 passes native builds/packages (289 macOS tests), all four Python jobs,
and complete-window chrome. Its normal pressure run 41174560185 passes startup
and every organization/chat/dialog through action-0165, then fails resize:
622.471 ms maximum, 202.781 MiB peak RSS, 9 threads, early stop. 76d842f makes
Markdown block layout lazy and waits for actual dialog presence/removal; strict
41175306371 reaches the same resize stage and fails at 250.741 ms (193.563 MiB,
9 threads). This remains a FAIL, not rounded down or excepted.

The newly mounted real Home/End test at 76d842f also catches Home leaving an
8 px top offset. 2aeca02 includes the actual top spacer in its scroll target,
without relaxing that assertion. Window size is now a nested Observable value,
so resizing notifies the views that actually read geometry rather than every
message/member/protocol through the global Model publisher. A native mounted
view test verifies this remains observable through EnvironmentObject, and a
model test verifies that a resize does not publish conversation data.

The current branch includes native-apps ecd83a1 (latest shared Windows font
preparation changes and reports). No full macOS pressure pass yet. Raw reports
remain under `S:\Codex\Outputs\Relic-native-visual\responsiveness-<commit>\macos`.

## A7 update: verified 60d07d0 build and continuing cold-layout fix

Native apps 41173774259 is green at 60d07d0 (289 macOS tests, zero failures,
both packages). Full-window chrome 41173774218 captures all four macOS cases
without errors. Both dark sizes were inspected: prepared Markdown, inspector
and traffic lights are visible. Artifacts are downloaded to
`S:\Codex\Outputs\Relic-native-visual\titlebar-60d07d0\macos`.

Strict responsiveness 41173774161 still FAILS at startup: maximum 334.410 ms,
135.938 MiB peak RSS, 8 threads, early stop. 56a32ac previously failed at
1030.851 ms, and 3a60986 at 440.148 ms. These are not full-duration comparisons.
Do not call these packages accepted. The complete API page is now admitted
in 200-identity display batches (all 1,000 initial messages remain loaded and
are mounted before capture readiness); cold native viewport/composer setup
is also split across real display turns in 360c930, pending validation.
The gate remains 250 ms, every plan action and the 180-second actual-click
phase remain required. No exception, timeout relaxation or data exclusion.

Merged native-apps 39c15ee. Its latest Windows repeat at 02b5940 is recorded
as a complete strict pass in the shared document; macOS is still incomplete.

## A7 update: dialog invalidation (2026-10-31)

The normal macOS run 41172011957 at e9df4aa reaches action-0160 Settings,
then fails at 276.840 ms; About and New organization reach 379.647 / 360.643 ms.
Peak RSS is 197 MiB, threads 9. This is an early failure, not a memory plateau
or a completed monkey pass. The independent run-loop probe agrees (377.739 ms),
so this is not merely the DispatchQueue callback being delayed while UI stays free.
The dialog presentation was a global Model publication, invalidating the whole
underlying chat. This branch now scopes it to the actual dialog overlay and
avoids publishing already-empty mention state; regression tests cover both the
notification scope and recipient dismissal. CI validation is pending.

cb02130 full-window captures (41172139399) pass both platforms; the actual
macOS dark 1024 capture was inspected and shows prepared Markdown and chrome.
Its build and strict pressure run are still pending. No passing pressure claim.
The latest shared update is merged, including the Windows repeat failure at
8d5f1ef. The earlier e346d03 passing run does not override that failure.

## 2026-10-31: Amendment 7 large-data responsiveness (current priority)

`3d9648e` full-window CI **41171394417** is green on both systems. All four Mac
captures report zero unprepared visible Markdown; wide views report one mounted
inspector. Downloaded `titlebar-3d9648e\macos` and inspected both dark sizes:
bold, inline code, fenced code, and the wide inspector are now correctly present.
Mac Native apps **41171394497** built but failed one of 285 tests: the new clipping
regression showed that AppKit `visibleRect` alone can include offscreen children.
The probe now explicitly intersects every native NSClipView (no assertion removed).
Strict **41171394443** still fails startup, **775.595 ms / 132.203 MiB / 9 threads**.
Next diagnostic records both main-dispatch and common-mode run-loop probes;
the original dispatcher result remains the gate, with the same 250 ms threshold.

05:09Z visual follow-up to `dd1ee4d`: confirmed raw Markdown in the actual dark
1024x700 full-window PNG at `b8e2195`; the green chrome check was insufficient.
`b22074f` removes the remaining initial native-clip jump, uses SwiftUI-owned
edge navigation, and waits for visible preparation. `fa6f72a` admits complex
visible rows across actual display turns through a cancellable queue, retaining
every data row. The follow-up adds actual clipped native readiness probes:
unprepared visible Markdown or a missing requested inspector now fails captures,
with counts written into `content_readiness` in the whole-window JSON. The same
readiness check is used by the unchanged strict responsiveness gate. Tests cover
cancelled row admission, off-main glyph preparation, and visible-content checks.
These fixes still require successful CI and inspection; none is claimed accepted.

`b8e2195` strict `41170186637` reduced conversation creations from 452 labels /
104 text views to 52 / 8; max **357.968 ms / 144.313 MiB / 10 threads**, still
startup failure. `60d5f1b` strict `41170738464` also failed, **457.849 ms /
130.953 MiB / 9 threads**. Its Native apps `41170738485` passed (281 tests).

Latest `f684317`: strict macOS `41169844247` still fails startup, maximum
**649.679 ms / 185.766 MiB / 8 threads**, early stop. The inspector and sidebar
are now flat lazy collections (5/6 and 10/10 current/peak appeared rows), but
native construction still reports 555 labels and 117 text views. Appeared rows
alone therefore do not establish actual view-creation bounds. The next trace
attributes native construction to its actual region. No tolerance change.
The full-window Mac capture passed in `41169844225`; all four images retained
at `S:\Codex\Outputs\Relic-native-visual\titlebar-f684317\macos`. Viewed light
1440x900 after the inspector refactor; the established visual hierarchy remains.
Shared-owner follow-up: Windows chrome at `aa1be2f` failed in `41169279678`;
its retained `Relic-titlebar-Windows/titlebar-report.json` has the per-case errors.
Mac in that workflow passed. Latest native tests/package are still running.

04:28Z: `6a444a9` builds/tests/package green (`41168489895`, 277 Mac tests).
Strict Mac run `41168489877` still fails: **774.486 ms / 196.5 MiB / 9 threads**.
The flat sidebar reports 10 mounted rows, peak 22; the 1000-message conversation
reports peak 5. This proves the view workload is bounded in that initial sample,
not that the full interaction passed. `ui-stalls.json` retains each >250 ms probe
and its actual action; startup had 285.700/254.366/256.000 ms, then action-0000
had 774.486 ms. Diagnostic `41168746001` is collecting its stack. The next change
removes zero-width paint/layout layers and production-only diagnostic hover/region
observers, while keeping actual paint, accessibility and interaction handlers.

04:21Z update: `87f7b77` Native apps `41167167998` is green (274 Mac tests,
Windows tests and packaging). Its strict Mac performance still fails at
**574.371 ms / 174.953 MiB / 8 threads** (`41167167972`). Diagnostic-only
`41167474995` retains the actual stack: after direct dictionary access, the
repeated Foundation whole-dictionary bridging hotspot is gone; SwiftUI layout
and native view creation remain. Diagnostic maximum **658.700 ms / 200.531 MiB /
10 threads**, with only early exhaustive coverage, is not acceptance. Current
`1d288de` progressively mounts all three organization panes over UI frames while
reserving their final widths. The same behavior is in production, and the
watchdog covers it; captures wait for all panes and Markdown tasks. Realized row
counts now accompany the work trace. Full-window capture `41167801377` passed.
The previous candidate failures and limits are retained; no exception requested.

Latest macOS evidence (04:01Z): strict `41166444498` at `a0cd274` still fails,
first during `startup:publish` (323.614 ms), maximum retained **1150.567 ms**,
**166.703 MiB / 9 threads**. Capture now waits for background row projection,
the production conversation view observing that version, and visible Markdown
preparation before navigating. This exposed more work than the older fixed
300 ms wait. It is not a passing result or a steady-state resource comparison.
Artifacts: `S:\Codex\Outputs\Relic-native-visual\responsiveness-a0cd274\macos`.
Diagnostic-only run `41166451889` retains 30 seconds after failure for stacks;
it is explicitly ineligible for acceptance. `0546118` adds background equality
checks so unchanged SSE responses do not republish the whole view tree, and
fixes the independent TextKit measurement regression; build/test CI is pending.
The next change preserves loaded history when clicking the current chat and
removes redundant SwiftUI end-anchor scrolls from the lazy conversation.

`572616a` full-window chrome (`41165819664`) and adaptive windows (`41165819518`)
are green on both platforms; Mac visual capture job in `41165819477` is green.
Native apps `41165819574` failed only the new TextMeasurementCacheTests (5
width assertions, out of 270 tests), so this is not a final package candidate.
All regression assertions and the 250 ms responsiveness limit remain unchanged.

The instrumented macOS **pre-optimization baseline is `6a92a00`**. It now uses
the shared `RELIC_PERF_MANIFEST` / `RELIC_PERF_OUTPUT` contract from `3af30a1`,
not the provisional visual-manifest proposal below. The baseline dispatch is
https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41162500465 . It records
all plan IDs and full earlier-history receipts, then repeats the shared seeded
deck for at least 180 seconds. One background timer posts at most one main
queue probe; the shared driver owns the unchanged 250 ms and resource limits.
The original eager conversation, repeated Markdown/date work, and quadratic
merge are deliberately unchanged in that baseline commit. Keep its actual
failed result for before/after comparison; do not rerun it from a fixed head.
Initial page size remains 1000, matching the current web client. Older pages
use the already implemented `limit=200&before=...` endpoint.

Measured baseline `41162500465` (mode baseline): startup fails at 250 ms;
worst retained dispatch delay **1986.742 ms**, peak RSS **133.281 MiB**, peak
threads **8**. The shared driver terminates after the first stall plus its
observation interval; it did not reach exhaustive/monkey completion. The
automatic run of the identical pre-fix source (`41162494417`, labelled
candidate by the push trigger) also failed startup, worst **816.036 ms**,
**133.641 MiB**, **7** threads. Preserve both as variability evidence, not as
a steady-state memory comparison. Reports downloaded under
`S:\Codex\Outputs\Relic-native-visual\responsiveness-6a92a00-baseline\macos\`
and `responsiveness-6a92a00\macos\`. First optimization is `68139d4`; CI pending.

`0891868` builds and passes the macOS Native apps job (`41163309124`) and both
full-window chrome captures (`41163309065`). Its performance run `41163309047`
still fails startup: **627.971 ms**, **134.016 MiB**, **8 threads** before early
termination; no completed monkey run yet. Its `sample` child was still
symbolicating when the shared driver killed descendants, so the stack file
was not retained. I am adding bounded in-process native-work counters to keep
useful evidence within the existing failure observation interval.

Shared Windows test fix needed: `41163309124` Windows fails compiling
`Relic.Capture.Tests`: `NativeLabelInterop.cs(16,56) CS0103 NativeLabelReadback
does not exist in the current context`. Please update that linked-source test
project when merging your diagnostic/readback changes. The macOS job is green.

`e5033b5` performance run `41164873872` gets past startup (188.634 ms maximum
through the first group action) and fails switching to the first private chat:
**305.656 ms**, **145.734 MiB**, **8 threads**. Label measurement cache reduced
recorded work from 5659 calls / 379.933 ms (`aa9d969`) to 9444 calls / 39.224 ms;
these are different early-stop windows, not equal-duration throughput claims.
The next fix preserves the existing organization snapshot across chat switches
instead of destroying/recreating its entire member tree and inspector. Pure
surface diagnostic probes are now mounted only for visual capture/XCTest;
actual outline painting and production accessibility remain active.

Confirmed macOS hot paths at `1e1fc14`: `ConversationStream` deliberately uses
an eager VStack for the complete 1000-item response; `Timeline.merge` searches
the accumulated array for every incoming item (quadratic); message Markdown
and conversation rows are recomputed during view evaluation. I will first add
a CI measurement entry point without changing those paths, publish its commit
as the macOS baseline, then optimize and run the identical fixture/interactions.

Please supply the shared large **synthetic** fixture, server/driver and workflow:
13 orgs, 5000+ main-chat messages, several 1000+ chats, 40+ members, hundreds of
tasks/events, including long/Markdown bodies. No human store data is needed.
Current `app.js` actually requests `limit=1000` and eagerly renders its response;
there is no chat before-page handler (only transcript paging at 400). Please
define the common reference/native chat page size and update that reference
contract. Proposed calls: initial `/api/org/{id}/chat?kind=group&limit=200` or
`kind=private&member={name}&limit=200`, earlier pages append `&before={id}`.
Existing response `{items: [...], more: bool}` is sufficient; keep old items
reachable on scrolling rather than silently truncating history.

Proposed macOS CI entry point: `RELIC_RESPONSIVENESS_CAPTURE=1` and
`RELIC_VISUAL_MANIFEST=<json>`, permitted only on GitHub Actions. Reuse manifest
`fixture.port/token` and `output`; add `seed` (default 17) and `duration_seconds`
(at least 180 for the seeded mouse run). It discovers every org/member using
the ordinary APIs, visits their chats, panes/dialogs/menus, resizes, and scrolls.
Output `responsiveness-report.json` with platform, duration, worst UI stall,
peak/final RSS and threads, timestamped samples, action counts and errors, plus
manifest-directory `complete.json`. A background watchdog records and fails
at >250 ms; it retains a report even if the main thread stops progressing.
Please align the exact report/resource-growth fields with Windows in
`docs/native-apps.md` early. Both platforms must use the same growth criterion.

The visual workflow already marks individual jobs continue-on-error but the
person still sees a red PR check. Please make the retained aggregate truly
report-only or fix the failure in the shared workflow, retaining its evidence.

## 2026-10-31: Amendment 6 window placement and reflow

Shared Windows capture failure at `d67957a`: all four cases exit with
`3221226107` during window construction. The retained `app-unhandled.jsonl`
reports `InvalidCastException: No such interface supported`, through
`IReadOnlyListImpl<T>.GetEnumerator -> Enumerable.Select(...).ToArray ->
ConfigureWindowPlacement`, `WindowLifecycle.cs:29`.
[Failing job](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41159185601/job/124412807319).
Please avoid the unsupported WinRT collection enumeration when collecting
DisplayAreas (use the collection's supported count/index access), then verify
the same four cases. The original receipt is downloaded under
`S:\Codex\Outputs\Relic-native-visual\window-d67957a\windows\`.

macOS is replacing the fixed SwiftUI startup size with a point-based policy:
`min(1440 x 900 pt, visibleFrame.size * 0.85)`, centred in the current screen,
an adaptive minimum, and AppKit frame autosaving/restoration. Screen changes
update constraints without converting points to physical pixels. Capture sizes
remain isolated behind the existing explicit CI capture flags.

Please retain the full-window capture driver (1440x900 and 1024x700, light/dark),
and add the Windows 150% display-scale cases where the runner supports them.
macOS continues to implement `RELIC_TITLEBAR_CAPTURE=1` with the same manifest
and completion protocol. Its per-case `.window-chrome.json` will additionally
report `initial_window_frame`, `visible_screen_frame`, `minimum_window_size`,
`inspector_overlay`, and `sidebar_width_pt`; these come from the product window
placement controller before the harness applies the requested capture size.
Keep these fields in the downloaded receipts. Put final artifacts under
`S:\Codex\Outputs\Relic-native-visual\window-<commit>\` and keep native builds,
tests, Python validation and packaging required. No server API changes needed.

At the person's 2560x1392 DIP work area, the specified fresh-launch default is
1440x900 DIP = 2160x1350 px at 150%; the minimum is 960x640 DIP = 1440x960 px.

## 2026-10-31: Amendment 5 shared validation cleanup failure

The native apps and whole-window capture pass at `f8f8704` (macOS: 248 tests,
4/4 real window captures). Shared Python validation is not yet consistently green:
[Windows Python 3.11 job](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41155754934/job/124402065105)
fails `test_runner.Runner.test_claude_session_created_then_resumed` in
`plugins/relic/tests/test_runner.py:103`, `tearDown -> self.tmp.cleanup()`.
The remaining `relic.sqlite3-wal` is held open, producing `WinError 32` then
`WinError 5`; the run ends `Ran 497 tests ... FAILED (errors=1, skipped=38)`.
Please fix the shared runner/test lifetime so outstanding background database
work has released its handles before temporary state cleanup. Investigate the
gap between `runner.is_running()` becoming false and the runner actually
finishing; do not suppress the test or treat a retry as the fix. The test already
uses `TemporaryDirectory(ignore_cleanup_errors=True)`, which did not prevent
this failure on Python 3.11. No client API change is needed. macOS cannot edit
the shared engine/tests under the agreed ownership split.

Static inspection confirms the ordering: `scripts/relic_run.py` writes the
terminal run state at the start of `finally`, then calls `Store()`,
`clear_focus`, receipts and `wake.dispatch`. `runner.is_running()` immediately
returns false for terminal status, so `Runner.turn()` can return while that
process is still using SQLite. The test should await actual runner process
completion before cleanup; preserve production receipt/wake ordering.

## 2026-10-31: Amendment 5 supersedes the strict parity gate

The person accepts the current look. Stop parity iteration and new matrix work.
Please make the retained element harness/report non-blocking, while keeping
native builds/tests, Python validation and packaging required. Merge `main`
(including PR #6 / `716ab44`) into `native-apps`; macOS will merge that branch.
Keep PR #4 open and do not install or launch locally.

macOS has committed the real transparent full-size title bar and a CI-only
`RELIC_TITLEBAR_CAPTURE=1` / `RELIC_VISUAL_MANIFEST` entry point, matching the
shared `titlebar_capture.py` driver. Its JSON uses the existing native manifest
shape: `fixture` with port/token/org/member/scene_endpoint, `lang`, `theme`,
`output`, and `cases` containing id/scene/file/width/height. Use `scene: group`,
both themes and 1440x900/1024x700. It will invoke `/usr/sbin/screencapture -x -o
-l <actual NSWindow.windowNumber> <output/file>`, preserving traffic lights and
real window chrome, and emits manifest-directory `complete.json` plus per-case
`output/<case.id>.window-chrome.json` with actual window/client bounds and scale.
Please add the shared fixture/launch workflow and upload the full-window PNGs;
the ordinary parity ImageRenderer/cacheDisplay PNGs do not satisfy this check.
The macOS package artifact remains `Relic-native-macOS-arm64-unsigned`.
Main's `716ab44` is merged into macOS at `4bafa12`. The native title-bar entry
point and capture contract are ready for the shared workflow; CI is pending.

## 2026-10-31: empty/long conversation follow-up (no new matrix work under Amendment 5)

The reference `app.js` requests `/api/org/{id}/chat?kind=group&limit=1000`
and `/api/org/{id}/chat?kind=private&member={encoded-seat}&limit=1000`
(lines 519/524). Its stream has no additional history-pagination button;
`trace.load_older` belongs to the trace dialog. macOS now uses those exact
requests and removes its extra stream button. The model transport regression
returns 250 messages in each chat type and checks the actual request and retained
history. No shared engine change is needed.

Please add `empty-group`, `empty-private`, and `long-conversation` fixture scenes
to the shared matrix and inventory. The two empty states must have neither chat
messages/transcript steps nor visible live output, and must exercise the actual
`renderStream` branch with `.notice` and `margin-top:40px`. The long conversation
must contain more than 200 messages and verify the same initial viewport and
history window on both clients. These are additional reference states, not
exclusions or accepted differences. Native capture already routes the two group
cases through the standard group selection and `empty-private` through the
standard private selection. All three still require the shared scene-reset
endpoint to acknowledge and actually prepare their data.

## 2026-10-31: actual native fill destination receipts

CI `41150748585` proved the original shadow fill's draw CGContext data pointer
equals the actual `NSBitmapImageRep.bitmapData` destination (the rejected 16-bit
replacement was removed because 121 pixels differed). The native capture now
records each original `cacheDisplay` call in `*.native-raster.json`:
`bitmaps[].native_fill_destinations[]` contains `actual_fill`,
`sequence_before_cache`, `sequence_after_cache`, `new_draw_during_cache`,
`same_destination_buffer`, and `draw_destination_bound`. Binding requires both
a new actual draw during that specific call and identical buffer addresses.
The bitmap entry records its actual view/window identities and data address.
`final_png_attribution_proven` and `occlusion_proven` remain false. The expanded
test also compares the complete observed/unobserved PNG bytes; fresh CI is pending.

Please retain these receipts in the shared fill diagnostic without promoting
them to final-pixel or occlusion proof. The remaining proof must still bind the
actual source path/clip, composition operation, layer order and screenshot pixels.
This gives that work the real draw destination rather than an inferred color match.

## 2026-10-31: measure the actual accent swatch selection (resolved in d019ebf)

The formal `312dab7` smoke report has 12 macOS selected-state mismatches
across settings-appearance and settings-navigation-hover. In the actual
reference `dom-537` is `button.swatch.on` (clay), while dom-538 through dom-542
are `button.swatch`; all six currently have `state.selected: null`.
`app.js` lines 2505-2506 bind that `on` class directly to `PREFS.accent === k`
and clicking a swatch calls setPrefs/redraw. These are visible selection states.

Please extend `scripts/visual/reference-elements.js`'s `selectable` query to
the production `.swatches>button.swatch` controls, keeping its existing actual
`classList.contains('on')` measurement. Cover the selected and unselected
swatches, an actual preference change, and unrelated noninteractive chart
legend swatches in the shared tests. No native state is to be erased and no
tolerance is to change. Evidence is in
`S:\Codex\Outputs\Relic-native-visual\parity-312dab7-smoke\reference\`
and the matching per-scene JSON under `report\`.

## 2026-10-30: digest reference scene omits the real header update (resolved in a20c0f3)

The full `dea54e8` reference scene `en-US-dark-1024x700-digest` records
`dom-164` (Digest) with class `chip-btn`, ordinary background `[37,37,35,255]`
and border `[58,57,54,255]`, while the digest card is open. This comes from
`scripts/visual/reference-hook.js`'s digest branch: it sets `S.digestOpen=true`
and calls only `renderBanner()`. The production `toggleDigest()` in app.js
calls both `renderHead()` and `renderBanner()`. Please make the reference
scene execute that real header update (or the actual click path), retaining
the deterministic digest fixture. Cover the open-card and selected-header
state together. This is a fixture-state correction, not a tolerance change;
the native production ChipButton already binds to the actual digestOpen state.
Do not change the native selected colors to reproduce a stale reference DOM.

## 2026-10-30: successful-test draw diagnostics upload

`be51e7f` / Native apps 41141825696 passes release and all 240 tests, including
the actual Avatar/container ordering regression. Please change the existing
native-macos-draw-diagnostics upload step from `if: failure()` to `if: always()`:
successful tests now retain the small surface-render-contexts.json needed to
characterize the original shadowed renderer. The bitmap fixtures are still only
written when their exact comparison fails. Until this shared CI change arrives,
the test also prints just the four actual context-format records in its log.
The real message snapshot still must verify the production ordering change.

## 2026-10-30: preserve exact call boundaries for the actual native stall

The full zh-CN-light 1280x800 artifact includes the original
`data/zh-CN/light/viewports/1280x800/native-stall.sample.{json,txt}`. Sampling
succeeded under the existing 90-second watchdog. The main thread is idle in
NSApplication's normal event loop, rather than visibly blocked in a layout
call. An HIE thread is suspended at
SOME_OTHER_THREAD_SWALLOWED_AT_LEAST_ONE_EXCEPTION; this alone does not identify
the cause. The completed scene-action receipt proves the rename input appeared,
but no native-geometry/screenshot receipt follows.

VisualCapture now writes a separate `<case>.capture-phases.json` timeline before
and after the member action, pointer settle, final layout/display, screenshot
and element extraction. It never modifies current-case.txt or resets the
watchdog. Existing timeout sampling is already sufficient on the shared side;
no deadline change or case exclusion is requested. Need the next CI sample and
phase receipt before calling this stall diagnosed or fixed.

## 2026-10-30: resumed; 239 tests green, actual snapshot still fails

`dea54e8` Native apps 41102763471 / macOS 124225131473 builds and passes all
239 tests. Package validation 41102763383 also passes. This confirms the
shadowed-fill fallback, actual search placeholder/editor, field paint switches
and exact scroll-focus getter. It does not establish element parity.

Smoke 41102763767 is downloaded to `parity-dea54e8-smoke`. Both platforms have
22 paired cases and zero accepted/strictly checked out of 672 expected.
macOS: 5523 valid native / 4913 paired; missing 46, extra 610, text 0,
geometry 554, style 6398, state 1327, kind 0, region 0, order 667, layout 2367,
icon 3, extraction 26830. Windows: 5165 valid native / 4869 paired; missing 93,
extra 296, text 632, geometry 1283, style 14582, state 708, kind 14, region 20,
order 449, layout 1851, icon 1, extraction 76845. No exceptions are accepted.

The real group snapshot still has six outgoing-message order errors. The old
isolated test used a ReferenceLabel in place of Avatar and did not cover its
actual AX container. A new mounted test uses the real Avatar and a multi-element
metadata/body card. Production avatar priority now uses its source row priority
plus 0.5, between that row's body and its date separator, rather than the same
global priority 1 for every avatar. No element sorting by reference is added.

Actual rejected `plusD` filter layers are all in the native system titlebar,
outside the captured content view. Their names are retained without interpreting
an undocumented blend name. Shadowed fills currently have no owned image, so
coverage remains unknown. Actual draw-context bit depth, alpha/bitmap info and
color space are now retained; the unchanged full-bitmap test uploads
surface-render-contexts.json to inform a pixel-preserving owned-image fix.

Full 41102763380 has a native 1280x800 timeout at member-card-rename and partial
language shards. Its unchanged report is being downloaded to `parity-dea54e8`;
the owner is investigating actual progress receipts, not extending deadlines.

## 2026-10-30: retain the actual filter identity behind rejected coverage

The actual chart PNG has the expected visible diagram, while its geometry
failures include background-pane nodes whose rectangles are covered by the
dialog. Coverage currently rejects the whole layer tree because some native
layers have compositing filters. NativeLayerOrder now retains the actual filter
string or public CIFilter.name/inputKeys, in both model and presentation layers,
alongside the existing presence flag. Names alone prove no compositing semantics
and do not remove any element or relax any condition. This provides the missing
input for deciding which actual paint operations can affect the covered area.

## 2026-10-30: exact viewport focus versus a surrounding SwiftUI focus binding

Actual `86357fe` live-tool-output has one remaining focus error: the button's
AXFocused is true and the scroll's own AXFocused is false, but the surrounding
SwiftUI FocusState is still true. The extractor had promoted that binding to
the exact scroll element. ConversationKeyboardMount now records the scope
binding separately and reads the actual scroll.isAccessibilityFocused getter
for exact focus. It retains both observations and makes no production focus
change. The mounted regression explicitly verifies that a true scope binding
does not replace a false native AX observation. This needs the next CI result.

## 2026-10-30: 86357fe formal report and passed actual mouse-hit test

Downloaded the unchanged joint report/HTML/heatmaps from 41098292475 into
`S:\Codex\Outputs\Relic-native-visual\parity-86357fe\report`, plus its visual
comparison artifact into `comparisons`. Both platforms have 22 paired cases;
strictly checked/passed remain zero out of 672 expected per platform.
macOS: 5523 valid native / 4913 paired elements; missing 46, extra 610, text 0,
geometry 642, style 6749, state 1335, kind 0, region 0, order 685, layout 2451,
icon 3, extraction 27468. The actual header badge fix removes its six group
order errors; six outgoing-message errors remain in this pre-2012515 capture.
Windows: 5124 valid native / 4868 paired; missing 94, extra 256, text 584,
geometry 1313, style 14444, state 722, kind 15, region 20, order 441,
layout 1646, icon 1, extraction 76650. No exceptions are accepted.

Native apps 41097832962 / macOS 124209643628 builds and runs 236 tests with
235 passing. Actual mouse-hit/front-control and covered-control tests now pass.
The sole failure is the already-fixed shadow bitmap comparison, whose fix is
in the subsequent production commit and still needs a new result. Some GitHub
job-state endpoints still report old queued/in-progress values even after logs
and uploaded report artifacts are available; the actual completed log provides
this test result.

For our final native search/rename cell classes only, capture now records actual
NSTextFieldCell drawsBackground/isBordered/isBezeled switches with native owner
identities. Disabled cell background/border paint supplies those properties;
shadow, outline and corner properties remain unmeasured. No generic/private cell
class is treated as known, and the field editor's background is checked. A
negative test changes the real switches and checks that absence is not supplied.

## 2026-10-30: actual 86357fe focus/badge results and observable search input

Smoke 41098292475 produced 22 macOS captures in `parity-86357fe/macos`.
The recipient button now owns actual focus; the expanded live-tool button owns
focus; new-org's ordinary name input is focused. Actual group navigation now
reads button / icon / count for both header notifications. These observations
are from the captured tree, not a matcher reorder. The final joint report is
still pending. This commit also contains the latest native-apps `215a313`.

The search placeholder was visibly rendered but had no measured foreground,
render-run font, text bounds or line configuration. Sidebar now uses an ordinary
NSTextField/NSCell with an observed read-only TextKit placeholder child and an
ObservedFieldEditor. The input retains editing, selection, IME and accessibility;
the single child label binds to its actual `relic-input/sidebar-search` owner.
No hidden replacement source or reference-derived font receipt is supplied.
The actual input height follows the reference's 14px × 1.6 line box. New mounted
CN/EN glyph/value/selection/focus tests and the same-scene capture must verify it.

Opaque diagnostics: recipients has 25 candidates (16 behind the target, 9 with
an unmeasured compositing filter); new-org has 16 (8 / 8). None is accepted as
occluded. The pointer receiver in message-hover is an actual DocumentView whose
AX hit remains a HostingScrollView; virtual child hover stays unknown. Raw
measurements remain in the artifacts. No tolerance, exception or matrix change.

## 2026-10-30: 236-test results and the shadow composition regression

Native apps 41097402930 / macOS 124209280678 (`663ced3`) builds and runs 236 tests.
Mounted banner flex/undistorted-icon tests, ordinary field-editor ownership,
message-evidence preservation, scoped message reading order with unchanged AX
inventory, and actual opaque-coverage positive/negative pixel tests all pass.
There are three failures: the two old content-hit assertions (before the newer
NSView mouse-hit fix) and one full surface bitmap comparison with dialog shadows.

Downloaded draw artifacts to `parity-663ced3/draw-diagnostics`. Exactly 107 pixels
differ at the rounded fill/border edge; the other three full-surface fixtures
match. The actual production RecordedSurface now keeps its prior AppKit native
fill path when shadows are present, while unshadowed fills retain the validated
owned image. The unchanged full-PNG equality assertion must pass again; a new
assertion also checks this renderer choice. No tolerance or scene changes.
Shadowed fills consequently retain unknown owned-image coverage; the diagnostic
does not treat the fallback as opaque proof. The actual intermediate precision
causing the edge difference has not been measured.

The passing native sort-priority test is now applied to production message rows:
actual source row order scopes priorities, with avatars before their message
contents, and date/load-older/thread/live ordering retained. Pixel layout and
accessible-element inventory still require the next real capture.

## 2026-10-30: obsolete CI work superseded; the full matrix stays required

Shared Native apps 41092324513 / macOS 124190297636 (`98841c1`) builds and runs
230 tests with only the two known content-AX-hit assertions failing. The raw
receipt confirms that the content hit returns NSWindow, while the separately
recorded window hit differs. The later actual NSView mouse-hit change still
needs its own build/tests.

At 17:23Z, cancellation was requested for our obsolete full run 41083211615
(`02df6a9`, already multiple failed shards and one cancelled macOS shard), and
our queued 41092316439 / 41091443092. Their macOS code is superseded and the
shared `98841c1` build plus 22 captures already provide the relevant evidence.
Existing artifacts remain on GitHub. Latest full and smoke runs retain every
required case; no cancelled/partial run counts as accepted and no scene is
excluded. New smoke 41098292475 and Native apps 41097832962 target `86357fe`.

## 2026-10-30: toolbar count belongs inside its real button

`98841c1` fixes the file header but exposes six header order errors: native
navigation reads each top-right count before its button/icon. IconButton's badge
was an outside overlay, a sibling of the control. It is now an overlay inside
the actual Button label and inherits that button's production parent identity.
Its position, dimensions, accessible title and count are unchanged. Actual
native hierarchy and same-scene pixel capture must verify the result; the
extractor does not sort by reference labels or coordinates.

## 2026-10-30: pointer observation distinguishes the actual AppKit mouse receiver

Actual `98841c1` message-hover shows the window AX getter stopping at a scroll
container and the content AX getter stopping at NSHostingView. Neither proves
the deepest pointer owner. NativePointerCapture now also reads the real
NSView.hitTest receiver, using that API's superview coordinate space, and asks
that actual receiver for its AX hit. Window/content/mouse hits remain separate
in the receipt. SwiftUI virtual descendants that still cannot be bound remain
unknown. The existing exact NSButton/owned-cell and covered-button negatives
are retained. No canonical hover state is inferred from these observations.

## 2026-10-30: actual file-header order fixed; message avatar order remains wrong

Downloaded 22 macOS captures from shared run 41092315894 (`98841c1`). In file-code
and file-markdown the actual native navigation order now puts header/title/path
and actions before the contents. Group still puts the outgoing avatar after
its metadata and message bubble. Its source-first Layout alone is insufficient.
An isolated mounted test now checks whether scoped row and avatar accessibility
sort priorities produce the required actual order while preserving the exact
native accessible-element inventory. No production priority change is enabled
until the test establishes both; no reference-coordinate sorting is used.

## 2026-10-30: opaque coverage diagnostics preserve all elements

New `capture_evidence.native_opaque_candidates` and the same raw AX field record
per-text-run candidates against actual NativeSurfaceFillView instances. Each
candidate requires the current exact owned CGImage in the presentation layer,
same native window, distinct front sibling branch, identical model/presentation
geometry and child order, no unmeasured transforms, masks, effects or animations,
opaque unclipped ancestry, and exact opaque source-image/final-PNG pixel equality
across the entire rectangle. Rounded transparent pixels, alpha fills, reverse
order, stale presentation and altered final pixels reject a candidate.

This is diagnostic only: `changes_visibility: false` and no emitted element is
removed or marked occluded. The mounted positive/negative tests and real SwiftUI
captures are pending CI. The shared checker must keep failing unknown occlusion;
no tolerance, exception or accepted proof shape is being changed by this work.

## 2026-10-30 shared request: current editor ownership for ordinary native fields

Actual `7ce27b4` new-org has the same visible input represented twice: the
`_SystemTextFieldCell` at window/3/2 and its `_SystemTextFieldFieldEditor` at
window/3/view-0/view-0/view-0/view-4/view-0/view-0/0. The previous receipt covered
only MemberRenameField.PaddedCell. macOS now reads the actual NSTextField,
NSTextFieldCell.controlView and NSTextField.currentEditor relationships for all
mounted native fields. Existing PaddedCell remains contract v2 unchanged.

Please extend `scripts/visual/macos_field_editor.py` and its tests for
`appkit-current-field-editor-v3`. This has every v2 identity, value, first-responder,
window, frame and selection field, plus actual native base-class observations:
`owner_is_text_field_cell: true`, `control_is_text_field: true`,
`editor_is_text_view: true`, and the actual `control_class`. The actual
`owner_class` and `editor_class` must equal the retained respective raw nodes;
all identity links, unique ownership, same window, current focus and exact value
checks remain required. No private class-name allowlist is used for v3.
Invalid, ambiguous or stale relationships retain both nodes and fail. The owner
keeps its original geometry and all editor evidence; actual children are retained.
CI includes a mounted ordinary NSTextField/currentEditor test and negative base
type checks. Its result and actual SwiftUI field capture are still pending.

## 2026-10-30: private banner follows actual native text flex widths

The macOS full `1ffe201` en-US/light/1024x700/private capture has a fixed 15px
banner icon and text at x=332; the reference icon viewport is 6.390625px and its
text starts at x=323.390625. This is an actual layout defect. BannerFlexLayout
now uses both flex-shrink bases and a native CFStringTokenizer line-break minimum
measured with CoreText from the exact production attributed text. It preserves
the text source and applies no scene-specific coordinates. The icon viewport can
shrink while its path and stroke use the SVG xMidYMid meet transform. Square
icons keep the same rendering. Mounted Chinese/English tests check actual view
frames, gap, glyph aspect ratio, stroke width and current backing-image binding.
These tests and whole-scene captures are pending CI. No gate change is requested.

## 2026-10-30: mounted dark/light painters pass; message receipts preserve other evidence

Native apps 41090924802 / macOS 124185072559 (`06890e8`) builds and runs 230 tests.
The new exact-inventory navigation-order test, all three owned-fill bitmap
fixtures, and actual Aqua/DarkAqua label/icon/fill comparisons pass. Two old
pointer assertions still fail; the subsequent content-view hit change awaits CI.
Owned fill images are now enabled, retaining their exact draw and identity checks.

The actual `7ce27b4` new-org input is focused. Recipients and live-tool disclosures
still leave the conversation viewport focused. Those two controls now explicitly
participate in native focus, with their existing focus bindings. Actual capture
must verify both the focused object and the unchanged element inventory.

MessageCaptureSession previously replaced the whole capture_evidence dictionary,
dropping independent pointer/fill/layer observations in message action scenes.
It now appends only message_action, with a regression preserving even incomplete
observations and prior extraction errors. No hover value or failed measurement
is replaced by a default. No shared change or exception is requested here.

## 2026-10-30: six hosted icon bitmaps passed; pointer owner binding still under test

Native apps 41089755638 / macOS job 124181361073 (`7ce27b4`) builds and executes
227 tests. Six actual hosted icon bitmap comparisons, source invalidation,
nonempty strokes and no-extra-child-layer assertions pass. The icon image path
is now enabled in production, with light/dark comparisons still pending the
next run. The initial multiline-editor focus test also passes.

The run has two failed pointer assertions: the chain did not contain the
NSButton objects themselves. Native buttons can expose their actual NSButtonCell
instead, so the test now accepts only that exact control or its exact owned cell
and retains the negative covered-control checks. Each assertion prints its raw
hit chain if it still fails. The capture additionally reads NSCell.controlView
identity; no hover value is synthesized and no success is claimed until rerun.

## 2026-10-30: actual accessibility navigation order, with inventory preservation

`528fcdb` completes 22 actual native captures with visible label text and current
owned-image receipts. Group now has 70 text elements with independently proven
own-outline absence. This does not cover controls or icons. Its raw regular AX
children still put the right-hand avatar after metadata and the pinned file
header after code, so those prior source/layout changes are not claimed fixed.

The AppKit bridge previously preferred accessibilityChildren and only read
accessibilityChildrenInNavigationOrder when ordinary children were empty. It now
uses actual navigation order only when it is an exact permutation of the same
object identities, with no omissions, duplicates or foreign objects. Otherwise
it retains all ordinary children. Raw selector evidence records both identity
arrays and the chosen API. This reads the platform's real linear navigation
order; it never sorts by reference text, geometry or expected order. Native
permutation/omission/duplicate/foreign-child cases run in CI. Actual SwiftUI
reading-order corrections remain pending capture.

## 2026-10-30: own image rendering uses actual effective appearance

CALayer.display does not provide NSView.draw's implicit appearance context.
All three owned painters now explicitly use their mounted view's actual
effectiveAppearance while executing the original native drawing. A new hosted
bitmap test compares old/new label, icon and fill paint in both actual Aqua and
Dark Aqua windows, and additionally requires light/dark images to differ.
This prevents equal-but-wrong theme renders from satisfying the comparison.
No theme-specific expected color or screenshot is copied into captured evidence.

## 2026-10-30: fill backing-image identity candidate, not an occlusion claim

NativeSurfaceFill now also has an isolated owned-image candidate, default false.
It retains the existing CGContext.fillPath and records the exact CGImage submitted
to its current CALayer, together with the draw/revision, frame, window, scale and
actual effective color. Three mounted SwiftUI comparisons cover light/dark,
asymmetric corners, translucent fill and surrounding shadows; original bitmap
bytes and a nonempty current fill are required. Even if these pass, compositing
order and final PNG attribution remain separate requirements: occlusion_proven
stays false and no background element is discarded by this candidate.

## 2026-10-30: icon backing-image candidate, pending hosted bitmap verification

Actual `7046f32` icon receipts still observe an NSViewBackingLayer containing a
private ContentLayer. It is not allowlisted as empty. The same explicit native
backing-image approach now has a separate icon candidate (production default
remains false). Its CALayer.display invokes the existing CGContext stroke path;
receipts bind that exact image, source revision, path draw and mounted geometry.
Six SwiftUI-hosted icon fixtures require nonempty pixels, unchanged full PNGs,
no extra native child layer, and invalidation on color change before this can
be enabled. This does not assert the containing button's own outline absence.

## 2026-10-30: production focus behavior matches the reference actions

The reference explicitly focuses the new-organization name, new-member name,
edited-member role, existing-session search and forwarded-reply editor after
opening their dialog. The native fields now perform those same initial focus
actions. The multiline editor waits for its actual window mount and consumes
the request once; later reattachment cannot steal focus back. A mounted native
responder test checks that behavior. The recipient trigger and live-tool
disclosure also request their real SwiftUI focus when activated, so their click
does not leave focus on the conversation viewport. Actual new-org, recipients
and live-tool-output focus mismatches remain pending CI verification; no state
getter is overridden to claim an expected value.

## 2026-10-30: actual pointer-hit observation, without inferred hover

The strict smoke report still contains many hovered=null failures when the real
pointer is inside the window. A new passive `native_pointer_hit` observation is
exported identically in raw AX and `elements.capture_evidence`. It reads the
frontmost actual NSWindow at the current screen point, calls its public
accessibilityHitTest, and walks actual accessibilityParent getters. Receipts
retain object identities, roles, labels, identifiers, window/root closure and
cycle status. A native overlapping-button test requires the covered button to
be absent from the hit chain and the exposed button to become the hit after
removal. This does not yet promote AX hit ancestry to CSS-equivalent hover or
replace existing onHover readings; live SwiftUI identity binding remains to be
verified from CI. No bounds-only hover or default false is synthesized.

## 2026-10-30: actual line clipping and disclosure evidence

Run 41084613768 (`7046f32`) completes all 22 macOS smoke captures. The real
live-tool-output click receipt now records y=420 both before and after expansion;
the old y=420 -> 517 jump is gone. The PNG was inspected alongside the reference.
The failure report is still retained; this is one repaired behavior, not acceptance.

In `63fc431` group, dom-383:text-0's last line is clipped at the window bottom:
the reference exports 12.6875px visible height, while macOS exported all 16.7999px
of its actual native line. Native line projection now intersects measured screen
line rectangles with the same actual NSView/ancestor/window clip already used
for its visible element bounds. `evidence.unclipped_text_bounds` preserves all
original screen lines; `evidence.text_clip` records the observed clip and keeps
occlusion_proven false. Line count is derived from surviving actual lines.
This matches the shared `text_bounds` visible-range quantity without changing
the original source line geometry, inventing a reference coordinate or changing
the 4px comparison. Partial vertical/horizontal and fully hidden line tests run
in CI. Editable native controls keep their separate existing measurements.

## 2026-10-30: hosted label-layer validation passed; production capture pending

Native apps run 41085619771, macOS job 124166161296 at `00c623b`, builds and passes
all 223 tests. The custom CALayer.display callback now actually invokes the same
TextKit painter: the isolated direct view has no extra child layer and nonempty
glyph pixels; the real SwiftUI host's full bitmap equals the previous painter;
the submitted layer image also equals AppKit's actual bitmap including Emoji.
This validates the implementation after the earlier blank regression. It is
now enabled in production; new full-page captures must still prove current
source binding and visible labels. No ContentLayer allowlist was introduced.
Final PNG attribution and the containing controls' own outline obligations
remain independent, unresolved requirements.

## 2026-10-30: owned-layer regression isolated from production (historical)

Actual `0d3d681` smoke captures from run 41078665367 completed, but show blank
ReferenceLabel text. Their actual glyph receipts are null. No bitmap success
is claimed: the earlier direct-CGContext eight-fixture success did not validate
the subsequent SwiftUI-hosted updateLayer lifecycle. `f538c9d` restores the
previous production draw path and retains the owned-layer approach only as an
explicit unit-test candidate. The original unknown ContentLayer drawing duty
therefore remains an unresolved parity failure, without any allowlist.

An additional test now mounts that candidate through the real ReferenceLabel /
NSHostingView / cacheDisplay path, requires nonempty text pixels, and compares
the full PNG against the existing painter. Candidate backing is explicitly
enabled only after its source TextKit view has been initialized. The app still
uses the previously validated drawing path until those mounted tests pass.

## 2026-10-30: live disclosure scroll and actual child ownership

Follow-up actual capture `63fc431` restores all label text but still records
the same 97px disclosure jump. Its NSClipView history shows the document grows
726 -> 823 while the clip origin moves 76 -> 173. Therefore the state-machine
change alone is insufficient. The production scroll controller now snapshots
its actual pre-click origin and restores it once after disclosure layout;
selection/content changes and explicit keyboard scrolling cancel that queued
restoration. A native NSScrollView regression exercises the real clip and a
later user navigation. The screenshot driver still sets no offset. Await CI.

The `06b914e` live-tool-output action receipt records the clicked row at screen
y=420 and the same expanded row at y=517: a 97px jump, equal to the inserted
output height. The production follow state cleared its disclosure guard after
the first size change; a subsequent TextKit pass could request bottom scrolling.
It now retains that guard until a real Model.revision/content update, and the
unit regression includes two successive layout passes before that event.
The capture driver still performs the real click and sets no matching offset.

The tool row also declares its actual parent environment for the 7px status
dot. Its measured mounted ancestry now retains that child before the title;
it must not be appended after unrelated cards. The earlier report paired this
dot with a 620px permission card. No matcher positions or reference IDs are
injected into the native hierarchy.

## 2026-10-30: actual popup fill observations now available

Consumed the shared reader contract: each observation is now obtained once
and reused unchanged in both `elements.capture_evidence.native_fill_draws`
and `ax.native_fill_draws`. Layer order is likewise emitted in both exports
from one snapshot. `CGImage.typeID` was already fixed in `cc4d1cd` and pushed;
the subsequent test run is queued, not yet passing.

`e8307ed` macOS job 124132215180 passes both NativeSurfaceFill tests, including
all four byte-identical SwiftUI/native bitmap fixtures (square, rounded and
dialog-shadow surfaces). The production dialog and action/recipient menu fills
now use that native painter. Each raw `*.ax.json` exposes `native_fill_draws`:
actual owner/region, submitted path/fill/CTM/clip, draw revision and sequence,
mounted view/window identity, current screen bounds and content coordinate
basis, native ancestry and opacity ancestry. Stale draws remain null/errors.

Shared checker request: consume these observations as actual paint evidence
when establishing popup occlusion. `occlusion_proven` intentionally stays false:
the observer still needs final-frame binding and measured compositing order
relative to each allegedly covered element. Do not suppress elements merely
because they fall inside the reference dialog or its native bounding rectangle.
No tolerance or exception change is requested.

The same AX audit now includes `native_layer_order` with actual view-to-layer
identities, roots, ordered sublayers, sibling indices, z positions, model and
presentation transforms/opacity/clipping, masks/filters/animations and contents
presence. The existing before/after geometry guard records each view's actual
`layer_order` too, so capture changes remain failures. This does not equate
NSView order with compositing order, sort children by expected visual positions,
or claim that private layer contents have known drawing duties.

## 2026-10-30: actual AX coordinate basis and glyph regression

20e61cf passes all eight unchanged glyph-image comparisons, but the mounted
plain-label test still detects AppKit ContentLayer even with the CGContext
primitive. ReferenceLabelView now uses AppKit's public wantsUpdateLayer /
makeBackingLayer / updateLayer route: actual TextKit draws into an owned sRGB
CGImage, then the view assigns that exact image to its own CALayer. Its
`native_backing_image` observation binds image/layer identity, current attributed
text, bounds/frame/window and scale to the actual glyph callback. The own-paint
checker rejects stale/unbound images. A new CI test compares the submitted
image's pixels against the original AppKit primitive, including Emoji; the
zero-extra-layer assertion remains unchanged. No ContentLayer allowlist exists.

Occlusion work is now starting from actual production paint. An opt-in
`RecordedSurface.nativeFill` candidate uses NativeSurfaceFillView's actual
CGContext.fillPath; it is NOT enabled in the application yet. CI first compares
its actual PNG against the existing SwiftUI surface, including rounded corners,
border and dialog shadows. Its retained record includes submitted local path,
actual fill/blend/global alpha, CTM/clip, draw revision/sequence, view/window
identity, current screen bounds/clip and content origin, NSView ancestry and
actual opacity ancestry. `occlusion_proven` stays false: these inputs alone do
not prove that a different native element was behind the fill in the final
frame. After bitmap validation, this will provide real dialog-fill evidence
instead of hiding AX descendants based on expected reference rectangles.

18c0b43's actual CoreText color candidate paints Emoji but differs from AppKit
in 286 pixels (actual ink bounds y=2..20 versus y=1..20). The production label
now uses the byte-identical CGContext path for outline fonts and the original
AppKit primitive for actual color fonts, selected by CTFont's color-glyph trait.
No bitmap assertion was relaxed. The receipt records which primitive actually
ran and only records submitted text-space positions for the CGContext branch.
Color-font AppKit ContentLayer evidence remains unresolved and visible to the
strict checker; this is NOT an absence claim or accepted exception. The same
mixed Emoji/Latin bitmap test continues to require byte-for-byte equality.

Please inspect two deterministic pairing errors in the actual 15581b1 report
(`41066609753`, downloaded `parity-15581b1/report`). No geometry tolerance or
exception change is requested:
* `zh-CN-light-1440x900-recipients`: reference `dom-497` and native
  `surface-paint/274` are both empty-text/empty-name menu avatars, order3,
  bounds (358,630.609375,20,20) and (358,630,20,20). They are reported as
  missing+extra instead of paired. Their actual parents are the first recipient
  row. Preserve all their style/state/extraction failures after pairing.
* `zh-CN-light-1440x900-chart`: all nine dialog cards exist in the same card
  reading order, including the header, two switch tracks, legend and its four
  samples, and canvas. Yet `dom-495` (header) pairs with `window/3/0/5`
  (first switch track), and every later card shifts by one. `dom-523` (18x12
  legend sample) pairs with `window/3/3` (1400x755 canvas); actual canvas
  `dom-527` is called missing and the native header `window/3/0` extra.
  Please retain established semantic-parent/anchor boundaries when aligning
  anonymous nodes, so equal-cost leftover sequences cannot shift an entire
  hierarchy. The actual canvas geometry is independently recorded, not a reason
  to waive its unknown style evidence or change the comparison tolerance.

The 15581b1 copies capture contains two actual accessibility regions at the
same panel bounds: a named SwiftUI AXGroup and its unnamed NSScrollView.
Content-sized dialogs now give the real NSScrollView the panel identifier and
title directly, removing the redundant production accessibility wrapper. Native
scrolling and children stay on that viewport. Fixed-height dialogs retain their
existing container. This is a production ownership fix, not a capture filter;
the next raw AX tree must confirm whether the duplicate has actually gone.

The e9206ea diagnostic images isolate the alternate glyph failure inside the
actual callback: the callback and final bitmap are both empty. TextKit supplies
user-space positions, whereas CGContext.showGlyphs(at:) consumes text-space
positions. The alternate path now inverse-maps each actual callback position
through its actual text matrix before submitting it to CoreGraphics; both the
original and submitted positions remain in the receipt. Production stays on
AppKit until the unchanged bitmap and layer tests pass. Apple API contracts:
https://developer.apple.com/documentation/coregraphics/cgcontext/showglyphs(_:at:)
https://developer.apple.com/documentation/appkit/nslayoutmanager/showcgglyphs(_:positions:count:font:textmatrix:attributes:in:)

The 19a4f92 macOS job confirms the corrected positions: Chinese/Latin,
truncation and strikethrough PNGs now equal AppKit byte for byte. The only
remaining bitmap mismatch is the omitted color Emoji (the surrounding Latin
is present). Color-font callbacks now use CTFontDrawGlyphs with the actual
substituted CTFont and the same inverse-mapped positions; outline fonts keep
the verified CGContext primitive. Production is still unchanged pending CI.
The actual list marker now supplies the requested content_screen_frame origin
by converting the current NSWindow.contentView bounds into screen coordinates.

macOS now draws unordered-list discs with NativeListMarkerView's actual
CGContext.fillEllipse, using its own primary font metrics and device-space
pixel snapping. Ordered markers keep their actual text renderer. Raw element
`evidence.native_list_marker` has source `production native disc observation`,
`current_draw` (provider, current view/window identity, revision, actual local
ellipse/device ellipse, foreground, actual font metrics, CTM and clip), plus
the actual screen bounds/ellipse and mounted native_structure. Its real AX
image retains the spoken alternative `• ` and canonical kind icon. Its visible
`text` is empty because no text glyph is painted; the actual AX name
and `alternative_text` remain `• `. This matches the new reference distinction
without deriving either side's painted geometry from its accessibility label.
Please include `file-markdown` in the diagnostic smoke matrix so the actual
native disc and the shared symbol reader receive a short feedback loop as well
as their existing full-matrix coverage. Full coverage and tolerances stay intact.
Canonical `icon` is deliberately unknown until the shared symbol-shape reader can check
the actual reference ellipse and this native receipt. Do not relabel it as a
font glyph or accept a new icon exception. The native actual-circle pixel test
checks the same 13.5px primary font's 7x19 symbol box and 5x5 painted ellipse.

New reference extraction issue found by looking at the full 1ffe201 matrix:
`zh-CN-light-1024x700-file-markdown` has three list discs. Reference
`dom-351::marker` is exported as `source: text-glyph`, glyph `• `, box
(528,285.453125,7,19), but the PNG is a larger filled disc than the native
PingFang glyph. The actual captured browser is HeadlessChrome/156.0.8078.4.
That exact Chromium tag's `core/paint/text_fragment_painter.cc` PaintSymbol
uses FillEllipse for disc, and `core/layout/list/list_marker.cc`
RelativeSymbolMarkerRect derives the actual ellipse from primary-font ascent
then the painter snaps it to pixels. It does not draw the alternative-text
bullet glyph. Please retain the generated marker's accessibility text, but
extract/validate the actual symbol paint as a shape independently; do not count
a guessed text-glyph representation as measured paint or add an icon exception.
Sources:
https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/paint/text_fragment_painter.cc
https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/layout/list/list_marker.cc
The macOS text-glyph marker visibly needs the corresponding real disc renderer;
this is still an outstanding visual mismatch, not a claimed match.

The full 1ffe201 zh-CN light shard has all168 captures downloaded under
`parity-1ffe201/full-macos-zh-CN-light` and its reference sibling. Local static
JSON pairing is saved as `full-zh-CN-light-direct-pairing.json` and explicitly
is NOT a CI gate result. Documents has119 extra native elements; many are
actually behind the opaque dialog in both PNGs. Exact opaque-layer occlusion
remains a native extraction gap, so they are retained until independently
measured native drawing order/cover evidence can establish invisibility.

Actual d74684f capture 41061971141 is downloaded under
`S:\Codex\Outputs\Relic-native-visual\parity-d74684f\report\`.
The rename element is now a single actual PaddedCell / AXTextField, named
秘书处负责人, bounds (1177,51,195,33), focused=true, selection=(0,0).
Its paired text, geometry and state mismatch lists are empty. Full matrix
acceptance is still zero and label paint still has the known regression.

The rename focus outline now uses the existing actual SurfaceView.draw
receipt instead of an unobserved SwiftUI overlay. SurfaceOutline accepts an
explicit offset; default remains -width for existing inset avatar outlines.
For a 2px outline with offset1, the actual drawing view gets 3px outside space
while the owner's surface stays unchanged. Receipts retain both actual
`local_bounds` and `local_owner_bounds`, `outline_offset`, current revision,
native transform/clip and submitted CGPath. Surface snapshots also retain
`probe_local_bounds`, `surface_local_bounds`, `outline_draw_outset`.
The native counterpart can therefore provide its actual contour; the missing
reference focus contour must remain a separate extraction failure. Tests
check actual outside ink, transparent corner/interior and unchanged owner size.

Production labels/placeholders now retain the working AppKit glyph primitive
while the alternate direct primitive is tested. This restores visible text;
the actual extra ContentLayer remains an extraction failure and the strict
mounted zero-child-layer test stays enabled. No unknown layer is allowlisted.

f0c2487 CI 41064042324 also fails: 212 tests, six failures. CTFontDrawGlyphs
still produces empty label rasters and an AppKit ContentLayer; it is NOT a
verified repair. The callback's actual clip, CTM and glyph positions are valid
in the preceding raw capture. The next candidate explicitly sets glyph fill
mode and retains every strict assertion. Current native binaries must not be
accepted while these tests fail.

Shared CI request: the macOS unit-test job should upload
`native/macos/.build/draw-diagnostics/**` with `if: failure()` and
`if-no-files-found: ignore`, artifact name `native-macos-draw-diagnostics`.
GlyphCaptureTests now saves both actual native PNGs plus their exact source
when the existing byte-equality assertion fails. These are small CI-only
diagnostics, not golden images or replacement screenshots. This is needed
because the current crash-report artifact retains nothing for ordinary
pixel assertion failures. Keep all test assertions unchanged.

d74684f now exports the requested v2 `owner_ax_frame` and
`content_screen_frame`, with the exact source strings and bottom-left AppKit
screen coordinates. Both are independent actual native API measurements;
neither is reconstructed from reference geometry or matching dimensions.
abb27ab also gives the actual rename field editor the reference caret ink and
26% accent selection tint through NSCell.setUpFieldEditorAttributes.

Native apps 41061514380 (e2bc218) builds release, but 212 tests have five
failures: the direct CGContext glyph primitive drew no ink. Four pixel equality
checks (CJK, truncation, strike-through, emoji) and the mounted nonempty-raster
test correctly caught it. The new cell AX role/focus ownership tests pass.
The correction explicitly applies the callback's actual substituted CTFont,
text matrix and existing glyph positions with CTFontDrawGlyphs. The strict
bitmap equality and no-extra-layer tests remain unchanged. New CI must prove
this correction; 942ab0e capture contains the known missing-glyph regression
and must not be accepted on the strength of successful extraction alone.

## 2026-10-30: v2 cell ownership correction from actual 2ffd371 capture

The 21-case 2ffd371 capture is complete and downloaded (41057354578):
`S:\Codex\Outputs\Relic-native-visual\parity-2ffd371\report\`.
It still accepts zero of 672. Mac 5289 raw / 5288 valid / 4656 paired elements,
4735 valid reference: missing79 extra632 text1 geometry1273 style8789 state1350
kind0 region4 order702 layout2351 icon0 extraction33042. Windows startup fails
all captured cases in this older binary; its missing4506 is not a successful
zero-mismatch result. Shared startup repair has been merged afterward.

Actual rename AX identifies the NSTextField Control as AXUnknown, while its
PaddedCell is the real AXTextField. Therefore the prior v1 Control-based alias
must NOT be accepted. 1097cdf keeps the control non-AX, assigns identifier/name
and the actual full interactive bounds to the existing native text-field cell,
and records `appkit-current-field-editor-v2`. The actual cell is owner_identity;
control_identity must equal owner_control_view_identity, control_cell_identity
must equal owner_identity, then the original actual currentEditor/window/value/
focus checks apply. The full raw editor remains under owned_editor_evidence.
The genuine native cell retains AppKit text-field accessibility behavior.
Tests require native cell label/id/frame and real editor focus transitions.

The same screenshot found the intrinsic Rename row recentered the card content
by 9px, and begin-edit notifications did not reflect initial focus. Its header
now preserves the card's allocated width while allowing the same right overflow
as the reference; actual field-editor first-responder transitions drive focus.

The recipient button anchor is now correct, but the popup's preference height
stayed zero, so its first row was y846 vs reference623.21875. 89417f8 allocates
the real fixed-height rows plus padding, capped at60vh; removes the spurious
trailing HStack gap in recipient/mention rows. All rows/controls remain present.

Direct TextKit label draw still retained an AppKit ContentLayer in 2ffd371;
no outline absence was accepted. 89417f8 now sends the actual shaped glyphs and
positions to CGContext.showGlyphs in TextKit's already-configured native graphics
state. New bitmap equality tests cover CJK/Latin/fallback, ellipsis, decoration
and emoji; the zero-extra-layer test remains strict. CI is pending, no proof
is inferred from this source change. See Apple showCGGlyphs API documentation
for its preconfigured context contract; the shared font/outline gate is unchanged.

## 2026-10-30: actual AppKit field-editor ownership and next shared assertion

9a468f8 actual capture confirms the rename microphone has its own icon-button
identity/name again; its input surface is 177x33 and still contains an extra
active `_SystemTextFieldFieldEditor` input. The later native field is 195x32.4.
c40e136 records `NSTextField.currentEditor()` for the mounted MemberRenameField
control, then projects only that editor's duplicate input representation onto
the actual owner when object identities, input roles, identifier, window,
first responder and current values are unique and consistent. The raw AX tree,
`native_field_editor` receipt and complete `owned_editor_evidence` remain.
Actual visible descendants are retained/reparented; no geometry/style/value
is copied from the editor onto the control. Missing/stale/ambiguous bindings
keep both elements and append an extraction failure. Mounted receipt tests
and nine negative binding mutations cover the rule; fresh CI remains pending.

Please independently validate `native_field_editor.contract ==
appkit-current-field-editor-v1`, native owner/editor/current-editor identities,
matching window/value/focus, and the raw retained editor in the shared macOS
reader when accepting this alias. It is a single visible native input with
an AppKit implementation editor, not an accepted extra element or exception.

New shared CI failure at 2ffd371 run 41057256619 job 124069844328:
`WindowsOutlineTests.test_exact_person_picture_parent_contract_does_not_clear_nonzero_template_brushes`
still requires text `Control container only`, whereas current evidence says
`Exact SDK PersonPicture or sealed retained-paint subclass container only; ...`.
Please update the stale wording assertion while preserving every nonzero-brush
and independent descendant paint check.

## 2026-10-30: verified input measurements and current diagnostic report

bcb9387 release compiled; 207/208 tests passed. The explicit per-line input
rectangle array now passes finite geometry, one actual line, current glyph
binding and no measurement-error assertions. Rename caret and IME tests pass.
Its sole failure: AppKit alignment outsets enlarged the styled rename field
from 195 to 199. b71af12 makes the borderless control's alignment insets zero,
preserving the original 195-width assertion. Fresh capture remains required.
1ffe201's macOS build, all 206 tests and packaging passed; its hosted AX test
now works after the real AppKit launch lifecycle, without weakening the test.

2ffd371 draws nonselectable ReferenceLabelView labels directly through their
existing TextKit manager, without NSTextView's second content drawing path.
Glyph callbacks, shaping and truncation remain the real production pipeline.
e2c5d3a adds a mounted/layer-backed test requiring actual glyph pixels and zero
extra child paint layers. No layer class is allowlisted, and TextOutlineCapture
still rejects unmeasured children/effects. Actual CI results are pending.

The dc2d96a formal diagnostic report (41053483797) is downloaded at
`S:\Codex\Outputs\Relic-native-visual\parity-dc2d96a\report\`.
All 20 Mac captures completed, still zero accepted of 672 required cases:
5039 native / 4480 valid reference / 4420 paired, missing60 extra619 text0
geometry1030 style8333 state1346 kind0 region2 order654 layout2236 icon0
extraction30381. Exceptions remain empty. Newer shared matcher direct pairing
has zero state differences for group/private; it is not a new formal full run.
The 21-case diagnostic extension and shared downloader test fix are merged.

## 2026-10-30: shared contract stale assertion after bounded downloader

Run 41055829988 job 124064563039 fails
`test_capture_viewport_shards.CaptureViewportShardTests.test_unfiltered_macos_and_reference_paths_and_deadlines_stay_unchanged`:
it still requires the removed YAML string `pattern: visual-windows-*`.
The actual compare job now uses `download_comparison_inputs.py`. Please retain
the coverage/deadline assertions and bind the artifact-path assertion to the
new downloader's exhaustive manifest contract; do not waive a capture failure.

d0d8277 release compiles; 205/206 tests pass. Its only failure remains the
unlaunched unit host's SwiftUI AX tree (-25208). 1ffe201 finishes the actual
AppKit launch lifecycle before querying, with the 100x24 assertion unchanged.
The nonfinite editable measurement is now located at `$.text_bounds.x/y`.
bf85998 explicitly constructs the per-line rectangle array and strengthens the
test to require one finite actual line rectangle and no measurement failures.

64863e7 gives Member Rename a padded native NSTextField: its entire 195x32.4
input is interactive/accessible, text/editor use the 9/35 internal insets, and
the microphone retains separate ownership. Initial focus preserves an empty
selection, and Return during IME composition does not submit. These changes
remain awaiting actual compiled/captured verification.

## 2026-10-30: recipient menu actual activation; diagnostic coverage request

The archived 72f5571 full capture places the recipients popup at the window's
top-left, not above the composer; its first row is x7/y1 vs reference x318/y623.
d0d8277 now reads the mounted native button's content bounds at actual activation,
and the `recipients` scene clicks that button instead of setting picker state.
Its scene-action receipt records actual button screen bounds and the production
content anchor. Labels keep their intrinsic widths, names include the actually
visible avatar initial with space separators, and the group avatar has its own
native owner. CI has not yet verified this change.

Please add `recipients` to the bounded diagnostic capture subset (both platforms,
same reference fixture). It remains in every full matrix case; this request adds
diagnostic coverage and removes no scene or acceptance requirement. Its physical
click and placement need a fresh artifact rather than an old model-toggle image.

The 5d4f8ea formal report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-5d4f8ea\report\` (41051920230).
It requires all 672 cases, accepts zero, exceptions empty. Mac 20 captures,
5039 native / 4480 valid reference / 4420 paired elements: missing60, extra619,
text0, geometry1030, style8373, state1378, kind0, region2, order655, layout2341,
icon0, extraction30667. No claim of full coverage or acceptance.

## 2026-10-30: editable native measurement serialization failure

dc2d96a release compiled; 201/203 tests passed. Its actual editable TextKit draw
produced a nonfinite nested native measurement, which JSONSerialization rejects.
The exporter now retains each exact native numeric spelling and JSON path in
`native_measurement_errors`, puts null in that numeric slot, and adds every such
failure to `coverage.unmeasured`. This prevents a whole capture crash without
asserting a finite measurement or accepting unknown evidence. The next test log
prints the actual failing paths for diagnosis. The other failure was the hosted
AX tree still being unmaterialized; 8c2609e adds the real capture's public AX
self-client initialization, retaining the same button box assertion.

## 2026-10-30: actual 5d4f8ea interaction and geometry verification

All 20 diagnostic Mac captures completed, downloaded with their reference files
to `parity-5d4f8ea`. The hover receipt is stable after action, before/after PNG and
after extraction: Appearance selected, Notifications hovered and unselected,
same native page contents/paint/geometry, no click or keyboard input.
Private chat first-author y now 221.0000 vs reference 221.3906 (previously 229).
Settings first segment now has actual full AX box 68x23 at x992,y211 vs reference
67.0156x23.1875 at x993.9531,y210.7969 (previously title-only 50x19).
The unit test's initial AX tree was not materialized; its unchanged 100x24
assertion now activates the same public self-process AX client as real captures.

New actual rename finding: applying the input's accessibility identifier/name
after the VoiceButton overlay overwrote the microphone with the input's name
and identifier, breaking its kind and unique surface ownership. Those modifiers
now attach to the actual TextField before the overlay. The reference's 195px
default input width vs native 177px remains a separate measured layout mismatch;
the active field editor also retains its separate raw AX node pending unique
native owner proof. Neither issue is hidden or corrected in exported geometry.

## 2026-10-30: production composer glyph measurements

Native apps c8ea3df run 41051300311 passes release compilation, tests and app
packaging. The visual gate remains failed. The next change closes the composer
input's missing actual text layout evidence: its production editor now explicitly
owns a TextKit1 NativeGlyphLayoutManager, and its placeholder is an actual
read-only TextKit child (no hit handling or separate accessible input), drawn
instead of the previous NSAttributedString convenience draw. It follows the
editor's actual padding, font, source, visible/empty state and native window.
The real input owns that label's measured glyph span and preserves its AX hit
box. Nonempty input reads its own native draw, retaining all raw spans; it only
projects a single exact source-complete span. No substitute shaped string or
reference measurements establish actual font/geometry. New mounted draw and
placeholder-to-text transition tests await CI, as do visual/IME regressions.

## 2026-10-30: actual 3934d53 draw and scroll-focus receipts

Downloaded actual 20-case smoke macOS/reference files to `parity-3934d53`.
Its new settings-navigation-hover row predates the implementation in 61e9830;
it opened the fallback About page, so capture completion is not scene acceptance.
The implemented pointer/selection guard remains required in the next capture.

Actual icon receipts now contain completed CGContext strokes and current mounted
bindings. Group icons have real measured own-outline absence; their final PNG
attribution remains separately unknown. Actual text own-outline inspection found
an AppKit ContentLayer with CATintedImage contents. Its drawing duty is unproven,
so it remains unknown; no class-name allow-list or optimistic absence was added.

The real conversation HostingScrollView now exposes its production keyboard mount
identifier, but AppKit reports enabled=false despite working scroll actions and
the SwiftUI focus/key handler. Native production now synchronizes its AX enabled
value with the same environment binding used by scrollDisabled, focusable and the
keyboard controller. Disabled keys are ignored and tested. Focus comes from the
actual SwiftUI FocusState on that viewport, with raw AX state kept separately.
`nodes[].native_keyboard_scroll` binds the unique mounted observer to the actual
scroll/window/controller, records first responder identity and both live bindings;
canonical enabled/focused use it only for that actual bound scroll object.
No focus state is supplied for unrelated regions. CI must verify this correction.

## 2026-10-30: actual 86b52e7 geometry evidence and native spacing fixes

Downloaded the formal diagnostic report plus all 19 macOS/reference captures to
`S:\Codex\Outputs\Relic-native-visual\parity-86b52e7`. Mac: 4757 native,
4263 valid reference, 4210 paired; missing 53, extra 547, text 0, geometry 1000,
style 7960, state 1200, kind 0, region 2, order 596, layout 2231, icon 0,
extraction 29250. Complete 660-case coverage at that head still fails, with zero
accepted scenes/elements and no exceptions. New matrix remains 672 required.

The private scene's date label already aligned, but every subsequent message
was 8px too low: SwiftUI added `.day` bottom margin to the next message margin
instead of the reference's collapsed maximum. Native separator spacing now
implements the same collapse for comfortable/compact/continued/notice/activity
rows, with a focused policy test and new captures required.

Actual Settings segment AX frames included only the title (e.g. 50x19 instead
of the padded 67x23 box). TextButton now applies its content shape after padding
and sizing, making the whole native button interactive. Segment paint is bound
to its actual owner identity. A mounted AX test checks the full interactive box;
no exporter bounding boxes are fabricated or enlarged to match reference values.

3934d53 compiled in release; 196/197 tests passed, including quote/draft/radio
and original-disclosure regressions. Its only failure was the same pre-fix icon
alpha assertion. The c8ea3df hover/alpha build and latest captures remain pending.

## 2026-10-30: required settings navigation hover capture and CI correction

Implemented the new `settings-navigation-hover` case without omitting prior cases.
Actual pointer movement targets the mounted unselected `notify` item; Appearance
remains selected. `.scene-action.json` and `capture_evidence.settings_navigation_action`
retain actual production hover callbacks, native input events, seven owned paint
surfaces, mounted page content identities/text/control states, pointer and geometry.
Checks run after interaction, around the PNG and after element extraction. Missing
paint/page evidence, clicks/keys, changed content/selection/geometry or lost hover
fail capture. Passive observers add no visible or interactive element. New tests
exercise actual mounted content reads and separate hover/selection bindings.

41ed54d release compilation passed; 191/192 tests passed. The sole failing icon
unit test assumed a 1.7px antialiased crossing covered a pixel completely (actual
alpha 250). Its fixture now uses the same renderer at 48px / 3.4px to sample a
fully covered center, retaining the existing strict alpha assertion. Production
rendering, element tolerances, scene coverage and exceptions are unchanged.
Static macOS parity still covers 686 keys / 52 routes / 214 flows. New CI required.

## 2026-10-30: full dark-capture text differences, quote and original disclosure

Downloaded actual 72f5571 zh-CN/dark native+reference captures (165 each) into
`parity-72f5571/full-macos-zh-CN-dark` and `full-reference-zh-CN-dark` under the
visual output directory. The static direct-pairing diagnostic has 96 text errors;
several are from session/settings/mention fixes already present after that head.
It is not a formal accepted full report, and the actual raw captures are retained.

The remaining radio errors came from using AXLabel as visible text despite the
real NSButton/NSButtonCell having an empty title and separately drawn labels.
The exporter now reads that native title for radio/checkbox text while retaining
the full AX name. The native radio and its visible labels are not removed.

Quote preview now draws the actual localized bold `composer.quoting` prefix and
the selected passage as separate attributed text spans, clamped together at three
lines. Its close icon uses the reference 14px glyph / 22px button. Optional draft
author/text fields preserve the presentation through navigation/restart; legacy
draft JSON still decodes. Existing serialized outbound quote text is unchanged.

The plain-language Original button now has its separate painted before-marker
and owned title, preserving the real full AX name and expanded state. Opening it
also uses the reference 4px gap before the original bubble. The marker retains
its actual parent/control state but is not folded into the button's visible title.
New native span, draft, radio-title and ownership regressions await CI.

74ac42c's release compile passed, but the new keyboard test fixture used `flipped`,
an inherited AppKit property name. 41ed54d renames the fixture field; no production
API or acceptance change is involved. The earlier 86b52e7 run verifies popup,
card-wrap and late-mounted-scroll regressions; its only failures are the two
already-corrected outline-test assertions. Latest-head tests remain required.

## 2026-10-30: real conversation keyboard behavior; no projected state override

The reference stream has tabindex=0, while the captured native scroll area is
not keyboard-focusable. ConversationStream now participates in SwiftUI focus,
with the reference's absent focus ring, and handles scrolling keys only while
that viewport is focused. A passive mount resolves its enclosing NSScrollView;
the handler moves that actual clip using native line/page metrics and native
bounds constraints. Typing and Command/Control/Option shortcuts are not consumed.
The production scroll view has identifier `relic-conversation-scroll` for actual
ownership. Two regressions exercise flipped/unflipped clip movement, bounds,
unhandled keys, mounted ownership and detachment. Current AX/canonical state is
not overridden: the next capture must establish the actual focus provider and
any native wrapper before the state mismatch can be considered resolved.

The 749e5e8 formal diagnostic report is now retained under
`S:\Codex\Outputs\Relic-native-visual\parity-749e5e8\report\`.
Mac captures all 19; file-code geometry errors drop 171 to 24 after actual initial
layout readiness. Total Mac geometry errors 1187, missing 58, extra 550, style
8025, state 1200, layout 2226, extraction 29240. Full 660 acceptance remains false.

## 2026-10-30: actual icon stroke receipts and corrected text-layer test assumption

The 749e5e8 Mac job 124026432050 compiles release, then runs 185 tests with two
assertion failures in one new OutlineDrawTests case. Actual AppKit supplied a
backing/presentation sublayer. The production inspector correctly kept outline
unknown, but the test incorrectly expected absence whenever a presentation layer
existed. The test now explicitly checks rejection of those actual extra layers;
the production outline contract is unchanged. Full capture still retains unknown
text outlines rather than declaring them absent. No gate exemption is requested.

The icon renderer now draws the same parsed CGPath, round caps/joins and color
in its final native NSView, replacing the SwiftUI Shape plus neighboring probe.
The actual `CGContext.strokePath` callback retains transformed path commands,
bounds, source resource, sRGB foreground, stroke parameters, revision, draw
sequence and view/window identity. Only a current source/color/bounds/window
binding supplies the canonical icon/foreground/stroke-width; stale or unmounted
draws stay unknown, with the raw previous receipt retained. Export source is
`live-CoreGraphics-icon-draw`, with `projection.current_draw`, `last_draw`,
`draw_binding_valid`, and `presentation_identity_proven: false`. The final PNG
contribution and complete layer/outline obligations remain independent. Please
consume these actual receipts in shared validation without treating them as
compositor equivalence. Pixel/selection/draw-invalidation regressions await CI.

The exact final icon view also retains `native_icon_outline`: its current draw,
focus ring, native children, model/presentation layer border, shadow, child layers,
animations, masks and filters. Only a current icon with no additional own paint
projects its own `outline: none`; no containing button receives that receipt.
Unknown presentation/child paint stays unknown. Text sublayer diagnostics now
retain actual class, delegate/content type and paint/effect fields recursively
(bounded depth, explicit truncation), with `drawing_duty_proven: false` throughout.

Also reserved the card's real 1px border inside its 340px box: content padding
is now 18+1, making its definition column 238px instead of 240px. The measured
model-note wrap difference is caused by this two-pixel width: the second `Relic`
word fit the old native first line but does not fit the reference line. A real
TextKit regression checks the two observed source ranges, 0..22 and 22..34.

## 2026-10-30: actual b63cd2f capture verifies scroll and typography geometry

macOS job 124021276290 in run 41042527320 completed all 19 diagnostic captures.
The formal report is retained at
`S:\Codex\Outputs\Relic-native-visual\parity-b63cd2f\report\`.
Actual right-pane clip y is now 0 instead of 7, with current glyph font extents;
geometry mismatches drop from 3199 to 1338 across this same diagnostic subset.
This is not full acceptance: 59 missing, 550 extra, 8036 style, 1200 state,
2225 layout and 29236 extraction errors remain, and the full 660 gate is false.
Both PNGs and actual text boxes show popup titles 10px too far left. Production
ReferencePopUpButton now pads its real title subview inside the unchanged control
and arrow, reducing the actual text container accordingly. New clipping and
selection tests require CI. No reference values or tolerances are changed.

The shared non-preempting build scheduling request below is now implemented by
902d08a and merged. Thanks; latest-head checks still must complete.

## 2026-10-30: preserve an active native build through its queued Mac job

Please consider the same non-preempting per-branch concurrency already used by
the full visual workflow for `native-apps.yml`: keep an active workflow's Mac
build/test job even if it is still queued, and replace only the next pending
workflow with the newest push. This changes scheduling only, not any check.
The actual 63aecc0 and b63cd2f native Mac jobs were cancelled before starting by
later pushes. Holding fd93174 finally produced 183 passing tests; 749e5e8 has
already passed its other three jobs while its Mac job remains queued. Preserving
that run would let both sessions keep pushing fixes without repeatedly losing
the queued compile/test feedback. Every latest-head check still must finish.

## 2026-10-30: late-mounted native scroll views must receive the production style

Full 711d27a en-US/light/1440x900/settings-harness retains an ordinary 17px
AppKit scrollbar at x1164 instead of ReferenceScroller's 10px gutter. Its
content column is consequently 629px versus the reference's 634px. The global
styling probe only ran when its own frame laid out, so a new dialog scroll view
could appear later without another probe layout. This code path is unchanged
in the newer pre-fix source.

The probe now also handles the public NSWindow.didUpdateNotification from its
own mounted window. Only missing/replaced native scrollers or changed style
properties are configured; existing instances and scroll state are retained.
Unmounting detaches the observer. A regression mounts an overflowing native
scroll view after the initial layout, uses the real window.update() API, verifies
the 10px gutter and retained scroller identity, then verifies observer detachment.
The CI geometry trace records first registration/configuration changes and
actual bounds notifications, without duplicating unchanged setup on every event.
No scrollbar extraction is filtered, and new full captures remain required.

## 2026-10-30: bounded own-outline evidence for native read-only text

`fd93174` native apps run `41043480042`, macOS job `124021988466`, now passes
release build, packaging and all 183 tests. This verifies the live CGFloat metric
projection and read-only text reflow regression. It precedes this own-outline
batch. The overall run still fails the shared menu fixture already corrected
in 000c186 and merged here; no capture or parity success follows from unit tests.

The next macOS batch measures only the own paint of the two final production
text classes, ReferenceLabelView and QuoteTextView, with their exact native
layout managers. The raw `native_text_outline` receipt retains current source
range/draw binding, focusRingType, editable/field-editor/background flags,
actual subview classes, model and presentation layer border/shadow/effect fields,
and each attribute run's attachment/shadow/stroke paint. Unmounted/stale/unknown
renderers, child paint, missing presentation observations or additional effects
remain unknown. Read-only labels/passages explicitly use focusRingType none.

Only an independently retained TextKit span can project its own absence to
`style.outline: "none"` with `evidence.outline.absence_proven: true` when all
checks succeed. A label folded into a button/avatar/tab does not provide that
owner's outline: ElementOwnership copies text properties only, and the exporter
does not promote owned_text_evidence into the owner's outline proof. Regression
tests cover this ownership boundary and rejection of focus rings/editor/children/
layer paint. The receipt explicitly does not establish final PNG contribution or
ancestor/control paint. CI verification is pending; no exception is requested.

## 2026-10-30: shared menu-identity contract regression from CI

Native apps `41042511824`, shared contracts job `124018504589`, runs 568 Python
checks and fails `test_recorded_full_identity_group_keeps_menu_region_and_actual_child`
at `scripts/visual/test_windows_elements.py:344`: actual `menu["parent"]` is None,
expected actual owner's parent `xaml-1`. This is outside macOS ownership; please
repair the real projection/fixture relationship without relaxing the gate.
The same shared failure occurs in the b63cd2f visual diagnostic contract job.

The next native capture retains `.initial-layout.json` before invoking scene
controls. In 72f5571 file-code, the first actual conversation scroll occurs after
the document has already reflowed from 824 to 634 pixels; its queued initial
bottom request therefore lands at 237 instead of completing at the original
width before opening File. The capture now flushes normal layout/display and
waits for three unchanged native scroll-geometry intervals before the action,
retaining all actual frames, clip offsets, layout flags and timestamps. It never
sets a desired offset. A timeout saves the observations and fails the case.
The existing full matrix remains unchanged. New captures must determine whether
this removes the startup/action race or exposes a production scrolling issue.

## 2026-10-30: native right-pane scroll origin has an actual AppKit caller

The successful macOS capture in `41040938552` (72f5571, 19/19) retains
`zh-CN-light-1440x900-group.native-scroll.json`. Its right pane changes from
clip origin y=0 to y=7 during actual NSTextView frame assignment:
`setFrameSize:` -> `_setFrameSize:forceScroll:` ->
`_centeredScrollRectToVisible:forceCenter:` -> `scrollRectToVisible:` ->
`NSClipView scrollToPoint:`. The first responder is CanvasFocusView, not the
read-only passage. Insets are zero. This is an unwanted dormant-selection
reveal during layout, not a seven-pixel padding requirement.

Both production read-only text subclasses now suppress automatic reveal only
while assigning their frame. Explicit scrolling and selection outside frame
assignment keep the normal NSTextView behavior. A native regression resizes
both selectable passages and static labels at several existing scroll offsets,
preserves selection, and verifies explicit scrolling still works. New CI must
verify the implementation and capture the right pane again; no measured offset
is overwritten and no tolerance is changed.

## 2026-10-30: text vertical extent now comes from actual font draw metrics

Follow-up `63aecc0`: `72f5571` release compiled, but its new test failed in the
metric projection. `XCTUnwrap(manager.lastDraw)` had succeeded; the failure is
not proof that the actual draw receipt was missing. Live callbacks retain
CGFloat font metrics/positions whereas decoded JSON contains Double values.
The projection now reads both through NSNumber, and its test unwraps before
indexing so a missing measurement reports its actual reason without a trap.
The actual CI result remains pending. Do not describe this as accepted geometry.

Full run `41029422171` compare job `124010396293` is marked failure, but its
step list ends inside the gate with uploads still pending. GitHub job logs
return BlobNotFound and the artifact list has no `Relic-native-element-parity`.
Its 660 native captures are retained in the four shard artifacts; en-US/light
capture/upload succeeded before the later browser-paint diagnostic was cancelled.
Please retain the next full report with the already-merged storage fix; there is
no newly downloadable complete report from this run to present as acceptance.

The complete `5d97933` 19-case diagnostic capture has zero direct text pairing
mismatches, but is not full-matrix acceptance. Its group code span exposes a
quantity error: native insertion geometry retained the 19.375px paragraph line
box, while the DOM text span is about 13px high per line. The actual native
`showCGGlyphs` receipts contain 11.25px Menlo ascent 10.4425048828125, descent
2.6531982421875 and baselines 13.1875 / 32.5625. These independently give a
13.095703125px font extent with the same 19.375px baseline step.

Native extraction now projects that actual typographic vertical extent with the
unchanged native insertion advance only when the exact current draw/source/view
binding is proven. `evidence.projection.native_typographic_geometry` retains each
original insertion line, callback indices, actual baselines, font metrics and
the resulting box. `text_bounds_quantity` then reads
`native-insertion-advance-and-actual-font-typographic-extent`. Original insertion
boxes, ink bounds and raw glyph callbacks are retained. Missing/stale draws,
partial source spans, transformed text or ambiguous baseline ownership do not
supply this quantity. Nothing is rounded to a reference box or matched by text.
CI tests render real two-line Menlo text, retain its original 38.75px line-box
height, verify its separate 32.470703125px typographic height, and require unchanged
PNG bytes. The API's text-matrix tx/ty are intentionally ignored as documented:
https://developer.apple.com/documentation/appkit/nslayoutmanager/showcgglyphs(_:positions:count:font:textmatrix:attributes:in:)

## 2026-10-30: scroller crash now has a concrete native stack

The crash upload in visual run `41035817459` worked. The retained
`Relic-2026-10-30-100410.ips` shows `RelicAXRole` -> AppKit
`_accessibilityUIElementSpecifierRegisterIfNeeded` ->
`accessibilityIndexOfChild` -> `ReferenceScroller.accessibilityChildren` ->
`RelicAXRole`, repeated until stack overflow. A role-only read still triggers
AppKit registration, so the earlier e5fe085 hypothesis was insufficient.
The native provider now supplies its original native child list during this
registration reentry and filters only the completed outer enumeration. Tests
retain full native thumb snapshots and repeat child-index checks. CI is still
required; no capture failure or element mismatch has been waived.

## 2026-10-30: reference CC readiness in every scene

The full `0a1d569` macOS reference quick-start PNG (en-US/light/1024x700)
has no CC badge, while the native PNG has one unread copy. The reference hook
awaits `loadOrgs()` / `openOrg()` but not `loadCc()` before creating the scene;
the native model awaits `/api/cc`. Please verify the real `/api/cc` response and
`S.cc.loaded` readiness for all cases, including quick-start, and await the
production `loadCc()` before capture if it is still pending. Retain the actual
response in the case evidence. Do not force the badge to a fixture value or
clear real unread copies solely for visual matching.

The native client now uses the response's `unread` total, as the reference does,
instead of recomputing it from the returned `items` (which can omit copies whose
organization/protocol is unavailable). Its model regression exercises a total
larger than the returned unread list. This is a production contract correction;
it does not claim the observed quick-start discrepancy is already resolved.

## 2026-10-30: retain native crash diagnostics on CI failure

Run `41032074842`, macOS job `123983931463`, release compilation succeeded but
the XCTest process exited with signal 11 in `FontShapingTests`. The log does
not contain a native stack. Please add an `if: failure()` upload of existing
`~/Library/Logs/DiagnosticReports/*.ips` and `*.crash` after the macOS test step
in `native-apps.yml`, plus the same artifact on native visual capture failure.
Do not launch a debugger or a process on the person's machine.
The line-fragment reentry hypothesis did not fix the crash (`f6c73ce` also failed).
The API error is now identified: `CTFontCopyAvailableTables` returns unboxed table
tags in CFArray pointer slots, not NSNumber objects. Native code now reads those
slots through `CFArrayGetValueAtIndex` and integer conversion; the actual
Regular/Bold draw tests remain and verify the retained table list.
Keeping the runner's actual crash report will distinguish any remaining font
API failure from text-layout recursion instead of guessing from the last log line.

## 2026-10-30: actual static-face weight receipt (shared matcher request)

The actual Menlo glyph callbacks have no `wght` axis. `font_weights.py` currently
requires that axis for every face, so even a real static font stays unresolved.
The native callback now adds `style.rendered_fonts[].weight_measurement` and the
same field in the retained `native_font_drawing.fonts` / raw callback font:

```json
{
  "version": 1,
  "source": "CTFont tables and variations of the actual showCGGlyphs font",
  "postscript_name": "Menlo-Regular",
  "available_table_tags": [1330851634],
  "variation_axes": null,
  "actual_variations": null,
  "os2_base64": "<complete actual CTFontCopyTable(OS/2) bytes>",
  "status": "measured",
  "value": 400,
  "quantity": "static-face-os2-usWeightClass"
}
```

The example table list is shortened here only; production records the complete
`CTFontCopyAvailableTables` result. Please validate the existing actual-draw /
source-span ownership first, the same PostScript identity, nonmissing table
inventory with `OS/2` and without `fvar`, no nonempty variation axes or coordinates,
and decode the retained complete table bytes (big-endian uint16 at offset 4,
valid 1...1000; known OS/2 version and at least 68 bytes). Reject corrupt,
inconsistent, variable or unbound receipts. Do not substitute OS/2 for an unknown
variable-font instance: its weight class is not adjusted by variation data.
Variable callbacks retain their actual coordinate and quantity
`actual-wght-coordinate`; absent coordinates remain unknown.

This is an additional actual measurement, not a tolerance or exception. Native
tests draw real Menlo Regular/Bold and reject variable/missing/truncated evidence.
The reference still needs its own independently bound actual-face measurement;
do not infer its weight from the native font, a family name, requested CSS weight
or a separately resolved replacement font. Final PNG attribution remains unknown
where the existing paint evidence cannot prove it.

Sources: [OpenType OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2),
[CTFontCopyTable](https://developer.apple.com/documentation/coretext/ctfontcopytable(_:_:_:)).

## 2026-10-30: live matrix consumption and shared extraction failures

`682034a` smoke run `41022654907` now has all 19 native captures with
`errors: []`, downloaded to `S:\Codex\Outputs\Relic-native-visual\parity-682034a\`.
Comparing its retained group JSON with the current matcher (diagnosis only,
not the full capture validation) confirms text mismatches **6 -> 0**, missing
**3 -> 2**, geometry **235 -> 162**. The remaining two missing elements are
the already-requested Install control/icon. No acceptance conclusion follows.
Its actual NSButton cell also appeared as a second checkbox; the production
cell is now excluded from AX and the actual parent owns the single checkbox.
Current shared scrollbar unknown geometry still makes the real native
track/thumb appear extra; native capture must not hide those painted elements.

The next native chart fixes use the reference's actually computed 1px border
(CSS requested 1.5px), expose the real native path AX name, record all legend
surfaces, and preserve the node's separately measured paint and AX extents.
The actual production checkbox owner now supplies its knob's checked/enabled
state; absent, ambiguous or cross-window ownership remains an extraction failure.

**Shared CI scheduling request:** set `jobs.macos.strategy.max-parallel: 2`
in `native-visual.yml`, retaining all four language/theme entries, all three
sizes, 55 scenes and the exact same 660-case acceptance gate. The four long
0a1d569 full jobs are running while the newer native build and diagnostic
capture wait for macOS capacity. Limiting concurrent full shards would leave
room to validate fixes while both branches continue their full matrices.
This is scheduling only; do not remove, truncate or exempt any capture.

The complete 0a1d569 diagnostic report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-0a1d569\report\` (19 cases only).
Its actual group still has missing3, extra13, text6, geometry235, style449,
state11, order65, layout141 and extraction1437. Header avatar, compound
avatar/reply names, explicit checkbox-label names and the chevron state are
now corrected in the production controls through 682034a, awaiting capture.
The newer font-weight schema adds independently required measurements, so
its aggregate style/error counts should not be treated as directly comparable
to older schema runs. All strict failures are retained.

**Actual 0a1d569 capture found two integration failures after its 152-test
green build (`41019034175`).** Smoke run `41019075828` captured all 19 macOS
cases with no capture errors. The hosted checkbox is 36x22 (a standalone
NSButton test was 32x18); `caaa834` removes the real NSButton bezel alignment
insets and adds a SwiftUI-hosted paint/hit-frame equality test. The card's
AXGroup arrives as `region` before surface kind refinement, so f9562b3 did
not update its bounds; caaa834 handles that actual transition and updates the
regression fixture. These are new runtime findings, not passing geometry.

`e5eae1d` removes an actual extra 10px message-column gap and preserves scroll
position during inspector width reflow. Reference `applyPanelWidth` does not
scroll the stream to its end. New sequence tests retain live-content following
and the actual strict <120px threshold. The new hierarchy-note regression in
8df1d5a failed because its test width omitted the real 10px scrollbar gutter;
the reference's retained owner box is **297px**, not 307px. e5eae1d corrects that
input, retaining all three reference advances and the original 0.5px tolerance.

**Full failed report downloaded:** `41011131381` / `2cb073c`,
`S:\Codex\Outputs\Relic-native-visual\parity-2cb073c\report\parity-report.json`
and all HTML/heat maps are local (1.95GB artifact). macOS raw native152916,
valid152833/invalid83, raw reference128628, valid126540/invalid2088, paired118753.
macOS missing7787, extra34080, text12880, geometry125674, style233000,
state16778, kind528, region898, order65230, layout79374, icon12, extraction808805.
Both platforms have scenes_checked=0, scenes_passed=0, matched_elements=0;
exceptions=[] and all 660 cases/platform remain mandatory. Capture completeness
is confirmed; the strict parity gate is still failing.

`1d3a643` Native apps run `41016580612` is fully green; macOS job
`123934169316` built the production app and passed **151 tests**. The corrected
real checkbox role/value/frame/press assertions and real rich-text AX range
reads all pass. The next `4086e2f` capture build caught main-actor isolation
on the new surface helper; `666b2bf` fixes it. Current queued build `0a1d569`
includes that correction, inspector note/row text, shared organization badges,
chart chip ownership and the shared font-weight quantity contract.

**Full macOS capture recovered, `2cb073c` / run `41011131381`:** downloaded
all four native artifacts to `S:\Codex\Outputs\Relic-native-visual\parity-2cb073c\`.
Each language/theme manifest records 165/165 cases, with `errors: []`;
660 actual PNGs and 660 element files are present. All three sequential viewport
processes now start and finish. The en-US/light job's subsequent browser-paint
diagnostic failed, but its native capture and upload succeeded. The comparison
job failed and its complete report is downloaded as recorded above; this is
capture completeness, not a parity pass.

`f9562b3` corrects an independently observed geometry projection: SwiftUI
AXGroup supplies inner content bounds, while the uniquely identified mounted
card surface already measures its full padding/border bounds. The native
export now uses that actual surface for card geometry and retains
`ax_content_rect` plus the surface identity/ancestry evidence. No reference
box is read by the projection. A mounted padded-card regression also rejects
an unrelated owner with identical geometry. Fresh CI is required.

`da54b3c` Native apps run `41014596650`, job `123927946212`, compiled the
production app and ran 150 tests. Four assertions in the new checkbox test
failed: the custom empty NSButtonCell supplied AXUnknown, a 30x16 interior
frame and no checkbox value. `717d2d3` implements the actual NSButton's AX
checkbox role, native state, full mounted hit frame and enabled press action.
The 32x18 and checked/disabled assertions are unchanged; fresh CI is required.

Correction to the Windows vocabulary request below: the shared owner traced
the four keys to the reference's actual `if (isMac())` desktop-connection UI.
They are used by macOS; no dead Windows references or new Windows UI should be
added for those macOS-only controls. The platform-guarded source inventory
needs its own accurate measurement, without excluding any captured scene.


**Requested-vs-resolved font weight remains a shared measurement issue.**
`a3ca2a3` group reference bold has computed CSS weight 700 but CDP reports
`PingFangSC-Semibold`; the native actual callback uses that same face with
`wght=600`. Geometry now matches (171.36 / 171.375). Native text now retains
`evidence.projection.native_font_weight_configuration` from the actual rendered
attributed input, separately from its unchanged canonical resolved weight and
actual callback variations. This supplies the missing quantity distinction;
it is not an exception and does not waive a style error. Please keep both
configured and actual-face quantities when completing the reference schema;
do not treat computed CSS 700 as measured resolved font-axis 700.


**Fresh shared CI evidence:** `7df43bd` run `41013183162`, macOS job
`123923528659`, passed release build and **148 tests**. The rich-source-span
test passed the exact PNG equality checks against the unsplit draw and
capture-disabled draw. Native actual font projection still does not assert
final-window glyph contribution. The same run's parity failure is Windows-only:
missing `settings.claude_desktop_hint`, `settings.desktop_connections`,
`settings.desktop_probe`, `settings.desktop_probe_hint`; macOS lists are empty.
This earlier Windows-controls request is superseded by the platform-guard
source finding above; do not add nonexistent Windows controls.


**a3ca2a3 actual diagnostic follow-up:** downloaded macOS/reference/HTML/JSON
to `S:\Codex\Outputs\Relic-native-visual\parity-a3ca2a3\`. All 19 native cases
captured; actual sidebar order now includes each avatar and dot before its name.
macOS missing 155, extra 723, text 477, geometry 3279, style 7990, state 1279,
kind 9, region 28, order 1323, layout 2948, icon 0, extraction 31240. Both
platforms still have zero accepted scenes under the full 660-case gate.

`41b68f4` macOS run `41012301431`, job `123920672083`, passed release build
and **147 tests**. Actual Chinese bold advance is 171.36 vs reference 171.375;
the unchanged English bold assertion also passes (292.4191 vs 292.40625).

The actual captures still report a 257px AX checkbox for a painted 32px track:
SwiftUI's accessibility representation inherits the entire outer Toggle row.
The macOS production switch now uses a real fixed-size NSButton checkbox with
the same SwiftUI track/knob paint and an independent visible native text label.
AX geometry, click/checked and disabled-state tests cover the real NSButton;
new capture must validate it. This replaces the faulty representation rather
than overriding exported bounds with expected values.


`2cb073c` macOS Native apps job `123917017688` (run `41011131346`) passed
release build and all **143 tests**. The unchanged six-point dialog shadow
test now passes after the raster-outset fix. Actual `27e39b3` window PNGs
also retain the shadow outside the card; artifacts are downloaded locally.

New rich-text font evidence is being tested against actual native drawing:
the production layout manager draws its already-shaped glyphs per attributed
range, keeping overlapping glyph clusters indivisible. Each actual callback
now retains the source range of that invocation. Font projection requires an
exact cover by completed calls; arbitrary substrings remain unknown. No
re-shaping or reference font data supplies actual fonts. The new bitmap test
compares this production draw with an unsplit TextKit draw, and compares
capture enabled/disabled. Final PNG attribution is still explicitly unproven.


**bbe04a3 diagnostic results, 2026-10-30:** all 19 native cases captured,
including the loaded member-card rename action and Copy continuity. The group
composer's actual native AX bounds now equal the reference's 758x26 viewport.
Artifacts and failed HTML/JSON reports are at
`S:\Codex\Outputs\Relic-native-visual\parity-bbe04a3\`. This is diagnostic only;
the 660-case gate still accepts zero scenes. The macOS input contains 4827
native elements / 4327 raw reference elements; missing 219, extra 787, text 455,
geometry 3674, style 8120, state 1264, kind 9, region 28, order 2257, layout 2887,
icon 0, extraction errors 31175. No exception or tolerance change.

Actual ignored avatar/dot/card surfaces still arrive in weak-registry order
after the AX tree. The macOS inspector now retains their production parent
environment and mounted `NSView.subviews` ancestry. It restores children only
for a unique real parent with measured paths; it preserves the raw extraction,
unknown/ambiguous ownership and all measured geometry. This does not sort by
reference coordinates/text or manufacture missing controls. Sidebar rows,
organization rows and the profile own their actual child records; native
ancestry/reordering regressions run in CI. New full capture is still required.

The `129ad45` production release compiled; test compilation exposed one stale
font-diagnostic API reference. `055a8fa` corrects the test without changing
assertions. Consumed shared `38d6cff` startup sampling and `27e39b3` diagnostics.


**Actual full-shard startup failure, `afe7f6f` / `41004901717`:** zh-CN/light
job `123897519335` completes the first 55-case viewport, then the 1280x800
process (PID 29604) writes no client log/progress and times out at 1200 seconds;
1024x700 likewise writes nothing before the unchanged 45-minute job deadline.
Downloaded evidence: `parity-afe7f6f/macos-zh-CN-light/data/zh-CN/light/viewports`.
This is a startup failure, not slow successful cases. macOS previously started
capture only from the ordinary Window's `.task`; a later process may restore
that window as closed. Capture now starts from `applicationDidFinishLaunching`
and owns its own model/window regardless of ordinary-window restoration, with
an immediate startup log/progress marker. Full multi-process validation is pending.

Shared request: `native_process` currently creates `current-case.txt` before
launch only for Windows. Please initialize a startup marker for macOS too so a
process that never reaches our app lifecycle triggers the existing 90-second
progress deadline and stack sampling, rather than waiting 1200 seconds without
startup evidence. Preserve all process/case/job deadlines, all 165 cases in
each language/theme and the existing failed-shard aggregation.

`edb98f3` smoke `41005480198` completes all 19 macOS captures; its actual new
PNG reveals a shadow regression: the non-linear drawingGroup clips all paint
outside its layout bounds. At the member-card left edge the native samples at
offsets 1/4/8/16/24/40 are all white; reference red channels are 234/240/244/250/
253/255. The shape-only raster group now receives padding derived from its own
blur radii and offsets, followed by equal negative layout padding, so the card
retains its original size and the actual shadow has room to render. The strict
reference edge-profile test remains unchanged and must pass in CI. The failed
edb98f3 images/report are retained under `parity-edb98f3`; no evidence is replaced.

The overview toggle previously exposed its entire 257px switch-and-label row
as one checkbox while the reference has a 32px control, separate visible text
and a 14px knob. The production SwiftUI style now scopes its native checkbox
representation to the actual 32x18 switch, preserves the visible label beside
it and allows label clicks only while enabled. The knob is an independently
painted/owned card with the unchanged 14px/white/1px shadow parameters. Hidden
labels in settings likewise keep the switch frame. Toggle canonical text is
empty because its actual visible label is now a separate native text element;
its accessible name/checked state remain on the real toggle. Capture pending.

Consumed `74b14eb` evidence-shape follow-up: macOS retains the original native
line-break properties under `raw`, with `source`, actual `owner`, and
`applicable:true` for `bool(text) || kind == "text"`. Non-text elements emit
version 1/null strategies/false applicability and a reason. Text controls with
no measured paragraph/container configuration retain explicit errors and null
strategies; the required shape is not used to disguise missing measurements.

New `597e113` smoke artifacts are downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-597e113\{macos,reference,report}`.
18/19 native cases are captured; Copy is completed and continuity observed
through `after-native-source-and-element-extraction`. The one failure is rename:
client.log records a click at window x=1194, but the loaded card's actual rename
button center is x=1389. The capture clicked the pre-load layout. It now waits
for the real card AX identity derived from the fetched member name, flushes
layout and dispatches exactly one action; the attempted target/result is saved
even on failure. The existing bounded API-readiness deadline is used; no scene
or failed assertion is excluded and no second click is used to hide failure.

Actual antialiasing verification: the same 1440 group message, measured from
its actual text rectangle, has native red-channel ink coverage 2065.15 versus
reference 2068.80 in 597e113. The old 56253c7 capture measured 2444.42 versus
2068.80. This confirms the observed excess ink was reduced for that paragraph,
not whole-font or whole-matrix equivalence. Both current reports still fail.

The real macOS popup AX element is `ReferencePopUpCell`, not its backing
`ReferencePopUpButton`. Captured cells had empty field names/identifiers and
only their 22px interior frame. The production control now assigns its actual
localized field name/identifier to the cell, so its existing border probe can
bind to that real owner. Extraction reads the cell's actual selected AX value
and native attributed title/font. The new regression changes selection on the
actual AppKit cell and reads the AX values; no expected values enter capture.
Status dots likewise now have actual component identities at their native
hierarchy positions, rather than unordered anonymous paint-only elements.

All independently re-shaped fonts, including AX/native-control attributed
font estimates, are now explicitly diagnostic `native_reshaped_fonts`.
Only currently bound actual glyph callbacks supply `rendered_fonts`; controls
without that measurement remain unknown and fail. Their actual declared AX
font metrics remain in the raw evidence, never promoted to actual fallback.

Additional actual-capture fixes: the `fcdc0b6` group composer exposed a 1158px
native editor inside its 758px viewport. The initial 400px document width was
being added by native autoresizing. The production scroll view now explicitly
lays out the editor to its real clip-view width and assigns the localized
placeholder/name directly to that NSTextView. A real AppKit resize regression
checks three viewport widths and return-to-original while preserving text/caret.

Unowned production card surfaces now create their real AX container at the
same point in the SwiftUI hierarchy and bind their paint probe to that identity.
The previous anonymous paint-only cards were appended after the AX tree, which
made actual message/event cards appear missing and extra despite near-identical
bounds. Native children stay inside the actual container; no matcher order or
reference values are used to fabricate ownership. New captures must validate it.

Consumed the line-break contract announced in `f7341de`. macOS TextKit spans now
emit `layout.break_strategy_version: 1`, `normal_break_strategy` and
`emergency_break_strategy`, keeping legacy wrap, actual line rectangles/count
and truncation. `evidence.line_break_configuration` binds the actual native
owner/container, paragraph/container modes, paragraph strategy, line limit and
the production slash-boundary delegate. Unknown delegates/modes stay unknown.
AppKit word wrapping is normal `word` plus `break-unbreakable`; character-first
wrapping is `character` plus `none`. Existing long-path native layout coverage
and a new actual word-versus-character first-line test exercise the distinction
in CI. This records configuration, never substitutes for actual glyph geometry.

The old `testBoxShadowDoesNotCastASecondShadowFromInteriorContent` failure is
resolved in `afe7f6f`: it now measures the production NSHostingView bitmap,
because ImageRenderer substitutes unsupported-view paint for the actual AppKit
outline overlay. All original assertions/tolerances are unchanged. macOS build
and all 138 tests pass in `41004901785`. The separate new six-position shadow
edge-profile test and current-font binding tests are still awaiting a runner.

The latest native sidebar probe carries unread from the very same condition
that constructs its actual count badge, including false for read rows. The bell
now paints the reference alert color and icon hover paints the reference ink.
These are production-control changes, not report substitutions; full capture
verification remains pending. No state mismatch is waived.

Actual-font evidence update: macOS TextKit spans now project `rendered_fonts`
only from the production `showCGGlyphs` callbacks for the same complete span,
unchanged attributed source, native view/container/window identity and layout.
Raw `native_font_drawing` records current binding or an explicit unknown reason;
independently reshaped `native_reshaped_fonts` stays diagnostic. A callback has
no per-callback source indices, so assigning its fonts to a partial rich span
would be unjustified and remains unknown. Please retain that unknown in the
gate, and do not treat reshaping metadata as actual rendered-font evidence.

`4f67f67` fixes the shared malformed-pattern fixture noted below; consumed via
`fcdc0b6`. Full `56253c7` report is downloaded to
`S:\Codex\Outputs\Relic-native-visual\parity-56253c7\report\`.
Both platforms have zero accepted scenes; all category counts are in STATUS.md
and the actual `parity-report.json`. No exception has been requested or approved.

Layout quantity review: the actual group bubble CSS is `overflow-wrap:anywhere`
with normal word wrapping (`app.css:233`), but reference canonical `layout.wrap`
is `character`; native TextKit's `.byWordWrapping` also breaks an overlong word
when necessary and is currently `word`. Those properties do not establish that
the two break opportunities differ. Please retain normal break strategy,
emergency break strategy and observed line fragments separately in the shared
layout contract; compare independently measured equivalent quantities, without
renaming native modes from expected values. Actual observed fragments must still
match. macOS now records paragraph and container line-break modes separately;
a multi-line clamp keeps paragraph word wrapping plus final-line ellipsis.

Consumed `663457c` / macOS per-viewport sharding with original case IDs and
unchanged deadlines. New build and full capture are being pushed together.
Current shared checker failure: `9289b84` smoke `41003664049`, job `123893680759`,
fails `test_reference_missing_or_malformed_pattern_evidence_never_reaches_pixel_comparison`
in `test_report_fail_closed.ReportFailureTests` with `AssertionError: 2 != 1`.
Please inspect the additional actual failure and adjust only the fixture/assertion
to cover the intended evidence; preserve all malformed-pattern rejections.

New downloaded full-capture evidence: `56253c7` / `40996703093` macOS zh-CN/light
job `123871871182` completes all 165 cases, every case `captured`, no errors.
The 1024x700 Copy toast and both panel gestures retain all four continuity
checkpoints through element extraction. Native and corresponding reference files
are in `parity-56253c7/macos-zh-CN-light` and `reference-macos-zh-CN-light` under
the requested output folder. This is capture completion only, not a passing gate.

`9289b84` keeps each production uniform label as one semantic text element across
actual TextKit font fallback, retaining every original attribute run and actual
fallback face. The 1024 group reference owns `→ 全体` as one label with SFNS and
PingFang runs; old native wrongly emitted two elements. Unmarked rich text keeps
its independent emphasis boundaries. New regression tests exercise actual fallback.
The composer recipient chip also now follows the later `.chip-btn` CSS override
(14px radius, 5px gap, 11px padding plus border, live hover paint).

Actual raster diagnosis: in the downloaded 1024 group, the same 40-character
message has PingFangSC-Regular, size 14, resolved weight 400 and virtually equal
advance widths on both sides (556.921875 / 556.92). Approximate red-channel ink
coverage is 2068.80 reference / 2444.42 native. Production text draws now explicitly
request antialiasing without font smoothing, matching app.css's antialiased mode
and Blink's macOS CreateSkFont branch; no font defaults or user system settings
are changed. Inputs remain raw draw evidence, not proof of final pixel equivalence.
Actual screenshot validation is pending. The preceding `9289b84` build exposed
OutlineDrawReceipt's missing MainActor annotation; `985a3ae` fixes it and awaits CI.

Consumed `6183507` / independent outline and measured-icon pairing. macOS now
draws its separate outline through the actual native surface view, retaining the
submitted CGPath, width, phase, dash, color, context clip/transform and current
view/window/configuration binding. It projects that actual stroke centerline to
window coordinates under the shared outline schema. Missing current draws and
unknown owner focus/template paint stay unknown; no blanket `none` is emitted.
Final-PNG attribution and browser dash/contour equivalence remain unproved.
New actual-raster phase/corner/clear-receipt tests await CI. The earlier generic
"comparison unimplemented" error is replaced by current canonical unknown fields
and specific draw binding errors, not an exception or suppressed mismatch.

Current verified macOS build is `e680244`, run `41001469107`, job `123886607450`:
133 tests pass, including actual logo paint. Mounted-Copy smoke `41001468895`
was still pending at this update; the old 18/19 result is not its validation.

Full-run timeout diagnosis: `56253c7` / `40996703093`, macOS en-US/dark job
`123871871096`, starts 148 cases over 1192.319 seconds and writes 147 PNG/element
pairs before the 1200-second total native wait cuts it off. CI's actual progress
timestamps give 8.111 seconds mean, 4.623 minimum and 14.466 maximum between cases;
there is no 90-second stalled case. The last case is 1024x700 recipients. Reference
then completes all 165 cases. Raw native receipt is a TimeoutError and no complete
file; partial screenshots are not a successful full matrix.

Please shard the macOS native invocation by viewport into three independent
55-case manifests against the same existing fixture/server and unchanged case IDs,
retaining the existing per-process timeout and every case/error in aggregation.
This keeps the 660-case acceptance matrix and all element tolerances unchanged;
it does not exclude failed states or increase a measurement tolerance. Current
branch also writes the same raw AX/element/geometry data without indentation;
the downloaded chart example drops to 51%/47%/44% of its prior JSON byte size,
with no measurements removed. Actual runtime benefit still needs CI evidence.

Confirmed large-window raster recovery: `25f57f2` / diagnostic `40997958370`
has actual opaque 1440x900 native PNGs, including both new panel gestures.
The previous all-transparent composite failure is absent. All 19 native cases
were attempted; 18 complete and Copy fails because its model toast was observed
at 6ms before SwiftUI mounted the actual text/surface (both measured counts zero).
The clipboard and same running timer were correct. Native now waits for that
same real mounted toast while its original clock runs, then pauses; no extra
Copy, toast replacement, lifetime extension or removed continuity assertion.
Source and report are under `smoke-25f57f2` / `parity-25f57f2` in the output folder.

Consumed shared `d8f74ff` image contract and scrollbar-fixture fix. NativeLogoView
now retains the actual parameters used by its CG calls: rectangle bounds/radii,
gradient stop locations/colors, sRGB space, both extension flags, parsed CGPath
segments and original parser input/fill rule, circle geometry, and executed layer
order. Its `native_image_draw.paint` uses `vector-image-v1`, emitted as canonical
icon only when the actual view/window identity and local bounds still match the
completed draw. Raw transform and outer clipping remain separate. The receipt
explicitly does not claim final-PNG pixel attribution. New native bitmap tests
check actual letter/circle pixels and orientation; CI validation is pending.

Latest verified build: `33a67ec`, Native apps `40999624975`, macOS job
`123880723628` passed. This includes the sidebar surface fixes and production
owner association; the actual large-window capture still awaits artifact upload.

Current shared checker regression: `25f57f2` diagnostic `40997958370`, job
`123876130410`, fails Node subtest 25, `overflow scrollbar evidence retains actual
metrics without inventing thumb bounds`. `test_reference_elements.mjs:253` throws
`SyntaxError: Unexpected token ';'` in `vm.runInNewContext`; source test location
247. Please fix the shared snippet extraction/test without suppressing the case.

Outline coverage request: reference `.org-badge.sub` has a separate 1.5px dashed
currentColor outline at -1.5px offset, with no border. macOS now draws a separate
inward outline, preserving the 22px avatar box and zero border. The actual surface
style retains `native_outline: {width, color, dash, offset, renderer}` from that
production draw, and explicitly reports common outline comparison as unimplemented.
Please include actual reference computed outline / paint evidence and canonical
outline comparison. Dashed curve phase/segment equivalence is not presumed.

Pairing diagnostic request: `b3d2385` en-US/dark 1440x900 group pairs the reference
Back glyph with the native Sidebar glyph, then Forward with Back. Both glyph
identities actually exist; same-kind/empty-text sequence alignment shifts after
a missing item. Please consider exact measured icon content as a same-region
pairing anchor (unique occurrences first, repeated occurrences in real reading
order), retaining the missing/extra items and all geometry/style/order failures.
No icon equivalence, content normalization beyond the existing identity decoder,
tolerance relaxation or inferred owner is requested. Raw evidence/report is at
`S:\Codex\Outputs\Relic-native-visual\parity-b3d2385\report\en-US-dark-1440x900-group.parity.json`.

Important capture regression, not acceptance: the downloaded `ee478c5` diagnostic
(`40993478737`) contains fully transparent native PNGs (all RGBA channels zero).
Its AX counts and 17 completed older actions do not make those screenshots valid.
The retagged NSBitmapImageRep final canvas retained a pre-draw image snapshot.
`9990d4f` now composites the actual native caches into an owned sRGB CGContext,
snapshots only after drawing, and verifies opaque source/final pixels. Its unit
test exercises that same compositing + PNG round trip with the original color
assertions. New CI is pending. Preserve the old transparent PNGs as failures;
no screenshot is replaced with reference paint. Local evidence is under
`S:\Codex\Outputs\Relic-native-visual\smoke-ee478c5\`.

Image identity request: reference `#appbar img.ab-logo` is a visible image even
though its web AX node is ignored. Its current canonical icon glyph is a
per-run `http://127.0.0.1:<port>/static/icon.svg` URL. Please retain the actual
loaded resource bytes / decoded SVG paint primitives as image evidence so
identical image content can be compared across clients independently of their
transport URI. Do not approve an icon mapping on that basis alone. macOS now
renders the brand image in one actual NativeLogoView and records its real draw
callback: view box, gradient stops/endpoints, vector letter path/fill, circle,
outer 5px clip and local bounds. The raw node's `native_image_draw` carries these
measurements; no reference URL or expected image identity is inserted by native
capture. Its source identity comparison remains unresolved until the common
format covers those actual resources.

Latest verified macOS build: `14b78e0`, run `40994507899`, job `123864386261`,
128 tests passed. The disabled-button failure is resolved without changing its
tolerance: actual sRGB bitmap/PNG bytes are [27,27,26,255] / [175,175,175,255].
`colorAt` had returned a calibrated color, so its subsequent sRGB conversion
changed those measured bytes. Capture now samples the actual tagged sRGB data.
The mixed-script label test independently measures advance 130.642880 versus
reference 130.640625; TextKit's glyph envelope is 135.528076. `e0c98f8` records
actual insertion-point advance geometry and keeps the separate ink envelope.
Truncated/missing boundaries remain unknown and fail coverage.

Consumed shared `ca134e4`: per-case bounded reference browser workers and the
original Copy PNG before clock pause address the confirmed CDP stall request.
Runtime success still awaits fresh CI. The older full `b3d2385` has one native
en-US/dark 1024x700 Copy failure: its AX button was entirely above the scroll
clip (top=68, stream starts at 96). Reference locator click scrolls that control
into view. macOS now uses the actual document's `scrollToVisible` before its
mouse gesture and retains the requested rectangle, before/after native clip,
clipboard and toast evidence even on failure. No substitute click or toast.

Consumed `d77f162`: all 55 shared scenes are retained (660 full / 19 diagnostic).
macOS implements the new real panel hover/64px drag inputs, opens a hidden pane
through its actual toolbar control, and records mounted pane/handle identities,
received production SwiftUI gesture callbacks, before/after bounds and pointer
state through PNG and extraction. The original width/position assertions remain
exact; execution awaits CI. Scrollbar kinds are now accepted by the shared schema;
macOS is wiring its actual draw receipts and native value range into those kinds.

New confirmed shared reference stall: full `40984430181`, macOS zh-CN/light job
`123832322148` exhausted its 45-minute job deadline. Native completed all 159
cases (151 captured / 8 preserved failed states); reference wrote only 51 cases.
The actual `zh-CN-light-1440x900-message-copy-toast.scene-action.json` has completed
clipboard reads, `clock_pause`, both state checkpoints and viewport validation.
Its final step is `screenshot:Page.captureScreenshot` with status `started`, at
host monotonic `1407.937113625`; no PNG returned before the job was cancelled.
Thus this is now the CDP capture itself stalling under paused virtual time,
not the already-fixed async clipboard read. Evidence is downloaded under
`S:\Codex\Outputs\Relic-native-visual\parity-c4b113d\reference-macos-zh-CN-light\`.
Please resolve the frame/clock coordination and retain bounded per-case failure
receipts so one CDP wait cannot consume the rest of the full reference matrix.
Keep the original toast/timer/clipboard identity checks, exact PNG and all cases;
do not replace the actual toast or skip Copy/textarea/remaining viewport sizes.

New extraction-contract requests from actual c4b113d reports:

* `scripts/visual/element_parity.py:KINDS` does not accept `scrollbar` and has no
  thumb kind. Each real macOS ReferenceScroller and AXValueIndicator child is
  currently structurally rejected (four of five rejected group elements). Add
  measured track/thumb counterparts to the common schema/reference extraction;
  these are visible/usable controls, not wrappers to drop. Native AX reports
  hit rectangles wider than the actual 10px NSView gutter; production draw and
  actual view geometry must supply paint bounds separately from AX hit bounds.
  macOS adds raw `nodes[].native_scrollbar_paint` from the actual draw callback:
  track/knob local bounds, the separate knob hit bounds, resolved fill/radius,
  clipping, orientation, normalized value, knob proportion and hover state.
  Missing draw receipts stay null; they are not supplied by expected geometry.
* Reference `.pane-resize` is a real 5px element with `onpointerdown: startResize`
  and a hover/drag accent fill at 40% alpha, but c4b113d extraction emits no
  counterpart. Emit its actual interaction as `resize-handle`, with its title,
  DOM bounds, paint and pointer state. macOS now names its existing production
  drag target `relic-resize-handle/panel`, matches that width and actual hover/drag
  paint, and retains it as `resize-handle`. Do not discard either control because
  its fill is transparent when idle. Add panel-resize action/hover scenes to the
  shared matrix to exercise this uncovered interaction on both clients.

The diagnostic report downloaded from `40984430455` is under
`S:\Codex\Outputs\Relic-native-visual\smoke-c4b113d\report\`. Its full gate still
expects 636 cases despite 17 diagnostic inputs. It records zero passed/checked
comparisons, 79 structurally rejected native elements, and all missing/unknown
measurements as failures. No diagnostic receipt is a full-matrix pass.

Update after shared `4afb5d1`: the aggregate-error assertion, 53-scene
expectations and regular screenshot `caret="initial"` request below are resolved.
Caret paint/geometry coverage itself remains unverified. macOS now writes failed
state debug PNGs under `diagnostics/`, preserving the canonical case and error.

New macOS runtime evidence: `40983620508` and `40984430455` both attempted all
17 diagnostic cases. The former confirms a real display-mode switch to
1600x1200, and the textarea gesture observes the same +64px height / -32px top
delta as its reference. Capture failed because inspecting `NSTextView.layoutManager`
can switch a TextKit 2 control permanently to TextKit 1, removing hundreds of
mounted text views; macOS `0c57b25` guards all such access and keeps the actual AX
controls/unknown measurements. The later `c4b113d` run, before that guard, has
mostly stable explicit TextKit 1 labels but still changes group document height
936 -> 916 and removes four rename-editor views. These remain failures until
new receipts prove stability. `b501f03` also fixes two diagnostic assertions:
expanded output is checked relative to the actual *current* row position after
the scroll moves, and avatar hover is verified using its actual painted label,
surface and pointer rather than requiring an invisible wrapper AX node.
No scene, tolerance or exception changes are requested.

Verified follow-up: `40987219219` / `38af737` now has 16/17 macOS diagnostic
cases captured, only group failing with four changed document views. The actual
hover/expanded/rename/textarea states pass their capture assertions, and no
TextKit 2 content views disappear. `3c652b7` lays out the currently loaded page
with VStack and anchors after the real 24px bottom space; this remains pending
capture validation. Its lazy-layout diagnosis must not be treated as a pass.

Dropdown arrow coverage: the actual c4b113d reference PNG shows one downward
chevron, while AppKit's default popup draws two directions. macOS now keeps the
real NSPopUpButton/menu and paints a single 8x4px, 2px butt-cap/miter-join arrow,
in the actual field foreground. Raw AX nodes retain `native_dropdown_arrow`
with the production draw's local vertices, stroke, color and completion. The
canonical icon remains unknown until independently matched. Please measure the
reference's UA select arrow and include it in the control paint/element contract;
do not declare it absent because it is not a DOM SVG. The inspected Chromium
`NativeThemeBase::PaintMenuList` and `ThemePainterDefault::SetupMenuListArrow`
describe this stroke/shape, and the downloaded reference's pixels agree, but
the captured Chromium 156 build still needs its own per-case evidence.

Test failures noted in the latest shared contract are addressed by macOS
`8308590`, pending CI: static-text name extraction now tests the actual
production ReferenceLabelView instead of an unattached NSTextField reporting
AXUnknown; two run/font tests construct the production TextKit 1 stack explicitly
while the separate TextKit 2 test still rejects renderer switching. The button
opacity raster test now uses NSHostingView caching, because ImageRenderer paints
unsupported-view substitutes for the AppKit probes behind a transparent button.
Original value, font, line, appearance and pixel assertions are retained.

The earlier browser-install substitutions near the end of this file are
historical source/function parity notes, NOT approved Amendment 4 exceptions.
The captured reference still visibly contains Install and native omits it.
The browser tutorial's `/api/install-window` action was removed by the shared
native architecture and returns 410; implementing a browser launcher would
conflict with the person's native-only requirement. Keep this visible missing
element/control difference in the strict report. It has not been approved as
an exception and must not be silently filtered by the existing source allowlist.

Follow-up shared checker failure after `442d1de`: run `40983885238`, job
`123830414252`, fails `test_main_writes_failed_aggregate_then_exits_nonzero`
at `scripts/visual/test_windows_capture_processes.py:170`. Its regex still
expects `Windows capture failed`, while the new independent-component
coordinator correctly raises `Capture has 1 component/case error(s); see ...`.
Update the assertion to the current aggregate error and keep its original
failed-receipt/nonzero-exit checks. This is a stale test contract, not a request
to suppress capture errors. The previous 53-scene expectations are now resolved.

The regular reference screenshot call at `capture.py:675` still omits `caret`,
so Playwright's default hides a focused input's caret during the PNG, while
native focused inputs retain the production caret. Please preserve actual
caret paint/state and add its independent measurement to focused-input scenes;
do not mark the unmeasured native/reference caret as absent. The new CDP Copy
toast path avoids this mutation already. This remains a pending paint/state
coverage difference, not an approved exception.

macOS now retains `raw nodes[].native_glyph_drawing` from the production
`NSLayoutManager.showCGGlyphs` callback for native labels and selectable Markdown.
It records the actual substituted font, glyph IDs/positions, font glyph bounds,
text/context matrices, clip and draw completion. These are raw independent draw
receipts, not another attributed-string reshaping or reference-derived geometry.
Canonical values are unchanged pending verified mapping to the captured bitmap
and corresponding text runs. A CI bitmap test requires real painted pixels and
no receipt from layout alone. This also supplies evidence for the unresolved
conversation coordinate discrepancy and the requested/actual font distinction.

Shared checker failure to fix on `native-apps`: full run `40982407855`, job
`123825557731`, fails `test_all_52_cases_get_fresh_process_inputs_and_continue_after_menu_crash`
in `scripts/visual/test_windows_capture_processes.py:54`. The 53-scene matrix
now ends in `new-org-textarea-resized`, but this assertion still expects
`message-copy-toast`; the success count still expects 51 instead of 52 after
the one deliberately failed menu case. Preserve the assertions and all 53
attempts, updating the stale expected last case and successful count. Current
`58d0179` still contains both old values. No client/source parity tolerance
change is requested.

The new `new-org-textarea-resized` scene from `a87f924` is consumed (53 states /
636 cases, diagnostic 17). Production native form textareas now have an AppKit
corner handle and resize through their real mouseDown/Dragged/Up handler in
both dimensions. CI requests the shared measured-corner +64px gesture, retains
the actual received events, owner/editor identities, values, pointer and observed
geometry deltas, and checks stability across PNG and extraction. Handle paint
is independently described by its actual draw routine; reference grip paint
measurement remains unresolved, so this is not an equivalence claim or exception.

New `.native-geometry.json` receipts compare the mounted NSView/NSClipView tree
before PNG, after PNG and after AX/TextKit inspection. The actual a644753 PNG
and text/surface geometry disagree inside the conversation scroll region.
These passive receipts retain frame/bounds/scroll coordinates and layer positions
to isolate the cause; they do not replace canonical bounds with reference values.
Geometry drift fails capture, and an existing PNG is preserved separately before
the failed-state screenshot is taken. The change awaits CI validation.

The macOS runner evidence reports a 768px screen while the native content is
1440x900; the real pointer cannot address every control when the window exceeds
that display. macOS CI now records all actual CGDisplay modes, selects an
advertised desktop mode large enough for the largest case plus native window
frame/pointer margin, and restores the original mode at capture completion.
`native-display.json` retains before/request/result/after/restore receipts. There
is no image/window scaling or matrix-size change. If no adequate mode is exposed,
the record says so and existing interaction/state failures remain; please provide
an adequately sized CI display through the shared runner setup if required.
No display API or application is run on the person's local Windows machine.

The 52-state / 624-case matrix and 16-case diagnostic from `native-message-capture.md`
are consumed. macOS toast expiry now has a production ContinuousClock deadline;
capture pauses that same task with measured remaining duration and resumes it in
per-case cleanup. It retains the same message/tooltip-toolbar/toast objects,
actual pointer, clipboard, paint and bounds across action, PNG and native source/
element extraction phases. Drift is a capture failure. The action sidecar keeps
all observations plus timer cleanup; successful elements embed `capture_evidence.message_action`.
CI validation is pending; no permanent-toast flag or repeated Copy action is used.

Latest native evidence: `838f96c` build/test run `40978875575` passes 110 tests.
Smoke `40978583080` captures all 11 cases but retains one actual state failure:
the tool row hovers at the requested center, yet expanded remains false. The
production plain Button label contained a non-hit-testable Spacer. Native now
uses a full rectangular contentShape for real row clicks; the unchanged capture
assertion must verify it. Historical transcript action groups also now retain
their actual border, timestamp, avatar-column offset, counted tool summary and
separate call/result blocks.

The form textarea's visible native resize grip remains a missing counterpart;
please add reference measurement for the real textarea resize affordance and a
`new-org-textarea-resized` state using a pointer drag on it. Existing canonical
kinds do not include a resize handle. Supply its measured kind/geometry/paint
and state before defining the common counterpart; keep this as a failure, not
an omission or exception. Native fixed-row editing now uses the entire assigned
viewport so its placeholder starts at the top instead of being vertically centered.

macOS capture event-dispatch correction: full run `40974621706` still stalls
at the first real input click after replacing NSPopover; smoke `40974672159`
reaches the live tool click but fails its open-output assertion. Capture now
queues complete mouse down/up and key down/up gestures through
`NSApplication.postEvent(_:atStart:)` instead of synchronously calling
`NSWindow.sendEvent` for mouseDown before mouseUp can be queued. Native text
fields can enter an AppKit tracking loop during that call. This is a diagnosed
dispatch hazard being tested, not a claim that the new capture has passed.

If a macOS case still fails to advance, please retain a `/usr/bin/sample <pid> 3`
report of the actual native process before the shared 90-second progress timeout
terminates the run. Suggested output: `data/<lang>/<theme>/native-stall.sample.txt`;
invoke only on the CI macOS runner and bound the diagnostic subprocess timeout.
The existing error/timeout remains a failure; no increased tolerance or skipped
case is requested.

Native capture now catches individual case failures, saves the mounted failed
window and its real AX/TextKit evidence with `native_scene_action_failed` in
`extraction_errors`, retains errors in `complete.json`, and then attempts all
remaining cases after the normal Model/view/fixture reset. A failed fixture
setup never reuses the previous case's PNG. The run still exits nonzero if any
case or integration assertion failed. This improves diagnostic coverage without
turning a failed state into acceptance evidence.

Please add `member-card-rename`, `member-card-model`, and `member-card-avatar-hover`
to the shared matrix/reference harness: start from `member-card`, click the real
rename button, click the real model Change button, or hover the real avatar,
respectively. macOS now renders the rename field in the header, the model editor
inside its value column and the avatar hover layer, and will perform those real
native actions in these additional scenes. Keep all existing 47 scenes and
tolerances. These previously unmeasured states are required by Amendment 4.
Resolved by `36fca26`: all three are in the shared 50-state / 600-case matrix;
the native real-action capture handlers are retained and await CI validation.

macOS consumes `fixture.scene_endpoint` before every case, records the actual
response as `<case>.scene-fixture.json`, reloads the returned member's real Hub
state, and opens the live tool disclosure by native mouse events at its measured
AX bounds. `live-busy`, `live-tool-output`, and `live-typing` remain additional
states (47 scenes / 564 cases); no previous scene is removed. The typing dots
use a production NSAnimation clock and native drawing; capture stops and seeks
that actual clock and retains before/after clock and draw receipts. This work
still awaits macOS build/capture validation and does not establish parity.

Also add `message-hover` and `message-copy-toast`: in the group chat, hover the
real `.msg[data-id="<fixture.thread>"]`; for the toast scene click that message's
real Copy icon and retain the actual clipboard/visible toast receipt. macOS
implements both scenes by actual pointer/mouse events against live view/AX
bounds. Hover scene captures must keep the pointer at the target; the existing
unconditional `page.mouse.move(width + 20, height + 20)` would erase these states
and the requested `member-card-avatar-hover` state. Other scenes continue moving
the actual pointer outside the viewport. No screenshot-only hover flags are used.

Native default notices now use the reference's independently expiring 3.6-second
bottom toast; member renames retain the reference's explicit 5-second duration.
The native message hover toolbar also has its actual icons/order and icon-only
Copy control. These added states still need reference measurement, not exemptions.

Shared checker run `40970311201`, job `123786329669`, fails Node tests 9 and 25:
`overflow scrollbar evidence retains actual metrics without inventing thumb bounds`
and `zero scrollbar gutter is not proof that overlay scrollbars are absent`.
Both report `SyntaxError: Unexpected token ';'` while evaluating the extracted
`scrollbarEvidence` expression (`test_reference_elements.mjs:176` and `:433`).
Please fix the shared test/extractor boundary on `native-apps`; macOS leaves
these files and the failure gate untouched.
Resolved by the shared changes merged through `ddf7759`: the shared checker jobs
in runs `40974621706` and `40974672159` now pass. The historical failure above is
retained as the evidence for the request; no shared file was edited here.

Color evidence question: the reference `color()` rasterizes the computed CSS
color through a 1x1 OffscreenCanvas and exports RGBA8 `getImageData`, whereas
native currently exports the actual NSColor sRGB floating components times
255. For alpha 0.07 these measure 18 versus 17.85; low-alpha premultiplication
can also change RGB when the canvas unpremultiplies. Please define/compare the
same measurement quantity for both platforms, preserving each provider's raw
components and raster evidence. This is not a request to relax alpha/DeltaE
tolerances or copy reference colors into native data. Native values remain
unchanged until a measured conversion is implemented and tested.
Resolved in the shared contract merged through `36fca26`: computed float RGBA
and independent canvas RGBA8 raster evidence now remain separate quantities.
Native actual brush values and matcher tolerances have not changed.

Canonical layout-container question: native AX exposes transparent grouping
nodes (`AXGroup`, `AXScrollArea`, `AXOpaqueProviderGroup`) independently of
visible paint. The reference `kindOf()` omits equivalent transparent DOM layout
wrappers except its explicitly named regions. Current macOS export retains
these as canonical regions as well as in raw AX, so a group screen has several
extra regions at the same bounds. Please document the common rule for projecting
unpainted layout-only wrappers versus visible/interactive region elements.
Native will retain every raw node and unresolved paint coverage failure; this
must not become a blanket element/scene exclusion or an exception. Painted
container borders/fills, scrollbars and actual controls remain separate evidence.
The shared `native-layout-projection.md` merged through `7d0703d` supplies this
contract. Native still needs independent paint/action/semantic ownership proof;
no AX wrapper has been removed under this request.
The raw macOS AX records now additionally retain actual legacy/custom action
names, modern selector availability/permissions, first-responder capability,
focus-settable evidence, native object/superview identities and view geometry.
An unfocused, empty-named AXGroup with an allowed action is covered by a negative
projection test. This does not certify absence of uninstrumented drawing or
delegated interaction; the existing unknown-paint failures and canonical nodes
remain. No user action is executed while extracting capabilities.

## 2026-10-29: literal Harness label in the reference member form

Font evidence update: `67dae7b` macOS build and 97 tests pass in
https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40970989476 . CI resolves
PingFangSC-Regular to the variable PingFangUI.ttc font. Public CoreText
`kCTFontOpticalSizeAttribute = "auto"` changes the actual shaping from
401.766371 px to 419.406371 px for the measured reference sentence (419.4375 px).
Four independent reference-width assertions now pass without changing any gate
tolerance. Native render-run evidence also retains actual variation coordinates,
optical-size attributes and ascent/descent/leading. This does not resolve the
separate requested-CSS-weight versus actual-font-weight comparison question.

Resolved by `5ff6706`: macOS now consumes `member.harness_label` and handles
both additional suggestion scenes through actual input/keyboard events. The
original request below is retained for audit; popup parity is still unverified.

`memberDialog()` renders the literal `Harness` above its app-run radio choices
in both languages. `common.harness` is `Harness connections` / its longer
Chinese settings label and does not match. Please add `member.harness_label`:
`Harness` to both `/api/i18n` word lists, preserving the actual reference text;
the member form will consume that key. Until it exists, the existing
`common.harness` label remains an explicit text mismatch. No client string fork
or raw-key fallback is introduced.

`cd6c840` also resolves the ordered file `display_text`, `common.app_name`, and
reference code-line reading-order requests below. macOS consumes both additive
fields. Native capture now recreates its Model, UserDefaults suite and SwiftUI
view identity for each case, matching reference capture's new page and cleared
local/session storage. This fixes unread/disclosure state leaking from preceding
cases; no fixture state is injected into the element exporter.

Please extend the matrix with the reference's open model and seat-name
`datalist` popups in the member host/existing forms. macOS retains both value
suggestion lists through the native input's Down Arrow action; their open
popover still needs the same measured reference scene. This adds states; it
does not replace/exclude any of the existing 42 scenes or waive popup geometry.

## 2026-10-29: ordered protocol JSON display from the shared engine

The reference shows `JSON.stringify(plainRules(p.rules), null, 2)` in the
protocol details code block. Foundation JSONSerialization does not preserve
wire object-member order; sorting native keys changes visible text. Please add
`rules_display: string` to protocol rows in the snapshot's `protocols` and
`inherited_protocols`, containing the exact indented display JSON of plainRules:
for check rules omit `code`, `examples`, `code_sha256`, preserve all remaining
wire key order, use two-space indentation and unescaped Unicode. The native
client now consumes this field, falling back to its existing serialization for
older servers; fallback differences remain reportable failures. Keep the
existing rules array and payloads unchanged.

The expanded check-rule examples additionally need `call_display` and
`call_json` on each example: `call_display` is reference `exampleText(call)`
(first command/file_path/path, else compact JSON; clip normalized text to 160
UTF-16 units); `call_json` is `JSON.stringify(call, null, 2)` for the tooltip.
Both must preserve source object ordering. The native implementation consumes
these optional fields and keeps its older-server fallback visible to the gate.

## 2026-10-29: measured chart paths and dashed stroke evidence

The macOS chart now draws the reference's orthogonal parent connectors and
shared-seat cubic paths with native SwiftUI/CoreGraphics, and exports each
live path's actual geometry, width, dash array, opacity, transform and glyph.
Zero-width vertical path bounds are retained because the stroke is visible.
Nodes carry their own real accessibility identities and individual native labels.

Please extend shared style comparison to preserve/check actual dash patterns
(`stroke_dash` for SVG/native paths, and border dash/style evidence for subgroup
cards). macOS exposes its production arrays as `projection.stroke_dash` and
`surface_evidence.border_dash`. These were absent from the common style shape,
but dashed versus solid is visible and is required by element parity. This is
an added measurement request, not an exception or a tolerance change.

`e4c559e` Native apps run 40957778580 is green. Earlier `57f183a` failed to
compile because an NSSize literal made greatestFiniteMagnitude ambiguous; the
fix explicitly specifies CGFloat and is included in e4c559e.

## 2026-10-29: actual macOS font identities and dialog continuation

`34d56cd` Native apps run 40953908181 is green, including macOS build/tests.
The en-US/dark shard of visual run 40952663814 (`119f04c`) completed all
126 captures. Its actual CoreText font records identify `PingFang SC` /
`PingFangSC-Regular` (or `PingFangSC-Semibold`); CDP records the same PostScript
faces with localized family name `蘋方-簡`. Please define the schema's font
identity comparison using the measured PostScript face when both APIs supply
it, preserving each original family spelling and all fallback runs. Do not
substitute fonts or suppress real face differences. The current report must
continue failing until this measurement question is resolved and tested.

This shard also exposed a native extraction bug: dynamic text colors were
resolved outside the text view's effective appearance, so dark screenshot
text had a light-theme foreground measurement. The macOS fix resolves the
actual attributed colors in each view's effective drawing appearance; it
does not copy screenshot expectations or reference values.

Native settings/form dialogs now use an in-window SwiftUI overlay to reproduce
reference placement, dimensions and scrim rather than the offset system
sheet. The actual native hierarchy and surface paint remain exported; this
change does not exempt background occlusion or any element/style mismatch.

# Requests to the shared/native-apps owner

The macOS session owns only `native/macos/**`. Please merge this branch regularly.

## Amendment 4 — element extraction / strict machine gate (active)

2026-10-29 restart update: d4a4e44 builds and passes 70 XCTest cases in
40938288562. Full visual 40938288684 captures all 504 macOS cases, including
1024x700 and the real-app compound-label integration assertion. The strict
report still fails. Native fixes continue; no exception or tolerance change.

The platform-specific reference request is resolved by e9488e1 and merged.
The actual macOS reference font is PingFangSC-Regular/Semibold, including English;
the native font configuration is being aligned to that existing CSS fallback.
Please review these measurement-unit/coverage issues without treating them as
exceptions or filtering any visible element:

- Font weight: macOS reference `group` sidebar `Group chat` reports computed CSS
  weight 550 but CDP's actual face is PingFangSC-Semibold. Native public font APIs
  report the resolved face weight, not the requested CSS weight. Define separate
  requested and resolved weight evidence, and compare equivalent quantities;
  do not normalize away an actual face/axis difference. Native will retain both
  production configuration and actual CoreText run evidence.
- Truncation geometry: `en-US-dark-1440x900-group` reference sidebar preview has
  a DOMRange width of 459.578125 even though its ellipsis box is about 140 px.
  Native TextKit's actual truncated glyph bounds are about 140 px. Please audit
  `bounds`, `visible_bounds`, and `text_bounds` so invisible characters beyond a
  CSS ellipsis are not reported as painted glyphs. Retain raw DOM ranges.
- Scrollbars are visible in both clients. Reference CSS specifies a 10 px track
  and a 4 px painted thumb, but DOM extraction appears to omit scrollbar parts.
  Please include real UA scrollbar paint and define canonical kinds for the
  scrollbar and thumb. Native AXScrollBar/AXValueIndicator are retained as
  explicit unresolved kinds until that common shape is defined.

Shared Windows failure in 40938288684: en-US/light stopped at
1280x800-settings-notify with COM E_FAIL in DrawConversation(), Conversation.cs
line 209. Other three Windows shards and all Mac shards completed. Please fix
on native-apps; this branch does not edit Windows files.

Latest macOS implementation is b7e6962. It includes the shared 237f254/4db4aa6
work, adopts RELIC_VISUAL_NOW and UTC only in CI, emits the version 1 schema,
and renders the reference icon path assets through CoreGraphics. Actual path
geometry/color/resource evidence is collected by transparent native view probes.
Toolbar menus and pane tabs now have in-window counterparts. This is ongoing
implementation, not an accepted element-parity result.

Update from CI 40930279724: public AX client initialization succeeded (0).
The en-US/dark group scene now exposes 790 raw nodes and 171 normalized
elements, including actual SwiftUI.AccessibilityNode children, not just the
hosting root. All 126 en-US/dark captures finished. Style/paint coverage still
fails explicitly; actual AXFont/CGColor attributes and TextKit run geometry are
being decoded next. It also exposed incorrectly inherited container AX labels;
those are being fixed in production views, not rewritten in the exporter.

The first complete strict report, CI 40926888945 at 61b2740, is downloaded to
S:\Codex\Outputs\Relic-native-visual\parity-61b2740\report. Both platforms have
0 fully measured/passing scenes. macOS AX still returned only hosting roots;
its 706 emitted elements are incomplete. Three macOS variants captured all
126 scenes; zh-CN/light stopped at mention, so the remaining cases are explicit
missing captures. Current CI adds navigation-order AX children, real AppKit
subviews, a public AX client request, and mention-state diagnostics. No failed
scene or unknown measurement was excluded.

Shared input question: reference capture currently runs on Windows, whose
platform/keyboard labels and available font fallback differ from the same
reference on macOS. Please expose the captured reference platform/font evidence
in the report and clarify the comparison input for macOS menu/shortcut labels.
The macOS app currently implements the reference's Mac keyLabel behavior.
No substitution or exception is requested or treated as passing.

The b7e6962 reference PNG also includes the browser-only Install button, while
the native client is already an application. Please record the chosen reference
launch mode/URL in capture evidence so this input difference is reviewable.
Fixture member doing_at values still show the real shard time (for example
18:26) instead of fixture.clock, and doing text contains runner-specific
absolute workspace paths (/Users/runner versus D:/a/...). Please make the
fixture's displayed activity data identical across clients, without modifying
exported text after rendering. Exact text mismatches remain failures.

Vector stroke audit: the renderer uses source stroke 1.7 in a 24-unit viewBox,
so a 16-pixel icon has effective stroke 1.7 * 16 / 24 pixels. The reference
extractor currently records computed SVG strokeWidth (1.7 source units), while
macOS records the actual CoreGraphics stroke width. Please define this field
as source or content-window units consistently and retain both source width
and CTM-derived effective width in evidence. This is a units correction, not
a requested tolerance change or icon substitution.

The macOS client is implementing real in-process AppKit/SwiftUI accessibility
tree extraction beside every existing PNG, including sheets/popovers. Please
publish the canonical element JSON shape and reference sample early. Proposed
filename: `<case-file-without-png>.elements.json`; existing PNG manifests and
receipt names remain unchanged. An additional raw AX JSON preserves all nodes
and measurements so matching cannot conceal skipped or unmeasured elements.

The extractor will report content-window-relative top-left coordinates in
logical pixels, role/kind, actual text/name, reading order, state, measured text
font attributes when available, and screenshot pixel samples. Unsupported style
measurements remain null with explicit diagnostics, not copied reference values.
AX-absent painted elements (cards/dividers/chart edges) need real view-bound
inspection in addition to AX; missing instrumentation must fail the coverage
gate. Please include an extraction-coverage diagnostic in the shared schema.

Please define the same visibility rule for reference and both native trees:
ancestor viewport clipping, offscreen exclusion, and occlusion by modal/popover
surfaces. Also define whether an input/button's label is a child text element or
is represented once by its parent's text. Raw trees retain both for audit;
normalization must be common and must not silently discard visible content.

All 504 cases remain required. No tolerance relaxation, approved exception or
scene exclusion is requested. The old native menu/member-card/date/Markdown/
quick-start differences are now mismatches to fix, not accepted substitutions.
The macOS source will consume the shared matcher without modifying shared files.

The shared 5cee956 contract and 82057a3 matcher are now merged. macOS is
emitting the exact schema; unknown measurements are listed in coverage.unmeasured.
Bootstrap 76b18c9 revealed only the NSHostingView root was exported, so those
files are explicitly incomplete, not usable parity evidence. 76879f8 replaces
formal Swift protocol casts with actual informal AppKit accessibility selectors,
retaining selector errors and child classes; its macOS CI is queued.

One shared extraction detail to audit: reference-elements.js currently supplies
computed wrap/foreground values even for paint-only SVG icons/backgrounds with no
text. Native shape drawing has no text-wrapping operation. Please distinguish
inapplicable text-layout properties from unknown measurements consistently on
both sides, documenting the normalization; do not treat a missing native text
measurement as inapplicable. Native exports will keep failures until aligned.

The earlier HTTP framing and document-selection requests below are resolved by
the latest merged `native-apps`; their failure history is retained as evidence.

## Amendment 3 — visual acceptance reopened (active)

The previous functional/route gate is not visual acceptance. macOS is rebuilding
the compact tree, chat/composer, toolbar, inspector, cards and dialogs against
app.css, then capturing the actual native window in CI at all three requested
sizes, both languages and both themes. STATUS.md's earlier completion describes
implementation/contract coverage only; visual acceptance is now outstanding.

Shared integration update: `f4fa186` is merged. macOS now consumes the documented
`fixture`/`cases`/`output` manifest, emits the exact shared filenames and
`complete.json`, and captures real NSHostingView/AppKit controls at one pixel per
point. All 42 scene names are dispatched, including dialogs, native toolbar menu
popovers, recipient picker and mention completion. Smoke capture starts with the
next push; screenshots have not yet been accepted. `composer.voice_title` is
confirmed present in both lists; its pre-load fallback is now blank on macOS,
and the vocabulary XCTest rejects missing source keys in either list.

The original requests below are addressed by the shared harness; no different
manifest format is now requested. Further shared failures will be listed here.

### Shared capture failure resolved in `536d5d9`; native mention fix `44486d8`

Reference job `123420849114` fails at `member-card` before the remaining scenes:
`Page.evaluate: TypeError: Cannot read properties of null (reading 'getBoundingClientRect')`,
`openCard(app.js:1990)`, called by `reference-hook.js` using
`document.querySelector('#head') || document.querySelector('#chat')` (both null).
Please anchor the existing production card to the actual chat header/member control,
with a verified non-null element (`index.html:30` defines `#chat-head`, not `#head`).
No production markup replacement is requested.
The macOS/Windows full captures continue in that run; the seven-scene smoke comparison
passed at `40865319424`. Native apps build/tests passed at `40866008575` (51 macOS tests).
The full 504-case comparison must be rerun after this shared fix.

`536d5d9` is merged; the real `#chat-head` anchor is fixed and the reference now
runs on the Windows runner against its fixture server. macOS independently
confirmed the same native mention stall from `40866009267` (34 PNGs, last `quote`).
`44486d8` replaces the blocking OS spell-completion service with a native
NSPopover/SwiftUI member list, including avatars and keyboard selection. No
mock screen or screenshot-only UI is used. Full capture is being rerun.

### Active: Windows HTTP startup failure, repeated in three full runs

At `fc4fd58`, all four macOS shards and three Windows shards completed, but
Windows zh-CN/dark failed before native capture with `HttpRequestException:
Received an invalid status line: '<!DOCTYPE HTML>'`, from `Client.Get` lines
63/64 and `MainWindow.<.ctor>b__185_12` line 132. Please inspect the shared
server's HTTP connection framing/response and the Windows startup request.
This is a different failure from the earlier menu automation access violation.
The run's failed job log and `visual-windows-zh-CN-dark` artifact preserve evidence.
No macOS route or manifest change is requested; another full comparison follows
the shared repair. Native builds/tests/parity passed at `40877622668`.

Static diagnosis: Windows `Client.Post` uses `PostAsJsonAsync`, whose streaming
JSON content can use `Transfer-Encoding: chunked`. `Handler._body` only reads
`Content-Length`; absent length becomes `{}`, leaving chunk bytes in the reused
HTTP/1.1 connection. The next GET can then receive Python's HTML parser error.
Please send the serialized UTF-8 body with an explicit/computable Content-Length
(e.g. buffered JSON StringContent), and add a CI regression for POST then GET on
one keep-alive connection. macOS already assigns Data to URLRequest.httpBody.
This diagnosis is source-based; no local server or test was run.

The same error reproduced in `40880037477` (zh-CN/dark), then `40882519398`
(zh-CN/dark, en-US/light, en-US/dark). It is not limited to one locale/theme.
All reference captures complete before this Windows startup error. The latest
macOS source is `f7a6bfd`, with 57 passing XCTest cases and native builds/parity
green at `40882519547`; its full native captures are independent of this failure.

### Active: capture a selected document in the shared `documents` scene

The 42-scene English/dark comparison at `40875042406` shows empty document bodies
in reference and Windows while macOS selects the first document and shows its
revision/body. Please make `documents` exercise the real document detail on all
clients. After `await openDetails('docs')`, the reference can click the actual
`.details .left .chat-row` button (verify the enclosing details class from
`app.js:2390`), then wait for `.doc-body`. Windows should invoke its existing
first-document selection. Do not replace the renderer or inject body markup.
The API is unchanged: `/api/org/<id>/document?key=review-plan` (use existing
`orgPath('/document?key=' + enc(key))`, not a new route). macOS already invokes
that real GET when DocumentsView selects the first key. No missing fixture data.

### Shared visual review note addressed: Settings row structure

The macOS Settings profile/notify/voice/about note from `2494e9d` is applied.
All seven settings sections now use compact native rows: label and helper text
on the left, controls on the right; avatar/name controls share their own row,
voice uses an inline microphone, and adapter diagnostics use expandable cards.
The runtime controls and API payloads are unchanged. macOS also adopts the
exact reference UInt32/Unicode avatar hash and HSL palette from `612e97c`. CI capture review follows
with the next full run; the old stacked Form screenshots are not final evidence.

### Fix merged in `e4bb502`, awaiting capture: Windows automation peer crash (`40873502291`)

All four Windows shards at `fdee097` exit `3221225477` without `complete.json`.
Reference captures complete all 126 files per shard. Downloaded Windows
`data/en-US/light/client.log` reports `System.AccessViolationException` at
`IExpandCollapseProviderMethods.Collapse`,
`MenuBarItemAutomationPeer.Collapse`, `MainWindow.CaptureVisuals`.
Please avoid collapsing a closed/unrealized native MenuBar automation peer and
repair the actual menu capture path. macOS shards are still running independently.
The shared owner replaced direct automation peer calls with CI desktop input in
`e4bb502`, now merged. The full comparison is being rerun against that fix.
Local diagnostic: `S:/Codex/Outputs/Relic-native-visual/iteration-09/visual-windows-en-US-light`.

### Resolved in `6391291`: shared localized platform diagnostic

The Chinese `settings-harness` capture shows the English built-in diagnostic
`No private host-supplied desktop socket; open a chat with the Relic plugin loaded`.
This is `GET /api/platform` → `desktop_transport.reason`, displayed by both native
clients as server content. Please move this fixed diagnostic to the shared word
lists and localize the existing `reason` field using the selected language. Keep
the current response shape; macOS calls `/api/platform` and reads
`platform["desktop_transport"]["reason"]`. Do the same for other fixed diagnostic
reasons in that response. Provider IDs and user-supplied paths remain data.

### Resolved in `441e6a7`: shared Windows capture regression `40868069780`

With shared `536d5d9`, reference capture now completes the first 126 zh-CN/light
cases. The Windows client then reports `COMException (0x800F1000): No installed
components were detected` at `UIElementCollection.Add`, `DrawSidebar()` in
`SidebarCopies.cs:41`, via `Select`/`Refresh` for each scene. macOS is still
capturing independently. Please repair the Windows capture failure before the
full comparison rerun; the reference anchor issue itself is resolved.

### Resolved in `6391291`: reference `plain` scene state correction

Visual review of `40868069780` reference `zh-CN-light-1024x700-plain.png` shows
the on-state toolbar label but original messages, with no fixture translation.
`renderStream()` (`app.js:827`) overwrites `S.plainMode` using `plainOn()`.
The hook currently sets only `S.plainMode = true`. Please call
`save('relic.plain.' + S.orgId, true)` before the existing fixture `S.plain`
assignment and `renderAll(true)` (and reset that preference for other scenes).
This uses the production renderer and avoids invoking a provider. macOS already
renders the injected translation plus the expandable original in this scene.

`6391291` is merged. The shared owner supplied localized GET/POST platform
reasons, real-format transcript/session fixtures, the plain preference fix, and
four language/theme shards per platform. The manifest remains unchanged.
macOS has confirmed actual mention-popup visibility in `c82262b` captures and
now fails that capture if the native NSPopover is absent. No new API is needed.

Original shared owner requests (superseded by `docs/native-visual.md`):

1. Supply the shared fixture/server and scenario manifest, and invoke the macOS
   capture entry point from the visual workflow. Proposed interface:
   `RELIC_VISUAL_MANIFEST=/absolute/manifest.json RELIC_VISUAL_OUTPUT=/absolute/pngs
   /path/Relic.app/Contents/MacOS/Relic` (CI only).
   Manifest: `{ "port": 39321, "token": "...", "org": "fixture-org",
   "member": "analyst", "thread": "12", "file": "/fixture/plan.md",
   "scenarios": [{"id":"group", "screen":"group", "lang":"zh-CN",
   "theme":"light", "width":1440, "height":900}] }`.
   Per-scenario fields can override org/member/thread/file and specify `sheet`,
   `pane`, `settings_section`, `detail`, `member_mode`. Captures will use the
   shared real HTTP API, not duplicate fixture data in Swift. Output naming:
   `<id>--<lang>--<theme>--<width>x<height>.png`, plus capture-results.json.
   If your manifest differs, document its exact format; macOS will adapt.
2. Produce shared reference captures and compose reference | Windows | macOS
   images, upload artifacts, and run the visual workflow on native-macos too.
   Include every page/dialog and long-content fixtures, at 1440x900, 1280x800,
   1024x700. Native capture is allowed only inside CI; no local launching.
3. Add/fix `composer.voice_title` in BOTH server word lists (the reference and
   both clients use it). Add shared tests rejecting every actually-used native
   key absent from either list, including dynamic families. macOS also adds an
   XCTest vocabulary check loading the actual lists from the repository.

## Resolved handoff (2026-10-29, shared `4c26286`)

All shared requests are resolved and merged. The shared owner reviewed all 34
screen/flow rows and 214 named reference functions as implemented. The local
static gate now reports zero missing keys/routes, zero incomplete flows and no
browser UI uses. `fe5c5a3` passed the complete Native apps workflow (parity,
macOS and Windows): https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40837118720.
The macOS Release build, **49 tests**, and unsigned app packaging passed in job
https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40837118720/job/123324399176.
This integration includes `native.episodes`, icon/language metadata, and the final
dictation-at-selection correction (original suffix preserved, interim results
replaced, UTF-16 caret, focus restored). No shared changes are requested.
`STATUS.md` contains all 34 screen/flow rows, 214 function mappings, test evidence
and the separate real-Mac acceptance checklist. No PR was opened by this session.

`Words.list` now uses `list.pair`, `list.middle`, `list.end` for recipient/member/
approver/rule-scope lists, with English and Simplified Chinese tests. Native
divider measurements persist sidebar/panel widths and the separate File width.

## Historical review follow-up (after `467fa95`, resolved)

The macOS Release build, **39 tests**, and unsigned app packaging passed at
`73a2c49`: https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40834159051/job/123314926758.
The latest push adds seven regression tests (46 total intended), currently in CI.
Static scan: zero missing routes and zero missing keys after shared substitutions.

Review follow-ups from `258e3d8` are implemented in `467fa95`:

- `Client.refreshRecord` reads the `RELIC_HOME/app.json` provider, verifies
  app/state/port/pid/instance using its token, and adopts the new loopback transport.
  SSE reconnect refreshes it. POST retries only an explicit HTTP 403
  `{"error":"missing token"}`, once; network errors and other rejections never
  replay a write. Four mocked transport tests cover renewal and rejection.
- Quote-only group/private/thread sends work; thread sends have a model-level
  duplicate-submission lock. Speech is exclusive across fields and stops on
  send/navigation/modal changes. Tests cover quote-only dispatch/failure and
  thread `reply_to`/duplicate Enter. Newer drafts/quotes/recipients are retained.
- Removed the ignored protocol `supersedes` control/payload. Shared native
  strength/rules labels and Windows field order are applied; the engine handles
  strong-rule validation. `summary_for_person` and `inherit` remain.

The shared owner subsequently reviewed and promoted these function and screen
rows; the first implementation review was recorded in `258e3d8`.

## Final bundle metadata request (resolved in `028e270`)

`native/macos/Resources/Relic.icns` packages the existing reference 512px PNG
unchanged into Apple's ICNS container (no new artwork). In `scripts/native_package.py`
copy it to `Relic.app/Contents/Resources/Relic.icns` and set
`CFBundleIconFile: "Relic.icns"`; Finder and Dock should use the same Relic identity.
Set `CFBundleDevelopmentRegion: "en"` and `CFBundleLocalizations: ["en", "zh-Hans"]`
so native system controls use the supported bundle languages on other-language Macs.
Add shared `native.episodes: "Episode"` in both approved word lists to remove the
reference's last literal section title from native source (same wording).
The Mac retains a Dock process when its last window closes and reopens that window
on Dock click; **Quit** releases the engine lease. Please reflect that platform
distinction in `docs/native-install.md` rather than saying closing the last Mac
window stops the engine.

Resolved already: native speech keys/privacy metadata, per-platform CI, inventory
corrections, explicit Enter/Shift-Enter semantics and justified vocabulary
substitutions. The older request rationale below remains for traceability.

## Native speech bundle metadata (required)

The SwiftUI composer uses `SFSpeechRecognizer` and `AVAudioEngine`, only after the
person clicks the microphone. Add `NSSpeechRecognitionUsageDescription` and
`NSMicrophoneUsageDescription` to the macOS app bundle Info.plist in
`scripts/package.py`, plus `en.lproj/InfoPlist.strings` and
`zh-Hans.lproj/InfoPlist.strings`, sourced from the shared i18n word lists.
Without these privacy strings macOS terminates the app when speech is requested.
Add shared keys `native.speech`, `native.speech_permission`,
`native.microphone_permission`, `native.speech_unavailable`. The first labels the
native speech setting; the next two are the OS prompt text; the last is the error.
Native client keeps the engine's existing `voice: "browser" | "off"` preference
for compatibility, but uses Apple Speech, never a browser implementation.

## Inventory corrections (required)

Include search within session choices, unread/recent chats, persisted per-chat
drafts/recipients/quotes, read-by disclosure, chat history pagination, native
Markdown links with local file/line navigation, protocol check examples, and
task report/evidence links in the corresponding existing rows. Reference
`document` renders `body` (not just the contract's `text`). The client supports both.

## CI parity (required)

Run parity checks on `native-macos` pushes and expose macOS-specific results.
Native package installation replaces PWA/service-worker/install-window routes.
Browser-only setup/voice labels must be replaced by the native equivalents above;
standard Edit/Window menus are provided by AppKit. Do not count inert key/route
lists as implementation coverage. Swift build and XCTest remain the macOS gate.

## Workflow ownership

If a Windows build/test or shared engine/parity check fails on `native-macos`, fix
it on `native-apps`; this branch will merge that branch without changing your files.

## Parity checker ownership issue and explicit native substitutions

At `8210b43`, the parity job fails both clients together and every function row
in `docs/native-apps.md` is still pending. The macOS session cannot change that
file. Please consume `native/macos/STATUS.md` mappings when updating the macOS
column, and expose a per-platform check (`--platform macos`) so an unfinished
Windows row does not prevent the macOS build from proving its own gate.

Please add **per-platform** justified vocabulary substitutions, rather than
requiring dead strings in Swift. The macOS alternatives are:

* All `install.*`, `appbar.install`, `appbar.install_tip`,
  `appbar.install_tip_mac`, `appmenu.install_app`, `settings.install`,
  `settings.install_app`, `settings.install_app_hint`, `settings.installed`:
  Finder `.app` installation and the existing shared `settings.install_app_done`
  About row replace the browser/PWA installation tutorial. No browser installer.
* `settings.voice_browser`, `settings.voice_edge`, `settings.voice_supported`,
  `settings.voice_supported_mac`, `settings.voice_unsupported`,
  `settings.voice_wechat`, `composer.voice_unsupported`, `composer.voice_denied`:
  native `SpeechInput` uses Apple Speech/AVFoundation and native permission keys;
  browser address-bar and Windows/WeType instructions are inapplicable.
* `work.open_in_explorer`: `work.open_in_finder` is the same action on macOS.
* `member.note_host`, `member.note_existing`: use the already-shared macOS
  variants `member.note_host_mac`, `member.note_existing_mac`.
* `appmenu.undo`, `appmenu.redo`, `appmenu.cut`, `appmenu.paste`,
  `appmenu.select_all`, `appmenu.paste_failed`, `appmenu.paste_need_field`:
  AppKit's standard Edit actions and responder-chain validation implement these;
  there is no browser clipboard-permission failure. `common.copy` is used by
  explicit message/file copy buttons.
* `appbar.menus`, `appmenu.edit`, `appmenu.view`, `appmenu.help`: native macOS menu
  groups replace the web toolbar's menu-popup scaffolding.
Notification authorization now handles both denial and UserNotifications service
errors with shared `settings.notify_denied` / `settings.notify_unsupported` keys;
no notification-key exception is required.

All other vocabulary is integrated into matching controls, status formatting,
accessibility labels, errors and success states. The Enter/Shift-Enter labels
are used directly and require no exemption.


## File JSON display order (2026-10-29, after e0bbd64)

Please add `display_text: string` to `GET /api/fs/read?path=...` for `kind == "json"`.
The reference parses the file and applies `JSON.stringify(parsed, null, 2)`: preserve
object insertion order except JavaScript array-index ordering, use JS numeric display,
and do not sort ordinary keys. macOS reads `display_text` when present, otherwise keeps
the original text, which is an explicitly remaining mismatch. The previous client-side
JSONSerialization `.sortedKeys` changed the visible order and has been removed. A shared
formatter avoids introducing another JSON parser/number formatter in the native client.
Existing raw `text`, truncation, size, path, and filesystem authorization stay unchanged.


## Brand vocabulary and reference code-line order

The empty conversation header renders the reference's literal `Relic`. Please supply
`common.app_name: "Relic"` in both word lists and use it in that reference header/title
so the client can remove the remaining brand literal without displaying a missing key.

Reference file-code extraction currently emits a line's text before its `::before`
line number (e.g. 4e18fc3 en-US/light/1440x900 file-code). Please audit that against the
required reading order: painted number is to the left, then source text. Keep both
actual elements and bounds, with no exclusions; do not simply waive the order error.
