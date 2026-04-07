"""
load_florida_blue.py
--------------------
Imports Florida Blue (BCBS Florida) fee schedule rates for Solrei Behavioral Health.

Rate policy (per Florida Blue contract document):
  - APRNs/NPs: 80% of CMS Medicare Physician Fee Schedule, FL locality 99
  - EXCEPT for MAT codes with HF modifier (Table 1 fixed rates)

This script:
  1. Fetches Medicare 2026 benchmark rates from the local database
  2. Calculates 80% of each rate for Florida Blue standard NP rates
  3. Imports fixed Table 1 MAT rates with HF modifier
  4. Loads for BOTH Florida Blue contracts:
       - Contract: Florida Blue × Solrei Behavioral Health, Inc. (Group NPI2)
       - Contract: Florida Blue × Jodene Jensen (Individual NPI1)

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_florida_blue.py
"""

import json
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "http://localhost:8000/api"
IMPORT_URL = f"{BASE_URL}/import-fee-schedule"

# ── Florida Blue NP rate policy ────────────────────────────────
# 80% of Medicare Physician Fee Schedule, FL locality 99
FL_BLUE_NP_FACTOR = 0.80

# ── Table 1: Fixed MAT rates (HF modifier required) ───────────
# Source: Florida Blue fee schedule document, Table 1
MAT_RATES = [
    {"cpt_code": "99203", "modifier": "HF", "allowed_amount": 118.45,
     "notes": "MAT new patient 30-44 min. Table 1 fixed rate."},
    {"cpt_code": "99204", "modifier": "HF", "allowed_amount": 177.53,
     "notes": "MAT new patient 45-59 min. Table 1 fixed rate."},
    {"cpt_code": "99205", "modifier": "HF", "allowed_amount": 234.66,
     "notes": "MAT new patient 60-74 min. Table 1 fixed rate."},
    {"cpt_code": "99213", "modifier": "HF", "allowed_amount": 86.75,
     "notes": "MAT established patient 30-44 min. Table 1 fixed rate."},
    {"cpt_code": "99214", "modifier": "HF", "allowed_amount": 123.22,
     "notes": "MAT established patient 45-59 min. Table 1 fixed rate."},
    {"cpt_code": "99215", "modifier": "HF", "allowed_amount": 172.53,
     "notes": "MAT established patient 60-74 min. Table 1 fixed rate."},
]


def api_get(path):
    url = f"{BASE_URL}/{urllib.parse.quote(path, safe='=&?/')}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def api_post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 60)
    print("Florida Blue Fee Schedule Import")
    print("Rate policy: 80% of Medicare FL locality 99 (NP/APRN)")
    print("=" * 60)
    print()

    # ── Step 1: Find Florida Blue contracts ───────────────────────
    print("Step 1: Finding Florida Blue contracts...")
    contracts = api_get("contracts?active_only=true")
    fl_blue_contracts = [
        c for c in contracts if "Florida Blue" in c["payer_name"]]

    if not fl_blue_contracts:
        print("ERROR: No Florida Blue contracts found. Run 09_seed_data.sql first.")
        return

    for c in fl_blue_contracts:
        print(f"  Found: [{c['contract_id']}] {c['payer_name']} × {c['provider_name']} "
              f"({c['entity_type']}, PID: {c.get('payer_contract_id', 'N/A')})")
    print()

    # ── Step 2: Get Medicare 2026 benchmark rates ──────────────────
    print("Step 2: Fetching Medicare 2026 benchmark rates...")
    benchmarks = api_get(
        "benchmark?source_name=Medicare 2026&locality=FL&year=2026")

    if not benchmarks:
        print("ERROR: No Medicare 2026 benchmark rates found.")
        print("  Run: python3 backend/load_medicare_2026.py")
        return

    print(f"  Found {len(benchmarks)} benchmark rates.")
    print()

    # ── Step 3: Build standard NP rate lines (80% of Medicare) ────
    standard_lines = []
    for b in benchmarks:
        rate = round(float(b["allowed_amount"]) * FL_BLUE_NP_FACTOR, 2)
        standard_lines.append({
            "cpt_code":       b["cpt_code"],
            "modifier":       "95",   # telehealth synchronous
            "place_of_service": "10",  # telehealth in patient home
            "unit_type":      "per_service",
            "allowed_amount": rate,
            "effective_date": "2026-01-01",
            "end_date":       None,
            "notes": (
                f"FL Blue NP rate: 80% × Medicare ${float(b['allowed_amount']):.2f} "
                f"= ${rate:.2f}. FL locality 99."
            ),
        })

    # ── Step 4: Add Table 1 MAT fixed rates ───────────────────────
    mat_lines = []
    for mat in MAT_RATES:
        mat_lines.append({
            "cpt_code":         mat["cpt_code"],
            "modifier":         mat["modifier"],
            "place_of_service": "10",
            "unit_type":        "per_service",
            "allowed_amount":   mat["allowed_amount"],
            "effective_date":   "2026-01-01",
            "end_date":         None,
            "notes":            mat["notes"],
        })

    all_lines = standard_lines + mat_lines
    print(
        f"Step 3: Built {len(standard_lines)} standard NP lines (80% of Medicare)")
    print(
        f"        + {len(mat_lines)} Table 1 MAT lines (HF modifier, fixed rates)")
    print(f"        = {len(all_lines)} total lines per contract")
    print()

    # ── Step 5: Import for each Florida Blue contract ─────────────
    print("Step 4: Importing to all Florida Blue contracts...")
    total_imported = 0
    for contract in fl_blue_contracts:
        payload = {
            "contract_id": contract["contract_id"],
            "lines": all_lines,
        }
        try:
            result = api_post(IMPORT_URL, payload)
            print(f"  ✓ Contract [{contract['contract_id']}] "
                  f"{contract['provider_name']}: {result['lines_upserted']} lines imported")
            total_imported += result["lines_upserted"]
        except urllib.error.HTTPError as e:
            print(
                f"  ✗ Contract [{contract['contract_id']}] error: {e.read().decode()}")

    print()
    print("=" * 60)
    print(f"✓ Import complete: {total_imported} total lines across "
          f"{len(fl_blue_contracts)} Florida Blue contracts")
    print()

    # ── Step 6: Show a preview of the rate gaps ───────────────────
    print("Rate gap preview (your highest-volume codes):")
    print(
        f"  {'Code':<8} {'Medicare':>10} {'FL Blue':>10} {'% of Med':>10} {'Gap/Unit':>10}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    highlight_codes = ["99214", "99213", "99215",
                       "90833", "90837", "90792", "90791"]
    bench_map = {b["cpt_code"]: float(b["allowed_amount"]) for b in benchmarks}

    for code in highlight_codes:
        if code in bench_map:
            medicare = bench_map[code]
            fl_blue = round(medicare * FL_BLUE_NP_FACTOR, 2)
            pct = round((fl_blue / medicare) * 100, 1)
            gap = round(medicare * 1.30 - fl_blue, 2)   # gap to 130% target
            print(
                f"  {code:<8} ${medicare:>9.2f} ${fl_blue:>9.2f} {pct:>9.1f}% ${gap:>9.2f}")

    print()
    print("These are gaps to your 130% target. Every row above is a negotiation opportunity.")
    print()
    print("Next steps:")
    print("  1. View full dashboard: http://localhost:8000/api/dashboard?payer_id=1")
    print("  2. View underpaid codes: http://localhost:8000/api/dashboard/underpaid/1")
    print("  3. View payer summary:   http://localhost:8000/api/dashboard/summary")


if __name__ == "__main__":
    main()
