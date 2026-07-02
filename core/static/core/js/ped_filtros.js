/* Filtros fluidos del módulo Pedidos: filtrado 100% en el navegador (las filas ya vienen
 * en el DOM), sin recargar. Búsqueda en vivo, multi-select, orden y KPIs en vivo.
 * En vistas sin filas filtrables (Avances) cae a submit clásico para no romper su filtrado. */
(function () {
  var form = document.getElementById('pedFiltros');
  if (!form) return;
  var filas = Array.prototype.slice.call(document.querySelectorAll('.js-fila'));

  function $(n) { return form.querySelector('[name=' + n + ']'); }

  // ── Fallback (Avances u otra vista de agregados): submit al cambiar ──
  if (!filas.length) {
    ['fuente', 'estado', 'envio', 'vendedor', 'orden', 'desde', 'hasta'].forEach(function (n) {
      var el = $(n);
      if (el) el.addEventListener('change', function () { form.submit(); });
    });
    document.querySelectorAll('.js-rango').forEach(function (b) {
      b.addEventListener('click', function () {
        var h = document.getElementById('fRango'); if (h) h.value = b.dataset.rango;
        form.submit();
      });
    });
    return;
  }

  // ── Modo instantáneo (Listado / Seguimiento) ──
  function norm(s) { return (s || '').toString().replace(/ /g, ' ').toLowerCase().split(/\s+/).join(' ').trim(); }

  var q = $('q'), fuente = $('fuente'), estado = $('estado'), envio = $('envio'),
      vendedor = $('vendedor'), orden = $('orden'), desde = $('desde'), hasta = $('hasta');
  var hidRango = document.getElementById('fRango');
  var rangoBtns = Array.prototype.slice.call(document.querySelectorAll('.js-rango'));
  var limpiar = form.querySelector('.js-fechas-limpiar');
  var tbody = filas[0].parentNode;

  function prodChecks() { return Array.prototype.slice.call(form.querySelectorAll('input[name=producto]')); }
  function prodSel() { return prodChecks().filter(function (c) { return c.checked; }).map(function (c) { return norm(c.value); }); }

  // ── Fechas ──
  function iso(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function hoyISO() { return iso(new Date()); }
  function isoMenos(dias) { var d = new Date(); d.setDate(d.getDate() - dias); return iso(d); }
  function rangoFechas() {
    if (desde.value || hasta.value) return [desde.value || null, hasta.value || null];
    var r = hidRango ? hidRango.value : 'todo';
    if (r === 'hoy') { var t = hoyISO(); return [t, t]; }
    if (r === '7d') return [isoMenos(6), null];
    if (r === '30d') return [isoMenos(29), null];
    return [null, null];
  }

  function setText(id, val) { var el = document.getElementById(id); if (el) el.textContent = val; }
  function num(v) { var n = parseFloat((v || '').toString().replace(',', '.')); return isNaN(n) ? 0 : n; }
  function estadoDe(r) { var s = r.querySelector('.js-estado'); return s ? s.value : (r.dataset.estado || ''); }

  function recomputarKPIs(visibles) {
    setText('kpiVisibles', visibles.length);
    var confN = 0, confMonto = 0, cobrado = 0, porCobrar = 0;
    visibles.forEach(function (r) {
      var est = estadoDe(r);
      var total = num((r.querySelector('.js-total') || {}).value);
      var adel = num((r.querySelector('.js-adelanto') || {}).value);
      var rest = num((r.querySelector('.js-restante') || {}).textContent);
      if (est === 'confirmado') { confN++; confMonto += total; cobrado += adel; }
      if (est !== 'cancelado') porCobrar += rest;
    });
    setText('kpiConfN', confN);
    setText('kpiConfMonto', confMonto.toFixed(2));
    setText('kpiCobrado', cobrado.toFixed(2));
    setText('kpiPorCobrar', porCobrar.toFixed(2));
  }

  function ordenar(lista) {
    if (!orden) return;
    var k = orden.value;
    function cmp(a, b) { a = a || ''; b = b || ''; return a < b ? -1 : (a > b ? 1 : 0); }
    var arr = filas.slice();
    arr.sort(function (a, b) {
      switch (k) {
        case 'antiguo': return cmp(a.dataset.fecha, b.dataset.fecha);
        case 'cliente': return cmp(a.dataset.nombre, b.dataset.nombre);
        case 'numero': return cmp(a.dataset.numero, b.dataset.numero);
        case 'telefono': return cmp(a.dataset.tel, b.dataset.tel);
        default: return cmp(b.dataset.fecha, a.dataset.fecha);   // reciente
      }
    });
    arr.forEach(function (r) { tbody.appendChild(r); });
  }

  function actualizarBadge(n) {
    var btn = document.getElementById('prodMultiBtn');
    if (btn) btn.innerHTML = '🛍️ Productos' + (n > 0 ? ' <span class="ped-multi-badge">' + n + '</span>' : '') + ' ▾';
  }

  function toggleVacio(hay) {
    var vacio = tbody.querySelector('.js-vacio');
    if (!hay) {
      if (!vacio) {
        vacio = document.createElement('tr'); vacio.className = 'js-vacio';
        var td = document.createElement('td'); td.className = 'integ-vacio-cell';
        td.colSpan = (filas[0].children.length) || 10;
        td.textContent = 'No hay pedidos con estos filtros.';
        vacio.appendChild(td); tbody.appendChild(vacio);
      }
      vacio.style.display = '';
    } else if (vacio) { vacio.style.display = 'none'; }
  }

  function sincronizarURL() {
    var p = new URLSearchParams();
    var v = $('vista'); if (v) p.set('vista', v.value);
    if (q.value.trim()) p.set('q', q.value.trim());
    if (fuente && fuente.value) p.set('fuente', fuente.value);
    if (estado && estado.value) p.set('estado', estado.value);
    if (envio && envio.value) p.set('envio', envio.value);
    if (vendedor && vendedor.value) p.set('vendedor', vendedor.value);
    if (orden && orden.value && orden.value !== 'reciente') p.set('orden', orden.value);
    prodChecks().forEach(function (c) { if (c.checked) p.append('producto', c.value); });
    if (desde.value) p.set('desde', desde.value);
    if (hasta.value) p.set('hasta', hasta.value);
    if (!desde.value && !hasta.value && hidRango && hidRango.value && hidRango.value !== 'todo') p.set('rango', hidRango.value);
    history.replaceState(null, '', '?' + p.toString());
  }

  function aplicar() {
    var texto = norm(q.value);
    var fFuente = fuente ? fuente.value : '';
    var fEstado = estado ? estado.value : '';
    var fEnvio = envio ? norm(envio.value) : '';
    var fVend = vendedor ? vendedor.value : '';
    var sel = prodSel();
    var rf = rangoFechas(), rDesde = rf[0], rHasta = rf[1];
    var visibles = [];

    filas.forEach(function (row) {
      var d = row.dataset, ok = true;
      if (texto && norm(d.nombre + ' ' + d.tel + ' ' + d.numero + ' ' + d.productos).indexOf(texto) === -1) ok = false;
      if (ok && fFuente && d.fuente !== fFuente) ok = false;
      if (ok && fEstado && estadoDe(row) !== fEstado) ok = false;
      if (ok && fEnvio && norm(d.envio) !== fEnvio) ok = false;
      if (ok && fVend && d.vendedor !== fVend) ok = false;
      if (ok && sel.length) {
        var prods = (d.productos || '').split('|').map(norm);
        if (!sel.some(function (s) { return prods.indexOf(s) !== -1; })) ok = false;
      }
      if (ok && (rDesde || rHasta)) {
        var f = d.fecha;
        if (!f || (rDesde && f < rDesde) || (rHasta && f > rHasta)) ok = false;
      }
      row.style.display = ok ? '' : 'none';
      if (ok) visibles.push(row);
    });

    ordenar(visibles);
    recomputarKPIs(visibles);
    actualizarBadge(sel.length);
    toggleVacio(visibles.length > 0);
    sincronizarURL();
  }

  // ── Listeners ──
  form.addEventListener('submit', function (e) { e.preventDefault(); });   // Enter no recarga
  if (q) q.addEventListener('input', aplicar);
  [fuente, estado, envio, vendedor, orden].forEach(function (el) { if (el) el.addEventListener('change', aplicar); });
  prodChecks().forEach(function (c) { c.addEventListener('change', aplicar); });

  var todo = document.getElementById('prodTodo'), ninguno = document.getElementById('prodNinguno');
  if (todo) todo.addEventListener('click', function () {
    prodChecks().forEach(function (c) {
      var opt = c.closest('.ped-multi-opt');
      if (!opt || opt.style.display !== 'none') c.checked = true;   // respeta el buscador de opciones
    });
    aplicar();
  });
  if (ninguno) ninguno.addEventListener('click', function () {
    prodChecks().forEach(function (c) { c.checked = false; });
    aplicar();
  });

  rangoBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      rangoBtns.forEach(function (x) { x.classList.remove('activo'); });
      b.classList.add('activo');
      if (hidRango) hidRango.value = b.dataset.rango;
      if (desde) desde.value = ''; if (hasta) hasta.value = '';
      if (limpiar) limpiar.style.display = 'none';
      aplicar();
    });
  });
  [desde, hasta].forEach(function (inp) {
    if (!inp) return;
    inp.addEventListener('change', function () {
      if (hidRango) hidRango.value = '';
      rangoBtns.forEach(function (x) { x.classList.remove('activo'); });
      if (limpiar) limpiar.style.display = (desde.value || hasta.value) ? '' : 'none';
      aplicar();
    });
  });
  if (limpiar) limpiar.addEventListener('click', function () {
    desde.value = ''; hasta.value = ''; limpiar.style.display = 'none'; aplicar();
  });

  // Recalcular tras editar inline (estado/montos) — disparado desde la plantilla.
  document.addEventListener('ped:recalc', aplicar);

  aplicar();   // estado inicial (aplica lo que venga en la URL / filtros fijados)
})();
