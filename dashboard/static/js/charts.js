// 0DTE Command Centre — Chart.js equity curve + calendar heatmap

var equityChartInstance = null;
var calendarChartInstance = null;

var chartColors = {
  green: '#22c55e',
  red: '#ef4444',
  cyan: '#06b6d4',
  gridLine: 'rgba(30, 41, 59, 0.8)',
  text: '#94a3b8',
  bgPanel: '#111827'
};

Chart.defaults.color = chartColors.text;
Chart.defaults.borderColor = chartColors.gridLine;
Chart.defaults.font.family = "'SF Mono', 'Fira Code', monospace";
Chart.defaults.font.size = 11;

function renderCharts(data) {
  renderEquityCurve(data.equity_curve);
  renderCalendar(data.calendar);
}

function renderEquityCurve(eq) {
  var ctx = document.getElementById('equityChart');
  if (!ctx) return;

  if (equityChartInstance) {
    equityChartInstance.destroy();
  }

  if (!eq || !eq.labels || eq.labels.length === 0) {
    equityChartInstance = new Chart(ctx, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: { plugins: { title: { display: true, text: 'No data', color: chartColors.text } } }
    });
    return;
  }

  // Determine line color based on final value
  var finalVal = eq.values[eq.values.length - 1];
  var lineColor = finalVal >= 0 ? chartColors.green : chartColors.red;
  var fillColor = finalVal >= 0 ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)';

  equityChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: eq.labels,
      datasets: [{
        label: 'Cumulative P/L',
        data: eq.values,
        borderColor: lineColor,
        backgroundColor: fillColor,
        fill: true,
        tension: 0.2,
        pointRadius: eq.labels.length > 30 ? 0 : 3,
        pointHoverRadius: 5,
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var v = ctx.parsed.y;
              return (v >= 0 ? '+' : '') + '$' + v.toFixed(2);
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { maxRotation: 45, maxTicksLimit: 15 },
          grid: { display: false }
        },
        y: {
          ticks: {
            callback: function (v) { return '$' + v.toFixed(0); }
          },
          grid: { color: chartColors.gridLine }
        }
      }
    }
  });
}

function renderCalendar(cal) {
  var ctx = document.getElementById('calendarChart');
  if (!ctx) return;

  if (calendarChartInstance) {
    calendarChartInstance.destroy();
  }

  if (!cal || !cal.labels || cal.labels.length === 0) {
    calendarChartInstance = new Chart(ctx, {
      type: 'bar',
      data: { labels: [], datasets: [] },
      options: { plugins: { title: { display: true, text: 'No data', color: chartColors.text } } }
    });
    return;
  }

  // Color each bar green/red
  var bgColors = cal.values.map(function (v) {
    return v >= 0 ? chartColors.green : chartColors.red;
  });

  calendarChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cal.labels,
      datasets: [{
        label: 'Daily P/L',
        data: cal.values,
        backgroundColor: bgColors,
        borderWidth: 0,
        borderRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var v = ctx.parsed.y;
              return (v >= 0 ? '+' : '') + '$' + v.toFixed(2);
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { maxRotation: 45, maxTicksLimit: 20 },
          grid: { display: false }
        },
        y: {
          ticks: {
            callback: function (v) { return '$' + v.toFixed(0); }
          },
          grid: { color: chartColors.gridLine }
        }
      }
    }
  });
}

// Initial render from server-bootstrapped data
document.addEventListener('DOMContentLoaded', function () {
  if (window.__chartData) {
    renderCharts(window.__chartData);
  }
});
