## 2026-10-29: live matrix consumption and shared extraction failures

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
