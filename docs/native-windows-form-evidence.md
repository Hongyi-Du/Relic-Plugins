# Windows member form evidence

The reference remains `2007a83`; the following observations do not change the
matrix, matching tolerances, or the acceptance gate.

## Visible reference defect: member-edit `null`

The `member-edit` reference contains a visible literal `null` below the environment
variables textarea. This is present in both the captured pixels and the element
tree, not just an extraction artifact:

- `S:\Codex\Outputs\Relic-native-visual\parity-1c3b037\images\reference\en-US-light-1440x900-member-edit.png`
- `S:\Codex\Outputs\Relic-native-visual\parity-1c3b037\elements\reference\en-US-light-1440x900-member-edit.elements.json`
- The text bounds in that capture are `(432, 751.984375, 22.640625, 19)`.

`memberDialog` calls the DOM's `form.append(..., edit ? null : ...)` directly;
the DOM converts that `null` argument to a text node. The app's own `append`
helper filters nulls, but is not used at this call site.

The Windows native form does not add this literal. It therefore currently lacks
that visible text, and the element gate must continue to report the mismatch.
No exception has been added, and the reference has not been changed. A decision
about correcting or retaining that baseline belongs to the person.

## Native form changes awaiting CI measurement

`Members.cs` now uses native segmented controls, radio choices, text inputs,
dropdowns, switches, session rows, and buttons in the reference's order. The
form has a 620 px outer width, 22 px padding, 14 px outer gaps, 12 px field gaps,
and a scrollable height limited to the window height minus 60 px. The reference
CSS makes its form switches a vertical track then label; the native form follows
that visible layout.

Host model and existing-seat inputs have stable automation IDs `member-model`
and `member-seat-name`. Their normal keyboard interaction opens a native
Popup/ListView on Down, including when the input is empty; typing filters the
actual server-provided options, Enter or a click accepts a value, and Escape
closes the popup. The capture uses this production interaction.

These code changes are not evidence of a passing element comparison. In
particular, native dropdown and suggestion-popup geometry, text wrapping,
selection/focus states and theme rendering still require the new CI captures.
