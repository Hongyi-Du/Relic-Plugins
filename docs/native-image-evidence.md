# Native image resource evidence

`scripts/visual/image_paint.py` decodes **actual loaded SVG bytes** into a common
`vector-image-v1` resource-paint representation. It does not fetch URLs, choose an
icon by name, read the repository asset instead of capture evidence, or prove
that the decoded resource contributed to a screenshot. Unknown or unsupported
content is a failure; it never produces a partially accepted image identity.

## API and evidence boundary

`decode_svg_bytes(content: bytes)` returns canonical paint or raises
`ImagePaintError`. The function has no resource-URI argument.

`svg_paint_evidence(content: bytes, source_evidence=None)` retains the exact input
as base64, byte length, a deep copy of the supplied raw capture evidence, and
either the decoded paint or the actual parser error. Its
`content_binding_status` is always `unverified-by-parser`, and
`presentation_identity_proven` remains `false`. `status: decoded` only reports a
successful resource decode. A transport URL is evidence metadata, never an
image identity or an approved substitution.

Reference integration must use the response bytes actually loaded by the
observed image, retaining the network/DOM identity and load evidence. Windows
integration must use `image_source_evidence.svg_asset.content_bytes` and its
actual `SvgImageSource.SetSourceAsync`/current `Image.Source` binding receipt.
Missing content, failed decoding, absent/false/ambiguous binding, or a different
currently bound source must remain a capture failure. Neither integration may
substitute `plugins/relic/app/static/icon.svg` because the URI looks familiar.
The repository file is used only by a pure decoder regression test.

## Canonical format

Coordinates are in the SVG image's own user-coordinate system, before the
image-element viewport transform, clipping, opacity, or native view placement.
Layers remain in source painting order. Colors are sRGB `[r,g,b,a]`, using 0–255
channel values. The currently supported colors are opaque, so alpha is 255.

```json
{
  "source": "vector-image-v1",
  "glyph": {
    "view_box": [0, 0, 64, 64],
    "layers": [
      {
        "kind": "rounded-rect",
        "bounds": [0, 0, 64, 64],
        "radii": [15, 15],
        "fill": {
          "kind": "linear-gradient",
          "start": [0, 0],
          "end": [0, 64],
          "spread": "pad",
          "color_space": "srgb",
          "stops": [
            {"offset": 0, "color": [46, 44, 41, 255]},
            {"offset": 1, "color": [27, 26, 24, 255]}
          ]
        }
      },
      {
        "kind": "path",
        "d": "<the complete actual path attribute, preserved without rewriting>",
        "fill_rule": "nonzero",
        "fill": {"kind": "solid", "color": [255, 255, 255, 255]}
      },
      {
        "kind": "circle",
        "center": [47.5, 46.5],
        "radius": 4.2,
        "fill": {"kind": "solid", "color": [217, 119, 87, 255]}
      }
    ]
  }
}
```

The example describes the current asset's three layers; the decoder contains no
Relic-specific dimensions, colors, path, resource name, or icon mapping. `d`
contains the entire XML-decoded source attribute, not the placeholder above.
Original byte spelling, including XML whitespace, remains in raw evidence.
The 5-pixel outer CSS/native-view corner clip is **element style** and is not
part of this resource identity. A different image position or viewport scale
must not change `glyph`; those actual transforms are checked separately.

## Supported SVG subset and exact semantics

Only a UTF-8 SVG root in the SVG namespace with an explicit positive `viewBox`
is accepted. Children may be `defs` containing `linearGradient`/`stop`, and
painted `rect`, `path`, or `circle` elements. XML whitespace and comments are
nonpainting syntax; all original bytes are retained. Unknown tags, text,
attributes, namespaces, stylesheets, processing instructions, DTD/entity
declarations, transforms, filters, masks, strokes, and external references fail.
No feature is silently dropped to produce identity.

Supported geometry uses finite unitless numbers. Rectangles require positive
width and height; circles require positive radius. Omitted `x`, `y`, `cx`, and
`cy` have their SVG default zero values. Omitted rectangle radius components
inherit the specified other component; their used values clamp to half the
corresponding dimension. Rectangles without corner rounding remain represented
as `rounded-rect` with `[0,0]` radii. These are SVG used-value rules, not parity
tolerances. See [SVG rectangle geometry](https://www.w3.org/TR/SVG2/shapes.html#RectElement).

Paths preserve `d` and validate finite numeric arguments, command arities, and
syntax for `M/L/H/V/C/S/Q/T/Z` and their relative forms. Elliptical arc commands
are not yet supported and fail. `fill-rule` may be `nonzero` (default) or
`evenodd`. No path simplification or independent rasterization is performed.
Equivalent but differently spelled path data is not automatically declared
identical. See [SVG path data](https://www.w3.org/TR/SVG2/paths.html#PathData).

Fills may be `none`, `#RGB`, `#RRGGBB`, or an exact local `url(#id)` gradient
reference. Missing fill uses SVG's opaque black default. Gradients support
`objectBoundingBox` units and `pad` spread (including their defaults), at least
two nondecreasing stops in `[0,1]`, and opaque stop colors. Missing stop color
uses black. Gradient coordinates/offsets accept finite numbers or percentages.
Duplicate IDs, gradient inheritance, unknown IDs, opacity, alternate units,
degenerate gradients, and unrepresented stop behavior fail.

The gradient's start/end values are resolved using the **actual filled shape's
bounds**: `image_x = shape_x + gradient_x * shape_width`, likewise for y. The
current rect's `(0,0)→(0,1)` therefore becomes `(0,0)→(0,64)` because its actual
height is 64, not because its identity is known in advance. Axis-aligned vectors
and square object bounds are represented; a diagonal vector in nonsquare bounds
fails because endpoints alone do not encode the transformed gradient normal.
Path gradient fills fail because this decoder does not measure Bézier bounds.
See [SVG linear gradients](https://www.w3.org/TR/SVG2/pservers.html#LinearGradientElement).

## macOS actual-draw mapping obligation

`NativeLogoView.draw` currently records the mounted view's actual CoreGraphics
operations in `native_image_draw`. macOS may emit this same format only from
that actual draw receipt: view box, rectangle geometry/radii, gradient endpoints,
actual stop positions/colors/color space, pad behavior, actual parsed path and
fill rule, circle geometry/fill, and their call order. It must retain the raw
draw receipt and completion/current-view identity. A field absent from the
receipt remains unknown until the production draw records it; it must not be
filled from the reference SVG or this example.

In particular, the existing receipt's gradient colors alone do not measure stop
offsets, and `image_corner_radius` alone does not state all rectangle bounds.
The current `CGGradient` call uses locations `[0,1]`, but capture must record the
actual supplied locations. Likewise the code's sRGB color space and its clipping
and gradient extension options must be recorded as actual draw parameters.
Native mapping must not interpret `draw_returned: true` as final PNG contribution
or copy the browser's content-binding proof into a native receipt.

## Validation and remaining work

`test_image_paint.py` contains ten pure CI tests covering the real resource,
shape-relative gradient decoding, source bytes and URI independence, changed
content/order, unknown features/references, malformed/nonfinite values,
unsupported gradient semantics, XML failures, and preserved path data.
No test starts a UI/server or downloads a resource. The parser and tests have
not been executed locally; only syntax compilation is allowed here.

Reference and Windows caller integration is now implemented in
`image_projection.py`: it independently rechecks the actual retained DOM object
and completed response bytes, or the current native SvgImageSource/SetSourceAsync
byte binding, before decoding. Successful decoding removes only that element's
collector-owned rendered-content gap; raw bytes, transport URI and all unrelated
errors remain. Unsupported image formats and incomplete bindings fail. CI must
still validate this integration on real captures. macOS native-draw receipt
completeness and mapping to this exact representation remain for its owner.
Final screenshot-pixel attribution is separate; decoding does not supply it.
