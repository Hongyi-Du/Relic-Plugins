# Computed color evidence

The reference extractor's canonical `style` colors use the same measurement stage
as the native resolved sRGB brush colors: **unpremultiplied sRGB float RGBA channels
on 0..255**, before rasterization. The extractor parses the actual
`getComputedStyle` serialization. It does not use expected theme values or derive
the canonical channels from screenshot pixels.

Supported serializations are `rgb(...)`, `rgba(...)`, and `color(srgb ...)`, with
numeric or percentage components and optional alpha. `transparent` is transparent
black; `none` denotes absent paint. Unsupported color spaces, unresolved expressions,
missing values, invalid grammar, non-finite numbers and out-of-range components
produce `null` and a `color_unreadable` extraction error at every distinct source.
Values are never clamped, rounded to bytes, or replaced by a Canvas conversion.
Small differences in the actual serialized values remain differences.

Each reference capture adds `capture_evidence.colors`. A record retains:

- `computed`: the original computed color string;
- `canonical`: the float RGBA result, its explicit quantity and any failure reason;
- `canvas`: an independent 1×1 sRGB Canvas RGBA8 readback, its own status and color
  space, or the reason it is unavailable;
- `sources`: every distinct actual node selector, CSS property, pseudo-element and
  original full property value. Compound shadows and gradient stops keep the full
  computed property value as well as the extracted color string.

For example, computed `rgba(0, 0, 0, 0.07)` has canonical alpha `0.07 * 255`, while
the separate Canvas readback may contain alpha `18`. These are different quantities;
the raster value is diagnostic and is never a fallback for the computed value.
`none` has no Canvas pixel sample. A failed optional Canvas readback does not erase
an independently parsed computed color; its failure is recorded in `canvas`.

The native values, ΔE limit, alpha comparison and all other parity gates are
unchanged. Actual background-pattern pixel comparison still requires its complete
independent raster evidence; a computed color record does not supply that evidence.
The CI entry point `test_reference_elements.mjs` imports the dedicated pure
`test_reference_colors.mjs` regressions, without opening a browser.

Serialization references: [CSS Color 4 RGB functions](https://www.w3.org/TR/css-color-4/#rgb-functions),
[`color()`](https://www.w3.org/TR/css-color-4/#color-function), and
[sRGB serialization](https://www.w3.org/TR/css-color-4/#serializing-sRGB-values).
