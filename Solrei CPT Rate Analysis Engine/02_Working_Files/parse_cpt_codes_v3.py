import os
import pandas as pd
import numpy as np
import numpy.linalg as LA

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "solrei_payouts_2025 - 2026.csv"
OUTPUT_DIR = "output"

TARGET_CODES = ["99214", "90833", "90836", "90838", "99215", "99204", "99205"]
EM_CODES = {"99214", "99215", "99204", "99205", "98006"}
PSYCH_CODES = {"90833", "90836", "90838"}

# If None, include all
YEAR_FILTER = None          # e.g. 2025, 2026, or None
PLATFORM_FILTER = None      # e.g. "Headway", "Alma", or None
PROVIDER_FILTER = None      # e.g. "Katherine Robins", "Jodene Jensen", or None

# ============================================================
# HELPERS
# ============================================================

def normalize_columns(df):
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df

def ensure_required_columns(df):
    required = [
        "payment_date",
        "payment_amount",
        "provider_name",
        "appointment_location_state",
        "billing_type",
        "payer",
        "appointment_date",
        "cpt_codes",
        "billing_platform",
        "service_year",
        "source_file",
        "notes",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df

def normalize_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip().lower()

def valid_platform_type(row):
    platform = normalize_text(row["billing_platform"])
    billing_type = normalize_text(row["billing_type"])

    # Exclude anomalies
    if billing_type in {"deduction", "cashpay item"}:
        return False

    # Headway logic
    if platform == "headway" and billing_type == "insurance":
        return True

    # Alma logic (allow a few variants just in case)
    if platform == "alma" and billing_type in {"paid claim", "paid_claim", "paidclaim"}:
        return True

    return False

def clean_cpt_list(value):
    if pd.isna(value):
        return []

    codes = [x.strip() for x in str(value).replace(" ", "").split(",") if x.strip()]

    # Normalize 98006 -> 99214 everywhere
    normalized = []
    for code in codes:
        if code == "98006":
            normalized.append("99214")
        else:
            normalized.append(code)

    return normalized

def classify_row(codes):
    """
    Return a dict describing whether the row is:
    - single target code
    - valid two-code combo (EM + psych)
    Otherwise None
    """
    if not isinstance(codes, list):
        return None

    codes = [c for c in codes if c in set(TARGET_CODES) | {"99214"}]

    if len(codes) == 1:
        code = codes[0]
        if code in TARGET_CODES:
            return {"row_type": "single", "single_code": code}

    if len(codes) == 2:
        a, b = codes
        if a in EM_CODES and b in PSYCH_CODES:
            return {"row_type": "pair", "em_code": "99214" if a == "98006" else a, "psych_code": b}
        if b in EM_CODES and a in PSYCH_CODES:
            return {"row_type": "pair", "em_code": "99214" if b == "98006" else b, "psych_code": a}

    return None

def solve_group(sub):
    """
    Solve one group:
    billing_platform + service_year + provider_name + state + payer
    """
    all_codes = sorted(set(TARGET_CODES))
    idx = {c: i for i, c in enumerate(all_codes)}

    rows = []
    b = []

    for _, row in sub.iterrows():
        vec = [0.0] * len(all_codes)

        if row["row_type"] == "single":
            code = row["single_code"]
            if code in idx:
                vec[idx[code]] = 1.0
                rows.append(vec)
                b.append(row["payment_amount"])

        elif row["row_type"] == "pair":
            em = row["em_code"]
            psych = row["psych_code"]
            if em in idx and psych in idx:
                vec[idx[em]] = 1.0
                vec[idx[psych]] = 1.0
                rows.append(vec)
                b.append(row["payment_amount"])

    if not rows:
        return None

    A = np.array(rows, dtype=float)
    b = np.array(b, dtype=float)

    # Solve least squares
    x, residuals, rank, s = LA.lstsq(A, b, rcond=None)

    result = {code: round(float(x[idx[code]]), 2) for code in all_codes}
    result["equation_count"] = int(len(rows))
    result["matrix_rank"] = int(rank)

    # Diagnostic: underdetermined if rank < number of distinct used columns
    used_cols = np.where(np.abs(A).sum(axis=0) > 0)[0]
    result["used_code_count"] = int(len(used_cols))
    result["is_underdetermined"] = bool(rank < len(used_cols))

    return result

# ============================================================
# LOAD
# ============================================================

df = pd.read_csv(INPUT_FILE, skipinitialspace=True)
df = normalize_columns(df)
df = ensure_required_columns(df)

print("\nSample billing_platform values (first 20) BEFORE filtering:")
print(df["billing_platform"].head(20))

print("\nSample billing_type values (first 20) BEFORE filtering:")
print(df["billing_type"].head(20))

# Normalize / type cleanup
df["payment_amount"] = pd.to_numeric(df["payment_amount"], errors="coerce")
df["appointment_date"] = pd.to_datetime(df["appointment_date"], errors="coerce")
df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce")

# If service_year is blank, derive from appointment_date
df["service_year"] = df["service_year"].where(df["service_year"].notna(), df["appointment_date"].dt.year)
df["service_year"] = pd.to_numeric(df["service_year"], errors="coerce").astype("Int64")

# Drop unusable rows
df = df[df["payment_amount"].notna()].copy()

print("\nBilling platform counts BEFORE valid_platform_type filter:")
print(df["billing_platform"].astype(str).str.strip().value_counts(dropna=False))

print("\nBilling type counts BEFORE valid_platform_type filter:")
print(df["billing_type"].astype(str).str.strip().value_counts(dropna=False))

# Drop unusable rows
df = df[df["payment_amount"].notna()].copy()

print("\nBilling platform counts BEFORE any platform/billing_type filter:")
print(df["billing_platform"].astype(str).str.strip().value_counts(dropna=False))

print("\nBilling type counts BEFORE any platform/billing_type filter:")
print(df["billing_type"].astype(str).str.strip().value_counts(dropna=False))

# TEMP: do not filter by valid_platform_type; keep both Alma and Headway
# df = df[df.apply(valid_platform_type, axis=1)].copy()


# Optional filters
if YEAR_FILTER is not None:
    df = df[df["service_year"] == YEAR_FILTER]

if PLATFORM_FILTER is not None:
    df = df[df["billing_platform"].astype(str).str.strip().str.lower() == PLATFORM_FILTER.strip().lower()]

if PROVIDER_FILTER is not None:
    df = df[df["provider_name"].astype(str).str.strip().str.lower() == PROVIDER_FILTER.strip().lower()]

# CPT parsing
df["cpt_list"] = df["cpt_codes"].apply(clean_cpt_list)
df["parsed"] = df["cpt_list"].apply(classify_row)

parsed = df[df["parsed"].notna()].copy()

parsed["row_type"] = parsed["parsed"].apply(lambda x: x["row_type"])
parsed["single_code"] = parsed["parsed"].apply(lambda x: x.get("single_code"))
parsed["em_code"] = parsed["parsed"].apply(lambda x: x.get("em_code"))
parsed["psych_code"] = parsed["parsed"].apply(lambda x: x.get("psych_code"))

# Rename state for cleaner output
parsed["state"] = parsed["appointment_location_state"]

# ============================================================
# SUMMARIZE INPUT EQUATIONS
# ============================================================

group_cols = [
    "billing_platform",
    "service_year",
    "provider_name",
    "state",
    "payer",
]

equation_summary = (
    parsed.groupby(group_cols + ["row_type", "single_code", "em_code", "psych_code"], dropna=False, as_index=False)
    .agg(
        avg_payment_amount=("payment_amount", "mean"),
        claim_count=("payment_amount", "size")
    )
)

equation_summary["avg_payment_amount"] = equation_summary["avg_payment_amount"].round(2)

# ============================================================
# SOLVE
# ============================================================

solved_rows = []

for keys, sub in parsed.groupby(group_cols):
    solution = solve_group(sub)
    if solution is None:
        continue

    row = {
        "billing_platform": keys[0],
        "service_year": keys[1],
        "provider_name": keys[2],
        "state": keys[3],
        "payer": keys[4],
    }
    row.update(solution)
    solved_rows.append(row)

rates = pd.DataFrame(solved_rows)

if not rates.empty:
    ordered_cols = [
        "billing_platform",
        "service_year",
        "provider_name",
        "state",
        "payer",
        "99214",
        "90833",
        "90836",
        "90838",
        "99215",
        "99204",
        "99205",
        "equation_count",
        "used_code_count",
        "matrix_rank",
        "is_underdetermined",
    ]
    existing_cols = [c for c in ordered_cols if c in rates.columns]
    rates = rates[existing_cols].sort_values(
        ["billing_platform", "service_year", "provider_name", "state", "payer"]
    ).reset_index(drop=True)

# ============================================================
# OUTPUT
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

parsed_out = os.path.join(OUTPUT_DIR, "parsed_rows_used_for_solving.csv")
equation_out = os.path.join(OUTPUT_DIR, "equation_summary_by_group.csv")
rates_out = os.path.join(OUTPUT_DIR, "cpt_rates_by_platform_year_provider_state_payer.csv")

parsed.to_csv(parsed_out, index=False)
equation_summary.to_csv(equation_out, index=False)
rates.to_csv(rates_out, index=False)

# Optional convenience outputs
if not rates.empty:
    headway = rates[rates["billing_platform"].astype(str).str.strip().str.lower() == "headway"]
    alma = rates[rates["billing_platform"].astype(str).str.strip().str.lower() == "alma"]

    headway.to_csv(os.path.join(OUTPUT_DIR, "cpt_rates_headway_only.csv"), index=False)
    alma.to_csv(os.path.join(OUTPUT_DIR, "cpt_rates_alma_only.csv"), index=False)

print("Done.")
print(f"Parsed rows used: {len(parsed):,}")
print(f"Groups solved: {len(rates):,}")
print(f"Output folder: {os.path.abspath(OUTPUT_DIR)}")
print(f"Main output: {os.path.abspath(rates_out)}")
