# Requests to the shared/native-apps owner

The macOS session owns only `native/macos/**`. Please merge this branch regularly.

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

### Shared visual review note addressed: Settings row structure

The macOS Settings profile/notify/voice/about note from `2494e9d` is applied.
All seven settings sections now use compact native rows: label and helper text
on the left, controls on the right; avatar/name controls share their own row,
voice uses an inline microphone, and adapter diagnostics use expandable cards.
The runtime controls and API payloads are unchanged. CI capture review follows
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
