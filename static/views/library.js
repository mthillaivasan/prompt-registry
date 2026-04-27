// Prompt Library — Admin-only reference library of gold-standard examples.
// Surfaced in Brief Builder coaching (Drop L2) and used as few-shot context
// for validate-topic. Distinct from /templates (those feed the generator).

(function () {
  const PROMPT_TYPES = [
    'Governance', 'Analysis', 'Comms', 'Classification',
    'Summarisation', 'Extraction', 'Comparison', 'Risk Review',
  ];
  const DOMAINS = ['finance', 'general'];

  let _state = {
    page: 1,
    pageSize: 25,
    promptType: '',
    domain: '',
    items: [],
    total: 0,
    hasNext: false,
    editingId: null,
  };

  viewInits.library = async function () {
    const el = document.getElementById('view-library');
    el.innerHTML = '<div class="loading-state"><div class="spinner"></div> Loading library…</div>';
    try {
      await _loadPage();
      _render();
    } catch (err) {
      el.innerHTML = '<div class="empty-state"><p style="color:var(--red)">' + esc(err.message) + '</p></div>';
    }
  };

  async function _loadPage() {
    const qs = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
    });
    if (_state.promptType) qs.set('prompt_type', _state.promptType);
    if (_state.domain) qs.set('domain', _state.domain);
    const data = await api('/library?' + qs.toString());
    _state.items = data.items || [];
    _state.total = data.total || 0;
    _state.hasNext = !!data.has_next;
  }

  function _render() {
    const el = document.getElementById('view-library');
    let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">';
    html += '<h2>Prompt Library</h2>';
    html += '<button class="btn btn-primary btn-sm" id="lib-new-btn">New entry</button>';
    html += '</div>';

    html += '<div class="card" style="margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">';
    html += '<label style="margin:0">Prompt type</label>';
    html += '<select id="lib-filter-type" style="width:auto"><option value="">All</option>';
    for (const t of PROMPT_TYPES) {
      html += '<option value="' + escAttr(t) + '"' + (_state.promptType === t ? ' selected' : '') + '>' + esc(t) + '</option>';
    }
    html += '</select>';
    html += '<label style="margin:0;margin-left:12px">Domain</label>';
    html += '<select id="lib-filter-domain" style="width:auto"><option value="">All</option>';
    for (const d of DOMAINS) {
      html += '<option value="' + escAttr(d) + '"' + (_state.domain === d ? ' selected' : '') + '>' + esc(d) + '</option>';
    }
    html += '</select>';
    html += '<span style="margin-left:auto;color:var(--text2);font-size:13px">' + _state.total + ' total</span>';
    html += '</div>';

    if (!_state.items.length) {
      html += '<div class="empty-state"><h3>No library entries</h3><p>Add entries via the New button or run <code>scripts/seed_library.py</code>.</p></div>';
    } else {
      html += '<div class="card" style="padding:0;overflow:hidden">';
      html += '<table><thead><tr>';
      html += '<th style="width:26%">Title</th>';
      html += '<th style="width:11%">Prompt type</th>';
      html += '<th style="width:9%">Domain</th>';
      html += '<th style="width:11%">Input</th>';
      html += '<th style="width:11%">Output</th>';
      html += '<th>Summary</th>';
      html += '<th style="width:120px">Actions</th>';
      html += '</tr></thead><tbody>';
      for (const e of _state.items) {
        const topics = (e.topic_coverage || []).length;
        const sourceBadge = _sourceCategoryBadge(e.source_category);
        html += '<tr data-id="' + escAttr(e.library_id) + '">';
        html += '<td><strong>' + esc(e.title) + '</strong>'
              + (topics ? '<br><span style="font-size:11px;color:var(--text2)" class="mono">' + topics + ' topic' + (topics === 1 ? '' : 's') + '</span>' : '')
              + '</td>';
        html += '<td><span class="badge badge-blue">' + esc(e.prompt_type) + '</span> ' + sourceBadge + '</td>';
        html += '<td><span class="mono" style="font-size:12px">' + esc(e.domain) + '</span></td>';
        html += '<td style="font-size:13px">' + esc(e.input_type || '—') + '</td>';
        html += '<td style="font-size:13px">' + esc(e.output_type || '—') + '</td>';
        html += '<td style="font-size:13px;color:var(--text2)">' + esc(e.summary || '—');
        if (e.classification_notes) {
          html += ' <a style="color:var(--accent);cursor:pointer;font-size:11px" class="lib-why" data-id="' + escAttr(e.library_id) + '">why?</a>';
        }
        html += '</td>';
        html += '<td>'
              + '<button class="btn btn-outline btn-sm lib-edit" data-id="' + escAttr(e.library_id) + '">Edit</button> '
              + '<button class="btn btn-outline btn-sm lib-delete" data-id="' + escAttr(e.library_id) + '">Delete</button>'
              + '</td>';
        html += '</tr>';
        html += '<tr class="lib-detail-row" data-id="' + escAttr(e.library_id) + '" style="display:none"><td colspan="7" style="background:var(--surface2);padding:16px"><div id="lib-detail-' + escAttr(e.library_id) + '"></div></td></tr>';
      }
      html += '</tbody></table>';
      html += '</div>';

      html += '<div class="pagination">';
      html += '<button class="btn btn-outline btn-sm" id="lib-prev"' + (_state.page <= 1 ? ' disabled' : '') + '>&larr; Prev</button>';
      html += '<span style="align-self:center;color:var(--text2);font-size:13px">Page ' + _state.page + '</span>';
      html += '<button class="btn btn-outline btn-sm" id="lib-next"' + (!_state.hasNext ? ' disabled' : '') + '>Next &rarr;</button>';
      html += '</div>';
    }

    el.innerHTML = html;
    _wireHandlers();
  }

  function _wireHandlers() {
    document.getElementById('lib-new-btn').onclick = () => _openEditor(null);
    document.getElementById('lib-filter-type').onchange = (e) => {
      _state.promptType = e.target.value;
      _state.page = 1;
      _refresh();
    };
    document.getElementById('lib-filter-domain').onchange = (e) => {
      _state.domain = e.target.value;
      _state.page = 1;
      _refresh();
    };
    const prev = document.getElementById('lib-prev');
    const next = document.getElementById('lib-next');
    if (prev) prev.onclick = () => { _state.page = Math.max(1, _state.page - 1); _refresh(); };
    if (next) next.onclick = () => { _state.page += 1; _refresh(); };

    document.querySelectorAll('.lib-edit').forEach(btn => {
      btn.onclick = () => _openEditor(btn.dataset.id);
    });
    document.querySelectorAll('.lib-delete').forEach(btn => {
      btn.onclick = () => _confirmDelete(btn.dataset.id);
    });
    document.querySelectorAll('.lib-why').forEach(a => {
      a.onclick = () => _toggleDetail(a.dataset.id);
    });
  }

  async function _refresh() {
    try {
      await _loadPage();
      _render();
    } catch (e) { toast(e.message, 'error'); }
  }

  function _sourceCategoryBadge(category) {
    // Server-derived category lives on entry.source_category. Older list
    // payloads predating the field render no badge — graceful fallback.
    if (!category) return '';
    const colour = category === 'Internal' ? 'badge-green'
                 : category === 'Public'   ? 'badge-blue'
                 : 'badge-purple';
    return '<span class="badge ' + colour + '" title="Source: ' + escAttr(category) + '">' + esc(category) + '</span>';
  }

  function _toggleDetail(id) {
    const row = document.querySelector('.lib-detail-row[data-id="' + CSS.escape(id) + '"]');
    const entry = _state.items.find(x => x.library_id === id);
    if (!row || !entry) return;
    if (row.style.display === 'none') {
      const host = document.getElementById('lib-detail-' + id);
      host.innerHTML = '<div style="font-size:13px;color:var(--text2);line-height:1.7">'
        + '<strong style="color:var(--text)">Why these tags?</strong><br>'
        + esc(entry.classification_notes || '—')
        + (entry.source_provenance ? '<br><br><strong style="color:var(--text)">Source:</strong> ' + esc(entry.source_provenance) : '')
        + (entry.topic_coverage && entry.topic_coverage.length ? '<br><br><strong style="color:var(--text)">Topic coverage:</strong> <span class="mono" style="font-size:12px">' + entry.topic_coverage.map(esc).join(', ') + '</span>' : '')
        + '</div>';
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  }

  function _openEditor(id) {
    const entry = id ? _state.items.find(x => x.library_id === id) : null;
    const el = document.getElementById('view-library');
    const isEdit = !!entry;
    let html = '<h2 style="margin-bottom:16px">' + (isEdit ? 'Edit' : 'New') + ' library entry</h2>';
    html += '<div class="card">';
    html += _formGroup('Title', '<input type="text" id="lib-f-title" value="' + escAttr(entry ? entry.title : '') + '">');
    html += _formGroup('Full prompt text', '<textarea id="lib-f-full" style="min-height:220px">' + esc(entry ? entry.full_text : '') + '</textarea>');
    html += _formGroup('Summary (one sentence)', '<input type="text" id="lib-f-summary" value="' + escAttr(entry ? (entry.summary || '') : '') + '">');

    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">';
    html += _formGroup('Prompt type', _select('lib-f-type', PROMPT_TYPES, entry ? entry.prompt_type : ''));
    html += _formGroup('Domain', _select('lib-f-domain', DOMAINS, entry ? entry.domain : 'general'));
    html += _formGroup('Input type', '<input type="text" id="lib-f-input" value="' + escAttr(entry ? (entry.input_type || '') : '') + '">');
    html += '</div>';

    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';
    html += _formGroup('Output type', '<input type="text" id="lib-f-output" value="' + escAttr(entry ? (entry.output_type || '') : '') + '">');
    html += _formGroup('Source / provenance', '<input type="text" id="lib-f-source" value="' + escAttr(entry ? (entry.source_provenance || '') : '') + '">');
    html += '</div>';

    html += _formGroup('Topic coverage (comma-separated topic_ids)',
      '<input type="text" id="lib-f-topics" placeholder="topic_6_data_points, topic_7_field_format" value="'
      + escAttr(entry ? (entry.topic_coverage || []).join(', ') : '') + '">');
    html += _formGroup('Classification notes (rationale)', '<textarea id="lib-f-notes" style="min-height:80px">' + esc(entry ? (entry.classification_notes || '') : '') + '</textarea>');

    html += '<div style="display:flex;gap:8px;margin-top:16px">';
    html += '<button class="btn btn-primary" id="lib-save">' + (isEdit ? 'Save changes' : 'Create entry') + '</button>';
    html += '<button class="btn btn-outline" id="lib-cancel">Cancel</button>';
    html += '</div>';
    html += '</div>';
    el.innerHTML = html;

    document.getElementById('lib-cancel').onclick = () => viewInits.library();
    document.getElementById('lib-save').onclick = () => _saveEntry(isEdit ? entry.library_id : null);
  }

  function _formGroup(label, control) {
    return '<div class="form-group"><label>' + esc(label) + '</label>' + control + '</div>';
  }

  function _select(id, options, current) {
    let h = '<select id="' + id + '">';
    for (const o of options) {
      h += '<option value="' + escAttr(o) + '"' + (o === current ? ' selected' : '') + '>' + esc(o) + '</option>';
    }
    h += '</select>';
    return h;
  }

  async function _saveEntry(id) {
    const payload = {
      title: document.getElementById('lib-f-title').value.trim(),
      full_text: document.getElementById('lib-f-full').value,
      summary: document.getElementById('lib-f-summary').value.trim() || null,
      prompt_type: document.getElementById('lib-f-type').value,
      domain: document.getElementById('lib-f-domain').value,
      input_type: document.getElementById('lib-f-input').value.trim() || null,
      output_type: document.getElementById('lib-f-output').value.trim() || null,
      source_provenance: document.getElementById('lib-f-source').value.trim() || null,
      topic_coverage: document.getElementById('lib-f-topics').value
        .split(',').map(s => s.trim()).filter(Boolean),
      classification_notes: document.getElementById('lib-f-notes').value.trim() || null,
    };
    if (!payload.title) { toast('Title required', 'error'); return; }
    if (!payload.full_text.trim()) { toast('Full text required', 'error'); return; }

    try {
      if (id) {
        await api('/library/' + id, { method: 'PATCH', body: payload });
        toast('Entry updated');
      } else {
        await api('/library', { method: 'POST', body: payload });
        toast('Entry created');
      }
      viewInits.library();
    } catch (e) { toast(e.message, 'error'); }
  }

  async function _confirmDelete(id) {
    const entry = _state.items.find(x => x.library_id === id);
    if (!entry) return;
    if (!confirm('Delete library entry "' + entry.title + '"? This cannot be undone.')) return;
    try {
      await api('/library/' + id, { method: 'DELETE' });
      toast('Entry deleted');
      await _refresh();
    } catch (e) { toast(e.message, 'error'); }
  }
})();
