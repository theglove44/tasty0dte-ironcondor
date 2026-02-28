// 0DTE Command Centre — Clock + helpers

(function () {
  // UK time clock
  function updateClock() {
    var el = document.getElementById('clock');
    if (!el) return;
    var now = new Date();
    var uk = now.toLocaleString('en-GB', {
      timeZone: 'Europe/London',
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
    el.textContent = uk + ' UK';
  }

  updateClock();
  setInterval(updateClock, 1000);
})();

// Chart update helper (called from period buttons)
function updateCharts(period) {
  fetch('/api/chart-data?period=' + encodeURIComponent(period))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      window.__chartData = data;
      if (typeof renderCharts === 'function') {
        renderCharts(data);
      }
    })
    .catch(function (err) {
      console.error('Chart data fetch failed:', err);
    });
}
