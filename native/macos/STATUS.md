# macOS native implementation status

Updated 2026-10-29; branch `native-macos`; scope `native/macos/**` only.

## Current validation

- macOS Release build, 30 XCTest cases, and unsigned app packaging passed at
  `fe453f6` in [Native apps macOS job](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40831000291/job/123304950300).
- Subsequent parity/detail changes are being validated by the next push.
- The reference route scan has zero missing macOS routes. All remaining literal
  vocabulary misses are platform substitutions documented in `REQUESTS.md`.
  The shared flow/screen table still requires the shared owner's review and
  macOS-column update; this branch cannot edit the shared table or allowlist.
- This is an implementation handoff, not the final full-parity acceptance report.
  `REQUESTS.md` lists shared i18n, packaging and CI changes needed from native-apps.
- No native window, browser, editor, local Python test suite or permission dialog
  was opened on the Windows gaming machine. Only static local checks ran.

## Screen inventory implementation

The three-column SwiftUI window, native Commands/Dock/notifications, tree/search/
recent/unread/history, per-chat drafts/recipients/quotes, native mention completion,
messages/threads/live tools/permissions, structural approvals, hierarchy edits,
Copies and rules, organization creation, App/host/existing-session member forms,
member identity/avatar/model/config/fresh/open/unbind/forward, secretary setup,
organization chart, workspace/git/files, text/Markdown/JSON/image previews,
plain words/digest, Apple Speech, task reports/evidence, documents/revisions,
transcript pagination and every Settings section have reachable native views.

## Reference-function mappings for the shared contract owner

These rows map JavaScript behavior to native implementations; DOM, HTML, SVG and
browser installer scaffolding are replaced by SwiftUI/AppKit/Finder equivalents.
The table is prose evidence for review, not a source-key or route allowlist.
CI and real-device acceptance remain separate gates.

| Reference function | Native implementation |
| --- | --- |
| `platformInfo@9` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `automaticDelivery@17` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `hostSurfaces@22` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortcutLabel@26` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortcutAction@29` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `absolutePath@46` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `inlineTokens@51` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `append@86` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `h@93` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `icon@148` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `hue@166` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `initial@172` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `dayLabel@179` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `clock@185` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortWhen@186` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `ago@191` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `stateLabel@200` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `taskLabel@204` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `pathLink@207` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `inline@211` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `rich@220` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `mdRun@245` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `quoteBlock@271` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `load@277` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `save@278` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `get@281` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadPlatform@287` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `freshToken@291` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `post@297` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `toast@305` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `lang@313` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `applyPrefs@314` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadPrefs@325` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `setPrefs@329` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `tget@343` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `targ@355` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `t@365` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `tn@369` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadLang@381` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `dname@417` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `roleName@429` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `avatar@432` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `secAvatar@446` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `groupAvatar@452` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `orgBadge@454` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `loadOrgs@460` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `readHash@470` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `writeHash@476` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `openOrg@482` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `refreshSnap@506` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `loadChat@513` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `markSeen@543` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `unreadOf@547` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `scheduleRefresh@554` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `notifyChanges@562` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `liveSlot@576` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `connect@577` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `lastLine@623` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `chatRow@629` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `orgTree@636` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `setFolded@652` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `unfoldTo@656` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderSide@662` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderMe@729` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `pushHist@736` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `goHist@744` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `toggleSide@753` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `go@759` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderAll@769` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderHead@772` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderBanner@802` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `nearBottom@821` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderStream@822` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `watchPlain@853` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `plainState@863` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `requestPlain@868` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `gotPlain@883` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `updatePlain@888` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `togglePlain@896` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `togglePlainOne@904` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `toggleDigest@910` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `loadDigest@916` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `digestCard@927` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `askSecretary@940` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `placeholder@950` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `renderItem@954` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `stripQuote@1013` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `copyText@1014` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `memberItems@1018` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `toolName@1050` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `stepArg@1051` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `actsBlock@1059` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `stepRow@1081` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `liveTurnStart@1102` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `liveItems@1109` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `renderLive@1120` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `permissionCard@1156` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `decide@1161` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `setQuote@1166` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `quotedBody@1174` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeSelBar@1181` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `micButton@1236` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `field@1242` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `composerBox@1249` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `doSend@1264` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `renderComposer@1290` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `toPicker@1312` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `mentionCheck@1331` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `pickMention@1347` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `mentionKey@1357` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeMention@1369` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeMenu@1373` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openMenu@1374` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openContextMenu@1381` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openThread@1400` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `loadThread@1405` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `closeThread@1416` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `renderThread@1417` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `panes@1436` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `setPane@1437` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `togglePanel@1444` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `applyPanelWidth@1450` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `startResize@1454` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `renderPanel@1465` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderWork@1493` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `fileTree@1540` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `fill@1543` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `openFile@1569` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `sizeLabel@1578` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderFile@1579` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `codeView@1602` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderOrgPane@1612` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `hierarchyBlock@1717` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `walk@1720` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `decisionCard@1784` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `scheduleCc@1838` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `loadCc@1839` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `openCopies@1852` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `drawCopies@1859` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `copyState@1874` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `copyCard@1881` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `checkRulesView@1905` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `issuedBy@1922` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `ruleScope@1923` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `exampleText@1933` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `plainRules@1939` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `ackCopy@1942` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `retireCopy@1951` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `closeCard@1964` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `identity@1965` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `pickImage@1972` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `openCard@1986` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `closeLayer@2081` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `scrim@2082` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `harnessList@2088` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `runModes@2094` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `runNotes@2095` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `hostKinds@2102` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `seatOptions@2105` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `memberDialog@2109` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `forwardDialog@2247` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `seatAction@2271` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `openSecretarySetup@2279` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `orgDialog@2288` | Forms.swift: CreateOrgView/MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `openDetails@2310` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `render@2323` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `countTasks@2402` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `reportBlock@2405` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `traceView@2410` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `fetchMore@2427` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `draw@2434` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `sections@2454` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `openSettings@2458` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `draw@2464` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `setRow@2474` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `segControl@2477` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `toggleControl@2480` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `redraw@2485` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawProfile@2486` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawAppearance@2501` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawLanguage@2510` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawVoice@2525` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawNotify@2533` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawHarness@2545` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `onInstall@2595` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawAbout@2603` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `svgEl@2621` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `protoName@2627` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `openChart@2635` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `applyView@2665` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `clampView@2672` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `fitChart@2677` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `zoomAt@2687` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `zoomBy@2695` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `panBy@2696` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `wireChart@2702` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `loadChart@2772` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `reloadChart@2781` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `redrawChart@2786` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `drawChart@2791` | ChartView.swift: Canvas edges/cards, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `menus@2965` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `abBtn@2966` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `renderAppbar@2970` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `openAppMenu@2995` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `menuItem@3003` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `appMenu@3011` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `focusSearch@3060` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `pasteText@3061` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `quoteSelection@3066` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `shortcutsDialog@3075` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `shortcut@3082` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `installApp@3096` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `installPage@3115` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `wire@3130` | RelicApp.swift: RelicApp/Delegate; Client.swift: ServerHost; Model.swift: start/stop; CreateOrgView/SecretarySetup |

## Real Mac acceptance still required

On macOS 14+ Apple silicon, the person or HaochenGu should run the unsigned bundle:
launch from Finder/Dock; create or borrow the local engine; close/reopen and Quit;
confirm owned-child cleanup and borrowed-server survival; verify all three columns
against the reference, keyboard/IME/selection/VoiceOver, both languages, resizing,
file links and previews, notifications and notification navigation, microphone and
speech permission flows, CLI/desktop capability gating, session launch and manual
forwarding. CI does not open native windows or establish these device behaviors.
