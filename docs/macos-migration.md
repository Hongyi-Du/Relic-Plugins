# macOS arm64 migration tracker

**v0.4.1-macos-beta.1 is an unsigned Apple silicon prerelease approved for publication.** It preserves
the tested v0.4.1-beta.1 baseline; newer upstream v0.6.0-beta.1 changes are outside this release. Intel and Rosetta are
out of scope. Installation, server lifecycle and a signed-in Claude Code/Codex organization workflow have passed
local checks. Browser and native desktop acceptance remain limited as recorded below and in
[validation.md](validation.md). The source branch `release/macos-v0.4.1-beta.1` has been pushed; `main` remains unchanged.
The release tag and assets use this independent branch.

## Step 1 — Platform and filesystem behavior

**Implemented:** native arm64 Python/Node checks; shared executable discovery and explicit path overrides;
Finder/default-app/Terminal launching; macOS shortcuts and POSIX file links; structured absolute/resolved activity
paths; NUL-delimited Git paths; case behavior queried from the target volume; Unicode/symlink-aware protocol matching.
Existing stores gain the activity-path column without losing records; historical records retain a fallback.

**Validation:** isolated platform, path and store-upgrade fixtures cover these behaviors. Real interactive Finder,
Terminal, browser and permission-denial checks remain in Step 6.

## Step 2 — Application and process lifecycle

**Implemented:** one server per data directory; authenticated `--status`, `--stop` and `--restart`; server/control
ownership locks; restart port reuse when available; cleanup of owned ACP process groups; isolated member/session
identity. Closing the browser keeps the server running. Stop preserves organization data and does not trust a stale
PID as authority to kill a process.

**Validation:** automated lifecycle and process fixtures cover concurrent starts, shutdown/restart, stale metadata and
child cleanup. Real host cancellation/resume and sleep/wake acceptance remain in Step 6.

## Step 3 — Installation and reproducible adapters

**Implemented:** managed `~/Applications/Relic.app` launcher, `--no-shortcut`, data-preserving `--remove-launcher`,
absolute runtime selection, source archives and runtime diagnostics. The built-in ACP pair uses a committed npm
lockfile and a hash-specific installation directory, with a legacy-location fallback. CI has passed native arm64 checks
and Windows/macOS Python coverage in all four jobs.

**Validation:** all 15 packaging/installer tests passed. The final local ZIP was extracted with macOS `ditto` and
passed installation, diagnostics, launcher execution, status, authenticated restart and stop in an isolated home.
Portable archive launch configurations are checked without changing the live install. The source package and locally
generated Finder launcher are unsigned and not notarized. The packaging suite passed all 15 tests in both Mac CI jobs;
each Windows job passed 13 with two Mac/POSIX-specific skips.

## Step 4 — Desktop transport implementation

**Implemented:** macOS Codex Unix-socket framing and private endpoint validation, a required-tools capability probe
bound to socket identity, and conditional UI/runner availability. Claude native messaging requires explicit activation,
a verified supported CLI and recent public Desktop Stop observations; each delivery still requires its exact peer and
completion receipt. GUI seats do not silently become CLI writers, and ambiguous sends are not blindly repeated.

**Unverified native desktop routes:** the installed Codex host closed the live handshake, despite confirmation of its
framing. An earlier Claude probe used 2.1.92, below the route's 2.1.224 minimum. The later organization test used
2.1.286, but did not verify Desktop enablement, per-seat public Stop observations or completion receipts. These host
conditions remain unverified on this machine, and native desktop delivery is outside the accepted smoke-test scope.

## Step 5 — Tests, documentation and prerelease packaging

**Prepared:** focused regression suites, bilingual macOS instructions, environment/lifecycle reference and release
metadata for v0.4.1-macos-beta.1. The Mac package is supplied as ZIP and tar.gz with checksums and a source manifest.
It contains source and a launcher installer; Python, Node.js, host CLIs and account access are supplied by the user.
Publication is approved; the tag and GitHub release are prepared from the independent Mac branch.

**Validation:** see [validation.md](validation.md) for current counts, runtime versions, adapter observations and
archive checks. All four jobs passed in [CI run 40808895809](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40808895809)
on runtime commit `2d790de6777454fc04013ff1ba2830c567da7108`. The release adds only documentation after that commit;
the passing run applies to the named runtime commit, not a new CI run on the documentation-only descendant.
Fixture, real adapter and signed-in model results remain distinct.

## Step 6 — Signed-in workflow and remaining acceptance

**Completed locally:** a coordinator created an organization with a Claude Code writer and Codex reviewer. Both
members completed tasks with reports; messages flowed in both directions; the reviewer requested a correction and
the writer produced shared-document revision 2. A separate stale expected-revision write was rejected without
changing the document. Explicit human task prompts were needed after the startup wait instruction, so this run does
not demonstrate autonomous startup. Prompt design remains separate research work.

**Outside completed acceptance:**

- The full hierarchy/governance workflow and all hook-enforcement cases with live hosts; the organization smoke test
  did not cover all tool-count, standalone CLI and concurrent-store scenarios.
- Actual host cancellation/resume and sleep/wake beyond the tested server lifecycle.
- Safari/Chromium, Finder/Terminal, clipboard, English/Chinese IME, trackpad and permission-denial interaction.
  Chrome automation was unavailable, the in-app browser timed out, and a Safari attempt hung and was aborted.
- Codex and Claude native desktop gates, exact delivery receipts and duplicate-send behavior against real hosts.

The release scope is an unsigned Apple silicon prerelease with these limitations disclosed. Windows CI passed, but no
new Windows artifact is offered by this Mac prerelease. The newer Windows release and `main` remain unchanged.
