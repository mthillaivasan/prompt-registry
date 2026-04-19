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

  // Briefs section — card layout
  if (_dashFilter !== 'prompts' && briefs.length > 0) {
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;margin-bottom:16px">';
    briefs.forEach(b => {
      const answers = JSON.parse(b.step_answers || '{}');
      const purpose = answers.purpose || '';
      const title = b.title || (purpose ? purpose.substring(0, 50) : (b.client_name || 'Untitled brief'));
      const qualityColor = b.quality_score >= 70 ? 'var(--green)' : b.quality_score >= 40 ? 'var(--amber)' : 'var(--red)';
      const qualityLabel = b.quality_score >= 80 ? 'Gold standard' : b.quality_score >= 60 ? 'Strong' : b.quality_score >= 40 ? 'Reasonable' : 'Weak';
      const dots = Array.from({length: 6}, (_, i) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${i < b.step_progress ? 'var(--accent)' : 'var(--border)'}"></span>`).join('');
      const ownerLine = b.business_owner_name ? esc(b.business_owner_name) + (b.business_owner_role ? ', ' + esc(b.business_owner_role) : '') : '—';
      html += `<div class="card" style="position:relative;cursor:pointer;border:1px dashed #252535;transition:border-color .15s" onmouseover="this.style.borderColor='var(--purple)'" onmouseout="this.style.borderColor='#252535'" onclick="navigate('brief',{briefId:'${b.brief_id}'})">
        <a style="position:absolute;top:8px;right:10px;font-size:18px;line-height:1;color:var(--text2);cursor:pointer;padding:2px 6px" title="Delete brief" onclick="event.stopPropagation();window._dashConfirmDelete('${b.brief_id}','${esc((title || '').replace(/'/g, '\\\''))}')">&times;</a>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <span class="badge badge-purple" style="font-size:11px">IN BRIEF</span>
          <span style="display:flex;align-items:center;gap:4px">${dots}<span class="mono" style="font-size:11px;color:var(--text2);margin-left:4px">Step ${b.step_progress}/5</span></span>
        </div>
        <h3 style="font-size:16px;margin-bottom:10px">${esc(title)}</h3>
        <div style="font-size:13px;color:var(--text2);line-height:1.8">
          <div>Owner: ${ownerLine}</div>
          <div>Quality: <span class="mono" style="color:${qualityColor}">${b.quality_score}</span> — ${qualityLabel}</div>
          <div>Started: ${timeAgo(b.created_at)} &middot; Updated: ${timeAgo(b.updated_at)}</div>
        </div>
        <button class="btn btn-gold btn-sm" style="margin-top:14px;width:100%;justify-content:center" onclick="event.stopPropagation();navigate('brief',{briefId:'${b.brief_id}'})">Continue Brief</button>
      </div>`;
    });
    html += '</div>';
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

window._dashConfirmDelete = function (briefId, title) {
  const backdrop = document.createElement('div');
  backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center';
  backdrop.innerHTML = `
    <div class="card" style="max-width:420px;margin:0">
      <h3 style="margin-bottom:10px">Delete this brief?</h3>
      <p style="color:var(--text2);font-size:14px;margin-bottom:6px">${esc(title || 'Untitled')}</p>
      <p style="color:var(--text2);font-size:13px;margin-bottom:18px">This cannot be undone.</p>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button class="btn btn-outline btn-sm" id="_dash-delete-cancel">Cancel</button>
        <button class="btn btn-danger btn-sm" id="_dash-delete-confirm">Delete</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  const close = () => backdrop.remove();
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
  document.getElementById('_dash-delete-cancel').addEventListener('click', close);
  document.getElementById('_dash-delete-confirm').addEventListener('click', async () => {
    try {
      await api('/briefs/' + briefId, { method: 'DELETE' });
      toast('Brief deleted');
      close();
      navigate('dashboard');
    } catch (e) {
      toast(e.message || 'Delete failed', 'error');
      close();
    }
  });
};
