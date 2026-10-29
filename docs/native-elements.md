# Element parity contract (Amendment 4)

This is a required machine gate, independent of route/vocabulary coverage and
screenshot completeness. The earlier visual differences are failures to fix,
not accepted platform substitutions. No exception has been approved.

## Capture interchange, version 1

Keep the existing manifest, PNG filenames and receipts. Beside **every** PNG,
write `<case-id>.elements.json`. Preserve the raw source tree separately or in
`raw_nodes`; do not derive native measurements from the reference JSON.

```json
{
  "schema_version": 1,
  "scene_id": "zh-CN-light-1024x700-group",
  "client": "reference",
  "viewport": {"width": 1024, "height": 700, "scale": 1},
  "extraction_errors": [],
  "coverage": {"raw_nodes": 1, "emitted_elements": 1, "unmeasured": []},
  "elements": [{
    "id": "tree-local-id", "parent": null,
    "region": "header", "order": 0, "kind": "text",
    "text": "Relic", "name": "",
    "bounds": {"x": 8, "y": 8, "width": 32, "height": 16},
    "style": {
      "font_size": 12, "font_weight": 400,
      "foreground": [27,27,26,255], "background": [0,0,0,0],
      "border_color": [0,0,0,0], "border_width": 0, "corner_radius": 0,
      "border_widths": [0,0,0,0],
      "border_colors": [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]],
      "corner_radii": [0,0,0,0], "opacity": 1,
      "background_image": "none", "shadow": []
    },
    "state": {
      "enabled": null, "selected": null, "checked": null,
      "expanded": null, "focused": null, "hovered": false, "unread": null
    },
    "layout": {"wrap": "none", "truncation": "none", "line_count": 1},
    "icon": null,
    "evidence": {"source": "DOMRange"}
  }]
}
```

The example illustrates the shape, not reference values for native clients.
Coordinates are content-window-relative, top-left origin, logical pixels;
screenshots remain one pixel per logical pixel. `bounds` is the measured layout
box; also retain `visible_bounds` when clipping changes it. Preserve original
font family, path/class, text ranges, pixel samples, clips and raw properties in
`evidence`. RGBA channels are 0..255. Font weight uses numeric CSS/OpenType values.
Measure actual rendered template text, not the owning control's unused defaults.
`null` means not applicable, never an undocumented substitute for an unknown
measurement. Unknown measurements go in `extraction_errors` and/or
`coverage.unmeasured`, which fail the gate.

Paint audit additions (no changed tolerances): `border_widths` and
`border_colors` use top/right/bottom/left; `corner_radii` uses
top-left/top-right/bottom-right/bottom-left. Compare the individual edges and
corners, not only a maximum scalar. `opacity` is actual effective paint opacity.
`shadow` is `[]` for measured absence or a list of
`{inset, offset_x, offset_y, blur_radius, spread_radius, color}`. Preserve original
platform descriptions in evidence; an unparsed description is not a successful
measurement. `background_image` is `"none"` for measured absence, or an actual
image/gradient description: `kind` identifies image/linear-gradient/radial-gradient/
conic-gradient, images include actual asset `content_sha256`, gradients include
`stops: [{position, color}]` and measured direction/center/size/repeat as applicable.
Unmeasured paint remains a coverage error, even when both clients omit it.
Stroke widths remain measured for painted vectors and edges. Fully transparent
RGBA has no visible RGB; compare its alpha exactly, and compare every nonzero
alpha color using the unchanged DeltaE bound. A zero-width border has no visible
border color; positive-width edges still require their actual color.

`stroke_width` uses content-window pixels, like bounds and corner radii. Keep
the original vector stroke in its source units and actual CTM in evidence;
apply actual scale (or vector-effect non-scaling-stroke) before comparing.
Nonuniform transforms need their actual directional stroke geometry or an
explicit coverage gap; do not assume every transform has one scalar scale.

Actual text fonts are recorded in `style.rendered_fonts` as records with
Windows TextPattern document/range bounds can prove a font witness even when
the UIA control's outer layout slot is stretched. Match the actual text and
measured range geometry unambiguously; do not replace a missing measurement
with the configured font family. WinUI TextPointer character rectangles are
caret positions, not glyph ink: preserve their raw positions and derive text
advance bounds only from measured monotonic start/end positions. Nonmonotonic
or unresolved ranges remain coverage failures requiring disjoint measurements.

Actual text fonts are recorded in `style.rendered_fonts` as records with
`family_name`, optional `postscript_name`, and provider evidence. A configured
fallback list is not an actual rendered-font measurement. Compare measured
family identity, font size and weight; compare PostScript identity when both
providers expose it. Provider glyph counts and custom-font loading flags remain
audit evidence, since providers can report different text-range subdivisions.
Missing actual family evidence remains a coverage error. Reference captures use
`CSS.getPlatformFontsForNode`, while native captures use actual UIA/AX text runs.

The reference is captured separately on Windows and macOS with the same source,
scene definition and local server as that platform's native client. This retains
the reference's real `isMac()` shortcut behavior and actual available fonts.
Reports preserve `reference_environment` with browser/platform/font evidence.
Missing platform-specific reference evidence fails; no string normalization or
cross-platform baseline fallback is permitted.

Regions: `window`, `header`, `sidebar`, `conversation`, `composer`, `right-pane`,
`dialog`, `menu`. Reading `order` starts at zero within each region. Kinds:
`region`, `text`, `button`, `icon-button`, `input`, `toggle`, `checkbox`, `tab`,
`menu-item`, `dropdown`, `chip`, `badge`, `avatar`, `state-dot`, `card`, `list-row`,
`divider`, `code`, `chart-node`, `chart-edge`, `icon`, `image`, `link`.
Text is the actual visible string, with no date/path/whitespace substitutions.
`name` preserves accessible naming separately; invisible tooltip text is not
visible text. A shown tooltip and its text are elements.

## Common visibility and counting rules

- Walk the actual DOM/UIA/AX tree and actual render/view tree. Preserve raw nodes,
  including ignored wrappers, with the projection reason. A layout-only wrapper
  with no paint, role or text is not a visible element. A painted background,
  border, divider, card, state dot, chart node or edge is an element even if AX
  omits it; missing render instrumentation is an extraction failure.
- Exclude display/visibility-hidden, zero-opacity, zero-area and fully clipped
  content. Intersect ancestor scroll/viewport clips and the content window.
  Retain partially clipped items and record visible bounds. Opaque overlays
  occlude the covered portion; translucent modal dimmers do not make underlying
  still-visible content disappear. Do not use a center-point-only hit test to
  discard a partially visible element. If exact occlusion is unavailable, report
  that measurement gap; do not silently count it as verified visibility.
- A control's single simple label is represented once in the control's `text`.
  Preserve its raw child text node and record that ownership. Distinct subtitles,
  counters, badges, avatars, state dots and icon glyphs remain separate elements.
  A complex row with differently styled labels must retain those individual text
  elements. A button's icon is a child `icon` with actual glyph/vector evidence.
  Never collapse the complete text of a card or region into a duplicate label.
- Background/border paint owned by a semantic control is measured on the control,
  not emitted again as its template's border. Standalone card/background/divider
  paint is retained. This ownership is based on actual view ancestry, not a
  target element count. Store the ownership relationship for audit.
- Record selected/checked/enabled/expanded/focused/hovered/unread states when
  applicable, including false values. Preserve actual wrapping, truncation and
  measured text-line count. `wrap` is `none`, `word` or `character`; `truncation`
  is `none`, `clip` or `ellipsis`. Unknown values fail extraction coverage.
- Inapplicability requested by macOS at `61b2740`: an element with **no visible
  text** has null font size/weight and null text wrapping/truncation/line count.
  Non-text backgrounds also have null foreground; icon/edge stroke or fill is
  still measured as foreground. Preserve inherited but unused DOM/XAML text
  properties in raw evidence. This rule must never null an unmeasured property
  on actual text, input placeholders or control labels. It removes no element
  and does not waive any tolerance or mismatch.

## Matching, reports and gate

Pair one-to-one by region, kind, exact text/name and reading order, never by
shared generated IDs. Report all unmatched and mismatched elements. The fixed
tolerances are 4 px per box component, or 3% of the corresponding reference axis
for boxes over 130 px; font size 0.5 px; exact font weight; CIE76 DeltaE <= 3;
radius 1 px. Exact text, kind, region/order, state, wrapping and truncation are
required. Icon glyph/vector differences fail unless the person has approved a
specific equivalence. Missing values are not equal to measured values.

`scripts/visual/element_parity.py` emits `parity-report.json`, an index and a page
per case/platform with outlined reference/native images, a mismatch list and a
pixel-difference heat map. All 504 cases are required for acceptance. A smoke
run can diagnose extraction but cannot pass full acceptance. Missing captures,
missing measurements, errors, extra scenes, or any mismatch make the job fail;
upload reports even after failure. Reports must remain self-contained artifacts.

## Exceptions and icon equivalences

| Element/platform | Requested exception | Reason | Person's decision |
| --- | --- | --- | --- |
| None | None | No exceptions or icon substitutions requested | None approved |

Do not add rows or loosen tolerances to make CI pass. Any proposed change must
remain a reported failure until the person decides. The macOS system menu bar
does not exempt an absent in-window counterpart automatically.

## Changes for clients

- Amendment 4 initial contract: emit version 1 files above on all 504 existing
  cases. Preserve raw AX/UIA plus paint/view inspection. macOS request at
  `43bb8e1` for filename/schema/counting/visibility/coverage is addressed here.
  Shared reference extraction and strict report/gate are being added first;
  native unknown measurements must remain explicit failures while implemented.
