(function () {
  var SAMPLE = [
    { InvoiceNumber: 'INV-2026-001', PONumber: 'PO-4401', InvoiceAmount: 12500, POAmount: 12500, Vendor: 'Apex Staffing', Date: '2026-03-01' },
    { InvoiceNumber: 'INV-2026-002', PONumber: 'PO-4402', InvoiceAmount: 8750, POAmount: 8200, Vendor: 'Apex Staffing', Date: '2026-03-01' },
    { InvoiceNumber: 'INV-2026-003', PONumber: 'PO-4403', InvoiceAmount: 15300, POAmount: 15300, Vendor: 'CoreStaff Inc', Date: '2026-03-02' },
    { InvoiceNumber: 'INV-2026-004', PONumber: '', InvoiceAmount: 6200, POAmount: 0, Vendor: 'TempForce LLC', Date: '2026-03-03' },
    { InvoiceNumber: 'INV-2026-005', PONumber: 'PO-4405', InvoiceAmount: 22100, POAmount: 22100, Vendor: 'CoreStaff Inc', Date: '2026-03-03' },
    { InvoiceNumber: 'INV-2026-006', PONumber: 'PO-4406', InvoiceAmount: 9800, POAmount: 9500, Vendor: 'PrimeWork Solutions', Date: '2026-03-04' },
    { InvoiceNumber: 'INV-2026-007', PONumber: 'PO-4407', InvoiceAmount: 18400, POAmount: 18400, Vendor: 'PrimeWork Solutions', Date: '2026-03-04' },
    { InvoiceNumber: 'INV-2026-008', PONumber: 'PO-4408', InvoiceAmount: 5500, POAmount: 5500, Vendor: 'TempForce LLC', Date: '2026-03-05' },
    { InvoiceNumber: 'INV-2026-009', PONumber: 'PO-4409', InvoiceAmount: 31200, POAmount: 28000, Vendor: 'Apex Staffing', Date: '2026-03-05' },
    { InvoiceNumber: 'INV-2026-010', PONumber: 'PO-4410', InvoiceAmount: 7600, POAmount: 7600, Vendor: 'CoreStaff Inc', Date: '2026-03-06' },
    { InvoiceNumber: 'INV-2026-011', PONumber: 'PO-4411', InvoiceAmount: 14200, POAmount: 14200, Vendor: 'StaffPlus Group', Date: '2026-03-06' },
    { InvoiceNumber: 'INV-2026-012', PONumber: 'PO-4412', InvoiceAmount: 10500, POAmount: 10500, Vendor: 'StaffPlus Group', Date: '2026-03-07' },
    { InvoiceNumber: 'INV-2026-013', PONumber: 'PO-4413', InvoiceAmount: 19800, POAmount: 17500, Vendor: 'Apex Staffing', Date: '2026-03-07' },
    { InvoiceNumber: 'INV-2026-014', PONumber: 'PO-4414', InvoiceAmount: 8900, POAmount: 8900, Vendor: 'TempForce LLC', Date: '2026-03-08' },
    { InvoiceNumber: 'INV-2026-002', PONumber: 'PO-4402', InvoiceAmount: 8750, POAmount: 8200, Vendor: 'Apex Staffing', Date: '2026-03-08' },
    { InvoiceNumber: 'INV-2026-015', PONumber: 'PO-4415', InvoiceAmount: 11300, POAmount: 11300, Vendor: 'CoreStaff Inc', Date: '2026-03-08' },
    { InvoiceNumber: 'INV-2026-016', PONumber: 'PO-4416', InvoiceAmount: 26500, POAmount: 26500, Vendor: 'PrimeWork Solutions', Date: '2026-03-09' },
    { InvoiceNumber: 'INV-2026-017', PONumber: '', InvoiceAmount: 4100, POAmount: 0, Vendor: 'StaffPlus Group', Date: '2026-03-09' },
    { InvoiceNumber: 'INV-2026-018', PONumber: 'PO-4418', InvoiceAmount: 16700, POAmount: 16700, Vendor: 'Apex Staffing', Date: '2026-03-10' },
    { InvoiceNumber: 'INV-2026-019', PONumber: 'PO-4419', InvoiceAmount: 13400, POAmount: 13400, Vendor: 'TempForce LLC', Date: '2026-03-10' }
  ];

  function analyze(rows) {
    var seen = {};
    return rows.map(function (r) {
      var inv = parseFloat(r.InvoiceAmount) || 0;
      var po = parseFloat(r.POAmount) || 0;
      var poNum = (r.PONumber || '').trim();
      var invNum = (r.InvoiceNumber || '').trim();
      var variance = Math.abs(inv - po);
      var flags = [];

      if (!poNum) flags.push({ type: 'Missing PO', severity: 'high' });
      else if (variance > 0) {
        var pctVar = po > 0 ? variance / po : 1;
        flags.push({ type: 'Amount Mismatch (' + DemoUtils.fmt(variance) + ')', severity: pctVar > 0.1 ? 'high' : 'medium' });
      }

      if (seen[invNum]) flags.push({ type: 'Duplicate Invoice', severity: 'high' });
      seen[invNum] = true;

      var status = flags.length > 0 ? (flags.some(function (f) { return f.severity === 'high'; }) ? 'high' : 'medium') : 'match';

      return {
        InvoiceNumber: invNum,
        PONumber: poNum || 'N/A',
        Vendor: r.Vendor || '',
        InvoiceAmount: inv,
        POAmount: po,
        Variance: variance,
        Date: r.Date || '',
        flags: flags,
        status: status,
        action: flags.length === 0 ? 'Auto-approve' :
                flags.some(function (f) { return f.type === 'Duplicate Invoice'; }) ? 'Reject & investigate' :
                flags.some(function (f) { return f.type === 'Missing PO'; }) ? 'Route to AP for PO creation' :
                'Escalate for review'
      };
    });
  }

  function run(rows) {
    document.getElementById('input-section').style.display = 'block';
    DemoUtils.renderTable('input-table',
      [{ key: 'InvoiceNumber', label: 'Invoice #' }, { key: 'PONumber', label: 'PO #' }, { label: 'Amount', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount); } }, { key: 'Vendor', label: 'Vendor' }, { key: 'Date', label: 'Date' }],
      rows
    );

    DemoUtils.runProcessing('processing',
      ['Loading invoices...', 'Matching to purchase orders...', 'Checking for duplicates...', 'Calculating variances...', 'Classifying discrepancies...', 'Generating recommendations...'],
      function () {
        var results = analyze(rows);
        var matched = results.filter(function (r) { return r.status === 'match'; });
        var flagged = results.filter(function (r) { return r.status !== 'match'; });
        var totalVariance = results.reduce(function (s, r) { return s + r.Variance; }, 0);

        DemoUtils.renderSummary('summary', [
          { value: results.length, label: 'Invoices Processed' },
          { value: matched.length, label: 'Auto-Matched' },
          { value: flagged.length, label: 'Flagged for Review', type: flagged.length > 0 ? 'alert' : '' },
          { value: DemoUtils.fmt(totalVariance), label: 'Total Variance', type: totalVariance > 0 ? 'warn' : '' }
        ]);

        DemoUtils.renderTable('results-table',
          [
            { key: 'InvoiceNumber', label: 'Invoice #' },
            { key: 'Vendor', label: 'Vendor' },
            { label: 'Inv / PO', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount) + ' / ' + DemoUtils.fmt(r.POAmount); } },
            { label: 'Status', render: function (r) { return r.status === 'match' ? DemoUtils.badgeMatch() : DemoUtils.badge(r.status); } },
            { label: 'Flags', render: function (r) { return r.flags.map(function (f) { return f.type; }).join(', ') || '&mdash;'; } },
            { label: 'Action', render: function (r) { return r.action; } }
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
