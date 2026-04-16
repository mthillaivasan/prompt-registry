// Brief Builder — 6-step guided form + review, purely frontend state
(function () {
  const TOTAL_STEPS = 6;
  let step = 1;
  const state = { purpose: '', inputType: '', outputType: '', audience: '', constraints: [], selectedGuardrails: [] };
  let guardrailData = null; // cached response from /scoring-dimensions/applicable

  const INPUT_OPTIONS = ['Form responses', 'Document or report', 'Data table', 'Email thread', 'Free text', 'Structured data', 'Meeting notes', 'Other'];
  const OUTPUT_OPTIONS = ['Structured assessment', 'Executive summary', 'Briefing note', 'Recommendation', 'Flag report', 'Draft email or communication', 'Data extraction', 'Comparison table', 'Other'];
  const AUDIENCE_OPTIONS = ['Senior committee', 'Operations team', 'Executive', 'Compliance team', 'External counterparty', 'Project sponsor', 'Broad internal audience'];
  const CONSTRAINT_OPTIONS = [
    'Must not admit liability',
    'Must flag uncertainty rather than guess',
    'Must not reproduce source text verbatim',
    'Must require human review before action is taken',
    'Involves personal or sensitive data',
    'Connects to a critical operational process',
    'Third-party AI platform (not internal)',
  ];

  viewInits.brief = function () {
    step = 1;
    state.purpose = ''; state.inputType = ''; state.outputType = ''; state.audience = '';
    state.constraints = []; state.selectedGuardrails = [];
    guardrailData = null;
    renderStep();
  };

  function renderStep() {
    const el = document.getElementById('view-brief');
    const progress = `<div style="display:flex;gap:4px;margin-bottom:24px">${
      Array.from({length: TOTAL_STEPS}, (_, i) => i + 1).map(i =>
        `<div style="flex:1;height:4px;border-radius:2px;background:${i <= step ? 'var(--accent)' : 'var(--surface2)'}"></div>`
      ).join('')}</div>`;

    let html = '<h2 style="margin-bottom:8px">Brief Builder</h2><p style="color:var(--text2);margin-bottom:20px;font-size:14px">Step ' + step + ' of ' + TOTAL_STEPS + '</p>' + progress + '<div class="card">';

    if (step === 1) {
      html += `<h3 style="margin-bottom:12px">What does this prompt need to do?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Describe in one or two sentences what you want the AI to do.</p>
        <div class="form-group">
          <textarea id="brief-purpose" rows="4" placeholder="e.g. Summarise incoming customer complaints and flag any that mention regulatory obligations or potential liability.">${esc(state.purpose)}</textarea>
        </div>`;
    } else if (step === 2) {
      html += `<h3 style="margin-bottom:12px">What goes in?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">What will the AI receive as input?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      INPUT_OPTIONS.forEach(opt => {
        const sel = state.inputType === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('inputType','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
    } else if (step === 3) {
      html += `<h3 style="margin-bottom:12px">What comes out?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">What should the AI produce?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      OUTPUT_OPTIONS.forEach(opt => {
        const sel = state.outputType === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('outputType','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
    } else if (step === 4) {
      html += `<h3 style="margin-bottom:12px">Who receives the output?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Who will read or use the AI output?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      AUDIENCE_OPTIONS.forEach(opt => {
        const sel = state.audience === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('audience','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
    } else if (step === 5) {
      html += `<h3 style="margin-bottom:12px">Any constraints?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Select all that apply.</p>
        <div style="display:flex;flex-direction:column;gap:10px">`;
      CONSTRAINT_OPTIONS.forEach(opt => {
        const checked = state.constraints.includes(opt) ? 'checked' : '';
        html += `<label style="display:flex;align-items:center;gap:8px;font-size:14px;color:var(--text);cursor:pointer">
          <input type="checkbox" ${checked} onchange="window._briefToggle('${esc(opt)}',this.checked)"> ${esc(opt)}
        </label>`;
      });
      html += '</div>';
    } else if (step === 6) {
      html += renderStep6();
    }

    html += '</div>';

    // Navigation
    html += '<div style="display:flex;justify-content:space-between;margin-top:16px">';
    if (step > 1) {
      html += '<button class="btn btn-outline" onclick="window._briefPrev()">Back</button>';
    } else {
      html += '<div></div>';
    }
    if (step < TOTAL_STEPS) {
      html += '<button class="btn btn-primary" onclick="window._briefNext()">Next</button>';
    } else {
      html += '<button class="btn btn-primary" onclick="window._briefReview()">Review Brief</button>';
    }
    html += '</div>';

    el.innerHTML = html;
  }

  function renderStep6() {
    if (!guardrailData) {
      return `<h3 style="margin-bottom:12px">Guardrail Configuration</h3>
        <div class="loading-state"><div class="spinner"></div> Loading applicable guardrails...</div>`;
    }

    const { tier1, tier2, tier3 } = guardrailData;
    let html = '<h3 style="margin-bottom:16px">Guardrail Configuration</h3>';

    // Section A — Always applied
    html += '<div style="margin-bottom:20px"><div style="font-weight:600;font-size:14px;color:var(--green);margin-bottom:8px">Always Applied</div>';
    html += '<p style="font-size:13px;color:var(--text2);margin-bottom:10px">These guardrails are included in every prompt. They cannot be removed.</p>';
    tier1.forEach(d => {
      html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:16px;opacity:.5">&#128274;</span>
        <div style="flex:1"><strong style="font-size:13px">${esc(d.code)}</strong> <span style="font-size:13px;color:var(--text2)">${esc(d.name)}</span>
        <div style="font-size:12px;color:var(--text2);margin-top:2px">${esc(d.description)}</div></div>
      </div>`;
    });
    html += '</div>';

    // Section B — Conditionally applied
    const triggered = tier2.filter(d => d.triggered);
    const notTriggered = tier2.filter(d => !d.triggered);
    if (triggered.length) {
      html += '<div style="margin-bottom:20px"><div style="font-weight:600;font-size:14px;color:var(--amber);margin-bottom:8px">Applied Based on Your Answers</div>';
      html += '<p style="font-size:13px;color:var(--text2);margin-bottom:10px">These were auto-selected because of your brief. They cannot be removed while the condition is met.</p>';
      triggered.forEach(d => {
        html += `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
          <span style="font-size:16px;opacity:.5">&#128274;</span>
          <div style="flex:1"><strong style="font-size:13px">${esc(d.code)}</strong> <span style="font-size:13px;color:var(--text2)">${esc(d.name)}</span>
          <div style="font-size:12px;color:var(--amber);margin-top:2px">Triggered: ${esc(d.trigger_reason)}</div>
          <div style="font-size:12px;color:var(--text2);margin-top:2px">${esc(d.description)}</div></div>
        </div>`;
      });
      html += '</div>';
    }
    if (notTriggered.length) {
      html += '<div style="margin-bottom:20px"><div style="font-weight:600;font-size:14px;color:var(--text2);margin-bottom:8px">Not Triggered (Conditional)</div>';
      html += '<p style="font-size:13px;color:var(--text2);margin-bottom:10px">These are available but were not triggered by your answers.</p>';
      notTriggered.forEach(d => {
        html += `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)">
          <span style="font-size:13px;color:var(--text2);opacity:.5">${esc(d.code)}</span>
          <span style="font-size:13px;color:var(--text2)">${esc(d.name)} — ${esc(d.trigger_reason)}</span>
        </div>`;
      });
      html += '</div>';
    }

    // Section C — Optional
    html += '<div style="margin-bottom:20px"><div style="font-weight:600;font-size:14px;color:var(--accent);margin-bottom:8px">Optional Guardrails</div>';
    html += '<p style="font-size:13px;color:var(--text2);margin-bottom:10px">All checked by default. Unchecking reduces your gold standard score.</p>';
    tier3.forEach(d => {
      const checked = state.selectedGuardrails.includes(d.code) ? 'checked' : '';
      html += `<label style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer">
        <input type="checkbox" ${checked} onchange="window._briefGuardrail('${esc(d.code)}',this.checked)" style="margin-top:2px;width:auto">
        <div style="flex:1"><strong style="font-size:13px">${esc(d.code)}</strong> <span style="font-size:13px;color:var(--text2)">${esc(d.name)}</span>
        <div style="font-size:12px;color:var(--text2);margin-top:2px">${esc(d.description)}</div>
        <div style="font-size:12px;color:var(--amber);margin-top:2px">Removing reduces gold standard by ~${d.score_impact_if_removed} points</div></div>
      </label>`;
    });
    html += '</div>';

    // Gold standard preview
    html += '<div style="padding:16px;background:var(--surface2);border-radius:8px;display:flex;justify-content:space-between;align-items:center">';
    html += '<span style="font-size:14px;font-weight:600">Estimated Gold Standard Impact</span>';
    const totalOptional = tier3.length;
    const selectedOptional = tier3.filter(d => state.selectedGuardrails.includes(d.code)).length;
    const removedImpact = tier3.filter(d => !state.selectedGuardrails.includes(d.code)).reduce((sum, d) => sum + (d.score_impact_if_removed || 0), 0);
    const estimatedMax = 100;
    const estimated = Math.max(0, Math.round(estimatedMax - removedImpact));
    const gc = estimated >= 70 ? 'grade-high' : estimated >= 40 ? 'grade-mid' : 'grade-low';
    html += `<div style="text-align:center"><span class="grade ${gc}" style="width:56px;height:56px;font-size:16px">${estimated}</span>`;
    html += `<div style="font-size:11px;color:var(--text2);margin-top:4px">${selectedOptional}/${totalOptional} optional selected</div></div>`;
    html += '</div>';

    return html;
  }

  async function loadGuardrails() {
    try {
      const deployTarget = inferDeployTarget();
      const riskTier = inferRiskTier();
      const params = new URLSearchParams({
        input_type: state.inputType || '',
        deployment_target: deployTarget,
        risk_tier: riskTier,
        prompt_text_snippet: state.purpose || '',
      });
      guardrailData = await api('/scoring-dimensions/applicable?' + params.toString());

      // Initialize selectedGuardrails: all tier1 + triggered tier2 + all tier3
      state.selectedGuardrails = [];
      guardrailData.tier1.forEach(d => state.selectedGuardrails.push(d.code));
      guardrailData.tier2.filter(d => d.triggered).forEach(d => state.selectedGuardrails.push(d.code));
      guardrailData.tier3.forEach(d => state.selectedGuardrails.push(d.code));

      renderStep();
    } catch (e) {
      const el = document.getElementById('view-brief');
      if (el) el.querySelector('.card').innerHTML = '<p style="color:var(--red)">' + esc(e.message) + '</p>';
    }
  }

  function inferDeployTarget() {
    if (state.constraints.includes('Third-party AI platform (not internal)')) return 'External';
    return 'Internal';
  }

  function inferRiskTier() {
    if (state.constraints.includes('Connects to a critical operational process')) return 'High';
    if (state.constraints.includes('Involves personal or sensitive data')) return 'Limited';
    return 'Minimal';
  }

  function buildBriefText() {
    let lines = [];
    lines.push('PURPOSE: ' + (state.purpose || '(not specified)'));
    lines.push('INPUT TYPE: ' + (state.inputType || '(not specified)'));
    lines.push('OUTPUT TYPE: ' + (state.outputType || '(not specified)'));
    lines.push('AUDIENCE: ' + (state.audience || '(not specified)'));
    if (state.constraints.length) {
      lines.push('CONSTRAINTS:');
      state.constraints.forEach(c => lines.push('  - ' + c));
    }
    if (state.selectedGuardrails.length) {
      lines.push('SELECTED GUARDRAILS: ' + state.selectedGuardrails.join(', '));
    }
    return lines.join('\n');
  }

  function renderReview() {
    const el = document.getElementById('view-brief');
    const brief = buildBriefText();
    let html = `<h2 style="margin-bottom:20px">Review Brief</h2>
      <div class="card">
        <table>
          <tr><td style="color:var(--text2);width:140px;vertical-align:top">Purpose</td><td>${esc(state.purpose || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Input type</td><td>${esc(state.inputType || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Output type</td><td>${esc(state.outputType || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Audience</td><td>${esc(state.audience || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Constraints</td><td>${state.constraints.length ? state.constraints.map(c => esc(c)).join('<br>') : '(none selected)'}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Guardrails</td><td>${state.selectedGuardrails.length} dimensions selected (${state.selectedGuardrails.join(', ')})</td></tr>
        </table>
      </div>
      <div class="card">
        <div class="card-title" style="margin-bottom:8px">Structured Brief</div>
        <div class="prompt-text" id="brief-output">${esc(brief)}</div>
      </div>
      <div style="display:flex;gap:12px;margin-top:16px">
        <button class="btn btn-outline" onclick="window._briefBack()">Back to editing</button>
        <button class="btn btn-outline" onclick="window._briefCopy()">Copy brief</button>
        <button class="btn btn-primary" onclick="window._briefSend()">Send to Generator</button>
      </div>`;
    el.innerHTML = html;
  }

  // Exposed handlers
  window._briefSelect = function (field, val) { state[field] = val; renderStep(); };
  window._briefToggle = function (opt, checked) {
    if (checked && !state.constraints.includes(opt)) state.constraints.push(opt);
    if (!checked) state.constraints = state.constraints.filter(c => c !== opt);
  };
  window._briefGuardrail = function (code, checked) {
    if (checked && !state.selectedGuardrails.includes(code)) state.selectedGuardrails.push(code);
    if (!checked) state.selectedGuardrails = state.selectedGuardrails.filter(c => c !== code);
    renderStep();
  };
  window._briefPrev = function () { saveStepState(); step--; guardrailData = step < 6 ? null : guardrailData; renderStep(); };
  window._briefNext = function () {
    saveStepState();
    step++;
    if (step === 6 && !guardrailData) { renderStep(); loadGuardrails(); }
    else renderStep();
  };
  window._briefReview = function () { saveStepState(); renderReview(); };
  window._briefBack = function () { step = 1; guardrailData = null; renderStep(); };

  window._briefCopy = function () {
    const text = buildBriefText();
    navigator.clipboard.writeText(text).then(() => toast('Brief copied to clipboard')).catch(() => {
      const el = document.getElementById('brief-output');
      if (el) { const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }
      toast('Select and copy manually', 'error');
    });
  };

  window._briefSend = function () {
    const guardrails = [...state.selectedGuardrails];
    navigate('generator');
    setTimeout(() => {
      const title = document.getElementById('gen-title');
      const type = document.getElementById('gen-type');
      const input = document.getElementById('gen-input');
      const output = document.getElementById('gen-output');
      const textarea = document.getElementById('gen-text');

      if (title && !title.value) title.value = state.purpose.substring(0, 80);

      const typeMap = {
        'Structured assessment': 'Analysis',
        'Executive summary': 'Summarisation',
        'Briefing note': 'Comms',
        'Recommendation': 'Governance',
        'Flag report': 'Risk Review',
        'Draft email or communication': 'Comms',
        'Data extraction': 'Extraction',
        'Comparison table': 'Comparison',
      };
      if (type && state.outputType && typeMap[state.outputType]) type.value = typeMap[state.outputType];
      if (input) input.value = state.inputType || input.value;
      if (output) output.value = state.outputType || output.value;

      if (textarea) {
        textarea.value = buildBriefText();
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
      }

      // Store selected guardrails for the generator to use
      window._briefSelectedGuardrails = guardrails;
      toast('Brief loaded into Generator — click Generate with AI');
    }, 100);
  };

  function saveStepState() {
    if (step === 1) {
      const el = document.getElementById('brief-purpose');
      if (el) state.purpose = el.value.trim();
    }
  }
})();
