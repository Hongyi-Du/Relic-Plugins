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
