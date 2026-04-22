var DemoUtils = (function () {
  var BOOKING = 'https://meetings-na2.hubspot.com/chris-scowden';
  var HS_PORTAL = '245521589';
  var HS_FORM = window.SA_HS_FORM_GUID || '33eb4c23-f577-486b-bd43-806fe31ddf01';

  function submitToHubSpot(data, context) {
    if (!HS_FORM) return;
    var parts = (data.name || '').split(' ');
    var fields = [
      { name: 'email', value: data.email },
      { name: 'firstname', value: parts[0] || '' },
      { name: 'lastname', value: parts.slice(1).join(' ') || '' },
      { name: 'company', value: data.company || '' }
    ];
    var payload = {
      fields: fields,
      context: {
        pageUri: window.location.href,
        pageName: document.title
      }
    };
    try {
      fetch('https://api.hsforms.com/submissions/v3/integration/submit/' + HS_PORTAL + '/' + HS_FORM, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (e) { /* silent — tracking code is backup */ }
  }

  function fmt(n) {
    return '$' + Math.round(n).toLocaleString('en-US');
  }

  function pct(n) {
    return (n * 100).toFixed(1) + '%';
  }

  // ---- File Parsing (requires SheetJS loaded) ----
  function parseFile(file, cb) {
    var reader = new FileReader();
    reader.onload = function (e) {
      try {
        var wb = XLSX.read(e.target.result, { type: 'array' });
        var sheet = wb.Sheets[wb.SheetNames[0]];
        var rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
        cb(null, rows);
      } catch (err) {
        cb('Could not parse file. Please upload a CSV or Excel (.xlsx) file.');
      }
    };
    reader.readAsArrayBuffer(file);
  }

  // ---- Email Gate Modal ----
  function createGateModal() {
    if (document.getElementById('demo-gate-overlay')) return;
    var overlay = document.createElement('div');
    overlay.id = 'demo-gate-overlay';
    overlay.className = 'demo-modal-overlay';
    overlay.innerHTML =
      '<div class="demo-modal" style="position:relative">' +
        '<button class="demo-modal-close" id="gate-close">&times;</button>' +
        '<h3>Upload Your Own Data</h3>' +
        '<p>Enter your details to unlock file upload. Your data never leaves your browser.</p>' +
        '<form id="gate-form">' +
          '<input type="text" name="name" placeholder="Full Name" required>' +
          '<input type="email" name="email" placeholder="Work Email" required>' +
          '<input type="text" name="company" placeholder="Company Name" required>' +
          '<button type="submit" class="btn btn-primary btn-block">Continue to Upload</button>' +
        '</form>' +
      '</div>';
    document.body.appendChild(overlay);

    document.getElementById('gate-close').addEventListener('click', function () {
      overlay.classList.remove('active');
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) overlay.classList.remove('active');
    });
  }

  function gateUpload(fileInput, onReady) {
    var stored = null;
    try { stored = JSON.parse(localStorage.getItem('sa_demo_lead')); } catch (e) {}

    if (stored && stored.email) {
      fileInput.click();
      return;
    }

    createGateModal();
    var overlay = document.getElementById('demo-gate-overlay');
    overlay.classList.add('active');

    var form = document.getElementById('gate-form');
    form.onsubmit = function (e) {
      e.preventDefault();
      var data = { name: form.name.value, email: form.email.value, company: form.company.value, ts: Date.now() };
      try { localStorage.setItem('sa_demo_lead', JSON.stringify(data)); } catch (err) {}
      submitToHubSpot(data, 'demo_upload_gate');
      var _hsq = window._hsq = window._hsq || [];
      var parts = data.name.split(' ');
      _hsq.push(['identify', { email: data.email, firstname: parts[0], lastname: parts.slice(1).join(' '), company: data.company }]);
      _hsq.push(['trackPageView']);
      overlay.classList.remove('active');
      fileInput.click();
      if (onReady) onReady(data);
    };
  }

  // ---- Table Renderer ----
  function renderTable(containerId, columns, rows) {
    var wrap = document.getElementById(containerId);
    if (!wrap) return;
    var html = '<table class="demo-table"><thead><tr>';
    columns.forEach(function (col) { html += '<th>' + col.label + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function (row, idx) {
      html += '<tr>';
      columns.forEach(function (col) {
        var val = col.render ? col.render(row, idx) : (row[col.key] != null ? row[col.key] : '');
        html += '<td>' + val + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }

  // ---- Summary Cards ----
  function renderSummary(containerId, cards) {
    var wrap = document.getElementById(containerId);
    if (!wrap) return;
    var html = '';
    cards.forEach(function (c) {
      var cls = c.type === 'alert' ? ' alert' : c.type === 'warn' ? ' warn' : '';
      html += '<div class="demo-summary-card' + cls + '"><span class="demo-summary-num">' + c.value + '</span><span class="demo-summary-label">' + c.label + '</span></div>';
    });
    wrap.innerHTML = html;
  }

  // ---- Processing Animation ----
  function runProcessing(containerId, steps, onDone) {
    var el = document.getElementById(containerId);
    if (!el) { onDone(); return; }
    el.classList.add('active');
    var fill = el.querySelector('.demo-progress-fill');
    var stepEl = el.querySelector('.demo-step');
    var total = steps.length;
    var i = 0;

    function next() {
      if (i >= total) {
        fill.style.width = '100%';
        setTimeout(function () { el.classList.remove('active'); onDone(); }, 300);
        return;
      }
      fill.style.width = ((i + 1) / total * 100) + '%';
      stepEl.textContent = steps[i];
      i++;
      setTimeout(next, 400 + Math.random() * 300);
    }
    next();
  }

  // ---- Severity Badge ----
  function badge(level) {
    return '<span class="badge-' + level + '">' + level + '</span>';
  }

  function badgeMatch() {
    return '<span class="badge-match">match</span>';
  }

  return {
    BOOKING: BOOKING,
    fmt: fmt,
    pct: pct,
    parseFile: parseFile,
    gateUpload: gateUpload,
    renderTable: renderTable,
    renderSummary: renderSummary,
    runProcessing: runProcessing,
    badge: badge,
    badgeMatch: badgeMatch
  };
})();
