// Prompt Detail view — full prompt text, copy, edit, version history with view
let _detailPromptId = null;
let _detailVersions = [];
let _detailSelectedVersion = null;

viewInits.detail = async function (params) {
  const el = document.getElementById('view-detail');
  _detailPromptId = params.promptId;
  if (!_detailPromptId) {
    el.innerHTML = '<div class="empty-state"><h3>Select a prompt from the Dashboard</h3></div>';
    return;
  }
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading...</div>';
  try {
    const p = await api('/prompts/' + _detailPromptId);
    _detailVersions = p.versions || [];
    const activeV = p.active_version;
    _detailSelectedVersion = activeV || (_detailVersions.length ? _detailVersions[_detailVersions.length - 1] : null);

    const riskClass = p.risk_tier === 'High' || p.risk_tier === 'Prohibited' ? 'badge-red'
      : p.risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
    const statusClass = p.status === 'Active' ? 'badge-green' : p.status === 'Draft' ? 'badge-blue'
      : p.status === 'Retired' ? 'badge-red' : 'badge-amber';

    let html = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">
        <div>
          <h2 style="font-size:20px">${esc(p.title)}</h2>
          <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
            <span class="badge ${statusClass}">${esc(p.status)}</span>
            <span class="badge ${riskClass}">${esc(p.risk_tier)}</span>
            <span class="badge badge-purple">${esc(p.prompt_type)}</span>
            <span class="badge badge-gold">${esc(p.deployment_target)}</span>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:16px">
          <div id="detail-grade-badge"></div>
          <button class="btn btn-gold btn-sm" onclick="runComplianceDetail('${p.prompt_id}')">Run Compliance</button>
        </div>
      </div>`;

    // Two-column layout: prompt text left, compliance panel right
    html += '<div class="detail-columns">';

    // Left column: prompt text
    html += `<div>
      <div class="card">
        <div class="card-header">
          <span class="card-title" id="detail-version-label"></span>
          <div style="display:flex;gap:8px">
            <button class="btn btn-outline btn-sm" onclick="detailCopyPrompt()">Copy</button>
            <button class="btn btn-outline btn-sm" onclick="detailEditAsNew('${p.prompt_id}')">Edit as New Version</button>
          </div>
        </div>
        <div class="prompt-text" id="detail-prompt-text" style="min-height:300px"></div>
      </div>
    </div>`;

    // Right column: compliance scores
    html += '<div id="detail-compliance-panel"><div class="card"><div class="card-title" style="margin-bottom:12px">Compliance Scores</div><p style="color:var(--text2);font-size:13px">Run a compliance check to see scores.</p></div></div>';
    html += '</div>'; // end detail-columns

    // Version history — open by default
    html += `<div class="card">
      <div class="card-title" style="margin-bottom:12px">Version History (${_detailVersions.length})</div>
      <table>
        <thead><tr><th>Version</th><th>Created</th><th>By</th><th>Summary</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody id="detail-version-rows"></tbody>
      </table>
    </div>`;

    // New version form (hidden by default)
    html += `<div id="detail-new-version" class="card" style="display:none">
      <div class="card-title" style="margin-bottom:12px">Create New Version</div>
      <div class="form-group">
        <label>Prompt Text</label>
        <textarea id="detail-new-text" rows="12"></textarea>
      </div>
      <div class="form-group">
        <label>Change Summary</label>
        <input type="text" id="detail-new-summary" placeholder="What changed in this version">
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="detailSaveVersion('${p.prompt_id}')">Save New Version</button>
        <button class="btn btn-outline" onclick="document.getElementById('detail-new-version').style.display='none'">Cancel</button>
      </div>
    </div>`;

    el.innerHTML = html;
    renderDetailVersionRows(p);
    renderDetailPromptText();

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + esc(err.message) + '</p></div>';
  }
};

function renderDetailPromptText() {
  const textEl = document.getElementById('detail-prompt-text');
  const labelEl = document.getElementById('detail-version-label');
  if (!textEl || !_detailSelectedVersion) return;
  textEl.textContent = _detailSelectedVersion.prompt_text || '(empty)';
  const activeTag = _detailSelectedVersion.is_active ? ' — Active' : '';
  labelEl.textContent = 'v' + _detailSelectedVersion.version_number + activeTag;
}

function renderDetailVersionRows(prompt) {
  const tbody = document.getElementById('detail-version-rows');
  if (!tbody) return;
  let html = '';
  _detailVersions.slice().reverse().forEach(v => {
    const isSelected = _detailSelectedVersion && _detailSelectedVersion.version_id === v.version_id;
    const activeBadge = v.is_active ? '<span class="badge badge-green">Active</span>' : '<span style="color:var(--text2)">Draft</span>';
    const viewClass = isSelected ? 'btn-primary' : 'btn-outline';
    const activateBtn = v.is_active ? '' : `<button class="btn btn-outline btn-sm" onclick="activateV('${prompt.prompt_id}','${v.version_id}')">Activate</button>`;
    html += `<tr${isSelected ? ' style="background:var(--surface2)"' : ''}>
      <td><strong>v${v.version_number}</strong></td>
      <td style="color:var(--text2)">${timeAgo(v.created_at)}</td>
      <td style="color:var(--text2);font-size:13px">${esc(v.created_by ? v.created_by.substring(0, 8) + '...' : '')}</td>
      <td>${esc(v.change_summary || '')}</td>
      <td>${activeBadge}</td>
      <td style="display:flex;gap:6px">
        <button class="btn ${viewClass} btn-sm" onclick="detailViewVersion('${v.version_id}')">View</button>
        ${activateBtn}
      </td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

function detailViewVersion(versionId) {
  const v = _detailVersions.find(v => v.version_id === versionId);
  if (v) {
    _detailSelectedVersion = v;
    renderDetailPromptText();
    // Re-render rows to update highlight
    if (_detailPromptId) {
      api('/prompts/' + _detailPromptId).then(p => renderDetailVersionRows(p)).catch(() => {});
    }
  }
}

function detailCopyPrompt() {
  if (!_detailSelectedVersion || !_detailSelectedVersion.prompt_text) {
    toast('No prompt text to copy', 'error');
    return;
  }
  navigator.clipboard.writeText(_detailSelectedVersion.prompt_text)
    .then(() => toast('Prompt text copied to clipboard'))
    .catch(() => toast('Copy failed — select text manually', 'error'));
}

function detailEditAsNew(promptId) {
  if (!_detailSelectedVersion) { toast('No version selected', 'error'); return; }
  const formEl = document.getElementById('detail-new-version');
  const textEl = document.getElementById('detail-new-text');
  formEl.style.display = 'block';
  textEl.value = _detailSelectedVersion.prompt_text || '';
  textEl.style.height = 'auto';
  textEl.style.height = textEl.scrollHeight + 'px';
  document.getElementById('detail-new-summary').value = '';
  formEl.scrollIntoView({ behavior: 'smooth' });
}

async function detailSaveVersion(promptId) {
  const text = document.getElementById('detail-new-text').value.trim();
  const summary = document.getElementById('detail-new-summary').value.trim();
  if (!text) { toast('Prompt text is required', 'error'); return; }
  try {
    await api('/prompts/' + promptId + '/versions', {
      method: 'POST',
      body: { prompt_text: text, change_summary: summary || null },
    });
    toast('New version created');
    navigate('detail', { promptId });
  } catch (e) { toast(e.message, 'error'); }
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
    const v = _detailSelectedVersion || p.active_version;
    if (!v) { toast('No version to score', 'error'); return; }
    toast('Running compliance check...');
    const job = await api('/compliance-checks', { method: 'POST', body: { version_id: v.version_id, force_refresh: true } });
    const result = await pollJob(job.job_id);
    if (result.status === 'Complete') {
      toast('Compliance check complete: ' + (result.result ? result.result.overall_result : ''));
    } else {
      toast('Failed: ' + (result.error_message || ''), 'error');
    }
    navigate('detail', { promptId });
  } catch (e) { toast(e.message, 'error'); }
}
