(function () {
  function formatInr(value) {
    var n = Math.round(Number(value) || 0);
    return '₹ ' + n.toLocaleString('en-IN');
  }

  function formatDateLabel(value) {
    var text = String(value || '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var parts = text.split('-');
    return Number(parts[2]) + ' ' + months[Number(parts[1]) - 1] + ' ' + parts[0];
  }

  function pad2(n) {
    n = String(n);
    return n.length < 2 ? '0' + n : n;
  }

  function formatValue(value, format) {
    if (value == null || value === '') return '—';
    if (format === 'percent') {
      return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 }) + '%';
    }
    if (format === 'number') {
      return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 });
    }
    if (format === 'kg') return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 }) + ' kg';
    if (format === 'cm') return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 }) + ' cm';
    if (format === 'kcal') return Number(value).toLocaleString('en-IN') + ' kcal';
    if (format === 'date') return formatDateLabel(value);
    if (format === 'text') return String(value);
    return formatInr(value);
  }

  function formatByType(value, format) {
    if (format === 'inr') return formatInr(value);
    if (format === 'percent') return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + '%';
    if (format === 'years') return Number(value) + ' years';
    if (format === 'kg') return Number(value) + ' kg';
    if (format === 'cm') return Number(value) + ' cm';
    if (format === 'kcal') return Number(value) + ' kcal';
    return String(value);
  }

  function readConfig() {
    var el = document.getElementById('calc-config');
    if (!el) return null;
    return JSON.parse(el.textContent);
  }

  function collectInputs(config) {
    var inputs = {};
    (config.fields || []).forEach(function (field) {
      if (field.type === 'radio') {
        var checked = document.querySelector('input[name="' + field.id + '"]:checked');
        inputs[field.id] = checked ? checked.value : field.current;
      } else if (field.type === 'select' || field.type === 'date' || field.type === 'number') {
        var sel = document.querySelector('[name="' + field.id + '"]');
        inputs[field.id] = sel ? sel.value : field.current;
      } else {
        var range = document.getElementById('f-' + field.id);
        inputs[field.id] = range ? range.value : field.current;
      }
    });
    return inputs;
  }

  function resolveEngine(slug) {
    var engines = window.PACalcEngines || {};
    if (engines[slug]) return engines[slug];
    if (slug && slug.slice(-12) !== '-calculator' && engines[slug + '-calculator']) {
      return engines[slug + '-calculator'];
    }
    if (slug && slug.slice(-12) === '-calculator' && engines[slug.slice(0, -12)]) {
      return engines[slug.slice(0, -12)];
    }
    return null;
  }

  var chart;
  var period = 'monthly';

  function setError(message) {
    var err = document.getElementById('calc-error');
    if (!err) return;
    if (message) {
      err.hidden = false;
      err.textContent = message;
    } else {
      err.hidden = true;
      err.textContent = '';
    }
  }

  function renderResults(config, result) {
    var outputs = config.outputs || {};
    var primaryKey = outputs.primary && outputs.primary.key;
    if (outputs.period_toggle && outputs.period_keys) {
      primaryKey = outputs.period_keys[period] || primaryKey;
    }
    var labelEl = document.getElementById('primary-label');
    var valueEl = document.getElementById('primary-value');
    if (labelEl) {
      if (outputs.period_toggle) {
        labelEl.textContent = period === 'yearly' ? 'Estimated yearly premium' : 'Estimated monthly premium';
      } else {
        labelEl.textContent = (outputs.primary && outputs.primary.label) || 'Result';
      }
    }
    var primaryFormat = (outputs.primary && outputs.primary.format) || 'inr';
    if (valueEl) valueEl.textContent = formatValue(result[primaryKey], primaryFormat);

    var rowsEl = document.getElementById('result-rows');
    if (rowsEl) {
      rowsEl.innerHTML = (outputs.rows || []).map(function (row) {
        return '<li><span>' + row.label + '</span><strong>' + formatValue(result[row.key], row.format || 'inr') + '</strong></li>';
      }).join('');
    }

    var slices = outputs.chart_slices || [];
    var wrap = document.getElementById('chart-wrap');
    if (!wrap || outputs.chart === 'none' || !slices.length || typeof Chart === 'undefined') {
      if (wrap && (outputs.chart === 'none' || !slices.length)) wrap.style.display = 'none';
      return;
    }
    wrap.style.display = '';

    var data = slices.map(function (s) { return Number(result[s.key]) || 0; });
    var labels = slices.map(function (s) { return s.label; });
    var colors = slices.map(function (s) { return s.color || '#273c8e'; });
    try {
      if (chart) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = data;
        chart.data.datasets[0].backgroundColor = colors;
        chart.update();
        return;
      }
      var canvas = document.getElementById('calc-chart');
      if (!canvas) return;
      chart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels: labels, datasets: [{ data: data, backgroundColor: colors, borderWidth: 0 }] },
        options: {
          plugins: { legend: { labels: { color: '#334155', boxWidth: 10, font: { size: 11 } } } },
          cutout: '64%',
          maintainAspectRatio: false
        }
      });
    } catch (err) {
      wrap.style.display = 'none';
    }
  }

  function recalc(config) {
    var engine = resolveEngine(config.slug);
    if (!engine) {
      setError('This calculator did not load. Refresh the page (Ctrl+F5) to clear a cached script.');
      return;
    }
    try {
      var result = engine(collectInputs(config));
      setError('');
      renderResults(config, result);
    } catch (err) {
      setError('Could not calculate with the current inputs.');
      if (typeof console !== 'undefined') console.error(err);
    }
  }

  function bind(config) {
    var form = document.getElementById('calc-form');
    if (!form) return;

    form.querySelectorAll('input[type="date"]').forEach(function (el) {
      if (!el.value) {
        var now = new Date();
        el.value = now.getFullYear() + '-' + pad2(now.getMonth() + 1) + '-' + pad2(now.getDate());
      }
    });

    form.addEventListener('input', function (e) {
      var twin = e.target.getAttribute('data-twin');
      if (twin) {
        var range = document.getElementById('f-' + twin);
        if (range) range.value = e.target.value;
      } else if (e.target.type === 'range') {
        var num = form.querySelector('[data-twin="' + e.target.name + '"]');
        if (num) num.value = e.target.value;
      }
      recalc(config);
    });
    form.addEventListener('change', function () { recalc(config); });

    document.querySelectorAll('.toggle-premium-period').forEach(function (btn) {
      btn.addEventListener('click', function () {
        period = btn.getAttribute('data-period');
        document.querySelectorAll('.toggle-premium-period').forEach(function (b) {
          b.classList.toggle('active', b === btn);
        });
        recalc(config);
      });
    });

    document.querySelectorAll('[data-min-label], [data-max-label]').forEach(function (el) {
      var format = el.getAttribute('data-format');
      el.textContent = formatByType(el.textContent.trim(), format);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var config = readConfig();
    if (!config) return;
    bind(config);
    recalc(config);
  });
})();
