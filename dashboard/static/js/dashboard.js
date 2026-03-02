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

// Strategy filter state
window.__selectedStrategy = '';
window.__currentPeriod = 'all';

// Chart update helper (called from period buttons)
function updateCharts(period) {
  window.__currentPeriod = period;
  _fetchChartData(period, window.__selectedStrategy);
}

// Strategy selection (called from strategy table rows)
function selectStrategy(strategy) {
  // Toggle off if clicking the already-selected strategy
  if (window.__selectedStrategy === strategy) {
    strategy = '';
  }
  window.__selectedStrategy = strategy;
  _fetchChartData(window.__currentPeriod, strategy);

  // Update row highlights immediately
  document.querySelectorAll('.strategy-row').forEach(function (row) {
    row.classList.remove('strategy-selected');
  });
  if (strategy) {
    document.querySelectorAll('.strategy-row').forEach(function (row) {
      if (row.querySelector('.badge') && row.querySelector('.badge').textContent.trim() === strategy) {
        row.classList.add('strategy-selected');
      }
    });
  }

  // Update filter label
  var label = document.querySelector('.strategy-filter-label');
  if (strategy) {
    var h3 = document.querySelector('#perf-panel h3');
    if (h3) {
      // Ensure label exists
      if (!label) {
        var span = document.createElement('span');
        span.className = 'strategy-filter-label';
        h3.appendChild(span);
        label = span;
      }
      label.innerHTML = 'Showing: ' + strategy +
        ' <button class="btn-clear-filter" onclick="selectStrategy(\'\')" title="Show all">&times;</button>';
    }
  } else if (label) {
    label.remove();
  }
}

function _fetchChartData(period, strategy) {
  var url = '/api/chart-data?period=' + encodeURIComponent(period);
  if (strategy) {
    url += '&strategy=' + encodeURIComponent(strategy);
  }
  fetch(url)
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
