(function () {
  function roundRupee(value) {
    var n = Number(value);
    if (!isFinite(n)) return 0;
    return Math.round(n);
  }

  // Compact Indian rupees: 2800000 → "₹ 28.00 L". Always two decimals.
  // K = thousand, L = lakh, Cr = crore. 100 of a smaller unit steps up.
  function formatInr(value) {
    var n = roundRupee(value);
    var sign = n < 0 ? '\u2212' : '';
    var abs = Math.abs(n);
    var scales = [
      { div: 10000000, suffix: 'Cr' },
      { div: 100000, suffix: 'L' },
      { div: 1000, suffix: 'K' }
    ];
    var i;
    for (i = 0; i < scales.length; i++) {
      if (abs >= scales[i].div) {
        var text = (abs / scales[i].div).toFixed(2);
        if (text === '100.00' && i > 0) {
          text = (abs / scales[i - 1].div).toFixed(2);
          return sign + '₹ ' + text + ' ' + scales[i - 1].suffix;
        }
        return sign + '₹ ' + text + ' ' + scales[i].suffix;
      }
    }
    return sign + '₹ ' + abs.toFixed(2);
  }

  function formatInrExact(value) {
    var n = roundRupee(value);
    var sign = n < 0 ? '\u2212' : '';
    return sign + '₹ ' + Math.abs(n).toLocaleString('en-IN');
  }

  function inrExactTitle(value) {
    if (!/ (K|L|Cr)$/.test(formatInr(value))) return '';
    return formatInrExact(value);
  }

  function chartTooltipLabel(ctx) {
    var raw = ctx.parsed;
    if (raw && typeof raw === 'object') raw = raw.y != null ? raw.y : raw.x;
    var line = (ctx.label ? ctx.label + ': ' : '') + formatInr(raw);
    var exact = inrExactTitle(raw);
    return exact ? line + ' (' + exact + ')' : line;
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

  var INR_CAP = 9990000000;

  function fieldById(config, id) {
    var fields = config.fields || [];
    var i;
    for (i = 0; i < fields.length; i++) {
      if (fields[i].id === id) return fields[i];
    }
    return null;
  }

  function fieldLimits(field) {
    var min = Number(field.min);
    var max = Number(field.max);
    if (field.format === 'inr' && (!isFinite(max) || max > INR_CAP)) max = INR_CAP;
    return { min: min, max: max };
  }

  function clampFieldNumber(field, raw) {
    var limits = fieldLimits(field);
    var n = Number(raw);
    if (field.format === 'inr') n = Math.round(n);
    if (!isFinite(n)) n = isFinite(limits.min) ? limits.min : 0;
    if (isFinite(limits.min) && n < limits.min) n = limits.min;
    if (isFinite(limits.max) && n > limits.max) n = limits.max;
    return n;
  }

  function sanitizeNumeric(input, field, commit) {
    var limits = fieldLimits(field);
    var raw = String(input.value);
    if (field.format === 'inr') {
      var body = raw;
      if (/e/i.test(body)) {
        var sci = Number(body);
        body = isFinite(sci) ? String(Math.trunc(Math.abs(sci))) : '';
      }
      var digits = body.replace(/\D/g, '').slice(0, 10);
      if (digits.length > 1) digits = digits.replace(/^0+/, '');
      if (!digits) {
        if (commit && isFinite(limits.min)) input.value = String(limits.min);
        return;
      }
      var n = Number(digits);
      if (n > limits.max) n = limits.max;
      if (commit && isFinite(limits.min) && n < limits.min) n = limits.min;
      var next = String(Math.round(n));
      if (input.value !== next) input.value = next;
      return;
    }
    if (raw === '' || raw === '-' || raw === '.' || raw === '-.') {
      if (commit && isFinite(limits.min)) input.value = String(limits.min);
      return;
    }
    var n2 = Number(raw);
    if (!isFinite(n2)) {
      if (commit && isFinite(limits.min)) input.value = String(limits.min);
      return;
    }
    if (isFinite(limits.max) && n2 > limits.max) input.value = String(limits.max);
    else if (commit && isFinite(limits.min) && n2 < limits.min) input.value = String(limits.min);
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
        var typed = document.querySelector('[data-twin="' + field.id + '"]');
        var range = document.getElementById('f-' + field.id);
        var raw = typed && String(typed.value) !== '' ? typed.value : (range ? range.value : field.current);
        inputs[field.id] = clampFieldNumber(field, raw);
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
    if (valueEl) {
      valueEl.textContent = formatValue(result[primaryKey], primaryFormat);
      if (primaryFormat === 'inr') {
        var exactPrimary = inrExactTitle(result[primaryKey]);
        if (exactPrimary) valueEl.title = exactPrimary;
        else valueEl.removeAttribute('title');
      } else {
        valueEl.removeAttribute('title');
      }
    }

    var rowsEl = document.getElementById('result-rows');
    if (rowsEl) {
      rowsEl.innerHTML = (outputs.rows || []).map(function (row) {
        var format = row.format || 'inr';
        var exact = format === 'inr' ? inrExactTitle(result[row.key]) : '';
        var titleAttr = exact ? ' title="' + exact + '"' : '';
        return '<li><span>' + row.label + '</span><strong' + titleAttr + '>' + formatValue(result[row.key], format) + '</strong></li>';
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
          plugins: {
            legend: { labels: { color: '#334155', boxWidth: 10, font: { size: 11 } } },
            tooltip: { callbacks: { label: chartTooltipLabel } }
          },
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

    form.addEventListener('keydown', function (e) {
      var twin = e.target.getAttribute && e.target.getAttribute('data-twin');
      if (!twin) return;
      var field = fieldById(config, twin);
      if (!field || field.type === 'radio' || field.type === 'select' || field.type === 'date') return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === 'e' || e.key === 'E' || e.key === '+' || e.key === '-') {
        e.preventDefault();
        return;
      }
      if (field.format === 'inr' && e.key === '.') {
        e.preventDefault();
        return;
      }
      if (field.format === 'inr' && /^\d$/.test(e.key)) {
        var start = e.target.selectionStart || 0;
        var end = e.target.selectionEnd || 0;
        if (start !== end) return;
        var digits = String(e.target.value || '').replace(/\D/g, '');
        var ceiling = fieldLimits(field).max;
        if (digits.length >= 10 || Number(e.target.value) >= ceiling) e.preventDefault();
      }
    });

    form.addEventListener('input', function (e) {
      var twin = e.target.getAttribute('data-twin');
      if (twin) {
        var field = fieldById(config, twin);
        if (field) sanitizeNumeric(e.target, field, false);
        var range = document.getElementById('f-' + twin);
        if (range && e.target.value !== '') range.value = e.target.value;
      } else if (e.target.type === 'range') {
        var num = form.querySelector('[data-twin="' + e.target.name + '"]');
        if (num) num.value = e.target.value;
      }
      recalc(config);
    });
    form.addEventListener('change', function () { recalc(config); });
    form.addEventListener('focusout', function (e) {
      var twin = e.target.getAttribute && e.target.getAttribute('data-twin');
      if (!twin) return;
      var field = fieldById(config, twin);
      if (field) sanitizeNumeric(e.target, field, true);
      var range = document.getElementById('f-' + twin);
      if (range && e.target.value !== '') range.value = e.target.value;
      recalc(config);
    });

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
