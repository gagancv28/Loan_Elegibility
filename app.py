"""
Veritas Credit Underwriting Portal — Flask Application Server
"""

import os
import sys
import json
import traceback

from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import HTTPException

# Ensure src/ is importable
SRC_DIR = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, SRC_DIR)

from data_generator import load_and_prepare
from model import train_model, load_model, predict_applicant, load_metrics, MODEL_PATH, ENCODER_PATH
from statement_parser import parse_bank_statement

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'veritas-default-dev-secret-key-change-in-prod')
# 10MB Maximum upload limit for bank statements (Layer 3 Guardrail)
max_upload_mb = int(os.environ.get('MAX_UPLOAD_MB', 10))
app.config['MAX_CONTENT_LENGTH'] = max_upload_mb * 1024 * 1024

@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        'error': f'File exceeds the {max_upload_mb}MB upload limit. Please upload a standard bank statement under {max_upload_mb}MB.'
    }), 413

# ---------------------------------------------------------------------------
# Boot: train model if it doesn't exist
# ---------------------------------------------------------------------------
def boot():
    if not os.path.exists(MODEL_PATH) or not os.path.exists(ENCODER_PATH):
        print("[Boot] No saved model found — training now...")
        df = load_and_prepare()
        train_model(df)
    else:
        print("[Boot] Saved model found — skipping training.")

boot()
_model, _encoders, _baseline_medians, _baseline_means = load_model()

# ---------------------------------------------------------------------------
# Sample Personas (for classroom demo dropdown)
# ---------------------------------------------------------------------------
SAMPLE_PERSONAS = {
    'prime': {
        'label'                 : 'Prime Borrower — Senior IT Professional',
        'Applicant_Income'      : 120000,
        'Coapplicant_Income'    : 55000,
        'Existing_Monthly_Debt' : 8000,
        'Loan_Amount'           : 2500000,
        'Loan_Term_Months'      : 180,
        'Credit_Score'          : 780,
        'Employment_Length_Years': 9,
        'Employment_Type'       : 'Salaried',
        'Property_Area'         : 'Urban',
        'Prior_Defaults'        : 0,
    },
    'borderline': {
        'label'                 : 'Borderline — Self-Employed Consultant',
        'Applicant_Income'      : 70000,
        'Coapplicant_Income'    : 15000,
        'Existing_Monthly_Debt' : 22000,
        'Loan_Amount'           : 1800000,
        'Loan_Term_Months'      : 120,
        'Credit_Score'          : 648,
        'Employment_Length_Years': 4,
        'Employment_Type'       : 'Self-Employed',
        'Property_Area'         : 'Semi-Urban',
        'Prior_Defaults'        : 0,
    },
    'highrisk': {
        'label'                 : 'High-Risk — Over-leveraged Small Business',
        'Applicant_Income'      : 45000,
        'Coapplicant_Income'    : 0,
        'Existing_Monthly_Debt' : 28000,
        'Loan_Amount'           : 2000000,
        'Loan_Term_Months'      : 84,
        'Credit_Score'          : 540,
        'Employment_Length_Years': 2,
        'Employment_Type'       : 'Business Owner',
        'Property_Area'         : 'Rural',
        'Prior_Defaults'        : 1,
    },
    'ntc_graduate': {
        'label'                 : 'New-to-Credit (NTC) Salaried Graduate',
        'Applicant_Income'      : 65000,
        'Coapplicant_Income'    : 0,
        'Existing_Monthly_Debt' : 0,
        'Loan_Amount'           : 600000,
        'Loan_Term_Months'      : 60,
        'Credit_Score'          : -1,
        'Employment_Length_Years': 1,
        'Employment_Type'       : 'Salaried',
        'Property_Area'         : 'Urban',
        'Prior_Defaults'        : 0,
        'is_ntc'                : True,
        'bank_statement_tenure' : 6,
        'average_bank_balance'  : 55000,
        'utility_repayment_consistency': 'High',
    },
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    personas = {k: v['label'] for k, v in SAMPLE_PERSONAS.items()}
    return render_template('index.html', personas=personas)


@app.route('/api/persona/<key>')
def get_persona(key):
    if key not in SAMPLE_PERSONAS:
        return jsonify({'error': 'Unknown persona'}), 404
    return jsonify(SAMPLE_PERSONAS[key])


@app.route('/api/assess', methods=['POST'])
def assess():
    try:
        data = request.get_json(force=True)

        is_ntc = bool(data.get('is_ntc', False))
        bank_statement_tenure = int(data.get('bank_statement_tenure', 6))
        average_bank_balance = int(data.get('average_bank_balance', 50000))
        utility_repayment_consistency = str(data.get('utility_repayment_consistency', 'High'))

        applicant = {
            'Applicant_Income'       : int(data.get('applicant_income', 0)),
            'Coapplicant_Income'     : int(data.get('coapplicant_income', 0)),
            'Existing_Monthly_Debt'  : int(data.get('existing_monthly_debt', 0)),
            'Loan_Amount'            : int(data.get('loan_amount', 0)),
            'Loan_Term_Months'       : int(data.get('loan_term_months', 180)),
            'Credit_Score'           : int(data.get('credit_score', 650)),
            'Employment_Length_Years': int(data.get('employment_length_years', 1)),
            'Employment_Type'        : str(data.get('employment_type', 'Salaried')),
            'Property_Area'          : str(data.get('property_area', 'Urban')),
            'Prior_Defaults'         : int(data.get('prior_defaults', 0)),
            'is_ntc'                 : is_ntc,
            'bank_statement_tenure'  : bank_statement_tenure,
            'average_bank_balance'   : average_bank_balance,
            'utility_repayment_consistency': utility_repayment_consistency,
        }

        result = predict_applicant(applicant, _model, _encoders, _baseline_medians, _baseline_means)
        result['applicant'] = applicant
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics')
def metrics():
    return jsonify(load_metrics())


@app.route('/api/parse-statement', methods=['POST'])
def parse_statement():
    try:
        # Check if 1-click simulation requested via JSON
        if request.is_json:
            req_data = request.get_json(silent=True) or {}
            sample_key = req_data.get('sample_key')
            if sample_key == 'salaried_6mo':
                file_path = os.path.join(app.static_folder, 'sample_statements', 'salaried_6mo_healthy.csv')
                with open(file_path, 'rb') as f:
                    file_bytes = f.read()
                filename = 'salaried_6mo_healthy.csv'
                parsed = parse_bank_statement(file_bytes, filename)
                return jsonify(parsed)
            elif sample_key == 'self_employed_12mo':
                file_path = os.path.join(app.static_folder, 'sample_statements', 'self_employed_12mo_risky.csv')
                with open(file_path, 'rb') as f:
                    file_bytes = f.read()
                filename = 'self_employed_12mo_risky.csv'
                parsed = parse_bank_statement(file_bytes, filename)
                return jsonify(parsed)

        # Otherwise handle direct file upload
        if 'file' not in request.files:
            return jsonify({'error': 'No bank statement file uploaded.'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'error': 'Selected filename is empty.'}), 400
        
        password = request.form.get('password', '').strip() or None
        file_bytes = uploaded_file.read()
        filename = uploaded_file.filename
        
        parsed = parse_bank_statement(file_bytes, filename, password)
        return jsonify(parsed)

    except HTTPException:
        raise
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 422
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f"Failed to parse statement: {str(e)}"}), 500


@app.route('/api/retrain', methods=['POST'])
def retrain():
    try:
        global _model, _encoders, _baseline_medians, _baseline_means
        df = load_and_prepare(force_download=True)
        train_model(df)
        _model, _encoders, _baseline_medians, _baseline_means = load_model()
        return jsonify({'status': 'Model retrained successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true") or os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
