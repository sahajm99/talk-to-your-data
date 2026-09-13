/* Talk To Your Data: client script. No build step, no dependencies. */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
  var root = document.documentElement;

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'text') { node.textContent = attrs[k]; }
        else if (attrs[k] !== null && attrs[k] !== undefined) { node.setAttribute(k, attrs[k]); }
      });
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) { return; }
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function formatNumber(n) {
    try { return Number(n).toLocaleString('en-US'); } catch (e) { return String(n); }
  }

  function passages(n) {
    return formatNumber(n) + (Number(n) === 1 ? ' passage' : ' passages');
  }

  /* Previews are the first 240 characters of a passage; mark the cut when it lands mid-sentence. */
  function previewText(s) {
    var text = String(s || '').replace(/\s*\n\s*/g, ' ').trim();
    if (text.length >= 230 && !/[.!?"”’)\]]$/.test(text)) { text += '…'; }
    return text;
  }

  function formatLatency(ms) {
    if (typeof ms !== 'number' || !isFinite(ms)) { return ''; }
    return ms < 1000 ? Math.round(ms) + ' ms' : (ms / 1000).toFixed(1) + ' s';
  }

  function submitForm(form) {
    if (typeof form.requestSubmit === 'function') { form.requestSubmit(); }
    else { form.dispatchEvent(new Event('submit', { cancelable: true })); }
  }

  /* ---------- theme ---------- */

  var toggle = $('#theme-toggle');

  function currentTheme() {
    var set = root.getAttribute('data-theme');
    if (set === 'light' || set === 'dark') { return set; }
    return prefersDark.matches ? 'dark' : 'light';
  }

  function labelToggle() {
    if (!toggle) { return; }
    var next = currentTheme() === 'dark' ? 'light' : 'dark';
    toggle.setAttribute('data-next', next);
    toggle.setAttribute('aria-label', 'Switch to ' + next + ' mode');
    var label = $('.theme-toggle__label', toggle);
    if (label) { label.textContent = next === 'dark' ? 'Dark mode' : 'Light mode'; }
  }

  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('ttyd-theme', next); } catch (e) { /* storage may be unavailable */ }
      labelToggle();
    });
    if (prefersDark.addEventListener) { prefersDark.addEventListener('change', labelToggle); }
    labelToggle();
  }

  /* ---------- ask page ---------- */

  var form = $('#ask-form');
  if (!form) { return; }

  var body = document.body;
  var questionInput = $('#question');
  var askButton = $('#ask-button');
  var modeDetails = $('#mode');
  var modeCurrent = $('#mode-current');
  var docList = $('#doc-list');
  var uploadInput = $('#upload-input');
  var uploadStatus = $('#upload-status');
  var statusEl = $('#status');
  var errorEl = $('#error');
  var readingEl = $('#reading');
  var answerEl = $('#answer');
  var citationsEl = $('#citations');
  var retrievalEl = $('#retrieval');
  var maxUploadMb = parseFloat(body.getAttribute('data-max-upload-mb')) || 2;
  var maxUploadBytes = Math.round(maxUploadMb * 1000000);
  var maxUploadLabel = String(Number(maxUploadMb.toFixed(2))) + ' MB';

  var state = { citations: [], busy: false };

  function setStatus(text, busy) {
    statusEl.textContent = text;
    statusEl.classList.toggle('is-busy', !!busy);
  }

  function showError(text) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }

  function clearError() {
    errorEl.textContent = '';
    errorEl.hidden = true;
  }

  function setBusy(busy) {
    state.busy = busy;
    askButton.disabled = busy;
    readingEl.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  /* Reads FastAPI's {detail: ...} body, whatever shape it takes. */
  function readDetail(res) {
    return res.json().then(function (j) {
      if (!j) { return ''; }
      if (typeof j.detail === 'string') { return j.detail; }
      if (Array.isArray(j.detail) && j.detail.length && j.detail[0].msg) { return j.detail[0].msg; }
      if (typeof j.message === 'string') { return j.message; }
      return '';
    }).catch(function () { return ''; });
  }

  function trimStop(s) { return String(s || '').trim().replace(/[.!]+$/, ''); }

  function httpErrorMessage(res, detail) {
    switch (res.status) {
      case 429:
        return 'Too many questions for now' + (detail ? ': ' + trimStop(detail) : '') + '. Try again in a few minutes.';
      case 400:
        return detail ? trimStop(detail) + '.' : 'The question could not be read. Type a question of up to 500 characters.';
      case 404:
        return 'One of the selected documents is no longer available; uploads are deleted after an hour. The document list has been refreshed.';
      case 413:
        return 'That file is larger than ' + maxUploadLabel + '. Choose a smaller file.';
      case 415:
        return 'That file type is not supported. Upload a PDF, Word, text or Markdown file.';
      case 422:
        return detail ? trimStop(detail) + '.' : 'The request was not understood. Check the question and try again.';
      default:
        if (res.status >= 500) { return 'Something went wrong on the server. Try again in a moment.'; }
        return detail ? trimStop(detail) + '.' : 'The server answered with status ' + res.status + '.';
    }
  }

  /* ---------- documents ---------- */

  function docItem(doc, checked) {
    var mine = doc.scope && doc.scope !== 'preloaded';
    var li = el('li', { 'class': 'doc' + (mine ? ' doc--mine' : ''), 'data-id': doc.id });
    var label = el('label', { 'class': 'doc__label' });
    var input = el('input', { 'class': 'doc__check', type: 'checkbox', name: 'document_ids', value: doc.id });
    input.checked = checked;
    label.appendChild(input);
    label.appendChild(el('span', { 'class': 'doc__title', text: doc.title || doc.id }));
    label.appendChild(el('span', { 'class': 'doc__meta', text: passages(doc.n_chunks) + (mine ? ', yours' : '') }));
    li.appendChild(label);
    return li;
  }

  function checkedIds() {
    return $$('input[name="document_ids"]:checked', docList).map(function (i) { return i.value; });
  }

  function renderDocuments(docs) {
    var wasChecked = {};
    var seen = {};
    $$('input[name="document_ids"]', docList).forEach(function (i) { seen[i.value] = true; wasChecked[i.value] = i.checked; });
    docList.innerHTML = '';
    if (!docs.length) {
      docList.appendChild(el('li', { 'class': 'doc-list__empty', text: 'No documents are loaded yet. Upload one below to start asking.' }));
      return;
    }
    docs.forEach(function (d) {
      docList.appendChild(docItem(d, seen[d.id] ? wasChecked[d.id] : true));
    });
  }

  function refreshDocuments() {
    return fetch('/api/documents', { headers: { 'Accept': 'application/json' } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (docs) { if (Array.isArray(docs)) { renderDocuments(docs); } })
      .catch(function () { /* the list on screen stays as it was */ });
  }

  function addDocument(doc) {
    var empty = $('.doc-list__empty', docList);
    if (empty) { empty.remove(); }
    $$('li[data-id]', docList).forEach(function (li) {
      if (li.getAttribute('data-id') === String(doc.id)) { li.remove(); }
    });
    docList.appendChild(docItem(doc, true));
  }

  function setUploadStatus(text, isError) {
    uploadStatus.textContent = text;
    uploadStatus.classList.toggle('is-error', !!isError);
  }

  if (uploadInput) {
    uploadInput.addEventListener('change', function () {
      var file = uploadInput.files && uploadInput.files[0];
      if (!file) { return; }
      if (file.size > maxUploadBytes) {
        setUploadStatus(file.name + ' is ' + (file.size / 1000000).toFixed(1) + ' MB; the limit is ' + maxUploadLabel + '.', true);
        uploadInput.value = '';
        return;
      }
      setUploadStatus('Uploading ' + file.name + '…');
      var fd = new FormData();
      fd.append('file', file, file.name);
      fetch('/api/upload', { method: 'POST', body: fd })
        .then(function (res) {
          if (!res.ok) {
            return readDetail(res).then(function (detail) { setUploadStatus(httpErrorMessage(res, detail), true); });
          }
          return res.json().then(function (doc) {
            addDocument(doc);
            setUploadStatus('Added ' + (doc.title || file.name) + ', ' + passages(doc.n_chunks) + '. It is checked and stays for an hour.');
            return refreshDocuments();
          });
        })
        .catch(function () { setUploadStatus('Could not reach the server. Check your connection and try again.', true); })
        .then(function () { uploadInput.value = ''; });
    });
  }

  /* ---------- mode ---------- */

  if (modeDetails) {
    modeDetails.addEventListener('change', function (e) {
      if (e.target && e.target.name === 'mode') { modeCurrent.textContent = e.target.value; }
    });
  }

  function currentMode() {
    var checked = $('input[name="mode"]:checked', form);
    return checked ? checked.value : 'hybrid';
  }

  /* ---------- ask ---------- */

  questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      submitForm(form);
    }
  });

  var tryBox = $('#try');
  if (tryBox) {
    tryBox.addEventListener('click', function (e) {
      var b = e.target.closest('.try__item');
      if (!b) { return; }
      questionInput.value = b.textContent.trim();
      questionInput.focus();
      submitForm(form);
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (state.busy) { return; }
    var question = questionInput.value.trim();
    clearError();
    if (!question) {
      showError('Type a question first.');
      questionInput.focus();
      return;
    }
    if (question.length > 500) {
      showError('Questions are limited to 500 characters; this one is ' + question.length + '.');
      return;
    }
    var ids = checkedIds();
    if (!ids.length) {
      showError('Pick at least one document to search.');
      return;
    }
    ask(question, ids, currentMode());
  });

  function ask(question, ids, mode) {
    setBusy(true);
    setStatus('Thinking…', true);
    fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ question: question, document_ids: ids, mode: mode })
    })
      .then(function (res) {
        if (!res.ok) {
          return readDetail(res).then(function (detail) {
            showError(httpErrorMessage(res, detail));
            setStatus('');
            if (res.status === 404) { refreshDocuments(); }
          });
        }
        return res.json().then(render);
      })
      .catch(function () {
        showError('Could not reach the server. Check your connection and try again.');
        setStatus('');
      })
      .then(function () { setBusy(false); });
  }

  /* ---------- rendering ---------- */

  function statusText(data) {
    var latency = formatLatency(data.latency_ms);
    if (data.mode === 'groq') {
      return 'Written by ' + (data.model || 'a Groq model') + ' on Groq from the passages below' + (latency ? ', in ' + latency : '') + '.';
    }
    return 'Extractive mode, no generation model: the best-supported passage, with your words highlighted' + (latency ? ', in ' + latency : '') + '.';
  }

  function render(data) {
    state.citations = Array.isArray(data.citations) ? data.citations : [];
    renderAnswer(data);
    renderCitations(state.citations);
    renderRetrieval(Array.isArray(data.retrieval) ? data.retrieval : [], state.citations);
    setStatus(statusText(data));
    readingEl.classList.add('has-answer');
  }

  /* Turns "[2]" and "[1, 3]" into buttons, for numbers that exist as citations. */
  function linkCitations(html, count) {
    return html.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g, function (whole, inner) {
      var nums = inner.split(/\s*,\s*/).map(Number);
      if (!nums.every(function (n) { return n >= 1 && n <= count; })) { return whole; }
      return nums.map(function (n) {
        return '<button type="button" class="cite-ref" data-n="' + n + '" aria-label="Go to cited passage ' + n + '">[' + n + ']</button>';
      }).join('');
    });
  }

  function paragraphs(html) {
    return html.split(/\n\s*\n/).map(function (p) {
      return '<p>' + p.replace(/\s*\n\s*/g, ' ').trim() + '</p>';
    }).join('');
  }

  function renderAnswer(data) {
    var raw = typeof data.answer === 'string' ? data.answer : '';
    /* The server escapes extractive answers itself and adds <mark>; anything else is plain text. */
    var html = data.mode === 'extractive' ? raw : escapeHtml(raw);
    var lead = 'Best-supported passage:';
    if (data.mode === 'extractive' && html.indexOf(lead) === 0) {
      html = '<span class="answer__lead">' + lead + '</span>' + html.slice(lead.length);
    }
    html = linkCitations(html, state.citations.length);
    answerEl.innerHTML = html.trim() ? paragraphs(html) : '<p class="empty">The model returned an empty answer. Try rephrasing the question.</p>';
  }

  /* Keeps paragraph breaks, joins the hard-wrapped lines of plain-text sources. */
  function flowText(s) {
    return String(s || '').replace(/[ \t]*\n[ \t]*\n[ \t\n]*/g, '\n\n').replace(/([^\n])\n(?!\n)/g, '$1 ');
  }

  function citeItem(c) {
    var li = el('li', { 'class': 'cite', id: 'cite-' + c.n, tabindex: '-1', 'data-chunk': c.chunk_id });
    li.appendChild(el('span', { 'class': 'cite__n', text: String(c.n), 'aria-label': 'Passage ' + c.n }));
    li.appendChild(el('div', { 'class': 'cite__head' }, [
      el('span', { 'class': 'cite__doc', text: c.doc_title || c.doc_id }),
      el('span', { 'class': 'cite__idx', text: 'passage ' + c.idx })
    ]));
    li.appendChild(el('p', { 'class': 'cite__text', text: flowText(c.text) }));
    return li;
  }

  function renderCitations(cites) {
    citationsEl.innerHTML = '';
    if (!cites.length) {
      citationsEl.appendChild(el('li', { 'class': 'empty', text: 'The answer did not cite a passage. The passages the search found are listed below.' }));
      return;
    }
    cites.forEach(function (c) { citationsEl.appendChild(citeItem(c)); });
  }

  /* Bar lengths relative to the best hit. BM25 from SQLite is negative (lower is better), so use magnitudes then. */
  function barWidths(hits) {
    var scores = hits.map(function (h) { return Number(h.score); }).filter(isFinite);
    if (!scores.length) { return hits.map(function () { return 0; }); }
    var allPositive = scores.every(function (s) { return s > 0; });
    var max = Math.max.apply(null, scores.map(function (s) { return allPositive ? s : Math.abs(s); }));
    if (!max) { return hits.map(function () { return 0; }); }
    return hits.map(function (h) {
      var s = Number(h.score);
      if (!isFinite(s)) { return 0; }
      return Math.max(4, Math.round(((allPositive ? s : Math.abs(s)) / max) * 100));
    });
  }

  function formatScore(s) {
    var n = Number(s);
    if (!isFinite(n)) { return ''; }
    return Math.abs(n) >= 10 ? n.toFixed(2) : n.toFixed(4);
  }

  function hitItem(h, rank, width, citedAs) {
    var via = Array.isArray(h.via) ? h.via : [];
    var both = via.indexOf('keyword') !== -1 && via.indexOf('vector') !== -1;
    var badgeName = both ? 'both' : (via[0] || 'unknown');
    var ranks = [];
    if (h.keyword_rank !== null && h.keyword_rank !== undefined) { ranks.push('keyword rank ' + h.keyword_rank); }
    if (h.vector_rank !== null && h.vector_rank !== undefined) { ranks.push('vector rank ' + h.vector_rank); }

    var line = el('div', { 'class': 'hit__line' }, [
      el('span', { 'class': 'hit__doc', text: h.doc_title || '' }),
      el('span', { 'class': 'hit__idx', text: 'passage ' + h.idx }),
      el('span', { 'class': 'badge badge--' + badgeName, text: badgeName }),
      ranks.length ? el('span', { 'class': 'hit__ranks', text: ranks.join(', ') }) : null
    ]);
    if (citedAs) {
      line.appendChild(el('span', { 'class': 'hit__cited' }, [
        'cited as ',
        el('button', { type: 'button', 'class': 'cite-ref', 'data-n': citedAs, 'aria-label': 'Go to cited passage ' + citedAs, text: '[' + citedAs + ']' })
      ]));
    }

    var bar = el('span', { 'class': 'bar', 'aria-hidden': 'true' }, [el('span', { 'class': 'bar__fill', style: 'width:' + width + '%' })]);
    var score = el('div', { 'class': 'hit__score' }, [bar, el('span', { 'class': 'hit__num', text: 'score ' + formatScore(h.score) })]);

    var li = el('li', { 'class': 'hit' });
    li.appendChild(el('span', { 'class': 'hit__rank', text: String(rank), 'aria-label': 'Rank ' + rank }));
    li.appendChild(el('div', { 'class': 'hit__main' }, [
      line,
      score,
      el('p', { 'class': 'hit__preview', text: previewText(h.preview) })
    ]));
    return li;
  }

  function renderRetrieval(hits, cites) {
    retrievalEl.innerHTML = '';
    if (!hits.length) {
      retrievalEl.appendChild(el('li', { 'class': 'empty', text: 'The search found no passages for this question in the selected documents.' }));
      return;
    }
    var citedBy = {};
    cites.forEach(function (c) { if (!(c.chunk_id in citedBy)) { citedBy[c.chunk_id] = c.n; } });
    var widths = barWidths(hits);
    hits.forEach(function (h, i) {
      retrievalEl.appendChild(hitItem(h, i + 1, widths[i], citedBy[h.chunk_id]));
    });
  }

  /* ---------- citation jump: the one moment of motion ---------- */

  function goToCitation(n) {
    var target = document.getElementById('cite-' + n);
    if (!target) { return; }
    $$('.cite.is-current', citationsEl).forEach(function (x) { x.classList.remove('is-current'); });
    target.classList.remove('is-lit');
    void target.offsetWidth; /* restart the ring animation */
    target.classList.add('is-current');
    target.classList.add('is-lit');
    target.scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'center' });
    target.focus({ preventScroll: true });
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('.cite-ref');
    if (!b) { return; }
    goToCitation(Number(b.getAttribute('data-n')));
  });
})();
