"""
load_payer_rates.py
-------------------
General-purpose loader for payer fee schedules (direct contracted rates).
Reads a CSV and imports rates into the fee_schedule_lines table.

HOW IT WORKS:
  1. You export or type your contracted rates into the CSV template
     (download from: python3 backend/load_payer_rates.py --template)
  2. Fill in the allowed_amount column for each CPT code
  3. Run: python3 backend/load_payer_rates.py your_rates.csv

USAGE:
    # Download blank CSV template:
    python3 backend/load_payer_rates.py --template

    # Import a filled CSV:
    python3 backend/load_payer_rates.py "Aetna rates 2026.csv"

    # List payers and their contracts:
    python3 backend/load_payer_rates.py --list-payers

TEMPLATE COLUMNS:
    payer_name      Required. Must match exactly (run --list-payers to see options)
    cpt_code        Required. Must exist in the cpt_codes table
    allowed_amount  Required. Your contracted rate in dollars (e.g. 145.00)
    modifier        Optional. e.g. 95, GT, HF — leave blank if none
    place_of_service Optional. e.g. 10 (telehealth), 11 (office) — leave blank
    effective_date  Optional. YYYY-MM-DD format
    notes           Optional. Free text
"""

from backend.database import get_db
import csv
import io
import os
import sys
from datetime import date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_ROOT)


# Solrei's CPT codes in the preferred display order
TEMPLATE_CPTS = [
    "99214", "99215", "90833", "90836", "90838",
    "99204", "99205", "90785", "98003", "98002", "98006", "98007",
]


def list_payers():
    """Print all payers and their active contracts."""
    with get_db() as cur:
        cur.execute(
            """
            SELECT p.payer_name, p.payer_id,
                   COUNT(c.contract_id) AS contract_count,
                   STRING_AGG(c.product_line, ', ' ORDER BY c.product_line) AS product_lines
            FROM payers p
            LEFT JOIN contracts c ON p.payer_id = c.payer_id AND c.active = TRUE
            GROUP BY p.payer_name, p.payer_id
            ORDER BY p.payer_name
            """
        )
        rows = cur.fetchall()

    print("\nPayers in the database:")
    print(f"{'Payer Name':<35} {'Contracts':<12} {'Product Lines'}")
    print("-" * 80)
    for r in rows:
        print(
            f"{r['payer_name']:<35} {r['contract_count']:<12} {r['product_lines'] or '—'}")
    print()


def generate_template():
    """Write a blank CSV template to stdout / a file."""
    filename = f"payer_rates_template_{date.today()}.csv"

    with get_db() as cur:
        cur.execute(
            "SELECT p.payer_name FROM payers p ORDER BY p.payer_name"
        )
        payer_names = [r["payer_name"] for r in cur.fetchall()]

        cur.execute(
            "SELECT cpt_code, short_description FROM cpt_codes WHERE cpt_code = ANY(%s)",
            (TEMPLATE_CPTS,)
        )
        cpt_map = {r["cpt_code"]: r["short_description"]
                   for r in cur.fetchall()}

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["payer_name", "cpt_code", "allowed_amount",
                     "modifier", "place_of_service", "effective_date", "notes"])
    writer.writerow(["# INSTRUCTIONS:", "", "", "", "", "", ""])
    writer.writerow(["# payer_name",     "Required. One of: " +
                    ", ".join(payer_names), "", "", "", "", ""])
    writer.writerow(
        ["# cpt_code",       "Required. CPT code", "", "", "", "", ""])
    writer.writerow(
        ["# allowed_amount", "Required. Contracted rate in $ (e.g. 145.00)", "", "", "", "", ""])
    writer.writerow(
        ["# modifier",       "Optional. e.g. 95 or HF — leave blank if none", "", "", "", "", ""])
    writer.writerow(["# place_of_service",
                    "Optional. 10=telehealth, 11=office", "", "", "", "", ""])
    writer.writerow(
        ["# effective_date", "Optional. YYYY-MM-DD", "", "", "", "", ""])
    writer.writerow(
        ["# notes",          "Optional free text", "", "", "", "", ""])
    writer.writerow([])

    for payer in payer_names:
        for cpt in TEMPLATE_CPTS:
            desc = cpt_map.get(cpt, "")
            writer.writerow([
                payer,
                cpt,
                "",                      # allowed_amount — fill in
                "",                      # modifier
                # place_of_service (telehealth default)
                "10",
                date.today().isoformat(),
                desc[:60] if desc else "",
            ])
        writer.writerow([])

    with open(filename, "w", newline="") as f:
        f.write(output.getvalue())

    print(f"\n✓  Template written to: {filename}")
    print(f"   Open in Excel, fill in the 'allowed_amount' column, save, then run:")
    print(f"   python3 backend/load_payer_rates.py \"{filename}\"\n")


def import_rates(csv_path: str):
    """Import a filled CSV into fee_schedule_lines."""
    if not os.path.exists(csv_path):
        print(f"✗  File not found: {csv_path}")
        sys.exit(1)

    print(f"Reading: {csv_path}")

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    imported = 0
    skipped = 0
    errors = []

    with get_db() as cur:
        # Build lookup caches
        cur.execute("SELECT payer_name, payer_id FROM payers")
        payer_map = {r["payer_name"].strip().lower(): r["payer_id"]
                     for r in cur.fetchall()}

        cur.execute("SELECT cpt_code FROM cpt_codes")
        valid_cpts = {r["cpt_code"] for r in cur.fetchall()}

        for i, row in enumerate(rows, start=2):
            # Skip comment and blank rows
            first = (list(row.values())[0] or "").strip()
            if not first or first.startswith("#"):
                skipped += 1
                continue

            # ── Payer ──────────────────────────────────────────
            pname = (row.get("payer_name") or "").strip()
            if not pname:
                skipped += 1
                continue

            payer_id = payer_map.get(pname.lower())
            if not payer_id:
                errors.append(
                    f"Row {i}: unknown payer '{pname}' — run --list-payers to see options")
                skipped += 1
                continue

            # ── CPT code ────────────────────────────────────────
            cpt_code = (row.get("cpt_code") or "").strip()
            if not cpt_code or cpt_code not in valid_cpts:
                if cpt_code:
                    errors.append(
                        f"Row {i}: unknown CPT code '{cpt_code}' — skipped")
                skipped += 1
                continue

            # ── Allowed amount ──────────────────────────────────
            raw = (row.get("allowed_amount") or "").strip().replace(
                "$", "").replace(",", "")
            if not raw:
                skipped += 1
                continue
            try:
                allowed_amount = float(raw)
            except ValueError:
                errors.append(f"Row {i}: invalid amount '{raw}' — skipped")
                skipped += 1
                continue

            # ── Optional fields ─────────────────────────────────
            modifier = (row.get("modifier") or "").strip() or None
            place_of_service = (row.get("place_of_service")
                                or "").strip() or None
            eff_raw = (row.get("effective_date") or "").strip()
            effective_date = eff_raw if eff_raw else None
            notes = (row.get("notes") or "").strip() or None

            # ── Resolve contract ────────────────────────────────
            # Find the NPI2 (group) contract for this payer
            cur.execute(
                """
                SELECT c.contract_id
                FROM contracts c
                JOIN provider_entities pe ON c.provider_entity_id = pe.provider_entity_id
                WHERE c.payer_id       = %s
                  AND pe.entity_type   = 'NPI2'
                  AND c.active         = TRUE
                ORDER BY c.effective_date DESC NULLS LAST
                LIMIT 1
                """,
                (payer_id,),
            )
            contract = cur.fetchone()
            if not contract:
                errors.append(
                    f"Row {i}: no active NPI2 contract found for '{pname}' — skipped")
                skipped += 1
                continue

            contract_id = contract["contract_id"]

            # ── Upsert ──────────────────────────────────────────
            try:
                cur.execute(
                    """
                    INSERT INTO fee_schedule_lines
                        (contract_id, cpt_code, modifier, place_of_service,
                         unit_type, allowed_amount, effective_date, notes)
                    VALUES (%s, %s, %s, %s, 'per_service', %s, %s, %s)
                    ON CONFLICT (contract_id, cpt_code, modifier, place_of_service, effective_date)
                    DO UPDATE SET
                        allowed_amount = EXCLUDED.allowed_amount,
                        notes          = EXCLUDED.notes
                    """,
                    (contract_id, cpt_code, modifier, place_of_service,
                     allowed_amount, effective_date, notes),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: DB error — {e}")
                skipped += 1

    print(f"\n✓  Done — {imported} rate(s) imported, {skipped} skipped.")

    if errors:
        print(f"\nWarnings ({len(errors)}):")
        for e in errors[:20]:
            print(f"  • {e}")

    if imported:
        print("\nRestart uvicorn (or it will auto-reload), then refresh the dashboard.")
        print("The Payer Rate column will now show your real contracted rates.\n")


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--list-payers" in args:
        list_payers()
        sys.exit(0)

    if "--template" in args:
        generate_template()
        sys.exit(0)

    # Default: import a CSV file
    csv_path = args[0]
    import_rates(csv_path)
