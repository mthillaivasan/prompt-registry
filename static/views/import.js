viewInits['import'] = function (params) {
  const el = document.getElementById('view-import');
  if (params && params.proposalId) { loadProposal(el, params.proposalId); return; }
  el.innerHTML = `
    <h2 style="margin-bottom:20px">Import &amp; Upgrade</h2>
    <div class="card">
      <div class="form-group"><label>Paste Existing Prompt</label>
        <textarea id="import-text" rows="12" placeholder="Paste your existing prompt text here for analysis..."></textarea>
      </div>
      <button class="btn btn-primary" id="import-btn" onclick="importAnalyse()">Analyse Prompt</button>
    </div>
    <div id="import-result"></div>`;
};

async function importAnalyse() {
  const text = document.getElementById('import-text').value.trim();
  const btn = document.getElementById('import-btn');
  const resultEl = document.getElementById('import-result');
  if (!text) { toast('Paste a prompt first', 'error'); return; }
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Analysing...';
  resultEl.innerHTML = '<div class="loading-state"><div class="spinner"></div> Submitting...</div>';
  try {
    const resp = await api('/prompts/analyse', { method: 'POST', body: { prompt_text: text } });
    resultEl.innerHTML = '<div class="loading-state"><div class="spinner"></div> AI analysis running...</div>';
    const job = await pollJob(resp.job_id);
    if (job.status === 'Complete') {
      toast('Analysis complete');
      await loadProposal(document.getElementById('view-import'), resp.proposal_id);
    } else {
      resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">Failed: ' + esc(job.error_message || 'Unknown') + '</p></div>';
    }
  } catch (e) {
    toast(e.message, 'error');
    resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">' + esc(e.message) + '</p></div>';
  } finally { btn.disabled = false; btn.innerHTML = 'Analyse Prompt'; }
}

async function loadProposal(container, proposalId) {
  container.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading proposal...</div>';
  try {
    const p = await api('/proposals/' + proposalId);
    renderProposal(container, p);
  } catch (e) { container.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + esc(e.message) + '</p></div>'; }
}

function renderProposal(container, p) {
  const responded = new Set((p.user_responses || []).map(r => r.suggestion_id));
  const respMap = {}; (p.user_responses || []).forEach(r => { respMap[r.suggestion_id] = r; });
  const riskClass = p.inferred_risk_tier === 'High' || p.inferred_risk_tier === 'Prohibited' ? 'badge-red'
    : p.inferred_risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
  const statusClass = p.status === 'Applied' ? 'badge-green' : p.status === 'Abandoned' ? 'badge-red'
    : p.status === 'Pending' ? 'badge-blue' : 'badge-amber';
  const isTerminal = p.status === 'Applied' || p.status === 'Abandoned';

  let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div><h2>Upgrade Proposal</h2><p style="color:var(--text2);font-size:13px;margin-top:4px">ID: ${esc(p.proposal_id)}</p></div>
    <span class="badge ${statusClass}">${esc(p.status)}</span>
  </div>`;

  // Classification
  if (p.inferred_purpose) {
    const ptOpts = ['Governance','Analysis','Comms','Classification','Summarisation','Extraction','Comparison','Risk Review'];
    const rtOpts = ['Minimal','Limited','High','Prohibited'];
    const ptSelect = ptOpts.map(o => `<option${o === p.inferred_prompt_type ? ' selected' : ''}>${o}</option>`).join('');
    const rtSelect = rtOpts.map(o => `<option${o === p.inferred_risk_tier ? ' selected' : ''}>${o}</option>`).join('');
    html += `<div class="card"><div class="card-title" style="margin-bottom:12px">Classification</div>
      <table>
        <tr><td style="color:var(--text2);width:180px">Purpose</td><td>${esc(p.inferred_purpose)}</td></tr>
        <tr><td style="color:var(--text2)">Type</td><td><select style="width:auto;min-width:180px" id="import-override-type">${ptSelect}</select></td></tr>
        <tr><td style="color:var(--text2)">Risk Tier</td><td><select style="width:auto;min-width:180px" id="import-override-risk">${rtSelect}</select></td></tr>
        <tr><td style="color:var(--text2)">Confidence</td><td>${esc(p.classification_confidence || '-')}</td></tr>
      </table></div>`;
  }

  // Findings
  if (p.findings && p.findings.length) {
    html += `<div class="card"><div class="card-title" style="margin-bottom:12px">Findings (${p.findings.length})</div>
      <table><thead><tr><th>Dimension</th><th>Score</th><th>Severity</th><th>Finding</th></tr></thead><tbody>`;
    p.findings.forEach(f => {
      const sc = f.severity === 'Blocking' || f.severity === 'Critical' ? 'badge-red' : f.severity === 'High' ? 'badge-amber' : 'badge-blue';
      html += `<tr><td><strong>${esc(f.dimension_code)}</strong><br><span style="font-size:12px;color:var(--text2)">${esc(f.dimension_name)}</span></td>
        <td><div class="score-bar score-${f.current_score}"><span>${f.current_score}/5</span><div class="score-bar-track"><div class="score-bar-fill"></div></div></div></td>
        <td><span class="badge ${sc}">${esc(f.severity)}</span></td>
        <td style="font-size:13px;color:var(--text2)">${esc(f.current_finding)}</td></tr>`;
    });
    html += '</tbody></table></div>';
  }

  // Suggestions
  if (p.suggestions && p.suggestions.length) {
    html += `<div class="card"><div class="card-title" style="margin-bottom:12px">Suggestions (${p.suggestions.length})</div>`;
    p.suggestions.forEach(s => {
      const resp = respMap[s.suggestion_id];
      const has = !!resp;
      const badge = has ? (resp.response === 'Accepted' ? '<span class="badge badge-green">Accepted</span>'
        : resp.response === 'Rejected' ? '<span class="badge badge-red">Rejected</span>'
        : '<span class="badge badge-amber">Modified</span>') : '<span class="badge badge-blue">Pending</span>';
      const imp = s.expected_score_improvement || {};
      const cardClass = has ? (resp.response === 'Accepted' ? 'accepted' : resp.response === 'Rejected' ? 'rejected' : 'modified') : '';
      const fromDot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--red)"></span>`;
      const toDot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--green)"></span>`;
      html += `<div class="suggestion-card ${cardClass}" id="sug-${s.suggestion_id}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div><span class="mono" style="color:var(--amber);font-weight:600">${esc(s.dimension_code)}</span> &mdash; ${esc(s.description)} ${badge}</div>
          <span style="font-size:12px;color:var(--text2);display:flex;align-items:center;gap:4px">${fromDot} ${imp.from || '?'} &rarr; ${toDot} ${imp.to || '?'}</span>
        </div>
        <div style="font-size:13px;color:var(--text2);margin-bottom:8px">${esc(s.rationale)}</div>
        <div class="diff-add">${esc(s.suggested_text)}</div>`;
      if (has && resp.response === 'Modified' && resp.modified_text) {
        html += `<div style="margin-top:4px;font-size:12px;color:var(--text2)">Modified to:</div>
          <div class="diff-add" style="border-color:var(--amber)">${esc(resp.modified_text)}</div>`;
      }
      if (!has && !isTerminal) {
        html += `<div class="suggestion-actions">
          <button class="btn btn-success btn-sm" onclick="respondSug('${p.proposal_id}','${s.suggestion_id}','Accepted')">Accept</button>
          <button class="btn btn-danger btn-sm" onclick="respondSug('${p.proposal_id}','${s.suggestion_id}','Rejected')">Reject</button>
          <button class="btn btn-outline btn-sm" onclick="showModify('${p.proposal_id}','${s.suggestion_id}')">Modify</button>
        </div>`;
      }
      html += '</div>';
    });
    html += '</div>';
  }

  // Actions
  if (!isTerminal) {
    const allDone = p.suggestions.every(s => responded.has(s.suggestion_id));
    html += `<div style="display:flex;gap:12px;margin-top:8px">
      <button class="btn btn-primary" ${allDone ? '' : 'disabled'} onclick="applyProp('${p.proposal_id}')">
        ${allDone ? 'Apply Upgrade' : 'Respond to all suggestions first'}
      </button>
      <button class="btn btn-outline" onclick="abandonProp('${p.proposal_id}')">Abandon</button>
    </div>`;
  }

  if (p.status === 'Applied' && p.resulting_version_id) {
    html += `<div class="card" style="border-color:var(--green);margin-top:16px">
      <p style="color:var(--green)">Upgrade applied. Version: ${esc(p.resulting_version_id)}</p></div>`;
  }
  container.innerHTML = html;
}

async function respondSug(proposalId, sugId, response, modText, note) {
  try {
    const body = { suggestion_id: sugId, response };
    if (modText) body.modified_text = modText;
    if (note) body.user_note = note;
    await api('/proposals/' + proposalId + '/responses', { method: 'POST', body });
    toast(response + ' recorded');
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (e) { toast(e.message, 'error'); }
}

function showModify(proposalId, sugId) {
  const card = document.getElementById('sug-' + sugId);
  if (card.querySelector('.modify-form')) return;
  const form = document.createElement('div');
  form.className = 'modify-form';
  form.style.marginTop = '8px';
  form.innerHTML = `<div class="form-group"><label>Your modified text</label>
    <textarea id="mod-text-${sugId}" rows="3"></textarea></div>
    <div class="form-group"><label>Note (optional)</label>
    <input type="text" id="mod-note-${sugId}"></div>
    <button class="btn btn-primary btn-sm" onclick="submitModify('${proposalId}','${sugId}')">Submit</button>`;
  card.appendChild(form);
}

async function submitModify(proposalId, sugId) {
  const text = document.getElementById('mod-text-' + sugId).value.trim();
  if (!text) { toast('Text required', 'error'); return; }
  const note = document.getElementById('mod-note-' + sugId).value.trim();
  await respondSug(proposalId, sugId, 'Modified', text, note);
}

async function applyProp(proposalId) {
  try {
    toast('Applying upgrade...');
    const result = await api('/proposals/' + proposalId + '/apply', { method: 'POST', body: {} });
    toast('Upgrade applied! Version: ' + result.version_id);
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (e) { toast(e.message, 'error'); }
}

async function abandonProp(proposalId) {
  const reason = prompt('Reason for abandoning:');
  if (reason === null) return;
  try {
    await api('/proposals/' + proposalId + '/abandon', { method: 'POST', body: { reason: reason || 'No reason' } });
    toast('Proposal abandoned');
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (e) { toast(e.message, 'error'); }
}
