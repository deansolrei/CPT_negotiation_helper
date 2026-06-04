"""
load_from_csv.py
----------------
Single-source-of-truth importer for ALL payer rates.

Reads payer_rates_template_*.csv and loads every payer — including
Florida Blue — into PostgreSQL using a clean DELETE-then-INSERT approach.

For each payer found in the CSV:
  1. Locates ALL active contracts for that payer (both NPI1 and NPI2)
  2. DELETES all existing fee schedule lines for those contracts
  3. Inserts fresh rates from the CSV into every contract

This guarantees the dashboard always reflects exactly what is in the CSV
with no stale rows from previous imports.

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python -m backend.load_from_csv
"""

import csv
import os
import sys
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT  = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJ_ROOT)

from backend.database import get_db  # noqa: E402


# ── Payer name mapping ────────────────────────────────────────────────────────
# Maps lowercase keywords found in the CSV → canonical payer name in the DB.
# Longest key wins (so "florida blue" matches before "blue").
PAYER_ALIASES = {
    "florida blue":  "Florida Blue",
    "massachusetts": "BCBS - Massachusetts",
    "blue cross":    "BCBS - Massachusetts",
    "bcbs":          "BCBS - Massachusetts",
    "aetna":         "Aetna",
    "ambetter":      "Ambetter",
    "carelon":       "Carelon",
    "beacon":        "Carelon",
    "cigna":         "Cigna",
    "optum":         "Optum / UHC",
    "uhc":           "Optum / UHC",
    "oscar":         "Oscar",
    "united":        "Optum / UHC",
    "quest":         "Quest Health",
    "wellmark":      "Wellmark Iowa",
}


def canonicalize(name: str) -> str:
    """Map a raw payer name to the DB payer name."""
    low = name.lower().strip()
    for alias in sorted(PAYER_ALIASES, key=len, reverse=True):
        if alias in low:
            return PAYER_ALIASES[alias]
    return name.strip()


def parse_date(raw: str) -> str | None:
    """Accept M/D/YY, M/D/YYYY, or YYYY-MM-DD; return YYYY-MM-DD or None."""
    if not raw or not raw.strip():
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    print(f"  ⚠  Could not parse date '{raw}' — storing as NULL")
    return None


def find_csv() -> str:
    """Return path to the most recent payer_rates_template_*.csv in project root."""
    candidates = sorted(
        [f for f in os.listdir(_PROJ_ROOT)
         if f.startswith("payer_rates_template") and f.endswith(".csv")],
        reverse=True,   # YYYY-MM-DD filenames sort correctly lexicographically
    )
    if not candidates:
        raise FileNotFoundError(
            "No payer_rates_template_*.csv found in project root.\n"
            "Expected: payer_rates_template_YYYY-MM-DD.csv"
        )
    return os.path.join(_PROJ_ROOT, candidates[0])


def read_csv(path: str) -> dict[str, list]:
    """
    Parse the rates CSV.
    Returns: { canonical_payer_name: [line_dict, ...] }
    Rows with missing payer_name, missing/non-numeric allowed_amount, or
    missing cpt_code are silently skipped.
    """
    payer_lines: dict[str, list] = {}
    skipped = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            payer_raw = (row.get("payer_name") or "").strip()
            if not payer_raw or payer_raw.startswith("#"):
                skipped += 1
                continue

            amount_raw = (row.get("allowed_amount") or "").strip()
            if not amount_raw or amount_raw.startswith("#"):
                skipped += 1
                continue   # no rate entered yet — skip silently

            try:
                amount = float(amount_raw)
            except ValueError:
                print(f"  ⚠  Skipping row — invalid allowed_amount: '{amount_raw}'")
                skipped += 1
                continue

            cpt = (row.get("cpt_code") or "").strip()
            if not cpt:
                skipped += 1
                continue

            canonical = canonicalize(payer_raw)
            payer_lines.setdefault(canonical, []).append({
                "cpt_code":         cpt,
                "modifier":         (row.get("modifier") or "").strip() or None,
                "place_of_service": (row.get("place_of_service") or "").strip() or None,
                "unit_type":        "per_service",
                "allowed_amount":   amount,
                "effective_date":   parse_date(row.get("effective_date") or ""),
                "end_date":         None,
                "notes":            (row.get("notes") or "").strip() or None,
            })

    if skipped:
        print(f"  (skipped {skipped} comment/blank/invalid rows)")
    return payer_lines


def load_all_contracts() -> dict[str, list]:
    """
    Fetch all active contracts from the database.
    Returns: { canonical_payer_name: [contract_dict, ...] }
    Each payer may have multiple contracts (NPI1 + NPI2).
    """
    with get_db() as cur:
        cur.execute("""
            SELECT c.contract_id, p.payer_name,
                   pe.legal_name, pe.entity_type, pe.npi_number
            FROM contracts c
            JOIN payers            p  ON c.payer_id           = p.payer_id
            JOIN provider_entities pe ON c.provider_entity_id = pe.provider_entity_id
            WHERE c.active = TRUE
            ORDER BY p.payer_name, pe.entity_type
        """)
        rows = cur.fetchall()

    result: dict[str, list] = {}
    for r in rows:
        canonical = canonicalize(r["payer_name"])
        result.setdefault(canonical, []).append(dict(r))
    return result


def main():
    print("=" * 65)
    print("Payer Rates CSV → PostgreSQL  (all payers, clean slate)")
    print("=" * 65)

    # ── Find CSV ──────────────────────────────────────────────────
    csv_path = find_csv()
    print(f"\nCSV: {os.path.basename(csv_path)}")

    # ── Read CSV ──────────────────────────────────────────────────
    print("\nReading rates from CSV…")
    payer_lines = read_csv(csv_path)
    total_csv = sum(len(v) for v in payer_lines.values())
    print(f"  {total_csv} rate rows across {len(payer_lines)} payers.")

    # ── Load contracts ────────────────────────────────────────────
    print("\nLoading contracts from database…")
    contract_map = load_all_contracts()
    print(f"  {sum(len(v) for v in contract_map.values())} contracts for "
          f"{len(contract_map)} payers.")

    # ── Process each payer ────────────────────────────────────────
    print()
    grand_deleted  = 0
    grand_inserted = 0
    skipped_payers = []

    for canonical in sorted(payer_lines.keys()):
        lines     = payer_lines[canonical]
        contracts = contract_map.get(canonical)

        print(f"{'─' * 65}")
        print(f"  {canonical}  ({len(lines)} codes in CSV)")

        if not contracts:
            print(f"  ⚠  No active contracts found — skipping.")
            print(f"     (Check PAYER_ALIASES if the DB name differs.)")
            skipped_payers.append(canonical)
            continue

        contract_ids = [c["contract_id"] for c in contracts]

        # Step 1 — clean slate: delete all existing lines for this payer
        with get_db() as cur:
            cur.execute(
                "DELETE FROM fee_schedule_lines WHERE contract_id = ANY(%s)",
                (contract_ids,)
            )
            deleted = cur.rowcount
        grand_deleted += deleted
        print(f"  Deleted {deleted} old rows from {len(contracts)} contract(s).")

        # Step 2 — insert fresh rows into every contract (NPI1 + NPI2)
        inserted = 0
        with get_db() as cur:
            for contract in contracts:
                cid = contract["contract_id"]
                for line in lines:
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
                    inserted += 1
                print(f"  ✓ [{cid}] {contract['legal_name']} ({contract['entity_type']})"
                      f" — {len(lines)} rows inserted")
        grand_inserted += inserted

    # ── Summary ───────────────────────────────────────────────────
    print(f"{'─' * 65}")
    print(f"\n✓ Done.")
    print(f"  Deleted : {grand_deleted} old rows")
    print(f"  Inserted: {grand_inserted} new rows")
    if skipped_payers:
        print(f"\n  ⚠  Skipped (no DB contract): {', '.join(skipped_payers)}")
        print("     Add these payers to PAYER_ALIASES or create their contracts.")
    print("\nRefresh the dashboard (↻ button) to see the updated rates.")


if __name__ == "__main__":
    main()
