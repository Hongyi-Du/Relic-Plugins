# Native Relic App contract

Baseline: `2007a83` (PR #1 merge, v0.7.0-beta.1 candidate). The executable clients are
SwiftUI on macOS 14+ arm64 and WinUI 3 / Windows App SDK with .NET 8 on Windows x64.
`plugins/relic` remains the single engine. Neither client instantiates a browser,
HTML renderer, JavaScript runtime, WebView2, or WKWebView. Server-side static files
remain a reference until full native parity is satisfied.

## Acceptance

Visual acceptance was rejected by the person on Windows at `ce34cde`. PR #4
is back in draft. The existing `done` columns describe function implementation
only; they do not certify presentation. The additional required visual gate is
documented in [native-visual.md](native-visual.md).

Changes for the clients (2026-10-29): `scripts/visual/scenes.json` and
`docs/native-visual.md` define the shared CI fixture/capture protocol. Both native
clients consume `RELIC_VISUAL_MANIFEST` only in CI and must capture every real
screen/dialog. Reverse native-key coverage now rejects keys missing from either
shared locale. `composer.voice_title` exists in both lists: the Windows bug was
constructing its label before `/api/i18n` loaded and retaining the raw fallback.
Microphone controls now use an icon with localized accessibility/tooltip text.
Mac amendment-3 requests 1/2 are addressed by the new shared manifest and visual
workflow (dispatchable on either branch); request 3 is addressed by reverse-key
tests and the existing shared voice title. Exact manifest fields are documented
in `docs/native-visual.md`; macOS should adopt that format.
The visual workflow assembles a real `.app` bundle before running the macOS
capture; launching a bare SwiftPM executable crashed before any capture. The
first reference captures are available in run `40862157094`. Fixture group
recipients and check-rule copies were corrected after inspecting those images.

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
| `appbar`, `menus`, `appMenu`, `shortcut`: New org, add existing/member, secretary, history, sidebar/panel, pane selection, font/density/theme, about, help | macOS menu bar/Commands; Windows MenuBar/KeyboardAccelerator; native standard edit menu for cut/copy/paste/select/undo | done | done |
| `orgTree`, `renderSide`, `setFolded`, search, recent chats | Recursive native sidebar, disclosure controls, searchable organizations and current members; unread/recent chat previews; selected group and member rows | done | done |
| `openOrg`, `go`, `renderHead`, `renderBanner` | Shared selection state; native conversation title, member state and permission/waiting banner | done | done |
| `renderStream`, `renderItem`, `renderLive`, `memberItems`, `actsBlock`, `stepRow` | Selectable native text, timestamps, notices, read-by disclosure, history pagination, tool/activity disclosure and live session items | done | done |
| `composerBox`, `toPicker`, `mentionCheck`, `quotedBody` | Native multiline editor, recipient selection and @member dispatch; persistent drafts, recipients and quotes per chat; Enter sends, Shift-Enter inserts a line | done | done |
| `permissionCard`, `decisionCard` | Native action cards; use exact permission option IDs; approve/deny structural requests; open blocked member/task | done | done |
| `renderOrgPane`, `hierarchyBlock` | Native Overview: goal, status, members, tasks/reports, protocol origins and inherited/replaced rules; parent/leader/secretariat/auto-wake and subgroup controls | done | done |
| `drawCopies`, `copyCard`, `checkRulesView`, `ackCopy`, `retireCopy` | Copies sheet, summary/author/status/statistics, expandable code/examples; Got it and confirmed Retire | done | done |
| `orgDialog` | Name → purpose → governance → create; navigate to created organization, then secretary/member setup | done | done |
| `memberDialog` App mode | Name → role → available harness → model → folder → secretary → create; open member conversation | done | done |
| `memberDialog` host mode | Name → role → Claude Code/Codex and supported surface → model/effort → folder/environment → permissions/env → start now or seat only | done | done |
| `memberDialog` existing mode | Search existing sessions by title/folder/id → session selection → seat → role → bind; preserve the complete session object | done | done |
| `openCard`, `seatAction`, `forwardDialog` | Native member detail: rename, avatar, model/effort, edit configuration, fresh/unbind/open session, forwarding, also-in memberships | done | done |
| `openSecretarySetup`, quick-start empty state | Native introductory sheet guiding organization → secretary/member → conversation | done | done |
| `openChart`, `drawChart`, `wireChart` | Native vector edges/cards with pan/zoom/fit; parent and shared-seat relationships, navigate to organization | done | done |
| `openThread`, `renderThread` | Right-pane thread with root/replies and reply composer; preserve `reply_to` | done | done |
| `renderWork`, `fileTree` | Workspace pane: member folder, branch/changes, recent edits, nested file list, system folder opener | done | done |
| `openFile`, `renderFile`, `codeView` | Native text/code/Markdown/image preview, clickable Markdown/local paths and line navigation, truncation/binary state, default-app opener | done | done |
| `requestPlain`, `togglePlainOne`, `toggleDigest`, `askSecretary` | Native plain-words toggle and digest card; async completion updates | done | done |
| `Voice`, `micButton` | Native OS speech input; explicit microphone permission on user action | done | done |
| `openDetails`, `traceView`, `reportBlock` | Native task filters/reports, documents/revisions, protocols/rules, context/trajectory pagination and requests | done | done |
| `drawProfile`, `drawAppearance`, `drawLanguage`, `drawVoice`, `drawNotify`, `drawHarness`, `drawAbout` | Native Settings; language and notification preference first; profile, appearance, voice, adapter install/path/capability and diagnostic actions | done | done |
| `installApp`, `installPage`, PWA manifest/service worker | Replaced by native package installation; no browser install screen in either native App | done | done |

`done` means the native implementation and its payload/control mapping have been
reviewed. It does not mean gate 3 (the person's real-window acceptance) has run.
CI build/test results are the separate gate 2 and must be green for this same PR
head. Source mappings: Windows `MainWindow`, `Navigation`, `SidebarCopies`,
`Conversation`, `ContentViews`, `Members`, `Organization`, `OrganizationChart`,
`FileWorkspace`, `DesktopSettings`, and `Relic.Core`; macOS exact mappings are in
[`native/macos/STATUS.md`](../native/macos/STATUS.md).

### Additional callbacks and flows

These flows are required in addition to every named function below; native
framework event callbacks replace the browser event wiring.

| Reference flow | Native implementation | Windows | macOS |
| --- | --- | --- | --- |
| Selection mouseup toolbar / quoteSelection | Selectable native message text and Copy/Quote context actions; Edit menu selection | done | done |
| Voice.supported / Voice.toggle / Voice.stop | OS speech availability, explicit start/stop, preference and permission handling | done | done |
| Voice.onresult / onerror / onend | Dictation at selection, interim/final text, microphone/network/no-speech errors, focus restoration | done | done |
| Enter / Shift-Enter / IME / mention completion | Native editor intercepts Return only outside composition/completion; Shift-Return newline | done | done |
| EventSource reopen / token rotation | Read app.json and verify the replacement lifecycle, reconnect SSE; retry an unauthenticated write only after token rejection | done | done |
| Resize pointer capture / remembered pane widths | Native split controls, separate File width, persisted visibility and dimensions | done | done |
| Hash navigation / back-forward history | Native `(org, member)` navigation stack; reveal selected organization's ancestors | done | done |
| Native install replaces PWA install / service worker | Per-user Windows installer and SwiftUI Mach-O bundle; retired browser installer returns 410 | done | done |
| Person issues protocol / inherited check rules | `/protocols` accepts weak guidance or strong JSON rules, rationale, trigger, inheritance and summary | done | done |
| Lifecycle close / beforeunload | Client-owned stdin lease and authenticated shutdown; borrowed server survives; no visible console | done | done |
| Native notification click | System notification activates Relic; copy and decision notifications retain the reference preference | done | done |

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
| `/api/install-window` | `{}` | 410 with native-package installation guidance; opens no window |
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
| --- | --- | --- | --- |
| `platformInfo@9` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `automaticDelivery@17` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `hostSurfaces@22` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortcutLabel@26` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortcutAction@29` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `absolutePath@46` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `inlineTokens@51` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `append@86` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `h@93` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `icon@148` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `hue@166` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `initial@172` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `dayLabel@179` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `clock@185` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `shortWhen@186` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `ago@191` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `stateLabel@200` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `taskLabel@204` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `pathLink@207` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `inline@211` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `rich@220` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `mdRun@245` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `quoteBlock@271` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `load@277` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `save@278` | Native platform adaptation, text rendering, timestamps, and persistent view state | done | done |
| `get@281` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadPlatform@287` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `freshToken@291` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `post@297` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `toast@305` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `lang@313` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `applyPrefs@314` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadPrefs@325` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `setPrefs@329` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `tget@343` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `targ@355` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `t@365` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `tn@369` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `loadLang@381` | Authenticated HTTP, errors, preferences, and shared language formatting | done | done |
| `dname@417` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `roleName@429` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `avatar@432` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `secAvatar@446` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `groupAvatar@452` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `orgBadge@454` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `loadOrgs@460` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `readHash@470` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `writeHash@476` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `openOrg@482` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `refreshSnap@506` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `loadChat@513` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `markSeen@543` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `unreadOf@547` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `scheduleRefresh@554` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `notifyChanges@562` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `liveSlot@576` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `connect@577` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `lastLine@623` | Organization/chat selection, history, unread state, SSE refresh and notifications | done | done |
| `chatRow@629` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `orgTree@636` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `setFolded@652` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `unfoldTo@656` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderSide@662` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderMe@729` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `pushHist@736` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `goHist@744` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `toggleSide@753` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `go@759` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderAll@769` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderHead@772` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderBanner@802` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `nearBottom@821` | Sidebar tree, folding, search, navigation, headings and member banners | done | done |
| `renderStream@822` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `watchPlain@853` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `plainState@863` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `requestPlain@868` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `gotPlain@883` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `updatePlain@888` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `togglePlain@896` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `togglePlainOne@904` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `toggleDigest@910` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `loadDigest@916` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `digestCard@927` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `askSecretary@940` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `placeholder@950` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `renderItem@954` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `stripQuote@1013` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `copyText@1014` | Messages, digest, plain words, rich text, quote/copy/reply actions | done | done |
| `memberItems@1018` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `toolName@1050` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `stepArg@1051` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `actsBlock@1059` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `stepRow@1081` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `liveTurnStart@1102` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `liveItems@1109` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `renderLive@1120` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `permissionCard@1156` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `decide@1161` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `setQuote@1166` | External transcripts, live ACP items, tool detail and permission decisions | done | done |
| `quotedBody@1174` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeSelBar@1181` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `micButton@1236` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `field@1242` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `composerBox@1249` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `doSend@1264` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `renderComposer@1290` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `toPicker@1312` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `mentionCheck@1331` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `pickMention@1347` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `mentionKey@1357` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeMention@1369` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `closeMenu@1373` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openMenu@1374` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openContextMenu@1381` | Native selection quote, voice input, drafts, recipients and mention completion | done | done |
| `openThread@1400` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `loadThread@1405` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `closeThread@1416` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `renderThread@1417` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `panes@1436` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `setPane@1437` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `togglePanel@1444` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `applyPanelWidth@1450` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `startResize@1454` | Thread pane, reply composer, panel tabs and resizing | done | done |
| `renderPanel@1465` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderWork@1493` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `fileTree@1540` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `fill@1543` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `openFile@1569` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `sizeLabel@1578` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderFile@1579` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `codeView@1602` | Workspace selection, git edits, recursive files, previews and line navigation | done | done |
| `renderOrgPane@1612` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `hierarchyBlock@1717` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `walk@1720` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `decisionCard@1784` | Overview, hierarchy, tasks, protocols, episodes and decision cards | done | done |
| `scheduleCc@1838` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `loadCc@1839` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `openCopies@1852` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `drawCopies@1859` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `copyState@1874` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `copyCard@1881` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `checkRulesView@1905` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `issuedBy@1922` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `ruleScope@1923` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `exampleText@1933` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `plainRules@1939` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `ackCopy@1942` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `retireCopy@1951` | Copies, unread acknowledgement, retirement, check source and examples | done | done |
| `closeCard@1964` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `identity@1965` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `pickImage@1972` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `openCard@1986` | Member identity, avatar, rename/model/configuration and seat actions | done | done |
| `closeLayer@2081` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `scrim@2082` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `harnessList@2088` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `runModes@2094` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `runNotes@2095` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `hostKinds@2102` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `seatOptions@2105` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `memberDialog@2109` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `forwardDialog@2247` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `seatAction@2271` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `openSecretarySetup@2279` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `orgDialog@2288` | Create organization, all member modes, secretary setup and manual forwarding | done | done |
| `openDetails@2310` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `render@2323` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `countTasks@2402` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `reportBlock@2405` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `traceView@2410` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `fetchMore@2427` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `draw@2434` | Organization detail tabs, task reports, documents and trajectory pagination | done | done |
| `sections@2454` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `openSettings@2458` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `draw@2464` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `setRow@2474` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `segControl@2477` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `toggleControl@2480` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `redraw@2485` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawProfile@2486` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawAppearance@2501` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawLanguage@2510` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawVoice@2525` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawNotify@2533` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawHarness@2545` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `onInstall@2595` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `drawAbout@2603` | Native settings sections, adapters, appearance, language, voice and about | done | done |
| `svgEl@2621` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `protoName@2627` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `openChart@2635` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `applyView@2665` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `clampView@2672` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `fitChart@2677` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `zoomAt@2687` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `zoomBy@2695` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `panBy@2696` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `wireChart@2702` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `loadChart@2772` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `reloadChart@2781` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `redrawChart@2786` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `drawChart@2791` | Native organization chart, shared seats, filters, pan, zoom and focus | done | done |
| `menus@2965` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `abBtn@2966` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `renderAppbar@2970` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `openAppMenu@2995` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `menuItem@3003` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `appMenu@3011` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `focusSearch@3060` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `pasteText@3061` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `quoteSelection@3066` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `shortcutsDialog@3075` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `shortcut@3082` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `installApp@3096` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `installPage@3115` | Native menus, all keyboard commands, clipboard and installation replacement | done | done |
| `wire@3130` | Window initialization, quick start, native event wiring and lifecycle | done | done |

## Changes for the clients

- 2026-10-29: Final macOS integration abbb5bb is merged; REQUESTS.md now records every shared request resolved. All 34 screen/callback rows and 214 named functions are done on both platforms. At 028e270, Native apps run 40835859590 passed Windows/macOS builds, client tests, package assembly and the complete parity gate (52 routes, 686 keys, no browser UI). This final integration and its shared Python checks are revalidated by CI before PR readiness; real-window acceptance remains outstanding.


- 2026-10-29: validate.yml now cancels superseded checks per branch, matching native-apps.yml, so simultaneous push/pull_request runs do not keep two identical four-platform matrices queued. Tests still run on each latest branch/PR head.


- 2026-10-29: Implemented the final REQUESTS.md bundle metadata: shared packaging copies native/macos/Resources/Relic.icns and sets CFBundleIconFile, CFBundleDevelopmentRegion=en, CFBundleLocalizations=[en, zh-Hans]. Shared native.episodes is Episode in both lists. Windows uses the unchanged reference PNG in an ICO container. native-install.md now distinguishes macOS Close Window (keep Dock/engine, reopen) from Quit (release owned engine), versus closing the Windows window.


- 2026-10-29: Merged and reviewed native-macos 467fa95: verified credential renewal, quote-only sends, thread-send lock, speech stop and protocol payload/labels now match; their pending implementation rows are done. REQUESTS.md contains no new shared changes. Shared list templates still require macOS implementation and remain enforced by vocabulary CI.
- 2026-10-29: CI also rejects browser controls and HTML/JavaScript rendering calls in native implementation sources. Windows history uses the existing before cursor and merges pages without losing older notices or updated read receipts; expanding the initial limit alone would stop at the server's bounded history window.


- 2026-10-29: Shared panel/open_app entry points now use the same native launcher and propagate a missing native installation as an error. Updated English/Chinese README, Windows/macOS guides and source-package README to distinguish native binary installation from shared plugin installation. The WinUI SDK carries its standard optional WebView2 SDK assemblies; Relic never creates that control or starts its browser runtime. All App rendering remains native.


- 2026-10-29: Merged native-macos through 73a2c49; REQUESTS.md has no new external requests. Its split form addresses the Swift type-check timeout from run 40833893160. Full Python matrix at 258e3d8 passed (40833893150), as did the Windows build/tests/installer job (123314102495).
- 2026-10-29: Expanded vocabulary CI found list.pair/list.middle/list.end missing on both clients. Windows now uses Words.List for people, recipients, copy approvals and rule scopes. macOS owner: replace comma joins in those user-visible lists with the same shared list templates; do not exempt these keys.


- 2026-10-29: Vocabulary coverage now includes keys in ternaries and data-driven arrays, plus real dynamic translation prefixes; the original literal t(...) scan missed these. CI scanner regressions are in tests/test_native_parity.py. Add actual corresponding controls if new missing keys appear; do not add inert lists.
- 2026-10-29: Windows voice now uses Microsoft System.Speech 8.0 / desktop SAPI because Windows.Media.SpeechRecognition requires package identity, unavailable in our Inno/ZIP distribution. It uses the installed en-US or zh-CN recognizer and desktop microphone permission, never a browser. native.voice_hint is corrected; native.voice_language_missing explains the OS language-component prerequisite. See https://learn.microsoft.com/en-us/windows/apps/develop/input/speech-recognition and https://www.nuget.org/packages/System.Speech/8.0.0.
- 2026-10-29: Composer mapping correction: reference permits sending a quote without typed text, stops dictation on send, and locks against duplicate Enter submissions. Windows now does all three. macOS Model.send/sendThread currently reject empty typed text even with quote; please allow quote-only sends, lock thread sends, and stop SpeechInput on successful send/navigation. Keep the existing draft-race protection.


- 2026-10-29: Reviewed the full implementation mappings and marked corresponding rows done (gate 1 only). Gate 2 still requires CI at the latest head; gate 3 remains the person's. macOS freshToken/post/connect remain pending: Client currently stores immutable base/token and reuses them after SSE reconnect. Please reread RELIC_HOME/app.json (default ~/.relic), validate /api/lifecycle against token/pid/instance, update the transport and reconnect events. A POST may retry only the explicit 403 missing-token rejection, never an ambiguous write failure. Windows implements this with mock HTTP regression coverage.
- 2026-10-29: macOS ProtocolForm already exposes strength/rules, but still sends a supersedes field that issue_protocol_as_person ignores. Please remove that misleading input/payload and use shared native.protocol_* labels (including strength/rules/rules_hint) in the same order as Windows. Preserve summary_for_person and inherit; no new engine semantics are requested.
- 2026-10-29: Removed the Edge/Chrome/app-mode launch path. relic_app.py's normal entry launches the native executable and lets it own the server; --serve and explicit headless/lifecycle CLI operations remain. /api/install-window now returns 410 without launching anything. scripts/install.py no longer creates the old macOS shell launcher. Native discovery rejects shell wrappers. No native/macos files were edited by the shared owner.
- 2026-10-29: Merged native-macos through 081c753 and read REQUESTS.md. Requested speech metadata, platform substitutions, Enter/Shift-Enter contract and inventory updates are applied. Last full Python package matrix at 75192db passed in run 40831648376; Windows/macOS native jobs passed in run 40831648315. New changes await CI.


- 2026-10-29: Person-issued protocol form must expose both weak guidance and strong executable rules, using the existing /protocols body (strength, rules, summary_for_person, inherit). Added shared native.protocol_strength, native.protocol_rules, native.protocol_rules_hint. Windows has both modes; macOS owner should apply this contract in its form.
- 2026-10-29: Latest native build jobs at 184b381 passed on Windows/macOS (run 40830357357); parity stayed failing. Python CI found native_package.py missing explicit creationflags at the Inno compiler boundary; it now uses the shared helper, with no local execution.

- 2026-10-29: Merged main at 10b0965 (hook/console fixes); native_host.py now uses relic_core.process.creation_flags. Mock-only native-host tests assert the flags.
- 2026-10-29: Parity substitutions support platform_keys.windows/macos with individual reasons. Browser installer/speech tutorial labels are replaced by native package/OS speech flows; native controls still require real implementations. REQUESTS.md shortcut note: the raised full-reference contract retains Enter=send and Shift-Enter=newline; Cmd-Enter on macOS may be an additional alias. Do not exempt these two labels as browser-only, or change native/macos here.

- 2026-10-29: Merged native-macos through 4f95775. Its speech request is implemented: native.speech, native.speech_permission, native.microphone_permission, native.speech_unavailable are shared /api/i18n keys. Packaging writes both macOS usage-description keys and en.lproj/zh-Hans.lproj/InfoPlist.strings from those lists; native.voice_hint and native.voice_system describe Windows speech. No browser speech implementation is used.
- 2026-10-29: Applied REQUESTS.md inventory corrections: session search, unread/recent chat, persisted drafts/recipients/quotes, read-by disclosure, history paging, Markdown file/line links, rule examples and task evidence. Document payload is body. CI already runs every push; native-macos now gets its own --platform macos parity output, while native-apps requires both.
- 2026-10-29: The parity inventory gate now also rejects pending screen rows in addition to named app.js functions. No row is promoted based on key presence alone.

- 2026-10-29: Full parity replaces phased delivery. `scripts/check_native_parity.py` fails on missing reference routes, literal i18n keys, or pending function rows. Only native implementation source counts. `native/parity-allowlist.json` initially exempts only browser installation. macOS owns `native/macos/**`; requests go in its `REQUESTS.md`; report completed inventory mappings in its `STATUS.md`.
- 2026-10-29: Existing `/api/i18n` remains the vocabulary contract. Person-issued weak protocol form now sends required `rationale` and `trigger`, plus `inherit`. Four `native.protocol_*` labels were added to the shared en-US and zh-CN files.
