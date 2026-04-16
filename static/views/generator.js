// Generator view — guided form to create new prompt, show compliance result
viewInits.generator = function () {
  const el = document.getElementById('view-generator');
  el.innerHTML = `
    <h2 style="margin-bottom:20px">Create New Prompt</h2>
    <div class="card">
      <div class="form-group">
        <label for="gen-name">Prompt Name</label>
        <input type="text" id="gen-name" placeholder="e.g. customer-service-v1">
      </div>
      <div class="form-group">
        <label for="gen-desc">Description</label>
        <input type="text" id="gen-desc" placeholder="What this prompt does">
      </div>
      <div class="form-group">
        <label for="gen-tags">Tags (comma-separated)</label>
        <input type="text" id="gen-tags" placeholder="e.g. support, customer, chatbot">
      </div>
      <div class="form-group">
        <label for="gen-content">Prompt Content</label>
        <textarea id="gen-content" rows="10" placeholder="Enter your prompt text here..."></textarea>
      </div>
      <div style="display:flex;gap:12px;align-items:center">
        <button class="btn btn-primary" id="gen-create-btn" onclick="generatorCreate()">Create Prompt</button>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;margin:0">
          <input type="checkbox" id="gen-auto-compliance" checked> Run compliance check automatically
        </label>
      </div>
    </div>
    <div id="gen-result"></div>`;
};

async function generatorCreate() {
  const name = document.getElementById('gen-name').value.trim();
  const desc = document.getElementById('gen-desc').value.trim();
  const tags = document.getElementById('gen-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const content = document.getElementById('gen-content').value.trim();
  const autoCompliance = document.getElementById('gen-auto-compliance').checked;
  const resultEl = document.getElementById('gen-result');
  const btn = document.getElementById('gen-create-btn');

  if (!name) { toast('Name is required', 'error'); return; }
  if (!content) { toast('Prompt content is required', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Creating...';
  resultEl.innerHTML = '';

  try {
    const prompt = await api('/prompts', {
      method: 'POST',
      body: { name, description: desc, tags, content },
    });

    toast('Prompt created');
    const versionId = prompt.latest_version.id;

    let html = `
      <div class="card" style="border-color:var(--green)">
        <div class="card-header">
          <span class="card-title" style="color:var(--green)">Prompt Created</span>
          <button class="btn btn-outline btn-sm" onclick="navigate('detail', {promptId: ${prompt.id}})">View Detail</button>
        </div>
        <table>
          <tr><td style="color:var(--text2);width:120px">Name</td><td><strong>${escapeHtml(prompt.name)}</strong></td></tr>
          <tr><td style="color:var(--text2)">Version</td><td>v${prompt.latest_version.version}</td></tr>
          <tr><td style="color:var(--text2)">Tags</td><td>${(prompt.tags || []).map(t => '<span class="badge badge-purple">' + escapeHtml(t) + '</span>').join(' ') || '-'}</td></tr>
        </table>
      </div>`;

    if (autoCompliance) {
      html += '<div id="gen-compliance"><div class="loading-state"><div class="spinner"></div> Running compliance check...</div></div>';
      resultEl.innerHTML = html;

      try {
        const job = await api('/compliance-checks', {
          method: 'POST',
          body: { version_id: versionId },
        });

        const completed = await pollJob(job.job_id);
        const compEl = document.getElementById('gen-compliance');

        if (completed.status === 'Complete' && completed.result) {
          compEl.innerHTML = buildComplianceCard(completed.result);
          toast('Compliance check complete');
        } else {
          compEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">Compliance check failed: ' + escapeHtml(completed.error_message || 'Unknown') + '</p></div>';
        }
      } catch (compErr) {
        document.getElementById('gen-compliance').innerHTML = '<div class="card"><p style="color:var(--amber)">Compliance check error: ' + escapeHtml(compErr.message) + '</p></div>';
      }
    } else {
      resultEl.innerHTML = html;
    }

  } catch (err) {
    toast(err.message, 'error');
    resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Create Prompt';
  }
}

function buildComplianceCard(result) {
  const gc = gradeClass(result.gold_score);
  const blockedHtml = result.blocked
    ? '<span class="badge badge-red">Blocked</span>'
    : '<span class="badge badge-green">Passed</span>';

  let html = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Compliance Result</span>
        <div style="display:flex;align-items:center;gap:12px">
          ${blockedHtml}
          <span class="grade ${gc}" style="width:42px;height:42px;font-size:13px">${Math.round(result.gold_score)}</span>
        </div>
      </div>`;

  // Group scores by framework
  const byFramework = {};
  (result.scores || []).forEach(s => {
    if (!byFramework[s.framework]) byFramework[s.framework] = [];
    byFramework[s.framework].push(s);
  });

  for (const [fw, scores] of Object.entries(byFramework).sort()) {
    const avg = scores.reduce((sum, s) => sum + s.score, 0) / scores.length;
    html += `<div style="margin-top:12px"><strong>${escapeHtml(fw)}</strong> <span style="color:var(--text2);font-size:12px">avg ${avg.toFixed(1)}/5</span></div>`;
    scores.forEach(s => {
      html += `
        <div style="display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid var(--border)">
          <span style="width:120px;font-size:13px;font-weight:500">${escapeHtml(s.code)}</span>
          <span style="width:160px;font-size:12px;color:var(--text2)">${escapeHtml(s.name)}</span>
          <div class="score-bar score-${s.score}" style="flex:1">
            <span style="width:30px;font-size:13px">${s.score}/5</span>
            <div class="score-bar-track"><div class="score-bar-fill"></div></div>
          </div>
          <span style="flex:2;font-size:12px;color:var(--text2)">${escapeHtml(s.rationale || '')}</span>
        </div>`;
    });
  }

  // Anomaly
  if (result.anomaly) {
    const anomalyClass = result.anomaly.result === 'clean' ? 'badge-green' : result.anomaly.result === 'suspicious' ? 'badge-amber' : 'badge-red';
    html += `<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border)">
      <span style="font-size:12px;color:var(--text2)">Anomaly Detection:</span>
      <span class="badge ${anomalyClass}">${escapeHtml(result.anomaly.result)}</span>
      <span style="font-size:12px;color:var(--text2);margin-left:8px">${escapeHtml(result.anomaly.reason || '')}</span>
    </div>`;
  }

  html += '</div>';
  return html;
}
