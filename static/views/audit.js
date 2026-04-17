(function () {
  const PAGE_SIZE = 25;
  let page = 0, filter = '';

  viewInits.audit = function () { page = 0; filter = ''; renderAudit(); };

  function renderAudit() {
    const el = document.getElementById('view-audit');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Audit Log</h2>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="audit-filter" onchange="window._auditFilter(this.value)" style="width:220px">
            <option value="">All actions</option>
            <option value="Created">Created</option>
            <option value="Edited">Edited</option>
            <option value="Activated">Activated</option>
            <option value="Approved">Approved</option>
            <option value="Retired">Retired</option>
            <option value="ComplianceChecked">ComplianceChecked</option>
            <option value="PromptImported">PromptImported</option>
            <option value="UpgradeProposed">UpgradeProposed</option>
            <option value="UpgradeResponseRecorded">UpgradeResponseRecorded</option>
            <option value="UpgradeApplied">UpgradeApplied</option>
            <option value="UpgradeAbandoned">UpgradeAbandoned</option>
            <option value="InjectionDetected">InjectionDetected</option>
          </select>
          <button class="btn btn-outline btn-sm" onclick="window._auditRefresh()">Refresh</button>
        </div>
      </div>
      <div id="audit-table"></div>
      <div id="audit-pag" class="pagination"></div>`;
    loadAudit();
  }

  async function loadAudit() {
    const container = document.getElementById('audit-table');
    container.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading...</div>';
    try {
      let url = '/audit-log?skip=' + (page * PAGE_SIZE) + '&limit=' + PAGE_SIZE;
      if (filter) url += '&action=' + encodeURIComponent(filter);
      const entries = await api(url);

      if (!entries.length && page === 0) {
        container.innerHTML = '<div class="empty-state"><h3>No audit entries</h3></div>';
        document.getElementById('audit-pag').innerHTML = '';
        return;
      }

      let html = '<div class="card" style="padding:12px 20px">';
      entries.forEach((e, i) => {
        const ac = actionBadge(e.action);
        const badgeColor = actionDotColor(e.action);
        const eid = e.entity_id ? e.entity_id.substring(0, 8) : '-';
        const det = e.detail && e.detail.length > 120 ? e.detail.substring(0, 120) + '...' : (e.detail || '');
        html += `<div class="timeline-row" id="audit-row-${i}">
          <div class="timeline-badge" style="background:${badgeColor}"></div>
          <div class="timeline-content">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span class="timeline-action badge ${ac}">${esc(e.action)}</span>
              <span class="mono" style="font-size:11px;color:var(--accent)">${esc(e.entity_type || '')}:${esc(eid)}</span>
              <span class="timeline-time" style="margin-left:auto">${fmtTime(e.timestamp)}</span>
            </div>
            ${det ? '<div style="font-size:13px;color:var(--text2);cursor:pointer" onclick="this.style.whiteSpace=this.style.whiteSpace===\\'normal\\'?\\'nowrap\\':\\'normal\\'" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(det) + '</div>' : ''}
          </div>
        </div>`;
      });
      html += '</div>';
      container.innerHTML = html;

      let pag = '';
      if (page > 0) pag += '<button class="btn btn-outline btn-sm" onclick="window._auditPrev()">Previous</button>';
      pag += '<span style="color:var(--text2);font-size:13px;padding:0 12px">Page ' + (page + 1) + '</span>';
      if (entries.length === PAGE_SIZE) pag += '<button class="btn btn-outline btn-sm" onclick="window._auditNext()">Next</button>';
      document.getElementById('audit-pag').innerHTML = pag;
    } catch (e) {
      container.innerHTML = '<div class="card"><p style="color:var(--red)">' + esc(e.message) + '</p></div>';
    }
  }

  function actionBadge(a) {
    const map = { Created: 'badge-green', Edited: 'badge-amber', Activated: 'badge-green', Approved: 'badge-green',
      Retired: 'badge-red', PromptImported: 'badge-gold', UpgradeProposed: 'badge-purple',
      UpgradeResponseRecorded: 'badge-amber', UpgradeApplied: 'badge-green', UpgradeAbandoned: 'badge-red',
      InjectionDetected: 'badge-red', ComplianceChecked: 'badge-gold', PromptGenerated: 'badge-gold' };
    return map[a] || 'badge-gold';
  }

  function actionDotColor(a) {
    const map = { Created: 'var(--green)', Edited: 'var(--amber)', Activated: 'var(--green)', Approved: 'var(--green)',
      Retired: 'var(--red)', PromptImported: 'var(--accent)', UpgradeProposed: 'var(--purple)',
      UpgradeResponseRecorded: 'var(--amber)', UpgradeApplied: 'var(--green)', UpgradeAbandoned: 'var(--red)',
      InjectionDetected: 'var(--red)', ComplianceChecked: 'var(--accent)', PromptGenerated: 'var(--accent)' };
    return map[a] || 'var(--text2)';
  }

  function fmtTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  window._auditFilter = function (v) { filter = v; page = 0; loadAudit(); };
  window._auditPrev = function () { if (page > 0) { page--; loadAudit(); } };
  window._auditNext = function () { page++; loadAudit(); };
  window._auditRefresh = function () { loadAudit(); };
})();
