// Import & Upgrade view — paste prompt, show findings/suggestions, accept/reject, diff, apply
viewInits['import'] = function (params) {
  const el = document.getElementById('view-import');

  if (params && params.proposalId) {
    loadProposal(el, params.proposalId);
    return;
  }

  el.innerHTML = `
    <h2 style="margin-bottom:20px">Import &amp; Upgrade</h2>
    <div class="card">
      <div class="form-group">
        <label for="import-name">Prompt Name (optional)</label>
        <input type="text" id="import-name" placeholder="Leave blank for auto-generated name">
      </div>
      <div class="form-group">
        <label for="import-text">Paste Existing Prompt</label>
        <textarea id="import-text" rows="12" placeholder="Paste your existing prompt text here for analysis..."></textarea>
      </div>
      <button class="btn btn-primary" id="import-analyse-btn" onclick="importAnalyse()">Analyse Prompt</button>
    </div>
    <div id="import-result"></div>`;
};

async function importAnalyse() {
  const text = document.getElementById('import-text').value.trim();
  const name = document.getElementById('import-name').value.trim();
  const btn = document.getElementById('import-analyse-btn');
  const resultEl = document.getElementById('import-result');

  if (!text) { toast('Paste a prompt first', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analysing...';
  resultEl.innerHTML = '<div class="loading-state"><div class="spinner"></div> Submitting for analysis...</div>';

  try {
    const body = { prompt_text: text };
    if (name) body.prompt_name = name;
    const resp = await api('/prompts/analyse', { method: 'POST', body });

    resultEl.innerHTML = '<div class="loading-state"><div class="spinner"></div> AI analysis running... polling for results.</div>';
    const job = await pollJob(resp.job_id);

    if (job.status === 'Complete') {
      toast('Analysis complete');
      await loadProposal(document.getElementById('view-import'), resp.proposal_id);
    } else {
      resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">Analysis failed: ' + escapeHtml(job.error_message || 'Unknown') + '</p></div>';
    }
  } catch (err) {
    toast(err.message, 'error');
    resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Analyse Prompt';
  }
}

async function loadProposal(container, proposalId) {
  container.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading proposal...</div>';

  try {
    const proposal = await api('/proposals/' + proposalId);
    renderProposal(container, proposal);
  } catch (err) {
    container.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
  }
}

function renderProposal(container, proposal) {
  const responded = new Set((proposal.user_responses || []).map(r => r.suggestion_id));
  const responseMap = {};
  (proposal.user_responses || []).forEach(r => { responseMap[r.suggestion_id] = r; });

  const riskClass = proposal.inferred_risk_tier === 'High' || proposal.inferred_risk_tier === 'Prohibited'
    ? 'badge-red' : proposal.inferred_risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';

  const statusClass = proposal.status === 'Applied' ? 'badge-green'
    : proposal.status === 'Abandoned' ? 'badge-red'
    : proposal.status === 'Pending' ? 'badge-blue' : 'badge-amber';

  let html = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">
      <div>
        <h2>Upgrade Proposal</h2>
        <p style="color:var(--text2);margin-top:4px">ID: ${escapeHtml(proposal.proposal_id)}</p>
      </div>
      <span class="badge ${statusClass}">${escapeHtml(proposal.status)}</span>
    </div>`;

  // Classification
  html += `
    <div class="card">
      <div class="card-title" style="margin-bottom:12px">Classification</div>
      <table>
        <tr><td style="color:var(--text2);width:180px">Inferred Purpose</td><td>${escapeHtml(proposal.inferred_purpose || '-')}</td></tr>
        <tr><td style="color:var(--text2)">Prompt Type</td><td>${escapeHtml(proposal.inferred_prompt_type || '-')}</td></tr>
        <tr><td style="color:var(--text2)">Risk Tier</td><td><span class="badge ${riskClass}">${escapeHtml(proposal.inferred_risk_tier || '-')}</span></td></tr>
        <tr><td style="color:var(--text2)">Confidence</td><td>${escapeHtml(proposal.classification_confidence || '-')}</td></tr>
      </table>
    </div>`;

  // Findings
  if (proposal.findings && proposal.findings.length) {
    html += `<div class="card"><div class="card-title" style="margin-bottom:12px">Findings (${proposal.findings.length})</div>`;
    html += '<table><thead><tr><th>Dimension</th><th>Framework</th><th>Score</th><th>Severity</th><th>Finding</th></tr></thead><tbody>';
    proposal.findings.forEach(f => {
      const sevClass = f.severity === 'Blocking' || f.severity === 'Critical' ? 'badge-red' : f.severity === 'High' ? 'badge-amber' : 'badge-blue';
      html += `<tr>
        <td><strong>${escapeHtml(f.dimension_code)}</strong><br><span style="font-size:12px;color:var(--text2)">${escapeHtml(f.dimension_name)}</span></td>
        <td>${escapeHtml(f.framework)}</td>
        <td><div class="score-bar score-${f.current_score}"><span>${f.current_score}/5</span><div class="score-bar-track"><div class="score-bar-fill"></div></div></div></td>
        <td><span class="badge ${sevClass}">${escapeHtml(f.severity)}</span></td>
        <td style="font-size:13px;color:var(--text2)">${escapeHtml(f.current_finding)}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  }

  // Suggestions
  if (proposal.suggestions && proposal.suggestions.length) {
    html += `<div class="card"><div class="card-title" style="margin-bottom:12px">Suggestions (${proposal.suggestions.length})</div>`;
    const isTerminal = proposal.status === 'Applied' || proposal.status === 'Abandoned';

    proposal.suggestions.forEach(s => {
      const resp = responseMap[s.suggestion_id];
      const hasResponse = !!resp;
      const respBadge = hasResponse
        ? (resp.response === 'Accepted' ? '<span class="badge badge-green">Accepted</span>'
          : resp.response === 'Rejected' ? '<span class="badge badge-red">Rejected</span>'
          : '<span class="badge badge-amber">Modified</span>')
        : '<span class="badge badge-blue">Pending</span>';

      const improvement = s.expected_score_improvement || {};

      html += `
        <div class="suggestion-card" id="suggestion-${s.suggestion_id}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div>
              <strong>${escapeHtml(s.dimension_code)}</strong> — ${escapeHtml(s.description)}
              ${respBadge}
            </div>
            <span style="font-size:12px;color:var(--text2)">${improvement.from || '?'} &rarr; ${improvement.to || '?'}</span>
          </div>
          <div style="font-size:13px;color:var(--text2);margin-bottom:8px">${escapeHtml(s.rationale)}</div>
          <div style="font-size:12px;color:var(--text2);margin-bottom:8px">Insertion: ${escapeHtml(s.insertion_hint || '')}</div>
          <div class="diff-add">${escapeHtml(s.suggested_text)}</div>`;

      if (hasResponse && resp.response === 'Modified' && resp.modified_text) {
        html += `<div style="margin-top:4px"><span style="font-size:12px;color:var(--text2)">Modified to:</span></div>
          <div class="diff-add" style="border-color:var(--amber)">${escapeHtml(resp.modified_text)}</div>`;
      }
      if (hasResponse && resp.user_note) {
        html += `<div style="margin-top:4px;font-size:12px;color:var(--text2)">Note: ${escapeHtml(resp.user_note)}</div>`;
      }

      if (!hasResponse && !isTerminal) {
        html += `
          <div class="suggestion-actions">
            <button class="btn btn-success btn-sm" onclick="respondSuggestion('${proposal.proposal_id}','${s.suggestion_id}','Accepted')">Accept</button>
            <button class="btn btn-danger btn-sm" onclick="respondSuggestion('${proposal.proposal_id}','${s.suggestion_id}','Rejected')">Reject</button>
            <button class="btn btn-outline btn-sm" onclick="showModifyForm('${proposal.proposal_id}','${s.suggestion_id}',this)">Modify</button>
          </div>`;
      }

      html += '</div>';
    });
    html += '</div>';
  }

  // Action buttons
  if (proposal.status !== 'Applied' && proposal.status !== 'Abandoned') {
    const allResponded = proposal.suggestions.every(s => responded.has(s.suggestion_id));
    html += `
      <div style="display:flex;gap:12px;margin-top:8px">
        <button class="btn btn-primary" ${allResponded ? '' : 'disabled'} onclick="applyProposal('${proposal.proposal_id}')">
          ${allResponded ? 'Apply Upgrade' : 'Respond to all suggestions first'}
        </button>
        <button class="btn btn-outline" onclick="abandonProposal('${proposal.proposal_id}')">Abandon</button>
      </div>`;
  }

  // Applied result
  if (proposal.status === 'Applied' && proposal.resulting_version_id) {
    html += `
      <div class="card" style="border-color:var(--green);margin-top:16px">
        <p style="color:var(--green)">Upgrade applied. New version ID: ${proposal.resulting_version_id}</p>
        ${proposal.prompt_id ? '<button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="navigate(\'detail\',{promptId:' + proposal.prompt_id + '})">View Prompt</button>' : ''}
      </div>`;
  }

  container.innerHTML = html;
}

async function respondSuggestion(proposalId, suggestionId, response, modifiedText, userNote) {
  try {
    const body = { suggestion_id: suggestionId, response };
    if (modifiedText) body.modified_text = modifiedText;
    if (userNote) body.user_note = userNote;
    await api('/proposals/' + proposalId + '/responses', { method: 'POST', body });
    toast(response + ' recorded');
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (err) {
    toast(err.message, 'error');
  }
}

function showModifyForm(proposalId, suggestionId, btn) {
  const card = document.getElementById('suggestion-' + suggestionId);
  const existing = card.querySelector('.modify-form');
  if (existing) { existing.remove(); return; }

  const form = document.createElement('div');
  form.className = 'modify-form';
  form.style.marginTop = '8px';
  form.innerHTML = `
    <div class="form-group">
      <label>Your modified text</label>
      <textarea id="modify-text-${suggestionId}" rows="3" placeholder="Enter your version of the suggested text..."></textarea>
    </div>
    <div class="form-group">
      <label>Note (optional)</label>
      <input type="text" id="modify-note-${suggestionId}" placeholder="Why you modified it">
    </div>
    <button class="btn btn-primary btn-sm" onclick="submitModify('${proposalId}','${suggestionId}')">Submit Modified</button>`;
  card.appendChild(form);
}

async function submitModify(proposalId, suggestionId) {
  const text = document.getElementById('modify-text-' + suggestionId).value.trim();
  const note = document.getElementById('modify-note-' + suggestionId).value.trim();
  if (!text) { toast('Modified text is required', 'error'); return; }
  await respondSuggestion(proposalId, suggestionId, 'Modified', text, note);
}

async function applyProposal(proposalId) {
  try {
    toast('Applying upgrade...');
    const result = await api('/proposals/' + proposalId + '/apply', { method: 'POST' });
    toast('Upgrade applied! Version ' + result.version_id + ' created');
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function abandonProposal(proposalId) {
  const reason = prompt('Reason for abandoning:');
  if (reason === null) return;
  try {
    await api('/proposals/' + proposalId + '/abandon', {
      method: 'POST',
      body: { reason: reason || 'No reason given' },
    });
    toast('Proposal abandoned');
    await loadProposal(document.getElementById('view-import'), proposalId);
  } catch (err) {
    toast(err.message, 'error');
  }
}
