# CI UI Automation observer

`Relic.Capture` reads an already-running Relic app without invoking UI actions.
It refuses execution unless `GITHUB_ACTIONS=true`; do not run it locally.

Build/publish it independently of the app:

```powershell
dotnet publish native/windows/Relic.Capture/Relic.Capture.csproj -c Release -o native-build/capture
```

The capture orchestrator writes a request after the app has settled:

```json
{"case_id":"zh-CN-light-1024x700-group","pid":123,"hwnd":456,"origin":{"x":0,"y":31},"width":1024,"height":700}
```

Then, only on the CI runner:

```powershell
native-build/capture/Relic.Capture.exe --request capture-request.json --output scene.uia.json
```

The output preserves every provider raw-tree node from that process's main
window and its separate popup HWNDs, deduplicated by UIA runtime ID. It does not
inspect other applications. Offscreen/zero-area nodes remain in the raw output
so normalization can audit its visibility decisions. Coordinates are relative
to the supplied client origin; UIA measurements are screen pixels, therefore
the orchestrator must verify the runner's one-pixel-per-logical-pixel capture.

TextPattern document/visible ranges retain font attributes, measurement status
and per-format runs. UIA font size is reported in **points**, never mislabeled
as CSS pixels. Unsupported attributes stay null with `unsupported` status;
mixed ranges retain `mixed` and their individual format runs. Pattern absence
does not mean an element lacks painted text. The app's actual render tree must
supplement UIA for paint, glyphs, clipping, hover/unread, borders and radii.
Provider exceptions are emitted as `extraction_errors`, with exit code 1 after
the raw file has been written. The orchestration must preserve that file and
report the failure instead of treating it as an empty/matching scene.

## Native text rectangles and managed `Rect.Empty`

The managed UIA wrapper is not a lossless view of provider rectangles.
[`UiaCoreApi.TextRange_GetBoundingRectangles`](https://github.com/dotnet/wpf/blob/main/src/Microsoft.DotNet.Wpf/src/UIAutomation/UIAutomationClient/MS/Internal/Automation/UiaCoreApi.cs)
replaces any returned rectangle with width or height `<= 0` with `Rect.Empty`.
That sentinel has `+Infinity` coordinates and `-Infinity` dimensions; it does
not establish that those were the provider's original numbers. In the
`030c4bb` Chinese light smoke capture, two trimmed sidebar previews each had
positive prefix/ellipsis boxes and a final punctuation range with this
managed sentinel. This finding does not prove the punctuation was painted.

`NativeTextEvidence.cs` reads the actual `IUIAutomationTextRange` COM
`SAFEARRAY<double>` as well. It resolves the same process element by unique
runtime ID, records the full document before and after observation, and
correlates ranges only through their actual document-prefix endpoints.
Duplicate endpoint identities, non-text positions, changing documents,
different range counts, or a different managed projection fail extraction.
No text search, screenshot coordinate match, or reference data identifies a
range. COM declarations preserve the vtable order in Windows SDK
`UIAutomationClient.h`; no provider or UI action is invoked.

Every original array component, its IEEE-754 bits, rectangle index, and the
actual managed rectangle are retained. These states remain distinct:

- Empty native array: no rectangles returned. A degenerate range can validly
  have this result; a nondegenerate range still lacks visibility evidence.
- Native finite zero-area rectangle: the provider returned a rectangle with
  no area. It is retained and still fails unresolved coverage; it does not
  prove that the whole range or owner is hidden.
- Native negative dimensions or nonfinite values: retained as explicit
  invalid measurements, with an extraction failure.
- Managed `Rect.Empty`: recorded as a managed projection diagnostic. The
  original COM dimensions must be measured and the exact projection checked
  before any finite native values can replace unknown canonical bounds.

This follows the distinction in the
[UIA range API](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.text.textpatternrange.getboundingrectangles)
between an empty rectangle **array** and an array containing rectangles.
No empty-array or zero-area case is silently removed. Native `IsHidden` is
recorded separately; unavailable or mixed values stay unknown. The existing
node-local offscreen diagnostic handling does not apply to descendants.

The COM path requires CI runtime validation. A successful build alone does
not establish native/managed range identity or text coverage.

## Runtime identity index and interrupted-capture diagnostics

Each actual HWND gets one native `IUIAutomation.RawViewWalker` enumeration
per observer process. The index contains the returned COM elements keyed by
their actual RuntimeId. It includes raw-only peers, without a control/content
view filter. A duplicate or empty RuntimeId, foreign-process node, or failed
traversal makes the index incomplete and identity lookup fails. Incomplete
indexes are retained rather than retried once per text field. No name, text,
class, or coordinate heuristic substitutes for a missing RuntimeId.

Each Attach still re-reads both managed and native RuntimeId and ProcessId.
Full document snapshots and unique exact range-prefix endpoint checks remain
mandatory, including after the native ranges have been read. The cache only
avoids repeated whole-tree searches; it does not make old properties current.

Alongside `scene.uia.json`, the observer writes
`scene.uia.json.progress.jsonl`. Every record is flushed before the next
provider stage. This journal contains monotonic elapsed/duration timings,
index progress and failures, individual lookup evidence, Attach stages,
native raw range rectangles, and measured node snapshots. A supervisor kill
therefore leaves completed records and the most recent started stage. The
final line may be incomplete if termination occurs during its write; earlier
complete JSONL lines remain readable. Preserve this sidecar even when the
final JSON does not exist. Partial records are diagnostic evidence, never a
replacement for the complete raw tree or a successful parity check.

The original native zero-area rectangles remain in both the raw capture and
journal and continue to fail unresolved coverage. Performance changes do not
change the capture timeout, geometry tolerance, or visibility decisions.

The `6dbdfd8` smoke captured only two entries in each primary HWND index. Its
COM tree-walker declaration omitted the `GetLastChildElement` vtable slot,
so the subsequent sibling call invoked the wrong method. The declaration
now includes that slot in SDK order. The recorded 2.35–4.89 second capture
times therefore do not demonstrate complete-tree performance. CI must
recheck native index coverage and timings with the corrected declaration.
Two file-code `TextPattern` provider failures in that run remain unresolved;
the journal now distinguishes document-range, visible-range, text, geometry,
identity, and declared-font inspection stages without suppressing failures.

In `34d4c35`, corrected full main-window indexes measured 315–367 nodes in
approximately 241–283 ms. The copies scene instead exposed a repeated child
RuntimeId at an Expander. The observer now retains the actual parent/child
edges and both current native element property snapshots. It stops recursive
entry into a repeated node, prevents repeated-sibling loops, and continues
other reachable branches for diagnostics. The index remains incomplete and
cannot satisfy an Attach. Managed traversal likewise records repeated
descendant edges and fails coverage rather than silently discarding them.
Revisiting an already-walked top-level HWND during process-window enumeration
is recorded separately and does not recurse into the already observed tree.

The six visible zero-area range errors in the otherwise completed `34d4c35`
scenes remain unresolved. The two trimmed sidebar previews return an actual
zero-area rectangle for their final punctuation while `IsHidden` is false.
Neither the screen origin of that rectangle nor identical RuntimeId values
prove invisible glyphs or interchangeable tree nodes, so those failures are
not converted into successful coverage.
