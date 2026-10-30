# Windows panel resize tooltip capture: unresolved

The `6183507` CI evidence proves that `panel-resize-hover` and `panel-resized`
cross a real tooltip transition between the PNG and the UI Automation capture.
The pointer still hovers over the production resize Thumb; the tooltip becomes
visible during extraction. The existing stability failure is correct. Waiting
for this tooltip to close naturally is **not a fix**: the fixed WinUI version
keeps it open while the pointer remains stationary in its safe zone.

## Actual CI observations

Source directory:
`S:\Codex\Outputs\Relic-native-visual\smoke-6183507-windows-zh-light`.
Each scene has prefix `zh-CN-light-1440x900-<scene>`. The evidence below comes
from `.scene-action.json` and `.uia.json.progress.jsonl`; the files are CI
artifacts, not locally generated captures.

| Measured observation | `panel-resize-hover` | `panel-resized` |
| --- | ---: | ---: |
| Initial hover observation completed, relative to that observation loop | 2.2887 ms | 2.2110 ms |
| Post-action hover observation completed, relative to that observation loop | 1.0980 ms | 122.6238 ms |
| First pointer enter to final pointer release/re-enter, from actual PointerPoint timestamps | Not applicable | 764.277 ms |
| PNG before/after and pre-extraction checkpoints | `PointerOver`, actual Thumb hit, no open popup | Same |
| First actual `ControlType.ToolTip` record, relative to UIA capture start | 110.2406 ms | 115.1152 ms |
| UIA capture completed, relative to UIA capture start | 5481.8800 ms | 5555.1266 ms |
| Post-extraction checkpoint | `PointerOver`, actual Thumb hit, one open popup | Same |

Both first tooltip records are sequence 31, `uia-5`, with the accessible name
`拖动调整宽度`. The popup bounds are `(1056, 418, 92, 32)` for hover and
`(992, 418, 92, 32)` after resize. The post-extraction popup child is the actual
`Microsoft.UI.Xaml.Controls.ToolTip`, with `is_open=true`.

These clocks are reported separately. The hover-loop measurements are not
tooltip-opening times; the first UIA record bounds when the tooltip was observed,
not the exact `Opened` event. This run has no `Opened`/`Closed` event timestamps
or measured `SPI_GETMOUSEHOVERTIME` value. It therefore does not establish an
exact first-hover-to-opening duration or any natural close time.

## Fixed Windows App SDK source

The project uses `Microsoft.WindowsAppSDK 1.6.250602001`, which Microsoft's
[release notes identify as 1.6.9](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/release-notes/windows-app-sdk-1-6).
The official `winui3/release/1.6.9` tag resolves to
[`da699b040bddc2a6adf660512a7c6db8a96bfbe3`](https://github.com/microsoft/microsoft-ui-xaml/commit/da699b040bddc2a6adf660512a7c6db8a96bfbe3),
whose commit message identifies the synchronized source as
`08ec1de0f82d16742618784569dcfb69a2c1c99f`, matching the SDK DLL's version marker.
The source path at this tag includes the `src/` prefix; current main is not used
as a substitute for this version.

- [`ToolTipService_Partial.cpp:449–459`](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/ToolTipService_Partial.cpp#L449)
  reads `SPI_GETMESSAGEDURATION`, falls back to 5 seconds on failure, and
  calculates `showDurationTimeSpan`. This path does not start a close timer with
  that duration. At line 488 it starts `StartSafeZoneCheckTimer` instead.
- [`ToolTipService_Partial.cpp:345–377`](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/ToolTipService_Partial.cpp#L345)
  retains the tooltip until the pointer leaves its safe zone. The periodic check
  returns without dismissal when the pointer has not moved from its position
  when the tooltip opened.
- [`ToolTipService_Partial.h:13–22`](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/ToolTipService_Partial.h#L13)
  defines a one-second safe-zone check interval. It is not a display timeout.
- [`ToolTipService_Partial.cpp:1730–1787`](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/ToolTipService_Partial.cpp#L1730)
  computes the normal mouse opening delay from twice `SPI_GETMOUSEHOVERTIME`.
  With the documented default parameter this would be 800 ms; that default is
  not an observed CI opening time.

## Status and capture boundary

**Unresolved.** Keep both scene failures and their actual popup evidence.
Do not disable the tooltip, change the production delay, move the pointer away,
assign a visual state, ignore popup changes, or add a fixed wait and claim that
the tooltip naturally disappeared. No capture code or gate was changed for this
diagnosis.

A later, explicitly defined tooltip-open hover state could observe the real
tooltip and capture it consistently in both the screenshot and extraction. It
would contain additional visible elements and must be compared with the same
reference state. It cannot be substituted for the current tooltip-free target
or counted as that target passing.
