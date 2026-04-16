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

      let html = '<div class="card" style="padding:0;overflow:hidden"><table><thead><tr><th>Time</th><th>Action</th><th>Entity</th><th>Actor</th><th>Detail</th></tr></thead><tbody>';
      entries.forEach(e => {
        const ac = actionBadge(e.action);
        const eid = e.entity_id ? e.entity_id.substring(0, 8) + '...' : '-';
        const det = e.detail && e.detail.length > 100 ? e.detail.substring(0, 100) + '...' : (e.detail || '-');
        html += `<tr>
          <td style="white-space:nowrap;color:var(--text2);font-size:13px">${fmtTime(e.timestamp)}</td>
          <td><span class="badge ${ac}">${esc(e.action)}</span></td>
          <td style="font-size:13px"><span style="color:var(--text2)">${esc(e.entity_type || '')}</span><br><code style="font-size:11px;color:var(--accent)">${esc(eid)}</code></td>
          <td style="font-size:13px">${esc(e.user_id || '')}</td>
          <td style="font-size:13px;color:var(--text2);max-width:300px">${esc(det)}</td>
        </tr>`;
      });
      html += '</tbody></table></div>';
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
      Retired: 'badge-red', PromptImported: 'badge-blue', UpgradeProposed: 'badge-purple',
      UpgradeResponseRecorded: 'badge-amber', UpgradeApplied: 'badge-green', UpgradeAbandoned: 'badge-red',
      InjectionDetected: 'badge-red', ComplianceChecked: 'badge-blue' };
    return map[a] || 'badge-blue';
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
