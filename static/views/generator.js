viewInits.generator = function () {
  const el = document.getElementById('view-generator');
  el.innerHTML = `
    <h2 style="margin-bottom:20px">Create New Prompt</h2>
    <div class="card">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="form-group"><label>Title</label><input type="text" id="gen-title" placeholder="e.g. Customer complaint summariser"></div>
        <div class="form-group"><label>Prompt Type</label>
          <select id="gen-type">
            <option>Governance</option><option>Analysis</option><option>Comms</option>
            <option>Classification</option><option selected>Summarisation</option>
            <option>Extraction</option><option>Comparison</option><option>Risk Review</option>
          </select>
        </div>
        <div class="form-group"><label>Deployment Target</label><input type="text" id="gen-deploy" placeholder="e.g. Internal, OpenAI, MS Copilot"></div>
        <div class="form-group"><label>Risk Tier</label>
          <select id="gen-risk">
            <option>Minimal</option><option selected>Limited</option><option>High</option><option>Prohibited</option>
          </select>
        </div>
        <div class="form-group"><label>Input Type</label><input type="text" id="gen-input" value="Plain text"></div>
        <div class="form-group"><label>Output Type</label><input type="text" id="gen-output" value="Plain text"></div>
      </div>
      <div class="form-group"><label>Prompt Text</label>
        <textarea id="gen-text" rows="10" placeholder="Write the full prompt text here..."></textarea>
      </div>
      <div class="form-group"><label>Change Summary (optional)</label>
        <input type="text" id="gen-summary" placeholder="e.g. Initial version">
      </div>
      <div style="display:flex;gap:12px;align-items:center">
        <button class="btn btn-primary" id="gen-submit" onclick="genSubmit()">Create Prompt</button>
        <label style="font-size:13px;display:flex;align-items:center;gap:6px;color:var(--text2)">
          <input type="checkbox" id="gen-auto-compliance" checked> Run compliance check automatically
        </label>
      </div>
    </div>
    <div id="gen-result"></div>`;
};

async function genSubmit() {
  const btn = document.getElementById('gen-submit');
  const resultEl = document.getElementById('gen-result');
  const title = document.getElementById('gen-title').value.trim();
  const text = document.getElementById('gen-text').value.trim();
  if (!title || !text) { toast('Title and prompt text required', 'error'); return; }

  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Creating...';
  resultEl.innerHTML = '';

  try {
    const prompt = await api('/prompts', { method: 'POST', body: {
      title,
      prompt_type: document.getElementById('gen-type').value,
      deployment_target: document.getElementById('gen-deploy').value || 'Internal',
      input_type: document.getElementById('gen-input').value || 'Plain text',
      output_type: document.getElementById('gen-output').value || 'Plain text',
      risk_tier: document.getElementById('gen-risk').value,
      prompt_text: text,
      change_summary: document.getElementById('gen-summary').value || null,
    }});

    let html = `<div class="card" style="border-color:var(--green)">
      <p style="color:var(--green);margin-bottom:8px">Prompt created: <strong>${esc(prompt.title)}</strong></p>
      <p style="font-size:13px;color:var(--text2)">ID: ${prompt.prompt_id} &mdash; v1 created</p>
      <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="navigate('detail',{promptId:'${prompt.prompt_id}'})">View Detail</button>
    </div>`;

    if (document.getElementById('gen-auto-compliance').checked && prompt.versions.length > 0) {
      html += '<div class="loading-state"><div class="spinner"></div> Running compliance check...</div>';
      resultEl.innerHTML = html;

      const versionId = prompt.versions[0].version_id;
      const job = await api('/compliance-checks', { method: 'POST', body: { version_id: versionId } });
      const result = await pollJob(job.job_id);

      if (result.status === 'Complete' && result.result) {
        const r = result.result;
        const gc = gradeClass(r.gold_standard ? r.gold_standard.composite : null);
        const gradeVal = r.gold_standard ? Math.round(r.gold_standard.composite) : '-';
        html = `<div class="card" style="border-color:var(--green)">
          <p style="color:var(--green);margin-bottom:8px">Prompt created: <strong>${esc(prompt.title)}</strong></p>
          <p style="font-size:13px;color:var(--text2)">ID: ${prompt.prompt_id} &mdash; v1 created</p>
          <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="navigate('detail',{promptId:'${prompt.prompt_id}'})">View Detail</button>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">Compliance Result</span>
            <div style="display:flex;align-items:center;gap:12px">
              ${badgeFor(r.overall_result)}
              <span class="grade ${gc}">${gradeVal}</span>
            </div>
          </div>
          <p style="font-size:13px;color:var(--text2);margin-bottom:12px">Blocking defects: ${r.blocking_defects}</p>`;

        if (r.scores && r.scores.length) {
          html += '<table><thead><tr><th>Dimension</th><th>Score</th><th>Rationale</th></tr></thead><tbody>';
          r.scores.forEach(s => {
            html += `<tr><td><strong>${esc(s.code)}</strong></td>
              <td><div class="score-bar score-${s.score}"><span>${s.score}/5</span><div class="score-bar-track"><div class="score-bar-fill"></div></div></div></td>
              <td style="font-size:13px;color:var(--text2)">${esc(s.rationale)}</td></tr>`;
          });
          html += '</tbody></table>';
        }
        html += '</div>';
      }
    }
    resultEl.innerHTML = html;
    toast('Prompt created successfully');
  } catch (e) {
    toast(e.message, 'error');
    resultEl.innerHTML = '<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">' + esc(e.message) + '</p></div>';
  } finally {
    btn.disabled = false; btn.innerHTML = 'Create Prompt';
  }
}
