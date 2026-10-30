// Injected into the reference's closure by Playwright only. Calls the existing
// production views and controls; does not replace their markup or styles.
const visualCcLoads = [];
Object.defineProperty(window, '__relicVisualSettingsState', {get: () => ({
  source: 'actual production closure settingsPane.current; read-only snapshot',
  current: settingsPane?.current ?? null
})});
const readVisualCc = () => JSON.parse(JSON.stringify({asked: ccAsked, cc: S.cc, copies_connected: !!(ccBox && ccBox.isConnected)}));
Object.defineProperty(window, '__relicVisualCcState', {get: () => ({
  source: 'actual production closure S.cc and ccAsked; detached read-only snapshot',
  ...readVisualCc(), loads: JSON.parse(JSON.stringify(visualCcLoads))
})});
async function visualLoadCc(stage) {
  const record = {stage, before: readVisualCc(), requested_at: performance.now(), status: 'loading'};
  visualCcLoads.push(record);
  try {
    const pending = loadCc();
    record.request_asked = ccAsked;
    await pending;
    record.after = readVisualCc(); record.completed_at = performance.now();
    if (!Number.isSafeInteger(record.request_asked) || record.request_asked !== record.before.asked + 1 ||
        record.after.asked !== record.request_asked || record.after.cc.loaded !== true ||
        !Array.isArray(record.after.cc.items) || !Number.isSafeInteger(record.after.cc.unread) || record.after.cc.unread < 0) {
      throw new Error('Production loadCc was superseded or did not establish measured CC readiness: ' + stage);
    }
    record.status = 'ready';
  } catch (error) {
    record.after = readVisualCc(); record.status = 'failed'; record.error = String(error);
    throw error;
  }
}
window.__relicVisual = async (scene, fixture) => {
  const sceneState = fixture.scene_state;
  const liveScene = scene.startsWith('live-');
  if (liveScene && (!sceneState || sceneState.scene !== scene || !sceneState.live || !sceneState.org || !sceneState.member)) throw new Error('Live scene needs its actual prepared fixture response: ' + scene);
  closeLayer(); closeCard(); closeMenu(); closeMention();
  settingsPane = null;
  S.quote = null; S.digestOpen = false; S.plainMode = false; S.thread = null;
  S.pane = 'org'; S.sideOpen = true; S.panelOpen = window.innerWidth > 1180;
  S.folded.clear(); S.search = ''; $('#search').value = '';
  await loadOrgs();
  await openOrg(sceneState?.org || fixture.org, { kind: 'group', member: null });
  // loadCc redraws the appbar. Complete it before opening menus or any other
  // scene control, without assigning a badge, unread total, or loaded state.
  await visualLoadCc('before-scene-controls');
  save('relic.plain.' + S.orgId, false);
  toggleSide(true); togglePanel(S.panelOpen);
  if (scene === 'settings-navigation-hover') { openSettings('appearance'); return; }
  if (scene.startsWith('settings-')) { openSettings(scene.slice(9)); return; }
  if (scene.startsWith('menu-')) { const k = scene.slice(5); openAppMenu(k, document.querySelector('[data-menu="' + k + '"]') || document.querySelector('.ab-menu')); return; }
  if (scene.startsWith('file-')) { await openFile(fixture.files[scene.slice(5)], scene === 'file-code' ? 2 : undefined); return; }
  switch (scene) {
    case 'group': break;
    case 'private': await go({ kind: 'secretary', member: fixture.member }); await loadChat(true); break;
    case 'live-busy': case 'live-tool-output': case 'live-typing': {
      // openOrg above refreshed the real snapshot, including embedded state.
      await openOrg(sceneState.org, { kind: sceneState.member === secretaryName() ? 'secretary' : 'member', member: sceneState.member });
      if (!member(sceneState.member)?.embedded || S.live[sceneState.member]?.status?.state !== sceneState.state) throw new Error('Prepared live state was not loaded through the production API: ' + scene);
      break;
    }
    case 'thread': await openThread(Number(fixture.thread)); break;
    case 'overview': setPane('org'); break;
    case 'workspace': S.workMember = fixture.member; setPane('work'); break;
    case 'copies': openCopies(); await visualLoadCc('after-open-copies'); break;
    case 'copy-rules':
      openCopies(); await visualLoadCc('after-open-copies');
      document.querySelectorAll('#layer details').forEach(x => { if (!x.open) x.querySelector('summary').click(); });
      break;
    case 'chart': openChart(fixture.org); break;
    case 'new-org': orgDialog(); break;
    case 'member-app': await memberDialog({ mode: 'app' }); break;
    case 'member-host': case 'member-host-model-suggestions': await memberDialog({ mode: 'host' }); break;
    case 'member-existing': case 'member-existing-seat-suggestions': await memberDialog({ mode: 'existing' }); break;
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
    case 'plain': save('relic.plain.' + S.orgId, true); S.plainMode = true; for (const item of S.chat.items) if (typeof item.id === 'number') S.plain[item.id] = fixture.plain; renderAll(true); break;
    case 'quick-start': S.orgId = null; S.orgs = []; S.snap = null; S.chat = null; renderAll(true); break;
    default: throw new Error('Unimplemented reference scene: ' + scene);
  }
};
