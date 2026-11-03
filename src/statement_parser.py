"""
Veritas Credit Underwriting Portal — Bulletproof 3-Layer Bank Statement Ingestion Engine

Layer 1: Tabular extraction for CSV, Excel (.xlsx, .xls), and structured Table PDFs.
         Scans first 35 rows to auto-detect headers across Indian banks (SBI, HDFC, ICICI, Axis, Kotak, Canara, PNB, BOB).
         Supports both separate Debit/Credit columns AND single Amount columns paired with Dr/Cr or Type indicators.

Layer 2: Regex text fallback for non-table / custom-layout PDFs (pdfplumber.extract_text line-by-line).
         Extracts date patterns and Indian currency figures, computes balance differences or infers from Dr/Cr keywords.

Layer 3: Zero-crash guarantee. Encrypted PDF password detection, scanned image detection, 
         strictly in-memory (io.BytesIO) execution for multi-user cloud concurrency.
"""

import io
import re
import csv
import datetime
from typing import Dict, Any, List, Optional, Tuple

# Supported bounce keywords common across Indian banking systems
BOUNCE_KEYWORDS = [
    'BOUNCE', 'ECS RETURN', 'NACH RETURN', 'CHQ RETURN',
    'INSUFFICIENT FUNDS', 'DISHONOUR', 'DISHONOR', 'PENAL CHARGES',
    'ECS BOUNCE', 'NACH BOUNCE', 'CHQ BOUNCE', 'RETURN CHG', 'CHEQUE RET'
]

# Common header synonyms across SBI, HDFC, ICICI, Axis, Kotak, Canara, PNB, BOB
HEADER_SYNONYMS = {
    'date': [
        'date', 'txn date', 'transaction date', 'value dt', 'post date',
        'tran date', 'txn_date', 'value date', 'booking date'
    ],
    'description': [
        'narration', 'description', 'transaction remarks', 'particulars',
        'details', 'remarks', 'txn details', 'transaction description', 'narrative'
    ],
    'debit': [
        'debit', 'withdrawal amt.', 'withdrawal amount', 'withdrawal',
        'dr', 'dr amount', 'debit (inr)', 'withdrawal amt', 'debit amount',
        'dr.', 'withdrawals', 'dr (inr)'
    ],
    'credit': [
        'credit', 'deposit amt.', 'deposit amount', 'deposit',
        'cr', 'cr amount', 'credit (inr)', 'deposit amt', 'credit amount',
        'cr.', 'deposits', 'cr (inr)'
    ],
    'balance': [
        'balance', 'closing balance', 'balance (inr)', 'running balance',
        'available balance', 'net balance', 'closing_balance', 'closing bal', 'bal'
    ],
    'amount': [
        'amount', 'txn amount', 'transaction amount', 'amt', 'amt.', 'amount (inr)'
    ],
    'type': [
        'type', 'dr/cr', 'cr/dr', 'transaction type', 'txn type', 'd/c', 'c/d', 'cr_dr'
    ]
}

DATE_REGEX = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[\s-][A-Za-z]{3}[\s-]\d{2,4})\b')
AMT_REGEX = re.compile(r'(?:₹|Rs\.?\s*)?([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{2}))')


def clean_currency(val_str: Any) -> float:
    """Clean Indian currency formats: Rs., ₹, commas, Dr/Cr suffixes."""
    if val_str is None:
        return 0.0
    if isinstance(val_str, (int, float)):
        return float(val_str)
    
    s = str(val_str).strip()
    if not s or s in ['-', '--', 'N/A', 'nil', 'None', 'nan']:
        return 0.0
    
    # Remove currency symbols and formatting
    s = s.replace('₹', '').replace('Rs.', '').replace('INR', '').replace(' ', '')
    is_negative = '-' in s or s.endswith('Dr') or s.endswith('dr')
    s = re.sub(r'[^\d.]', '', s)
    if not s:
        return 0.0
    try:
        val = float(s)
        return -val if is_negative else val
    except ValueError:
        return 0.0


def parse_date_to_ym(date_str: str) -> Optional[str]:
    """Parse various Indian bank date formats and return YYYY-MM string."""
    if not date_str:
        return None
    s = str(date_str).strip()
    # Remove time if present (e.g., 2026-05-01 10:30:00)
    s = s.split(' ')[0]
    
    patterns = [
        '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y',
        '%d-%b-%Y', '%d/%b/%Y', '%d-%b-%y', '%d/%b/%y',
        '%Y/%m/%d', '%d%m%Y'
    ]
    for fmt in patterns:
        try:
            dt = datetime.datetime.strptime(s, fmt)
            return dt.strftime('%Y-%m')
        except ValueError:
            pass
    
    # Fallback regex for YYYY-MM or MM-YYYY
    match = re.search(r'(\d{4})[-/](\d{2})', s)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def extract_rows_from_file(file_bytes: bytes, filename: str, password: Optional[str] = None) -> List[List[str]]:
    """Extract 2D tabular string rows from CSV, Excel, or structured table PDF."""
    fn_lower = filename.lower()
    raw_rows: List[List[str]] = []

    if fn_lower.endswith('.csv'):
        for enc in ['utf-8', 'latin-1', 'cp1252', 'utf-8-sig']:
            try:
                text = file_bytes.decode(enc)
                reader = csv.reader(io.StringIO(text))
                raw_rows = [row for row in reader if any(cell.strip() for cell in row)]
                if raw_rows:
                    break
            except Exception:
                continue

    elif fn_lower.endswith(('.xlsx', '.xls')):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                r_str = [str(c).strip() if c is not None else "" for c in row]
                if any(r_str):
                    raw_rows.append(r_str)
        except Exception as e:
            raise ValueError(f"Unable to read Excel workbook: {str(e)}")

    elif fn_lower.endswith('.pdf'):
        import pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(file_bytes), password=password or None) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for t in tables:
                            for row in t:
                                if row:
                                    cleaned_row = [str(c).strip() if c is not None else "" for c in row]
                                    if any(cleaned_row):
                                        raw_rows.append(cleaned_row)
        except Exception as e:
            err_repr = repr(e).lower() + " " + str(e).lower()
            if 'password' in err_repr or 'authenticate' in err_repr or 'encrypted' in err_repr or 'pdfpassword' in err_repr:
                raise ValueError("This PDF statement is password-protected. Please enter your PDF password in the password field below to unlock it.")
            raise ValueError(f"Failed to process PDF: {str(e)}")

    else:
        raise ValueError("Unsupported format. Please upload a .csv, .xlsx, .xls, or .pdf statement.")

    return raw_rows


def locate_headers(raw_rows: List[List[str]]) -> Tuple[int, Dict[str, int]]:
    """
    Scan the first 35 rows to identify the transaction table header row and column mapping.
    Accurately differentiates between:
      - Separate Debit / Credit columns across Indian banks
      - Single Amount column paired with Dr/Cr or Type indicators (e.g. SBI, ICICI)
    """
    for row_idx, row in enumerate(raw_rows[:35]):
        normalized = [str(c).strip().lower() for c in row]
        col_map: Dict[str, int] = {}
        
        for c_idx, cell in enumerate(normalized):
            if not cell:
                continue
            
            # Check type indicator first (dr/cr, cr/dr, type) to avoid false matches on 'dr'/'cr'
            if any(t in cell for t in ['dr/cr', 'cr/dr', 'txn type', 'transaction type', 'd/c', 'c/d']) or cell == 'type':
                col_map['type'] = c_idx
                continue
                
            # Check date
            if any(syn == cell or syn in cell for syn in HEADER_SYNONYMS['date']):
                if 'date' not in col_map:
                    col_map['date'] = c_idx
                continue
                
            # Check balance
            if any(syn == cell or syn in cell for syn in HEADER_SYNONYMS['balance']):
                if 'balance' not in col_map:
                    col_map['balance'] = c_idx
                continue
                
            # Check debit
            if any(syn in cell for syn in ['withdrawal', 'debit', 'withdrawals']) or cell in ['dr', 'dr.', 'dr (inr)']:
                if 'debit' not in col_map:
                    col_map['debit'] = c_idx
                continue
                
            # Check credit
            if any(syn in cell for syn in ['deposit', 'credit', 'deposits']) or cell in ['cr', 'cr.', 'cr (inr)']:
                if 'credit' not in col_map:
                    col_map['credit'] = c_idx
                continue
                
            # Check amount
            if any(syn in cell for syn in ['txn amount', 'transaction amount', 'amount (inr)', 'amount', 'amt.', 'amt']):
                if 'amount' not in col_map:
                    col_map['amount'] = c_idx
                continue
                
            # Check description / narration
            if any(syn in cell for syn in HEADER_SYNONYMS['description']):
                if 'description' not in col_map:
                    col_map['description'] = c_idx
                continue
        
        # Check requirements:
        has_date = 'date' in col_map
        has_fin_cols = (
            ('debit' in col_map or 'credit' in col_map or 'balance' in col_map) or
            ('amount' in col_map and 'type' in col_map) or
            ('amount' in col_map and 'balance' in col_map)
        )
        
        if has_date and has_fin_cols:
            return row_idx, col_map

    raise ValueError("Could not locate bank statement transaction table headers within the first 35 rows.")


def parse_pdf_text_fallback(file_bytes: bytes, filename: str, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Layer 2: Regex text fallback for non-table or custom-rendered PDFs.
    Extracts text line-by-line across all pages, parses transaction dates and currency values,
    and infers debits/credits via balance changes and transaction narration keywords.
    """
    import pdfplumber
    
    try:
        with pdfplumber.open(io.BytesIO(file_bytes), password=password or None) as pdf:
            all_text_lines: List[str] = []
            has_any_text = False
            for page in pdf.pages:
                txt = page.extract_text()
                if txt and txt.strip():
                    has_any_text = True
                    all_text_lines.extend(txt.splitlines())
    except Exception as e:
        err_repr = repr(e).lower() + " " + str(e).lower()
        if 'password' in err_repr or 'authenticate' in err_repr or 'encrypted' in err_repr or 'pdfpassword' in err_repr:
            raise ValueError("This PDF statement is password-protected. Please enter your PDF password in the password field below to unlock it.")
        raise ValueError(f"Failed to read PDF: {str(e)}")

    if not has_any_text:
        raise ValueError("Scanned image PDF detected. This document contains scanned images without a selectable text layer. Please upload an original digital e-statement or a CSV / Excel export.")

    transactions = []
    unique_months = set()
    total_credits = 0.0
    total_debits = 0.0
    balances = []
    bounce_rows = []
    prev_bal: Optional[float] = None

    for line in all_text_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        date_match = DATE_REGEX.search(line_clean)
        if not date_match:
            continue
        
        raw_date = date_match.group(1)
        ym = parse_date_to_ym(raw_date)
        if not ym:
            continue

        amounts = AMT_REGEX.findall(line_clean)
        if not amounts:
            continue

        clean_amts = [float(a.replace(',', '')) for a in amounts]
        closing_balance = clean_amts[-1]
        if closing_balance > 0:
            balances.append(closing_balance)
        unique_months.add(ym)

        # Narration
        narr = line_clean[date_match.end():].strip()
        for a in amounts:
            narr = narr.replace(a, '')
        narr = re.sub(r'\s+', ' ', narr).strip()
        narr_upper = line_clean.upper()

        credit = 0.0
        debit = 0.0

        if len(clean_amts) >= 2:
            txn_amt = clean_amts[-2]
            if any(w in narr_upper for w in ['SALARY', 'CR', 'CREDIT', 'DEPOSIT', 'NEFT CR', 'RTGS CR', 'IMPS CR', 'INWARD']):
                credit = txn_amt
            elif any(w in narr_upper for w in ['RENT', 'DR', 'DEBIT', 'WITHDRAWAL', 'POS', 'ATM', 'BBPS', 'BOUNCE', 'RETURN', 'OUTWARD', 'CHQ', 'CHARGES']):
                debit = txn_amt
            elif prev_bal is not None:
                if closing_balance > prev_bal:
                    credit = round(closing_balance - prev_bal, 2)
                else:
                    debit = round(prev_bal - closing_balance, 2)
            else:
                debit = txn_amt
        else:
            if prev_bal is not None:
                if closing_balance > prev_bal:
                    credit = round(closing_balance - prev_bal, 2)
                else:
                    debit = round(prev_bal - closing_balance, 2)

        prev_bal = closing_balance
        total_credits += credit
        total_debits += debit

        if any(bk in narr_upper for bk in BOUNCE_KEYWORDS):
            bounce_rows.append({
                'date': raw_date,
                'narration': narr or line_clean,
                'amount': debit or credit or 0.0
            })

        transactions.append({
            'date': raw_date,
            'narration': narr,
            'debit': debit,
            'credit': credit,
            'balance': closing_balance
        })

    if not transactions:
        raise ValueError("Could not extract structured transaction rows from PDF text. Please verify statement format or upload CSV/Excel.")

    n_months = max(len(unique_months), 1)
    verified_monthly_income = round(total_credits / n_months)
    avg_monthly_debit = round(total_debits / n_months)
    net_monthly_surplus = round(verified_monthly_income - avg_monthly_debit)
    calculated_abb = round(sum(balances) / len(balances)) if balances else round(verified_monthly_income * 0.40)
    bounce_count = len(bounce_rows)

    if bounce_count == 0:
        utility_consistency = "High"
    elif bounce_count == 1:
        utility_consistency = "Moderate"
    else:
        utility_consistency = "Low"

    tenure_detected = 12 if n_months >= 10 else 6

    return {
        'success': True,
        'filename': filename,
        'parser_layer': 'Layer 2 (Regex Text Fallback)',
        'transactions_count': len(transactions),
        'months_detected': n_months,
        'unique_months': sorted(list(unique_months)),
        'verified_monthly_income': verified_monthly_income,
        'avg_monthly_debit': avg_monthly_debit,
        'net_monthly_surplus': net_monthly_surplus,
        'calculated_abb': calculated_abb,
        'bounce_count': bounce_count,
        'bounce_events': bounce_rows[:5],
        'utility_consistency': utility_consistency,
        'statement_tenure': tenure_detected,
    }


def parse_bank_statement(file_bytes: bytes, filename: str, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Main parser coordinating Layer 1 (Tabular), Layer 2 (Regex Fallback), and Layer 3 (Safety Guardrails).
    """
    if not file_bytes:
        raise ValueError("The uploaded statement file is empty (0 bytes).")

    fn_lower = filename.lower()

    # Step 1: Attempt Layer 1 (Tabular Extraction)
    raw_rows: List[List[str]] = []
    tabular_header_error = None
    try:
        raw_rows = extract_rows_from_file(file_bytes, filename, password)
    except Exception as e:
        # If it's a PDF and table extraction errored (e.g. password or table extraction issue), let PDF text fallback or password rethrow
        if fn_lower.endswith('.pdf'):
            tabular_header_error = str(e)
            if "password" in tabular_header_error.lower():
                raise
        else:
            raise

    # If tabular rows found, attempt to locate headers
    if raw_rows:
        try:
            header_idx, col_map = locate_headers(raw_rows)
            data_rows = raw_rows[header_idx + 1:]

            transactions = []
            unique_months = set()
            total_credits = 0.0
            total_debits = 0.0
            balances = []
            bounce_rows = []
            prev_bal = None

            for row in data_rows:
                if not row or not any(row):
                    continue

                # 1. Date
                date_col = col_map.get('date')
                if date_col is None or date_col >= len(row):
                    continue
                raw_date = row[date_col].strip()
                ym = parse_date_to_ym(raw_date)
                if not ym:
                    continue
                unique_months.add(ym)

                # 2. Description
                desc_col = col_map.get('description')
                narration = ""
                if desc_col is not None and desc_col < len(row):
                    narration = row[desc_col].strip()
                else:
                    # fallback to any non-date, non-empty string column
                    for idx, c in enumerate(row):
                        if idx != date_col and len(c.strip()) > 3 and not re.match(r'^\d', c.strip()):
                            narration = c.strip()
                            break

                # 3. Debit / Credit calculation
                debit = 0.0
                credit = 0.0

                dr_col = col_map.get('debit')
                cr_col = col_map.get('credit')
                amt_col = col_map.get('amount')
                type_col = col_map.get('type')

                if dr_col is not None or cr_col is not None:
                    debit = clean_currency(row[dr_col]) if dr_col is not None and dr_col < len(row) else 0.0
                    credit = clean_currency(row[cr_col]) if cr_col is not None and cr_col < len(row) else 0.0
                elif amt_col is not None and amt_col < len(row):
                    raw_amt = clean_currency(row[amt_col])
                    if type_col is not None and type_col < len(row):
                        t_val = row[type_col].strip().upper()
                        if any(w in t_val for w in ['CR', 'CREDIT', 'DEPOSIT', 'C']):
                            credit = abs(raw_amt)
                        elif any(w in t_val for w in ['DR', 'DEBIT', 'WITHDRAWAL', 'D']):
                            debit = abs(raw_amt)
                        elif raw_amt < 0:
                            debit = abs(raw_amt)
                        else:
                            credit = raw_amt
                    else:
                        if raw_amt < 0:
                            debit = abs(raw_amt)
                        else:
                            # check narration keywords
                            n_upper = narration.upper()
                            if any(w in n_upper for w in ['SALARY', 'CREDIT', 'CR', 'DEPOSIT']):
                                credit = raw_amt
                            else:
                                debit = raw_amt

                # 4. Balance
                bal_col = col_map.get('balance')
                balance = None
                if bal_col is not None and bal_col < len(row):
                    balance = clean_currency(row[bal_col])
                    if balance > 0:
                        balances.append(balance)
                        prev_bal = balance

                total_credits += credit
                total_debits += debit

                # Bounce check
                narr_upper = narration.upper()
                if any(bk in narr_upper for bk in BOUNCE_KEYWORDS):
                    bounce_rows.append({
                        'date': raw_date,
                        'narration': narration,
                        'amount': debit or credit or 0.0
                    })

                transactions.append({
                    'date': raw_date,
                    'narration': narration,
                    'debit': debit,
                    'credit': credit,
                    'balance': balance
                })

            if transactions:
                n_months = max(len(unique_months), 1)
                verified_monthly_income = round(total_credits / n_months)
                avg_monthly_debit = round(total_debits / n_months)
                net_monthly_surplus = round(verified_monthly_income - avg_monthly_debit)
                calculated_abb = round(sum(balances) / len(balances)) if balances else round(verified_monthly_income * 0.40)
                bounce_count = len(bounce_rows)

                if bounce_count == 0:
                    utility_consistency = "High"
                elif bounce_count == 1:
                    utility_consistency = "Moderate"
                else:
                    utility_consistency = "Low"

                tenure_detected = 12 if n_months >= 10 else 6

                return {
                    'success': True,
                    'filename': filename,
                    'parser_layer': 'Layer 1 (Tabular Extraction)',
                    'transactions_count': len(transactions),
                    'months_detected': n_months,
                    'unique_months': sorted(list(unique_months)),
                    'verified_monthly_income': verified_monthly_income,
                    'avg_monthly_debit': avg_monthly_debit,
                    'net_monthly_surplus': net_monthly_surplus,
                    'calculated_abb': calculated_abb,
                    'bounce_count': bounce_count,
                    'bounce_events': bounce_rows[:5],
                    'utility_consistency': utility_consistency,
                    'statement_tenure': tenure_detected,
                }

        except Exception as e:
            tabular_header_error = str(e)

    # Step 2: Fallback to Layer 2 for PDFs if Layer 1 found no tables or header detection failed
    if fn_lower.endswith('.pdf'):
        return parse_pdf_text_fallback(file_bytes, filename, password)

    # If it was CSV/Excel and failed:
    if tabular_header_error:
        raise ValueError(f"Could not parse bank statement table: {tabular_header_error}")
    
    raise ValueError("The uploaded statement file is empty or does not contain recognizable bank transaction records.")
