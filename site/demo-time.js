(function () {
  var SAMPLE = [
    { Employee: 'Sarah Chen', Date: '2026-03-03', HoursWorked: 8, Department: 'Accounting', ShiftType: 'Day' },
    { Employee: 'Sarah Chen', Date: '2026-03-04', HoursWorked: 9, Department: 'Accounting', ShiftType: 'Day' },
    { Employee: 'Sarah Chen', Date: '2026-03-05', HoursWorked: 10, Department: 'Accounting', ShiftType: 'Day' },
    { Employee: 'Sarah Chen', Date: '2026-03-06', HoursWorked: 9, Department: 'Accounting', ShiftType: 'Day' },
    { Employee: 'Sarah Chen', Date: '2026-03-07', HoursWorked: 8, Department: 'Accounting', ShiftType: 'Day' },
    { Employee: 'Marcus Johnson', Date: '2026-03-03', HoursWorked: 12, Department: 'Operations', ShiftType: 'Day' },
    { Employee: 'Marcus Johnson', Date: '2026-03-04', HoursWorked: 11, Department: 'Operations', ShiftType: 'Day' },
    { Employee: 'Marcus Johnson', Date: '2026-03-05', HoursWorked: 12, Department: 'Operations', ShiftType: 'Night' },
    { Employee: 'Marcus Johnson', Date: '2026-03-06', HoursWorked: 10, Department: 'Operations', ShiftType: 'Day' },
    { Employee: 'Marcus Johnson', Date: '2026-03-07', HoursWorked: 8, Department: 'Operations', ShiftType: 'Day' },
    { Employee: 'Lisa Park', Date: '2026-03-08', HoursWorked: 10, Department: 'HR', ShiftType: 'Weekend' },
    { Employee: 'Lisa Park', Date: '2026-03-09', HoursWorked: 8, Department: 'HR', ShiftType: 'Weekend' },
    { Employee: 'Lisa Park', Date: '2026-03-03', HoursWorked: 8, Department: 'HR', ShiftType: 'Day' },
    { Employee: 'Lisa Park', Date: '2026-03-04', HoursWorked: 8, Department: 'HR', ShiftType: 'Day' },
    { Employee: 'Lisa Park', Date: '2026-03-05', HoursWorked: 8, Department: 'HR', ShiftType: 'Day' },
    { Employee: 'David Wright', Date: '2026-03-03', HoursWorked: 8, Department: 'IT', ShiftType: 'Day' },
    { Employee: 'David Wright', Date: '2026-03-04', HoursWorked: 8, Department: 'IT', ShiftType: 'Day' },
    { Employee: 'David Wright', Date: '2026-03-05', HoursWorked: 8, Department: 'IT', ShiftType: 'Day' },
    { Employee: 'David Wright', Date: '2026-03-05', HoursWorked: 8, Department: 'IT', ShiftType: 'Night' },
    { Employee: 'David Wright', Date: '2026-03-06', HoursWorked: 8, Department: 'IT', ShiftType: 'Day' },
    { Employee: 'David Wright', Date: '2026-03-07', HoursWorked: 8, Department: 'IT', ShiftType: 'Day' },
    { Employee: 'Rachel Adams', Date: '2026-03-03', HoursWorked: 8, Department: 'Finance', ShiftType: 'Day' },
    { Employee: 'Rachel Adams', Date: '2026-03-04', HoursWorked: 8, Department: 'Finance', ShiftType: 'Day' },
    { Employee: 'Rachel Adams', Date: '2026-03-05', HoursWorked: 8, Department: 'Finance', ShiftType: 'Day' },
    { Employee: 'Rachel Adams', Date: '2026-03-06', HoursWorked: 8, Department: 'Finance', ShiftType: 'Day' },
    { Employee: 'Rachel Adams', Date: '2026-03-07', HoursWorked: 8, Department: 'Finance', ShiftType: 'Day' },
    { Employee: 'James Liu', Date: '2026-03-08', HoursWorked: 12, Department: 'Warehouse', ShiftType: 'Weekend' },
    { Employee: 'James Liu', Date: '2026-03-09', HoursWorked: 10, Department: 'Warehouse', ShiftType: 'Weekend' },
    { Employee: 'James Liu', Date: '2026-03-03', HoursWorked: 8, Department: 'Warehouse', ShiftType: 'Night' },
    { Employee: 'James Liu', Date: '2026-03-04', HoursWorked: 8, Department: 'Warehouse', ShiftType: 'Night' }
  ];

  function analyze(rows) {
    var byEmployee = {};
    rows.forEach(function (r) {
      var name = r.Employee || 'Unknown';
      if (!byEmployee[name]) byEmployee[name] = [];
      byEmployee[name].push(r);
    });

    var results = [];
    Object.keys(byEmployee).forEach(function (name) {
      var entries = byEmployee[name];
      var totalHours = entries.reduce(function (s, e) { return s + (parseFloat(e.HoursWorked) || 0); }, 0);
      var flags = [];

      if (totalHours > 40) flags.push({ type: 'Overtime (' + totalHours + 'h/week)', severity: totalHours > 50 ? 'high' : 'medium' });

      var dateCount = {};
      entries.forEach(function (e) {
        var key = e.Date + '|' + e.ShiftType;
        dateCount[key] = (dateCount[key] || 0) + 1;
      });
      Object.keys(dateCount).forEach(function (key) {
        if (dateCount[key] > 1) flags.push({ type: 'Duplicate Entry (' + key.split('|')[0] + ')', severity: 'high' });
      });

      var weekendShifts = entries.filter(function (e) { return e.ShiftType === 'Weekend'; });
      var nightShifts = entries.filter(function (e) { return e.ShiftType === 'Night'; });
      if (weekendShifts.length > 0 && nightShifts.length > 0) flags.push({ type: 'Ghost Shift Pattern (weekend + night)', severity: 'high' });
      else if (weekendShifts.length >= 2) flags.push({ type: 'Excessive Weekend Hours', severity: 'medium' });

      var maxDay = 0;
      entries.forEach(function (e) { var h = parseFloat(e.HoursWorked) || 0; if (h > maxDay) maxDay = h; });
      if (maxDay > 10) flags.push({ type: 'Single Day > 10h (' + maxDay + 'h)', severity: 'medium' });

      results.push({
        Employee: name,
        Department: entries[0].Department || '',
        Entries: entries.length,
        TotalHours: totalHours,
        flags: flags,
        severity: flags.length > 0 ? flags.reduce(function (worst, f) { return f.severity === 'high' ? 'high' : worst; }, 'medium') : 'low'
      });
    });
    return results;
  }

  function run(rows) {
    document.getElementById('input-section').style.display = 'block';
    DemoUtils.renderTable('input-table',
      [{ key: 'Employee', label: 'Employee' }, { key: 'Date', label: 'Date' }, { key: 'HoursWorked', label: 'Hours' }, { key: 'Department', label: 'Department' }, { key: 'ShiftType', label: 'Shift' }],
      rows
    );

    DemoUtils.runProcessing('processing',
      ['Loading timesheet entries...', 'Grouping by employee...', 'Checking overtime thresholds...', 'Scanning for duplicate entries...', 'Detecting ghost shift patterns...', 'Scoring anomalies...'],
      function () {
        var results = analyze(rows);
        var flagged = results.filter(function (r) { return r.flags.length > 0; });
        var highSev = results.filter(function (r) { return r.severity === 'high'; });

        DemoUtils.renderSummary('summary', [
          { value: rows.length, label: 'Timesheet Entries' },
          { value: results.length, label: 'Employees Analyzed' },
          { value: flagged.length, label: 'Employees Flagged', type: flagged.length > 0 ? 'alert' : '' },
          { value: highSev.length, label: 'High Severity', type: highSev.length > 0 ? 'alert' : '' }
        ]);

        DemoUtils.renderTable('results-table',
          [
            { key: 'Employee', label: 'Employee' },
            { key: 'Department', label: 'Department' },
            { label: 'Entries', render: function (r) { return r.Entries; } },
            { label: 'Total Hours', render: function (r) { return r.TotalHours + 'h'; } },
            { label: 'Severity', render: function (r) { return r.flags.length ? DemoUtils.badge(r.severity) : DemoUtils.badgeMatch(); } },
            { label: 'Anomalies', render: function (r) { return r.flags.map(function (f) { return f.type; }).join('; ') || 'Clean'; } }
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
