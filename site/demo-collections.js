(function () {
  var SAMPLE = [
    { Client: 'Acme Manufacturing', InvoiceAmount: 45000, DueDate: '2026-01-15', DaysPastDue: 55, PaymentHistory: 'Late 3 of last 5' },
    { Client: 'TechPro Solutions', InvoiceAmount: 28500, DueDate: '2026-02-01', DaysPastDue: 38, PaymentHistory: 'Late 1 of last 5' },
    { Client: 'Global Logistics Inc', InvoiceAmount: 67000, DueDate: '2025-12-20', DaysPastDue: 81, PaymentHistory: 'Late 4 of last 5' },
    { Client: 'Riverside Healthcare', InvoiceAmount: 32000, DueDate: '2026-02-15', DaysPastDue: 24, PaymentHistory: 'On time 5 of 5' },
    { Client: 'Metro Construction', InvoiceAmount: 18500, DueDate: '2026-01-30', DaysPastDue: 40, PaymentHistory: 'Late 2 of last 5' },
    { Client: 'Pacific Energy Corp', InvoiceAmount: 55000, DueDate: '2025-12-01', DaysPastDue: 100, PaymentHistory: 'Late 5 of last 5' },
    { Client: 'Summit Financial', InvoiceAmount: 22000, DueDate: '2026-02-20', DaysPastDue: 19, PaymentHistory: 'On time 4 of 5' },
    { Client: 'Beacon Pharma', InvoiceAmount: 41000, DueDate: '2026-01-10', DaysPastDue: 60, PaymentHistory: 'Late 3 of last 5' },
    { Client: 'Allied Services Group', InvoiceAmount: 15800, DueDate: '2026-02-28', DaysPastDue: 11, PaymentHistory: 'On time 5 of 5' },
    { Client: 'Northwind Industries', InvoiceAmount: 73000, DueDate: '2025-11-15', DaysPastDue: 116, PaymentHistory: 'Late 4 of last 5' },
    { Client: 'Coastal Telecom', InvoiceAmount: 19200, DueDate: '2026-02-10', DaysPastDue: 29, PaymentHistory: 'Late 1 of last 5' },
    { Client: 'Delta Aerospace', InvoiceAmount: 88000, DueDate: '2026-01-05', DaysPastDue: 65, PaymentHistory: 'Late 2 of last 5' },
    { Client: 'Pinnacle Retail', InvoiceAmount: 11500, DueDate: '2026-03-01', DaysPastDue: 10, PaymentHistory: 'On time 3 of 5' },
    { Client: 'Horizon Media', InvoiceAmount: 34000, DueDate: '2026-01-20', DaysPastDue: 50, PaymentHistory: 'Late 3 of last 5' },
    { Client: 'Atlas Distribution', InvoiceAmount: 26500, DueDate: '2026-02-05', DaysPastDue: 34, PaymentHistory: 'Late 2 of last 5' }
  ];

  function parseHistory(hist) {
    var match = (hist || '').match(/(\d+)\s+of\s+(?:last\s+)?(\d+)/);
    if (!match) return 0;
    if (hist.toLowerCase().indexOf('on time') >= 0) return (parseInt(match[2]) - parseInt(match[1])) / parseInt(match[2]);
    return parseInt(match[1]) / parseInt(match[2]);
  }

  function analyze(rows) {
    return rows.map(function (r) {
      var amount = parseFloat(r.InvoiceAmount) || 0;
      var dpd = parseInt(r.DaysPastDue) || 0;
      var lateRatio = parseHistory(r.PaymentHistory);

      var riskScore = 0;
      if (dpd > 90) riskScore += 40; else if (dpd > 60) riskScore += 30; else if (dpd > 30) riskScore += 20; else riskScore += 5;
      riskScore += Math.round(lateRatio * 35);
      if (amount > 50000) riskScore += 15; else if (amount > 25000) riskScore += 10; else riskScore += 5;
      riskScore = Math.min(riskScore, 100);

      var risk = riskScore >= 65 ? 'high' : riskScore >= 35 ? 'medium' : 'low';

      var action, escalation;
      if (risk === 'high') {
        escalation = 'Tier 3 — Executive';
        action = dpd > 90 ? 'Legal hold review + CFO escalation' : 'Direct outreach from VP collections';
      } else if (risk === 'medium') {
        escalation = 'Tier 2 — Manager';
        action = dpd > 45 ? 'Formal demand letter + payment plan offer' : 'Phone follow-up with AP contact';
      } else {
        escalation = 'Tier 1 — Automated';
        action = 'Automated reminder email sequence';
      }

      var projectedRecovery = risk === 'high' ? amount * 0.65 : risk === 'medium' ? amount * 0.85 : amount * 0.95;

      return {
        Client: r.Client || 'Unknown',
        InvoiceAmount: amount,
        DaysPastDue: dpd,
        PaymentHistory: r.PaymentHistory || '',
        riskScore: riskScore,
        risk: risk,
        escalation: escalation,
        action: action,
        projectedRecovery: projectedRecovery,
        priority: riskScore
      };
    }).sort(function (a, b) { return b.priority - a.priority; });
  }

  function run(rows) {
    document.getElementById('input-section').style.display = 'block';
    DemoUtils.renderTable('input-table',
      [{ key: 'Client', label: 'Client' }, { label: 'Amount', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount); } }, { key: 'DueDate', label: 'Due Date' }, { label: 'Days Past Due', render: function (r) { return r.DaysPastDue; } }, { key: 'PaymentHistory', label: 'History' }],
      rows
    );

    DemoUtils.runProcessing('processing',
      ['Loading AR aging data...', 'Analyzing payment history...', 'Scoring client risk profiles...', 'Calculating recovery projections...', 'Prioritizing collection queue...', 'Assigning escalation tiers...'],
      function () {
        var results = analyze(rows);
        var totalAR = results.reduce(function (s, r) { return s + r.InvoiceAmount; }, 0);
        var totalRecovery = results.reduce(function (s, r) { return s + r.projectedRecovery; }, 0);
        var highRisk = results.filter(function (r) { return r.risk === 'high'; });
        var avgDPD = Math.round(results.reduce(function (s, r) { return s + r.DaysPastDue; }, 0) / results.length);

        DemoUtils.renderSummary('summary', [
          { value: DemoUtils.fmt(totalAR), label: 'Total AR Outstanding' },
          { value: highRisk.length, label: 'High Risk Accounts', type: highRisk.length > 0 ? 'alert' : '' },
          { value: avgDPD + ' days', label: 'Avg Days Past Due', type: 'warn' },
          { value: DemoUtils.fmt(totalRecovery), label: 'Projected Recovery' }
        ]);

        DemoUtils.renderTable('results-table',
          [
            { label: '#', render: function (r, i) { return i + 1; } },
            { key: 'Client', label: 'Client' },
            { label: 'Amount', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount); } },
            { label: 'DPD', render: function (r) { return r.DaysPastDue + 'd'; } },
            { label: 'Risk', render: function (r) { return DemoUtils.badge(r.risk) + ' <small>' + r.riskScore + '/100</small>'; } },
            { key: 'escalation', label: 'Escalation' },
            { key: 'action', label: 'Recommended Action' },
            { label: 'Proj. Recovery', render: function (r) { return DemoUtils.fmt(r.projectedRecovery); } }
          ],
          results
        );

        document.getElementById('results').classList.add('active');
        document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    );
  }

  document.getElementById('btn-sample').addEventListener('click', function () { run(SAMPLE); });
  var fileInput = document.getElementById('file-input');
  document.getElementById('btn-upload').addEventListener('click', function () { DemoUtils.gateUpload(fileInput); });
  fileInput.addEventListener('change', function () {
    if (this.files.length) DemoUtils.parseFile(this.files[0], function (err, rows) { if (err) { alert(err); return; } run(rows); });
  });
})();
