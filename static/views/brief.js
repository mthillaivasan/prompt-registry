// Brief Builder — 6-step guided form + review, purely frontend state
(function () {
  const TOTAL_STEPS = 6;
  const STEP_NAMES = ['Purpose', 'Input type', 'Output type', 'Audience', 'Constraints', 'Guardrails'];
  let step = 1;
  let validationError = '';
  let validationResult = null;
  let tier3Count = 0; // question counter per step
  let briefScore = null; // { score, label, weakest_dimension, improvement_tip, dimensions }
  let restructuredBrief = null; // restructured text from Claude
  let useRestructured = true; // default to restructured
  const state = { purpose: '', inputType: '', outputType: '', audience: '', constraints: [], selectedGuardrails: [],
    clientName: '', ownerName: '', ownerRole: '', skipped: [] };
  let guardrailData = null;
  let briefId = null; // server-side brief ID once created

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

  viewInits.brief = async function (params) {
    step = 1; validationError = '';
    state.purpose = ''; state.inputType = ''; state.outputType = ''; state.audience = '';
    state.constraints = []; state.selectedGuardrails = [];
    state.clientName = ''; state.ownerName = ''; state.ownerRole = ''; state.skipped = [];
    validationResult = null; tier3Count = 0; briefScore = null; restructuredBrief = null; useRestructured = true;
    guardrailData = null; briefId = null;

    // Resume existing brief — from params or localStorage
    const resumeId = (params && params.briefId) || localStorage.getItem('pr_active_brief');
    if (resumeId && !(params && params.startNew)) {
      try {
        const b = await api('/briefs/' + resumeId);
        if (b.status === 'In Progress') {
          // Show resume prompt if coming from nav (not from dashboard Continue)
          if (!params || !params.briefId) {
            const el = document.getElementById('view-brief');
            const bAnswers = JSON.parse(b.step_answers || '{}');
            const bSkipped = bAnswers.skipped || [];
            const nSkipped = bSkipped.length;
            let resumeHtml = `<div class="card" style="max-width:500px;margin:60px auto;text-align:center">
              <h3 style="margin-bottom:12px">You have an unfinished brief</h3>
              <p style="color:var(--text2);margin-bottom:8px">${esc(b.client_name || 'Untitled')} — Step ${b.step_progress}/6</p>`;
            if (nSkipped > 0) {
              resumeHtml += `<p style="color:var(--amber);font-size:13px;margin-bottom:8px">You have ${nSkipped} skipped step${nSkipped > 1 ? 's' : ''}. Complete them for a stronger brief.</p>`;
            }
            resumeHtml += `<p style="color:var(--text2);font-size:13px;margin-bottom:20px">Last updated ${timeAgo(b.updated_at)}</p>
              <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
                <button class="btn btn-gold" onclick="navigate('brief',{briefId:'${b.brief_id}'})">Continue Brief</button>`;
            if (nSkipped > 0) {
              const firstSkipped = bSkipped[0].step;
              resumeHtml += `<button class="btn btn-outline" onclick="navigate('brief',{briefId:'${b.brief_id}',jumpTo:${firstSkipped}})">Complete skipped steps</button>`;
            }
            resumeHtml += `<button class="btn btn-outline" onclick="navigate('brief',{startNew:true})">Start New</button>
              </div>
            </div>`;
            el.innerHTML = resumeHtml;
            return;
          }
          briefId = b.brief_id;
          step = b.step_progress || 1;
          state.clientName = b.client_name || '';
          state.ownerName = b.business_owner_name || '';
          state.ownerRole = b.business_owner_role || '';
          briefScore = b.quality_score ? { score: b.quality_score, label: '', weakest_dimension: '', improvement_tip: '' } : null;
          const answers = JSON.parse(b.step_answers || '{}');
          state.purpose = answers.purpose || '';
          state.inputType = answers.inputType || '';
          state.outputType = answers.outputType || '';
          state.audience = answers.audience || '';
          state.constraints = answers.constraints || [];
          state.skipped = answers.skipped || [];
          state.selectedGuardrails = JSON.parse(b.selected_guardrails || '[]');
          localStorage.setItem('pr_active_brief', briefId);
          if (params && params.jumpTo) step = params.jumpTo;
        }
      } catch (e) {
        localStorage.removeItem('pr_active_brief');
      }
    }
    // Pre-fill from template
    if (params && params.fromTemplate) {
      const t = params.fromTemplate;
      state.purpose = t.description || '';
      state.inputType = t.input_type || '';
      state.outputType = t.output_type || '';
      window._briefHasContent = true;
      window._inBrief = true;
      const el = document.getElementById('view-brief');
      el.innerHTML = `<div class="card" style="border-left:3px solid var(--accent);max-width:600px;margin:40px auto">
        <h3 style="margin-bottom:8px">Starting from template: ${esc(t.name)}</h3>
        <p style="color:var(--text2);font-size:14px;margin-bottom:16px">${esc(t.description)} — customise any step or proceed directly to review.</p>
        <div style="display:flex;gap:12px">
          <button class="btn btn-gold" onclick="navigate('brief')">Customise Steps</button>
          <button class="btn btn-outline" onclick="window._briefReview()">Go to Review</button>
        </div>
      </div>`;
      return;
    }
    window._inBrief = true;
    window._briefHasContent = false;
    renderStep();
  };

  function isStepValid() {
    if (step === 1) return state.purpose.length >= 20;
    if (step === 2) return !!state.inputType;
    if (step === 3) return !!state.outputType;
    if (step === 4) return !!state.audience;
    return true; // steps 5, 6 always valid
  }

  function getValidationHint() {
    if (step === 1) return 'Please describe what this prompt needs to do in at least 20 characters';
    if (step === 2) return 'Please select an input type';
    if (step === 3) return 'Please select an output type';
    if (step === 4) return 'Please select an audience';
    return '';
  }

  function buildQualityDial() {
    if (!briefScore) return '';
    const s = briefScore.score;
    const pct = s / 100;
    const r = 38, cx = 50, cy = 50;
    const circumference = 2 * Math.PI * r;
    const dashoffset = circumference * (1 - pct);
    const color = s >= 70 ? 'var(--green)' : s >= 40 ? 'var(--amber)' : 'var(--red)';
    return `<div style="text-align:center;min-width:100px">
      <svg width="80" height="80" viewBox="0 0 100 100">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--surface2)" stroke-width="6"/>
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="6"
          stroke-dasharray="${circumference}" stroke-dashoffset="${dashoffset}"
          stroke-linecap="round" transform="rotate(-90 ${cx} ${cy})" style="transition:stroke-dashoffset .5s"/>
        <text x="${cx}" y="${cy+2}" text-anchor="middle" dominant-baseline="middle"
          fill="${color}" font-family="var(--font-mono)" font-size="18" font-weight="700">${s}</text>
      </svg>
      <div style="font-size:11px;color:var(--text2);margin-top:-4px">${esc(briefScore.label)}</div>
    </div>`;
  }

  function renderStep() {
    const el = document.getElementById('view-brief');
    const skippedNums = new Set(state.skipped.map(s => s.step));
    const progress = `<div style="display:flex;gap:4px;margin-bottom:12px">${
      Array.from({length: TOTAL_STEPS}, (_, i) => i + 1).map(i => {
        if (skippedNums.has(i)) return `<div style="flex:1;height:4px;border-radius:2px;border:1px solid var(--amber);background:transparent"></div>`;
        return `<div style="flex:1;height:4px;border-radius:2px;background:${i <= step ? 'var(--accent)' : 'var(--surface2)'}"></div>`;
      }).join('')}</div>`;
    const remaining = STEP_NAMES.slice(step).map(n => esc(n)).join(' &middot; ');

    let html = `<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
      <div>
        <h2 style="margin-bottom:4px">Step ${step} of ${TOTAL_STEPS}</h2>
        <p style="color:var(--text2);font-size:13px">${remaining ? 'Next: ' + remaining : 'Final step'}</p>
      </div>
      ${buildQualityDial()}
    </div>` + progress + '<div class="card">';

    if (step === 1) {
      const charCount = state.purpose.length;
      const isValid = charCount >= 20;
      html += `<h3 style="margin-bottom:12px">What does this prompt need to do?</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
          <div class="form-group"><label>Client</label><input type="text" id="brief-client" value="${esc(state.clientName)}" placeholder="e.g. Lombard Odier" onchange="window._briefMeta('clientName',this.value)"><a style="font-size:11px;color:var(--text2);cursor:pointer;margin-top:4px;display:block" onclick="document.getElementById('brief-client').value='';window._briefMeta('clientName','')">Skip for now</a></div>
          <div class="form-group"><label>Business owner</label><input type="text" id="brief-owner" value="${esc(state.ownerName)}" placeholder="e.g. Sarah Chen" onchange="window._briefMeta('ownerName',this.value)"><a style="font-size:11px;color:var(--text2);cursor:pointer;margin-top:4px;display:block" onclick="document.getElementById('brief-owner').value='';window._briefMeta('ownerName','');document.getElementById('brief-role').focus()">Skip for now</a></div>
          <div class="form-group"><label>Role</label><input type="text" id="brief-role" value="${esc(state.ownerRole)}" placeholder="e.g. Head of Settlement" onchange="window._briefMeta('ownerRole',this.value)"><a style="font-size:11px;color:var(--text2);cursor:pointer;margin-top:4px;display:block" onclick="document.getElementById('brief-role').value='';window._briefMeta('ownerRole','')">Skip for now</a></div>
        </div>
        <p style="color:var(--text2);margin-bottom:16px;font-size:12px">This records who the requirement came from for the audit trail.</p>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Describe in one or two sentences what you want the AI to do.</p>
        <div class="form-group">
          <textarea id="brief-purpose" rows="4" oninput="window._briefPurposeInput(this.value)" placeholder="e.g. Summarise incoming customer complaints and flag any that mention regulatory obligations or potential liability.">${esc(state.purpose)}</textarea>
          <div style="display:flex;justify-content:flex-end;margin-top:6px">
            <span class="mono" style="font-size:12px;color:${isValid ? 'var(--green)' : 'var(--text2)'}">${charCount}/20 ${isValid ? '&#10003;' : 'min'}</span>
          </div>
        </div>`;
      if (validationError && !isValid) {
        html += `<p style="color:var(--amber);font-size:13px;margin-top:-8px">${getValidationHint()}</p>`;
      }
      // Tier 2 — suggestion card
      if (validationResult && validationResult.tier === 2) {
        html += `<div style="background:var(--surface2);border-left:3px solid var(--accent);padding:14px 16px;border-radius:0 6px 6px 0;margin-top:8px">
          <div style="font-size:13px;color:var(--accent);margin-bottom:6px;font-weight:600">One suggestion</div>
          <p style="font-size:14px;color:var(--text);margin:0 0 10px">${esc(validationResult.suggestion || '')}</p>
          <div style="display:flex;gap:8px">
            <button class="btn btn-gold btn-sm" onclick="window._briefUseSuggestion()">Use this addition</button>
            <button class="btn btn-outline btn-sm" onclick="window._briefSkipSuggestion()">Continue as is</button>
          </div>
        </div>`;
      }
      // Tier 3 — question with options
      if (validationResult && validationResult.tier === 3) {
        const counterText = tier3Count === 1 ? 'One question — then we can move on.' : 'Last question on this — then we are ready.';
        html += `<div style="background:var(--surface2);border-left:3px solid var(--amber);padding:14px 16px;border-radius:0 6px 6px 0;margin-top:8px">
          <div style="font-size:12px;color:var(--amber);margin-bottom:6px;font-family:var(--font-mono)">${counterText}</div>
          <div style="font-size:15px;color:var(--text);margin-bottom:10px;font-family:var(--font-heading)">${esc(validationResult.question || 'Help me understand this better')}</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px">`;
        (validationResult.options || []).forEach(opt => {
          html += `<button class="btn btn-outline btn-sm" onclick="window._briefPickOption('${esc(opt)}')">${esc(opt)}</button>`;
        });
        html += `</div>
          <div style="display:flex;gap:8px">
            <input type="text" id="brief-tier3-free" style="flex:1" placeholder="${esc(validationResult.free_text_placeholder || 'Or type your answer...')}">
            <button class="btn btn-gold btn-sm" onclick="window._briefSubmitFree()">Continue with this</button>
          </div>
        </div>`;
      }
    } else if (step === 2) {
      html += `<h3 style="margin-bottom:12px">What goes in?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">What will the AI receive as input?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      INPUT_OPTIONS.forEach(opt => {
        const sel = state.inputType === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('inputType','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
      if (validationError && !state.inputType) {
        html += `<p style="color:var(--red);font-size:13px;margin-top:12px">${getValidationHint()}</p>`;
      }
    } else if (step === 3) {
      html += `<h3 style="margin-bottom:12px">What comes out?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">What should the AI produce?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      OUTPUT_OPTIONS.forEach(opt => {
        const sel = state.outputType === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('outputType','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
      if (validationError && !state.outputType) {
        html += `<p style="color:var(--red);font-size:13px;margin-top:12px">${getValidationHint()}</p>`;
      }
    } else if (step === 4) {
      html += `<h3 style="margin-bottom:12px">Who receives the output?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Who will read or use the AI output?</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
      AUDIENCE_OPTIONS.forEach(opt => {
        const sel = state.audience === opt;
        html += `<button class="btn ${sel ? 'btn-primary' : 'btn-outline'}" onclick="window._briefSelect('audience','${esc(opt)}')">${esc(opt)}</button>`;
      });
      html += '</div>';
      if (validationError && !state.audience) {
        html += `<p style="color:var(--red);font-size:13px;margin-top:12px">${getValidationHint()}</p>`;
      }
    } else if (step === 5) {
      html += `<h3 style="margin-bottom:12px">Any constraints?</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Select all that apply.</p>
        <div style="display:flex;flex-direction:column;gap:0">`;
      CONSTRAINT_OPTIONS.forEach(opt => {
        const checked = state.constraints.includes(opt) ? 'checked' : '';
        html += `<label style="display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid #2e2e2e;cursor:pointer;width:100%" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background='transparent'">
          <input type="checkbox" style="width:20px;height:20px;flex-shrink:0" ${checked} onchange="window._briefToggle('${esc(opt)}',this.checked)">
          <span style="font-size:14px;color:var(--text)">${esc(opt)}</span>
        </label>`;
      });
      html += '</div>';
    } else if (step === 6) {
      html += renderStep6();
    }

    html += '</div>';

    // Navigation
    const valid = isStepValid();
    html += '<div style="display:flex;justify-content:space-between;margin-top:16px">';
    if (step > 1) {
      html += '<button class="btn btn-outline" onclick="window._briefPrev()">Back</button>';
    } else {
      html += '<div></div>';
    }
    if (step < TOTAL_STEPS) {
      const canSkip = step >= 2 && step <= 5;
      const disabledStyle = valid ? '' : (canSkip ? '' : 'opacity:0.4;cursor:not-allowed;pointer-events:none');
      html += '<div style="display:flex;align-items:center;gap:16px">';
      html += `<button class="btn btn-gold" id="brief-next-btn" style="padding:12px 0;width:${step > 1 ? '120px' : '100%'};justify-content:center;font-size:15px;${disabledStyle}" onclick="window._briefNext()">Next</button>`;
      if (canSkip) {
        html += `<a style="font-size:13px;color:var(--text2);cursor:pointer" onclick="window._briefSkipStep()">Skip for now</a>`;
      }
      html += '</div>';
    } else {
      html += '<button class="btn btn-gold" style="padding:12px 0;width:120px;justify-content:center;font-size:15px" onclick="window._briefReview()">Review Brief</button>';
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

    html += '<div style="padding:16px;background:var(--surface2);border-radius:8px;display:flex;justify-content:space-between;align-items:center">';
    html += '<span style="font-size:14px;font-weight:600">Estimated Gold Standard Impact</span>';
    const totalOptional = tier3.length;
    const selectedOptional = tier3.filter(d => state.selectedGuardrails.includes(d.code)).length;
    const removedImpact = tier3.filter(d => !state.selectedGuardrails.includes(d.code)).reduce((sum, d) => sum + (d.score_impact_if_removed || 0), 0);
    const estimated = Math.max(0, Math.round(100 - removedImpact));
    const gc = estimated >= 70 ? 'grade-high' : estimated >= 40 ? 'grade-mid' : 'grade-low';
    html += `<div style="text-align:center"><span class="grade ${gc}" style="width:56px;height:56px;font-size:16px">${estimated}</span>`;
    html += `<div style="font-size:11px;color:var(--text2);margin-top:4px">${selectedOptional}/${totalOptional} optional selected</div></div>`;
    html += '</div>';

    return html;
  }

  async function loadGuardrails() {
    try {
      const params = new URLSearchParams({
        input_type: state.inputType || '',
        deployment_target: inferDeployTarget(),
        risk_tier: inferRiskTier(),
        prompt_text_snippet: state.purpose || '',
      });
      guardrailData = await api('/scoring-dimensions/applicable?' + params.toString());
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
    let html = `<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">
      <h2>Review Brief</h2>${buildQualityDial()}
    </div>
      <div class="card">
        <table>
          <tr><td style="color:var(--text2);width:140px;vertical-align:top">Purpose</td><td>${esc(state.purpose || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Input type</td><td>${esc(state.inputType || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Output type</td><td>${esc(state.outputType || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Audience</td><td>${esc(state.audience || '(not specified)')}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Constraints</td><td>${state.constraints.length ? state.constraints.map(c => esc(c)).join('<br>') : '(none selected)'}</td></tr>
          <tr><td style="color:var(--text2);vertical-align:top">Guardrails</td><td>${state.selectedGuardrails.length} dimensions selected</td></tr>
          ${state.skipped.length ? '<tr><td style="color:var(--text2);vertical-align:top">Skipped</td><td>' + state.skipped.map(s => '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span class="badge badge-amber">' + esc(s.name) + '</span><span style="font-size:12px;color:var(--text2)">Adding this would improve prompt quality.</span><a style="font-size:12px;color:var(--accent);cursor:pointer" onclick="window._briefJumpToStep(' + s.step + ')">Complete now</a></div>').join('') + '</td></tr>' : ''}
        </table>
      </div>`;

    // Restructured brief
    if (restructuredBrief) {
      const selRestructured = useRestructured ? 'border-color:var(--accent)' : 'border-color:var(--border);opacity:.7';
      const selOriginal = !useRestructured ? 'border-color:var(--accent)' : 'border-color:var(--border);opacity:.7';
      html += `<div class="card" style="${selRestructured}">
        <div class="card-title" style="margin-bottom:8px;color:var(--accent)">Restructured brief — recommended</div>
        <div class="prompt-text">${esc(restructuredBrief)}</div>
        <button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="window._briefSelectVersion(true)">
          ${useRestructured ? '&#10003; Selected' : 'Use restructured brief'}
        </button>
      </div>
      <div class="card" style="${selOriginal}">
        <div class="card-title" style="margin-bottom:8px">Original answers</div>
        <div class="prompt-text" id="brief-output">${esc(brief)}</div>
        <button class="btn btn-outline btn-sm" style="margin-top:10px" onclick="window._briefSelectVersion(false)">
          ${!useRestructured ? '&#10003; Selected' : 'Use my original answers'}
        </button>
      </div>`;
    } else {
      html += `<div class="card">
        <div class="card-title" style="margin-bottom:8px">Structured Brief</div>
        <div class="prompt-text" id="brief-output">${esc(brief)}</div>
      </div>`;
    }

    if (briefScore && briefScore.improvement_tip) {
      html += `<div style="font-size:13px;color:var(--text2);margin-bottom:12px;padding:0 4px">Tip: ${esc(briefScore.improvement_tip)}</div>`;
    }

    html += `<div style="display:flex;gap:12px;margin-top:8px">
        <button class="btn btn-outline" onclick="window._briefBack()">Back to editing</button>
        <button class="btn btn-outline" onclick="window._briefCopy()">Copy brief</button>
        <button class="btn btn-gold" onclick="window._briefSend()">Send to Generator</button>
      </div>`;
    el.innerHTML = html;
  }

  window._briefSelectVersion = function (useRestr) {
    useRestructured = useRestr;
    renderReview();
  };

  // Server persistence
  async function saveBriefToServer() {
    const answers = {
      purpose: state.purpose, inputType: state.inputType, outputType: state.outputType,
      audience: state.audience, constraints: state.constraints, skipped: state.skipped,
    };
    const body = {
      step_progress: step,
      step_answers: answers,
      selected_guardrails: state.selectedGuardrails,
      quality_score: briefScore ? briefScore.score : 0,
      client_name: state.clientName || null,
      business_owner_name: state.ownerName || null,
      business_owner_role: state.ownerRole || null,
    };
    try {
      if (!briefId) {
        const created = await api('/briefs', { method: 'POST', body: {
          client_name: state.clientName || null,
          business_owner_name: state.ownerName || null,
          business_owner_role: state.ownerRole || null,
        }});
        briefId = created.brief_id;
      }
      localStorage.setItem('pr_active_brief', briefId);
      await api('/briefs/' + briefId + '/step/' + step, { method: 'PATCH', body });
    } catch (e) { console.warn('Brief save failed:', e.message); }
  }

  // Exposed handlers
  window._briefMeta = function (field, val) { state[field] = val; };
  window._briefJumpToStep = function (n) {
    state.skipped = state.skipped.filter(s => s.step !== n);
    step = n;
    validationError = ''; validationResult = null;
    renderStep();
  };
  window._briefSkipStep = async function () {
    saveStepState();
    const skippedStep = step;
    const skippedName = STEP_NAMES[step - 1] || 'Step ' + step;
    state.skipped.push({ step: skippedStep, name: skippedName, timestamp: new Date().toISOString() });
    validationError = ''; validationResult = null; tier3Count = 0;
    step++;
    await updateScore();
    await saveBriefToServer();
    // Log skip to audit trail
    if (briefId) {
      api('/briefs/' + briefId + '/skip-step/' + skippedStep, { method: 'POST' }).catch(() => {});
    }
    if (step === 6 && !guardrailData) { renderStep(); loadGuardrails(); }
    else renderStep();
    toast('Skipped: ' + skippedName);
  };
  window._briefSelect = function (field, val) { state[field] = val; validationError = ''; renderStep(); };
  window._briefToggle = function (opt, checked) {
    if (checked && !state.constraints.includes(opt)) state.constraints.push(opt);
    if (!checked) state.constraints = state.constraints.filter(c => c !== opt);
  };
  window._briefGuardrail = function (code, checked) {
    if (checked && !state.selectedGuardrails.includes(code)) state.selectedGuardrails.push(code);
    if (!checked) state.selectedGuardrails = state.selectedGuardrails.filter(c => c !== code);
    renderStep();
  };
  window._briefPurposeInput = function (val) {
    state.purpose = val;
    validationError = '';
    validationResult = null;
    if (val.length > 0) window._briefHasContent = true;
    localStorage.setItem('brief_step_1_draft', val);
    const btn = document.getElementById('brief-next-btn');
    if (btn) {
      if (val.length >= 20) { btn.style.opacity = '1'; btn.style.cursor = 'pointer'; btn.style.pointerEvents = 'auto'; }
      else { btn.style.opacity = '0.4'; btn.style.cursor = 'not-allowed'; btn.style.pointerEvents = 'none'; }
    }
  };
  window._briefUseSuggestion = function () {
    if (validationResult && validationResult.suggested_addition) {
      state.purpose = state.purpose.trim() + ' ' + validationResult.suggested_addition;
    }
    validationResult = null; validationError = '';
    step++; renderStep();
  };
  window._briefSkipSuggestion = function () {
    validationResult = null; validationError = '';
    step++; renderStep();
  };
  window._briefPickOption = function (opt) {
    state.purpose = state.purpose.trim() + ' — ' + opt;
    validationResult = null; validationError = '';
    // Re-validate with the enriched purpose
    renderStep();
    window._briefNext();
  };
  window._briefSubmitFree = function () {
    const el = document.getElementById('brief-tier3-free');
    const val = el ? el.value.trim() : '';
    if (!val) { toast('Enter an answer or tap an option above', 'error'); return; }
    state.purpose = state.purpose.trim() + ' — ' + val;
    validationResult = null; validationError = '';
    renderStep();
    window._briefNext();
  };
  window._briefPrev = function () { saveStepState(); validationError = ''; validationResult = null; tier3Count = 0; step--; guardrailData = step < 6 ? null : guardrailData; renderStep(); };
  window._briefNext = async function () {
    saveStepState();
    if (!isStepValid()) { validationError = getValidationHint(); renderStep(); return; }

    if (step === 1) {
      const btn = document.getElementById('brief-next-btn');
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Checking...'; }
      try {
        const resp = await api('/prompts/validate-brief', { method: 'POST', body: { description: state.purpose } });
        validationResult = resp;
        if (resp.tier === 1) {
          // Strong — proceed
        } else if (resp.tier === 2) {
          renderStep(); return;
        } else {
          // Tier 3 — enforce question counter
          tier3Count++;
          if (tier3Count >= 3) {
            // Third attempt — accept as tier 2, never ask again
            validationResult = null;
          } else {
            renderStep(); return;
          }
        }
      } catch (e) { /* proceed on failure */ }
    }

    validationError = ''; validationResult = null; tier3Count = 0;
    step++;
    await updateScore();
    await saveBriefToServer();
    if (step === 6 && !guardrailData) { renderStep(); loadGuardrails(); }
    else renderStep();
  };
  window._briefReview = async function () {
    saveStepState();
    window._inBrief = false;
    window._briefHasContent = false;
    await updateScore();
    await saveBriefToServer();
    await loadRestructuredBrief();
    renderReview();
  };
  window._briefBack = function () { step = 1; validationError = ''; validationResult = null; tier3Count = 0; guardrailData = null; renderStep(); };

  async function updateScore() {
    try {
      briefScore = await api('/prompts/briefs/score', { method: 'POST', body: {
        purpose: state.purpose, input_type: state.inputType, output_type: state.outputType,
        audience: state.audience, constraints: state.constraints,
        deployment_target: inferDeployTarget(),
        skipped_steps: state.skipped.map(s => s.step),
      }});
    } catch (e) { /* score is optional */ }
  }

  async function loadRestructuredBrief() {
    try {
      const resp = await api('/prompts/briefs/restructure', { method: 'POST', body: { brief_text: buildBriefText() } });
      restructuredBrief = resp.restructured;
    } catch (e) { restructuredBrief = null; }
  }

  window._briefCopy = function () {
    const text = buildBriefText();
    navigator.clipboard.writeText(text).then(() => toast('Brief copied to clipboard')).catch(() => {
      const el = document.getElementById('brief-output');
      if (el) { const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }
      toast('Select and copy manually', 'error');
    });
  };

  window._briefSend = function () {
    window._inBrief = false;
    window._briefHasContent = false;
    const guardrails = [...state.selectedGuardrails];
    if (briefId) {
      api('/briefs/' + briefId + '/complete', { method: 'POST' }).catch(() => {});
    }
    localStorage.removeItem('pr_active_brief');
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

      // Store brief text for the Generate API call, but do NOT put it in the textarea
      window._briefTextForGenerate = (useRestructured && restructuredBrief) ? restructuredBrief : buildBriefText();
      if (textarea) textarea.value = '';

      window._briefSelectedGuardrails = guardrails;
      window._briefConstraints = [...state.constraints];
      window._briefPrefilled = true;
      toast('Brief loaded. Click Generate with AI to create your prompt.');
    }, 100);
  };

  function saveStepState() {
    if (step === 1) {
      const el = document.getElementById('brief-purpose');
      if (el) state.purpose = el.value.trim();
      const c = document.getElementById('brief-client');
      if (c) state.clientName = c.value.trim();
      const o = document.getElementById('brief-owner');
      if (o) state.ownerName = o.value.trim();
      const r = document.getElementById('brief-role');
      if (r) state.ownerRole = r.value.trim();
    }
  }
})();
