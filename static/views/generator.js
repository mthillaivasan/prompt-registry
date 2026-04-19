let _genAICompleted = false;
let _cameFromBrief = false;

viewInits.generator = function () {
  _genAICompleted = false;
  _cameFromBrief = false;
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
        <label style="margin-bottom:8px">Prompt Text</label>
        <div id="gen-ai-section" style="margin-bottom:12px">
          <button class="btn btn-gold" id="gen-ai-btn" onclick="genAI()" style="padding:14px 0;font-size:16px;width:100%;justify-content:center">Generate with AI</button>
          <p id="gen-ai-hint" style="margin-top:8px;font-size:13px;color:var(--text2);text-align:center"></p>
        </div>
        <textarea id="gen-text" rows="10" placeholder="Click Generate with AI above, or write the prompt text manually..." oninput="window._genOnTextInput()"></textarea>
        <div id="gen-cost-line" style="margin-top:6px;font-size:12px;color:var(--text2);min-height:18px"></div>
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
      <p id="gen-save-hint" style="display:none;color:var(--amber);font-size:13px;margin-top:8px">Click Generate with AI first to create proper prompt text from your brief.</p>
    </div>
    <div id="gen-result"></div>`;

  // Check if Brief Builder pre-filled — defer to allow _briefSend to run
  setTimeout(() => {
    if (window._briefPrefilled) {
      _cameFromBrief = true;
      _genAICompleted = false;
      window._briefPrefilled = false;
      updateSaveState();
      // Show prominent brief loaded message
      const hint = document.getElementById('gen-ai-hint');
      if (hint) {
        hint.innerHTML = '<strong style="color:var(--accent)">Brief loaded.</strong> Click Generate with AI to create your prompt.';
      }
    }
  }, 200);
};

function updateSaveState() {
  const btn = document.getElementById('gen-submit');
  const hint = document.getElementById('gen-save-hint');
  if (!btn) return;
  if (_cameFromBrief && !_genAICompleted) {
    btn.style.opacity = '0.4';
    btn.style.cursor = 'not-allowed';
    btn.style.pointerEvents = 'none';
    if (hint) hint.style.display = 'block';
  } else {
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
    btn.style.pointerEvents = 'auto';
    if (hint) hint.style.display = 'none';
  }
}

async function genSubmit() {
  if (_cameFromBrief && !_genAICompleted) {
    toast('Click Generate with AI first to create proper prompt text', 'error');
    return;
  }
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
  const hint = document.getElementById('gen-ai-hint');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...';
  if (hint) hint.textContent = 'Calling Claude API — this takes 10-30 seconds...';
  try {
    const body = {
      title,
      prompt_type: document.getElementById('gen-type').value,
      deployment_target: document.getElementById('gen-deploy').value || '',
      input_type: document.getElementById('gen-input').value || '',
      output_type: document.getElementById('gen-output').value || '',
      brief_text: window._briefTextForGenerate || textarea.value.trim(),
    };
    window._briefTextForGenerate = null; // consume once
    if (window._briefSelectedGuardrails && window._briefSelectedGuardrails.length) {
      body.selected_guardrails = window._briefSelectedGuardrails;
      window._briefSelectedGuardrails = null;
    }
    if (window._briefConstraints && window._briefConstraints.length) {
      body.constraints = window._briefConstraints;
      window._briefConstraints = null;
    }
    const resp = await api('/prompts/generate', { method: 'POST', body });
    textarea.value = resp.prompt_text;
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
    textarea.style.borderLeft = '3px solid var(--teal)';
    _genAICompleted = true;
    updateSaveState();
    window._genRefreshCost();
    if (hint) hint.textContent = 'Generated — review the text below and edit if needed, then click Create Prompt.';
    hint.style.color = 'var(--green)';
    toast('Prompt generated — review and edit before saving');
  } catch (e) {
    toast(e.message, 'error');
    if (hint) { hint.textContent = 'Generation failed: ' + e.message; hint.style.color = 'var(--red)'; }
  } finally {
    btn.disabled = false; btn.textContent = 'Generate with AI';
  }
}

// ── Token count + cost display (Drop 1) ──────────────────────────────────────
// Post-Generate render, and debounced live update on every textarea edit.
// Displays "~4,287 tokens · ~$0.02 per invocation (input only, estimated)"
// under the textarea, with an inline "recalculating…" state during the fetch.

let _genCostDebounce = null;
let _genCostSeq = 0;

function _formatCostLine(tokens, cost, outputEstimate) {
  const tokenStr = tokens.toLocaleString();
  const costStr = cost < 0.01 ? '<$0.01' : '~$' + cost.toFixed(2);
  return '~' + tokenStr + ' tokens · ' + costStr +
    ' per invocation (input only, ~' + outputEstimate + '-token output estimated)';
}

window._genRefreshCost = async function () {
  const textarea = document.getElementById('gen-text');
  const line = document.getElementById('gen-cost-line');
  if (!textarea || !line) return;
  const text = textarea.value || '';
  if (!text.trim()) { line.textContent = ''; return; }
  const seq = ++_genCostSeq;
  line.innerHTML = '<span class="spinner" style="width:10px;height:10px;vertical-align:middle"></span> recalculating…';
  try {
    const resp = await api('/prompts/count-tokens', { method: 'POST', body: { text } });
    if (seq !== _genCostSeq) return; // a newer call superseded this one
    line.textContent = _formatCostLine(resp.token_count, resp.estimated_cost_usd, resp.output_tokens_estimate);
  } catch (e) {
    if (seq !== _genCostSeq) return;
    line.textContent = 'Could not compute cost: ' + ((e && e.message) || 'unknown error');
  }
};

window._genOnTextInput = function () {
  if (_genCostDebounce) clearTimeout(_genCostDebounce);
  _genCostDebounce = setTimeout(window._genRefreshCost, 500);
};
