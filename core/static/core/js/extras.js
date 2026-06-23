// core/static/core/js/extras.js
// Funcionalidad transversal que se carga vía {% block extra_js %} en las páginas
// que la necesitan (NO modifica base.js): buscador del topbar + enlace Configuración.

(function () {
  // ── Estilos del dropdown del buscador (inyectados una sola vez) ──
  const css = `
    .search-dropdown {
      position: absolute; top: calc(100% + 6px); left: 0; right: 0;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; box-shadow: var(--shadow-md);
      max-height: 360px; overflow-y: auto; z-index: 100; display: none; padding: 6px;
    }
    .search-dropdown.show { display: block; }
    .sd-group-label { font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: .06em; color: var(--muted); padding: 8px 10px 4px; }
    .sd-item { display: flex; align-items: center; gap: 9px; padding: 8px 10px;
      border-radius: 7px; cursor: pointer; }
    .sd-item:hover { background: var(--bg); }
    .sd-ico { width: 22px; text-align: center; flex-shrink: 0; }
    .sd-name { font-size: 13px; color: var(--text); flex: 1; }
    .sd-meta { font-size: 11px; color: var(--muted); flex-shrink: 0; }
    .sd-empty { padding: 14px; text-align: center; color: var(--muted); font-size: 12.5px; }
    .topbar-search { position: relative; }
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── Buscador del topbar ──
  const input = document.querySelector('.topbar-search input');
  if (!input) return;

  // Contenedor del dropdown
  const dropdown = document.createElement('div');
  dropdown.className = 'search-dropdown';
  input.closest('.topbar-search').appendChild(dropdown);

  let timer = null;

  // Debounce: esperamos 300ms tras la última tecla antes de buscar
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { ocultar(); return; }
    timer = setTimeout(() => buscar(q), 300);
  });

  // Cerrar el dropdown al hacer click fuera
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.topbar-search')) ocultar();
  });

  function ocultar() { dropdown.classList.remove('show'); dropdown.innerHTML = ''; }

  function buscar(q) {
    fetch('/buscar/?q=' + encodeURIComponent(q))
      .then(r => r.json())
      .then(data => render(data))
      .catch(() => ocultar());
  }

  function render(data) {
    let html = '';

    if (data.tareas && data.tareas.length) {
      html += '<div class="sd-group-label">Tareas</div>';
      data.tareas.forEach(t => {
        html += `<div class="sd-item" data-tipo="tarea" data-id="${t.id}">
                   <span class="sd-ico">📋</span>
                   <span class="sd-name">${escapar(t.nombre)}</span>
                   <span class="sd-meta">${t.hora}</span>
                 </div>`;
      });
    }

    if (data.productos && data.productos.length) {
      html += '<div class="sd-group-label">Productos</div>';
      data.productos.forEach(p => {
        html += `<div class="sd-item" data-tipo="producto" data-id="${p.id}">
                   <span class="sd-ico">📦</span>
                   <span class="sd-name">${escapar(p.nombre)}</span>
                   <span class="sd-meta">S/ ${p.precio}</span>
                 </div>`;
      });
    }

    if (!html) html = '<div class="sd-empty">Sin resultados</div>';

    dropdown.innerHTML = html;
    dropdown.classList.add('show');

    // Click en cada resultado
    dropdown.querySelectorAll('.sd-item').forEach(item => {
      item.addEventListener('click', () => abrirResultado(item.dataset.tipo, item.dataset.id));
    });
  }

  function abrirResultado(tipo, id) {
    if (tipo === 'producto') {
      // Producto → ficha rápida
      window.location.href = '/productos/ficha/' + id + '/';
      return;
    }
    // Tarea → si estamos en el runbook, scroll + expandir; si no, navegar al runbook
    if (typeof window.irATarea === 'function' && document.getElementById('row-' + id)) {
      window.irATarea(parseInt(id));
      ocultar();
    } else {
      window.location.href = '/capacitacion/#row-' + id;
    }
  }

  // Escapa texto para evitar inyección de HTML en los resultados
  function escapar(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
})();

// ── Helpers globales para compartir material (usados en catálogo y ficha rápida) ──

// Abre WhatsApp con el link del medio pre-cargado en el mensaje
window.compartirWhatsApp = function (url) {
  window.open('https://wa.me/?text=' + encodeURIComponent(url), '_blank');
};

// Copia el link de un medio al portapapeles y da feedback en el botón
window.copiarLinkMedio = function (btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    const original = btn.textContent;
    btn.textContent = '✓ Copiado';
    setTimeout(() => { btn.textContent = original; }, 1500);
  });
};
