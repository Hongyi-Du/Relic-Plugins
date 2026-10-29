# Requests to the shared/native-apps owner

The macOS session owns only `native/macos/**`. Please merge this branch regularly.

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
* `shortcuts.send_newline`, `composer.send_title`: reference says Enter sends,
  but the agreed native contract uses Command-Enter / Control-Enter. Please add
  `native.send_shortcut` and `native.send_newline` and exempt these misleading
  browser labels for macOS. Current code uses the shared `common.send` action.

All other missing vocabulary is being integrated into the actual matching
controls, status formatting, accessibility labels, error and success states.
