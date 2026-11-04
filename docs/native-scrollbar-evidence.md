# Reference scrollbar evidence

This contract distinguishes the scrollbar's reserved layout gutter, a thumb's
outer part box, its hit rectangle, and its visible ink. They are separate
quantities. A PNG ink envelope never supplies a transparent outer or hit box.
Unknown measurements remain failures in the element gate.

## Actual source and quantities

The reference captures the production page and its original PNG. It does not
change the app's scrollbar CSS, redraw the scrollbar, or render a replacement
image. `reference-elements.js` retains the visible owner's identity, bounds,
client/offset/content dimensions, scroll offsets, direction, writing mode,
ancestor effects and actual computed values for all seven WebKit scrollbar
pseudos. These computed values are style requests; they do not prove that a
pseudo has a painted part or supply its actual part rectangle.

The `8b5bfce` Windows reference smoke capture contains these real measurements
in `zh-CN-light-1440x900-group.elements.json`:

| Owner | Actual border box | Client size | Offset size | Scroll extent and offset | Reserved gutter |
| --- | --- | --- | --- | --- | --- |
| `dom-171`, `#stream` | `(276,96,824,698)` | `814 × 698` | `824 × 698` | height `907`, top `209` | `(1090,96,10,698)` |
| `dom-326`, right pane content | `(1101,84,339,816)` | `329 × 816` | `339 × 816` | height `1918`, top `0` | `(1430,84,10,816)` |

Both owners report `clientLeft = clientTop = 0`. Their gutter dimensions follow
from the actual integer client/offset measurements and border widths. The
source artifact is
`S:\Codex\Outputs\Relic-native-visual\smoke-8b5bfce-reference-zh-light\`;
[the CI run](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40994609011)
completed these reference captures. These observations do not establish the
new extractor's CI result or a parity pass.

The extractor uses the exact untransformed, integer case only. It requires an
unambiguous reserved side, positive area, no zoom/transform, horizontal writing
mode, and agreement with the actually computed scrollbar thickness. Fractional
or rounded layout, overlay scrollbars, ambiguous reserved sides and nonstandard
writing modes leave gutter geometry unknown. A missing gutter is never proof
that a scrollbar is absent.

Each actual scroll axis produces a `scrollbar` and a `scrollbar-thumb` obligation
in `elements`, ordered after that owner's content. The scrollbar's measured
gutter may populate its `bounds`, with the quantity explicitly stated. The thumb
`bounds`, `visible_bounds`, `evidence.outer_bounds` and `evidence.hit_bounds`
remain `null`. Its name, part hover/focus state, resolved paint and radii are not
invented. `ua_scrollbar_part_measurement_unavailable` and corresponding coverage
failures remain for both parts.

`state.orientation` comes from the actual overflowing axis.
`state.scroll_position` is the actual scroll offset divided by the actual range
only for a known non-reversed coordinate convention and an in-range offset.
That ratio is state evidence, never thumb position or length. Unsupported or
ambiguous coordinate conventions keep the normalized value unknown.

## Original PNG readback

`scrollbar_pixels.py` runs after the original screenshot and DOM extraction. It
decodes the existing RGB/RGBA PNG at the captured viewport's exact 1:1 scale;
there is no resampling, drawing, browser mutation or additional render. For
each measured gutter, `<case>.scrollbar-pixels.json` saves every actual RGBA8
pixel cell as lossless horizontal equal-color runs, its color counts, the
source PNG identity and the independent DOM gutter witness.

Ink attribution is deliberately narrow. The entire gutter must be visible,
with no unresolved overlay ordering or shape/effect coverage. Ancestor images,
opacity, filters, masks or blending prevent attribution. All potential scrollbar
pseudos need complete actual computed paint records; only the thumb may have a
nontransparent fill, and none may introduce another visible border, generated
content, image or shadow. The captured gutter must have a single uniform
perimeter color that is the unique majority background. Every remaining pixel
is retained; none is dropped because of a color tolerance. Its channels must
fall within the quantized interval between the observed background and actual
computed thumb fill. There must be exactly one connected non-background pixel
component. Empty ink does not establish an absent thumb, and multiple components
are not resolved using the expected scroll position.

When those witnesses are complete, `evidence.ink_bounds` is the occupied PNG
pixel-cell envelope of that component, with `status: measured-ink`. Its source
and attribution conditions remain in `evidence.original_png`; the individual
sample colors remain in the companion file. This is not a continuous paint
boundary or an independently resolved CSS radius. A one-pixel antialiasing
footprint remains a one-pixel measured cell; no threshold shrinks it.

When attribution is ambiguous, raw runs remain available and `ink_bounds` stays
unknown. No requested 3 px transparent border is added around measured ink.
The `measured-ink` status never clears the missing outer/hit/style/state errors,
and no sampled composited color is silently promoted to the uncomposited
canonical fill color.

## Remaining measurement boundary

Chromium's `CustomScrollbarTheme::PaintIntoRect` paints
`LayoutCustomScrollbarPart` separately because it has no normal layout fragments
and is not attached to the layout tree. This explains why ordinary DOM and
DOMSnapshot evidence need not contain its actual part geometry; source code
does not provide a particular capture's runtime box. See the
[official Chromium implementation](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/paint/custom_scrollbar_theme.cc).

The current implementation does not recover transparent thumb outer bounds,
hit rectangles, individual track pieces/buttons, actual corner curves, or
part-specific hover/focus from that source. Their absence remains visible in
raw evidence and gate failures. Future runtime paint/part evidence must measure
the same quantity independently; it cannot replace unknowns with source
constants, scroll-ratio estimates or native/reference expected values.

## CI checks

`test_reference_elements.mjs` exercises actual production helpers using recorded
owner geometry, including left/right/bottom gutters, unknown overlay/fractional
cases, unresolved visibility, retained obligations and reading order.
`test_scrollbar_pixels.py` uses explicit pixel fixtures and mocked PNG transport
to check lossless pixel receipts, ambiguity failures, and that scroll metrics or
requested transparent borders never supply thumb geometry. These fixtures run
through the existing CI Node test and Python discovery steps. Local checks for
this change are limited to Python compilation and `git diff --check`; CI must
validate the new code before its output is used as evidence.
