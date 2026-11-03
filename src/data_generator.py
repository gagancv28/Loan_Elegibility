"""
Veritas Credit Underwriting Portal — Real Data Loader & Preprocessor
Downloads the Analytics Vidhya Loan Prediction Dataset (614 verified records)
and augments it with engineered banking features for model training.

Source: https://github.com/shrikant-temburwar/Loan-Prediction-Dataset
Citation: Analytics Vidhya Loan Prediction Challenge (public benchmark dataset)
"""

import os
import sys
import urllib.request
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR   = os.path.join(BASE_DIR, 'data')
RAW_PATH   = os.path.join(DATA_DIR, 'loan_raw.csv')
CLEAN_PATH = os.path.join(DATA_DIR, 'loan_data.csv')

DATASET_URL = (
    'https://raw.githubusercontent.com/shrikant-temburwar/'
    'Loan-Prediction-Dataset/master/train.csv'
)

# ---------------------------------------------------------------------------
# Annual interest rate used for EMI engineering
# ---------------------------------------------------------------------------
ANNUAL_RATE = 0.095   # 9.5% p.a. (standard Indian retail lending benchmark)


# ---------------------------------------------------------------------------
# Step 1: Download raw data
# ---------------------------------------------------------------------------
def download_raw(force: bool = False) -> pd.DataFrame:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(RAW_PATH) or force:
        print(f"[DataLoader] Downloading real dataset from:\n  {DATASET_URL}")
        urllib.request.urlretrieve(DATASET_URL, RAW_PATH)
        print(f"[DataLoader] Saved raw file -> {RAW_PATH}")
    else:
        print(f"[DataLoader] Raw file already exists -> {RAW_PATH}")
    return pd.read_csv(RAW_PATH)


# ---------------------------------------------------------------------------
# Step 2: Clean & standardise the raw Analytics Vidhya dataset
# ---------------------------------------------------------------------------
def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # -- Drop identifier column
    df = df.drop(columns=['Loan_ID'], errors='ignore')

    # -- Target: Y/N -> 1/0
    df['Loan_Approved'] = (df['Loan_Status'] == 'Y').astype(int)
    df = df.drop(columns=['Loan_Status'])

    # ---- Numerical missing-value imputation --------------------------------
    # LoanAmount: use median within (Self_Employed x Education) group
    df['LoanAmount'] = df.groupby(['Self_Employed', 'Education'])['LoanAmount'] \
                         .transform(lambda x: x.fillna(x.median()))
    df['LoanAmount'] = df['LoanAmount'].fillna(df['LoanAmount'].median())

    # Loan_Amount_Term: mode imputation + safe int conversion
    lat_mode = df['Loan_Amount_Term'].mode()[0]
    df['Loan_Amount_Term'] = df['Loan_Amount_Term'].fillna(lat_mode).astype(float).round().astype(int)

    # Credit_History: 0 or 1 — impute with mode, coerce to int safely
    ch_mode = df['Credit_History'].mode()[0]
    df['Credit_History'] = df['Credit_History'].fillna(ch_mode).astype(float).round().astype(int)

    # CoapplicantIncome: fill NaN with 0
    df['CoapplicantIncome'] = df['CoapplicantIncome'].fillna(0)

    # ---- Categorical missing-value imputation ------------------------------
    for col in ['Gender', 'Married', 'Dependents', 'Self_Employed']:
        df[col] = df[col].fillna(df[col].mode()[0])

    # ---- Unit conversions & modern Indian retail banking scaling ---------
    # In raw dataset, LoanAmount is in thousands and ApplicantIncome is on old micro-scale.
    # We scale by 10x to represent modern retail banking (Incomes ~₹50,000/mo, Loans ~₹15,00,000).
    df['Applicant_Income']      = (df['ApplicantIncome'] * 10).astype(int)
    df['Coapplicant_Income']    = (df['CoapplicantIncome'] * 10).astype(int)
    df['Loan_Amount']           = (df['LoanAmount'] * 10000).astype(int)
    df['Existing_Monthly_Debt'] = (df['Applicant_Income'] * 0.15).astype(int)
    df['Loan_Term_Months']      = df['Loan_Amount_Term'].astype(int)

    # ---- Remap / rename to our canonical schema ---------------------------
    # Map Self_Employed to realistic retail categories
    df['Employment_Type'] = np.where(
        df['Self_Employed'] == 'Yes',
        np.where(df['Applicant_Income'] >= 80000, 'Business Owner', 'Self-Employed'),
        'Salaried'
    )

    # Normalize Property_Area: 'Semiurban' -> 'Semi-Urban' for consistency with UI
    df['Property_Area'] = df['Property_Area'].replace({'Semiurban': 'Semi-Urban'})

    # Employment_Length_Years: proxy from Education + Married heuristic
    df['Employment_Length_Years'] = np.where(
        (df['Education'] == 'Graduate') & (df['Married'] == 'Yes'), 7,
        np.where(df['Education'] == 'Graduate', 5, 3)
    ).astype(int)

    # Prior_Defaults: inverse of Credit_History (0 = past default)
    df['Prior_Defaults'] = (df['Credit_History'] == 0).astype(int)

    # Credit_Score: realistic continuous credit score distribution
    # Good credit history: centered at 745 (std 45, bounded 640-850)
    # Bad credit history:  centered at 520 (std 60, bounded 300-630)
    rng = np.random.default_rng(42)
    cs_good = rng.normal(loc=745, scale=45, size=len(df)).clip(640, 850).round().astype(int)
    cs_bad  = rng.normal(loc=520, scale=60, size=len(df)).clip(300, 630).round().astype(int)
    df['Credit_Score'] = np.where(df['Credit_History'] == 1, cs_good, cs_bad)

    # ---- Final column selection (canonical schema) -------------------------
    keep = [
        'Applicant_Income',
        'Coapplicant_Income',
        'Existing_Monthly_Debt',
        'Loan_Amount',
        'Loan_Term_Months',
        'Credit_Score',
        'Employment_Length_Years',
        'Employment_Type',
        'Property_Area',
        'Prior_Defaults',
        'Loan_Approved',
    ]
    df = df[keep]

    # ---- Sanity guard: drop any remaining NaN rows -------------------------
    before = len(df)
    df.dropna(inplace=True)
    after  = len(df)
    if before != after:
        print(f"[DataLoader] Dropped {before - after} rows with residual NaNs.")

    return df


# ---------------------------------------------------------------------------
# Step 3: Feature engineering (domain banking ratios)
# ---------------------------------------------------------------------------
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    r = ANNUAL_RATE / 12   # monthly interest rate

    df['Total_Monthly_Income'] = df['Applicant_Income'] + df['Coapplicant_Income']

    # EMI = P × r × (1+r)^n / ((1+r)^n − 1)
    n = df['Loan_Term_Months']
    df['Estimated_Monthly_EMI'] = df['Loan_Amount'] * (
        r * (1 + r) ** n / ((1 + r) ** n - 1)
    )

    df['Debt_To_Income_Ratio'] = (
        (df['Existing_Monthly_Debt'] + df['Estimated_Monthly_EMI'])
        / df['Total_Monthly_Income']
    )

    df['Loan_To_Annual_Income_Ratio'] = (
        df['Loan_Amount'] / (df['Total_Monthly_Income'] * 12)
    )

    return df


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------
def load_and_prepare(force_download: bool = False) -> pd.DataFrame:
    """
    Download (if needed), clean, engineer features, and return the full
    processed DataFrame. Also persists it to CLEAN_PATH.
    """
    raw_df   = download_raw(force=force_download)
    clean_df = clean(raw_df)
    final_df = engineer_features(clean_df)

    final_df.to_csv(CLEAN_PATH, index=False)

    print(f"[DataLoader] Final dataset: {len(final_df)} records, "
          f"{final_df.columns.tolist()}")
    print(f"[DataLoader] Approval rate : {final_df['Loan_Approved'].mean():.1%}")
    print(f"[DataLoader] Saved -> {CLEAN_PATH}")

    return final_df


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    force = '--force' in sys.argv
    df = load_and_prepare(force_download=force)
    print("\n--- Sample Records ---")
    print(df[['Applicant_Income', 'Credit_Score', 'Debt_To_Income_Ratio',
              'Loan_Amount', 'Loan_Approved']].head(10).to_string())
