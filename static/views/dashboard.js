let _dashFilter = 'all'; // all | prompts | briefs

viewInits.dashboard = async function () {
  const el = document.getElementById('view-dashboard');
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading...</div>';
  try {
    const [prompts, briefs] = await Promise.all([api('/prompts'), api('/briefs')]);
    const inProgressBriefs = briefs.filter(b => b.status === 'In Progress');

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Dashboard</h2>
        <div style="display:flex;gap:8px">
          <button class="btn btn-gold" onclick="navigate('brief')">New Brief</button>
          <button class="btn btn-outline" onclick="navigate('generator')">New Prompt</button>
          <button class="btn btn-outline" onclick="navigate('import')">Import</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button class="btn ${_dashFilter==='all'?'btn-primary':'btn-outline'} btn-sm" onclick="window._dashSetFilter('all')">All</button>
        <button class="btn ${_dashFilter==='prompts'?'btn-primary':'btn-outline'} btn-sm" onclick="window._dashSetFilter('prompts')">Prompts (${prompts.length})</button>
        <button class="btn ${_dashFilter==='briefs'?'btn-primary':'btn-outline'} btn-sm" onclick="window._dashSetFilter('briefs')">Briefs (${inProgressBriefs.length})</button>
      </div>
      <div id="dash-content"></div>`;

    renderDashContent(prompts, inProgressBriefs);
  } catch (err) {
    console.error('Dashboard load error:', err);
    el.innerHTML = '<div class="empty-state"><h3>Error loading</h3><p style="color:var(--red)">' + esc(err.message) + '</p></div>';
  }
};

window._dashSetFilter = function (f) { _dashFilter = f; navigate('dashboard'); };

function renderDashContent(prompts, briefs) {
  const container = document.getElementById('dash-content');
  if (!container) return;
  let html = '';

  // Briefs section
  if (_dashFilter !== 'prompts' && briefs.length > 0) {
    html += '<div class="card" style="padding:0;overflow:hidden"><table><thead><tr>';
    html += '<th></th><th>Client</th><th>Owner</th><th>Progress</th><th>Quality</th><th>Updated</th><th></th>';
    html += '</tr></thead><tbody>';
    briefs.forEach(b => {
      const answers = JSON.parse(b.step_answers || '{}');
      const purpose = answers.purpose || '';
      const qualityColor = b.quality_score >= 70 ? 'var(--green)' : b.quality_score >= 40 ? 'var(--amber)' : 'var(--red)';
      html += `<tr style="cursor:pointer" onclick="navigate('brief',{briefId:'${b.brief_id}'})">
        <td><span class="badge badge-amber">Brief</span></td>
        <td><strong>${esc(b.client_name || '—')}</strong>${purpose ? '<br><span style="font-size:12px;color:var(--text2)">' + esc(purpose.substring(0, 60)) + '</span>' : ''}</td>
        <td style="font-size:13px;color:var(--text2)">${esc(b.business_owner_name || '—')}</td>
        <td><span class="mono" style="font-size:13px">Step ${b.step_progress}/6</span></td>
        <td><span class="mono" style="font-size:13px;color:${qualityColor}">${b.quality_score}</span></td>
        <td style="color:var(--text2)">${timeAgo(b.updated_at)}</td>
        <td><button class="btn btn-outline btn-sm" onclick="event.stopPropagation();navigate('brief',{briefId:'${b.brief_id}'})">Continue</button></td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  }

  // Prompts section
  if (_dashFilter !== 'briefs') {
    if (prompts.length > 0) {
      html += '<div class="card" style="padding:0;overflow:hidden"><table><thead><tr>';
      html += '<th></th><th>Title</th><th>Type</th><th>Risk Tier</th><th>Status</th><th>Updated</th><th></th>';
      html += '</tr></thead><tbody>';
      prompts.forEach(p => {
        const riskClass = p.risk_tier === 'High' || p.risk_tier === 'Prohibited' ? 'badge-red'
          : p.risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
        const statusClass = p.status === 'Active' ? 'badge-green'
          : p.status === 'Draft' ? 'badge-blue'
          : p.status === 'Retired' ? 'badge-red' : 'badge-amber';
        const pid = p.prompt_id;
        html += `<tr style="cursor:pointer" onclick="navigate('detail',{promptId:'${pid}'})">
          <td><span class="badge badge-purple">Prompt</span></td>
          <td><strong>${esc(p.title)}</strong></td>
          <td>${esc(p.prompt_type)}</td>
          <td><span class="badge ${riskClass}">${esc(p.risk_tier)}</span></td>
          <td><span class="badge ${statusClass}">${esc(p.status)}</span></td>
          <td style="color:var(--text2)">${timeAgo(p.updated_at)}</td>
          <td><button class="btn btn-outline btn-sm" onclick="event.stopPropagation();navigate('detail',{promptId:'${pid}'})">View</button></td>
        </tr>`;
      });
      html += '</tbody></table></div>';
    }
  }

  if (!html) {
    html = '<div class="empty-state"><h3>Nothing here yet</h3><p>Start a new brief or create a prompt.</p></div>';
  }
  container.innerHTML = html;
}
