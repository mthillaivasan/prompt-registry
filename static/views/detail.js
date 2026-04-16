// Prompt Detail view — active version text, compliance scores, version timeline
viewInits.detail = async function (params) {
  const el = document.getElementById('view-detail');
  const promptId = params.promptId;

  if (!promptId) {
    el.innerHTML = '<div class="empty-state"><h3>Select a prompt from the Dashboard</h3></div>';
    return;
  }

  el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading prompt...</div>';

  try {
    const [prompt, timeline] = await Promise.all([
      api('/prompts/' + promptId),
      api('/prompts/' + promptId + '/timeline'),
    ]);

    const activeVersion = prompt.versions && prompt.versions.length
      ? prompt.versions[prompt.versions.length - 1] : null;
    const activeTimeline = timeline.find(t => t.is_active);

    // Header
    let html = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px">
        <div>
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
            <h2>${escapeHtml(prompt.name)}</h2>
            ${activeTimeline ? badgeFor(activeTimeline.overall_result) : badgeFor(null)}
          </div>
          <p style="color:var(--text2)">${escapeHtml(prompt.description || '')}</p>
          <div style="margin-top:8px">${(prompt.tags || []).map(t => '<span class="badge badge-purple">' + escapeHtml(t) + '</span>').join(' ')}</div>
        </div>
        <div style="display:flex;align-items:center;gap:16px">`;

    if (activeTimeline && activeTimeline.gold_standard_grade != null) {
      const gc = gradeClass(activeTimeline.gold_standard_grade);
      html += `<div style="text-align:center"><span class="grade ${gc}">${Math.round(activeTimeline.gold_standard_grade)}</span><div style="font-size:11px;color:var(--text2);margin-top:4px">Gold Score</div></div>`;
    }

    html += `
          <button class="btn btn-outline btn-sm" onclick="runComplianceFromDetail(${promptId})">Re-score</button>
        </div>
      </div>`;

    // Active version text
    html += `<div class="card"><div class="card-header"><span class="card-title">Active Version ${activeVersion ? 'v' + activeVersion.version : ''}</span></div>`;
    if (activeVersion) {
      html += `<div class="prompt-text">${escapeHtml(activeVersion.content)}</div>`;
    } else {
      html += '<p style="color:var(--text2)">No versions yet.</p>';
    }
    html += '</div>';

    // Compliance scores
    if (activeTimeline && activeTimeline.gold_standard_grade != null) {
      html += buildScoresSection(activeTimeline, timeline);
    }

    // Version timeline
    html += buildTimelineSection(timeline, promptId);

    el.innerHTML = html;
    attachCollapsibleHandlers(el);

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + escapeHtml(err.message) + '</p></div>';
  }
};

function buildScoresSection(activeTimeline, allTimeline) {
  // Get scores from the compliance result via the defects on timeline
  // We need to fetch the compliance job for full scores — use what we have
  let html = '<div class="card"><div class="card-header"><span class="card-title">Compliance Scores</span></div>';

  if (activeTimeline.defects && activeTimeline.defects.length > 0) {
    html += '<div style="margin-bottom:12px"><span class="badge badge-red">' + activeTimeline.open_defects + ' blocking</span> <span class="badge badge-amber">' + activeTimeline.total_defects + ' total defects</span></div>';
    html += '<table><thead><tr><th>Dimension</th><th>Framework</th><th>Score</th><th>Severity</th><th>Finding</th></tr></thead><tbody>';
    activeTimeline.defects.forEach(d => {
      const sevClass = d.severity === 'Blocking' ? 'badge-red' : 'badge-amber';
      html += `<tr>
        <td><strong>${escapeHtml(d.dimension_code)}</strong><br><span style="color:var(--text2);font-size:12px">${escapeHtml(d.dimension_name)}</span></td>
        <td>${escapeHtml(d.framework)}</td>
        <td><div class="score-bar score-${d.current_score}"><span>${d.current_score}/5</span><div class="score-bar-track"><div class="score-bar-fill"></div></div></div></td>
        <td><span class="badge ${sevClass}">${escapeHtml(d.severity)}</span></td>
        <td style="color:var(--text2);font-size:13px;max-width:300px">${escapeHtml(d.current_finding)}</td>
      </tr>`;
    });
    html += '</tbody></table>';
  } else {
    html += '<p style="color:var(--green)">No defects found. All dimensions scored 4 or above.</p>';
  }

  html += '</div>';
  return html;
}

function buildTimelineSection(timeline, promptId) {
  let html = `<div class="card">
    <div class="collapsible-header" data-target="timeline-body"><span class="card-title">Version Timeline (${timeline.length})</span></div>
    <div id="timeline-body" class="collapsible-body">`;

  if (timeline.length === 0) {
    html += '<p style="color:var(--text2)">No versions.</p>';
  } else {
    html += '<table><thead><tr><th>Version</th><th>Created</th><th>By</th><th>Type</th><th>Status</th><th>Grade</th><th>Defects</th></tr></thead><tbody>';
    timeline.forEach(v => {
      const typeHtml = v.was_upgrade
        ? '<span class="badge badge-blue">Upgrade</span>'
        : '<span class="badge badge-purple">Manual</span>';
      const gc = gradeClass(v.gold_standard_grade);
      const gradeHtml = v.gold_standard_grade != null
        ? '<span class="grade ' + gc + '" style="width:36px;height:36px;font-size:12px">' + Math.round(v.gold_standard_grade) + '</span>'
        : '<span style="color:var(--text2)">-</span>';
      const activeHtml = v.is_active ? ' <span class="badge badge-green">Active</span>' : '';
      html += `<tr>
        <td>v${v.version_number}${activeHtml}</td>
        <td style="color:var(--text2)">${timeAgo(v.created_at)}</td>
        <td>${escapeHtml(v.created_by)}</td>
        <td>${typeHtml}</td>
        <td>${badgeFor(v.overall_result)}</td>
        <td>${gradeHtml}</td>
        <td>${v.total_defects > 0 ? '<span class="badge badge-red">' + v.open_defects + '/' + v.total_defects + '</span>' : '<span style="color:var(--text2)">0</span>'}</td>
      </tr>`;
    });
    html += '</tbody></table>';
  }

  html += '</div></div>';
  return html;
}

function attachCollapsibleHandlers(container) {
  container.querySelectorAll('.collapsible-header').forEach(header => {
    header.addEventListener('click', () => {
      header.classList.toggle('open');
      const target = document.getElementById(header.dataset.target);
      if (target) target.classList.toggle('open');
    });
  });
}

async function runComplianceFromDetail(promptId) {
  try {
    const prompt = await api('/prompts/' + promptId);
    const activeVersion = prompt.versions[prompt.versions.length - 1];
    if (!activeVersion) { toast('No version to score', 'error'); return; }

    toast('Queuing compliance check...');
    const job = await api('/compliance-checks', {
      method: 'POST',
      body: { version_id: activeVersion.id, force_refresh: true },
    });

    toast('Running... job ' + job.job_id);
    const result = await pollJob(job.job_id);

    if (result.status === 'Complete') {
      toast('Compliance check complete');
      navigate('detail', { promptId });
    } else {
      toast('Compliance check failed: ' + (result.error_message || 'Unknown error'), 'error');
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}
