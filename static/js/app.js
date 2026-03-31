'use strict';

let sessionId = null;
let extractedImages = [];
let editingFilename = null;

// ── Inicialización ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  setupDropZone();
  document.getElementById('process-btn').addEventListener('click', processPdf);
  document.getElementById('download-btn').addEventListener('click', downloadSelected);
  document.getElementById('enhance-btn').addEventListener('click', enhanceImage);
});

// ── Drop Zone ──────────────────────────────────────────────────────────────

function setupDropZone() {
  const zone = document.getElementById('drop-zone');
  const input = document.getElementById('pdf-input');

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelected(file);
  });
  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => { if (input.files[0]) handleFileSelected(input.files[0]); });
}

function handleFileSelected(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    setStatus('upload-status', 'El archivo debe ser un PDF.', 'error');
    return;
  }

  document.getElementById('file-name').textContent = file.name;
  setStatus('upload-status', '<span class="spinner"></span> Subiendo archivo...', 'loading');

  const form = new FormData();
  form.append('pdf', file);

  fetch('/upload', { method: 'POST', body: form })
    .then(r => r.json())
    .then(data => {
      if (data.error) { setStatus('upload-status', data.error, 'error'); return; }
      sessionId = data.session_id;
      setStatus('upload-status', `✅ Archivo subido: <strong>${data.filename}</strong>`, 'success');
      document.getElementById('process-btn').disabled = false;
    })
    .catch(() => setStatus('upload-status', 'Error al subir el archivo.', 'error'));
}

// ── Procesar PDF ───────────────────────────────────────────────────────────

function processPdf() {
  if (!sessionId) return;

  const bgColor = document.getElementById('bg-color').value.replace('#', '');

  const params = {
    session_id: sessionId,
    canvas_size: parseInt(document.getElementById('canvas-size').value),
    background_color: bgColor,
    render_dpi: parseInt(document.getElementById('render-dpi').value),
    remove_bg: document.getElementById('remove-bg').checked,
    no_cv_fallback: !document.getElementById('cv-fallback').checked,
    start_page: parseInt(document.getElementById('start-page').value) || 1,
    end_page: parseInt(document.getElementById('end-page').value) || null,
    min_size: parseInt(document.getElementById('min-size').value) || 500,
    max_per_page: parseInt(document.getElementById('max-per-page').value) || null,
    merge_kernel: parseInt(document.getElementById('merge-kernel').value),
    min_area: parseFloat(document.getElementById('min-area').value),
    white_threshold: parseInt(document.getElementById('white-threshold').value),
    edge_margin: parseFloat(document.getElementById('edge-margin').value),
  };

  const btn = document.getElementById('process-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Procesando...';

  const removeBg = params.remove_bg;
  setStatus('process-status',
    `<span class="spinner"></span> Extrayendo imágenes${removeBg ? ' y removiendo fondos (puede tardar)' : ''}...`,
    'loading'
  );

  document.getElementById('results-section').style.display = 'none';

  fetch('/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
    .then(r => r.json())
    .then(data => {
      btn.disabled = false;
      btn.textContent = '⚙️ Procesar catálogo';

      if (data.error) { setStatus('process-status', data.error, 'error'); return; }

      const s = data.summary;
      setStatus('process-status',
        `✅ ${s.images_found} imágenes extraídas de ${s.pages_processed} páginas.`,
        'success'
      );

      extractedImages = data.images;
      renderGallery(data.session_id, data.images, s);
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = '⚙️ Procesar catálogo';
      setStatus('process-status', 'Error al procesar el PDF.', 'error');
    });
}

// ── Galería ────────────────────────────────────────────────────────────────

function renderGallery(sid, images, summary) {
  const section = document.getElementById('results-section');
  const gallery = document.getElementById('gallery');
  const summaryEl = document.getElementById('results-summary');

  summaryEl.textContent = `${summary.images_found} imágenes · ${summary.pages_processed} páginas`;

  gallery.innerHTML = '';
  images.forEach(img => {
    const item = document.createElement('div');
    item.className = 'gallery-item selected';
    item.dataset.filename = img.filename;

    item.innerHTML = `
      <div class="check-overlay">✓</div>
      <img src="/image/${sid}/${img.filename}" alt="${img.filename}" loading="lazy" />
      <div class="gallery-item-info">Pág. ${img.page} · #${img.index}</div>
      <div class="gallery-item-actions">
        <button class="btn-enhance" onclick="openEditModal('${img.filename}', '/image/${sid}/${img.filename}', event)">✨ IA</button>
        <button class="btn-edit" onclick="toggleSelect(this, event)">☑</button>
      </div>
    `;

    item.addEventListener('click', () => toggleItem(item));
    gallery.appendChild(item);
  });

  section.style.display = '';
}

function toggleItem(item) {
  item.classList.toggle('selected');
  const check = item.querySelector('.check-overlay');
  check.textContent = item.classList.contains('selected') ? '✓' : '';
}

function toggleSelect(btn, e) {
  e.stopPropagation();
  const item = btn.closest('.gallery-item');
  toggleItem(item);
}

function selectAll(val) {
  document.querySelectorAll('.gallery-item').forEach(item => {
    const check = item.querySelector('.check-overlay');
    if (val) { item.classList.add('selected'); check.textContent = '✓'; }
    else { item.classList.remove('selected'); check.textContent = ''; }
  });
}

// ── Descarga ───────────────────────────────────────────────────────────────

function downloadSelected() {
  const selected = [...document.querySelectorAll('.gallery-item.selected')]
    .map(el => el.dataset.filename);

  if (!selected.length) {
    alert('Selecciona al menos una imagen para descargar.');
    return;
  }

  const fmt = document.getElementById('format-select').value;

  fetch('/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, selected, format: fmt }),
  })
    .then(r => {
      const cd = r.headers.get('Content-Disposition') || '';
      const match = cd.match(/filename="?([^"]+)"?/);
      const name = match ? match[1] : `imagenes.${fmt === 'png' ? 'png' : 'zip'}`;
      return r.blob().then(blob => ({ blob, name }));
    })
    .then(({ blob, name }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
    })
    .catch(() => alert('Error al descargar las imágenes.'));
}

// ── Gemini ─────────────────────────────────────────────────────────────────

function openEditModal(filename, imgSrc, e) {
  e.stopPropagation();
  editingFilename = filename;
  document.getElementById('modal-preview-img').src = imgSrc + '?t=' + Date.now();
  document.getElementById('edit-prompt').value = '';
  setStatus('modal-status', '', '');
  document.getElementById('edit-modal').style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('edit-modal').style.display = 'none';
  editingFilename = null;
}

function enhanceImage() {
  if (!editingFilename) return;
  callGemini('/gemini/enhance', { filename: editingFilename });
}

function callGemini(endpoint, extraData) {
  setStatus('modal-status', '<span class="spinner"></span> Mejorando imagen...', 'loading');
  document.getElementById('enhance-btn').disabled = true;

  fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, ...extraData }),
  })
    .then(r => r.json())
    .then(data => {
      document.getElementById('enhance-btn').disabled = false;

      if (data.error) { setStatus('modal-status', data.error, 'error'); return; }

      setStatus('modal-status', '✅ Imagen actualizada.', 'success');
      // Recargar la imagen en modal y galería
      const ts = Date.now();
      const imgEl = document.getElementById('modal-preview-img');
      const base = imgEl.src.split('?')[0];
      imgEl.src = base + '?t=' + ts;

      // Actualizar en galería
      const galleryImg = document.querySelector(`.gallery-item[data-filename="${editingFilename}"] img`);
      if (galleryImg) {
        const gBase = galleryImg.src.split('?')[0];
        galleryImg.src = gBase + '?t=' + ts;
      }
    })
    .catch(() => {
      document.getElementById('enhance-btn').disabled = false;
      setStatus('modal-status', 'Error al mejorar la imagen.', 'error');
    });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function setStatus(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  // Para mensajes de error usar textContent para evitar que HTML se interprete
  if (type === 'error') {
    el.textContent = msg;
  } else {
    el.innerHTML = msg;
  }
  el.className = 'status-msg' + (type ? ' ' + type : '');
}
