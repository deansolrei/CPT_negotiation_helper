import pandas as pd
import numpy as np

# 1) Load the file (adjust sheet_name if needed)
fname = "Solrei_Behavioral_Health_Inc__2026-01-01_2026-04-15_Payments.xlsx"
raw = pd.read_excel(fname, header=None)

# 2) Find the header row by looking for the row that starts with "Payment date"
header_row_idx = raw.index[raw.iloc[:,0].astype(str).str.contains("Payment date", na=False)]
if len(header_row_idx) == 0:
    raise ValueError("Could not find header row containing 'Payment date'")
header_row = header_row_idx[0]

df = pd.read_excel(fname, header=header_row)

# 3) Normalize column names
df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

# 4) Keep only the columns we care about
needed = {
    "payment_date": "payment_date",
    "payment_amount": "payment_amount",
    "provider_id": "provider_id",
    "provider_name": "provider_name",
    "appointment_location_state": "state",
    "billing_type": "billing_type",
    "payer": "payer",
    "appointment_date": "appointment_date",
}

# Map from existing columns to canonical names
col_map = {}
for c in df.columns:
    if "payment_date" == c:
        col_map[c] = "payment_date"
    elif "payment_amount" == c:
        col_map[c] = "payment_amount"
    elif "provider_id" == c:
        col_map[c] = "provider_id"
    elif "provider_name" == c:
        col_map[c] = "provider_name"
    elif "appointment_location_state" == c:
        col_map[c] = "state"
    elif "billing_type" == c:
        col_map[c] = "billing_type"
    elif c == "payer":
        col_map[c] = "payer"
    elif "appointment_date" == c:
        col_map[c] = "appointment_date"
    elif "cpt" in c:
        col_map[c] = "cpt_codes"

# Rename
df = df.rename(columns=col_map)

# Drop rows that are just header text, NaNs, etc.
df = df[df["payment_amount"].notna()].copy()

# 5) Parse CPT codes into list
df["cpt_codes"] = df["cpt_codes"].where(df["cpt_codes"].notna(), "")
df["cpt_codes"] = df["cpt_codes"].astype(str).str.strip()
df["cpt_list"] = df["cpt_codes"].str.replace(" ", "", regex=False).str.split(",")


# 6) Define the codes we care about
EM_CODES = {"99214", "99215", "99205"}
PSYCH_CODES = {"90833", "90836", "90838"}

def classify_pair(codes):
    """
    Return (EM, PSYCH) if the row is exactly EM+psych with no extras.
    Otherwise return None.
    """
    if not isinstance(codes, list):
        return None

    codes = [str(c).strip() for c in codes if pd.notna(c) and str(c).strip() != ""]

    if len(codes) != 2:
        return None

    a, b = codes

    if a in EM_CODES and b in PSYCH_CODES:
        return (a, b)
    if b in EM_CODES and a in PSYCH_CODES:
        return (b, a)

    return None


df["pair"] = df["cpt_list"].apply(classify_pair)

# 7) Keep only rows that are clean EM+psych pairs (no 90785, no odd triples)
pairs = df[df["pair"].notna()].copy()

# 8) Split pair into separate columns
pairs["em_code"] = pairs["pair"].apply(lambda t: t[0])
pairs["psych_code"] = pairs["pair"].apply(lambda t: t[1])

from collections import defaultdict

group_cols = ["provider_name", "state", "payer"]

# Average payment for identical combo to smooth out noise
pairs["payment_amount"] = pairs["payment_amount"].astype(float)
combo_summary = (
    pairs
    .groupby(group_cols + ["em_code", "psych_code"], as_index=False)["payment_amount"]
    .mean()
)

combo_summary.head()

import numpy.linalg as LA

TARGET_CODES = ["99214", "99215", "99205", "90833", "90836", "90838"]

def solve_group(sub):
    """
    sub: rows for one provider+state+payer with columns
         em_code, psych_code, payment_amount.
    Returns: dict of solved CPT rates for the TARGET_CODES in this group.
    """
    # Determine which codes actually appear in this group
    ems = sorted(sub["em_code"].unique())
    psychs = sorted(sub["psych_code"].unique())
    codes_in_group = sorted(set(ems) | set(psychs))

    # Index mapping CPT -> column index in A
    idx = {c: i for i, c in enumerate(codes_in_group)}

    # Build A matrix and b vector
    rows = []
    b = []
    for _, row in sub.iterrows():
        em = row["em_code"]
        psych = row["psych_code"]
        y = row["payment_amount"]
        vec = [0.0] * len(codes_in_group)
        vec[idx[em]] = 1.0
        vec[idx[psych]] = 1.0
        rows.append(vec)
        b.append(y)

    A = np.array(rows)
    b = np.array(b)

    # Solve with least squares A x ≈ b
    x, *_ = LA.lstsq(A, b, rcond=None)

    # Map back to CPT code -> rate
    result = {c: x[idx[c]] for c in codes_in_group}
    # Include missing codes as NaN (if a code never appears in this group)
    for c in TARGET_CODES:
        result.setdefault(c, np.nan)
    return result

# Apply solver per group
solved_rows = []

for keys, sub in combo_summary.groupby(group_cols):
    solution = solve_group(sub)
    row = {
        "provider_name": keys[0],
        "state": keys[1],
        "payer": keys[2],
    }
    row.update(solution)
    solved_rows.append(row)

rates = pd.DataFrame(solved_rows)

# Optional: round to cents
for c in TARGET_CODES:
    rates[c] = rates[c].round(2)

import os
os.makedirs("output", exist_ok=True)

out_path = "output/provider_state_payer_cpt_rates.csv"
rates = rates.sort_values(["provider_name", "state", "payer"]).reset_index(drop=True)

rates.to_csv(out_path, index=False)

counts = (
    combo_summary.groupby(group_cols)["payment_amount"]
    .count()
    .reset_index(name="n_pairs")
)

rates = rates.merge(counts, on=group_cols, how="left")


rates.head(20)
