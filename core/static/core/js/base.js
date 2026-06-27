(function () {
  const sidebar     = document.getElementById('sidebar');
  const collapseBtn = document.getElementById('collapseBtn');
  const rightPanel  = document.getElementById('rightPanel');
  const rightToggle = document.getElementById('rightPanelToggle');

  // ── Sidebar collapse
  const SIDEBAR_KEY = 'dash_sidebar_collapsed';
  if (localStorage.getItem(SIDEBAR_KEY) === 'true') {
    sidebar.classList.add('collapsed');
  }
  if (collapseBtn) {
    collapseBtn.addEventListener('click', () => {
      const c = sidebar.classList.toggle('collapsed');
      localStorage.setItem(SIDEBAR_KEY, c);
    });
  }

  // ── Right panel toggle
  const PANEL_KEY = 'dash_panel_collapsed';
  if (localStorage.getItem(PANEL_KEY) === 'true') {
    rightPanel.classList.add('collapsed');
  }
  if (rightToggle) {
    rightToggle.addEventListener('click', () => {
      const c = rightPanel.classList.toggle('collapsed');
      localStorage.setItem(PANEL_KEY, c);
    });
  }

  // ── Ctrl+K search
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      document.querySelector('.topbar-search input')?.focus();
    }
  });
})();