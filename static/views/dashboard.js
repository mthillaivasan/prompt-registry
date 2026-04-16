// Dashboard view — list all prompts with status badge and gold standard grade
viewInits.dashboard = async function () {
  const el = document.getElementById('view-dashboard');
  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading prompts...</div>';

  try {
    const prompts = await api('/prompts');

    if (prompts.length === 0) {
      el.innerHTML = `
        <div class="empty-state">
          <h3>No prompts yet</h3>
          <p>Create one in the Generator or import an existing prompt.</p>
        </div>`;
      return;
    }

    // Fetch compliance status for each prompt's latest version
    const enriched = await Promise.all(prompts.map(async p => {
      let status = null;
      let gold = null;
      let blocked = false;
      if (p.latest_version) {
        try {
          const timeline = await api('/prompts/' + p.id + '/timeline');
          const active = timeline.find(t => t.is_active);
          if (active) {
            status = active.overall_result;
            gold = active.gold_standard_grade;
            blocked = status === 'Blocked';
          }
        } catch (e) { /* no compliance result yet */ }
      }
      return { ...p, compliance_status: status, gold_score: gold, blocked };
    }));

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Prompts</h2>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="navigate('generator')">New Prompt</button>
          <button class="btn btn-outline" onclick="navigate('import')">Import</button>
        </div>
      </div>
      <div class="card" style="padding:0;overflow:hidden">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Tags</th>
              <th>Version</th>
              <th>Status</th>
              <th>Grade</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody id="dashboard-tbody"></tbody>
        </table>
      </div>`;

    const tbody = document.getElementById('dashboard-tbody');
    enriched.forEach(p => {
      const ver = p.latest_version ? 'v' + p.latest_version.version : '-';
      const tags = (p.tags || []).map(t => '<span class="badge badge-purple">' + escapeHtml(t) + '</span>').join(' ');
      const gc = gradeClass(p.gold_score);
      const gradeHtml = p.gold_score != null
        ? '<span class="grade ' + gc + '">' + Math.round(p.gold_score) + '</span>'
        : '<span class="grade grade-none">-</span>';

      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.name)}</strong></td>
        <td style="color:var(--text2);max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.description || '')}</td>
        <td>${tags}</td>
        <td>${ver}</td>
        <td>${badgeFor(p.compliance_status)}</td>
        <td>${gradeHtml}</td>
        <td style="color:var(--text2)">${timeAgo(p.updated_at)}</td>`;
      tr.addEventListener('click', () => navigate('detail', { promptId: p.id }));
      tbody.appendChild(tr);
    });

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
  }
};
