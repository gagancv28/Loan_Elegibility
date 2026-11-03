/**
 * Veritas Credit Underwriting Portal — Frontend Logic
 * Handles: form interactions, slider sync, persona loading,
 *          API calls, chart rendering, memo generation, modal.
 */

'use strict';

// ============================================================
// 1. Utility Helpers
// ============================================================
const fmt = {
  /** Format INR in lakhs or thousands with ₹ symbol */
  inr(n) {
    n = Math.round(n);
    if (n >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
    if (n >= 1000)   return `₹${(n / 1000).toFixed(1)}K`;
    return `₹${n}`;
  },
  /** Format as percentage */
  pct(n, decimals = 1) {
    return `${(n * 100).toFixed(decimals)}%`;
  },
  /** Format percentage points for SHAP bars */
  pp(n) {
    const sign = n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(1)}pp`;
  },
  /** Format a number with commas */
  num(n) {
    return Math.round(n).toLocaleString('en-IN');
  },
};

function clamp(val, min, max) {
  return Math.min(Math.max(val, min), max);
}

function showToast(msg, duration = 2800) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

// ============================================================
// 2. Slider ↔ Input Sync
// ============================================================
function initSlider(sliderId, inputId, min, max, format) {
  const slider = document.getElementById(sliderId);
  const input  = document.getElementById(inputId);
  const labelEl = document.getElementById(sliderId + '-display');

  function updateSliderBackground(val) {
    const pct = ((val - min) / (max - min)) * 100;
    slider.style.setProperty('--range-pct', `${pct}%`);
  }

  function sync(val) {
    val = clamp(parseFloat(val) || min, min, max);
    slider.value = val;
    input.value  = Math.round(val);
    if (labelEl) labelEl.textContent = format ? format(val) : val;
    updateSliderBackground(val);
  }

  slider.addEventListener('input', () => sync(slider.value));
  input.addEventListener('input', () => sync(input.value));
  input.addEventListener('change', () => sync(input.value));

  // Initialise from current value
  sync(slider.value);
}

// ============================================================
// 3. Initialise All Sliders
// ============================================================
function initAllSliders() {
  initSlider('s-app-income', 'i-app-income', 10000, 500000, fmt.inr);
  initSlider('s-coapp-income', 'i-coapp-income', 0, 300000, fmt.inr);
  initSlider('s-existing-debt', 'i-existing-debt', 0, 150000, fmt.inr);
  initSlider('s-loan-amount', 'i-loan-amount', 100000, 10000000, fmt.inr);
  initSlider('s-loan-term', 'i-loan-term', 12, 360, v => `${v} mo`);
  initSlider('s-credit-score', 'i-credit-score', 300, 850, v => v);
  initSlider('s-emp-length', 'i-emp-length', 0, 30, v => `${v} yr`);
  initSlider('s-abb', 'i-abb', 5000, 500000, fmt.inr);
}

// ============================================================
// 4. Prior Defaults Toggle & NTC Toggle
// ============================================================
function initDefaultToggle() {
  const btnNo  = document.getElementById('toggle-default-no');
  const btnYes = document.getElementById('toggle-default-yes');
  const input  = document.getElementById('h-prior-defaults');

  function setDefault(val) {
    input.value = val;
    btnNo.classList.remove('active-no', 'active-yes');
    btnYes.classList.remove('active-no', 'active-yes');
    if (val === '0') btnNo.classList.add('active-no');
    else             btnYes.classList.add('active-yes');
  }

  btnNo.addEventListener('click', () => setDefault('0'));
  btnYes.addEventListener('click', () => setDefault('1'));
  setDefault('0'); // default
}

function initNtcToggle() {
  const chk = document.getElementById('chk-ntc');
  const sliderWrap = document.getElementById('credit-score-slider-wrap');
  const badge = document.getElementById('ntc-active-badge');
  const cashflowSec = document.getElementById('ntc-cashflow-section');
  const empSel = document.getElementById('sel-employment-type');
  const tenureSel = document.getElementById('sel-statement-tenure');
  const scoreDisplay = document.getElementById('s-credit-score-display');
  const scoreSlider = document.getElementById('s-credit-score');

  if (!chk) return;

  function updateNtcState() {
    const isNtc = chk.checked;
    if (isNtc) {
      if (sliderWrap) sliderWrap.classList.add('muted-slider');
      if (badge) badge.style.display = 'flex';
      if (cashflowSec) cashflowSec.style.display = 'block';
      if (scoreDisplay) scoreDisplay.textContent = 'NTC (-1 / NH)';
    } else {
      if (sliderWrap) sliderWrap.classList.remove('muted-slider');
      if (badge) badge.style.display = 'none';
      if (cashflowSec) cashflowSec.style.display = 'none';
      if (scoreDisplay && scoreSlider) scoreDisplay.textContent = scoreSlider.value;
    }
  }

  window.updateNtcState = updateNtcState;
  chk.addEventListener('change', updateNtcState);

  // Dynamic statement tenure update when employment type changes
  if (empSel && tenureSel) {
    empSel.addEventListener('change', () => {
      const val = empSel.value;
      if (val === 'Salaried') {
        tenureSel.value = '6';
      } else {
        tenureSel.value = '12';
      }
    });
  }

  updateNtcState();
}

// ============================================================
// 4.2. Bank Statement Ingestion & 1-Click AA Fetch
// ============================================================
function initStatementIngestion() {
  const dropzone = document.getElementById('statement-dropzone');
  const fileInput = document.getElementById('statement-file-input');
  const btnUpload = document.getElementById('btn-parse-upload');
  const pwdInput = document.getElementById('statement-password');
  const filenameDisplay = document.getElementById('dropzone-filename');
  const btnSimSalaried = document.getElementById('btn-sim-salaried');
  const btnSimBusiness = document.getElementById('btn-sim-business');

  if (!dropzone || !fileInput) return;

  dropzone.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) {
      const f = fileInput.files[0];
      if (filenameDisplay) {
        filenameDisplay.textContent = `Selected: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
      }
    }
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      fileInput.files = e.dataTransfer.files;
      const f = fileInput.files[0];
      if (filenameDisplay) {
        filenameDisplay.textContent = `Selected: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
      }
    }
  });

  // Manual File Upload & Parse
  if (btnUpload) {
    btnUpload.addEventListener('click', async () => {
      if (!fileInput.files || !fileInput.files[0]) {
        showToast('Please select or drop a bank statement file (.csv, .xlsx, .pdf) first.');
        return;
      }
      const file = fileInput.files[0];
      const formData = new FormData();
      formData.append('file', file);
      if (pwdInput && pwdInput.value) {
        formData.append('password', pwdInput.value.trim());
      }

      const origText = btnUpload.innerHTML;
      btnUpload.disabled = true;
      btnUpload.innerHTML = '<span>Analyzing Statement...</span>';

      try {
        const res = await fetch('/api/parse-statement', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.error) {
          showToast(`Error: ${data.error}`);
        } else {
          applyParsedStatement(data);
        }
      } catch (err) {
        showToast('Network error analyzing statement.');
      } finally {
        btnUpload.disabled = false;
        btnUpload.innerHTML = origText;
      }
    });
  }

  // 1-Click Simulation: Salaried 6-Mo
  if (btnSimSalaried) {
    btnSimSalaried.addEventListener('click', async () => {
      const origText = btnSimSalaried.innerHTML;
      btnSimSalaried.disabled = true;
      btnSimSalaried.innerHTML = '<span>Fetching 6-Mo Salaried AA Data...</span>';

      try {
        const res = await fetch('/api/parse-statement', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sample_key: 'salaried_6mo' })
        });
        const data = await res.json();
        if (data.error) {
          showToast(`Error: ${data.error}`);
        } else {
          const empSel = document.getElementById('sel-employment-type');
          if (empSel) empSel.value = 'Salaried';
          applyParsedStatement(data);
        }
      } catch (err) {
        showToast('Error simulating salaried AA statement.');
      } finally {
        btnSimSalaried.disabled = false;
        btnSimSalaried.innerHTML = origText;
      }
    });
  }

  // 1-Click Simulation: Business 12-Mo Risky
  if (btnSimBusiness) {
    btnSimBusiness.addEventListener('click', async () => {
      const origText = btnSimBusiness.innerHTML;
      btnSimBusiness.disabled = true;
      btnSimBusiness.innerHTML = '<span>Fetching 12-Mo Business AA Data...</span>';

      try {
        const res = await fetch('/api/parse-statement', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sample_key: 'self_employed_12mo' })
        });
        const data = await res.json();
        if (data.error) {
          showToast(`Error: ${data.error}`);
        } else {
          const empSel = document.getElementById('sel-employment-type');
          if (empSel) empSel.value = 'Self-Employed';
          applyParsedStatement(data);
        }
      } catch (err) {
        showToast('Error simulating business AA statement.');
      } finally {
        btnSimBusiness.disabled = false;
        btnSimBusiness.innerHTML = origText;
      }
    });
  }
}

function applyParsedStatement(data) {
  // Populate Audit Card
  const auditCard = document.getElementById('statement-audit-card');
  const auditFn = document.getElementById('audit-filename');
  const auditTxns = document.getElementById('audit-txns-count');
  const auditInflow = document.getElementById('audit-monthly-inflow');
  const auditAbb = document.getElementById('audit-abb');
  const auditSurplus = document.getElementById('audit-surplus');
  const auditBouncesWrap = document.getElementById('audit-bounces-wrap');

  if (auditFn) auditFn.textContent = data.filename;
  if (auditTxns) auditTxns.textContent = `${data.transactions_count} txns (${data.months_detected} Mo)`;
  if (auditInflow) auditInflow.textContent = fmt.inr(data.verified_monthly_income) + '/mo';
  if (auditAbb) auditAbb.textContent = fmt.inr(data.calculated_abb);
  if (auditSurplus) {
    const sgn = data.net_monthly_surplus >= 0 ? '+' : '';
    auditSurplus.textContent = `${sgn}${fmt.inr(data.net_monthly_surplus)}/mo`;
  }
  if (auditBouncesWrap) {
    if (data.bounce_count === 0) {
      auditBouncesWrap.innerHTML = `<span class="bounce-clean-pill">0 Detected (Clean)</span>`;
    } else {
      auditBouncesWrap.innerHTML = `<span class="bounce-alert-pill">${data.bounce_count} Bounces Detected!</span>`;
    }
  }
  if (auditCard) auditCard.style.display = 'block';

  // Ensure NTC toggle is ON
  const chkNtc = document.getElementById('chk-ntc');
  if (chkNtc && !chkNtc.checked) {
    chkNtc.checked = true;
    if (typeof window.updateNtcState === 'function') window.updateNtcState();
  }

  // Synchronize form fields
  if (data.verified_monthly_income) {
    setValue('s-app-income', 'i-app-income', data.verified_monthly_income);
  }
  if (data.statement_tenure) {
    const tenureSel = document.getElementById('sel-statement-tenure');
    if (tenureSel) tenureSel.value = String(data.statement_tenure);
  }
  if (data.calculated_abb) {
    setValue('s-abb', 'i-abb', data.calculated_abb);
  }
  if (data.utility_consistency) {
    const utilSel = document.getElementById('sel-utility-consistency');
    if (utilSel) utilSel.value = data.utility_consistency;
  }

  // Trigger Underwriting Assessment immediately
  const btnAssess = document.getElementById('btn-assess');
  if (btnAssess) {
    setTimeout(() => btnAssess.click(), 150);
  }

  showToast(`Statement analyzed: ${fmt.inr(data.calculated_abb)} ABB · ${data.utility_consistency} discipline`);
}

// ============================================================
// 5. Persona Loader
// ============================================================
async function loadPersona(key) {
  if (!key) return;
  try {
    const res = await fetch(`/api/persona/${key}`);
    const p   = await res.json();
    if (p.error) { showToast('Error loading persona.'); return; }

    // Push values into sliders/inputs
    setValue('s-app-income',    'i-app-income',    p.Applicant_Income);
    setValue('s-coapp-income',  'i-coapp-income',  p.Coapplicant_Income);
    setValue('s-existing-debt', 'i-existing-debt', p.Existing_Monthly_Debt);
    setValue('s-loan-amount',   'i-loan-amount',   p.Loan_Amount);
    setValue('s-loan-term',     'i-loan-term',     p.Loan_Term_Months);
    if (p.Credit_Score && p.Credit_Score > 0) {
      setValue('s-credit-score', 'i-credit-score', p.Credit_Score);
    }
    setValue('s-emp-length',    'i-emp-length',     p.Employment_Length_Years);

    const empSel  = document.getElementById('sel-employment-type');
    const areaSel = document.getElementById('sel-property-area');
    if (empSel)  empSel.value  = p.Employment_Type;
    if (areaSel) areaSel.value = p.Property_Area;

    // NTC Toggle & Alternative Cash-Flow inputs
    const chkNtc = document.getElementById('chk-ntc');
    if (chkNtc) {
      chkNtc.checked = !!p.is_ntc;
      if (typeof window.updateNtcState === 'function') window.updateNtcState();
    }
    if (p.bank_statement_tenure) {
      const tenureSel = document.getElementById('sel-statement-tenure');
      if (tenureSel) tenureSel.value = String(p.bank_statement_tenure);
    }
    if (p.average_bank_balance) {
      setValue('s-abb', 'i-abb', p.average_bank_balance);
    }
    if (p.utility_repayment_consistency) {
      const utilSel = document.getElementById('sel-utility-consistency');
      if (utilSel) utilSel.value = p.utility_repayment_consistency;
    }

    // Prior defaults toggle
    const defaultToggle = p.Prior_Defaults === 1 ? '1' : '0';
    document.getElementById('h-prior-defaults').value = defaultToggle;
    document.getElementById('toggle-default-no').classList.remove('active-no', 'active-yes');
    document.getElementById('toggle-default-yes').classList.remove('active-no', 'active-yes');
    if (defaultToggle === '0') document.getElementById('toggle-default-no').classList.add('active-no');
    else                       document.getElementById('toggle-default-yes').classList.add('active-yes');

    showToast(`Loaded: ${p.label}`);

    // Auto-assess after persona load
    setTimeout(() => document.getElementById('btn-assess').click(), 300);

  } catch (e) {
    showToast('Network error loading persona.');
  }
}

function setValue(sliderId, inputId, val) {
  const slider  = document.getElementById(sliderId);
  const input   = document.getElementById(inputId);
  const labelEl = document.getElementById(sliderId + '-display');
  slider.value  = val;
  input.value   = Math.round(val);
  slider.dispatchEvent(new Event('input'));
}

// ============================================================
// 6. Form Data Collection
// ============================================================
function collectFormData() {
  const chkNtc = document.getElementById('chk-ntc');
  const isNtc = chkNtc ? chkNtc.checked : false;
  const tenureSel = document.getElementById('sel-statement-tenure');
  const abbInput = document.getElementById('i-abb');
  const utilitySel = document.getElementById('sel-utility-consistency');

  return {
    applicant_income        : parseInt(document.getElementById('i-app-income').value)    || 0,
    coapplicant_income      : parseInt(document.getElementById('i-coapp-income').value)  || 0,
    existing_monthly_debt   : parseInt(document.getElementById('i-existing-debt').value) || 0,
    loan_amount             : parseInt(document.getElementById('i-loan-amount').value)   || 0,
    loan_term_months        : parseInt(document.getElementById('i-loan-term').value)     || 180,
    credit_score            : parseInt(document.getElementById('i-credit-score').value)  || 650,
    employment_length_years : parseInt(document.getElementById('i-emp-length').value)    || 1,
    employment_type         : document.getElementById('sel-employment-type').value,
    property_area           : document.getElementById('sel-property-area').value,
    prior_defaults          : parseInt(document.getElementById('h-prior-defaults').value) || 0,
    is_ntc                  : isNtc,
    bank_statement_tenure   : tenureSel ? parseInt(tenureSel.value) || 6 : 6,
    average_bank_balance    : abbInput ? parseInt(abbInput.value) || 50000 : 50000,
    utility_repayment_consistency: utilitySel ? utilitySel.value : 'High',
  };
}

// ============================================================
// 7. API Call & Render
// ============================================================
async function runAssessment() {
  const btn = document.getElementById('btn-assess');
  btn.classList.add('loading');
  btn.querySelector('.btn-text').textContent = 'Analysing…';

  const formData = collectFormData();

  try {
    const res    = await fetch('/api/assess', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify(formData),
    });
    const result = await res.json();

    if (result.error) {
      showToast(`Error: ${result.error}`);
      return;
    }

    renderDecisionPanel(result, formData);

  } catch (e) {
    showToast('Network error. Is the Flask server running?');
  } finally {
    btn.classList.remove('loading');
    btn.querySelector('.btn-text').textContent = 'Run Underwriting Assessment';
  }
}

// ============================================================
// 8. Render Decision Panel
// ============================================================
function renderDecisionPanel(result, formData) {
  const panel = document.getElementById('decision-panel');

  // Hide empty state
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.style.display = 'none';

  const { decision, risk_tier, probability, contributions, engineered, counterfactual, applicant } = result;

  const decisionClass = decision === 'Approved' ? 'approved'
                      : decision === 'Conditional Review' ? 'conditional'
                      : 'rejected';

  const iconSvg = {
    approved    : `<polyline points="20 6 9 17 4 12"></polyline>`,
    conditional : `<line x1="12" y1="8" x2="12" y2="12"></line><circle cx="12" cy="16" r="0.5" fill="white" stroke-width="2"></circle><circle cx="12" cy="12" r="10"></circle>`,
    rejected    : `<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>`,
  };

  const dti     = engineered.dti_ratio;
  const dtiPill = dti < 0.36 ? 'pill-low' : dti < 0.50 ? 'pill-mod' : 'pill-high';
  const dtiLbl  = dti < 0.36 ? 'Healthy' : dti < 0.50 ? 'Elevated' : 'Stressed';

  const lti     = engineered.lti_ratio;
  const ltiPill = lti < 2.0 ? 'pill-low' : lti < 4.0 ? 'pill-mod' : 'pill-high';

  const crPill  = applicant.Credit_Score >= 720 ? 'pill-low'
                : applicant.Credit_Score >= 640 ? 'pill-mod' : 'pill-high';
  const crLbl   = applicant.Credit_Score >= 720 ? 'Prime'
                : applicant.Credit_Score >= 640 ? 'Near-Prime' : 'Sub-Prime';

  const riskPill = risk_tier === 'Low' ? 'pill-low' : risk_tier === 'Moderate' ? 'pill-mod' : 'pill-high';

  // --- Decision Banner ---
  const bannerHTML = `
    <div class="decision-banner ${decisionClass}">
      <div class="banner-left">
        <div class="banner-icon">
          <svg viewBox="0 0 24 24">${iconSvg[decisionClass]}</svg>
        </div>
        <div>
          <div class="banner-decision">${decision}</div>
          <div class="banner-sub">Risk Classification: ${risk_tier} Risk</div>
        </div>
      </div>
      <div class="banner-prob">
        <div class="prob-value">${fmt.pct(probability, 0)}</div>
        <div class="prob-label">Approval Probability</div>
      </div>
    </div>`;

  const isNtc = engineered.is_ntc || applicant.is_ntc;

  // --- KPI Cards ---
  const crCardHTML = isNtc
    ? `<div class="kpi-card">
        <div class="kpi-label">Credit Segment</div>
        <div class="kpi-value" style="font-size: 1.05rem;">NTC / Thin-File</div>
        <span class="kpi-pill pill-ntc">${engineered.bank_statement_tenure || 6}-Mo AA Verified</span>
      </div>`
    : `<div class="kpi-card">
        <div class="kpi-label">Credit Segment</div>
        <div class="kpi-value">${applicant.Credit_Score}</div>
        <span class="kpi-pill ${crPill}">${crLbl}</span>
      </div>`;

  const kpiHTML = `
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Monthly EMI</div>
        <div class="kpi-value">${fmt.inr(engineered.estimated_monthly_emi)}</div>
        <div class="kpi-sub">At 9.5% p.a.</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Debt-to-Income</div>
        <div class="kpi-value">${fmt.pct(dti)}</div>
        <span class="kpi-pill ${dtiPill}">${dtiLbl}</span>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Loan-to-Income</div>
        <div class="kpi-value">${lti.toFixed(2)}×</div>
        <span class="kpi-pill ${ltiPill}">${lti < 2 ? 'Conservative' : lti < 4 ? 'Moderate' : 'Aggressive'}</span>
      </div>
      ${crCardHTML}
    </div>`;

  // --- XAI Bar Chart ---
  const barsHTML = contributions.map((c, i) => {
    const val = Number(c.contribution) || 0;
    const isPos = val >= 0;
    const dirClass = isPos ? 'pos' : 'neg';
    const barColor = isPos ? '#166534' : '#B91C1C';
    // Percentage width: min(abs(val) * 3, 50)% as specified
    const calcWidth = Math.min(Math.max(Math.abs(val) * 3, val === 0 ? 0 : 2.5), 50);
    const delay = (i + 1) * 30;
    const posStyle = isPos 
      ? `left: 50%; width: ${calcWidth}%; background-color: #166534;` 
      : `right: 50%; width: ${calcWidth}%; background-color: #B91C1C;`;

    return `
      <div class="bar-row" style="animation-delay:${delay}ms">
        <div class="bar-label" title="${c.display_name}">${c.display_name}</div>
        <div class="bar-track">
          <div class="bar-zero"></div>
          <div class="bar-fill ${dirClass}"
               style="height: 100%; position: absolute; top: 0; z-index: 2; ${posStyle}"
               data-target="${calcWidth}"
               data-dir="${dirClass}"></div>
        </div>
        <div class="bar-value ${dirClass}">${fmt.pp(val)}</div>
      </div>`;
  }).join('');

  const chartSubtitle = isNtc
    ? "Feature contribution analysis via RBI Account Aggregator cash-flow & liquidity metrics"
    : "How each factor shifted this applicant's approval probability from baseline";

  const chartHTML = `
    <div class="chart-card">
      <div class="card-header">
        <div>
          <div class="card-title">Explainable AI — Feature Contributions</div>
          <div class="card-subtitle">${chartSubtitle}</div>
        </div>
      </div>
      <div class="chart-body">
        <div class="chart-legend">
          <div class="legend-item"><div class="legend-dot pos"></div> Increases approval odds</div>
          <div class="legend-item"><div class="legend-dot neg"></div> Decreases approval odds</div>
        </div>
        ${barsHTML}
      </div>
    </div>`;

  // --- Credit Memo ---
  const memo = generateCreditMemo(result, formData, engineered);
  const stampClass = decision === 'Approved' ? 'stamp-approved'
                   : decision === 'Conditional Review' ? 'stamp-conditional'
                   : 'stamp-rejected';
  const memoHTML = `
    <div class="memo-card">
      <div class="memo-header">
        <div>
          <div class="memo-title-block">Automated Underwriter Credit Memorandum</div>
          <div class="memo-meta">Generated · ${new Date().toLocaleDateString('en-IN', {day:'numeric',month:'long',year:'numeric'})} · Veritas Credit Engine v2.0</div>
        </div>
        <div class="memo-stamp ${stampClass}">${decision.toUpperCase()}</div>
      </div>
      <div class="memo-body">${memo}</div>
    </div>`;

  // --- Counterfactual ---
  let cfHTML = '';
  if (counterfactual && counterfactual.length > 0 && decision !== 'Approved') {
    const cfActionIcons = {
      reduce_loan    : `<path d="M3 12h18M3 6h18M3 18h12"/>`,
      improve_credit : `<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>`,
      extend_tenure  : `<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`,
      add_coapplicant: `<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>`,
    };
    const cfItems = counterfactual.map(s => `
      <div class="cf-item">
        <div class="cf-item-icon">
          <svg viewBox="0 0 24 24">${cfActionIcons[s.action] || cfActionIcons.improve_credit}</svg>
        </div>
        <div class="cf-item-text">
          <strong>${s.label}</strong>
          <span>${s.detail}</span>
        </div>
        <div class="cf-new-prob">${fmt.pct(s.new_prob, 0)}</div>
      </div>`).join('');

    cfHTML = `
      <div class="counterfactual-card">
        <div class="cf-header">
          <div class="cf-header-icon">
            <svg viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
          </div>
          <div>
            <div class="cf-title">Path to Approval — What-If Advisor</div>
            <div class="cf-subtitle">Concrete adjustments that would achieve ≥70% approval probability</div>
          </div>
        </div>
        <div class="cf-body">${cfItems}</div>
      </div>`;
  }

  // --- Assemble Panel ---
  panel.innerHTML = bannerHTML + kpiHTML + chartHTML + memoHTML + cfHTML;

  // Animate bars after render
  requestAnimationFrame(() => {
    setTimeout(() => {
      document.querySelectorAll('.bar-fill').forEach(bar => {
        bar.style.width = bar.dataset.target + '%';
      });
    }, 100);
  });

  // Scroll to results on mobile
  if (window.innerWidth <= 1100) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ============================================================
// 9. Credit Memo Generator
// ============================================================
function generateCreditMemo(result, formData, engineered) {
  const { decision, risk_tier, probability, applicant } = result;
  const isNtc = engineered.is_ntc || applicant.is_ntc;
  const dti = engineered.dti_ratio;
  const lti = engineered.lti_ratio;
  const emi = engineered.estimated_monthly_emi;
  const totalIncome = engineered.total_monthly_income;

  const empType = applicant.Employment_Type;
  const area    = applicant.Property_Area;
  const cs      = applicant.Credit_Score;
  const defaults = applicant.Prior_Defaults;

  // Income quality
  const incomeQuality = empType === 'Salaried' ? 'stable, verifiable salaried income'
                      : empType === 'Self-Employed' ? 'self-reported business income (higher verification threshold applies)'
                      : 'business owner income (subject to 2-year ITR verification)';

  // Credit narrative in Section I
  const creditNarr = isNtc
    ? `no prior bureau history (<strong>New-to-Credit / Thin-File</strong>) and has been evaluated via <strong>RBI Account Aggregator cash-flow analysis</strong>`
    : (cs >= 750 ? `an excellent credit score of <strong>${cs}</strong>, indicating a strong repayment history and low credit utilisation`
       : cs >= 700 ? `a good credit score of <strong>${cs}</strong>, reflecting adequate creditworthiness with minor blemishes`
       : cs >= 640 ? `a near-prime credit score of <strong>${cs}</strong>, indicating moderate credit risk and potential gaps in repayment history`
       : `a sub-prime credit score of <strong>${cs}</strong>, which raises material concerns regarding historical repayment discipline`);

  // DTI narrative
  const dtiNarr = dti < 0.36 ? `The applicant's Debt-to-Income Ratio of <strong>${fmt.pct(dti)}</strong> is well within the institutional threshold of 43%, indicating robust debt-service capacity.`
                : dti < 0.50 ? `The Debt-to-Income Ratio of <strong>${fmt.pct(dti)}</strong> is elevated but remains within the acceptable range. Close monitoring of cash-flow adequacy is recommended.`
                : `The Debt-to-Income Ratio of <strong>${fmt.pct(dti)}</strong> materially exceeds prudent lending thresholds (43%), indicating significant financial stress and limited surplus for debt servicing.`;

  // Default narrative / Section III content
  let sectionIIIContent = '';
  if (isNtc) {
    const tenureMonths = engineered.bank_statement_tenure || applicant.bank_statement_tenure || 6;
    const windowName = tenureMonths === 6 ? '6-month (Salaried)' : '12-month (Self-Employed)';
    const abbVal = engineered.average_bank_balance || applicant.average_bank_balance || 50000;
    const lcrVal = engineered.lcr ? `${engineered.lcr.toFixed(1)}×` : `${(abbVal / Math.max(emi, 1)).toFixed(1)}×`;
    const consistency = engineered.utility_consistency || applicant.utility_repayment_consistency || 'High';

    sectionIIIContent = `
      <p class="memo-text">
        <strong>Prior Bureau History: Thin-File / New-to-Credit (CIBIL Score: NH / -1).</strong> In accordance with RBI Account Aggregator (AA) cash-flow underwriting guidelines, evaluation was conducted using the applicant's verified <strong>${windowName}</strong> bank statement history. The applicant maintains an Average Monthly Balance (ABB) of <strong>${fmt.inr(abbVal)}</strong> (<strong>${lcrVal}</strong> of proposed EMI) alongside <strong>${consistency}</strong> utility and digital payment regularity.
      </p>`;

    if (engineered.tenure_deficit) {
      sectionIIIContent += `
        <p class="memo-text" style="color: #991B1B; margin-top: 8px;">
          <strong>Lookback Verification Warning:</strong> Applicant is ${empType} but submitted only 6 months of bank statement history against the mandatory 12-month lookback requirement for non-salaried borrowers. A risk haircut (-8.0pp) has been applied; full sanction requires obtaining the full 12-month statement history via AA consent.
        </p>`;
    }
  } else {
    const defaultNarr = defaults === 1
      ? `<strong>Prior Default History: Adverse.</strong> The applicant has a documented record of loan default, which substantially elevates the credit risk profile and triggers enhanced due-diligence protocols.`
      : `<strong>Prior Default History: Clean.</strong> No adverse credit events on record.`;
    sectionIIIContent = `<p class="memo-text">${defaultNarr}</p>`;
  }

  // Section IV: Underwriting Decision narrative (fully consistent with Sections I-III)
  const isHighLeverage = dti > 0.43;
  const isSubprimeOrNear = cs < 680;
  let decisionNarrative = '';

  if (isNtc) {
    if (decision === 'Approved') {
      decisionNarrative = `
        <p class="memo-text">Based on verified <strong>Account Aggregator cash-flow liquidity</strong> and debt-service capacity, this New-to-Credit application is recommended for <strong>approval</strong>. The applicant exhibits a healthy Average Monthly Balance (ABB: <strong>${fmt.inr(engineered.average_bank_balance)}</strong>, covering <strong>${engineered.lcr ? engineered.lcr.toFixed(1) : '3.0'}×</strong> of proposed monthly EMI), manageable leverage (DTI: <strong>${fmt.pct(dti)}</strong>), and flawless payment discipline. The computed approval probability of <strong>${fmt.pct(probability, 0)}</strong> satisfies institutional NTC cash-flow underwriting criteria.</p>`;
    } else if (decision === 'Conditional Review') {
      decisionNarrative = `
        <p class="memo-text">This New-to-Credit application is referred for <strong>Conditional Review / Exception Underwriting</strong>. While cash-flow metrics indicate viable capacity, ${engineered.tenure_deficit ? 'the non-salaried statement tenure deficit (6 mo vs 12 mo required)' : isHighLeverage ? `an elevated DTI of <strong>${fmt.pct(dti)}</strong>` : 'moderate liquidity coverage'} requires risk-mitigating stipulations. Sanction is contingent upon securing an automated NACH auto-debit mandate and verifying continuous account surplus.</p>`;
    } else {
      decisionNarrative = `
        <p class="memo-text">This New-to-Credit application is recommended for <strong>decline</strong>. Insufficient cash-flow buffer relative to requested EMI obligations (ABB: <strong>${fmt.inr(engineered.average_bank_balance)}</strong>) alongside leverage indicators depresses the computed approval probability to <strong>${fmt.pct(probability, 0)}</strong>, breaching institutional NTC risk tolerance limits.</p>`;
    }
  } else {
    if (decision === 'Approved') {
      if (!isHighLeverage && !isSubprimeOrNear && defaults === 0) {
        decisionNarrative = `
          <p class="memo-text">Based on the aggregate credit assessment, this application is recommended for <strong>unconditional approval</strong>. The applicant demonstrates sufficient income stability, healthy leverage ratios (DTI: <strong>${fmt.pct(dti)}</strong>), and an established prime credit profile (Score: <strong>${cs}</strong>). The computed approval probability of <strong>${fmt.pct(probability, 0)}</strong> comfortably exceeds the institution's acceptance threshold.</p>`;
      } else {
        decisionNarrative = `
          <p class="memo-text">Based on overall repayment capacity, this application is recommended for <strong>Conditional Approval with Covenants</strong>. While baseline cash flow supports the commitment, the ${isHighLeverage ? `elevated Debt-to-Income ratio of <strong>${fmt.pct(dti)}</strong>` : ''}${isHighLeverage && isSubprimeOrNear ? ' and ' : ''}${isSubprimeOrNear ? `marginal credit score of <strong>${cs}</strong>` : ''} warrant prudent risk-mitigating stipulations. Formal sanction is contingent upon verifying 6 months of banking surplus and obtaining an automated NACH auto-debit mandate before loan disbursal.</p>`;
      }
    } else if (decision === 'Conditional Review') {
      decisionNarrative = `
        <p class="memo-text">This application is referred to the credit underwriting committee for <strong>Conditional Review / Exception Underwriting</strong>. Significant risk factors—specifically ${isHighLeverage ? `a stressed DTI of <strong>${fmt.pct(dti)}</strong> (above benchmark 43%)` : ''}${isHighLeverage && isSubprimeOrNear ? ' and ' : ''}${isSubprimeOrNear ? `a sub-prime credit score of <strong>${cs}</strong>` : ''}${defaults ? ' alongside documented prior default history' : ''}—preclude automatic sanction. Committee review will determine whether structured covenants (such as extending tenure or securing a prime co-borrower) can sufficiently mitigate default exposure before a final commitment is rendered.</p>`;
    } else {
      decisionNarrative = `
        <p class="memo-text">This application is recommended for <strong>decline</strong>. The accumulation of material risk drivers—including ${isHighLeverage ? `an unsustainable DTI of <strong>${fmt.pct(dti)}</strong>` : ''}${isHighLeverage && isSubprimeOrNear ? ', ' : ''}${isSubprimeOrNear ? `a sub-prime credit score of <strong>${cs}</strong>` : ''}${defaults ? ', and documented prior default history' : ''}—depresses the computed approval probability to <strong>${fmt.pct(probability, 0)}</strong>, breaching institutional risk tolerance limits. The applicant is advised to consult the Path to Approval advisor below for recommended adjustments before reapplying.</p>`;
    }
  }

  return `
    <div class="memo-section">
      <div class="memo-section-title">I. Applicant Financial Summary</div>
      <p class="memo-text">
        The applicant reports ${incomeQuality} of <strong>${fmt.inr(applicant.Applicant_Income)}/month</strong>
        ${applicant.Coapplicant_Income > 0 ? `with a co-applicant contributing <strong>${fmt.inr(applicant.Coapplicant_Income)}/month</strong>, yielding a combined household income of <strong>${fmt.inr(totalIncome)}/month</strong>` : `with no co-applicant, resulting in a total assessed income of <strong>${fmt.inr(totalIncome)}/month</strong>`}.
        The applicant has been in employment for <strong>${applicant.Employment_Length_Years} year${applicant.Employment_Length_Years !== 1 ? 's' : ''}</strong>
        and is located in a <strong>${area}</strong> property area.
        The applicant carries ${creditNarr}.
      </p>
    </div>

    <div class="memo-section">
      <div class="memo-section-title">II. Debt Service & Leverage Analysis</div>
      <p class="memo-text">
        The requested loan of <strong>${fmt.inr(applicant.Loan_Amount)}</strong> over a tenure of
        <strong>${applicant.Loan_Term_Months} months</strong> generates an estimated monthly EMI of
        <strong>${fmt.inr(emi)}</strong> at the applicable rate of 9.5% p.a.
        Combined with existing monthly obligations of <strong>${fmt.inr(applicant.Existing_Monthly_Debt)}</strong>,
        the applicant's total monthly debt burden is <strong>${fmt.inr(applicant.Existing_Monthly_Debt + emi)}</strong>.
        ${dtiNarr}
        The Loan-to-Annual-Income Ratio (LTI) stands at <strong>${lti.toFixed(2)}×</strong>
        ${lti < 2 ? '(conservative leverage)' : lti < 4 ? '(moderate leverage — within policy)' : '(aggressive leverage — exceeds policy limits)'}.
      </p>
    </div>

    <div class="memo-section">
      <div class="memo-section-title">III. Credit History Assessment</div>
      ${sectionIIIContent}
    </div>

    <div class="memo-section">
      <div class="memo-section-title">IV. Underwriting Decision</div>
      ${decisionNarrative}
    </div>`;
}

// ============================================================
// 10. Model Governance Modal
// ============================================================
async function openGovernanceModal() {
  const overlay = document.getElementById('governance-modal');
  overlay.classList.add('active');

  const content = document.getElementById('modal-metrics-content');
  content.innerHTML = '<p style="color:var(--text-tertiary);font-size:0.85rem;">Loading model validation report…</p>';

  try {
    const res  = await fetch('/api/metrics');
    const data = await res.json();
    content.innerHTML = renderMetrics(data);
  } catch (e) {
    content.innerHTML = '<p style="color:var(--status-rej-text)">Failed to load metrics.</p>';
  }
}

function renderMetrics(d) {
  const cm = d.confusion_matrix || [[0,0],[0,0]];
  const tn = cm[0][0], fp = cm[0][1], fn = cm[1][0], tp = cm[1][1];

  return `
    <div class="metrics-grid">
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.roc_auc * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">ROC-AUC</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.accuracy * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">Accuracy</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.f1_score * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">F1 Score</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.precision * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">Precision</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.recall * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">Recall</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile-val">${(d.cv_roc_auc_mean * 100).toFixed(1)}%</div>
        <div class="metric-tile-label">5-Fold CV AUC</div>
      </div>
    </div>

    <hr class="section-divider">

    <div class="memo-section-title" style="margin-bottom:12px;">Confusion Matrix (Hold-out Test Set)</div>
    <div class="confusion-grid">
      <div class="cm-cell tp"><div class="cm-val">${tp}</div><div class="cm-label">True Approve</div></div>
      <div class="cm-cell fp"><div class="cm-val">${fp}</div><div class="cm-label">False Approve</div></div>
      <div class="cm-cell fn"><div class="cm-val">${fn}</div><div class="cm-label">Missed Approve</div></div>
      <div class="cm-cell tn"><div class="cm-val">${tn}</div><div class="cm-label">True Decline</div></div>
    </div>

    <hr class="section-divider">

    <div class="info-row">
      <div class="info-row-label">Data Source</div>
      <div class="info-row-value">${d.data_source}</div>
    </div>
    <div class="info-row">
      <div class="info-row-label">Model Architecture</div>
      <div class="info-row-value">${d.model_type}<br>
        <small style="color:var(--text-tertiary)">300 estimators · lr=0.05 · max_depth=4 · Platt calibration</small></div>
    </div>
    <div class="info-row">
      <div class="info-row-label">Training Split</div>
      <div class="info-row-value">${d.n_train} train / ${d.n_test} test (75/25 stratified)</div>
    </div>
    <div class="info-row">
      <div class="info-row-label">Approval Rate</div>
      <div class="info-row-value">${(d.approval_rate * 100).toFixed(1)}% of real historical applications approved</div>
    </div>
    <div class="info-row">
      <div class="info-row-label">CV AUC (±σ)</div>
      <div class="info-row-value">${(d.cv_roc_auc_mean * 100).toFixed(2)}% ± ${(d.cv_roc_auc_std * 100).toFixed(2)}%</div>
    </div>
    <div class="info-row">
      <div class="info-row-label">XAI Method</div>
      <div class="info-row-value">Manual feature-perturbation SHAP proxy<br>
        <small style="color:var(--text-tertiary)">Each feature contribution = P(approve | applicant) − P(approve | feature set to mean)</small></div>
    </div>
    <div class="info-row">
      <div class="info-row-label">Compliance Note</div>
      <div class="info-row-value" style="color:var(--text-secondary)">This system is designed for educational use. All decisions are explainable and auditable per fair-lending guidelines. Protected characteristics (gender, religion, caste) are excluded from the feature set.</div>
    </div>`;
}

// ============================================================
// 11. Boot
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  // Sliders
  initAllSliders();

  // Toggles
  initDefaultToggle();
  initNtcToggle();
  initStatementIngestion();

  // Persona dropdown
  const personaSelect = document.getElementById('persona-select');
  if (personaSelect) {
    personaSelect.addEventListener('change', () => {
      loadPersona(personaSelect.value);
      personaSelect.value = ''; // reset
    });
  }

  // Assess button
  document.getElementById('btn-assess').addEventListener('click', runAssessment);

  // Governance modal
  document.getElementById('btn-governance').addEventListener('click', openGovernanceModal);
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('governance-modal').classList.remove('active');
  });
  document.getElementById('governance-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
      e.currentTarget.classList.remove('active');
    }
  });

  // Keyboard: Escape closes modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.getElementById('governance-modal').classList.remove('active');
    }
  });

  // Auto-run with default values on page load after short delay
  setTimeout(() => document.getElementById('btn-assess').click(), 600);
});
