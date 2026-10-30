# One-record SKP font diagnostic (CI only)

This is an independent diagnostic, not an element-parity provider. It does not
write `elements.json`, resolve an existing measurement failure, draw a replacement
image, or assert that a trace record belongs to the final screenshot. A successful
decode is **not** a passed scene or gate. Original trace loss and layer attribution
failures remain in copied receipts even when raw font parsing succeeds.

## Exact input and build

The first supported input is the existing Windows full-Chromium artifact from
run `41024085363` / commit `81e93ac`:

```
paint-diagnostic-windows-chromium-en-US-light/paint/en-US-light-1440x900-group/
  browser.json
  pictures.json
  pictures/picture-00483.skp
```

Its actual browser revision is
`f842f52ef39fd97b449eb27cff414bf05a98ddce` (Chrome `156.0.8078.4`). The
[official Chromium DEPS at that revision](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/DEPS)
binds Skia `95ee33d7ec7791ab9c071675710a14fe6408ae4f`. The selected original SKP
has `965492` bytes and an actual trace pointer
`/traceEvents/334/args/snapshot/skp64`; these are recorded observations, not a
hardcoded replacement for each input's receipt. `run_ci.py` requires exact actual
`pictures.json` byte-count/header binding and records a byte digest.

The build uses that exact official Skia checkout, its own GN/bootstrap script and
installed Windows runner VC/Ninja tools. No compiler is installed by this code.
Only `buildtools`, `libpng`, and `zlib` entries from its original DEPS are synced
with the official `tools/git-sync-deps` and its documented `GIT_SYNC_DEPS_PATH`.
Each actual checkout revision is checked against its original DEPS entry. GPU,
PDF, SVG, Skottie, ICU, HarfBuzz, other image codecs and tools are disabled. The
original Chromium SKP serializer encodes images as PNG; encountering an unsupported
actual image remains a decode error, not an omitted image. The original parser,
factory, font manager and serialization sources are not patched. A standalone
executable target is appended to the disposable CI checkout.

The pinned source contract is checked against that actual checkout before build.
It guards the private run iterator's positional enum and known decoder behavior;
it does not establish runtime success. No local build or run has been performed.

The first CI attempt, run `41068736846`, passed all 14 input tests and all
source-contract checks, fetched the exact dependencies and generated GN files,
then Ninja failed before compilation on an absent Expat source. The pinned
`gn/skia.gni` defaults JPEG gainmaps on for development builds; `BUILD.gn` enables
the XML target when either Expat or gainmaps is enabled. The diagnostic now also
disables JPEG gainmaps, consistently with its existing PNG-only image support.
No image or font decoding error is suppressed; actual compilation is still
unverified until the next CI result.

## Root workflow hookup

Use a separate, explicitly diagnostic Windows job. Download only
`paint-diagnostic-windows-chromium-en-US-light` from the already completed run
`41024085363` with the workflow's existing artifact tooling/token. This does not
need a fixture server, browser, native executable, or any new screenshot. Keep
`GITHUB_ACTIONS=true` (provided by Actions). Example steps after that download:

```powershell
$case = "$env:RUNNER_TEMP/skp-input/paint/en-US-light-1440x900-group"
python -m unittest discover -s scripts/visual/skp_probe -p test_contract.py
python scripts/visual/skp_probe/build_ci.py --case $case --work "$env:RUNNER_TEMP/relic-skp-build" --output artifacts/skp/build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/visual/skp_probe/run_ci.py --case $case --picture pictures/picture-00483.skp --build artifacts/skp/build --output artifacts/skp/group
exit $LASTEXITCODE
```

Upload `artifacts/skp/**` with `if: always()`, including failed output. Build and
run both refuse non-CI execution. The build refuses an existing work directory;
the decoder refuses a stale `raw.json`. The chosen diagnostic is one SKP, not a
new capture matrix. Existing full/smoke parity jobs and their timeouts are unchanged.

Output contains `build.json`, `source-contract.json`, individual build logs,
`diagnostic.json`, `raw.json`, actual font streams, encoded original image bytes,
and original input receipts. `raw.json.status=decoded` only certifies this parser
completed without its recorded decode/query errors. It is not evidence that the
original trace was lossless or that every drawn glyph reached the screenshot.

## Recorded quantities and boundaries

`SkNoDrawCanvas` traverses the original `SkPicture` without allocating pixels.
The observer handles nested pictures using actual base `SkCanvas` playback,
preserving its transformation/paint behavior, and records actual annotation
key/bytes without interpreting them as DOM ownership. Its rectangular clip is
explicitly conservative; it is not an exact clip mask or final visible bounds.

Each `drawTextBlob` record contains the original draw origin, CTM, raw paint
properties, blob recorded bounds, run offset, and:

- `default-implicit-advances`: zero stored position scalars; no invented advances;
- `horizontal-x`: one actual scalar per glyph;
- `full-xy`: two actual scalars per glyph;
- `rsxform`: four actual scalars per glyph.

This uses the pinned `SkTextBlobRunIterator`, not `ExperimentalRun.positions`,
whose point interpretation would be invalid for the actual normal horizontal
Blink blobs. Glyph ID 0 is retained like every other recorded ID. If the SKP
includes extended source UTF-8 and clusters, their original bytes/numbers are
kept. Ordinary glyph-only records keep these fields null; no glyph-to-Unicode
reverse lookup is performed and no ellipsis is guessed from a glyph ID.

Typeface evidence comes from the actual decoded object held by that run. It
includes exact same-pointer links to deserialize callbacks, intrinsic
`fontStyle().weight/width/slant`, PostScript/family query results, variation-axis
count/read calls and values, synthetic flags, and exact returned font stream
bytes/collection index. Configured CSS weight is not substituted for these
values. `SkFont` size/scale/skew/embolden/hinting are separate actual run values.

The deserialize callback passes **no last-resort font manager**. The pinned Skia
code can return an empty typeface itself, and picture deserialization can also
replace a null typeface with an empty one. Both paths are detected by callback
errors or an actual nonpositive typeface glyph count. No picture playback occurs
after a decode/query error. Missing font streams, PostScript names, or failed or
inconsistent variation queries fail the diagnostic; they are not replaced by
family-name guesses. This does not infer information the serializer already
discarded about the original live browser object.

Still unmeasured: original DOM/text-span identity when absent, exact source/frame
and final-PNG attribution, final visible glyph/ellipsis bounds, complex clip
coverage, and resolved browser weight for any canonical text element. Actual
Skia decoding must first run in CI; the existence of these source paths alone
does not close those gaps.

## Primary source basis

- [Chromium original SKP serializer](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/cc/debug/picture_debug_util.cc)
  customizes image serialization, not the typeface serializer.
- [Pinned SkPictureData](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/src/core/SkPictureData.cpp)
  includes typeface data and has the empty-replacement behavior.
- [Pinned SkTypeface](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/src/core/SkTypeface.cpp)
  dispatches the serialized factory and documents the potentially wrong-glyph
  last-resort path, which this diagnostic does not request.
- [Pinned blob iterator](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/src/core/SkTextBlobPriv.h)
  exposes the distinct run representations.
- [Pinned SkNoDrawCanvas](https://github.com/google/skia/blob/95ee33d7ec7791ab9c071675710a14fe6408ae4f/include/utils/SkNoDrawCanvas.h)
  documents conservative clipping and no-pixel behavior.
- [Official build instructions](https://skia.org/docs/user/build/).
