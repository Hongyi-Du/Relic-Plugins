# Textarea resize scene and measurement evidence

`new-org-textarea-resized` is appended to the existing 52 scenes. The full
matrix is now 53 scenes × 3 sizes × 2 languages × 2 themes = 636 cases per
client. The diagnostic smoke set retains all 16 earlier scenes and appends
this state, giving 17 cases at zh-CN/light/1440×900. Smoke is not acceptance;
no existing scene, mismatch or tolerance is removed.

## Production control and actual action

`plugins/relic/app/static/app.js` constructs the new-organization purpose
control with `h('textarea', { rows: 3, placeholder: t('neworg.purpose_placeholder') })`
inside the real dialog's `.form .field`. Its form CSS supplies the border,
padding and width but does not disable resizing. The separate composer rule
sets `resize: none`; it must not be used to infer the form control's behavior.
The capture reads the live `getComputedStyle(textarea).resize` before acting.

The scene opens the existing `new-org` dialog and resolves exactly one
`#layer .dialog[role='dialog'] .form textarea`. After fonts and two animation
frames settle, it records the actual textarea border box, value, text content,
placeholder, rows, focus/hover state, resize mode, overflow, writing mode,
client/scroll metrics and actual inline style. It never fills the field or
changes DOM, CSS, dimensions or application state through JavaScript.

The shared operation recipe is:

1. Require the actual textarea's `horizontal-tb` and `ltr` layout and a vertical
   resize-capable computed mode. Other layouts fail rather than inventing a
   different grip location.
2. From its measured border box, request the pointer at
   `(x + width - 3, y + height - 3)` in window CSS pixels.
3. Press the real left mouse button, move vertically by `+64` CSS pixels in
   eight steps, then release. The release runs even if a move fails.
4. Settle actual fonts and two animation frames; read the same textarea again.
   Its real height must have increased and value/text/placeholder must be
   unchanged. Record the measured `x/y/width/height` delta without replacing it
   with the requested delta. A centered dialog can move as its field grows.
5. Keep the resulting pointer and production state through the PNG, DOM,
   accessibility, font and element capture. Do not move the pointer away after
   the action or temporarily change animations for the screenshot.

These are real browser input calls, using the documented viewport CSS-pixel
coordinate system and interpolated mouse movements. The requested point is an
**action coordinate, not measured resize-handle geometry**. Successful resizing
proves the action affected the control; it does not reveal every painted pixel
of the grip. [Playwright Mouse API](https://playwright.dev/python/docs/api/class-mouse)

The passive event observer retains the actual document pointer/mouse events,
`isTrusted`, coordinates, buttons, timestamps and real target association.
Browser-internal resize tracking can consume events; absent events remain
absent and are not synthesized. Any observed untrusted event fails this action.
The recipe/command receipt is kept separately from document event receipts.

Native clients should perform the same real corner gesture against their own
measured production textarea bounds, retain actual native event/control
receipts, and compare resulting geometry normally. A scene flag, a direct
height assignment or a fabricated resize-handle box cannot substitute for
the operation. Unsupported production resizing remains a failed scene.

## Captured evidence and stable-state checks

`<case>.scene-action.json` contains the before/after observations, requested
pointer path, actual events, geometry delta, before/after pierced DOM and full
AX trees, and all capture checkpoints. The same capture-phase receipt is
included in `elements.json` as `capture_evidence.textarea_resize_action`.
Checkpoints run after the action, before/after the screenshot, after the DOM
snapshot, after other source evidence, and after element extraction. A changed
control identity, geometry, value, placeholder, style/state or pointer receipt
fails capture and leaves the changed observation in the sidecar.

The current reference extractor adds `raw_nodes[].resize_handle` for each
visible textarea with a computed resize capability, even when it has no
overflow. This is independent of the existing scrollbar evidence. It retains:

- the actual owner border box and textarea metrics;
- the computed `::-webkit-resizer` values, explicitly labeled as a pseudo-style
  query, not painted existence or pixels;
- actual matching DOMSnapshot pseudo records, if the browser exports any;
- the real textarea AX owner and descendant records;
- `kind: "resize-handle"` in the evidence, with `painted_presence`, `bounds`,
  `style` and `state` all `null` until independently measured.

No canonical visible resize-handle rectangle is created from the owner box,
the requested corner, a fixed 15×15 size or a computed pseudo width. Every such
unmeasured affordance appends `resize_handle.rendered_part` to
`coverage.unmeasured` and `ua_resize_handle_measurement_unavailable` to
`extraction_errors`. Thus the gate fails; a missing measurement cannot make
either native client appear to match. Existing measured control boxes remain
intact.

## What the existing CI evidence does and does not establish

The retained artifact
`parity-1e3b7c5/elements/reference/en-US-light-1440x900-new-org.elements.json`
contains actual textarea owner `dom-505`, AX node/backend ID `766`, with
border box `(482, 416.09375, 476, 76)`, `rows=3` and the real English purpose
placeholder. Its AX role is `textbox`. That artifact contains no independently
identified resizer DOM node or resize-named/typed AX node; its owner's
`scrollbar` evidence is null. These observations demonstrate why checking only
overflow misses the resizable form control. They do not establish that the
browser painted no grip, or that a guessed corner rectangle is correct.

CSS defines `resize` as control over a user-agent resizing mechanism; that
capability is distinct from the mechanism's implementation-specific paint.
CDP's snapshot exposes DOM/layout and optional element rectangles; those
rectangles alone are not a generic API for anonymous UA paint. The new scene
retains pierced DOM/AX and snapshot records so any actually exported grip
can be audited, but the current collector has no independently verified grip
paint/geometry provider. It therefore preserves nulls and a measurement
failure. [CSS UI resize](https://www.w3.org/TR/css-ui-4/#resize),
[CDP DOMSnapshot schema](https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/DOMSnapshot.pdl)

The new drag path and measurement gap tests are pure mock/fixture tests for
CI. Their success cannot establish that the actual browser drag worked or
that native resizing matches. Only the new CI action receipts, screenshots
and element gate can provide that evidence. No local browser, application,
server, input action or test run is needed to prepare these changes.
