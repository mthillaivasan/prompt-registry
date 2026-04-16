// Brief Builder — 5-step guided form, purely frontend state
(function () {
  let step = 1;
  const state = { purpose: '', inputType: '', outputType: '', audience: '', constraints: [] };

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
    state.purpose = ''; state.inputType = ''; state.outputType = ''; state.audience = ''; state.constraints = [];
    renderStep();
  };

  function renderStep() {
    const el = document.getElementById('view-brief');
    const progress = `<div style="display:flex;gap:4px;margin-bottom:24px">${[1,2,3,4,5].map(i =>
      `<div style="flex:1;height:4px;border-radius:2px;background:${i <= step ? 'var(--accent)' : 'var(--surface2)'}"></div>`
    ).join('')}</div>`;

    let html = '<h2 style="margin-bottom:8px">Brief Builder</h2><p style="color:var(--text2);margin-bottom:20px;font-size:14px">Step ' + step + ' of 5</p>' + progress + '<div class="card">';

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
    }

    html += '</div>';

    // Navigation
    html += '<div style="display:flex;justify-content:space-between;margin-top:16px">';
    if (step > 1) {
      html += `<button class="btn btn-outline" onclick="window._briefPrev()">Back</button>`;
    } else {
      html += '<div></div>';
    }
    if (step < 5) {
      html += `<button class="btn btn-primary" onclick="window._briefNext()">Next</button>`;
    } else {
      html += `<button class="btn btn-primary" onclick="window._briefReview()">Review Brief</button>`;
    }
    html += '</div>';

    el.innerHTML = html;
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
  window._briefPrev = function () { saveStepState(); step--; renderStep(); };
  window._briefNext = function () { saveStepState(); step++; renderStep(); };
  window._briefReview = function () { saveStepState(); renderReview(); };
  window._briefBack = function () { step = 1; renderStep(); };

  window._briefCopy = function () {
    const text = buildBriefText();
    navigator.clipboard.writeText(text).then(() => toast('Brief copied to clipboard')).catch(() => {
      const el = document.getElementById('brief-output');
      if (el) { const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }
      toast('Select and copy manually', 'error');
    });
  };

  window._briefSend = function () {
    navigate('generator');
    setTimeout(() => {
      const title = document.getElementById('gen-title');
      const type = document.getElementById('gen-type');
      const input = document.getElementById('gen-input');
      const output = document.getElementById('gen-output');
      const textarea = document.getElementById('gen-text');

      if (title && !title.value) title.value = state.purpose.substring(0, 80);

      // Map output type to prompt type
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
      if (type && state.outputType && typeMap[state.outputType]) {
        type.value = typeMap[state.outputType];
      }

      if (input) input.value = state.inputType || input.value;
      if (output) output.value = state.outputType || output.value;

      if (textarea) {
        textarea.value = buildBriefText();
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
      }

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
