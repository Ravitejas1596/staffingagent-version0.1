(function () {
  var AVG_INVOICE = 5000;
  var TIERS = [
    { name: 'Assess', monthly: 5000 },
    { name: 'Transform', monthly: 12500 },
    { name: 'Enterprise', monthly: 20000 }
  ];

  var els = {
    contractors: document.getElementById('contractors'),
    invoices: document.getElementById('invoices'),
    backlog: document.getElementById('backlog'),
    hours: document.getElementById('hours'),
    vmsPct: document.getElementById('vms-pct'),
    contractorsVal: document.getElementById('contractors-val'),
    invoicesVal: document.getElementById('invoices-val'),
    hoursVal: document.getElementById('hours-val'),
    outLabor: document.getElementById('out-labor'),
    outRecovery: document.getElementById('out-recovery'),
    outErrors: document.getElementById('out-errors'),
    outTotal: document.getElementById('out-total'),
    outMultiple: document.getElementById('out-multiple'),
    outTier: document.getElementById('out-tier')
  };

  function fmt(n) {
    return '$' + Math.round(n).toLocaleString('en-US');
  }

  function recommendedTier(contractors) {
    if (contractors >= 1000) return TIERS[2];
    if (contractors >= 300) return TIERS[1];
    return TIERS[0];
  }

  function calculate() {
    var hoursWeek = parseFloat(els.hours.value) || 0;
    var backlog = parseFloat(els.backlog.value) || 0;
    var invoicesMonth = parseFloat(els.invoices.value) || 0;
    var contractors = parseFloat(els.contractors.value) || 0;

    var laborSavings = hoursWeek * 50 * 55 * 0.60;
    var revenueRecovery = backlog * 0.40;
    var billingErrorReduction = invoicesMonth * 12 * AVG_INVOICE * 0.02 * 0.70;

    var total = laborSavings + revenueRecovery + billingErrorReduction;

    var tier = recommendedTier(contractors);
    var annualCost = tier.monthly * 12;
    var multiple = annualCost > 0 ? (total / annualCost) : 0;

    els.outLabor.textContent = fmt(laborSavings);
    els.outRecovery.textContent = fmt(revenueRecovery);
    els.outErrors.textContent = fmt(billingErrorReduction);
    els.outTotal.textContent = fmt(total);
    els.outMultiple.textContent = multiple.toFixed(1);

    if (els.outTier) {
      els.outTier.textContent = 'Based on ' + tier.name + ' tier at ' + fmt(tier.monthly) + '/mo (' + fmt(annualCost) + '/year)';
    }

    els.contractorsVal.textContent = parseInt(els.contractors.value).toLocaleString('en-US');
    els.invoicesVal.textContent = parseInt(els.invoices.value).toLocaleString('en-US');
    els.hoursVal.textContent = parseInt(els.hours.value);
  }

  ['contractors', 'invoices', 'backlog', 'hours', 'vmsPct'].forEach(function (key) {
    els[key].addEventListener('input', calculate);
  });

  calculate();
})();
