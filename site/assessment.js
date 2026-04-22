(function () {
  const BOOKING = 'https://meetings-na2.hubspot.com/chris-scowden';
  var HS_PORTAL = '245521589';
  var HS_FORM = window.SA_HS_FORM_GUID || '33eb4c23-f577-486b-bd43-806fe31ddf01';
  const questions = document.querySelectorAll('.assess-q');
  const progressBar = document.getElementById('progress-bar');
  const resultsEl = document.getElementById('results');
  const questionsEl = document.getElementById('questions');
  const total = questions.length;
  let current = 0;
  let score = 0;
  const answers = [];

  function showQuestion(idx) {
    questions.forEach(q => q.classList.remove('active'));
    if (idx < total) {
      questions[idx].classList.add('active');
      progressBar.style.width = ((idx / total) * 100) + '%';
    }
  }

  document.querySelectorAll('.assess-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const q = this.closest('.assess-q');
      const qIdx = parseInt(q.dataset.q, 10);
      const val = parseInt(this.dataset.val, 10);

      q.querySelectorAll('.assess-btn').forEach(b => b.classList.remove('selected'));
      this.classList.add('selected');

      answers[qIdx] = val;
      score = answers.reduce((a, b) => a + b, 0);

      setTimeout(function () {
        current = qIdx + 1;
        if (current >= total) {
          showResults();
        } else {
          showQuestion(current);
        }
      }, 350);
    });
  });

  function showResults() {
    progressBar.style.width = '100%';
    questionsEl.style.display = 'none';
    resultsEl.style.display = 'block';

    document.getElementById('score-num').textContent = score;

    const card = document.getElementById('score-card');
    const headline = document.getElementById('result-headline');
    const body = document.getElementById('result-body');
    const cta = document.getElementById('result-cta');
    const bookingWithScore = BOOKING + '&score=' + score;

    card.className = 'assess-score-card';

    if (score >= 4) {
      card.classList.add('score-ready');
      headline.textContent = 'You\'re ready for the Command Center.';
      body.textContent = 'Your data and organization are ready. The next step is a 30-minute discovery call to scope your Command Center deployment and identify the highest-ROI workflows to automate first.';
      cta.innerHTML = '<a href="' + bookingWithScore + '" class="btn btn-primary btn-lg" target="_blank" rel="noopener">Book Your Discovery Call &rarr;</a>';
    } else if (score >= 2) {
      card.classList.add('score-foundation');
      headline.textContent = 'You need foundational work first — and that\'s normal.';
      body.textContent = 'Most firms start here. Our Data & Systems Readiness phase gets you deployment-ready in 4-6 weeks — it\'s included in the platform license. No extra fees, no separate engagement.';
      cta.innerHTML = '<a href="' + bookingWithScore + '" class="btn btn-primary btn-lg" target="_blank" rel="noopener">Discuss Your Readiness Roadmap &rarr;</a>';
    } else {
      card.classList.add('score-early');
      headline.textContent = 'Not ready today — but let\'s stay connected.';
      body.textContent = 'You have foundational work ahead, and that\'s okay. Join our AI Roundtable — quarterly sessions where 25 staffing executives explore AI together, share challenges, and learn from each other.';
      cta.innerHTML = '<a href="mailto:chris.scowden@staffingagent.ai?subject=AI%20Roundtable%20Invitation&body=Score%3A%20' + score + '%2F5" class="btn btn-outline btn-lg">Request AI Roundtable Invitation</a>';
    }

    try {
      localStorage.setItem('sa_assessment', JSON.stringify({ score: score, answers: answers, ts: Date.now() }));
    } catch (e) { /* localStorage unavailable */ }

    resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  document.getElementById('lead-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var form = this;
    var data = {
      name: form.name.value,
      email: form.email.value,
      company: form.company.value,
      score: score,
      answers: answers
    };

    try {
      localStorage.setItem('sa_lead', JSON.stringify(data));
    } catch (e) { /* */ }
    if (HS_FORM) {
      var parts = data.name.split(' ');
      var fields = [
        { name: 'email', value: data.email },
        { name: 'firstname', value: parts[0] || '' },
        { name: 'lastname', value: parts.slice(1).join(' ') || '' },
        { name: 'company', value: data.company || '' }
      ];
      try {
        fetch('https://api.hsforms.com/submissions/v3/integration/submit/' + HS_PORTAL + '/' + HS_FORM, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fields: fields, context: { pageUri: window.location.href, pageName: document.title } })
        });
      } catch (ex) { /* silent */ }
    }
    var _hsq = window._hsq = window._hsq || [];
    var nameParts = data.name.split(' ');
    _hsq.push(['identify', { email: data.email, firstname: nameParts[0], lastname: nameParts.slice(1).join(' '), company: data.company, sa_assessment_score: String(data.score) }]);
    _hsq.push(['trackPageView']);

    form.innerHTML = '<p style="text-align:center;font-size:1.1rem;font-weight:600;color:#06b6d4;padding:1.5rem 0">Thank you! We\'ll follow up within 24 hours.</p>';
  });

  showQuestion(0);
})();
