const state = {
  runs: [],
  currentRun: null,
  currentPageIndex: 0,
  filteredPages: [],
  showBacks: false,
  image: null,
  annotations: [],
  imageWidth: 0,
  imageHeight: 0,
  drawing: false,
  pendingRect: null,
  startPoint: null,
  dirty: false,
  fieldOrder: [
    'name',
    'hp',
    'evolves_from',
    'ability_name',
    'ability_text',
    'attacks',
    'set_code',
    'set_name',
    'card_number',
    'artist',
    'weakness',
    'resistance',
    'retreat',
    'notes',
  ],
};

const elements = {
  runList: document.getElementById('run-list'),
  refreshRuns: document.getElementById('refresh-runs'),
  runInfo: document.getElementById('run-info'),
  pageSelect: document.getElementById('page-select'),
  labelSelect: document.getElementById('label-select'),
  noteInput: document.getElementById('note-input'),
  clearPage: document.getElementById('clear-page'),
  undoButton: document.getElementById('undo-annotation'),
  saveButton: document.getElementById('save-annotations'),
  toggleBacks: document.getElementById('toggle-backs'),
  prevPage: document.getElementById('prev-page'),
  nextPage: document.getElementById('next-page'),
  canvas: document.getElementById('card-canvas'),
  tableBody: document.getElementById('annotation-table'),
  annotationCount: document.getElementById('annotation-count'),
};

const ctx = elements.canvas.getContext('2d');

const feedbackState = {
  queue: [],
  current: null,
  image: null,
  box: null,
  drawing: false,
  start: null,
  canvasWidth: 0,
  canvasHeight: 0,
};

const feedbackElements = {
  modal: document.getElementById('feedback-modal'),
  title: document.getElementById('feedback-title'),
  subtitle: document.getElementById('feedback-subtitle'),
  canvas: document.getElementById('feedback-canvas'),
  valueInput: document.getElementById('feedback-value'),
  drawButton: document.getElementById('feedback-draw'),
  saveButton: document.getElementById('feedback-save'),
  skipButton: document.getElementById('feedback-skip'),
};
const feedbackCtx = feedbackElements.canvas ? feedbackElements.canvas.getContext('2d') : null;

function fetchRuns() {
  fetch('/api/runs')
    .then((res) => res.json())
    .then((runs) => {
      state.runs = Array.isArray(runs) ? runs : [];
      renderRunList();
    })
    .catch((err) => console.error('Failed to load runs', err));
}

function renderRunList() {
  elements.runList.innerHTML = '';
  if (!state.runs.length) {
    const li = document.createElement('li');
    li.textContent = 'No runs yet';
    elements.runList.appendChild(li);
    return;
  }
  state.runs.forEach((run) => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = `${run.run_id} (${run.rows} rows)`;
    btn.dataset.runId = run.run_id;
    if (state.currentRun && state.currentRun.run_id === run.run_id) {
      btn.classList.add('active');
    }
    btn.addEventListener('click', () => selectRun(run.run_id));
    li.appendChild(btn);
    elements.runList.appendChild(li);
  });
}

function selectRun(runId) {
  saveIfDirty();
  fetch(`/api/runs/${encodeURIComponent(runId)}`)
    .then((res) => {
      if (!res.ok) throw new Error('Run not found');
      return res.json();
    })
    .then((run) => {
      state.currentRun = run;
      state.currentPageIndex = 0;
      state.showBacks = false;
      elements.toggleBacks.checked = false;
      elements.runInfo.textContent = `${run.run_id} · ${run.source_name}`;
      updateFilteredPages();
      renderRunList();
      loadPage(state.currentPageIndex);
      fetchLowConfidence(run.run_id);
    })
    .catch((err) => console.error('Failed to load run', err));
}

function updateFilteredPages() {
  if (!state.currentRun || !Array.isArray(state.currentRun.pages)) {
    state.filteredPages = [];
  } else {
    const pages = state.currentRun.pages;
    state.filteredPages = state.showBacks
      ? pages
      : pages.filter((page) => page.index % 2 === 0);
    if (!state.filteredPages.length) {
      state.filteredPages = pages;
    }
  }
  populatePageSelect();
  if (state.currentPageIndex >= state.filteredPages.length) {
    state.currentPageIndex = 0;
  }
  if (elements.pageSelect.options.length) {
    elements.pageSelect.value = String(state.currentPageIndex);
  }
}

function populatePageSelect() {
  elements.pageSelect.innerHTML = '';
  state.filteredPages.forEach((page, idx) => {
    const option = document.createElement('option');
    option.value = String(idx);
    option.textContent = `Page ${page.index}`;
    elements.pageSelect.appendChild(option);
  });
}

function loadPage(pageIndex) {
  if (!state.filteredPages.length) {
    state.annotations = [];
    redrawCanvas();
    renderAnnotationsTable();
    return;
  }
  const idx = Math.max(0, Math.min(pageIndex, state.filteredPages.length - 1));
  state.currentPageIndex = idx;
  elements.pageSelect.value = String(idx);
  const page = state.filteredPages[idx];
  const img = new Image();
  img.onload = () => {
    state.image = img;
    state.imageWidth = img.naturalWidth;
    state.imageHeight = img.naturalHeight;
    elements.canvas.width = state.imageWidth;
    elements.canvas.height = state.imageHeight;
    fetchAnnotations(page.file);
  };
  img.src = `/review/${encodeURIComponent(state.currentRun.run_id)}/images/${encodeURIComponent(page.file)}`;
}

function fetchAnnotations(imageName) {
  if (!state.currentRun) return;
  fetch(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/annotations/${encodeURIComponent(imageName)}`)
    .then((res) => {
      if (!res.ok) throw new Error('Failed to fetch annotations');
      return res.json();
    })
    .then((payload) => {
      state.annotations = Array.isArray(payload.annotations) ? payload.annotations : [];
      state.dirty = false;
      redrawCanvas();
      renderAnnotationsTable();
    })
    .catch((err) => {
      console.error(err);
      state.annotations = [];
      state.dirty = false;
      redrawCanvas();
      renderAnnotationsTable();
    });
}

function redrawCanvas(previewRect = null) {
  ctx.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
  if (state.image) {
    ctx.drawImage(state.image, 0, 0, elements.canvas.width, elements.canvas.height);
  }
  ctx.lineWidth = 2;
  state.annotations.forEach((anno) => {
    if (!anno.box) return;
    const { x, y, w, h } = denormalizeBox(anno.box);
    ctx.strokeStyle = '#facc15';
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = 'rgba(250, 204, 21, 0.18)';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#1e1b4b';
    ctx.font = '16px sans-serif';
    ctx.fillText(anno.label || '?', x + 4, y + 18);
  });
  if (previewRect) {
    ctx.strokeStyle = '#38bdf8';
    ctx.strokeRect(previewRect.x, previewRect.y, previewRect.w, previewRect.h);
  }
}

function renderAnnotationsTable() {
  elements.tableBody.innerHTML = '';
  if (elements.annotationCount) {
    elements.annotationCount.textContent = state.annotations.length;
  }
  state.annotations.forEach((anno, idx) => {
    const tr = document.createElement('tr');
    const cols = [
      idx + 1,
      anno.label || '',
      anno.note || '',
      formatBox(anno.box),
    ];
    cols.forEach((val) => {
      const td = document.createElement('td');
      td.textContent = val;
      tr.appendChild(td);
    });
    const tdActions = document.createElement('td');
    const btn = document.createElement('button');
    btn.textContent = 'Delete';
    btn.className = 'annotation-action';
    btn.addEventListener('click', () => deleteAnnotation(anno.id));
    tdActions.appendChild(btn);
    tr.appendChild(tdActions);
    elements.tableBody.appendChild(tr);
  });
}

function formatBox(box) {
  if (!box) return '';
  const x = (box.x * 100).toFixed(1);
  const y = (box.y * 100).toFixed(1);
  const w = (box.w * 100).toFixed(1);
  const h = (box.h * 100).toFixed(1);
  return `${x}%, ${y}%, ${w}%, ${h}%`;
}

function deleteAnnotation(id) {
  state.annotations = state.annotations.filter((anno) => anno.id !== id);
  redrawCanvas();
  renderAnnotationsTable();
  state.dirty = true;
}

function clearAnnotationsForPage() {
  if (!state.annotations.length) return;
  if (!confirm('Remove all annotations for this page?')) return;
  state.annotations = [];
  redrawCanvas();
  renderAnnotationsTable();
  state.dirty = true;
}

function undoAnnotation() {
  if (!state.annotations.length) return;
  state.annotations.pop();
  redrawCanvas();
  renderAnnotationsTable();
  state.dirty = true;
}

function denormalizeBox(box) {
  return {
    x: box.x * state.imageWidth,
    y: box.y * state.imageHeight,
    w: box.w * state.imageWidth,
    h: box.h * state.imageHeight,
  };
}

function normalizeBox(box) {
  return {
    x: clamp(box.x / state.imageWidth, 0, 1),
    y: clamp(box.y / state.imageHeight, 0, 1),
    w: clamp(box.w / state.imageWidth, 0, 1),
    h: clamp(box.h / state.imageHeight, 0, 1),
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function saveAnnotations() {
  if (!state.currentRun || !state.filteredPages.length) return;
  const page = state.filteredPages[state.currentPageIndex];
  fetch(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/annotations/${encodeURIComponent(page.file)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotations: state.annotations }),
  })
    .then(() => {
      state.dirty = false;
      console.info('Saved annotations');
    })
    .catch((err) => console.error('Failed to save annotations', err));
}

function canvasPoint(evt) {
  const rect = elements.canvas.getBoundingClientRect();
  const scaleX = elements.canvas.width / rect.width;
  const scaleY = elements.canvas.height / rect.height;
  const x = (evt.clientX - rect.left) * scaleX;
  const y = (evt.clientY - rect.top) * scaleY;
  return { x, y };
}

function onCanvasMouseDown(evt) {
  if (!state.image) return;
  state.drawing = true;
  state.startPoint = canvasPoint(evt);
}

function onCanvasMouseMove(evt) {
  if (!state.drawing || !state.startPoint) return;
  const current = canvasPoint(evt);
  const rect = buildRect(state.startPoint, current);
  state.pendingRect = rect;
  redrawCanvas(rect);
}

function onCanvasMouseUp(evt) {
  if (!state.drawing || !state.startPoint) return;
  state.drawing = false;
  const current = canvasPoint(evt);
  const rect = buildRect(state.startPoint, current);
  state.pendingRect = null;
  redrawCanvas();
  if (rect.w < 4 || rect.h < 4) {
    return;
  }
  const label = elements.labelSelect.value;
  const note = elements.noteInput.value.trim();
  const annotation = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    label,
    note,
    box: normalizeBox(rect),
  };
  state.annotations.push(annotation);
  redrawCanvas();
  renderAnnotationsTable();
  state.dirty = true;
  autoAdvanceField();
}

function buildRect(start, end) {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  return { x, y, w, h };
}

function stepPage(delta) {
  if (!state.filteredPages.length) return;
  const nextIdx = (state.currentPageIndex + delta + state.filteredPages.length) % state.filteredPages.length;
  loadPage(nextIdx);
}

function autoAdvanceField() {
  const current = elements.labelSelect.value;
  const idx = state.fieldOrder.indexOf(current);
  if (idx === -1) return;
  const next = state.fieldOrder[(idx + 1) % state.fieldOrder.length];
  elements.labelSelect.value = next;
}

function fetchLowConfidence(runId) {
  if (!feedbackElements.modal) return;
  fetch(`/api/runs/${encodeURIComponent(runId)}/low-confidence`)
    .then((res) => {
      if (!res.ok) throw new Error('Failed to load low-confidence items');
      return res.json();
    })
    .then((payload) => {
      feedbackState.queue = payload.items || [];
      if (feedbackState.queue.length) {
        openFeedbackModal(feedbackState.queue[0]);
      } else {
        closeFeedbackModal();
      }
    })
    .catch((err) => console.error('Low-confidence lookup failed', err));
}

function openFeedbackModal(item) {
  if (!feedbackElements.modal) return;
  feedbackState.current = item;
  feedbackState.box = null;
  feedbackState.drawing = false;
  if (feedbackElements.valueInput) {
    feedbackElements.valueInput.value = item.value || '';
  }
  if (feedbackElements.title) {
    feedbackElements.title.textContent = `Verify ${item.field}`;
  }
  if (feedbackElements.subtitle) {
    const score = item.confidence != null ? Math.round(item.confidence * 100) : '—';
    feedbackElements.subtitle.textContent = `Confidence ${score}%`;
  }
  loadFeedbackImage(item.image_url);
  feedbackElements.modal.hidden = false;
}

function closeFeedbackModal() {
  if (!feedbackElements.modal) return;
  feedbackElements.modal.hidden = true;
  feedbackState.current = null;
  feedbackState.image = null;
  feedbackState.box = null;
}

function loadFeedbackImage(imageUrl) {
  if (!feedbackCtx || !feedbackElements.canvas) return;
  if (!imageUrl) {
    closeFeedbackModal();
    return;
  }
  const img = new Image();
  img.onload = () => {
    feedbackState.image = img;
    feedbackState.canvasWidth = img.naturalWidth;
    feedbackState.canvasHeight = img.naturalHeight;
    feedbackElements.canvas.width = feedbackState.canvasWidth;
    feedbackElements.canvas.height = feedbackState.canvasHeight;
    renderFeedbackCanvas();
  };
  img.src = imageUrl;
}

function renderFeedbackCanvas(preview) {
  if (!feedbackCtx || !feedbackElements.canvas) return;
  feedbackCtx.clearRect(0, 0, feedbackElements.canvas.width, feedbackElements.canvas.height);
  if (feedbackState.image) {
    feedbackCtx.drawImage(
      feedbackState.image,
      0,
      0,
      feedbackElements.canvas.width,
      feedbackElements.canvas.height
    );
  }
  if (feedbackState.box) {
    drawFeedbackBox(feedbackState.box, '#34d399');
  }
  if (preview) {
    drawFeedbackBox(preview, '#38bdf8');
  }
}

function drawFeedbackBox(box, color) {
  if (!feedbackCtx) return;
  feedbackCtx.strokeStyle = color;
  feedbackCtx.lineWidth = 2;
  feedbackCtx.strokeRect(box.x, box.y, box.w, box.h);
  feedbackCtx.fillStyle = `${color}33`;
  feedbackCtx.fillRect(box.x, box.y, box.w, box.h);
}

function onFeedbackMouseDown(evt) {
  if (!feedbackState.image) return;
  feedbackState.drawing = true;
  feedbackState.start = feedbackCanvasPoint(evt);
}

function onFeedbackMouseMove(evt) {
  if (!feedbackState.drawing || !feedbackState.start) return;
  const current = feedbackCanvasPoint(evt);
  const rect = buildRect(feedbackState.start, current);
  renderFeedbackCanvas(rect);
}

function onFeedbackMouseUp(evt) {
  if (!feedbackState.drawing || !feedbackState.start) return;
  feedbackState.drawing = false;
  const current = feedbackCanvasPoint(evt);
  const rect = buildRect(feedbackState.start, current);
  if (rect.w < 4 || rect.h < 4) {
    renderFeedbackCanvas();
    return;
  }
  feedbackState.box = rect;
  renderFeedbackCanvas();
}

function feedbackCanvasPoint(evt) {
  const rect = feedbackElements.canvas.getBoundingClientRect();
  const scaleX = feedbackElements.canvas.width / rect.width;
  const scaleY = feedbackElements.canvas.height / rect.height;
  const x = (evt.clientX - rect.left) * scaleX;
  const y = (evt.clientY - rect.top) * scaleY;
  return { x, y };
}

function submitFeedback(action) {
  if (!feedbackState.current || !state.currentRun) return;
  const payload = {
    page_index: feedbackState.current.page_index,
    image: feedbackState.current.image,
    field: feedbackState.current.field,
    confidence: feedbackState.current.confidence,
    original_value: feedbackState.current.value,
    action,
  };
  if (action === 'save') {
    const value = feedbackElements.valueInput ? feedbackElements.valueInput.value.trim() : '';
    if (!value) {
      alert('Enter a value or use Skip.');
      return;
    }
    payload.value = value;
    if (feedbackState.box) {
      payload.box = normalizeFeedbackBox(feedbackState.box);
    }
  }

  fetch(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then((res) => {
      if (!res.ok) throw new Error('Failed to record feedback');
      advanceFeedbackQueue();
    })
    .catch((err) => alert(err.message));
}

function normalizeFeedbackBox(box) {
  if (!feedbackState.canvasWidth || !feedbackState.canvasHeight) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }
  return {
    x: clamp(box.x / feedbackState.canvasWidth, 0, 1),
    y: clamp(box.y / feedbackState.canvasHeight, 0, 1),
    w: clamp(box.w / feedbackState.canvasWidth, 0, 1),
    h: clamp(box.h / feedbackState.canvasHeight, 0, 1),
  };
}

function advanceFeedbackQueue() {
  if (feedbackState.queue.length) {
    feedbackState.queue.shift();
  }
  if (feedbackState.queue.length) {
    openFeedbackModal(feedbackState.queue[0]);
  } else {
    closeFeedbackModal();
  }
}

if (elements.refreshRuns) {
  elements.refreshRuns.addEventListener('click', fetchRuns);
}
if (elements.pageSelect) {
  elements.pageSelect.addEventListener('change', (evt) => {
    const idx = parseInt(evt.target.value, 10);
    if (!Number.isNaN(idx)) {
      saveIfDirty();
      loadPage(idx);
    }
  });
}
if (elements.clearPage) {
  elements.clearPage.addEventListener('click', () => {
    clearAnnotationsForPage();
  });
}
if (elements.undoButton) {
  elements.undoButton.addEventListener('click', () => {
    undoAnnotation();
  });
}
if (elements.saveButton) {
  elements.saveButton.addEventListener('click', saveAnnotations);
}
if (elements.toggleBacks) {
  elements.toggleBacks.addEventListener('change', () => {
    saveIfDirty();
    state.showBacks = elements.toggleBacks.checked;
    state.currentPageIndex = 0;
    updateFilteredPages();
    loadPage(state.currentPageIndex);
  });
}
if (elements.prevPage) {
  elements.prevPage.addEventListener('click', () => {
    saveIfDirty();
    stepPage(-1);
  });
}
if (elements.nextPage) {
  elements.nextPage.addEventListener('click', () => {
    saveIfDirty();
    stepPage(1);
  });
}

elements.canvas.addEventListener('mousedown', onCanvasMouseDown);
elements.canvas.addEventListener('mousemove', onCanvasMouseMove);
elements.canvas.addEventListener('mouseup', onCanvasMouseUp);
elements.canvas.addEventListener('mouseleave', () => {
  if (state.drawing) {
    state.drawing = false;
    state.pendingRect = null;
    redrawCanvas();
  }
});

fetchRuns();

function saveIfDirty() {
  if (state.dirty) {
    saveAnnotations();
  }
}

if (feedbackElements.canvas && feedbackCtx) {
  feedbackElements.canvas.addEventListener('mousedown', onFeedbackMouseDown);
  feedbackElements.canvas.addEventListener('mousemove', onFeedbackMouseMove);
  feedbackElements.canvas.addEventListener('mouseup', onFeedbackMouseUp);
  feedbackElements.canvas.addEventListener('mouseleave', () => {
    if (feedbackState.drawing) {
      feedbackState.drawing = false;
      renderFeedbackCanvas();
    }
  });
}

if (feedbackElements.drawButton) {
  feedbackElements.drawButton.addEventListener('click', () => {
    feedbackState.box = null;
    renderFeedbackCanvas();
  });
}

if (feedbackElements.saveButton) {
  feedbackElements.saveButton.addEventListener('click', () => submitFeedback('save'));
}

if (feedbackElements.skipButton) {
  feedbackElements.skipButton.addEventListener('click', () => submitFeedback('skip'));
}

if (feedbackElements.canvas && feedbackCtx) {
  feedbackElements.canvas.addEventListener('mousedown', onFeedbackMouseDown);
  feedbackElements.canvas.addEventListener('mousemove', onFeedbackMouseMove);
  feedbackElements.canvas.addEventListener('mouseup', onFeedbackMouseUp);
  feedbackElements.canvas.addEventListener('mouseleave', () => {
    if (feedbackState.drawing) {
      feedbackState.drawing = false;
      renderFeedbackCanvas();
    }
  });
}

if (feedbackElements.drawButton) {
  feedbackElements.drawButton.addEventListener('click', () => {
    feedbackState.box = null;
    renderFeedbackCanvas();
  });
}

if (feedbackElements.saveButton) {
  feedbackElements.saveButton.addEventListener('click', () => submitFeedback('save'));
}

if (feedbackElements.skipButton) {
  feedbackElements.skipButton.addEventListener('click', () => submitFeedback('skip'));
}
