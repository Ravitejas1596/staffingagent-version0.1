import type { EntityPanelData, RiskCategory, TimesheetRecord, RiskRecord, FilterState } from '../../types';

// ─── deterministic hash for filter combos ───────────────────────────
function hashFilters(f: FilterState): number {
  const str = `${f.dateFrom}|${f.dateTo}|${f.branch}|${f.employmentType}|${f.legalEntity}|${f.employeeType}|${f.glSegment}`;
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function scaleFactor(filters: FilterState): number {
  let factor = 1.0;
  if (filters.branch !== 'All Branches') factor *= 0.28;
  if (filters.employmentType !== 'All Types') factor *= 0.45;
  if (filters.employeeType !== 'All Types') factor *= 0.55;
  if (filters.legalEntity !== 'All Entities') factor *= 0.55;
  if (filters.glSegment !== 'All Segments') factor *= 0.65;
  if (filters.productServiceCode !== 'All Codes') factor *= 0.70;

  const from = new Date(filters.dateFrom).getTime();
  const to = new Date(filters.dateTo).getTime();
  const days = Math.max(1, (to - from) / 86_400_000);
  const baselineDays = 250;
  factor *= Math.min(days / baselineDays, 1.5);

  return factor;
}

function jitter(base: number, hash: number, idx: number): number {
  const seed = ((hash * (idx + 7)) % 97) / 97;
  return Math.max(0, Math.round(base * (0.92 + seed * 0.16)));
}

function fmtNum(n: number): string {
  return n >= 1000 ? n.toLocaleString('en-US') : String(n);
}

function fmtDollar(n: number): string {
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (n >= 1000) return '$' + n.toLocaleString('en-US');
  return '$' + n.toString();
}

function pctOf(part: number, total: number): string {
  if (total === 0) return '0.0%';
  return (part / total * 100).toFixed(1) + '%';
}

// ─── generate filter-adjusted entity panels ─────────────────────────
export function generateEntityPanels(filters: FilterState): EntityPanelData[] {
  const h = hashFilters(filters);
  const s = scaleFactor(filters);

  // Placements
  const activePlacements = jitter(Math.round(274 * s), h, 0);
  const approvedPlacements = jitter(Math.round(247 * s), h, 1);
  const pendingPlacements = jitter(Math.round(18 * s), h, 2);
  const candidatesAtApproved = jitter(Math.round(189 * s), h, 3);
  const customersAtApproved = jitter(Math.round(73 * s), h, 4);
  const placementStarts = jitter(Math.round(42 * s), h, 5);
  const placementEnds = jitter(Math.round(15 * s), h, 6);
  const notSynced = jitter(Math.round(9 * s), h, 7);
  const syncFailed = jitter(Math.round(4 * s), h, 8);
  const notSyncedPending = jitter(Math.round(0 * s), h, 81);

  // T&E
  const expectedTS = jitter(Math.round(1847 * s), h, 10);
  const approvedTS = jitter(Math.round(1589 * s), h, 11);
  const openTS = jitter(Math.round(173 * s), h, 12);
  const didNotWorkTS = jitter(Math.round(22 * s), h, 13);
  const btlFailures = jitter(Math.round(34 * s), h, 14);
  const approvedExpense = jitter(Math.round(89 * s), h, 15);
  const missingTS = jitter(Math.round(142 * s), h, 16);
  const rejectedTS = jitter(Math.round(8 * s), h, 17);
  const disputedTS = jitter(Math.round(15 * s), h, 18);
  const submittedTS = jitter(Math.round(1652 * s), h, 19);
  const tsPct = expectedTS > 0 ? (approvedTS / expectedTS) * 100 : 0;

  // Payroll
  const totalPayable = jitter(Math.round(1589 * s), h, 20);
  const payProcessed = jitter(Math.round(1456 * s), h, 21);
  const payNotProcessed = Math.max(0, totalPayable - payProcessed);
  const payHasAdjustments = jitter(Math.round(47 * s), h, 22);
  const payNotReady = jitter(Math.round(85 * s), h, 23);
  const payReady = jitter(Math.round(32 * s), h, 24);
  const payProcessing = jitter(Math.round(12 * s), h, 25);
  const payExportError = jitter(Math.round(4 * s), h, 26);
  const payProcessedAmt = payProcessed * 1786;
  const payNotProcessedAmt = payNotProcessed * 1793;
  const payPct = totalPayable > 0 ? (payProcessed / totalPayable) * 100 : 0;

  // Billing
  const totalBillable = jitter(Math.round(1589 * s), h, 30);
  const billInvoiced = jitter(Math.round(1387 * s), h, 31);
  const billNotProcessed = Math.max(0, totalBillable - billInvoiced);
  const billHasAdjustments = jitter(Math.round(52 * s), h, 32);
  const billNotReady = jitter(Math.round(89 * s), h, 33);
  const billReady = jitter(Math.round(45 * s), h, 34);
  const billNeedsReview = jitter(Math.round(28 * s), h, 35);
  const billInvoicing = jitter(Math.round(15 * s), h, 36);
  const billUnbillable = jitter(Math.round(12 * s), h, 37);
  const billFailed = jitter(Math.round(8 * s), h, 38);
  const billOnHold = jitter(Math.round(5 * s), h, 39);
  const billInvoicedAmt = billInvoiced * 2177;
  const billNotProcessedAmt = billNotProcessed * 2178;
  const billPct = totalBillable > 0 ? (billInvoiced / totalBillable) * 100 : 0;

  // Invoices
  const totalInv = jitter(Math.round(962 * s), h, 40);
  const invFinalized = jitter(Math.round(892 * s), h, 41);
  const invNotProcessed = Math.max(0, totalInv - invFinalized);
  const invNew = jitter(Math.round(35 * s), h, 42);
  const invReady = jitter(Math.round(18 * s), h, 43);
  const invHold = jitter(Math.round(12 * s), h, 44);
  const invError = jitter(Math.round(3 * s), h, 45);
  const invProgress = jitter(Math.round(2 * s), h, 46);
  const glExportProcessed = jitter(Math.round(840 * s), h, 47);
  const glExportNotProcessed = Math.max(0, totalInv - glExportProcessed);
  const glNotReady = jitter(Math.round(78 * s), h, 48);
  const glReady = jitter(Math.round(32 * s), h, 49);
  const glInProgress = jitter(Math.round(8 * s), h, 50);
  const glFailed = jitter(Math.round(4 * s), h, 51);
  const invDelivered = jitter(Math.round(834 * s), h, 52);
  const invNotDelivered = Math.max(0, invFinalized - invDelivered);
  const invFinalizedAmt = invFinalized * 3626;
  const invNotProcessedAmt = invNotProcessed * 19286;
  const glProcessedAmt = glExportProcessed * 4762;
  const glNotProcessedAmt = glExportNotProcessed * 4770;
  const invDeliveredAmt = invDelivered * 5132;
  const invNotDeliveredAmt = invNotDelivered * 5138;
  const invPct = totalInv > 0 ? (invFinalized / totalInv) * 100 : 0;

  return [
    {
      id: 'placement', title: 'Placements', type: 'placement',
      metrics: [
        { label: 'Total Active Placements', value: activePlacements, isTile: true, dataKey: 'total-active-placements' },
        { label: 'Approved Placements', value: approvedPlacements, isTile: true, dataKey: 'approved-placements' },
        { label: 'Pending Placements', value: pendingPlacements, isTile: true, dataKey: 'pending-placements' },
        { label: 'Candidates at Approved Placements', value: candidatesAtApproved, isTile: true, dataKey: 'candidates-at-approved' },
        { label: 'Customers at Approved Placements', value: customersAtApproved, isTile: true, dataKey: 'customers-at-approved' },
        { label: 'Placement Starts', value: placementStarts, isTile: true, dataKey: 'placement-starts' },
        { label: 'Placement Ends', value: placementEnds, isTile: true, dataKey: 'placement-ends' },
        { label: 'Approved Placements Not Synced to BTE', value: notSynced, isAlert: true,
          subMetrics: [
            { label: 'Failed', value: syncFailed },
            { label: 'Not Synced', value: Math.max(0, notSynced - syncFailed - notSyncedPending) },
            { label: 'Pending', value: notSyncedPending },
          ],
        },
      ],
    },
    {
      id: 'time-expense', title: 'Time & Expense', type: 'time-expense',
      metrics: [
        { label: 'Total Timesheets Expected', value: fmtNum(expectedTS) },
        { label: 'Approved Timesheets', value: fmtNum(approvedTS), percentage: pctOf(approvedTS, expectedTS) },
        { label: 'Open Timesheets', value: openTS, percentage: pctOf(openTS, expectedTS),
          subMetrics: [
            { label: 'Missing Timesheets', value: missingTS, percentage: pctOf(missingTS, expectedTS) },
            { label: 'Rejected Timesheets', value: rejectedTS, percentage: pctOf(rejectedTS, expectedTS) },
            { label: 'Disputed Timesheets', value: disputedTS, percentage: pctOf(disputedTS, expectedTS) },
            { label: 'Submitted Timesheets', value: fmtNum(submittedTS), percentage: pctOf(submittedTS, expectedTS), clickable: true },
          ],
        },
        { label: 'Did Not Work Timesheets', value: didNotWorkTS, percentage: pctOf(didNotWorkTS, expectedTS) },
        { label: 'BTL Processing Failures', value: btlFailures, percentage: pctOf(btlFailures, expectedTS) },
        { label: 'Approved Expense Reports', value: approvedExpense, amount: fmtDollar(approvedExpense * 274) },
      ],
      progressBar: { value: Math.min(100, Math.round(tsPct * 10) / 10), label: `${tsPct.toFixed(1)}% Approved`, status: tsPct >= 85 ? 'success' : tsPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'payroll', title: 'Payroll', type: 'payroll',
      metrics: [
        { label: 'Total Payable Charges', value: fmtNum(totalPayable), amount: fmtDollar(payProcessedAmt + payNotProcessedAmt) },
        { label: 'Payable Charges Processed (Exported)', value: fmtNum(payProcessed), percentage: pctOf(payProcessed, totalPayable), amount: fmtDollar(payProcessedAmt) },
        { label: 'Payable Charges Not Processed', value: payNotProcessed, percentage: pctOf(payNotProcessed, totalPayable), amount: fmtDollar(payNotProcessedAmt),
          subMetrics: [
            { label: 'Not Ready to Pay', value: payNotReady },
            { label: 'Ready to Pay', value: payReady },
            { label: 'Processing / Waiting on Payroll Provider', value: payProcessing },
            { label: 'Export Error', value: payExportError },
          ],
        },
        { label: 'Payable Charges Has Adjustments', value: payHasAdjustments, percentage: pctOf(payHasAdjustments, totalPayable), amount: fmtDollar(payHasAdjustments * 402) },
      ],
      progressBar: { value: Math.min(100, Math.round(payPct * 10) / 10), label: `${payPct.toFixed(1)}% Processed`, status: payPct >= 85 ? 'success' : payPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'billing', title: 'Billing', type: 'billing',
      metrics: [
        { label: 'Total Billable Charges', value: fmtNum(totalBillable), amount: fmtDollar(billInvoicedAmt + billNotProcessedAmt) },
        { label: 'Billable Charges Processed (Invoiced)', value: fmtNum(billInvoiced), percentage: pctOf(billInvoiced, totalBillable), amount: fmtDollar(billInvoicedAmt) },
        { label: 'Billable Charges Not Processed', value: billNotProcessed, percentage: pctOf(billNotProcessed, totalBillable), amount: fmtDollar(billNotProcessedAmt),
          subMetrics: [
            { label: 'Not Ready to Bill', value: billNotReady },
            { label: 'Ready to Bill', value: billReady },
            { label: 'Processing / Needs Review', value: billNeedsReview },
            { label: 'Invoicing', value: billInvoicing },
            { label: 'Unbillable', value: billUnbillable },
            { label: 'Processing Failed', value: billFailed },
            { label: 'On Hold', value: billOnHold },
          ],
        },
        { label: 'Billable Charges Has Adjustments', value: billHasAdjustments, percentage: pctOf(billHasAdjustments, totalBillable), amount: fmtDollar(billHasAdjustments * 475) },
      ],
      progressBar: { value: Math.min(100, Math.round(billPct * 10) / 10), label: `${billPct.toFixed(1)}% Invoiced`, status: billPct >= 85 ? 'success' : billPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'invoices', title: 'Invoices', type: 'invoices',
      metrics: [
        { label: 'Total Invoices', value: totalInv, amount: fmtDollar(invFinalizedAmt + invNotProcessedAmt) },
        { label: 'Invoices Processed (Finalized)', value: invFinalized, percentage: pctOf(invFinalized, totalInv), amount: fmtDollar(invFinalizedAmt) },
        { label: 'Invoices Not Processed', value: invNotProcessed, percentage: pctOf(invNotProcessed, totalInv), amount: fmtDollar(invNotProcessedAmt),
          subMetrics: [
            { label: 'New', value: invNew },
            { label: 'Ready', value: invReady },
            { label: 'Hold', value: invHold },
            { label: 'Finalization in Error', value: invError },
            { label: 'Finalization in Progress', value: invProgress },
          ],
        },
        { label: 'General Ledger Export Processed', value: glExportProcessed, percentage: pctOf(glExportProcessed, totalInv), amount: fmtDollar(glProcessedAmt) },
        { label: 'General Ledger Export Not Processed', value: glExportNotProcessed, percentage: pctOf(glExportNotProcessed, totalInv), amount: fmtDollar(glNotProcessedAmt),
          subMetrics: [
            { label: 'Not Ready to Export', value: glNotReady },
            { label: 'Ready to Export', value: glReady },
            { label: 'Export in Progress', value: glInProgress },
            { label: 'Export Failed', value: glFailed },
          ],
        },
        { label: 'Invoice Delivery Status', value: '',
          subMetrics: [
            { label: 'Invoice Delivered', value: invDelivered, percentage: pctOf(invDelivered, invFinalized), amount: fmtDollar(invDeliveredAmt) },
            { label: 'Invoice Not Delivered', value: invNotDelivered, percentage: pctOf(invNotDelivered, invFinalized), amount: fmtDollar(invNotDeliveredAmt) },
          ],
        },
      ],
      progressBar: { value: Math.min(100, Math.round(invPct * 10) / 10), label: `${invPct.toFixed(1)}% Finalized`, status: invPct >= 85 ? 'success' : invPct >= 70 ? 'warning' : 'danger' },
    },
  ];
}

// ─── generate filter-adjusted risk categories ───────────────────────
export function generateRiskCategories(filters: FilterState): RiskCategory[] {
  const h = hashFilters(filters);
  const s = scaleFactor(filters);

  return [
    { id: 'timesheet', label: 'Timesheets', count: jitter(Math.round(142 * s), h, 60), severity: 'HIGH', color: '#1d4ed8',
      subCategories: [
        { label: 'Missing Timesheets', count: jitter(Math.round(142 * s), h, 61), errorType: 'missing-timesheets' },
        { label: 'Timesheets Excluded from Missing', count: jitter(Math.round(22 * s), h, 62), errorType: 'excluded-timesheets' },
        { label: 'Missing Timesheets After Exclusions', count: jitter(Math.round(120 * s), h, 63), errorType: 'after-exclusions' },
      ],
    },
    { id: 'placement-alignment', label: 'Placement Alignment', count: jitter(Math.round(20 * s), h, 64), severity: 'MED', color: '#f59e0b',
      subCategories: [
        { label: 'Active Placement Date Mismatches', count: jitter(Math.round(12 * s), h, 65), errorType: 'active-date-mismatch' },
        { label: 'Inactive Placements Date Mismatches', count: jitter(Math.round(8 * s), h, 66), errorType: 'inactive-date-mismatch' },
        { label: 'Rate Card Missing', count: jitter(Math.round(0 * s), h, 67), errorType: 'rate-card-missing' },
      ],
    },
    { id: 'wage-compliance', label: 'Minimum Wage Compliance', count: jitter(Math.round(4 * s), h, 68), severity: 'LOW', color: '#16a34a',
      subCategories: [
        { label: 'Below Federal Min Wage', count: jitter(Math.round(4 * s), h, 69), errorType: 'below-min-wage' },
      ],
    },
    { id: 'rate-flags', label: 'Rate Flags', count: jitter(Math.round(5 * s), h, 70), severity: 'MED', color: '#2563eb',
      subCategories: [
        { label: 'Rate Card Mismatch', count: jitter(Math.round(5 * s), h, 71), errorType: 'rate-card-mismatch' },
        { label: 'High Pay Rate', count: jitter(Math.round(0 * s), h, 72), errorType: 'high-pay-rate' },
        { label: 'High Bill Rate', count: jitter(Math.round(0 * s), h, 73), errorType: 'high-bill-rate' },
      ],
    },
    { id: 'hours-flags', label: 'Hours Flags', count: jitter(Math.round(46 * s), h, 74), severity: 'HIGH', color: '#ea580c',
      subCategories: [
        { label: 'Pay ≠ Bill Hours', count: jitter(Math.round(23 * s), h, 75), errorType: 'pay-bill-mismatch' },
        { label: 'Hours > 40', count: jitter(Math.round(15 * s), h, 76), errorType: 'overtime' },
        { label: 'High Hours', count: jitter(Math.round(8 * s), h, 77), errorType: 'high-hours' },
      ],
    },
    { id: 'amounts-flags', label: 'Amounts Flags', count: jitter(Math.round(23 * s), h, 78), severity: 'CRT', color: '#dc2626',
      subCategories: [
        { label: 'High Pay Amounts', count: jitter(Math.round(6 * s), h, 79), errorType: 'high-pay-amounts' },
        { label: 'High Bill Amounts', count: jitter(Math.round(4 * s), h, 80), errorType: 'high-bill-amounts' },
        { label: 'Pay Amount with No Bill Amount', count: jitter(Math.round(7 * s), h, 81), errorType: 'pay-no-bill' },
        { label: 'Bill Amount with No Pay Amount', count: jitter(Math.round(3 * s), h, 82), errorType: 'bill-no-pay' },
        { label: 'Negative Pay Amounts', count: jitter(Math.round(2 * s), h, 83), errorType: 'negative-pay' },
        { label: 'Negative Bill Amounts', count: jitter(Math.round(1 * s), h, 84), errorType: 'negative-bill' },
      ],
    },
    { id: 'markup-analysis', label: 'Markup Analysis', count: jitter(Math.round(29 * s), h, 85), severity: 'MED', color: '#7c3aed',
      subCategories: [
        { label: 'Negative Markup', count: jitter(Math.round(2 * s), h, 86), errorType: 'negative-markup' },
        { label: 'Low Markup', count: jitter(Math.round(18 * s), h, 87), errorType: 'low-markup' },
        { label: 'High Markup', count: jitter(Math.round(9 * s), h, 88), errorType: 'high-markup' },
      ],
    },
  ];
}

// ─── static defaults (used for initial render) ──────────────────────
const defaultFilters: FilterState = {
  dateType: 'Period End Date',
  timeFrame: 'Date Range',
  dateFrom: '2025-01-01',
  dateTo: '2025-09-08',
  branch: 'All Branches',
  employmentType: 'All Types',
  employeeType: 'All Types',
  legalEntity: 'All Entities',
  glSegment: 'All Segments',
  productServiceCode: 'All Codes',
};

export const entityPanels: EntityPanelData[] = generateEntityPanels(defaultFilters);
export const riskCategories: RiskCategory[] = generateRiskCategories(defaultFilters);

export const timesheetRecords: TimesheetRecord[] = [
  { id: 1, timesheetId: 'TS-2025-001', excluded: false, lastReminderSent: '08/25/2025', placementId: 'PL-8901', customerName: 'ACME Corporation', jobTitle: 'Senior Software Engineer', candidateName: 'John Smith', placementStart: '01/15/2025', placementEnd: '12/31/2025', periodEndDate: '09/05/2025', candidateEmail: 'john.smith@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'North Region' },
  { id: 2, timesheetId: 'TS-2025-002', excluded: true, lastReminderSent: '08/20/2025', placementId: 'PL-8902', customerName: 'GlobalTech Solutions', jobTitle: 'Data Analyst', candidateName: 'Jane Doe', placementStart: '03/01/2025', placementEnd: '02/28/2026', periodEndDate: '09/05/2025', candidateEmail: 'jane.doe@email.com', comments: 'Medical leave approved', excludedBy: 'Sarah Wilson', excludedDate: '08/22/2025 2:30 PM', branch: 'South Region' },
  { id: 3, timesheetId: 'TS-2025-003', excluded: false, lastReminderSent: '08/28/2025', placementId: 'PL-8903', customerName: 'MedStaff Inc', jobTitle: 'Project Manager', candidateName: 'Jennifer Walsh', placementStart: '06/01/2025', placementEnd: '11/30/2025', periodEndDate: '09/05/2025', candidateEmail: 'j.walsh@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'East Region' },
  { id: 4, timesheetId: 'TS-2025-004', excluded: false, lastReminderSent: '—', placementId: 'PL-8904', customerName: 'Summit Health', jobTitle: 'Network Administrator', candidateName: 'David Kim', placementStart: '04/15/2025', placementEnd: '04/14/2026', periodEndDate: '09/05/2025', candidateEmail: 'd.kim@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'North Region' },
  { id: 5, timesheetId: 'TS-2025-005', excluded: true, lastReminderSent: '08/15/2025', placementId: 'PL-8905', customerName: 'BlueChip LLC', jobTitle: 'QA Engineer', candidateName: 'Amanda Price', placementStart: '02/01/2025', placementEnd: '01/31/2026', periodEndDate: '08/29/2025', candidateEmail: 'a.price@email.com', comments: 'Client vacation week', excludedBy: 'James O\'Brien', excludedDate: '08/20/2025 10:15 AM', branch: 'South Region' },
  { id: 6, timesheetId: 'TS-2025-006', excluded: false, lastReminderSent: '08/30/2025', placementId: 'PL-8906', customerName: 'Apex Solutions', jobTitle: 'Business Analyst', candidateName: 'Robert Chen', placementStart: '07/01/2025', placementEnd: '06/30/2026', periodEndDate: '09/05/2025', candidateEmail: 'r.chen@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'West Region' },
  { id: 7, timesheetId: 'TS-2025-007', excluded: false, lastReminderSent: '—', placementId: 'PL-8907', customerName: 'NovaCare', jobTitle: 'DevOps Engineer', candidateName: 'Lisa Patel', placementStart: '05/15/2025', placementEnd: '05/14/2026', periodEndDate: '09/05/2025', candidateEmail: 'l.patel@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'North Region' },
  { id: 8, timesheetId: 'TS-2025-008', excluded: false, lastReminderSent: '08/27/2025', placementId: 'PL-8908', customerName: 'TechForce', jobTitle: 'Full Stack Developer', candidateName: 'James Rodriguez', placementStart: '08/01/2025', placementEnd: '07/31/2026', periodEndDate: '09/05/2025', candidateEmail: 'j.rodriguez@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'South Region' },
  { id: 9, timesheetId: 'TS-2025-009', excluded: false, lastReminderSent: '08/22/2025', placementId: 'PL-8909', customerName: 'Pinnacle Group', jobTitle: 'Systems Architect', candidateName: 'Emily Watson', placementStart: '03/15/2025', placementEnd: '03/14/2026', periodEndDate: '08/29/2025', candidateEmail: 'e.watson@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'East Region' },
  { id: 10, timesheetId: 'TS-2025-010', excluded: false, lastReminderSent: '—', placementId: 'PL-8910', customerName: 'ACME Corporation', jobTitle: 'Cloud Engineer', candidateName: 'Christopher Lee', placementStart: '01/02/2025', placementEnd: '12/31/2025', periodEndDate: '09/05/2025', candidateEmail: 'c.lee@email.com', comments: '', excludedBy: '—', excludedDate: '—', branch: 'North Region' },
];

export const riskRecords: RiskRecord[] = [
  { id: 1, timesheetId: 'TS-2025-001', resolvedStatus: 'Open', category: 'placement-alignment', errorType: 'Active Placement Date Mismatches', customerName: 'ACME Corporation', candidateName: 'John Smith', placementId: 'PL-8901', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$2,800', billed: '$4,200', markupPct: '50.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'MED', branch: 'North Region' },
  { id: 2, timesheetId: 'TS-2025-002', resolvedStatus: 'Pending', category: 'rate-flags', errorType: 'Rate Card Mismatch', customerName: 'GlobalTech Solutions', candidateName: 'Jane Doe', placementId: 'PL-8902', tsPeriod: '09/05/2025', hoursWorked: 38, payHours: 38, billHours: 38, paid: '$1,710', billed: '$2,660', markupPct: '55.6%', comments: 'Under review by AP', resolvedBy: 'Sarah Wilson', resolvedDate: '08/28/2025 3:45 PM', severity: 'MED', branch: 'South Region' },
  { id: 3, timesheetId: 'TS-2025-003', resolvedStatus: 'Open', category: 'amounts-flags', errorType: 'Pay Amount with No Bill Amount', customerName: 'MedStaff Inc', candidateName: 'Jennifer Walsh', placementId: 'PL-8903', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 0, paid: '$2,400', billed: '$0', markupPct: '-100.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'CRT', branch: 'East Region' },
  { id: 4, timesheetId: 'TS-2025-004', resolvedStatus: 'Open', category: 'hours-flags', errorType: 'Hours > 40', customerName: 'Summit Health', candidateName: 'David Kim', placementId: 'PL-8904', tsPeriod: '09/05/2025', hoursWorked: 52, payHours: 52, billHours: 52, paid: '$3,640', billed: '$5,460', markupPct: '50.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'HIGH', branch: 'North Region' },
  { id: 5, timesheetId: 'TS-2025-005', resolvedStatus: 'Open', category: 'wage-compliance', errorType: 'Below Federal Min Wage', customerName: 'BlueChip LLC', candidateName: 'Amanda Price', placementId: 'PL-8905', tsPeriod: '08/29/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$286', billed: '$520', markupPct: '81.8%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'CRT', branch: 'South Region' },
  { id: 6, timesheetId: 'TS-2025-006', resolvedStatus: 'Resolved', category: 'markup-analysis', errorType: 'Low Markup', customerName: 'Apex Solutions', candidateName: 'Robert Chen', placementId: 'PL-8906', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$3,400', billed: '$4,012', markupPct: '18.0%', comments: 'Approved by VP Sales', resolvedBy: 'Chris Scowden', resolvedDate: '09/01/2025 11:30 AM', severity: 'MED', branch: 'West Region' },
  { id: 7, timesheetId: 'TS-2025-007', resolvedStatus: 'Open', category: 'hours-flags', errorType: 'High Hours', customerName: 'NovaCare', candidateName: 'Lisa Patel', placementId: 'PL-8907', tsPeriod: '09/05/2025', hoursWorked: 72, payHours: 72, billHours: 72, paid: '$5,040', billed: '$7,560', markupPct: '50.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'HIGH', branch: 'North Region' },
  { id: 8, timesheetId: 'TS-2025-008', resolvedStatus: 'Pending', category: 'amounts-flags', errorType: 'High Pay Amounts', customerName: 'TechForce', candidateName: 'James Rodriguez', placementId: 'PL-8908', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$7,400', billed: '$11,100', markupPct: '50.0%', comments: 'Rate confirmed', resolvedBy: 'Jane Smith', resolvedDate: '09/02/2025 9:00 AM', severity: 'MED', branch: 'South Region' },
  { id: 9, timesheetId: 'TS-2025-009', resolvedStatus: 'Open', category: 'hours-flags', errorType: 'Pay ≠ Bill Hours', customerName: 'Pinnacle Group', candidateName: 'Emily Watson', placementId: 'PL-8909', tsPeriod: '08/29/2025', hoursWorked: 45, payHours: 45, billHours: 40, paid: '$3,150', billed: '$4,200', markupPct: '33.3%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'HIGH', branch: 'East Region' },
  { id: 10, timesheetId: 'TS-2025-010', resolvedStatus: 'Open', category: 'markup-analysis', errorType: 'Negative Markup', customerName: 'ACME Corporation', candidateName: 'Christopher Lee', placementId: 'PL-8910', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$4,000', billed: '$3,600', markupPct: '-10.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'CRT', branch: 'North Region' },
  { id: 11, timesheetId: 'TS-2025-011', resolvedStatus: 'Open', category: 'placement-alignment', errorType: 'Inactive Placements Date Mismatches', customerName: 'Summit Health', candidateName: 'Maria Garcia', placementId: 'PL-8911', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$2,600', billed: '$3,900', markupPct: '50.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'MED', branch: 'West Region' },
  { id: 12, timesheetId: 'TS-2025-012', resolvedStatus: 'Open', category: 'amounts-flags', errorType: 'Negative Pay Amounts', customerName: 'GlobalTech Solutions', candidateName: 'Tom Anderson', placementId: 'PL-8912', tsPeriod: '09/05/2025', hoursWorked: 8, payHours: -8, billHours: 0, paid: '-$560', billed: '$0', markupPct: '0.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'HIGH', branch: 'South Region' },
  { id: 13, timesheetId: 'TS-2025-013', resolvedStatus: 'Open', category: 'markup-analysis', errorType: 'High Markup', customerName: 'Apex Solutions', candidateName: 'Sarah Mitchell', placementId: 'PL-8913', tsPeriod: '09/05/2025', hoursWorked: 40, payHours: 40, billHours: 40, paid: '$1,200', billed: '$3,600', markupPct: '200.0%', comments: '', resolvedBy: '—', resolvedDate: '—', severity: 'MED', branch: 'East Region' },
];
