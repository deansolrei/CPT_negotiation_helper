"""
load_headway_fl.py
------------------
Imports the Headway Florida rates CSV directly into the intermediary_rates table.

Headway CSV format (wide / payer-as-columns):
    Row 1: "Florida Rates" header (skip)
    Row 2: CPT Code | Description | Payer1 | Payer2 | ...
    Row 3+: code | description | rate | rate | ...

Usage:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_headway_fl.py

Or pass a custom CSV path:
    python3 backend/load_headway_fl.py /path/to/headway_rates.csv
"""

import csv
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend.database import get_db

# Default path — the file the user already uploaded
DEFAULT_CSV = os.path.join(
    PROJECT_ROOT,
    "HEADWAY SOLREI FLORIDA RATES - Sheet1.csv",
)

STATE       = "FL"
PLATFORM    = "Headway"
EFF_DATE    = "2026-01-01"  # Update this when Headway sends new rate sheets


def clean_amount(raw: str) -> float | None:
    """Strip $, commas, spaces and return float, or None if empty."""
    v = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def ensure_cpt_codes(cur, code_descriptions: dict[str, str]) -> None:
    """Insert any CPT codes that don't already exist in cpt_codes."""
    for code, desc in code_descriptions.items():
        cur.execute(
            """
            INSERT INTO cpt_codes (cpt_code, short_description, full_description, category)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cpt_code) DO NOTHING
            """,
            (
                code,
                desc[:100] if desc else code,
                desc,
                "Telehealth E/M" if code.startswith("980") else "E/M",
            ),
        )


def load_headway_csv(csv_path: str) -> None:
    if not os.path.exists(csv_path):
        print(f"✗  File not found: {csv_path}")
        print("   Pass the path as an argument: python3 backend/load_headway_fl.py /path/to/file.csv")
        sys.exit(1)

    print(f"Reading: {csv_path}")

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows   = list(reader)

    # Find the header row (contains "CPT Code")
    header_idx = None
    for i, row in enumerate(rows):
        if row and "CPT Code" in row[0]:
            header_idx = i
            break

    if header_idx is None:
        print("✗  Could not find header row with 'CPT Code'. Check the file format.")
        sys.exit(1)

    header    = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    # Columns: 0=CPT Code, 1=Description, 2+=payer names
    payer_names = [h.strip() for h in header[2:]]
    print(f"Found {len(payer_names)} payers: {', '.join(payer_names)}")

    # Build code → description map for any new CPT codes
    code_descriptions: dict[str, str] = {}
    rate_data: list[tuple] = []   # (cpt_code, payer_name, amount)

    for row in data_rows:
        if not row or not row[0].strip():
            continue
        cpt_code = row[0].strip()
        desc     = row[1].strip() if len(row) > 1 else ""

        code_descriptions[cpt_code] = desc

        for col_idx, payer_name in enumerate(payer_names, start=2):
            raw = row[col_idx] if col_idx < len(row) else ""
            amt = clean_amount(raw)
            if amt is not None and amt > 0:
                rate_data.append((cpt_code, payer_name.strip(), amt))

    print(f"Found {len(code_descriptions)} CPT codes, {len(rate_data)} rate entries")

    with get_db() as cur:
        # 1. Ensure all CPT codes exist
        print("Ensuring CPT codes are in the database…")
        ensure_cpt_codes(cur, code_descriptions)

        # 2. Get Headway's intermediary_id
        cur.execute("SELECT intermediary_id FROM intermediaries WHERE name = %s", (PLATFORM,))
        row = cur.fetchone()
        if not row:
            print(f"✗  '{PLATFORM}' not found in intermediaries table.")
            print("   Run: python3 backend/load_intermediaries.py  first.")
            sys.exit(1)
        intermediary_id = row["intermediary_id"]
        print(f"Using intermediary_id={intermediary_id} for {PLATFORM}")

        # 3. Ensure payer names are in intermediary_payer_map
        print("Updating payer name mappings…")
        for payer_name in payer_names:
            cur.execute(
                """
                INSERT INTO intermediary_payer_map (intermediary_payer_name)
                VALUES (%s)
                ON CONFLICT (intermediary_payer_name) DO NOTHING
                """,
                (payer_name,),
            )

        # 4. Upsert all rates
        print("Importing rates…")
        imported = 0
        for cpt_code, payer_name, amount in rate_data:
            cur.execute(
                """
                INSERT INTO intermediary_rates
                    (intermediary_id, payer_name, cpt_code, state,
                     allowed_amount, effective_date, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT ON CONSTRAINT intermediary_rates_unique
                DO UPDATE SET
                    allowed_amount = EXCLUDED.allowed_amount,
                    updated_at     = NOW()
                """,
                (intermediary_id, payer_name, cpt_code, STATE, amount, EFF_DATE),
            )
            imported += 1

    print(f"\n✓  Done — {imported} Headway Florida rate(s) imported.")
    print(f"   Payers: {len(payer_names)}  ·  CPT codes: {len(code_descriptions)}")
    print("\nRestart uvicorn (or it will auto-reload), then refresh the dashboard.")
    print("The Billing Channel Comparison section will now show all Headway rates.")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    load_headway_csv(csv_path)
