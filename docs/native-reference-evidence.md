# Reference text and scrollbar measurement audit

This checkpoint addresses the open macOS requests about CSS ellipsis geometry
and UA scrollbar coverage. It does not establish element parity. Unknown
measurements continue to fail coverage; no scene, element, tolerance or exception
has been removed or changed to pass the gate.

## Quantities must stay distinct

| Quantity | Actual source | What it proves |
| --- | --- | --- |
| Element/control border box | `Element.getBoundingClientRect()` | The native counterpart of the DOM element's layout box, including its current transforms. It does not locate every text glyph inside it. |
| Text advance/line rectangle | `Range.getClientRects()` and `getBoundingClientRect()` | Font-metric ascent/descent and text advance geometry. These are not contours or bounds of the painted glyph ink. |
| Clipped range envelope | Intersection of the original range with measured owner/ancestor/window clips | A diagnostic candidate area. Applying clipping cannot identify which characters the ellipsis algorithm removed or where the generated glyph paints. |
| Actual rendered ellipsis text geometry | Not present in the current evidence | `null`, with an explicit coverage failure. Both the surviving text and the generated ellipsis must be measured before this becomes known. |
| UA scrollbar part paint | Not present in the current evidence | `null`. Scroll extents and computed pseudo styles are retained, but do not prove that a particular thumb/track/button was painted or locate it. |

The CSSOM specification defines range rectangles using font metrics and advance
width. CSS ellipsis changes rendering without changing layout, may remove
characters to make room, and may itself be clipped. A range or a guessed
ellipsis width is therefore insufficient evidence for the painted result.
Sources: [CSSOM View, Range geometry](https://drafts.csswg.org/cssom-view/#dom-range-getclientrects),
[CSS Overflow, ellipsis](https://www.w3.org/TR/css-overflow-3/#text-overflow).

## Recorded CI evidence

The inspected case is `en-US-dark-1440x900-group` from `dffd7c4`, stored under
`S:\Codex\Outputs\Relic-native-visual\parity-dffd7c4\elements\reference-macos\`.
Its recorded browser is Chromium `156.0.8078.4`, platform `macos`, device pixel
ratio `1`. This is existing CI evidence, not a new local browser run.

For the sidebar preview `dom-82:text-0`:

- The owner element's directly measured box is
  `{x:80, y:263.125, width:144.28125, height:16.1875}`.
- The original range/layout box is
  `{x:80, y:262.125, width:459.578125, height:17}`.
- DOMSnapshot backend node `144`, node index `136`, layout index `102` has one
  text-box entry at that same full width, starting at UTF-16 index `0`, length
  `80`. It does not supply the painted ellipsis box.
- AX node `144` has three `InlineTextBox` children: the full original string,
  the shorter prefix, and `…`. Their actual records contain identities,
  names, roles, properties and child/parent IDs, but no rectangle coordinates.
- The old report's `195 px` visible text width came from an ancestor clip and
  exceeded the owner's own ellipsis box. Clipping to the owner corrects that
  diagnostic envelope, but does not make it a measured glyph box.

The same raw DOMSnapshot contains only an `after` pseudo type, and no scrollbar
strings; its AX tree has `239` inline text boxes and no scrollbar/slider roles.
These absences prove only that these APIs did not export scrollbar parts in this
case. They do not prove that no scrollbar painted in the screenshot.

## Why another layout snapshot does not solve the ellipsis gap

The official Chromium source explains the recorded result. The DOMSnapshot
agent obtains text boxes from `LayoutText::GetTextBoxInfo()`. That function
retains the original unpainted fragments, stops before the truncated painted
fragments after them, and skips layout-generated text such as ellipses. The
legacy `DOMSnapshot.getSnapshot` route calls the same method. Switching between
these two snapshot methods does not establish missing ellipsis geometry.
Sources: [DOMSnapshot agent](https://github.com/chromium/chromium/blob/main/third_party/blink/renderer/core/inspector/inspector_dom_snapshot_agent.cc),
[LayoutText implementation](https://github.com/chromium/chromium/blob/main/third_party/blink/renderer/core/layout/layout_text.cc),
[legacy snapshot agent](https://github.com/chromium/chromium/blob/main/third_party/blink/renderer/core/inspector/legacy_dom_snapshot_agent.cc).

The CDP `AXNode` schema has no bounds field. Its text fragments remain valuable
identity evidence, but cannot provide coordinates. `LayerTree.snapshotCommandLog`
is a possible additional diagnostic source, not a proven geometry solution:
the current Chromium `LoggingCanvas::onDrawTextBlob` implementation exports
position and paint, without the blob's glyph IDs, glyph positions or ink bounds.
Sources: [CDP schema](https://github.com/ChromeDevTools/devtools-protocol/blob/master/json/browser_protocol.json),
[LoggingCanvas](https://github.com/chromium/chromium/blob/main/third_party/blink/renderer/platform/graphics/logging_canvas.cc).

These upstream `main` sources were read during this audit. They explain the
mechanism and agree with the recorded CI case; they are not claimed to be an
exact source checkout of Chromium `156.0.8078.4`.

## Extractor behavior in this checkpoint

`textMeasurement` now retains the original range, all original range rectangles,
the actual element box, owner clip metrics, clipped candidate envelopes, actual
DOMSnapshot layout rows/text boxes, and actual AX fragments. Each record states
that range geometry is font-metric/advance geometry. `glyph_bounds` stays `null`.
Computed ellipsis/clamp plus overflow on the owner or an ancestor marks an
unresolved candidate; it is not presented as proof of the generated glyph's
exact presence, text or position.

For a standalone text element with this unresolved ellipsis:

- `bounds` and `visible_bounds` retain their JSON rectangle shape, with each
  coordinate set to `null`. This is invalid measured geometry and must fail.
- `evidence.text_bounds` is `null`; no clipped advance range substitutes for
  the missing painted text, including the generated ellipsis.
- `evidence.clipped_range_envelope` and `text_layout_bounds` keep the candidate
  area for a diagnostic dashed outline, explicitly labeled as unmeasured paint.
- One known visible layout line remains `line_count: 1` with its evidence source;
  ambiguous multiline ellipsis uses `null`. This does not supply missing glyph
  geometry.
- The full logical/source text and actual AX accessible name remain unchanged.
  Their availability does not certify the visibly painted substring.

For a button or other control with an ellipsized owned label, its actual control
box remains measured. Only the label geometry is unknown. Non-ellipsized range
rectangles remain available with the explicit quantity
`font-metric-text-advance-range`; they are not renamed glyph-ink bounds.

The existing `text.ellipsis_glyph_geometry` coverage failure remains mandatory.
Raw ranges are never discarded, text is not removed from the inventory, and
CSS clipping does not manufacture a matching native measurement.

## Scrollbar evidence and remaining work

The extractor preserves scroll/client/offset metrics, overflow axes, writing
direction/mode, gutter settings, and computed styles for scrollbar, buttons,
track, track-piece, thumb, corner and resizer. It also retains any corresponding
DOMSnapshot pseudo records actually returned. Each pseudo-style record leaves
painted presence and geometry unknown; a style query is not a painted part.

The existing `scrollbar.rendered_parts` coverage failure remains. In particular,
zero difference between offset and client width does not certify absence:
overlay scrollbars can occupy no gutter, and a stable gutter may exist without
a visible scrollbar. See [CSS Overflow, scrollbar gutters](https://www.w3.org/TR/css-overflow-3/#scrollbar-gutter-property).

A subsequent CI-only measurement experiment must capture actual paint or a
browser/platform accessibility source which reports the missing parts, retain
the browser version and original records, and prove attribution to the source
element. An ellipsis measurement must cover the surviving text and generated
ellipsis together, including clipping and bidi placement. A scrollbar
measurement must cover actual visibility, all painted parts, geometry and
state. Color-threshold crops, source-text re-rendering, scroll-ratio thumb
estimates and guessed font metrics are not accepted substitutes. Until such
evidence exists, the gate must stay red.

## Validation boundary

The Node fixtures exercise the production extraction functions with recorded
range metrics and API-shaped inputs. New checks cover null ellipsis geometry,
preserved control boxes, known line-count evidence, ancestor ellipsis, and zero
gutter uncertainty. Fixtures run only in CI. No local application, browser,
server or test process was launched for this checkpoint.

## Independent paint-trace diagnostic (2026-10-29)

`scripts/visual/paint_trace.py` adds a CI-only experiment without changing the
main capture order, the full matrix (now 564 cases), or canonical unknown measurements. It
reads an existing capture manifest and selects `group` and `file-code` at
1440x900 by default. Each requested case must already exist in that manifest.
It starts an independent fixture through the same `serve.py`, preserves the
manifest's language, theme and fixed clock, and calls the existing production
`reference-hook.js`. The original fixture/server is not reused or restarted.

Tracing starts before navigation, with the actual Chromium categories
`disabled-by-default-devtools.timeline.picture`, `cc.debug.picture` and
`cc.debug.display_items` (the latter two also use the
`disabled-by-default-` prefix). The browser-level CDP session requests a JSON
stream. The script preserves every byte returned by `IO.read`, plus the
`Tracing.tracingComplete` receipt. Every actual `skp64` value is decoded to a
separate `.skp` file with its exact JSON pointer, event metadata and any actual
event `layer_id` in `pictures.json`. Invalid payloads, absent payloads and trace
data loss are diagnostic failures. No picture is selected merely because it
resembles the expected screen.

Per-scene evidence also includes `Browser.getVersion`, Playwright's browser
version, available trace categories, original `LayerTree` events, trace clock
markers around the screenshot, page layout/viewport metrics, all DOM scroll
metrics, `DOMSnapshot`, AX, the existing UA input evidence and platform fonts.
The scene screenshot accompanies these records. DOM metrics are explicitly
layout evidence; they do not certify scrollbar visibility or glyph ink.

The newly identified upstream path is
[`DisplayItemList::EmitTraceSnapshot` / `AddToValue`](https://github.com/chromium/chromium/blob/main/cc/paint/display_item_list.cc),
which serializes real paint records, including individual operations when the
display-items category is enabled. Skia's
[`DrawTextBlobCommand::toJSON`](https://github.com/google/skia/blob/main/tools/debugger/DrawCommand.cpp)
can expose glyph IDs, positions, fonts and clusters from a text blob. This is
different evidence from layout ranges or the incomplete LoggingCanvas export.
These upstream sources establish an experiment to attempt; the checked-in
script does not yet parse SKP or prove that the CI Chromium build emits it.

Several attribution requirements remain. Traces contain navigation and earlier
frames as well as the final frame. DisplayItemList serialization uses zero
scroll offsets, so layer transforms, real scroll offsets, clipping and final
paint timing must be reconciled from original evidence. The current upstream
[`PictureDebugUtil`](https://github.com/chromium/chromium/blob/main/cc/debug/picture_debug_util.cc)
serializes typeface descriptors without embedding font data, but this is not
the implementation in the first recorded CI browser; see the revision-pinned
correction below. No substitute font can be used to claim original glyph
bounds. Scrollbars may use independent
compositor resources or solid-color thumbs absent from a content SKP. Their
absence from a picture cannot establish absence from the screenshot.

`summary.json` therefore distinguishes `raw_records_collected` from `failed`,
while `measurement_status` always remains `unresolved`. Per-scene `glyph_bounds`
and `scrollbar_parts`, and each picture's parsed status and final-scene
attribution, remain null. The strict parity gate continues to fail for its
existing coverage gaps regardless of the diagnostic's exit status.

The minimum additional CI step, after an existing full Windows capture, is:

```powershell
python -X utf8 scripts/visual/paint_trace.py --manifest visual/windows/data/en-US/light/manifest.json --output visual/paint-trace-windows-en-US-light
```

Upload `visual/paint-trace-windows-en-US-light` with `if: always()`, separately
from the canonical reference/native artifacts. The same command can use a
macOS manifest and separate output directory. A smoke manifest lacks
`file-code`; explicitly pass `--scene group` for that diagnostic. Pure mock
tests in `test_paint_trace.py` are covered by the existing CI unittest discovery.
No local browser, server, test or Skia tool is launched or installed for this
experiment. Only Python compilation and whitespace checks are local checks.

## First actual trace and next diagnostic configuration (2026-10-29)

The downloaded artifact is
`S:\Codex\Outputs\Relic-native-visual\paint-trace-05fe5cf-windows-en-light\`.
Both `group` and `file-code` retained 18 decoded SKP payloads, totaling 4,018
bytes per scene. Their header bytes identify `skiapict` and format version 110;
this header inspection is not Skia deserialization. Both completion receipts
have `dataLossOccurred: true` and remain failed. Original trace processor
statistics distinguish producer/writer sequence loss from a full central
buffer:

| Original metric | group | file-code |
| --- | ---: | ---: |
| Main buffer size, bytes | 209,715,200 | 209,715,200 |
| Main buffer bytes written | 65,708,032 | 60,112,896 |
| Main buffer bytes overwritten | 0 | 0 |
| Main buffer trace writer packet loss | 14 | 12 |
| Main buffer sequence packet loss | 14 | 12 |
| Packets skipped for invalid incremental state | 59,873 | 31,750 |
| Discarded chunks | 0 | 3 |

The two payload-bearing display-item snapshots in `group` occurred 52,075 and
56,850 microseconds after its navigation marker, over two seconds before the
screenshot marker. `file-code` likewise retained only two early snapshots.
These are initial background records, not proof of final text, ellipsis, or
scrollbar painting. Both `layer-events.json` files are empty, and every
picture's `layer_id` is null. Final-scene attribution remains unresolved.

The actual browser is `HeadlessChrome/156.0.8078.4`, Chromium revision
`f842f52ef39fd97b449eb27cff414bf05a98ddce`. Its
[`DisplayItemList::EmitTraceSnapshot`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/paint/display_item_list.cc)
does not export a `layer_id`; the field cannot be recovered by renaming an
existing event argument. Its
[`PictureDebugUtil`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/debug/picture_debug_util.cc)
sets an image serializer but no typeface serializer. The
[`DEPS`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/DEPS)
pins Skia `95ee33d7ec7791ab9c071675710a14fe6408ae4f`, whose
[`SkPictureData`](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/src/core/SkPictureData.cpp)
default serializer calls `kDoIncludeData` for typefaces. It attempts to include
font streams, unlike the newer Chromium implementation cited earlier. Large
font-bearing picture records are a possible contributor to producer bursts;
the loss counters alone do not establish that cause.

The diagnostic now uses the supported
[`Tracing.start` / `TraceConfig`](https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Tracing.pdl)
configuration rather than deprecated `categories`/`options`. It keeps
`recordUntilFull` and explicitly records the same 200 MiB central buffer as the
previous default. It retains all three picture categories, including individual
display-item records, plus `devtools.timeline` and the explicit frame category.
Only the broad `blink` and `cc` categories are removed: their general layout
and compositor events dominated the original event count. At the recorded
Chromium revision,
[`RecordingSource::FinishDisplayItemListUpdate`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/layers/recording_source.cc)
invokes `EmitTraceSnapshot` independently of the broad `cc` tracing category.
No picture category will be removed merely to obtain a clean exit status.
This configuration is an experiment, not a confirmed repair for producer loss.

Each scene additionally preserves `trace-config.json`, all actual
`Tracing.bufferUsage` callbacks in `buffer-usage.json`, and
`trace-diagnostics.json`. The latter retains the original command line and
complete trace processor statistics, indexes nonzero loss counters by original
JSON pointer, and lists original clock-sync and picture-event timestamps.
Original `trace.json` bytes remain unchanged. Missing layer events, any retained
loss evidence, and an unknown or scrollbar-hiding command line fail the
diagnostic. Even a loss-free raw collection continues to have null canonical
glyph/scrollbar measurements and null final-frame attribution.

The original command line contains `--hide-scrollbars`, a Playwright default
which changes the measurement environment. The diagnostic now passes
`ignore_default_args=["--hide-scrollbars"]`, using the documented
[Playwright launch argument filter](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-ignore-default-args).
This removes that flag while retaining the rest of Playwright's defaults and
the production scrollbar CSS. The actual trace command line is checked and
preserved; a requested argument list is not treated as execution evidence.
The main capture receives the same environment correction separately. Earlier
hidden-scrollbar reports are not comparable on an unchanged measurement basis,
and newly exposed scrollbar elements receive no exemption from the gate.

The next parser experiment must use the recorded Skia revision. Its
[`SkPicture::MakeFromData`](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/src/core/SkPicture.cpp)
can validate/deserialise the actual record, and its
[`DrawTextBlobCommand::toJSON`](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/tools/debugger/DrawCommand.cpp)
exports glyph IDs, positions, font records and available source-text clusters.
The same revision explicitly leaves RSXform positioning unimplemented in that
JSON exporter, and a text blob's aggregate bounds are not per-glyph painted
ink. A future CI decoder must retain that coverage gap, verify actual font
streams without fallback substitution, and reconcile real draw matrices,
clips, layers, scroll offsets and final-frame provenance. No parser is installed
or run locally, and no decoded text has yet been obtained from this artifact.

Scrollbar capture also needs compositor evidence beyond content SKPs. In the
recorded Chromium revision,
[`PaintedScrollbarLayer`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/layers/painted_scrollbar_layer.cc)
rasterizes track/buttons and thumb into separate UI resources, while
[`SolidColorScrollbarLayerImpl`](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/layers/solid_color_scrollbar_layer_impl.cc)
can emit a solid-color draw quad. The next evidence collection must associate
such actual resources/quads and transforms with the final screenshot and
source scroller. Content-picture absence still cannot certify scrollbar
absence; no estimated thumb rectangles or inferred part counts are added.
