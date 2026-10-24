# Dependent development and OrganizationBench

The native window exposes **启动三人开发任务** and **启动 OrganizationBench**. These are human actions that authorize the selected chats to run that specific workload. Do not start a new workload merely because a previous one is connected.

## Dependent development

Use `org_benchmark` operations with `org_id`, `operation`, and `data`. `list` shows runs; `brief` with `run_id` reveals your component assignment and professional constraints. Three owners implement API, ledger, and policy in their own workspaces. `status` reads the shared source bundle and its revision. Share constraints and agree interfaces through organization messages; all contribute to the same delivery outcome.

`submit` uses `{run_id,component,content,expected_revision}`. Only the assigned component owner can submit it. On revision conflict, reread status and merge; do not overwrite another owner's work. `evaluate` with `{run_id}` executes 18 host-owned API workflows against an immutable source snapshot and repeats them from fresh state. The response contains exact failure evidence, `bundle_hash`, and `bundle_path`. Individual module tests and meeting participation are not acceptance.

`release` uses `{run_id,bundle_hash}`. It requires passing host evidence for the current bundle and real submissions by all owners. Active protocols check `org_benchmark_release` against those exact two arguments before publication. `require_peer_review` can bind a different member's real `org_review record` to that exact source hash. The plugin does not pre-adopt a coordination policy: members choose whether an observed episode supports a reusable rule, discuss it and adopt it normally.

Existing chats may retain a cached MCP catalog. A compatible CLI is `python -X utf8 <plugin>/scripts/benchmark.py --org <org_id> --actor <your own real chat ID> --operation <operation> --data <JSON path>`. Use only your own actor ID. This fallback is a member-issued shell action, not a claim of MCP executor attestation. Both paths use the same membership, component ownership, revision and protocol checks.

## Complete OrganizationBench transport

The human selects a local OrganizationBench source repository. A separate loopback process starts the unmodified environment in the plugin's benchmark run directory; existing research runs are untouched. The default native button starts `acmecloud_portfolio_v2`, 5–8 periods. Programmatic creation also supports `acmecloud_portfolio_longitudinal_v1`, 16–64 periods.

Selected chats map to the native roster. With three chats, the leader receives Customer/Product and Business/Operations, one member Engineering, and one Quality/Support plus Risk/Security. These are information projections and initial responsibilities, not different rewards or action restrictions. Every actor retains the full upstream tool catalog. There is no SDL or extra model runtime.

- `catalog` returns the actual connected session's full descriptions and JSON schemas. Never infer tool fields from a different workload.
- `events` with `{bench_actor?,cursor?}` reads the assigned actor's observation stream. Save the cursor, and use each actor assigned to your chat. Responses include real tool results and business events.
- `invoke` with `{bench_actor?,tool,arguments,request_id}` calls the upstream tool. Use a fresh ID for new work and reuse it after an unknown outcome. The adapter checks chat membership, roster mapping and protocols before the real action. Protocol tool names are `bench_<tool>`, for example `bench_deploy`, and match the full upstream `arguments`.
- `upstream_status` reads current epoch, completion, workspace and score. `export` returns the real artifact.

Use `org_message` for peer coordination; upstream's internal `send_message` persists benchmark observations but does not itself wake a Codex chat. Keep agents' own workspaces, use upstream workspace tools to submit the company's source deliberately. Draft tests, source changes, deployment and fulfilled customer contracts are distinct states. The leader coordinates explicit epoch barriers only after considering current commitments and peers' evidence. Endogenous resource scarcity and customer obligations create tradeoffs; do not manufacture mandatory disagreement, vetoes, or private rewards.

The objective is final Net Profit from executed customer workflows, costs, penalties and losses. A negative score is a valid observed outcome. Do not rewrite the agent trajectory with a fixture policy, restart a failed trial silently, or use message/protocol counts as performance. Close episodes with actual outcome evidence and reflect on reusable coordination improvements. A six-period live run is one integration trial; a longitudinal run remains unfinished until its complete horizon settles.
