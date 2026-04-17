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
        <div class="form-group"><label>Deployment Target</label>
          <select id="gen-deploy">
            <option selected>Claude</option>
            <option>MS Copilot Agent - Declarative</option>
            <option>MS Copilot Agent - Custom Engine</option>
            <option>OpenAI</option>
            <option>Multi-model</option>
            <option>Other</option>
          </select>
        </div>
        <div class="form-group"><label>Risk Tier</label>
          <select id="gen-risk">
            <option>Minimal</option><option selected>Limited</option><option>High</option><option>Prohibited</option>
          </select>
        </div>
        <div class="form-group"><label>Input Type</label>
          <select id="gen-input">
            <option>Form responses</option>
            <option>Document or report</option>
            <option>Data table</option>
            <option>Email thread</option>
            <option selected>Free text</option>
            <option>JSON or structured data</option>
            <option>Meeting notes</option>
            <option>Other</option>
          </select>
        </div>
        <div class="form-group"><label>Output Type</label>
          <select id="gen-output">
            <option>Structured assessment</option>
            <option selected>Executive narrative</option>
            <option>Briefing note</option>
            <option>Recommendation</option>
            <option>Flag report</option>
            <option>Draft comms</option>
            <option>Comparison table</option>
            <option>Data extraction</option>
            <option>Other</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <label style="margin-bottom:0">Prompt Text</label>
          <button class="btn btn-outline btn-sm" id="gen-ai-btn" onclick="genAI()" title="Generate prompt text using Claude AI based on the title, type, and fields above">Generate with AI</button>
        </div>
        <textarea id="gen-text" rows="10" placeholder="Write the full prompt text here, or click Generate with AI to create one from the fields above..."></textarea>
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
    const createBody = {
      title,
      prompt_type: document.getElementById('gen-type').value,
      deployment_target: document.getElementById('gen-deploy').value || 'Claude',
      input_type: document.getElementById('gen-input').value || 'Free text',
      output_type: document.getElementById('gen-output').value || 'Executive narrative',
      risk_tier: document.getElementById('gen-risk').value,
      prompt_text: text,
      change_summary: document.getElementById('gen-summary').value || null,
    };
    console.log('Creating prompt:', JSON.stringify(createBody));
    const prompt = await api('/prompts', { method: 'POST', body: createBody });
    console.log('Prompt created successfully:', prompt.prompt_id, prompt.title);

    let html = `<div class="card" style="border-color:var(--green)">
      <p style="color:var(--green);margin-bottom:8px">Prompt saved successfully: <strong>${esc(prompt.title)}</strong></p>
      <p style="font-size:13px;color:var(--text2)">ID: ${prompt.prompt_id} &mdash; v1 created</p>
      <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="navigate('detail',{promptId:'${prompt.prompt_id}'})">View Detail</button>
      <button class="btn btn-outline btn-sm" style="margin-top:8px;margin-left:8px" onclick="navigate('dashboard')">Back to Dashboard</button>
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
          <p style="color:var(--green);margin-bottom:8px">Prompt saved successfully: <strong>${esc(prompt.title)}</strong></p>
          <p style="font-size:13px;color:var(--text2)">ID: ${prompt.prompt_id} &mdash; v1 created</p>
          <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="navigate('detail',{promptId:'${prompt.prompt_id}'})">View Detail</button>
      <button class="btn btn-outline btn-sm" style="margin-top:8px;margin-left:8px" onclick="navigate('dashboard')">Back to Dashboard</button>
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

async function genAI() {
  const title = document.getElementById('gen-title').value.trim();
  if (!title) { toast('Enter a title first so the AI knows what to generate', 'error'); return; }
  const btn = document.getElementById('gen-ai-btn');
  const textarea = document.getElementById('gen-text');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...';
  try {
    const body = {
      title,
      prompt_type: document.getElementById('gen-type').value,
      deployment_target: document.getElementById('gen-deploy').value || '',
      input_type: document.getElementById('gen-input').value || '',
      output_type: document.getElementById('gen-output').value || '',
      brief_text: textarea.value.trim(),
    };
    // If Brief Builder passed selected guardrails, include them
    if (window._briefSelectedGuardrails && window._briefSelectedGuardrails.length) {
      body.selected_guardrails = window._briefSelectedGuardrails;
      window._briefSelectedGuardrails = null; // consume once
    }
    const resp = await api('/prompts/generate', { method: 'POST', body });
    textarea.value = resp.prompt_text;
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
    toast('Prompt generated — review and edit before saving');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = 'Generate with AI';
  }
}
