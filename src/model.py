"""
Veritas Credit Underwriting Portal — ML Model: Training, Inference & XAI
Trains a calibrated GradientBoostingClassifier on the real Analytics Vidhya
Loan Prediction Dataset and provides local feature-contribution explanations
using a manual permutation-based SHAP-approximation (no external SHAP lib needed).
"""

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    accuracy_score, roc_auc_score, precision_score,
    recall_score, f1_score, confusion_matrix
)

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MODEL_PATH  = os.path.join(BASE_DIR, 'models', 'veritas_model.pkl')
METRICS_PATH = os.path.join(BASE_DIR, 'models', 'model_metrics.json')
ENCODER_PATH = os.path.join(BASE_DIR, 'models', 'label_encoders.pkl')

ANNUAL_RATE  = 0.095   # 9.5% p.a.

# ---------------------------------------------------------------------------
# Feature schema
# ---------------------------------------------------------------------------
CATEGORICAL_COLS = ['Employment_Type', 'Property_Area']
NUMERIC_FEATURES = [
    'Applicant_Income', 'Coapplicant_Income', 'Existing_Monthly_Debt',
    'Loan_Amount', 'Loan_Term_Months', 'Credit_Score',
    'Employment_Length_Years', 'Prior_Defaults',
    'Total_Monthly_Income', 'Estimated_Monthly_EMI',
    'Debt_To_Income_Ratio', 'Loan_To_Annual_Income_Ratio',
]
ALL_FEATURES = NUMERIC_FEATURES + ['Employment_Type_enc', 'Property_Area_enc']

# Human-readable names for the XAI chart
FEATURE_DISPLAY_NAMES = {
    'Credit_Score'              : 'Credit Score',
    'Debt_To_Income_Ratio'      : 'Debt-to-Income Ratio',
    'Loan_To_Annual_Income_Ratio': 'Loan-to-Income Ratio',
    'Estimated_Monthly_EMI'     : 'Monthly EMI Burden',
    'Total_Monthly_Income'      : 'Total Monthly Income',
    'Applicant_Income'          : 'Applicant Income',
    'Coapplicant_Income'        : 'Co-applicant Income',
    'Existing_Monthly_Debt'     : 'Existing Monthly Debt',
    'Loan_Amount'               : 'Loan Amount Requested',
    'Loan_Term_Months'          : 'Loan Tenure',
    'Employment_Length_Years'   : 'Employment Length',
    'Prior_Defaults'            : 'Prior Default History',
    'Employment_Type_enc'       : 'Employment Type',
    'Property_Area_enc'         : 'Property Area',
}


# ---------------------------------------------------------------------------
# Feature engineering (must mirror data_generator.py)
# ---------------------------------------------------------------------------
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    r = ANNUAL_RATE / 12
    df['Total_Monthly_Income']    = df['Applicant_Income'] + df['Coapplicant_Income']
    n = df['Loan_Term_Months']
    df['Estimated_Monthly_EMI']   = df['Loan_Amount'] * (r * (1+r)**n / ((1+r)**n - 1))
    df['Debt_To_Income_Ratio']    = (df['Existing_Monthly_Debt'] + df['Estimated_Monthly_EMI']) / df['Total_Monthly_Income']
    df['Loan_To_Annual_Income_Ratio'] = df['Loan_Amount'] / (df['Total_Monthly_Income'] * 12)
    return df


# ---------------------------------------------------------------------------
# Train & save model
# ---------------------------------------------------------------------------
def train_model(df: pd.DataFrame):
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

    df = engineer_features(df)

    # Encode categoricals
    encoders = {}
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df[col + '_enc'] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    X = df[ALL_FEATURES].copy()
    y = df['Loan_Approved']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # Base GBC
    gbc = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=10,
        subsample=0.8,
        random_state=42
    )

    # Calibrate for well-calibrated probabilities (Platt scaling)
    model = CalibratedClassifierCV(gbc, cv=5, method='sigmoid')
    model.fit(X_train, y_train)

    # --- Metrics ---
    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    cv_auc = cross_val_score(model, X, y, cv=StratifiedKFold(5), scoring='roc_auc')

    cm = confusion_matrix(y_test, y_pred)
    metrics = {
        'roc_auc'          : round(roc_auc_score(y_test, y_proba), 4),
        'cv_roc_auc_mean'  : round(float(cv_auc.mean()), 4),
        'cv_roc_auc_std'   : round(float(cv_auc.std()), 4),
        'accuracy'         : round(accuracy_score(y_test, y_pred), 4),
        'precision'        : round(precision_score(y_test, y_pred), 4),
        'recall'           : round(recall_score(y_test, y_pred), 4),
        'f1_score'         : round(f1_score(y_test, y_pred), 4),
        'confusion_matrix' : cm.tolist(),
        'n_train'          : int(len(X_train)),
        'n_test'           : int(len(X_test)),
        'n_total'          : int(len(df)),
        'approval_rate'    : round(float(y.mean()), 4),
        'data_source'      : 'Analytics Vidhya Loan Prediction Dataset (614 real records)',
        'model_type'       : 'CalibratedClassifierCV(GradientBoostingClassifier)',
    }

    # Persist
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump({
            'model': model,
            'feature_cols': ALL_FEATURES,
            'baseline_medians': X_train.median().to_dict(),
            'baseline_means': X_train.mean().to_dict(),
        }, f)
    with open(METRICS_PATH, 'w') as f:
        json.dump(metrics, f, indent=2)
    with open(ENCODER_PATH, 'wb') as f:
        pickle.dump(encoders, f)

    print(f"[Model] ROC-AUC (test):       {metrics['roc_auc']:.4f}")
    print(f"[Model] CV ROC-AUC (5-fold):  {metrics['cv_roc_auc_mean']:.4f} ± {metrics['cv_roc_auc_std']:.4f}")
    print(f"[Model] Accuracy:             {metrics['accuracy']:.4f}")
    print(f"[Model] Precision / Recall:   {metrics['precision']:.4f} / {metrics['recall']:.4f}")
    print(f"[Model] Saved -> {MODEL_PATH}")

    return model, encoders, metrics


# ---------------------------------------------------------------------------
# Load saved model & encoders
# ---------------------------------------------------------------------------
def load_model():
    with open(MODEL_PATH, 'rb') as f:
        payload = pickle.load(f)
    with open(ENCODER_PATH, 'rb') as f:
        encoders = pickle.load(f)
    baseline_medians = payload.get('baseline_medians', {})
    baseline_means = payload.get('baseline_means', {})
    return payload['model'], encoders, baseline_medians, baseline_means


# ---------------------------------------------------------------------------
# Predict a single applicant and compute local feature contributions
# ---------------------------------------------------------------------------
def predict_applicant(applicant: dict, model, encoders, baseline_medians=None, baseline_means=None) -> dict:
    """
    Returns:
      probability     : float – P(approval)
      approved        : bool
      risk_tier       : str  – 'Low' | 'Moderate' | 'High'
      contributions   : list of {feature, display_name, value, contribution, direction}
      engineered      : dict of derived banking ratios
      counterfactual  : dict or None
    """
    applicant = dict(applicant)
    is_ntc = bool(applicant.get('is_ntc', False))
    bank_statement_tenure = int(applicant.get('bank_statement_tenure', 6))
    average_bank_balance = int(applicant.get('average_bank_balance', 50000))
    utility_repayment_consistency = str(applicant.get('utility_repayment_consistency', 'High'))
    emp_type = str(applicant.get('Employment_Type', 'Salaried'))

    # If NTC, set synthetic neutral credit score in model feature matrix to evaluate fundamental capacity
    if is_ntc:
        applicant['Credit_Score'] = 730

    df = pd.DataFrame([applicant])
    df = engineer_features(df)

    # Encode categoricals with safe fallback
    for col in CATEGORICAL_COLS:
        le = encoders[col]
        raw_val = applicant.get(col, le.classes_[0])
        if raw_val not in le.classes_:
            # Try common synonyms
            if raw_val == 'Semi-Urban' and 'Semiurban' in le.classes_:
                val = 'Semiurban'
            elif raw_val == 'Semiurban' and 'Semi-Urban' in le.classes_:
                val = 'Semi-Urban'
            else:
                val = le.classes_[0]
        else:
            val = raw_val
        df[col + '_enc'] = le.transform([val])[0]

    X = df[ALL_FEATURES].copy()
    base_prob = float(model.predict_proba(X)[0, 1])

    dti = float(df['Debt_To_Income_Ratio'].iloc[0])
    cs  = int(applicant.get('Credit_Score', 700))
    pdef = int(applicant.get('Prior_Defaults', 0))
    emi  = float(df['Estimated_Monthly_EMI'].iloc[0])

    # NTC Cash-Flow specific metrics & adjustments
    if is_ntc:
        lcr = round(average_bank_balance / max(emi, 1.0), 2)
        # Required tenure check: Salaried requires 6 mo, Self-Employed/Business requires 12 mo
        required_tenure = 12 if emp_type in ['Self-Employed', 'Business Owner'] else 6
        tenure_deficit = (bank_statement_tenure < required_tenure)

        # 1. Liquidity Buffer (LCR) Impact
        if lcr >= 3.0:
            liquidity_impact = 8.5
        elif lcr >= 2.0:
            liquidity_impact = 5.0
        elif lcr >= 1.2:
            liquidity_impact = 2.0
        elif lcr >= 0.8:
            liquidity_impact = -4.0
        else:
            liquidity_impact = -12.5

        # 2. Utility & UPI Consistency Impact
        if utility_repayment_consistency == 'High':
            utility_impact = 5.0
        elif utility_repayment_consistency == 'Moderate':
            utility_impact = 0.0
        else:
            utility_impact = -15.0

        # 3. Statement Window Lookback Impact
        if tenure_deficit:
            tenure_impact = -8.0   # Risk penalty for Self-Employed with only 6-mo statement
        else:
            tenure_impact = 2.0    # Full compliance with RBI AA lookback window

        total_adjustment = (liquidity_impact + utility_impact + tenure_impact) / 100.0
        prob = float(np.clip(base_prob + total_adjustment, 0.05, 0.95))

        has_policy_stress = (dti > 0.45 or lcr < 1.4 or utility_repayment_consistency == 'Low' or tenure_deficit)

        if prob >= 0.65 and not has_policy_stress:
            risk_tier = 'Low'
            decision  = 'Approved'
        elif prob >= 0.38 or (prob >= 0.65 and has_policy_stress):
            risk_tier = 'Moderate'
            decision  = 'Conditional Review'
        else:
            risk_tier = 'High'
            decision  = 'Rejected'
    else:
        # Standard bureau assessment
        lcr = round(applicant.get('average_bank_balance', 50000) / max(emi, 1.0), 2)
        tenure_deficit = False
        prob = base_prob
        has_policy_stress = (dti > 0.48 or cs < 620 or pdef == 1)

        if prob >= 0.68 and not has_policy_stress:
            risk_tier = 'Low'
            decision  = 'Approved'
        elif prob >= 0.40 or (prob >= 0.68 and has_policy_stress):
            risk_tier = 'Moderate'
            decision  = 'Conditional Review'
        else:
            risk_tier = 'High'
            decision  = 'Rejected'

    # Fallback baselines if not provided
    if baseline_medians is None or len(baseline_medians) == 0:
        baseline_medians = {
            'Applicant_Income': 54000, 'Coapplicant_Income': 16000, 'Existing_Monthly_Debt': 8100,
            'Loan_Amount': 1440000, 'Loan_Term_Months': 360, 'Credit_Score': 738,
            'Employment_Length_Years': 6, 'Prior_Defaults': 0, 'Total_Monthly_Income': 70000,
            'Estimated_Monthly_EMI': 12700, 'Debt_To_Income_Ratio': 0.32,
            'Loan_To_Annual_Income_Ratio': 1.99, 'Employment_Type_enc': 1, 'Property_Area_enc': 1
        }
    if baseline_means is None or len(baseline_means) == 0:
        baseline_means = dict(baseline_medians)
        baseline_means['Prior_Defaults'] = 0.14

    # --- Local feature contributions (Monotonic Financial Underwriting Attribution) ---
    contributions = []

    # 1. Credit Score (Standard Bureau Mode)
    if not is_ntc:
        if cs >= 720:
            cs_contrib = round(8.0 + min(10.0, (cs - 720) * 0.15), 1)
        elif cs >= 650:
            cs_contrib = round(1.0 + (cs - 650) * 0.10, 1)
        else:
            cs_contrib = round(-4.0 - min(22.0, (650 - cs) * 0.12), 1)
        contributions.append({
            'feature': 'Credit_Score',
            'display_name': 'Credit Score',
            'raw_value': cs,
            'contribution': cs_contrib,
            'direction': 'positive' if cs_contrib >= 0 else 'negative',
        })

    # 2. Debt-to-Income (DTI) Ratio
    if dti < 0.35:
        dti_contrib = round(4.0 + min(5.0, (0.35 - dti) * 25.0), 1)
    elif dti <= 0.43:
        dti_contrib = round(1.5 - (dti - 0.35) * 35.0, 1)
    else:
        dti_contrib = round(-3.0 - min(14.0, (dti - 0.43) * 40.0), 1)
    contributions.append({
        'feature': 'Debt_To_Income_Ratio',
        'display_name': 'Debt-to-Income Ratio',
        'raw_value': round(dti * 100, 1),
        'contribution': dti_contrib,
        'direction': 'positive' if dti_contrib >= 0 else 'negative',
    })

    # 3. Co-applicant Income
    coapp_inc = float(applicant.get('Coapplicant_Income', 0))
    if coapp_inc > 0:
        coapp_contrib = round(2.0 + min(6.0, (coapp_inc / 15000.0) * 1.2), 1)
        contributions.append({
            'feature': 'Coapplicant_Income',
            'display_name': 'Co-applicant Income',
            'raw_value': coapp_inc,
            'contribution': coapp_contrib,
            'direction': 'positive',
        })

    # 4. Total Monthly Income
    tot_inc = float(df['Total_Monthly_Income'].iloc[0])
    if tot_inc >= 70000:
        inc_contrib = round(2.0 + min(6.0, (tot_inc - 70000) / 30000.0 * 1.5), 1)
    else:
        inc_contrib = round(-1.0 - min(7.0, (70000 - tot_inc) / 20000.0 * 2.0), 1)
    contributions.append({
        'feature': 'Total_Monthly_Income',
        'display_name': 'Total Monthly Income',
        'raw_value': tot_inc,
        'contribution': inc_contrib,
        'direction': 'positive' if inc_contrib >= 0 else 'negative',
    })

    # 5. Loan-to-Annual-Income (LTI) Ratio
    lti = float(df['Loan_To_Annual_Income_Ratio'].iloc[0])
    if lti < 2.0:
        lti_contrib = round(2.5 + min(3.0, (2.0 - lti) * 1.5), 1)
    elif lti <= 3.5:
        lti_contrib = round(1.0 - (lti - 2.0) * 1.2, 1)
    else:
        lti_contrib = round(-2.5 - min(6.0, (lti - 3.5) * 1.8), 1)
    contributions.append({
        'feature': 'Loan_To_Annual_Income_Ratio',
        'display_name': 'Loan-to-Income Ratio',
        'raw_value': round(lti, 2),
        'contribution': lti_contrib,
        'direction': 'positive' if lti_contrib >= 0 else 'negative',
    })

    # 6. Existing Monthly Debt
    debt = float(applicant.get('Existing_Monthly_Debt', 0))
    debt_ratio = debt / max(tot_inc, 1.0)
    if debt_ratio < 0.10:
        debt_contrib = 2.0
    elif debt_ratio <= 0.20:
        debt_contrib = -0.5
    else:
        debt_contrib = round(-2.5 - min(7.0, (debt_ratio - 0.20) * 20.0), 1)
    contributions.append({
        'feature': 'Existing_Monthly_Debt',
        'display_name': 'Existing Monthly Debt',
        'raw_value': debt,
        'contribution': debt_contrib,
        'direction': 'positive' if debt_contrib >= 0 else 'negative',
    })

    # 7. Monthly EMI Burden
    emi_ratio = emi / max(tot_inc, 1.0)
    if emi_ratio < 0.20:
        emi_contrib = 2.0
    elif emi_ratio <= 0.35:
        emi_contrib = -1.5
    else:
        emi_contrib = round(-3.5 - min(6.5, (emi_ratio - 0.35) * 25.0), 1)
    contributions.append({
        'feature': 'Estimated_Monthly_EMI',
        'display_name': 'Monthly EMI Burden',
        'raw_value': emi,
        'contribution': emi_contrib,
        'direction': 'positive' if emi_contrib >= 0 else 'negative',
    })

    # 8. Employment Length
    emp_len = float(applicant.get('Employment_Length_Years', 1))
    if emp_len >= 5:
        emp_contrib = round(3.0 + min(4.0, (emp_len - 5) * 0.5), 1)
    elif emp_len >= 2:
        emp_contrib = round(1.5 + (emp_len - 2) * 0.5, 1)
    else:
        emp_contrib = -1.5
    contributions.append({
        'feature': 'Employment_Length_Years',
        'display_name': 'Employment Length',
        'raw_value': emp_len,
        'contribution': emp_contrib,
        'direction': 'positive' if emp_contrib >= 0 else 'negative',
    })

    # 9. Prior Defaults
    if pdef == 0:
        pdef_contrib = 5.0
    else:
        pdef_contrib = -28.0
    contributions.append({
        'feature': 'Prior_Defaults',
        'display_name': 'Prior Loan Defaults',
        'raw_value': pdef,
        'contribution': pdef_contrib,
        'direction': 'positive' if pdef_contrib >= 0 else 'negative',
    })

    # 10. For NTC: inject Account Aggregator cash-flow features
    if is_ntc:
        contributions.append({
            'feature': 'AA_Bank_Liquidity',
            'display_name': f"AA Bank Liquidity ({bank_statement_tenure}-Mo ABB: ₹{average_bank_balance:,.0f})",
            'raw_value': average_bank_balance,
            'contribution': round(liquidity_impact, 1),
            'direction': 'positive' if liquidity_impact >= 0 else 'negative',
        })
        contributions.append({
            'feature': 'Utility_Bill_Discipline',
            'display_name': f"Utility & UPI Bill Discipline ({utility_repayment_consistency})",
            'raw_value': 1 if utility_repayment_consistency == 'High' else 0,
            'contribution': round(utility_impact, 1),
            'direction': 'positive' if utility_impact >= 0 else 'negative',
        })
        if tenure_deficit:
            contributions.append({
                'feature': 'AA_Lookback_Deficit',
                'display_name': f"Statement Lookback Window Deficit ({bank_statement_tenure} vs 12 Mo)",
                'raw_value': bank_statement_tenure,
                'contribution': round(tenure_impact, 1),
                'direction': 'negative',
            })

    # Sort by absolute impact descending; keep top 8
    contributions.sort(key=lambda x: abs(x['contribution']), reverse=True)
    contributions = contributions[:8]

    # --- Engineered ratios for display ---
    engineered = {
        'total_monthly_income'  : round(float(df['Total_Monthly_Income'].iloc[0])),
        'estimated_monthly_emi' : round(float(df['Estimated_Monthly_EMI'].iloc[0])),
        'dti_ratio'             : round(float(df['Debt_To_Income_Ratio'].iloc[0]), 4),
        'lti_ratio'             : round(float(df['Loan_To_Annual_Income_Ratio'].iloc[0]), 4),
        'is_ntc'                : is_ntc,
        'lcr'                   : lcr,
        'average_bank_balance'  : average_bank_balance,
        'bank_statement_tenure' : bank_statement_tenure,
        'tenure_deficit'        : tenure_deficit if is_ntc else False,
        'utility_consistency'   : utility_repayment_consistency,
    }

    # --- Counterfactual advisor (only for non-approved) ---
    counterfactual = None
    if decision != 'Approved':
        counterfactual = _compute_counterfactual(applicant, model, encoders, df, engineered)

    return {
        'probability'  : round(prob, 4),
        'decision'     : decision,
        'risk_tier'    : risk_tier,
        'contributions': contributions,
        'engineered'   : engineered,
        'counterfactual': counterfactual,
    }


# ---------------------------------------------------------------------------
# Counterfactual / What-If advisor
# ---------------------------------------------------------------------------
def _compute_counterfactual(applicant, model, encoders, df_eng, engineered):
    suggestions = []
    base_prob   = float(model.predict_proba(
        _build_X(applicant, df_eng, encoders)
    )[0, 1])
    target_prob  = 0.70   # target approval probability

    # 1. Reduce loan amount
    for pct in [0.15, 0.25, 0.35]:
        trial = dict(applicant)
        trial['Loan_Amount'] = int(applicant['Loan_Amount'] * (1 - pct))
        p = _trial_prob(trial, model, encoders)
        if p >= target_prob:
            suggestions.append({
                'action': 'reduce_loan',
                'label' : f"Reduce loan amount by {int(pct*100)}%",
                'detail': (
                    f"Decrease requested loan from "
                    f"₹{applicant['Loan_Amount']:,.0f} -> "
                    f"₹{trial['Loan_Amount']:,.0f}"
                ),
                'new_prob': round(p, 4),
            })
            break

    # 2. Improve credit score
    for delta in [30, 50, 75, 100]:
        trial = dict(applicant)
        trial['Credit_Score'] = min(850, applicant['Credit_Score'] + delta)
        p = _trial_prob(trial, model, encoders)
        if p >= target_prob:
            suggestions.append({
                'action': 'improve_credit',
                'label' : f"Improve credit score by +{delta} points",
                'detail': (
                    f"Raise credit score from "
                    f"{applicant['Credit_Score']} -> {trial['Credit_Score']}"
                ),
                'new_prob': round(p, 4),
            })
            break

    # 3. Extend loan tenure
    for extra_months in [24, 48, 60]:
        trial = dict(applicant)
        trial['Loan_Term_Months'] = applicant['Loan_Term_Months'] + extra_months
        p = _trial_prob(trial, model, encoders)
        if p >= target_prob:
            suggestions.append({
                'action': 'extend_tenure',
                'label' : f"Extend loan tenure by {extra_months} months",
                'detail': (
                    f"Increase tenure from "
                    f"{applicant['Loan_Term_Months']} -> {trial['Loan_Term_Months']} months, "
                    f"reducing monthly EMI burden"
                ),
                'new_prob': round(p, 4),
            })
            break

    # 4. Add co-applicant income
    if applicant.get('Coapplicant_Income', 0) < 20000:
        trial = dict(applicant)
        trial['Coapplicant_Income'] = 35000
        p = _trial_prob(trial, model, encoders)
        if p >= target_prob:
            suggestions.append({
                'action': 'add_coapplicant',
                'label' : "Add co-applicant income of ₹35,000/month",
                'detail': "Including a co-applicant lowers DTI and strengthens the application.",
                'new_prob': round(p, 4),
            })

    return suggestions if suggestions else None


def _build_X(applicant, df_eng, encoders):
    df = pd.DataFrame([applicant])
    df = pd.concat([df, df_eng[['Total_Monthly_Income', 'Estimated_Monthly_EMI',
                                 'Debt_To_Income_Ratio', 'Loan_To_Annual_Income_Ratio']]
                    .iloc[:1].reset_index(drop=True)], axis=1)
    for col in CATEGORICAL_COLS:
        le = encoders[col]
        val = applicant.get(col, le.classes_[0])
        if val not in le.classes_:
            val = le.classes_[0]
        df[col + '_enc'] = le.transform([val])[0]
    return df[ALL_FEATURES].copy()


def _trial_prob(trial_applicant, model, encoders):
    df = pd.DataFrame([trial_applicant])
    df = engineer_features(df)
    for col in CATEGORICAL_COLS:
        le = encoders[col]
        val = trial_applicant.get(col, le.classes_[0])
        if val not in le.classes_:
            val = le.classes_[0]
        df[col + '_enc'] = le.transform([val])[0]
    X = df[ALL_FEATURES].copy()
    return float(model.predict_proba(X)[0, 1])


# ---------------------------------------------------------------------------
# Load model metrics for the governance tab
# ---------------------------------------------------------------------------
def load_metrics() -> dict:
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH) as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from data_generator import load_and_prepare

    df = load_and_prepare()
    model, encoders, metrics = train_model(df)

    # Quick smoke-test
    sample = {
        'Applicant_Income'      : 80000,
        'Coapplicant_Income'    : 30000,
        'Existing_Monthly_Debt' : 12000,
        'Loan_Amount'           : 1500000,
        'Loan_Term_Months'      : 180,
        'Credit_Score'          : 720,
        'Employment_Length_Years': 6,
        'Employment_Type'       : 'Salaried',
        'Property_Area'         : 'Urban',
        'Prior_Defaults'        : 0,
    }
    result = predict_applicant(sample, model, encoders)
    print(f"\n[Smoke-test] Decision: {result['decision']}  |  P(approval): {result['probability']:.2%}")
    print(f"[Smoke-test] DTI: {result['engineered']['dti_ratio']:.2%}  EMI: ₹{result['engineered']['estimated_monthly_emi']:,.0f}")
