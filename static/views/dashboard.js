viewInits.dashboard = async function () {
  const el = document.getElementById('view-dashboard');
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading prompts...</div>';
  try {
    const prompts = await api('/prompts');
    if (prompts.length === 0) {
      el.innerHTML = '<div class="empty-state"><h3>No prompts yet</h3><p>Create one in the Generator or import an existing prompt.</p></div>';
      return;
    }
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Prompts</h2>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="navigate('generator')">New Prompt</button>
          <button class="btn btn-outline" onclick="navigate('import')">Import</button>
        </div>
      </div>
      <div class="card" style="padding:0;overflow:hidden">
        <table><thead><tr>
          <th>Title</th><th>Type</th><th>Risk Tier</th><th>Status</th><th>Updated</th><th></th>
        </tr></thead><tbody id="dash-tbody"></tbody></table>
      </div>`;
    const tbody = document.getElementById('dash-tbody');
    prompts.forEach(p => {
      const riskClass = p.risk_tier === 'High' || p.risk_tier === 'Prohibited' ? 'badge-red'
        : p.risk_tier === 'Limited' ? 'badge-amber' : 'badge-green';
      const statusClass = p.status === 'Active' ? 'badge-green'
        : p.status === 'Draft' ? 'badge-blue'
        : p.status === 'Retired' ? 'badge-red' : 'badge-amber';
      const pid = p.prompt_id;
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.innerHTML = `
        <td><strong>${esc(p.title)}</strong></td>
        <td>${esc(p.prompt_type)}</td>
        <td><span class="badge ${riskClass}">${esc(p.risk_tier)}</span></td>
        <td><span class="badge ${statusClass}">${esc(p.status)}</span></td>
        <td style="color:var(--text2)">${timeAgo(p.updated_at)}</td>
        <td><button class="btn btn-outline btn-sm" onclick="event.stopPropagation();navigate('detail',{promptId:'${pid}'})">View</button></td>`;
      tr.onclick = function() { navigate('detail', {promptId: pid}); };
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Dashboard load error:', err);
    el.innerHTML = '<div class="empty-state"><h3>Error loading prompts</h3><p style="color:var(--red)">' + esc(err.message) + '</p><p style="color:var(--text2);margin-top:8px">Check the browser console for details.</p></div>';
  }
};
