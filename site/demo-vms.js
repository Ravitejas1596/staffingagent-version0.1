(function () {
  var SAMPLE = [
    { Employee: 'Sarah Chen', TimesheetHours: 40, VMSHours: 40, BillRate: 85, InvoiceAmount: 3400 },
    { Employee: 'Marcus Johnson', TimesheetHours: 45, VMSHours: 40, BillRate: 72, InvoiceAmount: 2880 },
    { Employee: 'Lisa Park', TimesheetHours: 38, VMSHours: 38, BillRate: 95, InvoiceAmount: 3610 },
    { Employee: 'David Wright', TimesheetHours: 40, VMSHours: 40, BillRate: 68, InvoiceAmount: 2720 },
    { Employee: 'Rachel Adams', TimesheetHours: 42, VMSHours: 40, BillRate: 78, InvoiceAmount: 3120 },
    { Employee: 'James Liu', TimesheetHours: 40, VMSHours: 40, BillRate: 110, InvoiceAmount: 4400 },
    { Employee: 'Emily Torres', TimesheetHours: 36, VMSHours: 40, BillRate: 82, InvoiceAmount: 3280 },
    { Employee: 'Michael Brown', TimesheetHours: 40, VMSHours: 38, BillRate: 90, InvoiceAmount: 3600 },
    { Employee: 'Karen White', TimesheetHours: 40, VMSHours: 40, BillRate: 75, InvoiceAmount: 3000 },
    { Employee: 'Tom Nguyen', TimesheetHours: 48, VMSHours: 40, BillRate: 65, InvoiceAmount: 2600 },
    { Employee: 'Anna Patel', TimesheetHours: 40, VMSHours: 40, BillRate: 88, InvoiceAmount: 3520 },
    { Employee: 'Chris Martinez', TimesheetHours: 40, VMSHours: 40, BillRate: 92, InvoiceAmount: 3500 },
    { Employee: 'Jessica Kim', TimesheetHours: 35, VMSHours: 40, BillRate: 105, InvoiceAmount: 4200 },
    { Employee: 'Brian Scott', TimesheetHours: 40, VMSHours: 0, BillRate: 70, InvoiceAmount: 2800 },
    { Employee: 'Nancy Lee', TimesheetHours: 40, VMSHours: 40, BillRate: 85, InvoiceAmount: 3400 },
    { Employee: 'Roberto Silva', TimesheetHours: 44, VMSHours: 40, BillRate: 77, InvoiceAmount: 3080 },
    { Employee: 'Diane Foster', TimesheetHours: 40, VMSHours: 42, BillRate: 98, InvoiceAmount: 3920 },
    { Employee: 'Steve Clark', TimesheetHours: 40, VMSHours: 40, BillRate: 80, InvoiceAmount: 3200 },
    { Employee: 'Megan Hall', TimesheetHours: 40, VMSHours: 40, BillRate: 73, InvoiceAmount: 2920 },
    { Employee: 'Kevin Ross', TimesheetHours: 0, VMSHours: 40, BillRate: 86, InvoiceAmount: 3440 },
    { Employee: 'Sandra Day', TimesheetHours: 40, VMSHours: 40, BillRate: 91, InvoiceAmount: 3640 },
    { Employee: 'Paul Young', TimesheetHours: 40, VMSHours: 39, BillRate: 69, InvoiceAmount: 2760 },
    { Employee: 'Laura Green', TimesheetHours: 43, VMSHours: 40, BillRate: 84, InvoiceAmount: 3360 },
    { Employee: 'Ryan Thomas', TimesheetHours: 40, VMSHours: 40, BillRate: 76, InvoiceAmount: 3040 },
    { Employee: 'Amy Wilson', TimesheetHours: 40, VMSHours: 40, BillRate: 100, InvoiceAmount: 3800 }
  ];

  function analyze(rows) {
    return rows.map(function (r) {
      var ts = parseFloat(r.TimesheetHours) || 0;
      var vms = parseFloat(r.VMSHours) || 0;
      var rate = parseFloat(r.BillRate) || 0;
      var inv = parseFloat(r.InvoiceAmount) || 0;
      var expected = ts * rate;
      var hourDelta = Math.abs(ts - vms);
      var invDelta = Math.abs(inv - expected);
      var flags = [];

      if (vms === 0 && ts > 0) flags.push({ type: 'Missing VMS Record', severity: 'high' });
      else if (ts === 0 && vms > 0) flags.push({ type: 'Missing Timesheet', severity: 'high' });
      if (hourDelta > 0.5) flags.push({ type: 'Hour Mismatch (' + hourDelta.toFixed(1) + 'h)', severity: hourDelta > 4 ? 'high' : 'medium' });
      if (invDelta > rate) flags.push({ type: 'Invoice Variance (' + DemoUtils.fmt(invDelta) + ')', severity: invDelta > rate * 2 ? 'high' : 'medium' });

      return {
        Employee: r.Employee || 'Unknown',
        TimesheetHours: ts,
        VMSHours: vms,
        BillRate: rate,
        InvoiceAmount: inv,
        Expected: expected,
        status: flags.length > 0 ? flags[0].severity : 'match',
        flags: flags,
        valueAtRisk: flags.length > 0 ? Math.max(invDelta, hourDelta * rate) : 0
      };
    });
  }

  function run(rows) {
    document.getElementById('input-section').style.display = 'block';
    DemoUtils.renderTable('input-table',
      [{ key: 'Employee', label: 'Employee' }, { key: 'TimesheetHours', label: 'TS Hours' }, { key: 'VMSHours', label: 'VMS Hours' }, { key: 'BillRate', label: 'Bill Rate', render: function (r) { return DemoUtils.fmt(r.BillRate); } }, { key: 'InvoiceAmount', label: 'Invoice', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount); } }],
      rows
    );

    DemoUtils.runProcessing('processing',
      ['Loading records...', 'Matching timesheets to VMS data...', 'Checking bill rates...', 'Validating invoice amounts...', 'Flagging discrepancies...', 'Calculating value at risk...'],
      function () {
        var results = analyze(rows);
        var flagged = results.filter(function (r) { return r.flags.length > 0; });
        var totalRisk = flagged.reduce(function (s, r) { return s + r.valueAtRisk; }, 0);

        DemoUtils.renderSummary('summary', [
          { value: results.length, label: 'Records Analyzed' },
          { value: flagged.length, label: 'Discrepancies Found', type: flagged.length > 0 ? 'alert' : '' },
          { value: DemoUtils.fmt(totalRisk), label: 'Value at Risk', type: 'warn' },
          { value: DemoUtils.pct(flagged.length / results.length), label: 'Error Rate' }
        ]);

        DemoUtils.renderTable('results-table',
          [
            { key: 'Employee', label: 'Employee' },
            { label: 'TS / VMS', render: function (r) { return r.TimesheetHours + 'h / ' + r.VMSHours + 'h'; } },
            { label: 'Invoice / Expected', render: function (r) { return DemoUtils.fmt(r.InvoiceAmount) + ' / ' + DemoUtils.fmt(r.Expected); } },
            { label: 'Status', render: function (r) { return r.flags.length ? DemoUtils.badge(r.status) : DemoUtils.badgeMatch(); } },
            { label: 'Flags', render: function (r) { return r.flags.map(function (f) { return f.type; }).join(', ') || '&mdash;'; } },
            { label: 'Value at Risk', render: function (r) { return r.valueAtRisk > 0 ? DemoUtils.fmt(r.valueAtRisk) : '&mdash;'; } }
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
  document.getElementById('btn-upload').addEventListener('click', function () {
    DemoUtils.gateUpload(fileInput);
  });
  fileInput.addEventListener('change', function () {
    if (this.files.length) DemoUtils.parseFile(this.files[0], function (err, rows) {
      if (err) { alert(err); return; }
      run(rows);
    });
  });
})();
