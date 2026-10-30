# Message hover and Copy-toast capture contract

The shared matrix adds `message-hover` and `message-copy-toast`, after all 50
existing scenes. No existing scene is removed or reordered. The full matrix is
52 scenes x 3 sizes x 2 languages x 2 themes = 624 cases per client.

The diagnostic smoke run retains its original 11 scenes and adds
`member-card-rename`, `member-card-model`, `member-card-avatar-hover`,
`message-hover`, and `message-copy-toast`: 16 cases at zh-CN/light/1440x900.
This exposes failures of the new actual controls early. Smoke is a diagnostic
subset, not acceptance; the complete 624-case gate remains required.

Both scenes start in the real group conversation and use the message whose
actual ID is `fixture.thread`. The reference navigates through the existing
`group` hook, then uses Playwright's real pointer action on
`.msg[data-id="<fixture.thread>"]`. It does not set a hover class or a scene flag
in application state. Keep the pointer at the target throughout capture;
the normal neutral-pointer movement happens before this action, never after it.

For `message-hover`, retain the actual `.hover-acts` toolbar, its controls,
icons, labels, states and paint. For `message-copy-toast`, click that toolbar's
actual Copy button, identified by the live `/api/i18n` `common.copy` title.
The expected message body is independently read from the real group chat API.
Success requires the actual clipboard to contain that body and the real toast
to display `/api/i18n` `msg.copied`. No clipboard writer, timeout callback,
message body, DOM node or toast text is replaced by the harness.

The headless reference context grants `clipboard-read` and `clipboard-write`
only for the fixture's local origin through the documented
[Playwright permission API](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-grant-permissions).
It records the requested permission grant and both real clipboard reads, then
clears the context's permission overrides during cleanup. This is CI-only;
no local clipboard or installed application is accessed.

## Stable timer and pointer evidence

Production `toast()` creates a real `role=status` element and schedules its
removal after 3,600 ms. Full font and source collection may take longer than
that. After the real Copy click has already created its success toast, the
reference uses the actual browser
[`Emulation.setVirtualTimePolicy`](https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Emulation.pdl)
command with `policy=pause`. It records the original command receipt, including
`virtualTimeTicksBase`, real Date/performance readings before and after the
command, and host monotonic time. Missing CDP receipts fail capture.

This pauses the browser's virtual time source; it does not replace the
production timeout or repeatedly trigger Copy. The remaining production
timeout delay is not exposed by this CDP command, so `toast_remaining_ms`
stays null with an explicit measurement reason. It is not filled with the
initial 3,600 ms duration or an inferred value. Canonical element measurements
continue to come from the live controls, DOM/AX and screenshot.

The reference retains handles to the same message and toast objects. A passive
capture listener records trusted pointer/click events, coordinates, target
message ID and event timestamp without changing DOM or application state.
The capture records and checks the same actual message, visible toolbar,
pointer position, toast identity/text/style/bounds and clipboard at these
boundaries:

1. After the real action and before the screenshot.
2. Immediately after the screenshot.
3. After the real DOMSnapshot.
4. After AX, input-text and platform-font collection.
5. After canonical element extraction.

Changes, lost hover, an expired/replaced toast, unknown trusted-pointer
evidence, changed clipboard, or advancement of the paused performance clock
fail capture. The actual failing observation remains in the receipt; no value
is substituted to match the earlier state. Message scenes use screenshot
`animations=allow` so screenshot preparation does not temporarily change the
captured state. The receipt is `<case>.scene-action.json`; successful element
output also contains `capture_evidence.message_action` with its capture-phase
observations. The sidecar additionally retains the later cleanup receipt.

Cleanup resumes virtual time with `policy=advance`, records that CDP receipt,
removes the passive listener, releases handles and closes the isolated page
target. Cleanup runs after failures too. No capture-only setting leaves the
production toast permanently alive, and normal application expiration behavior
is unchanged outside the isolated CI target.

## Native requirements and validation boundary

Both native captures must perform their real pointer and Copy actions against
the production message identity, preserve the actual pointer, and retain
actual clipboard/toast evidence. If source collection exceeds the toast's
lifetime, pause the actual timer/clock that owns the production toast and
record the before/after state and remaining time when the platform can measure
it. Restore that timer during cleanup or dispose the isolated capture instance.
A capture flag which bypasses expiration, a replacement permanent toast, a
synthetic clipboard success, or repeated Copy clicks does not satisfy this
contract. An unavailable measurement stays unknown and a state-continuity
failure remains a failed capture.

The shared integration includes pure mock tests for trusted actions, actual
readbacks, pause/resume cleanup, state drift and phase ordering. These tests run
only in CI. This document specifies the required runtime evidence; it does not
claim that the newly added native/reference scenes have already passed a CI
capture or the parity gate.
