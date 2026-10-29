# Native Relic App contract

Baseline: `2007a83` (PR #1 merge, v0.7.0-beta.1 candidate). The executable clients are
SwiftUI on macOS 14+ arm64 and WinUI 3 / Windows App SDK with .NET 8 on Windows x64.
`plugins/relic` remains the single engine. Neither client contains a browser,
HTML renderer, JavaScript runtime, WebView2, or WKWebView. Server-side static files
remain a reference until full native parity is satisfied.

## Acceptance

All reference functionality is required on both systems. The draft PR cannot
leave draft until the per-function inventory is done on both, the route and
vocabulary checks pass, and both platform builds and all test suites are green.
The person's real-window acceptance remains last, after the game. Signing and
notarization remain the person's decisions. No local Python or native tests may
run while the game restriction is active.

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
of actions and server payloads below. Every row is required; there are no deferred features.

| Reference screen / action | Native controls and location | Windows | macOS |
| --- | --- | --- | --- |
| `appbar`, `menus`, `appMenu`, `shortcut`: New org, add existing/member, secretary, history, sidebar/panel, pane selection, font/density/theme, about, help | macOS menu bar/Commands; Windows MenuBar/KeyboardAccelerator; native standard edit menu for cut/copy/paste/select/undo | pending | pending |
| `orgTree`, `renderSide`, `setFolded`, search, recent chats | Recursive native sidebar, disclosure controls, searchable organizations and current members; unread/recent chat previews; selected group and member rows | pending | pending |
| `openOrg`, `go`, `renderHead`, `renderBanner` | Shared selection state; native conversation title, member state and permission/waiting banner | pending | pending |
| `renderStream`, `renderItem`, `renderLive`, `memberItems`, `actsBlock`, `stepRow` | Selectable native text, timestamps, notices, read-by disclosure, history pagination, tool/activity disclosure and live session items | pending | pending |
| `composerBox`, `toPicker`, `mentionCheck`, `quotedBody` | Native multiline editor, recipient selection and @member dispatch; persistent drafts, recipients and quotes per chat; Enter sends, Shift-Enter inserts a line | pending | pending |
| `permissionCard`, `decisionCard` | Native action cards; use exact permission option IDs; approve/deny structural requests; open blocked member/task | pending | pending |
| `renderOrgPane`, `hierarchyBlock` | Native Overview: goal, status, members, tasks/reports, protocol origins and inherited/replaced rules; parent/leader/secretariat/auto-wake and subgroup controls | pending | pending |
| `drawCopies`, `copyCard`, `checkRulesView`, `ackCopy`, `retireCopy` | Copies sheet, summary/author/status/statistics, expandable code/examples; Got it and confirmed Retire | pending | pending |
| `orgDialog` | Name → purpose → governance → create; navigate to created organization, then secretary/member setup | pending | pending |
| `memberDialog` App mode | Name → role → available harness → model → folder → secretary → create; open member conversation | pending | pending |
| `memberDialog` host mode | Name → role → Claude Code/Codex and supported surface → model/effort → folder/environment → permissions/env → start now or seat only | pending | pending |
| `memberDialog` existing mode | Search existing sessions by title/folder/id → session selection → seat → role → bind; preserve the complete session object | pending | pending |
| `openCard`, `seatAction`, `forwardDialog` | Native member detail: rename, avatar, model/effort, edit configuration, fresh/unbind/open session, forwarding, also-in memberships | pending | pending |
| `openSecretarySetup`, quick-start empty state | Native introductory sheet guiding organization → secretary/member → conversation | pending | pending |
| `openChart`, `drawChart`, `wireChart` | Native vector edges/cards with pan/zoom/fit; parent and shared-seat relationships, navigate to organization | pending | pending |
| `openThread`, `renderThread` | Right-pane thread with root/replies and reply composer; preserve `reply_to` | pending | pending |
| `renderWork`, `fileTree` | Workspace pane: member folder, branch/changes, recent edits, nested file list, system folder opener | pending | pending |
| `openFile`, `renderFile`, `codeView` | Native text/code/Markdown/image preview, clickable Markdown/local paths and line navigation, truncation/binary state, default-app opener | pending | pending |
| `requestPlain`, `togglePlainOne`, `toggleDigest`, `askSecretary` | Native plain-words toggle and digest card; async completion updates | pending | pending |
| `Voice`, `micButton` | Native OS speech input; explicit microphone permission on user action | pending | pending |
| `openDetails`, `traceView`, `reportBlock` | Native task filters/reports, documents/revisions, protocols/rules, context/trajectory pagination and requests | pending | pending |
| `drawProfile`, `drawAppearance`, `drawLanguage`, `drawVoice`, `drawNotify`, `drawHarness`, `drawAbout` | Native Settings; language and notification preference first; profile, appearance, voice, adapter install/path/capability and diagnostic actions | pending | pending |
| `installApp`, `installPage`, PWA manifest/service worker | Replaced by native package installation; no browser install screen in either native App | pending | pending |

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
query values are shown with `?`. Both native clients implement the complete reference surface.

| Route | Request | Response shape / use |
| --- | --- | --- | --- |
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
| `/api/org/O/document` | `?key=` | `{key,body,revision,author,at,…}` or `{missing:true}` |
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
| --- | --- | --- | --- |
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

## Full reference function inventory

Full v0.6 parity is required. No row is deferred. Each function and flow must be implemented and reviewed on both systems before the PR leaves draft. The static check deliberately fails while any cell is pending. DOM rendering helpers map to native controls, not an HTML renderer.

| Reference function | Native responsibility | Windows | macOS |
| --- | --- | --- | --- | --- |
| `platformInfo@9` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `automaticDelivery@17` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `hostSurfaces@22` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `shortcutLabel@26` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `shortcutAction@29` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `absolutePath@46` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `inlineTokens@51` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `append@86` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `h@93` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `icon@148` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `hue@166` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `initial@172` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `dayLabel@179` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `clock@185` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `shortWhen@186` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `ago@191` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `stateLabel@200` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `taskLabel@204` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `pathLink@207` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `inline@211` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `rich@220` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `mdRun@245` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `quoteBlock@271` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `load@277` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `save@278` | Native platform adaptation, text rendering, timestamps, and persistent view state | pending | pending |
| `get@281` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `loadPlatform@287` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `freshToken@291` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `post@297` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `toast@305` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `lang@313` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `applyPrefs@314` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `loadPrefs@325` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `setPrefs@329` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `tget@343` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `targ@355` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `t@365` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `tn@369` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `loadLang@381` | Authenticated HTTP, errors, preferences, and shared language formatting | pending | pending |
| `dname@417` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `roleName@429` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `avatar@432` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `secAvatar@446` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `groupAvatar@452` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `orgBadge@454` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `loadOrgs@460` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `readHash@470` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `writeHash@476` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `openOrg@482` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `refreshSnap@506` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `loadChat@513` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `markSeen@543` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `unreadOf@547` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `scheduleRefresh@554` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `notifyChanges@562` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `liveSlot@576` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `connect@577` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `lastLine@623` | Organization/chat selection, history, unread state, SSE refresh and notifications | pending | pending |
| `chatRow@629` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `orgTree@636` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `setFolded@652` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `unfoldTo@656` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderSide@662` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderMe@729` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `pushHist@736` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `goHist@744` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `toggleSide@753` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `go@759` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderAll@769` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderHead@772` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderBanner@802` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `nearBottom@821` | Sidebar tree, folding, search, navigation, headings and member banners | pending | pending |
| `renderStream@822` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `watchPlain@853` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `plainState@863` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `requestPlain@868` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `gotPlain@883` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `updatePlain@888` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `togglePlain@896` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `togglePlainOne@904` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `toggleDigest@910` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `loadDigest@916` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `digestCard@927` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `askSecretary@940` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `placeholder@950` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `renderItem@954` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `stripQuote@1013` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `copyText@1014` | Messages, digest, plain words, rich text, quote/copy/reply actions | pending | pending |
| `memberItems@1018` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `toolName@1050` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `stepArg@1051` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `actsBlock@1059` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `stepRow@1081` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `liveTurnStart@1102` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `liveItems@1109` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `renderLive@1120` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `permissionCard@1156` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `decide@1161` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `setQuote@1166` | External transcripts, live ACP items, tool detail and permission decisions | pending | pending |
| `quotedBody@1174` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `closeSelBar@1181` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `micButton@1236` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `field@1242` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `composerBox@1249` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `doSend@1264` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `renderComposer@1290` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `toPicker@1312` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `mentionCheck@1331` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `pickMention@1347` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `mentionKey@1357` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `closeMention@1369` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `closeMenu@1373` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `openMenu@1374` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `openContextMenu@1381` | Native selection quote, voice input, drafts, recipients and mention completion | pending | pending |
| `openThread@1400` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `loadThread@1405` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `closeThread@1416` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `renderThread@1417` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `panes@1436` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `setPane@1437` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `togglePanel@1444` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `applyPanelWidth@1450` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `startResize@1454` | Thread pane, reply composer, panel tabs and resizing | pending | pending |
| `renderPanel@1465` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `renderWork@1493` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `fileTree@1540` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `fill@1543` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `openFile@1569` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `sizeLabel@1578` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `renderFile@1579` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `codeView@1602` | Workspace selection, git edits, recursive files, previews and line navigation | pending | pending |
| `renderOrgPane@1612` | Overview, hierarchy, tasks, protocols, episodes and decision cards | pending | pending |
| `hierarchyBlock@1717` | Overview, hierarchy, tasks, protocols, episodes and decision cards | pending | pending |
| `walk@1720` | Overview, hierarchy, tasks, protocols, episodes and decision cards | pending | pending |
| `decisionCard@1784` | Overview, hierarchy, tasks, protocols, episodes and decision cards | pending | pending |
| `scheduleCc@1838` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `loadCc@1839` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `openCopies@1852` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `drawCopies@1859` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `copyState@1874` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `copyCard@1881` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `checkRulesView@1905` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `issuedBy@1922` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `ruleScope@1923` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `exampleText@1933` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `plainRules@1939` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `ackCopy@1942` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `retireCopy@1951` | Copies, unread acknowledgement, retirement, check source and examples | pending | pending |
| `closeCard@1964` | Member identity, avatar, rename/model/configuration and seat actions | pending | pending |
| `identity@1965` | Member identity, avatar, rename/model/configuration and seat actions | pending | pending |
| `pickImage@1972` | Member identity, avatar, rename/model/configuration and seat actions | pending | pending |
| `openCard@1986` | Member identity, avatar, rename/model/configuration and seat actions | pending | pending |
| `closeLayer@2081` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `scrim@2082` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `harnessList@2088` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `runModes@2094` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `runNotes@2095` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `hostKinds@2102` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `seatOptions@2105` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `memberDialog@2109` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `forwardDialog@2247` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `seatAction@2271` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `openSecretarySetup@2279` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `orgDialog@2288` | Create organization, all member modes, secretary setup and manual forwarding | pending | pending |
| `openDetails@2310` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `render@2323` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `countTasks@2402` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `reportBlock@2405` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `traceView@2410` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `fetchMore@2427` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `draw@2434` | Organization detail tabs, task reports, documents and trajectory pagination | pending | pending |
| `sections@2454` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `openSettings@2458` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `draw@2464` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `setRow@2474` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `segControl@2477` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `toggleControl@2480` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `redraw@2485` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawProfile@2486` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawAppearance@2501` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawLanguage@2510` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawVoice@2525` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawNotify@2533` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawHarness@2545` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `onInstall@2595` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `drawAbout@2603` | Native settings sections, adapters, appearance, language, voice and about | pending | pending |
| `svgEl@2621` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `protoName@2627` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `openChart@2635` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `applyView@2665` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `clampView@2672` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `fitChart@2677` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `zoomAt@2687` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `zoomBy@2695` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `panBy@2696` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `wireChart@2702` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `loadChart@2772` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `reloadChart@2781` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `redrawChart@2786` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `drawChart@2791` | Native organization chart, shared seats, filters, pan, zoom and focus | pending | pending |
| `menus@2965` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `abBtn@2966` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `renderAppbar@2970` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `openAppMenu@2995` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `menuItem@3003` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `appMenu@3011` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `focusSearch@3060` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `pasteText@3061` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `quoteSelection@3066` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `shortcutsDialog@3075` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `shortcut@3082` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `installApp@3096` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `installPage@3115` | Native menus, all keyboard commands, clipboard and installation replacement | pending | pending |
| `wire@3130` | Window initialization, quick start, native event wiring and lifecycle | pending | pending |

## Changes for the clients

- 2026-10-29: Merged native-macos through 4f95775. Its speech request is implemented: native.speech, native.speech_permission, native.microphone_permission, native.speech_unavailable are shared /api/i18n keys. Packaging writes both macOS usage-description keys and en.lproj/zh-Hans.lproj/InfoPlist.strings from those lists; native.voice_hint and native.voice_system describe Windows speech. No browser speech implementation is used.
- 2026-10-29: Applied REQUESTS.md inventory corrections: session search, unread/recent chat, persisted drafts/recipients/quotes, read-by disclosure, history paging, Markdown file/line links, rule examples and task evidence. Document payload is body. CI already runs every push; native-macos now gets its own --platform macos parity output, while native-apps requires both.
- 2026-10-29: The parity inventory gate now also rejects pending screen rows in addition to named app.js functions. No row is promoted based on key presence alone.

- 2026-10-29: Full parity replaces phased delivery. `scripts/check_native_parity.py` fails on missing reference routes, literal i18n keys, or pending function rows. Only native implementation source counts. `native/parity-allowlist.json` initially exempts only browser installation. macOS owns `native/macos/**`; requests go in its `REQUESTS.md`; report completed inventory mappings in its `STATUS.md`.
- 2026-10-29: Existing `/api/i18n` remains the vocabulary contract. Person-issued weak protocol form now sends required `rationale` and `trigger`, plus `inherit`. Four `native.protocol_*` labels were added to the shared en-US and zh-CN files.
