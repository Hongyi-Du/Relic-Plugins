// Injected into the reference's closure by Playwright only. Calls the existing
// production views and controls; does not replace their markup or styles.
window.__relicVisual = async (scene, fixture) => {
  closeLayer(); closeCard(); closeMenu(); closeMention();
  settingsPane = null;
  S.quote = null; S.digestOpen = false; S.plainMode = false; S.thread = null;
  S.pane = 'org'; S.sideOpen = true; S.panelOpen = window.innerWidth > 1180;
  S.folded.clear(); S.search = ''; $('#search').value = '';
  await loadOrgs();
  await openOrg(fixture.org, { kind: 'group', member: null });
  toggleSide(true); togglePanel(S.panelOpen);
  if (scene.startsWith('settings-')) { openSettings(scene.slice(9)); return; }
  if (scene.startsWith('menu-')) { const k = scene.slice(5); openAppMenu(k, document.querySelector('[data-menu="' + k + '"]') || document.querySelector('.ab-menu')); return; }
  if (scene.startsWith('file-')) { await openFile(fixture.files[scene.slice(5)], scene === 'file-code' ? 2 : undefined); return; }
  switch (scene) {
    case 'group': break;
    case 'private': await go({ kind: 'secretary', member: fixture.member }); await loadChat(true); break;
    case 'thread': await openThread(Number(fixture.thread)); break;
    case 'overview': setPane('org'); break;
    case 'workspace': S.workMember = fixture.member; setPane('work'); break;
    case 'copies': openCopies(); break;
    case 'copy-rules': openCopies(); setTimeout(() => document.querySelectorAll('#layer details').forEach(x => x.open = true), 100); break;
    case 'chart': openChart(fixture.org); break;
    case 'new-org': orgDialog(); break;
    case 'member-app': await memberDialog({ mode: 'app' }); break;
    case 'member-host': await memberDialog({ mode: 'host' }); break;
    case 'member-existing': await memberDialog({ mode: 'existing' }); break;
    case 'member-card': await openCard(fixture.member, document.querySelector('#chat-head')); break;
    case 'member-edit': await memberDialog({ edit: fixture.member, mode: 'host' }); break;
    case 'forward': await forwardDialog('advisor'); break;
    case 'secretary': openSecretarySetup(); break;
    case 'tasks': await openDetails('tasks'); break;
    case 'task-report': await openDetails('tasks', { task: fixture.task }); break;
    case 'protocols': await openDetails('protocols'); break;
    case 'documents': await openDetails('docs'); break;
    case 'trajectory': await openDetails('trace', { member: fixture.member }); break;
    case 'shortcuts': shortcutsDialog(); break;
    case 'recipients': document.querySelector('#composer .to-picker, #composer .to-btn, #composer .bar button').click(); break;
    case 'quote': setQuote(dname(fixture.member), fixture.quote); break;
    case 'mention': { const ta = document.querySelector('#composer textarea'); ta.value = '@'; ta.focus(); ta.setSelectionRange(1, 1); ta.dispatchEvent(new Event('input', { bubbles: true })); break; }
    case 'digest': S.digest = fixture.digest; S.digestOpen = true; renderBanner(); break;
    case 'plain': S.plainMode = true; for (const item of S.chat.items) if (typeof item.id === 'number') S.plain[item.id] = fixture.plain; renderAll(true); break;
    case 'quick-start': S.orgId = null; S.orgs = []; S.snap = null; S.chat = null; renderAll(true); break;
    default: throw new Error('Unimplemented reference scene: ' + scene);
  }
};
