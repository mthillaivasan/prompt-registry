// Brief Builder — 6-step guided form + review, purely frontend state
(function () {
  const TOTAL_STEPS = 5;
  const STEP_NAMES = ['Metadata', 'Brief', 'Audience', 'Constraints', 'Guardrails'];
  let step = 1;
  let validationError = '';
  let validationResult = null;
  let tier3Count = 0; // question counter per step (still incremented; no longer caps — see PHASE2 §5)
  let tier3Selected = new Set(); // multi-select picks for current Tier-3 question
  let validating = false; // Step 1 re-validate in flight
  let validationSeq = 0; // monotonic counter; responses with stale seq are discarded
  let briefScore = null; // { score, label, weakest_dimension, improvement_tip, dimensions }
  let restructuredBrief = null; // restructured text from Claude
  let restructuredTitle = null; // Claude-generated title; user may edit at review step
  let useRestructured = true;
  const state = { purpose: '', inputType: '', outputType: '', audience: '', constraints: [], selectedGuardrails: [],
    clientName: '', ownerName: '', ownerRole: '', skipped: [] };
  window._briefConversation = [];
  window._briefQuestionCount = {};
  let guardrailData = null;
  let briefId = null; // server-side brief ID once created

  const INPUT_OPTIONS = ['Form responses', 'Document or report', 'Data table', 'Email thread', 'Free text', 'Structured data', 'Meeting notes', 'Other'];
  const OUTPUT_OPTIONS = ['Structured assessment', 'Executive summary', 'Briefing note', 'Recommendation', 'Flag report', 'Draft email or communication', 'Data extraction', 'Comparison table', 'Other'];
  const AUDIENCE_OPTIONS = ['Senior committee', 'Operations team', 'Executive', 'Compliance team', 'External counterparty', 'Project sponsor', 'Broad internal audience'];

  // B1: structured Extraction topic pickers on Step 1. Mirrors services/topic_rubrics.py
  // EXTRACTION_RUBRICS (options only). Non-Extraction prompt types render a
  // "not yet available" placeholder for topics 2-5+4b — design §B1 / §B6 #5.
  const PROMPT_TYPES = ['Extraction', 'Classification', 'Summarisation', 'Comparison', 'Analysis', 'Comms', 'Governance', 'Risk Review'];
  const EXTRACTION_TOPICS = [
    // B2 note: topic_1_prompt_type is multi-select. When validate-topic fires
    // against sibling_answers, the rubric selection rule is:
    //   (1) if "Extraction" is in the picked array, use the Extraction rubric
    //   (2) else use the first picked type's rubric
    //   (3) if that type has no rubric defined, return 501 "rubric not defined"
    // sibling_answers expects string values at the API layer — join the array
    // with ", " or pick the primary type when serialising.
    { id: 'topic_1_prompt_type',  name: 'Prompt Type',                                       required: true,  multiSelect: true, options: PROMPT_TYPES },
    { id: 'topic_2_source_doc',   name: 'Source document type',                              required: false, options: ['Prospectus', 'Policy', 'Circular', 'Regulatory filing', 'Report', 'Contract', 'Email thread', 'Form responses', 'Data table', 'Free text', 'Other'] },
    { id: 'topic_3_output_format',name: 'Output format',                                     required: false, options: ['JSON object', 'Table/CSV', 'Markdown extraction report', 'Flag report', 'Data extraction payload', 'Other'] },
    { id: 'topic_4_target_system',name: 'Target system (where the output goes)',             required: false, options: ['Simcorp', 'Temenos', 'Charles River', 'Bloomberg AIM', 'Murex', 'Internal spreadsheet', 'Downstream AI or pipeline', 'Advisory only — no system', 'Other'] },
    { id: 'topic_4b_ai_platform', name: 'AI platform (what runs the prompt)',                required: false, options: ['Claude', 'MS Copilot — Declarative', 'MS Copilot — Custom Engine', 'OpenAI', 'Multi-model', 'Other'] },
    { id: 'topic_5_risk_tier',    name: 'Risk tier',                                         required: false, options: ['Minimal', 'Limited', 'High', 'Prohibited'] },
  ];

  // B1 transitional dual-write: picking a topic also sets the legacy state field
  // so the generator handoff (which currently reads state.inputType / state.outputType)
  // keeps working. Remove in B3 once topic→generator piping lands cleanly.
  const TOPIC_2_TO_INPUT_TYPE = {
    'Prospectus': 'Document or report',
    'Policy': 'Document or report',
    'Circular': 'Document or report',
    'Regulatory filing': 'Document or report',
    'Report': 'Document or report',
    'Contract': 'Document or report',
    'Email thread': 'Email thread',
    'Form responses': 'Form responses',
    'Data table': 'Data table',
    'Free text': 'Free text',
    'Other': '',
  };
  const TOPIC_3_TO_OUTPUT_TYPE = {
    'JSON object': 'Data extraction',
    'Table/CSV': 'Data extraction',
    'Markdown extraction report': 'Data extraction',
    'Flag report': 'Flag report',
    'Data extraction payload': 'Data extraction',
    'Other': '',
  };

  let topicState = {}; // { topic_id: { value, state: 'red'|'amber'|'green', updated_at } }
  let expandedTopic = null; // id of the currently-expanded topic, or null
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
    validationResult = null; tier3Count = 0; tier3Selected.clear(); briefScore = null; restructuredBrief = null; restructuredTitle = null; useRestructured = true;
    validating = false; validationSeq = 0;
    topicState = {}; expandedTopic = null;
    window._briefConversation = []; window._briefQuestionCount = {};
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
              <p style="color:var(--text2);margin-bottom:8px">${esc(b.title || b.client_name || 'Untitled')} — Step ${b.step_progress}/6</p>`;
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
          // B1: hydrate per-topic entries (Phase A schema — see docs/CHECKLIST_DESIGN.md §B4).
          for (const key in answers) {
            if (key.startsWith('topic_')) topicState[key] = answers[key];
          }
          // Transitional: if a prior topic pick exists but state.inputType / state.outputType
          // are empty (e.g. brief was picked via Step 1 but the generator was never reached),
          // derive them now so Steps 3+ and the generator handoff still see the right values.
          if (topicState.topic_2_source_doc && !state.inputType) {
            state.inputType = TOPIC_2_TO_INPUT_TYPE[topicState.topic_2_source_doc.value] || '';
          }
          if (topicState.topic_3_output_format && !state.outputType) {
            state.outputType = TOPIC_3_TO_OUTPUT_TYPE[topicState.topic_3_output_format.value] || '';
          }
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
    if (step === 1) {
      const e = topicState.topic_1_prompt_type;
      if (!e || e.state !== 'green') return false;
      return Array.isArray(e.value) ? e.value.length > 0 : !!e.value;
    }
    if (step === 2) return state.purpose.length >= 20;
    if (step === 3) return !!state.audience;
    return true; // steps 4, 5 always valid
  }

  function getValidationHint() {
    if (step === 1) return 'Please pick a Prompt Type';
    if (step === 2) return 'Please describe the task in at least 20 characters';
    if (step === 3) return 'Please select an audience';
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
      // Step 1 — structured metadata picks. Six quick picks. Prompt Type is the gate;
      // others optional. See docs/CHECKLIST_DESIGN.md §B1/B2.
      html += `<h3 style="margin-bottom:8px">Describe this prompt at a glance</h3>
        <p style="color:var(--text2);margin-bottom:16px;font-size:14px">Pick the structured metadata. Only Prompt Type is required; other picks are quick and help the generator produce a better prompt.</p>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px">
          <div class="form-group"><label>Client</label><input type="text" id="brief-client" value="${esc(state.clientName)}" placeholder="e.g. Lombard Odier" onchange="window._briefMeta('clientName',this.value)"></div>
          <div class="form-group"><label>Business owner</label><input type="text" id="brief-owner" value="${esc(state.ownerName)}" placeholder="e.g. Sarah Chen" onchange="window._briefMeta('ownerName',this.value)"></div>
          <div class="form-group"><label>Role</label><input type="text" id="brief-role" value="${esc(state.ownerRole)}" placeholder="e.g. Head of Settlement" onchange="window._briefMeta('ownerRole',this.value)"></div>
        </div>
        <p style="color:var(--text2);margin-bottom:20px;font-size:12px">Client/owner/role records who the requirement came from, for the audit trail.</p>`;

      // All structured topics render regardless of Prompt Type. They are
      // generic metadata; Phase A's Extraction-only scope applies to prose
      // topic coaching (B2), not structured capture.
      EXTRACTION_TOPICS.forEach(topic => {
        const entry = topicState[topic.id];
        const picked = entry && entry.value;
        const pickedArr = Array.isArray(picked) ? picked : (picked ? [picked] : []);
        const summary = pickedArr.join(', ');
        html += `<div style="margin-bottom:14px">
          <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">
            <span style="font-size:14px;font-weight:600">${esc(topic.name)}</span>`;
        if (topic.required) {
          html += `<span style="font-size:11px;color:var(--amber);font-family:var(--font-mono)">required</span>`;
        }
        if (summary) {
          html += `<span style="font-size:11px;color:var(--green);font-family:var(--font-mono)">${esc(summary)}</span>`;
        }
        html += `</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px">`;
        topic.options.forEach(opt => {
          const sel = pickedArr.includes(opt);
          const cls = sel ? 'btn btn-gold btn-sm' : 'btn btn-outline btn-sm';
          html += `<button class="${cls}" onclick="window._briefPickTopic('${esc(topic.id)}','${esc(opt)}')">${esc(opt)}</button>`;
        });
        html += `</div>
        </div>`;
      });

      if (validationError && !isStepValid()) {
        html += `<p style="color:var(--amber);font-size:13px;margin-top:12px">${getValidationHint()}</p>`;
      }
    } else if (step === 2) {
      // Step 2 — prose brief, scoped. Prose topic coaching (Review button, Tier cards)
      // is out of scope for B1 — lands in B2.
      const charCount = state.purpose.length;
      const isValid = charCount >= 20;
      html += `<h3 style="margin-bottom:8px">Describe the task</h3>
        <p style="color:var(--text2);margin-bottom:12px;font-size:14px">Describe the task: what data points to extract, per-field format, how to handle missing data, confidence requirements, error modes. Everything else is already captured above.</p>
        <div class="form-group">
          <textarea id="brief-purpose" rows="8" oninput="window._briefPurposeInput(this.value)" placeholder="e.g. Extract subscription cut-off time (HH:MM + time zone), ISIN, and minimum investment amount from the Share Class Details and Dealing Procedures sections of each prospectus. Output as JSON with page references. If a field is missing, return null with confidence: low. Handle partial documents by flagging the missing section but not blocking.">${esc(state.purpose)}</textarea>
          <div style="display:flex;justify-content:flex-end;margin-top:6px">
            <span class="mono" style="font-size:12px;color:${isValid ? 'var(--green)' : 'var(--text2)'}">${charCount}/20 ${isValid ? '&#10003;' : 'min'}</span>
          </div>
        </div>`;
      if (validationError && !isValid) {
        html += `<p style="color:var(--amber);font-size:13px;margin-top:-8px">${getValidationHint()}</p>`;
      }
    } else if (step === 3) {
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
    } else if (step === 4) {
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
    } else if (step === 5) {
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
      const canSkip = step >= 2 && step <= 4;
      const disabledStyle = valid ? '' : (canSkip ? '' : 'opacity:0.4;cursor:not-allowed;pointer-events:none');
      html += '<div style="display:flex;align-items:center;gap:16px">';
      const nextLabel = step === 1 ? 'Next stage' : 'Next';
      html += `<button class="btn btn-gold" id="brief-next-btn" style="padding:12px 0;width:${step > 1 ? '120px' : '100%'};justify-content:center;font-size:15px;${disabledStyle}" onclick="window._briefNext()">${nextLabel}</button>`;
      if (step === 1 && validating) {
        html += `<span style="font-size:12px;color:var(--text2)">Checking brief…</span>`;
      }
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
      html += `<div class="card">
        <div class="card-title" style="margin-bottom:8px">Title</div>
        <input type="text" id="brief-title-input" maxlength="120"
               value="${esc(restructuredTitle || '')}"
               placeholder="e.g. Summarise FINMA obligations from prospectus"
               oninput="window._briefTitleInput(this.value)"
               style="width:100%">
      </div>`;
      const selRestructured = useRestructured ? 'border-color:var(--accent)' : 'border-color:var(--border);opacity:.7';
      const selOriginal = !useRestructured ? 'border-color:var(--accent)' : 'border-color:var(--border);opacity:.7';
      html += `<div class="card" style="${selRestructured}">
        <div class="card-title" style="margin-bottom:8px;color:var(--accent)">Restructured brief — recommended</div>
        <textarea id="brief-restructured-input" rows="6" style="width:100%"
                  oninput="window._briefRestructuredInput(this.value)">${esc(restructuredBrief)}</textarea>
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
  window._briefTitleInput = function (val) { restructuredTitle = val; };
  window._briefRestructuredInput = function (val) { restructuredBrief = val; };

  // Server persistence
  async function saveBriefToServer() {
    const answers = {
      purpose: state.purpose, inputType: state.inputType, outputType: state.outputType,
      audience: state.audience, constraints: state.constraints, skipped: state.skipped,
    };
    // B1: include per-topic entries so Step 1 picks persist. Backend save_step
    // handler uses .update() semantics so legacy flat keys + topic_* keys coexist.
    for (const topicId in topicState) {
      answers[topicId] = topicState[topicId];
    }
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
    validationError = ''; validationResult = null; tier3Count = 0; tier3Selected.clear();
    step++;
    await updateScore();
    await saveBriefToServer();
    // Log skip to audit trail
    if (briefId) {
      api('/briefs/' + briefId + '/skip-step/' + skippedStep, { method: 'POST' }).catch(() => {});
    }
    if (step === 5 && !guardrailData) { renderStep(); loadGuardrails(); }
    else renderStep();
    toast('Skipped: ' + skippedName);
  };
  window._briefSelect = function (field, val) { state[field] = val; validationError = ''; renderStep(); };
  window._briefPickTopic = function (topicId, val) {
    const topic = EXTRACTION_TOPICS.find(t => t.id === topicId);
    const now = new Date().toISOString();
    if (topic && topic.multiSelect) {
      const current = topicState[topicId] && topicState[topicId].value;
      const arr = Array.isArray(current) ? current.slice() : (current ? [current] : []);
      const idx = arr.indexOf(val);
      if (idx >= 0) arr.splice(idx, 1);
      else arr.push(val);
      if (arr.length === 0) {
        delete topicState[topicId];
      } else {
        topicState[topicId] = { value: arr, state: 'green', updated_at: now };
      }
    } else {
      topicState[topicId] = { value: val, state: 'green', updated_at: now };
    }
    // Transitional dual-write: picking single-select topic 2 / 3 also sets the
    // legacy state field so the generator handoff (state.inputType / state.outputType)
    // keeps working during the B1→B3 window. Remove when B3 lands proper
    // topic-to-generator piping.
    if (topicId === 'topic_2_source_doc') {
      state.inputType = TOPIC_2_TO_INPUT_TYPE[val] || '';
    } else if (topicId === 'topic_3_output_format') {
      state.outputType = TOPIC_3_TO_OUTPUT_TYPE[val] || '';
    }
    validationError = '';
    renderStep();
    saveBriefToServer();
  };
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
    if (val.length > 0) window._briefHasContent = true;
    localStorage.setItem('brief_step_1_draft', val);
    // Stale result: clear the old card while user is editing so it can't be acted on.
    // Re-render so the Review button's state (primary/disabled/neutral) updates too.
    if (validationResult) { validationResult = null; renderStep(); return; }
    const btn = document.getElementById('brief-next-btn');
    if (btn) {
      if (val.length >= 20) { btn.style.opacity = '1'; btn.style.cursor = 'pointer'; btn.style.pointerEvents = 'auto'; }
      else { btn.style.opacity = '0.4'; btn.style.cursor = 'not-allowed'; btn.style.pointerEvents = 'none'; }
    }
    const reviewBtn = document.getElementById('brief-review-btn');
    if (reviewBtn) {
      if (val.length >= 200) { reviewBtn.style.opacity = '1'; reviewBtn.style.cursor = 'pointer'; reviewBtn.style.pointerEvents = 'auto'; }
      else { reviewBtn.style.opacity = '0.4'; reviewBtn.style.cursor = 'not-allowed'; reviewBtn.style.pointerEvents = 'none'; }
    }
  };
  window._briefUseSuggestion = function () {
    if (validationResult && validationResult.suggested_addition) {
      state.purpose = state.purpose.trim() + ' ' + validationResult.suggested_addition;
    }
    validationResult = null; validationError = '';
    _briefRevalidate();
  };
  // Dismiss the current probe and re-validate. Records a coaching entry with
  // skipped=false so validate_brief's filter forwards it to Claude — the
  // dismissal text IS the answer. System-prompt rule "DO NOT re-ask anything
  // in PRIOR COACHING" then prevents repetition. See PHASE2 §5.
  window._briefDismissProbe = function () {
    const q = validationResult ? (validationResult.question || validationResult.suggestion || '') : '';
    if (q) {
      window._briefConversation.push({
        role: 'system', step, question: q,
        answer: '(user dismissed this line of thought)', skipped: false,
      });
    }
    validationResult = null; validationError = ''; tier3Selected.clear();
    _briefRevalidate();
  };
  window._briefSkipSuggestion = function () {
    window._briefConversation.push({ role: 'system', step, question: validationResult ? validationResult.suggestion : '', answer: 'skipped', skipped: true });
    validationResult = null; validationError = ''; tier3Selected.clear();
    step++; renderStep();
  };
  window._briefSkipQuestion = function () {
    window._briefConversation.push({ role: 'system', step, question: validationResult ? validationResult.question : '', answer: 'skipped', skipped: true });
    if (briefId) {
      api('/briefs/' + briefId + '/skip-step/' + step, { method: 'POST' }).catch(() => {});
    }
    validationResult = null; validationError = ''; tier3Count = 0; tier3Selected.clear();
    step++; renderStep();
    toast('Question skipped');
  };
  window._briefAbandonTrack = function () {
    window._briefConversation.push({ role: 'system', step, question: 'track', answer: 'abandoned', skipped: true });
    if (briefId) {
      api('/briefs/' + briefId + '/skip-step/' + step, { method: 'POST' }).catch(() => {});
    }
    validationResult = null; validationError = ''; tier3Count = 0; tier3Selected.clear();
    step++; renderStep();
    toast('Moved on');
  };
  window._briefToggleOption = function (opt) {
    if (tier3Selected.has(opt)) tier3Selected.delete(opt);
    else tier3Selected.add(opt);
    renderStep();
  };
  window._briefSubmit = function () {
    const el = document.getElementById('brief-tier3-free');
    const free = el ? el.value.trim() : '';
    const picks = Array.from(tier3Selected);
    if (!picks.length && !free) {
      toast('Pick one or more options or type an answer', 'error');
      return;
    }
    const parts = [];
    if (picks.length) parts.push(picks.join(', '));
    if (free) parts.push(free);
    const answer = parts.join('. ') + '.';
    window._briefConversation.push({ role: 'system', step, question: validationResult ? validationResult.question : '', answer, skipped: false });
    state.purpose = state.purpose.trim() + ' — ' + answer;
    tier3Selected.clear();
    validationResult = null; validationError = '';
    _briefRevalidate();
  };
  window._briefPrev = function () { saveStepState(); validationError = ''; validationResult = null; tier3Count = 0; tier3Selected.clear(); step--; guardrailData = step < 5 ? null : guardrailData; renderStep(); };

  // Step 1 auto re-validate loop. No step advancement — caller decides when
  // to move on via the Next stage button. Stale-response guard: seq captured
  // before the await; if seq changes while awaiting (user kept typing /
  // clicked another action), the response is dropped on arrival.
  async function _briefRevalidate() {
    if (step !== 1) return;
    if ((state.purpose || '').length < 20) {
      validationResult = null; validating = false;
      renderStep();
      return;
    }
    validationSeq += 1;
    const mySeq = validationSeq;
    validating = true;
    renderStep();
    try {
      const resp = await api('/prompts/validate-brief', { method: 'POST', body: { description: state.purpose, conversation_history: window._briefConversation } });
      if (mySeq !== validationSeq) return;
      validationResult = resp;
      if (resp.tier === 1) {
        window._briefConversation.push({ role: 'system', step, question: 'validation', answer: 'accepted', skipped: false });
      } else if (resp.tier === 3) {
        window._briefQuestionCount[step] = (window._briefQuestionCount[step] || 0) + 1;
        tier3Count = window._briefQuestionCount[step];
      }
    } catch (e) {
      if (mySeq !== validationSeq) return;
      console.warn('[Brief] Validation failed:', e.message);
      validationResult = null;
    } finally {
      if (mySeq === validationSeq) {
        validating = false;
        renderStep();
      }
    }
  }
  window._briefRevalidate = _briefRevalidate;

  window._briefNext = async function () {
    saveStepState();
    if (!isStepValid()) { validationError = getValidationHint(); renderStep(); return; }

    validationError = ''; validationResult = null; tier3Count = 0; tier3Selected.clear();
    step++;
    await updateScore();
    await saveBriefToServer();
    if (step === 5 && !guardrailData) { renderStep(); loadGuardrails(); }
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
  window._briefBack = function () { step = 1; validationError = ''; validationResult = null; tier3Count = 0; tier3Selected.clear(); guardrailData = null; renderStep(); };

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
      restructuredTitle = resp.title || null;
    } catch (e) { restructuredBrief = null; restructuredTitle = null; }
  }

  window._briefCopy = function () {
    const text = buildBriefText();
    navigator.clipboard.writeText(text).then(() => toast('Brief copied to clipboard')).catch(() => {
      const el = document.getElementById('brief-output');
      if (el) { const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }
      toast('Select and copy manually', 'error');
    });
  };

  window._briefSend = async function () {
    window._inBrief = false;
    window._briefHasContent = false;
    const guardrails = [...state.selectedGuardrails];
    if (briefId) {
      try {
        await api('/briefs/' + briefId, { method: 'PATCH', body: {
          title: restructuredTitle || null,
          restructured_brief: restructuredBrief || null,
        }});
      } catch (e) { console.warn('Brief title save failed:', e.message); }
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

      if (title && !title.value) title.value = restructuredTitle || state.purpose.substring(0, 80);

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

  // Tier-3 Enter-to-submit. Gated on the question card being in the DOM so
  // this listener is a no-op outside the Brief Builder. INPUT/TEXTAREA/BUTTON
  // are excluded so the free-text input's own onkeydown handles itself,
  // toggle buttons keep Enter-to-activate, and the catch-all only fires when
  // focus is on the body / wrapper.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (!document.getElementById('brief-tier3-free')) return;
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return;
    if (tier3Selected.size === 0) return;
    e.preventDefault();
    window._briefSubmit();
  });
})();
