// Audit Log view — paginated list of all audit events
(function () {
  const PAGE_SIZE = 25;
  let currentPage = 0;
  let currentFilter = '';

  viewInits.audit = function () {
    currentPage = 0;
    currentFilter = '';
    renderAuditView();
  };

  function renderAuditView() {
    const el = document.getElementById('view-audit');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Audit Log</h2>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="audit-filter" onchange="window._auditFilterChange(this.value)" style="width:220px">
            <option value="">All actions</option>
            <option value="PromptImported">PromptImported</option>
            <option value="UpgradeProposed">UpgradeProposed</option>
            <option value="UpgradeResponseRecorded">UpgradeResponseRecorded</option>
            <option value="ClassificationOverridden">ClassificationOverridden</option>
            <option value="UpgradeApplied">UpgradeApplied</option>
            <option value="UpgradeAbandoned">UpgradeAbandoned</option>
            <option value="InjectionDetected">InjectionDetected</option>
          </select>
          <button class="btn btn-outline btn-sm" onclick="window._auditRefresh()">Refresh</button>
        </div>
      </div>
      <div id="audit-table-container"></div>
      <div id="audit-pagination" class="pagination"></div>`;
    loadAuditPage();
  }

  async function loadAuditPage() {
    const container = document.getElementById('audit-table-container');
    container.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading...</div>';

    try {
      const skip = currentPage * PAGE_SIZE;
      let url = '/audit-log?skip=' + skip + '&limit=' + PAGE_SIZE;
      if (currentFilter) url += '&action=' + encodeURIComponent(currentFilter);

      const entries = await api(url);

      if (entries.length === 0 && currentPage === 0) {
        container.innerHTML = '<div class="empty-state"><h3>No audit entries</h3><p>Events will appear here as you use the system.</p></div>';
        document.getElementById('audit-pagination').innerHTML = '';
        return;
      }

      let html = `
        <div class="card" style="padding:0;overflow:hidden">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Actor</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>`;

      entries.forEach(e => {
        const actionClass = getActionBadgeClass(e.action);
        const entityId = e.entity_id ? e.entity_id.substring(0, 8) + '...' : '-';
        const detail = e.detail && e.detail.length > 120 ? e.detail.substring(0, 120) + '...' : (e.detail || '-');
        html += `
          <tr>
            <td style="white-space:nowrap;color:var(--text2);font-size:13px">${formatTime(e.created_at)}</td>
            <td><span class="badge ${actionClass}">${escapeHtml(e.action)}</span></td>
            <td style="font-size:13px"><span style="color:var(--text2)">${escapeHtml(e.entity_type || '')}</span><br><code style="font-size:11px;color:var(--accent)">${escapeHtml(entityId)}</code></td>
            <td style="font-size:13px">${escapeHtml(e.actor || '')}</td>
            <td style="font-size:13px;color:var(--text2);max-width:350px">${escapeHtml(detail)}</td>
          </tr>`;
      });

      html += '</tbody></table></div>';
      container.innerHTML = html;

      // Pagination
      const pagEl = document.getElementById('audit-pagination');
      let pagHtml = '';
      if (currentPage > 0) {
        pagHtml += '<button class="btn btn-outline btn-sm" onclick="window._auditPrev()">Previous</button>';
      }
      pagHtml += '<span style="color:var(--text2);font-size:13px;padding:0 12px">Page ' + (currentPage + 1) + '</span>';
      if (entries.length === PAGE_SIZE) {
        pagHtml += '<button class="btn btn-outline btn-sm" onclick="window._auditNext()">Next</button>';
      }
      pagEl.innerHTML = pagHtml;

    } catch (err) {
      container.innerHTML = '<div class="card"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
    }
  }

  function getActionBadgeClass(action) {
    switch (action) {
      case 'PromptImported': return 'badge-blue';
      case 'UpgradeProposed': return 'badge-purple';
      case 'UpgradeResponseRecorded': return 'badge-amber';
      case 'ClassificationOverridden': return 'badge-amber';
      case 'UpgradeApplied': return 'badge-green';
      case 'UpgradeAbandoned': return 'badge-red';
      case 'InjectionDetected': return 'badge-red';
      default: return 'badge-blue';
    }
  }

  function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  // Expose handlers to global scope
  window._auditFilterChange = function (val) {
    currentFilter = val;
    currentPage = 0;
    loadAuditPage();
  };
  window._auditPrev = function () {
    if (currentPage > 0) { currentPage--; loadAuditPage(); }
  };
  window._auditNext = function () {
    currentPage++;
    loadAuditPage();
  };
  window._auditRefresh = function () {
    loadAuditPage();
  };
})();
