# Native Relic App contract

Baseline: `2007a83` (PR #1 merge, v0.7.0-beta.1 candidate). The executable clients are
SwiftUI on macOS 14+ arm64 and WinUI 3 / Windows App SDK with .NET 8 on Windows x64.
`plugins/relic` remains the single engine. Neither client contains a browser,
HTML renderer, JavaScript runtime, WebView2, or WKWebView. Server-side static files
remain a reference until the Phase 1 parity gate below is satisfied.

## Delivery gates

1. Contract and client projects: this document, HTTP clients and headless tests.
2. Phase 1: everyday core on both platforms, green build and unit-test jobs.
3. Human acceptance: run both native windows, compare against the reference, check
   lifecycle, notifications, keyboard operation and accessibility. CI does not
   establish this gate. Do not launch a local app while the person's game is running.
4. Phase 2: remaining screens and actions in the inventory below.
5. Distribution: unsigned native artifacts, then person-owned signing/notarization
   decisions. Do not merge the draft PR before review.

Current implementation and outstanding acceptance are recorded in the PR, not
inferred from this contract. A route being listed here does not mean its native
screen is complete.

## Window and vocabulary

The window order is **organization tree | conversation + composer | Overview /
Workspace / File**. Selection identifies `(organization ID, group or member)`.
The sidebar folds organizations; group chat precedes members. The member list
retains server display names, roles, states, secretary/leader identity and activity.
Overview presents decisions, hierarchy, current work, protocols, and episodes;
details expand without replacing the conversation. Copies is a separate sheet,
reachable beside the organization chart and Settings.

All display strings use the existing `GET /api/i18n?lang=…` response; there is no
new localization route and no forked word list. Native language menus contain
only `zh-CN` and `en-US`. Chinese system locales resolve to Simplified Chinese;
other unsupported locales resolve to English. Explicitly save the resolved
language to `/api/prefs` so server-generated states and notices match. Plural
objects select `one` only for English `n=1`, otherwise `other`. Preserve `{name}`
substitutions. Framework names and user-entered content are not translated.

## Screen/action inventory

Source anchors refer to named functions in `app/static/app.js` and the structural
elements of `app/static/index.html`. Both native clients must use the same order
of actions and server payloads below. “P2” is planned native work, not a removed
engine function.

| Reference screen / action | Native controls and location | Phase |
| --- | --- | --- |
| `appbar`, `menus`, `appMenu`, `shortcut`: New org, add existing/member, secretary, history, sidebar/panel, pane selection, font/density/theme, about, help | macOS menu bar/Commands; Windows MenuBar/KeyboardAccelerator; native standard edit menu for cut/copy/paste/select/undo | P1 core menus; P2 remaining commands |
| `orgTree`, `renderSide`, `setFolded`, search, recent chats | Recursive native sidebar, disclosure controls, searchable organizations; selected group and member rows | P1 |
| `openOrg`, `go`, `renderHead`, `renderBanner` | Shared selection state; native conversation title, member state and permission/waiting banner | P1 |
| `renderStream`, `renderItem`, `renderLive`, `memberItems`, `actsBlock`, `stepRow` | Selectable native text, timestamps, notices, read indicators, tool/activity disclosure and live session items | P1 text/live; P2 rich activities/read indicators |
| `composerBox`, `toPicker`, `mentionCheck`, `quotedBody` | Native multiline editor, recipient selection and @member dispatch; drafts per chat; Send/Command-Enter/Ctrl-Enter | P1 send/mentions; P2 quote/mention completion/multi-select |
| `permissionCard`, `decisionCard` | Native action cards; use exact permission option IDs; approve/deny structural requests; open blocked member/task | P1 |
| `renderOrgPane`, `hierarchyBlock` | Native Overview: goal, status, members, tasks/reports, protocol origins and inherited/replaced rules; parent/leader/secretariat/auto-wake and subgroup controls | P1 core reading; P2 hierarchy editing/view modes/episode details |
| `drawCopies`, `copyCard`, `checkRulesView`, `ackCopy`, `retireCopy` | Copies sheet, summary/author/status/statistics, expandable code/examples; Got it and confirmed Retire | P1 |
| `orgDialog` | Name → purpose → governance → create; navigate to created organization | P1 |
| `memberDialog` App mode | Name → role → available harness → model → folder → secretary → create; open member conversation | P1 |
| `memberDialog` host mode | Name → role → Claude Code/Codex and supported surface → model/effort → folder/environment → permissions/env → start now or seat only | P1 CLI; P2 desktop surface capability choices |
| `memberDialog` existing mode | Existing session selection → seat → role → bind; preserve the complete session object | P1 |
| `openCard`, `seatAction`, `forwardDialog` | Native member detail: rename, avatar, model/effort, edit configuration, fresh/unbind/open session, forwarding, also-in memberships | P2 |
| `openSecretarySetup`, quick-start empty state | Native introductory sheet guiding organization → secretary/member → conversation | P2 |
| `openChart`, `drawChart`, `wireChart` | Native vector edges/cards with pan/zoom/fit; parent and shared-seat relationships, navigate to organization | P1 basic chart; P2 filters/shared-seat edge presentation |
| `openThread`, `renderThread` | Right-pane thread with root/replies and reply composer; preserve `reply_to` | P2 |
| `renderWork`, `fileTree` | Workspace pane: member folder, branch/changes, recent edits, nested file list, system folder opener | P2 (basic directory browsing scaffold exists) |
| `openFile`, `renderFile`, `codeView` | Native text/code/Markdown/image preview, line navigation, truncation/binary state, default-app opener | P2 |
| `requestPlain`, `togglePlainOne`, `toggleDigest`, `askSecretary` | Native plain-words toggle and digest card; async completion updates | P2 |
| `Voice`, `micButton` | Native OS speech input; explicit microphone permission on user action | P2 |
| `openDetails`, `traceView`, `reportBlock` | Native task filters/reports, documents/revisions, protocols/rules, context/trajectory pagination and requests | P2 |
| `drawProfile`, `drawAppearance`, `drawLanguage`, `drawVoice`, `drawNotify`, `drawHarness`, `drawAbout` | Native Settings; language and notification preference first; profile, appearance, voice, adapter install/path/capability and diagnostic actions later | P1 language/notifications; P2 other sections |
| `installApp`, `installPage`, PWA manifest/service worker | Replaced by native package installation; no browser install screen in either native App | Packaging |

## HTTP transport and lifecycle

Base URL is strictly `http://127.0.0.1:<port>` from the readiness record. Do not
honor HTTP proxies. JSON is UTF-8. Every client request sends `X-Relic-Token`;
server writes and lifecycle verification require it. The server also validates
the Host header. URL-encode individual path/query values. Errors are JSON
`{error: string}` with a non-2xx status. Never clear drafts or show an approval as
successful before checking the response; a request decision can return HTTP 200
with `status: "failed"` and `error`, which is also a failure.

The shared `plugins/relic/scripts/native_host.py` starts the existing
`scripts/relic_app.py --serve` as a child, with `CREATE_NO_WINDOW` on Windows.
Its single stdout line is the private readiness record:
`{port, pid, token, instance, started, version, state, owned}` (state/started are
optional). A pipe held by the native process is the lifetime lease. EOF closes
only an owned child, through authenticated `/api/shutdown` before a bounded
child-process fallback. The host borrows a verified existing server and never
stops it. It never kills a PID taken from disk. Failed readiness also cleans up
the exact spawned child. Logs stay under the engine's data directory `runs`.

The server's `app.json` is under `relic_core.store.data_home()` (default `~/.relic`,
respecting `RELIC_HOME`). Verify `pid`, `port`, `instance` through `/api/lifecycle`
before use. Do not put tokens in URLs, preferences, diagnostics, or notifications.

`GET /api/events` is SSE (`text/event-stream`): comments are heartbeats; each data
frame is a JSON object. Event types include `orgs`, `org`, `live`, `decision`,
`cc`, `prefs`, `install`, `plain`, `digest`, `shutdown`. `live` includes organization,
member, item and/or status; items can update existing seq/tool IDs. Other events
invalidate corresponding snapshots. Debounce refreshes, preserve selection and
drafts, and refetch after reconnection: this stream has no durable replay cursor.
An in-flight response must not overwrite a newly selected chat.

## Route inventory: GET

`O` denotes an encoded organization ID; `M` an encoded member name. Optional
query values are shown with `?`. Fields not rendered in Phase 1 must be preserved
in the underlying engine and remain available for Phase 2.

| Route | Request | Response shape / use |
| --- | --- | --- |
| `/api/ping` | none | `{app:"relic",version,pid}`; public discovery, not ownership |
| `/api/lifecycle` | token | `{app,version,pid,port,instance,state:"running" or "stopping"}` |
| `/api/platform` | none | OS/capability object from `platform_support.capabilities`; desktop delivery flags |
| `/api/events` | token | SSE frames described above |
| `/api/orgs` | none | `[{id,name,purpose,governance,status,parent,kind,cabinet,leader,members,…}]` |
| `/api/orgchart` | none | `{orgs:[{id,name,parent,kind,purpose,status,cabinet,governance,leader,leader_display,members,decisions,ex_officio,ended_at}],shared:[{session,harness,seats:[{org,member}]}],cabinet,secretary_general}` |
| `/api/cc` | none | `{items:[{id,org,org_name,protocol_id,title,summary,author_display,approved_display,issued_by,status,org_status,read,rules,stats,activated_at,supersedes,superseded_by,…}],unread}` |
| `/api/harnesses` | none | `[{id,title,vendor,available,program,problem,later,…}]`; show available choices and unavailable reasons |
| `/api/seat-options` | none | `{efforts,claude_modes,codex_sandboxes,claude_models}` string arrays |
| `/api/sessions` | none | `{sessions:[{id,harness,surface,title,cwd,updated,…}],problems:[string]}`; return session unchanged to bind |
| `/api/prefs` | none | prefs plus `{avatar,data,port,version}` |
| `/api/i18n` | `?lang=zh-CN` or `en-US` | `{lang,languages:[{code,name}],strings:{key:string or {one,other}}}`; native menu filters supported languages |
| `/api/avatar[/O/M]` | optional cache version | image bytes or 404 |
| `/api/fs/list` | `?path=absolute` | `{path,parent,entries:[{name,path,dir,size,mtime}],more}`; authorized roots only |
| `/api/fs/read` | `?path=absolute` | `{path,name,size,mtime,kind,text?,truncated?,url?}`; kind text/markdown/json/image/binary |
| `/api/fs/raw` | `?path=absolute` | raw bytes and MIME type; authorized roots only |
| `/api/org/O` | `?lang=` | Snapshot below |
| `/api/org/O/chat` | `?kind=group or private&member=M&limit=200&before=id` | `{items:[message or notice],more}` oldest first; replies are in threads |
| `/api/org/O/thread` | `?root=id` | `{root:message or null,replies:[message]}` |
| `/api/org/O/convo` | `?member=M` | `{steps:[…],total,…}` summarized context; missing session yields `{steps:[],total:0,missing:true}` |
| `/api/org/O/step` | `?member=M&i=index` | one full trajectory step |
| `/api/org/O/transcript` | `?member=M&limit=300&before=index&full=1` | `{steps:[…],total,…}` paged transcript or missing marker |
| `/api/org/O/document` | `?key=` | `{key,text,revision,author,at,…}` or `{missing:true}` |
| `/api/org/O/live` | `?member=M&after=seq` | `{items:[{seq,type,text,id?,title?,status?,options?,…}],status:{state,…} or null}` |
| `/api/org/O/waiting` | `?member=M` | `{waiting:[…],members:[name]}` manual reply forwarding |
| `/api/org/O/workspace` | `?member=M` | `{folder,git:{branch,root,changes},recent:[{path,tool,at}],…}` |
| `/api/org/O/member/M` | none | Member card + `{recent,config,waiting_replies}`; no seat token/session secret |

Snapshot: `{org,members,tasks,protocols,inherited_protocols,replaced_protocols,
requests,episodes,decisions,documents,chats,stamp}`. `org` includes ID/name/purpose,
governance/leader/status/auto_wake, secretary, parent/above/children/subgroups,
kind/cabinet/home/ended_at. Members have name/display/avatar/role, harness/surface
labels, model/effort and editable choices, state/detail/doing, session/agent/parent,
leader/secretary, unread/cwd, embedded/has_transcript, tasks/also_in/ex_officio.
Tasks have id/title/owner/status/evidence/report/done_at. Protocols include
id/title/strength/status/version/author/guidance/rules/trigger, votes/uses,
issued_by/downward/inherit/supersedes/retire_target/check/summary_for_person;
inherited rules add from/from_id, replaced rules add how/by/at/at_id.

Messages have `id,type,from,to,body,at,reply_to,read_by` and optional thread summary
`{count,last_at,people}`. Notices have `id:"e<seq>",type:"notice",text,at,seq`.
Decisions discriminate by `kind`: permission (id/member/title/detail/options),
approval (id/org/request/label/text/reason/status/requester/args), trajectory
(id/member/carrier/requester/reason), wake (member/error), task (id/title/member).

## Route inventory: POST

All bodies are JSON objects. `OK` below is `{ok:true}`. Preserve optional fields
when editing; do not construct a second engine or implement store mutations in
either native language.

| Route | Body | Response |
| --- | --- | --- |
| `/api/shutdown` | `{instance}` | `{stopping:true,instance}`; mismatch 409 |
| `/api/platform` | capability settings | updated capabilities |
| `/api/orgs` | `{name,purpose,governance:"leader" or "peer"}` | `{org_id}` |
| `/api/permission/id` | `{option:exact option ID}` | hub decision acknowledgement |
| `/api/prefs` | changed keys from name/lang/theme/accent/font/density/auto_names/notify/voice/paths | saved prefs; no arbitrary extra keys |
| `/api/avatar` | `{data:data-URL or "",org?,member?}` | `{avatar:URL or null}` |
| `/api/harnesses/id/install` | `{}` | `{started:bool}`; progress via install events |
| `/api/cc/id/read` | `{}` | `{id,read:true}` |
| `/api/cc/id/retire` | `{}` after confirmation | store retirement result; stops inherited rule too |
| `/api/fs/open` | `{path}` | `{opened:path}` |
| `/api/open` | `{what:"data" or "logs"}` | `{opened:path}` |
| `/api/install-window` | `{}` | legacy browser installation action; forbidden in native client |
| `/api/org/O/send` | `{to:["all"] or member names,body,channel:"group" or "private",reply_to?}` | `{id,to:[resolved recipients]}` |
| `/api/org/O/turn` | `{member,prompt,wake_from?,wake_hop?}` | `{accepted:true}`; runner integration, not normal composer |
| `/api/org/O/members` | `{name,role,harness,model?,mode?,folder?,secretary?}` | created App-managed member / status |
| `/api/org/O/seat` | `{name,role,harness,surface,model,effort,folder,environment,permission,env,start,edit?}` | `{member,config}`; `env` is KEY=VALUE lines |
| `/api/org/O/bind` | `{session:complete session object,member,role}` | `{member}` |
| `/api/org/O/parent` | `{parent:org ID or ""}` | store hierarchy result |
| `/api/org/O/cabinet` | `{on:bool}` | store cabinet result |
| `/api/org/O/leader` | `{member}` | store leader result |
| `/api/org/O/request` | `{request_id,decision:"approve" or "deny",note?}` | request record with status; failed + error must be shown |
| `/api/org/O/close` | `{}` after confirmation | subgroup closure result |
| `/api/org/O/protocols` | protocol proposal fields: title/strength/guidance/trigger/rules/summary_for_person/downward/supersedes as applicable | protocol record, active immediately as person-issued |
| `/api/org/O/secretary` | `{member}` | OK |
| `/api/org/O/fresh` | `{member}` after confirmation | OK; preserves seat, starts a fresh session |
| `/api/org/O/open_session` | `{member}` | OK; opens external host only on explicit user action |
| `/api/org/O/unbind` | `{member}` after confirmation | OK; seat/tasks/protocols retained |
| `/api/org/O/forward` | `{member,to:[names],body}` | forwarding result or OK |
| `/api/org/O/plain` | `{ids:[message IDs]}` (max 200) | explanation results/pending; `plain` events |
| `/api/org/O/digest` | `{refresh:bool}` | digest result/pending; `digest` events |
| `/api/org/O/rename` | `{member,name}` | `{display,synced,note}` |
| `/api/org/O/model` | `{member,model,effort}` | `{model,effort,applied:"now" or "next",…}` |
| `/api/org/O/auto_wake` | `{on:bool}` | OK |
| `/api/org/O/cancel` | `{member}` | OK |
| `/api/org/O/trajectory_answer` | `{request_id,decision,note?,redact?:true}` | trajectory decision result |

## Building without opening windows

Windows (SDK 8; Visual Studio not required):

```powershell
dotnet build native/windows/Relic/Relic.csproj -c Release -p:Platform=x64
```

macOS (macOS 14+, Apple silicon, Xcode command-line tools):

```sh
swift build --package-path native/macos -c release --arch arm64
```

CI runs `dotnet test native/windows/Relic.Core.Tests/Relic.Core.Tests.csproj` and
`swift test --package-path native/macos --arch arm64`; neither test target opens
a native window. The Python suite remains in `validate.yml`, isolated from live
stores. `test_native_host.py` mocks every process/server interaction, including
the Windows creation flags. During the game, all tests run in CI only.

Developer launches (only after the game): set `RELIC_ENGINE_ROOT` to this checkout
and optionally `RELIC_PYTHON` to the Python 3.11+ executable. Production packages
locate the engine adjacent to the Windows executable or inside macOS Resources.
Do not use `dotnet run` or `swift run` for a headless build.

Official build references: [WinUI unpackaged distribution](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app),
[Swift Package targets](https://docs.swift.org/latest/documentation/packagedescription/target/).
