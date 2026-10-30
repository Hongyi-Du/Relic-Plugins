# Native Relic App contract

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
