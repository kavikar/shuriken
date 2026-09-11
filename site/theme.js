(function () {
  const saved = localStorage.getItem('vanilla-theme') || 'dark';
  document.documentElement.dataset.theme = saved;
})();
