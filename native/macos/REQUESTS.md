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
