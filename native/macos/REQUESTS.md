# Requests to the shared/native-apps owner

The macOS session owns only `native/macos/**`. Please merge this branch regularly.

## Resolved handoff (2026-10-29, shared `028e270`)

All shared requests are resolved and merged. The shared owner reviewed all 34
screen/flow rows and 214 named reference functions as implemented. The local
static gate now reports zero missing keys/routes, zero incomplete flows and no
browser UI uses. `327ccdf` passed the macOS Release build, **47 tests**, and app
packaging: https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40835781285/job/123320115882.
This final integration uses `native.episodes` and includes shared icon/language
metadata. No further shared changes are requested. Latest-head CI remains the
release-candidate validation gate; the person's real-Mac review remains separate.

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
