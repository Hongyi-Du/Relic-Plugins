# Independent outline evidence

Outline paint is separate from the layout border. The matcher reads
`style.outline` on every emitted element. Missing fields and `null` remain
measurement failures; absence of a WinUI CSS-like property does not establish
absence of rendered outline/focus paint.

The shared shape is either the string `"none"`, accompanied by
`evidence.outline.absence_proven: true`, or this measured object:

```json
{
  "style": "dashed",
  "color": [27, 27, 26, 255],
  "width": 1.5,
  "offset": -1.5,
  "dash": null,
  "dash_offset": null,
  "contour": null
}
```

The values above illustrate the fields; extractors must supply their actual
measurements. In particular a CSS declaration of `1.5px` is not a substitute for
the captured computed value. Width, offset, dash lengths and phase are in window
pixels. Color is measured RGBA in the existing 0–255 channel convention.
`evidence.outline` retains source/API, raw values, owner bounds, transform/zoom
evidence, and measurement failures. CSS `auto` does not establish its actual
paint from `outline-width`/`outline-color`; preserve those raw computed values
and leave unmeasured canonical values unknown.

The reference extractor may prove `none` from actual `outline-style: none`, or
a zero used width of a supported explicit non-auto style. Native extraction
needs actual evidence that its current production paint/owned template did not
render a separate outline, including current focus/hover state. It must not
default every missing field to `none`, use border width zero as proof, or treat
an absent measurement API as proof. The boolean assertion is meaningful only
with that producer evidence; the matcher does not manufacture it.

Absence is scoped to the actual paint operation, not to the entire window.
An identified ordinary native primitive can establish its own fill/border/stroke
contract without another raster experiment. Children and separately attached
Composition/focus paint retain their own owners and obligations. Windows is
adding actual focused-object relationships, full FocusState, UseSystemFocusVisuals
and GetElementChildVisual observations; missing or unsupported attachments stay
unknown. A child being Unfocused alone does not exclude its parent's focus visual.
For macOS, a recorded surface may prove its own outline branch absent from the
same actual production optional outline value and bound owner. That does not
prove absence of another AppKit focus ring or SwiftUI overlay. No extra hashing
or whole-window pixel attribution is required to establish an identified
primitive's own paint contract.

## Pattern and contour coverage

Solid outlines use `dash: []` and `dash_offset: null`; phase is inapplicable to a
continuous line. Dashed/dotted outlines require independently measured nonempty
dash segments and a finite actual phase. The matcher never derives a pattern
from the word `dashed`, sets unknown phase to zero, or assumes that native
`[3,3]` matches the browser's paint. All active outlines also require their
actual painted contour. Computed CSS and the owning element's rectangle alone
do not prove that contour, particularly around rounded corners.

The strict contour representation uses actual absolute SVG path coordinates:

```json
{
  "coordinate_space": "window",
  "paths": [{"d": "M10 12L110 12L110 32L10 32Z"}]
}
```

It accepts finite absolute `M/L/C/Q/Z` paths, preserving subpath/segment order.
Unknown fields, incomplete paths, alternative coordinate spaces, and currently
unrepresented path commands fail. Extractors may not create this path from an
expected rounded rectangle. Until they can observe the actual contour, `null`
is the accurate value and remains a failure.

The existing macOS `native_outline` receipt is consumed for its actual width,
color, offset and dash values if no canonical outline exists. The raw receipt
is unchanged. Missing style category, phase and contour remain unknown; the
legacy receipt does not become complete merely because its known values match.
Producer integration should emit the full canonical object and remove an old
“comparison unimplemented” diagnostic only when replaced with current measured
coverage. An incomplete canonical object continues to fail.

## Comparison rules

No parity tolerance was changed. Width/offset, pattern lengths and phase compare
exactly, following the existing zero border-width/style tolerance. Colors retain
the existing Delta E 76 ≤ 3 threshold and exact alpha. Contour coordinate pairs
use the existing geometry tolerance for the reference owner's corresponding
dimension: 4 pixels, or 3% when that dimension exceeds 130 pixels. Different path
topology remains a paint difference. Missing evidence contributes extraction
errors even when both platforms contain the same `null` values.

`outline_paint.py` performs these checks independently of border fields.
`test_outline_paint.py` contains pure fixtures for absence proof, separate
border/outline ownership, missing dash/phase/contour, raw native preservation,
invalid values, exact pattern changes, geometry thresholds, and color/alpha.
Tests are CI-only; no application or desktop capture runs locally.

## Exact icon-content pairing

After the existing exact text/name anchors, the matcher may use independently
decoded `svg` or strictly validated `vector-image-v1` content within the same
region as an additional pairing anchor. Unique occurrences are processed first;
repeated identical content pairs in each client's actual reading order. It uses
the existing identity decoder without an icon-equivalence table, URI lookup,
font-name guess, or geometry-based nearest-neighbor search. Unvalidated image
URLs, font glyph labels, malformed trees and incomplete image descriptions do
not qualify.

This changes correspondence selection only. Surplus elements remain eligible
for missing/extra reporting; all paired elements still undergo kind, region,
text/name, reading-order, geometry, style and state comparisons. Swapping two
valid icons therefore exposes the order difference instead of making shifted
position pairing compare each icon against the wrong neighbor. No element,
scene, mismatch category, exception, or tolerance is removed.
