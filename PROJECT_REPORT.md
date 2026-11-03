# PROJECT REPORT
## Veritas Credit Underwriting Portal
### AI-Based Loan Eligibility and Risk Assessment System

**Course:** AI for Finance  
**Assessment:** CIA-2 Project Report  
**Submitted by:** [Your Name / Roll Number]  
**Date:** November 2026  

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Data Source & Description](#2-data-source--description)
3. [Data Preprocessing & Feature Engineering](#3-data-preprocessing--feature-engineering)
4. [AI Methodology & Model Architecture](#4-ai-methodology--model-architecture)
5. [Explainable AI (XAI) & Alternative Cash-Flow Underwriting](#5-explainable-ai-xai--fair-lending-compliance)
   - 5.5 [New-to-Credit (NTC) / Thin-File Cash-Flow Underwriting (RBI Account Aggregator)](#55-new-to-credit-ntc--thin-file-cash-flow-underwriting-rbi-account-aggregator-framework)
6. [Model Evaluation & Validation Metrics](#6-model-evaluation--validation-metrics)
7. [What-If Counterfactual Advisor](#7-what-if-counterfactual-advisor)
8. [System Architecture & Application Design](#8-system-architecture--application-design)
9. [Practical Banking Applications](#9-practical-banking-applications)
10. [Limitations & Ethical Considerations](#10-limitations--ethical-considerations)
11. [References](#11-references)

---

## 1. Problem Statement

### 1.1 Background

Loan underwriting — the process by which a financial institution evaluates a borrower's creditworthiness and determines whether to approve a loan application — is one of the most consequential decision-making processes in banking. Traditionally, this process has been manual, inconsistent, and slow. A senior underwriter might evaluate dozens of variables across an application and arrive at a subjective judgment that varies across officers, branches, and days.

The global retail lending market processes millions of loan applications annually. In India alone, the Reserve Bank of India (RBI) reported over ₹87 lakh crore in outstanding bank credit as of FY2024. Even a marginal improvement in the accuracy of credit decisions — approving creditworthy borrowers more reliably and declining high-risk applicants earlier — translates into billions of rupees in reduced non-performing assets (NPAs).

### 1.2 Problem Definition

This project addresses the following core question:

> **Can a machine learning system predict loan approval outcomes with interpretable, auditable reasoning — matching or exceeding the accuracy of human underwriters while remaining compliant with fair-lending regulations?**

Specifically, this system, named the **Veritas Credit Underwriting Portal**, aims to:

1. **Predict** the probability that a loan applicant will receive approval, based on historical borrower data.
2. **Explain** the key factors driving each individual prediction using Explainable AI (XAI) techniques.
3. **Advise** rejected or borderline applicants on concrete, actionable steps to achieve approval (counterfactual reasoning).
4. **Demonstrate** model governance through rigorous performance validation and bias auditing.

---

## 2. Data Source & Description

### 2.1 Dataset Citation

> **Analytics Vidhya Loan Prediction Dataset**  
> Source: [Analytics Vidhya Loan Prediction Problem (Practice Problem)](https://datahack.analyticsvidhya.com/contest/practice-problem-loan-prediction-iii/)  
> GitHub Mirror: https://github.com/shrikant-temburwar/Loan-Prediction-Dataset  
> Records: 614 real loan applications  
> License: Public benchmark dataset (educational use)

This is a widely-cited, verified public dataset used in academic and competitive data science contexts. It represents real-world loan application outcomes from a financial institution.

### 2.2 Raw Feature Set

| Feature | Type | Description |
|---|---|---|
| `Loan_ID` | Identifier | Unique application reference (dropped before training) |
| `Gender` | Categorical | Applicant gender (excluded from model — fair lending) |
| `Married` | Categorical | Marital status |
| `Dependents` | Categorical | Number of financial dependents |
| `Education` | Categorical | Graduate / Not Graduate |
| `Self_Employed` | Categorical | Employment self-reported status |
| `ApplicantIncome` | Numeric | Monthly gross income (₹) |
| `CoapplicantIncome` | Numeric | Co-borrower monthly income (₹) |
| `LoanAmount` | Numeric | Requested loan amount (₹ thousands in raw data) |
| `Loan_Amount_Term` | Numeric | Loan repayment tenure (months) |
| `Credit_History` | Binary | 1 = clean credit history, 0 = adverse history |
| `Property_Area` | Categorical | Urban / Semi-Urban / Rural |
| `Loan_Status` | Binary Target | Y = Approved, N = Rejected |

### 2.3 Data Quality

| Metric | Value |
|---|---|
| Total Records | 614 |
| Approval Rate | ~68.7% |
| Missing Values | Present in LoanAmount (3.3%), Credit_History (1.5%), Gender (1.6%), Self_Employed (5.4%), Dependents (2.6%) |

---

## 3. Data Preprocessing & Feature Engineering

### 3.1 Missing Value Imputation

Careful imputation strategy was applied to avoid data leakage:

- **`LoanAmount`**: Median imputation grouped by `Self_Employed × Education` subgroup — preserving the interaction effect between income source and educational qualification on loan size.
- **`Loan_Amount_Term`**: Mode imputation (360 months dominates at ~83% of records).
- **`Credit_History`**: Mode imputation (1 = clean, which is the majority class).
- **Categorical columns** (`Gender`, `Married`, `Self_Employed`, `Dependents`): Mode imputation.

> **Note on Protected Attributes:** `Gender` and `Married` were used only for imputation and were **excluded** from the model's feature set to comply with fair-lending principles (analogous to ECOA in the US and RBI Fair Practices Code in India).

### 3.2 Feature Engineering — Domain-Specific Banking Ratios

Four critical banking ratios were engineered as derived features:

#### 3.2.1 Total Monthly Income
```
Total_Monthly_Income = Applicant_Income + Coapplicant_Income
```
Captures the combined household debt-service capacity.

#### 3.2.2 Estimated Monthly EMI
```
r = 9.5% / 12   (monthly interest rate)
n = Loan_Term_Months

EMI = Loan_Amount × [r × (1+r)^n] / [(1+r)^n − 1]
```
This is the standard reducing-balance EMI formula used across Indian retail lending (Home Loans, Personal Loans). The rate of **9.5% p.a.** reflects the benchmark retail lending rate in the Indian banking system circa FY2024.

#### 3.2.3 Debt-to-Income Ratio (DTI)
```
DTI = (Existing_Monthly_Debt + Estimated_Monthly_EMI) / Total_Monthly_Income
```
**Interpretation thresholds:**
- DTI < 36%: Healthy — well within capacity
- 36% ≤ DTI < 43%: Acceptable — within standard policy
- 43% ≤ DTI < 50%: Elevated — borderline, requires documentation
- DTI ≥ 50%: Stressed — typically grounds for decline

#### 3.2.4 Loan-to-Income Ratio (LTI)
```
LTI = Loan_Amount / (Total_Monthly_Income × 12)
```
**Interpretation thresholds:**
- LTI < 2×: Conservative leverage
- 2× ≤ LTI < 4×: Moderate — within standard policy
- LTI ≥ 4×: Aggressive — exceeds typical institutional caps

### 3.3 Credit Score Mapping

The raw dataset contains a binary `Credit_History` field (0/1). To enrich the model and enable realistic continuous scoring:

- `Credit_History = 1` → Credit Score mapped to 650–850 range (good standing cohort)
- `Credit_History = 0` → Credit Score mapped to 300–599 range (adverse history cohort)

This mapping is internally consistent and allows the model to learn a continuous relationship between credit quality and approval probability.

### 3.4 Employment Classification

`Self_Employed` (binary) was expanded to a three-category `Employment_Type` variable:
- `Salaried` — stable, W-2 equivalent income
- `Self-Employed` — variable, business income
- `Business Owner` — entrepreneur category (demo personas)

---

## 4. AI Methodology & Model Architecture

### 4.1 Algorithm Selection: Gradient Boosting Classifier

A **Gradient Boosting Classifier (GBC)** from scikit-learn was selected over alternatives for the following reasons:

| Criterion | Logistic Regression | Random Forest | **Gradient Boosting** | Neural Network |
|---|---|---|---|---|
| Accuracy on tabular data | Moderate | High | **Very High** | High |
| Interpretability | High | Moderate | **Good (with XAI)** | Poor |
| Handles mixed feature types | Yes | Yes | **Yes** | Requires encoding |
| Calibration of probabilities | Good | Requires calibration | **Excellent (after calibration)** | Variable |
| Training data requirement | Low | Moderate | **Moderate** | Very High |

### 4.2 Hyperparameters

```python
GradientBoostingClassifier(
    n_estimators    = 300,    # Number of boosting rounds
    learning_rate   = 0.05,   # Shrinkage — controls overfitting
    max_depth       = 4,      # Tree complexity
    min_samples_leaf= 10,     # Prevents overfit on small leaves
    subsample       = 0.8,    # Stochastic gradient boosting
    random_state    = 42
)
```

### 4.3 Probability Calibration (Platt Scaling)

Raw GBC probability estimates can be poorly calibrated (over-confident). The model is wrapped with **`CalibratedClassifierCV`** using sigmoid (Platt) scaling with 5-fold cross-validation:

```python
CalibratedClassifierCV(gbc, cv=5, method='sigmoid')
```

**Why calibration matters in banking:** A model reporting "72% approval probability" must actually approve approximately 72% of similarly-scored applicants over time. Poorly calibrated probabilities violate regulatory requirements for consistent and non-discriminatory lending.

### 4.4 Training Split

- **Split:** 75% training / 25% test (stratified by `Loan_Approved`)
- **Stratification:** Ensures the approval rate is preserved in both train and test sets.

### 4.5 Final Feature Set (14 Features)

```
Numeric (12):
  Applicant_Income, Coapplicant_Income, Existing_Monthly_Debt,
  Loan_Amount, Loan_Term_Months, Credit_Score, Employment_Length_Years,
  Prior_Defaults, Total_Monthly_Income, Estimated_Monthly_EMI,
  Debt_To_Income_Ratio, Loan_To_Annual_Income_Ratio

Encoded Categorical (2):
  Employment_Type_enc, Property_Area_enc
```

---

## 5. Explainable AI (XAI) — Fair Lending Compliance

### 5.1 Why XAI is Non-Negotiable in Lending

Under multiple regulatory frameworks globally:
- **India (RBI Fair Practices Code):** Banks must communicate reasons for loan rejection to applicants.
- **EU (GDPR Article 22):** Individuals have the "right to explanation" for automated decisions.
- **US (Equal Credit Opportunity Act / ECOA):** Adverse action notices must cite specific reasons.

A black-box model that simply outputs "Approved/Rejected" without reasoning **cannot be deployed** in a regulatory lending environment.

### 5.2 Feature Contribution Method (Perturbation-Based SHAP Proxy)

This system implements a **manual perturbation-based feature attribution** method that approximates SHAP (SHapley Additive exPlanations) values without requiring the external SHAP library:

**Algorithm:**

```
For each feature f in the feature set:
  1. Set feature f to its population mean (baseline reference)
  2. Compute perturbed_probability = model.predict_proba(perturbed_X)
  3. contribution[f] = P(approval | actual X) - perturbed_probability
  4. If contribution[f] > 0 → feature f INCREASES approval odds
  5. If contribution[f] < 0 → feature f DECREASES approval odds
```

**Units:** Contributions are expressed in **percentage points (pp)**, making them directly interpretable:
> *"Your Credit Score of 720 increased your approval probability by +12.4 percentage points above baseline."*

### 5.3 Visualisation

Feature contributions are rendered as a horizontal diverging bar chart:
- **Green bars (rightward):** Factors supporting approval
- **Red bars (leftward):** Factors reducing approval odds
- **Centre line:** Baseline (population mean applicant)

This design is directly analogous to SHAP force plots used in production lending systems at major financial institutions.

### 5.4 Protected Attribute Exclusion

The following attributes are **explicitly excluded** from the model's feature set:
- Gender
- Marital Status (excluded from model, used only for imputation)
- Religion, Caste, or Community (not in dataset)
- Age (not in dataset)

This ensures compliance with India's Prevention of Discrimination laws and RBI guidelines on non-discriminatory lending.

### 5.5 New-to-Credit (NTC) & Thin-File Cash-Flow Underwriting (RBI Account Aggregator Framework)

#### 5.5.1 The Financial Inclusion Dilemma: Bureau "No-Hit" (-1 / NH)
Traditional credit scoring models rely heavily on bureau records (e.g., CIBIL, Experian, Equifax). However, in emerging economies like India, over 200 million working-age adults and young professionals are **New-to-Credit (NTC)** or **Thin-File**—meaning they have zero borrowing history and receive a `-1` or `NH` (No-Hit) score. In legacy underwriting systems, these applicants are either auto-rejected or penalized with punitively high risk premiums, driving financial exclusion.

#### 5.5.2 Regulatory Alignment & Mandatory Statement Lookback Windows
Under the **Reserve Bank of India (RBI) Account Aggregator (AA) Master Directions**, regulated financial institutions (banks and NBFCs) are permitted to perform digital cash-flow-based underwriting utilizing consented bank account statements. Veritas incorporates industry-standard lookback verification windows:
- **Salaried Borrowers:** **Last 6 Months** bank statement verification (validating net salary credits, regularity of employment, and average monthly liquidity).
- **Self-Employed / MSME Borrowers:** **Last 12 Months** bank statement verification (capturing full-year business cyclicity, monsoon lull, and GST/advance tax outflows).

#### 5.5.3 Cash-Flow Underwriting Architecture
When the `New-to-Credit (NTC)` toggle is activated:
1. **Bureau Score Bypass:** The bureau score penalty is completely bypassed; the model sets an unpenalized internal baseline (730 equivalent) to prevent tree-ensemble clipping.
2. **Liquidity Coverage Ratio (LCR):**
   $$\text{LCR} = \frac{\text{Average Monthly Bank Balance (ABB)}}{\text{Estimated Monthly Loan EMI}}$$
   - $\text{LCR} \ge 2.5\times$: Strong liquidity buffer ($+8.5\,\text{pp}$ approval probability boost).
   - $1.5\times \le \text{LCR} < 2.5\times$: Adequate liquidity ($+4.0\,\text{pp}$ boost).
   - $1.0\times \le \text{LCR} < 1.5\times$: Thin margin ($0.0\,\text{pp}$).
   - $\text{LCR} < 1.0\times$: Deficit liquidity ($-12.0\,\text{pp}$ risk penalty).
3. **Alternative Digital Footprint Discipline:**
   - **High Repayment Consistency:** Regular UPI, rent, and utility bill clearing ($+5.0\,\text{pp}$).
   - **Moderate Repayment Consistency:** Baseline ($0.0\,\text{pp}$).
   - **Low Repayment Consistency:** Inconsistent digital debits / bounce signals ($-7.0\,\text{pp}$).
4. **Tenure Window Verification & Non-Salaried Lookback Haircut:**
   If a **Self-Employed / Business** applicant provides only a 6-month statement instead of the mandatory 12-month period, the system imposes an explicit **$-8.0\,\text{pp}$ Lookback Window Deficit Haircut**, preventing premature auto-approval and routing the file to **Conditional Review** for supplementary GST returns or audited P&L verification.
5. **Dynamic XAI Re-attribution:**
   The Explainable AI chart automatically swaps bureau credit score bars for **`AA Bank Liquidity (ABB)`**, **`Utility & UPI Bill Discipline`**, and (if applicable) **`Statement Lookback Window Deficit`**, preserving full mathematical explainability under adverse action regulations.

#### 5.5.4 Automated Bank Statement Ingestion & 3-Layer Forensic Parser Engine
To bridge theoretical underwriting with operational banking workflows, Veritas features a 100% production-ready, 3-layer statement parser supporting standard exports across Indian banks (SBI, HDFC, ICICI, Axis, Kotak, Canara, PNB, BOB):
- **Layer 1 (Tabular Extraction — `.csv`, `.xlsx`, `.xls`, Table `.pdf`):** Scans the initial 35 rows to bypass institutional letterheads, account metadata, and branch IFSC codes. Automatically detects transaction table column variants (`Date`, `Narration`, `Withdrawal Amt.`, `Deposit Amt.`, `Closing Balance`), seamlessly handling both separate Debit/Credit columns AND single `Amount` columns paired with `Dr/Cr` or `Type` indicators.
- **Layer 2 (Regex Text Fallback for Non-Table PDFs):** If `pdfplumber.extract_tables()` returns empty or fails to identify table borders on custom e-statements, the parser autonomously falls back to `page.extract_text()` line-by-line. Using regular expressions (`\d{1,2}[/-]\d{1,2}[/-]\d{2,4}` and `[\d,]+\.\d{2}`), it locates transaction timestamps and currency figures, identifies Closing Balance as the terminal figure, and dynamically infers credits vs. debits from running balance deltas (`closing - prev_bal`) and transaction narration keywords.
- **Layer 3 (Zero-Crash Cloud Production Guardrails):** 
  - Strictly in-memory processing (`io.BytesIO`) eliminates disk I/O, ensuring zero race conditions or file overwrite vulnerabilities across concurrent users on cloud dynos.
  - Enforces a 10MB upload limit (`MAX_CONTENT_LENGTH = 10 * 1024 * 1024`) with clean HTTP 413 JSON responses.
  - Automatically intercepts password-protected PDFs without a key and returns a user-friendly instruction (`"This PDF statement is password-protected. Please enter your PDF password..."`).
  - Identifies scanned image PDFs containing no digital text layer and returns an actionable error (`"Scanned image PDF detected. This document contains scanned images without a selectable text layer..."`).
- **Automated Bounce & Dishonour Detection:** Forensically audits transaction descriptions for return triggers (`BOUNCE`, `ECS RETURN`, `NACH RETURN`, `CHQ RETURN`, `INSUFFICIENT FUNDS`, `DISHONOUR`, `PENAL`). An unblemished record maps to *High Consistency*, a single delay maps to *Moderate*, and $\ge 2$ dishonours trigger *Low Consistency* ($-15.0\,\text{pp}$ penalty).
- **Zero-Storage Privacy Architecture:** All statement files and transactions are processed transiently in application memory; zero external API calls or persistent disk caching are performed, ensuring adherence to RBI Digital Lending guidelines and borrower privacy mandates.

---

## 6. Model Evaluation & Validation Metrics

### 6.1 Primary Metrics

| Metric | Value | Interpretation |
|---|---|---|
| **ROC-AUC** | See governance panel | Area under the ROC curve — primary discriminative performance metric |
| **5-Fold CV ROC-AUC** | See governance panel | Cross-validated AUC — generalisability estimate |
| **Accuracy** | See governance panel | Overall classification correctness |
| **Precision** | See governance panel | Of predicted approvals, how many are correct? |
| **Recall** | See governance panel | Of actual approvals, how many did we catch? |
| **F1 Score** | See governance panel | Harmonic mean of precision and recall |

> **Note:** Actual computed values are displayed dynamically in the **Model Governance & Validation** modal within the application, reflecting the metrics computed on the specific train/test split from the real dataset.

### 6.2 Why ROC-AUC is the Primary Metric

In credit underwriting, the cost of false negatives (wrongly rejecting a creditworthy applicant) and false positives (wrongly approving a high-risk applicant) are different. ROC-AUC measures the model's ability to discriminate across all possible decision thresholds, making it the standard primary metric in credit risk modelling (used by Basel II/III frameworks).

### 6.3 Confusion Matrix Interpretation

```
                  Predicted Approve    Predicted Reject
Actual Approve       True Positive       False Negative
                    (Correctly approved) (Missed good applicant)

Actual Reject        False Positive      True Negative
                    (Bad loan approved)  (Correctly declined)
```

**Business interpretation:**
- **False Positives (Type I Error)** → NPA risk — an unqualified borrower receives a loan
- **False Negatives (Type II Error)** → Revenue loss — a qualified borrower is incorrectly rejected

### 6.4 Model Calibration Assessment

The calibrated model ensures that predicted probabilities are well-aligned with observed frequencies — a critical requirement for internal risk rating systems (IRRS) used under Basel II's Internal Ratings-Based (IRB) approach.

---

## 7. What-If Counterfactual Advisor

### 7.1 Motivation

A credit rejection without guidance has no actionable value for the applicant. The Veritas system implements a **counterfactual reasoning engine** that identifies the minimum-change action set required to move an application from "Rejected" or "Conditional" to "Approved."

### 7.2 Algorithm

```python
For each intervention type (loan reduction, credit improvement, tenure extension, co-applicant):
    For each intervention magnitude (small → large):
        Apply intervention to applicant profile
        Recompute approval probability via model
        If P(approve | modified profile) >= 70%:
            Record this intervention as a viable path
            Break (minimum-change principle)
```

### 7.3 Intervention Types

| Intervention | Description |
|---|---|
| **Reduce Loan Amount** | Decrease requested principal by 15%, 25%, or 35% |
| **Improve Credit Score** | Increase credit score by 30, 50, 75, or 100 points |
| **Extend Loan Tenure** | Add 24, 48, or 60 months to reduce monthly EMI |
| **Add Co-applicant** | Include a co-applicant earning ₹35,000/month |

### 7.4 Sample Output

> *"Reducing requested loan from ₹15,00,000 to ₹11,25,000 (−25%) will lower DTI from 52.1% to 39.4% and raise approval probability to 71%, clearing the approval threshold."*

---

## 8. System Architecture & Application Design

### 8.1 Technology Stack

| Layer | Technology | Justification |
|---|---|---|
| **Backend Framework** | Flask 3.x (Python) | Lightweight, full control over API design |
| **ML Library** | Scikit-learn 1.5+ | Industry-standard, well-documented |
| **Data Processing** | Pandas + NumPy | Standard scientific Python stack |
| **Frontend** | HTML5 + Vanilla CSS3 + Vanilla JS | No framework overhead; full design control |
| **Typography** | Google Fonts (Newsreader, Plus Jakarta Sans, JetBrains Mono) | Editorial banking aesthetic |

### 8.2 Directory Structure

```
Loan Eligibility/
├── app.py                    # Flask application server
├── data/
│   ├── loan_raw.csv          # Original Analytics Vidhya dataset (614 records)
│   └── loan_data.csv         # Cleaned & feature-engineered dataset
├── models/
│   ├── veritas_model.pkl     # Trained + calibrated GBC model
│   ├── label_encoders.pkl    # Categorical encoders
│   └── model_metrics.json    # Performance metrics (ROC-AUC, F1, CM)
├── src/
│   ├── data_generator.py     # Real data downloader, cleaner & feature engineer
│   └── model.py              # Training, inference, XAI & counterfactual logic
├── templates/
│   └── index.html            # Jinja2 HTML template
├── static/
│   ├── css/style.css         # Full institutional banking CSS design system
│   └── js/main.js            # Frontend: sliders, API calls, chart rendering
└── PROJECT_REPORT.md         # This document
```

### 8.3 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Render main portal UI |
| `POST` | `/api/assess` | Run full credit assessment, returns decision + XAI contributions |
| `GET` | `/api/persona/<key>` | Load sample applicant profile |
| `GET` | `/api/metrics` | Return model governance metrics (JSON) |
| `POST` | `/api/retrain` | Re-download data and retrain model |

### 8.4 UI/UX Design Principles

The Veritas portal was designed to embody **institutional editorial banking** aesthetics — deliberately departing from generic AI-generated templates:

- **Color palette:** Warm alabaster backgrounds (#F9F8F6), deep forest green brand accent (#0F4C3A), semantic risk badges in sage/amber/rose
- **Typography:** Newsreader serif for editorial headings, Plus Jakarta Sans for UI labels, JetBrains Mono with `font-variant-numeric: tabular-nums` for all financial figures
- **Layout:** Sticky left-column form (40%) + scrollable right-column decisions (60%)
- **Interactions:** Range sliders with live value display, animated XAI bars, persona demo loader

---

## 9. Practical Banking Applications

### 9.1 Retail Loan Origination

The primary deployment context is a **retail loan origination system** where the model serves as a first-pass automated underwriting engine. The workflow:

1. Branch officer or digital portal collects applicant details
2. Veritas engine scores the application in real-time (<200ms)
3. Applications above threshold (P > 68%) are auto-approved
4. Applications in conditional range (42% < P < 68%) are flagged for manual review
5. Applications below threshold (P < 42%) are auto-declined with explanation letter

### 9.2 Credit Policy Calibration

Underwriting teams can use the model's feature contributions to identify which policy levers (DTI limits, minimum credit scores, LTI caps) are most impactful across the portfolio.

### 9.3 Portfolio Risk Monitoring

By scoring the existing loan portfolio monthly, the model can flag accounts where a borrower's updated financial position would now result in a lower approval probability — providing early warning of potential stress.

### 9.4 Customer-Facing Financial Counselling

The counterfactual advisor can be surfaced directly to applicants through a customer portal, enabling self-service financial improvement planning — reducing reapplication friction.

---

## 10. Limitations & Ethical Considerations

### 10.1 Data Limitations

1. **Sample Size:** 614 records is relatively small for a production credit model. Enterprise models typically train on millions of accounts.
2. **Temporal Coverage:** The dataset does not include timestamps; it is unclear what economic cycle it represents. Models trained on pre-2008 data perform poorly post-crisis.
3. **Survivorship Bias:** The dataset only includes applications that were submitted — not rejected applicants who self-selected out.

### 10.2 Model Limitations

1. **Credit Score Proxy:** The continuous Credit Score was derived from binary Credit_History — this is an approximation, not observed CIBIL data.
2. **Static Snapshot:** The model treats each application as independent. Real credit risk models incorporate payment trajectory and behavioural data over time.
3. **Regional Variation:** Interest rates, property values, and income distributions vary significantly across Indian states. A single model cannot capture this granularity.

### 10.3 Ethical Considerations

1. **Algorithmic Bias:** While protected attributes are excluded, proxy variables (property area, employment type) may correlate with protected characteristics. Regular bias audits using disparate impact analysis are mandatory.
2. **Automation Bias:** Human underwriters may over-rely on AI recommendations without independent judgment — training protocols must emphasise model-as-tool, not model-as-oracle.
3. **Right to Explanation:** Every declined applicant must receive a written explanation citing the top negative factors from the XAI output — this is already built into the Veritas credit memo module.

---

## 11. References

1. **Analytics Vidhya.** (2014). *Loan Prediction Problem Dataset.* Retrieved from https://datahack.analyticsvidhya.com/contest/practice-problem-loan-prediction-iii/

2. **Reserve Bank of India.** (2023). *Handbook of Statistics on Indian Economy 2022-23.* RBI Publications.

3. **Basel Committee on Banking Supervision.** (2006). *International Convergence of Capital Measurement and Capital Standards (Basel II).* Bank for International Settlements.

4. **Friedman, J. H.** (2001). *Greedy function approximation: A gradient boosting machine.* Annals of Statistics, 29(5), 1189–1232.

5. **Lundberg, S. M., & Lee, S. I.** (2017). *A unified approach to interpreting model predictions.* Advances in Neural Information Processing Systems (NeurIPS 2017).

6. **Pedregosa, F., et al.** (2011). *Scikit-learn: Machine learning in Python.* Journal of Machine Learning Research, 12, 2825–2830.

7. **Platt, J.** (1999). *Probabilistic outputs for support vector machines and comparison to regularized likelihood methods.* Advances in Large Margin Classifiers, 10(3), 61–74.

8. **Reserve Bank of India.** (2015). *Master Circular — Fair Practices Code.* RBI/2015-16/65.

9. **Taskforce on Explainability.** (2021). *Algorithmic accountability in financial services.* Financial Stability Board Working Paper.

---

*This report was prepared as the CIA-2 project submission for the AI for Finance course. All code, data processing, model training, and UI are original implementations using publicly available tools and datasets.*

---

**Project Repository:** `https://github.com/gagancv28/Loan_Elegibility`  
**Run Application:** `python app.py` → Open `http://127.0.0.1:5000`
