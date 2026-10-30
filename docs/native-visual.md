# Native visual acceptance

Amendment 4 supersedes the earlier screenshot-only acceptance. The required
gate is now [element-by-element parity](native-elements.md): all 660 cases per platform,
independent DOM/UIA/AX/render measurements, exact visible counterparts, fixed
tolerances, no unapproved exceptions. Screenshots being complete or appearing
close is not a pass. The sections below retain harness/history information;
former native-control/date/menu/Markdown differences are failures to fix.

PR #4 is back in draft after the person's Windows review rejected the interface.
Route/key coverage is implementation coverage, not visual acceptance. No screen
is visually accepted until its three-way comparison has been opened and reviewed.

The first complete full-matrix run is [40886071671](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40886071671)
at `a4f3b11`: 504 comparisons, no missing captures. Subsequent Windows polish
adds task avatars/status badges/report surfaces, compact trace and document
columns, protocol hierarchy, paired member fields and the selected accent on
dialog actions. Final evidence must use the later final commit's full run.

Review found that a check rule without `on_error` was displayed as blocked by
macOS while the engine defaults to allow. The shared API now returns the engine's
effective `on_error` explicitly in copies and owned/inherited protocol snapshots.
The omitted-field fixture is retained; tests compare the returned value with
`Store._check_outcome` and verify that stored records are not changed. All clients
therefore consume the same effective value. This is a response projection fix,
not a change to enforcement or a screenshot-only workaround. PR #4 remains draft
for final visual review; no local app or test execution is authorized.

`scripts/visual/scenes.json` is the shared capture matrix: 55 screens and interaction
states, both languages, both themes, 1440x900 / 1280x800 / 1024x700. The full run
produces 504 comparisons. `smoke` is an iteration aid, never the final gate.

`Native visual review` is manually dispatched on the branch. The fixture starts
the real Relic server in an isolated CI data directory and seeds actual store
records. No model provider or member session is launched. The reference capture
injects a scene driver into the existing JavaScript closure in Playwright;
production markup and CSS are unchanged. Native captures must render the real
app views and controls. Missing captures fail composition; no placeholder image
may stand in for a native capture.

## Shared native capture contract (2026-10-29)

Only when `GITHUB_ACTIONS=true`, a native executable may consume the absolute
`RELIC_VISUAL_MANIFEST` JSON path. `RELIC_HOME`, `RELIC_PYTHON`, and
`RELIC_ENGINE_ROOT` point at the isolated fixture and current checkout. It may
borrow the fixture server normally, or use `fixture.port/token` directly.

Manifest fields: `version:1`, `client`, `lang`, `theme`, `fixture`, `output`,
`cases:[{id,scene,width,height,file}]`. Fixture fields include `org`, `parent`,
`subgroup`, `member`, `thread`, `task`, `workspace`, `files:{markdown,code,image}`,
`quote`, `plain`, `digest`, `port`, `token`, `pid`, `instance`, `home`.

For each case reset navigation to the fixture org/group, select the named real
view/dialog, render at the requested size, wait for layout/data, and write PNG
to `output/file`. The capture is the app's content area at one logical point per
pixel (exclude OS titlebar/shadow), preserving native controls. Dialogs must be
included. After all cases, write `complete.json` beside the manifest with
`{errors:[],count:N}`. Record actual failures in `errors`; never silently skip a
scene. App may then exit. The harness terminates only the child it started.

For macOS the owner implements this entirely in `native/macos/**`, using actual
SwiftUI rendering or window screenshots. Windows uses its real WinUI window.
The shared compose step places images reference | Windows | macOS and writes a
clickable HTML index. Final downloaded evidence belongs in
`S:\Codex\Outputs\Relic-native-visual`.

The reference and WinUI captures run sequentially against the same isolated
server on the Windows runner. Chromium is headless. The runner's desktop is set
to 1920x1080 without a settings window so the largest native client area fits;
WinUI rejects a root layout whose actual dimensions differ from the manifest.
Composition checks receipt counts, matching matrices and exact PNG dimensions
before producing comparisons. A successful workflow means complete evidence,
not visual acceptance: its `coverage.json` explicitly requires human review.

Full runs split the four language/theme variants into separate jobs per platform;
each job captures all 42 scenes at all three sizes. Native `complete.json`
remains beside each manifest. The harness writes root
`capture-complete-<lang>-<theme>.json` receipts, and compose checks their sum and
the exact 504 names from `scenes.json`. Downloaded artifact groups are merged by
client. The realistic fixture also includes stored Claude transcript/tool-result
records and an existing unseated session; these are files, never launched agents.

The local machine is off limits for installing, launching, restarting, UI capture,
or tests. The Python entry points fail outside GitHub Actions by default.
