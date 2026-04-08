"""
load_florida_blue.py
--------------------
Loads Florida Blue fee schedule rates from the payer_rates_template CSV.

The CSV (payer_rates_template_*.csv in the project root) is the single
source of truth for Florida Blue rates. Edit that file with your actual
contracted amounts, then run this script to push them to the database.

What this script does:
  1. Finds the most recent payer_rates_template_*.csv in the project root
  2. Reads all rows where payer_name contains "Florida Blue"
  3. DELETES all existing Florida Blue fee schedule lines (clean slate)
  4. Inserts the fresh rates into BOTH Florida Blue contracts:
       - Florida Blue × Jodene Jensen, PMHNP-BC       (NPI1 / individual)
       - Florida Blue × Solrei Behavioral Health, Inc. (NPI2 / group)

Deleting before inserting prevents the duplicate-rate problem where old
estimated rates and new actual rates coexist and cause sections of the
dashboard to disagree.

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_florida_blue.py
"""

import csv
import os
import sys
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT  = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJ_ROOT)

from backend.database import get_db   # noqa: E402  (import after path setup)


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_csv() -> str:
    """Return path to the most recent payer_rates_template_*.csv."""
    candidates = sorted(
        [f for f in os.listdir(_PROJ_ROOT)
         if f.startswith("payer_rates_template") and f.endswith(".csv")],
        reverse=True,   # newest name first (YYYY-MM-DD sorts lexicographically)
    )
    if not candidates:
        raise FileNotFoundError(
            "No payer_rates_template_*.csv found in the project root.\n"
            "Expected a file named like: payer_rates_template_2026-04-06.csv"
        )
    return os.path.join(_PROJ_ROOT, candidates[0])


def parse_date(raw: str) -> str | None:
    """Accept M/D/YY, M/D/YYYY, or YYYY-MM-DD; return YYYY-MM-DD or None."""
    if not raw or not raw.strip():
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    print(f"  ⚠  Could not parse date '{raw}' — will store as NULL")
    return None


def read_florida_blue_rows(csv_path: str) -> list[dict]:
    """
    Read the CSV and return only Florida Blue rows that have an allowed_amount.
    Skips comment lines (starting with #) and blank rows.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            payer = (row.get("payer_name") or "").strip()
            if not payer or payer.startswith("#"):
                continue
            if "florida" not in payer.lower():
                continue

            amount_raw = (row.get("allowed_amount") or "").strip()
            if not amount_raw or amount_raw.startswith("#"):
                continue   # no rate entered yet — skip silently

            try:
                amount = float(amount_raw)
            except ValueError:
                print(f"  ⚠  Skipping row — bad allowed_amount: '{amount_raw}'")
                continue

            cpt = (row.get("cpt_code") or "").strip()
            if not cpt:
                continue

            rows.append({
                "cpt_code":         cpt,
                "modifier":         (row.get("modifier") or "").strip() or None,
                "place_of_service": (row.get("place_of_service") or "10").strip() or "10",
                "unit_type":        "per_service",
                "allowed_amount":   amount,
                "effective_date":   parse_date(row.get("effective_date") or ""),
                "end_date":         None,
                "notes":            (row.get("notes") or "").strip() or None,
            })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("Florida Blue Fee Schedule Loader")
    print("Source: payer_rates_template CSV  →  PostgreSQL")
    print("=" * 65)

    # ── 1. Find CSV ───────────────────────────────────────────────
    csv_path = find_csv()
    print(f"\nCSV: {os.path.basename(csv_path)}")

    # ── 2. Read Florida Blue rows from CSV ────────────────────────
    fl_rows = read_florida_blue_rows(csv_path)
    if not fl_rows:
        print("\nERROR: No Florida Blue rows with rates found in the CSV.")
        print("  Make sure rows have 'Florida Blue' in the payer_name column")
        print("  and a numeric value in the allowed_amount column.")
        sys.exit(1)

    print(f"  {len(fl_rows)} Florida Blue rate rows found in CSV.")
    for r in fl_rows:
        print(f"    {r['cpt_code']:8s}  ${r['allowed_amount']:>8.2f}"
              f"  mod={r['modifier'] or '—'}  eff={r['effective_date'] or 'NULL'}")

    # ── 3. Find Florida Blue contracts in the database ────────────
    print("\nLooking up Florida Blue contracts in database...")
    with get_db() as cur:
        cur.execute("""
            SELECT c.contract_id, p.payer_name, pe.legal_name, pe.entity_type, pe.npi_number
            FROM contracts c
            JOIN payers            p  ON c.payer_id           = p.payer_id
            JOIN provider_entities pe ON c.provider_entity_id = pe.provider_entity_id
            WHERE lower(p.payer_name) LIKE '%florida%'
              AND c.active = TRUE
            ORDER BY pe.entity_type
        """)
        contracts = cur.fetchall()

    if not contracts:
        print("ERROR: No active Florida Blue contracts found in the database.")
        print("  Run 09_seed_data.sql first to set up the contracts.")
        sys.exit(1)

    for c in contracts:
        print(f"  [{c['contract_id']}] {c['payer_name']} × {c['legal_name']}"
              f"  ({c['entity_type']} · NPI {c['npi_number']})")

    contract_ids = [c["contract_id"] for c in contracts]

    # ── 4. Delete ALL existing Florida Blue fee schedule lines ────
    print(f"\nDeleting existing Florida Blue fee schedule lines "
          f"(contracts: {contract_ids})...")
    with get_db() as cur:
        cur.execute(
            "DELETE FROM fee_schedule_lines WHERE contract_id = ANY(%s)",
            (contract_ids,)
        )
        deleted = cur.rowcount
    print(f"  Deleted {deleted} old rows.")

    # ── 5. Insert fresh rates for every contract ──────────────────
    print(f"\nInserting {len(fl_rows)} rates into {len(contracts)} contracts...")
    total_inserted = 0

    with get_db() as cur:
        for contract in contracts:
            cid = contract["contract_id"]
            for line in fl_rows:
                cur.execute("""
                    INSERT INTO fee_schedule_lines
                        (contract_id, cpt_code, modifier, place_of_service,
                         unit_type, allowed_amount, effective_date, end_date, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    cid,
                    line["cpt_code"],
                    line["modifier"],
                    line["place_of_service"],
                    line["unit_type"],
                    line["allowed_amount"],
                    line["effective_date"],
                    line["end_date"],
                    line["notes"],
                ))
                total_inserted += 1
            print(f"  ✓ [{cid}] {contract['legal_name']} ({contract['entity_type']})"
                  f" — {len(fl_rows)} lines inserted")

    # ── 6. Verify: no duplicates should exist ─────────────────────
    print("\nVerifying — no duplicates should exist...")
    with get_db() as cur:
        cur.execute("""
            SELECT COUNT(*) AS dupes
            FROM (
                SELECT contract_id, cpt_code
                FROM fee_schedule_lines
                WHERE contract_id = ANY(%s)
                GROUP BY contract_id, cpt_code
                HAVING COUNT(*) > 1
            ) d
        """, (contract_ids,))
        dupes = cur.fetchone()["dupes"]

    if dupes == 0:
        print("  ✓ Zero duplicate rows — clean.")
    else:
        print(f"  ⚠  {dupes} duplicate (contract, CPT) pairs still found.")
        print("     This should not happen — please report this.")

    print(f"\n{'=' * 65}")
    print(f"✓ Done — {total_inserted} rows inserted across {len(contracts)} contracts.")
    print("\nNext steps:")
    print("  1. Restart uvicorn if it's running:")
    print("       lsof -ti:8000 | xargs kill -9")
    print("       uvicorn backend.main:app --reload")
    print("  2. Refresh the dashboard (↻ button) — Rate Comparison and")
    print("     Billing Channel Comparison should now show the same rates.")


if __name__ == "__main__":
    main()
