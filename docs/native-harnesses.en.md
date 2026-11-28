# Kimi Code and DeepSeek Harness in the Relic App

[中文](native-harnesses.zh-CN.md)

The Relic App can run **Kimi Code** (`kimi-code`) and **DeepSeek Harness** (`deepseek-harness`) as members through their own ACP servers. They use the same member dialog, Relic messages, shared documents, tasks, permission requests and session lifecycle as the existing App members. No extra npm ACP adapter is needed for these two harnesses.

## Connect an existing installation

1. Install and sign in to the harness using its own instructions. Confirm that `kimi acp` or `dsh --profile acp` starts successfully. The App does not install the harness, create its profile or change its login.
2. In **Settings → Harness connections**, set its program path if it is not on `PATH`. For Kimi select `kimi` / `kimi.exe`; for DSH select `dsh`, a CLI wrapper, or the installed Windows `DeepSeek Harness.exe`.
3. Choose **Add member → Run in the App**, then Kimi Code or DeepSeek Harness. Choose a workspace and create the member. Its introduction calls Relic status; its card shows the actual session model.
4. Use the member card to select the model and reasoning effort offered by that session. Kimi's `thinking` selector and DSH's grouped provider/model options are supported. DSH model IDs are opaque strings; keep the complete value offered by the selector.

Program selection is the App's explicit path, then the environment override below, then `PATH` and the platform's standard CLI locations. An invalid explicit path is reported instead of silently switching installations. Settings describe native ACP and do not offer an npm install button for these harnesses.

| Environment variable | Purpose |
| --- | --- |
| `RELIC_KIMI_PATH` | Kimi executable or CLI wrapper, when no App path is set. |
| `RELIC_DSH_PATH` | DSH executable or CLI wrapper, when no App path is set. |
| `RELIC_DSH_PROFILE` | Existing DSH profile name; default `acp`. |
| `RELIC_DSH_PATCH` | Optional existing DSH configuration overlay file, passed with `--patch`. |

Set environment variables in the process that starts the Relic App. For example, on Windows:

```powershell
$env:RELIC_KIMI_PATH = 'C:\Tools\Kimi\kimi.exe'
$env:RELIC_DSH_PATH = 'C:\Tools\DeepSeek Harness\DeepSeek Harness.exe'
python -X utf8 scripts/open_app.py
```

Use your actual installation paths. The DSH Windows desktop launcher uses its adjacent `resources/app.asar` and bundled runtime; it does not require a second DSH installation or a separate system Node.js for that member. Other desktop distribution layouts are not detected. CLI discovery supports Windows, macOS and Linux; real acceptance for this contribution is on Windows.

## DSH account and model routing

The ACP profile must already have a working provider and model. Use the provider configured and authenticated in DSH. If it needs an overlay, set `RELIC_DSH_PATCH` to that existing file before starting the App. Relic does not force a provider, copy credentials, or modify DSH's profile and default model. The chosen native provider determines billing; using ACP does not change that provider's charging model.

If session creation fails before models appear, first check that the same profile and optional patch work from DSH itself. Missing program paths and patch files are reported in Harness connections. Authentication remains in the native harness, outside Relic.

## Sessions and protocols

Each member receives a separate Relic MCP server tied to its seat token. Messages and documents belong to the existing Relic organization. When the App closes an idle session or restarts, it resumes the same native session where supported and supplies its Relic MCP server again; it does not create a replacement conversation on a resume failure.

These two harnesses do not load Claude Code/Codex Relic hooks. The App uses its existing ACP behavior: permission requests reach the person, Relic protocols can block those requests, completed tool calls are recorded as activity, and turn completion can prompt episode reflection. Tools that do not request permission are outside that pre-execution check; hook-only Reply checks are not added by this adapter.

## Checks

Run `python -X utf8 scripts/check.py` from the repository root. The native-launch, model-option and App-integration fixtures use temporary data and fake agents. They cover program selection, paths with spaces, desktop/CLI launch, grouped options, actual setting receipts, MCP seat identity, permission rejection, cancellation and resume with MCP reinjection. Live acceptance is separate from the fixtures and uses synthetic documents in an isolated organization.

References: [Kimi ACP command](https://moonshotai.github.io/kimi-code/en/reference/kimi-acp), [DSH ACP server contract](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md).
