// Template Library view
viewInits.templates = async function () {
  const el = document.getElementById('view-templates');
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading templates...</div>';
  try {
    const templates = await api('/templates');
    if (!templates.length) {
      el.innerHTML = '<div class="empty-state"><h3>No templates available</h3></div>';
      return;
    }
    let html = '<h2 style="margin-bottom:20px">Template Library</h2>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px">';
    templates.forEach(t => {
      const riskClass = t.risk_tier === 'High' ? 'badge-red' : t.risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
      const gradeColor = (t.gold_standard_grade || '').startsWith('A') ? 'var(--green)' : (t.gold_standard_grade || '').startsWith('B') ? 'var(--accent)' : 'var(--amber)';
      const compCount = (t.component_codes || []).length;
      html += `<div class="card" style="display:flex;flex-direction:column">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span class="mono" style="font-size:12px;color:var(--accent)">${esc(t.code)}</span>
          <div style="display:flex;gap:6px">
            <span class="badge ${riskClass}">${esc(t.risk_tier)}</span>
            <span class="mono" style="font-size:13px;font-weight:700;color:${gradeColor}">${esc(t.gold_standard_grade || '')}</span>
          </div>
        </div>
        <h3 style="font-size:15px;margin-bottom:6px">${esc(t.name)}</h3>
        <p style="font-size:13px;color:var(--text2);margin-bottom:8px;flex:1">${esc(t.description)}</p>
        <div style="font-size:12px;color:var(--text2);margin-bottom:12px">
          <span class="mono">${compCount} components</span>
          ${t.use_case ? ' &middot; ' + esc(t.use_case) : ''}
        </div>`;
      if (t.output_example) {
        html += `<div style="margin-bottom:12px">
          <a style="font-size:12px;color:var(--accent);cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none';this.textContent=this.nextElementSibling.style.display==='none'?'See example output':'Hide example'">See example output</a>
          <div class="prompt-text" style="display:none;margin-top:8px;font-size:12px;max-height:200px">${esc(t.output_example)}</div>
        </div>`;
      }
      html += `<button class="btn btn-gold btn-sm" style="width:100%;justify-content:center" onclick="window._useTemplate('${t.template_id}','${esc(t.code)}')">Use Template</button>
      </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + esc(err.message) + '</p></div>';
  }
};

window._useTemplate = async function (templateId, code) {
  try {
    const t = await api('/templates/' + templateId);
    navigate('brief', { fromTemplate: t });
  } catch (e) { toast(e.message, 'error'); }
};
