# Element parity contract (Amendment 4)

The current matrix has 55 states (660 cases per platform); the diagnostic smoke
has 19. It retains all prior states and adds `panel-resize-hover` and
`panel-resized`. Both begin with the actual group overview pane, opening it through
the real toolbar control if needed. The former hovers the actual panel handle;
the latter presses it, moves left by 64 logical pixels in eight steps and releases.
The real pane must grow by 64px and move left by 64px without changing top/height.
The pointer stays at its action endpoint through PNG and element extraction.
Actual geometry, controls, pointer/drag events and visible popup state must remain
stable; no width assignment substitutes for the drag. The same inputs apply at
all three sizes, in both languages and both themes.

Scrollbar parts use `kind: scrollbar` for the actual track/control and
`kind: scrollbar-thumb` for its independently drawn drag part. They remain
interactive, requiring actual enabled state. Both also require
`state.orientation: horizontal|vertical` and `state.scroll_position` in [0,1],
calculated from the actual provider value/min/max (zero for an actual zero range).
Preserve the original range and viewport measurements as evidence; never derive
thumb paint geometry from that ratio. Orientation and position compare exactly.
Keep actual control/hit rectangles and actual painted rectangles separately;
an AX hit region wider than the drawn gutter is not its painted width. Unknown
track/thumb paint stays a coverage failure. A painted or labelled child is not
discarded as a wrapper. Template page-action hit areas without independent paint
or labels may belong to the actual scrollbar owner, with complete object ancestry,
action and hit-area evidence retained in the raw tree and projection record.
For a thumb, canonical `bounds` means its actual paint primitive's border box;
an observed alpha/ink box is a separate quantity and cannot replace that box.
Windows records the actual hit box, primitive outer box and background-fill
envelope separately. Its finite supported branch uses measured solid rectangular
template primitives with complete transform, clipping, brush and rounding
evidence. A nonzero native radius remains unresolved until its actual curve is
measured; the requested radius value does not stand in for a CSS radius. The
transparent track's actual usable region is still a required element.

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
      "border_styles": ["none","none","none","none"],
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
`border_colors` and `border_styles` use top/right/bottom/left; `corner_radii` uses
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
Visible strokes also require `stroke_dash` (a measured array of window-pixel
lengths, `[]` for solid), `stroke_dash_offset` (window pixels),
`stroke_linecap` (`butt`/`round`/`square`) and `stroke_linejoin`
(`miter`/`round`/`bevel`). Keep source arrays and units in evidence. SVG odd-length
dash lists repeat to an even period; WinUI dash numbers multiply the actual
stroke thickness before the actual transform. These are unit conversions, not
matching tolerances. Unknown pathLength calibration, nonuniform transforms or
unknown paint fail. Computed CSS border styles do not reveal the exact painted
dash lengths: retain their measured `border_styles` without inventing a
`border_dash` pattern. Native dashed border primitives remain measured shapes
unless actual control ownership proves they belong to the same border surface.

Chart nodes additionally require `state.current`, independently of selection.
Read actual `aria-current` / production current-organization state and preserve
its provider source; a current node is not automatically an AX/UIA selected item.

Windows TextPattern document/range bounds can prove a font witness even when
the UIA control's outer layout slot is stretched. Match the actual text and
measured range geometry unambiguously; do not replace a missing measurement
with the configured font family. WinUI TextPointer character rectangles are
caret positions, not glyph ink: preserve their raw positions and derive text
advance bounds only from measured monotonic start/end positions. Nonmonotonic
or unresolved ranges remain coverage failures requiring disjoint measurements.
UIA `FontNameAttribute` is a declared text property in WinUI, not the physical
fallback glyph-run face. The Windows extractor now stores it in
`evidence.provider_fonts` and leaves canonical `style.rendered_fonts` unknown
until physical-face evidence exists. System-font cmap inspection may disprove
an impossible family but cannot prove which face WinUI rendered. See the
[actual WinUI implementation](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/common/textrangeadapter.cpp#L1987).

For non-ellipsized reference text, `bounds` is the DOMRange advance envelope
after content clipping; `visible_bounds` also applies ancestor and window
clips. These are font-metric/advance rectangles, not glyph-ink contours.
Preserve unmodified ranges in `evidence.text_measurements` (`raw_bounds`,
`raw_rectangles`). When CSS ellipsis leaves actual painted text geometry
unknown, standalone text bounds keep their rectangle shape with null axes,
and `evidence.text_bounds` is null. A control's directly measured border box
is retained. The diagnostic `evidence.clipped_range_envelope` may locate the
unknown text in HTML using a dashed outline; it never establishes parity.
See [reference evidence audit](native-reference-evidence.md). Raw scrollbar records
retain actual scroll metrics and UA styles; unknown thumb/track paint geometry
cannot be replaced with scroll-ratio estimates. Requested/computed CSS font
weight and actually resolved font-face evidence are separate quantities. The
new evidence fields do not waive existing weight differences or unknowns.

Actual text fonts are recorded in `style.rendered_fonts` as records with
`family_name`, optional `postscript_name`, and provider evidence. A configured
fallback list is not an actual rendered-font measurement. When both providers
measure a PostScript identity for every actual face, compare the exact complete
PostScript face sets. A localized family spelling is retained as provider
evidence, not treated as a different face: CDP's `蘋方-簡` and CoreText's
`PingFang SC` can both report the actual `PingFangSC-Semibold` face. This is not
an alias table. If either provider lacks any PostScript identity, measured
family sets must match exactly, and available faces within each family must
also match. Additional fallback faces, different actual faces, font-size and
numeric weight differences still fail. Provider glyph counts and custom-font loading flags remain
audit evidence, since providers can report different text-range subdivisions.
Missing actual family evidence remains a coverage error. Reference captures use
`CSS.getPlatformFontsForNode`, while native captures use actual UIA/AX text runs.
`evidence.font_request` preserves the computed CSS weight, variation-settings,
style and stretch separately from the actual face records; it does not claim
these requests are resolved OpenType weights or variation axes. The current
numeric weight check is unchanged pending independently measured comparable
native request/resolved-axis evidence. AX InlineTextBox fragments retain actual
names, including generated ellipses, but no bounds are invented when CDP omits
them.

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
  measured text-line count. `layout.wrap` retains the legacy `none`, `word` or
  `character` diagnostic, but combined normal/emergency classifications are not
  compared as one quantity. The additive break-strategy contract below replaces
  that comparison. `truncation` remains `none`, `clip` or `ellipsis`; its checks,
  actual text rectangles and measured line count are unchanged.
- Inapplicability requested by macOS at `61b2740`: an element with **no visible
  text** has null font size/weight and null text wrapping/truncation/line count.
  Non-text backgrounds also have null foreground; icon/edge stroke or fill is
  still measured as foreground. Preserve inherited but unused DOM/XAML text
  properties in raw evidence. This rule must never null an unmeasured property
  on actual text, input placeholders or control labels. It removes no element
  and does not waive any tolerance or mismatch.

### Independent line-break strategy, version 1

The capture `schema_version` remains 1. Every emitted element additionally records
`layout.break_strategy_version: 1`, `layout.normal_break_strategy` and
`layout.emergency_break_strategy`. Text applicability remains exactly
`bool(element.text) || element.kind == "text"`; no new element exclusion is used.

- `normal_break_strategy`: `none`, `word`, `break-all`, `character`, `keep-all`.
  `word` means the provider's ordinary language-aware opportunities, not identical
  Unicode algorithms or proof that the visible lines match. CSS `break-all` is
  kept distinct from a native character-wrapping mode.
- `emergency_break_strategy`: `none`, `break-unbreakable`. The latter allows an
  otherwise unbreakable sequence to be broken when it cannot fit. It does not
  claim a measured glyph boundary, matching intrinsic width, or a particular
  Unicode cluster algorithm.
- `evidence.line_break_configuration` contains `source`, the actual text `owner`,
  `raw` provider properties and `applicable`. Text with an unknown strategy,
  missing version/configuration/owner/raw measurement, or unresolved provider
  errors fails coverage. Unknowns on both sides still fail comparison.
- For non-text elements both strategies are explicitly null, with
  `applicable:false` and a nonempty reason. Their inherited but unused properties
  remain raw evidence. Null never proves a no-wrap strategy for actual text.

Mappings are based on provider semantics and each current control's measured
configuration, never on a counterpart's expected mode:

| Actual provider configuration | Normal | Emergency |
| --- | --- | --- |
| CSS normal word breaking + `overflow-wrap:anywhere` or `break-word` | `word` | `break-unbreakable` |
| CSS normal word breaking + `overflow-wrap:normal` | `word` | `none` |
| CSS `word-break:break-all` + normal overflow wrapping | `break-all` | `none` |
| CSS effective `nowrap` or `pre` | `none` | `none` |
| WinUI `TextWrapping.Wrap` | `word` | `break-unbreakable` |
| WinUI `TextWrapping.WrapWholeWords` | `word` | `none` |
| WinUI `TextWrapping.NoWrap` | `none` | `none` |
| Current production DirectWrite `DWRITE_WORD_WRAPPING_NO_WRAP` getter | `none` | `none` |
| TextKit actual `.byWordWrapping` paragraph mode | `word` | `break-unbreakable` |

CSS evidence retains computed `whiteSpace`, `textWrapMode`, `textWrapStyle`,
`wordBreak`, `overflowWrap`, `lineBreak`, `hyphens`, clamp, direction and writing
mode. In particular `anywhere` and `break-word` retain their different raw
min-content behavior. Effective no-wrap disables soft breaks without erasing an
inherited `overflow-wrap` request. Unsupported values remain unknown. CSS
`line-break:anywhere` and the `keep-all` relaxation fallback are not claimed to
fit the version-1 enumerations; unresolved values produce coverage failures.
Several text nodes folded into one semantic label require a uniform measured
configuration; otherwise retain all owners and the ambiguity.

WinUI evidence retains the actual enum spelling/value, control type and language.
The projector carries that actual text-owner configuration to its independent
rich-text runs with owner identity intact. It never recovers a policy from old
`wrap:"character"` captures. macOS retains paragraph mode, container mode and
maximum lines separately: final-line truncation cannot replace the paragraph's
normal wrapping policy.

Primary API definitions: [CSS overflow wrapping](https://drafts.csswg.org/css-text-3/#overflow-wrap-property),
[Windows App SDK 1.6 TextWrapping](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.textwrapping?view=windows-app-sdk-1.6),
[DirectWrite wrapping](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ne-dwrite-dwrite_word_wrapping),
and [AppKit byWordWrapping](https://developer.apple.com/documentation/appkit/nslinebreakmode/bywordwrapping).

This change does not fabricate a new unified text-fragment index. Existing
DOMSnapshot layout-text offsets, DOMRange rectangles, WinUI TextPointer offsets
and TextKit insertion geometry remain available with their original quantities.
TextPointer content offsets are not presumed UTF-16 indices. Common per-fragment
text/range binding is still incomplete; no new success flag is emitted for it.
The existing measured `text_bounds`, `line_count`, geometry and truncation checks
remain mandatory, including all existing ellipsis and missing-fragment failures.
Equal normal/emergency policies cannot waive different actual lines or positions.

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
