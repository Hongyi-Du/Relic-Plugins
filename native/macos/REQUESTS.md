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
