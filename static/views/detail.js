viewInits.detail = async function (params) {
  const el = document.getElementById('view-detail');
  if (!params.promptId) {
    el.innerHTML = '<div class="empty-state"><h3>Select a prompt from the Dashboard</h3></div>';
    return;
  }
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading...</div>';
  try {
    const p = await api('/prompts/' + params.promptId);
    const activeV = p.active_version;
    const riskClass = p.risk_tier === 'High' || p.risk_tier === 'Prohibited' ? 'badge-red'
      : p.risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
    const statusClass = p.status === 'Active' ? 'badge-green' : p.status === 'Draft' ? 'badge-blue'
      : p.status === 'Retired' ? 'badge-red' : 'badge-amber';

    let html = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">
        <div>
          <h2>${esc(p.title)}</h2>
          <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
            <span class="badge ${statusClass}">${esc(p.status)}</span>
            <span class="badge ${riskClass}">${esc(p.risk_tier)}</span>
            <span class="badge badge-purple">${esc(p.prompt_type)}</span>
            <span class="badge badge-blue">${esc(p.deployment_target)}</span>
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-outline btn-sm" onclick="runComplianceDetail('${p.prompt_id}')">Run Compliance</button>
        </div>
      </div>`;

    // Active version
    html += '<div class="card"><div class="card-header"><span class="card-title">Active Version</span></div>';
    if (activeV) {
      html += `<div style="margin-bottom:8px;font-size:13px;color:var(--text2)">v${activeV.version_number} &mdash; ${esc(activeV.change_summary || '')} &mdash; ${timeAgo(activeV.created_at)}</div>`;
      html += `<div class="prompt-text">${esc(activeV.prompt_text)}</div>`;
    } else {
      html += '<p style="color:var(--text2)">No active version. Activate one below.</p>';
    }
    html += '</div>';

    // Compliance result for active version
    if (activeV && activeV.version_id) {
      html += '<div id="detail-compliance"></div>';
    }

    // Versions
    html += `<div class="card">
      <div class="collapsible-header" onclick="this.classList.toggle('open');document.getElementById('detail-versions').classList.toggle('open')">
        <span class="card-title">All Versions (${p.versions.length})</span>
      </div>
      <div id="detail-versions" class="collapsible-body">
      <table><thead><tr><th>Version</th><th>Created</th><th>Summary</th><th>Active</th><th>Actions</th></tr></thead><tbody>`;
    p.versions.slice().reverse().forEach(v => {
      const activeTag = v.is_active ? '<span class="badge badge-green">Active</span>' : '';
      const activateBtn = v.is_active ? '' : `<button class="btn btn-outline btn-sm" onclick="activateV('${p.prompt_id}','${v.version_id}')">Activate</button>`;
      html += `<tr>
        <td>v${v.version_number}</td>
        <td style="color:var(--text2)">${timeAgo(v.created_at)}</td>
        <td>${esc(v.change_summary || '')}</td>
        <td>${activeTag}</td>
        <td>${activateBtn}</td>
      </tr>`;
    });
    html += '</tbody></table></div></div>';
    el.innerHTML = html;

    // Load compliance for active version
    if (activeV && activeV.version_id) {
      loadComplianceForVersion(activeV.version_id);
    }
  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + esc(err.message) + '</p></div>';
  }
};

async function loadComplianceForVersion(versionId) {
  const container = document.getElementById('detail-compliance');
  if (!container) return;
  try {
    const resp = await api('/compliance-checks?version_id=' + versionId);
  } catch (e) { /* no compliance endpoint for listing by version yet */ }
}

async function activateV(promptId, versionId) {
  try {
    await api('/prompts/' + promptId + '/versions/' + versionId + '/activate', { method: 'POST' });
    toast('Version activated');
    navigate('detail', { promptId });
  } catch (e) { toast(e.message, 'error'); }
}

async function runComplianceDetail(promptId) {
  try {
    const p = await api('/prompts/' + promptId);
    const activeV = p.active_version;
    if (!activeV) { toast('Activate a version first', 'error'); return; }
    toast('Running compliance check...');
    const job = await api('/compliance-checks', { method: 'POST', body: { version_id: activeV.version_id, force_refresh: true } });
    const result = await pollJob(job.job_id);
    if (result.status === 'Complete') {
      toast('Compliance check complete: ' + (result.result ? result.result.overall_result : ''));
    } else {
      toast('Failed: ' + (result.error_message || ''), 'error');
    }
    navigate('detail', { promptId });
  } catch (e) { toast(e.message, 'error'); }
}
