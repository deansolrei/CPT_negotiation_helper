#!/usr/bin/env python3
"""
import_billing_actuals.py
--------------------------
Imports aggregated billing actuals CSV into the billing_actuals table.

Usage (run from cpt_dashboard directory on Mac Mini):
    python3 sql/import_billing_actuals.py data/billing_actuals_2026.csv

CSV columns:
    intermediary, insurance_plan, state, primary_cpt, addon_cpt,
    avg_payment, session_count, min_payment, max_payment, effective_year
"""

import csv
import sys
import os

# Allow running from cpt_dashboard root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_db


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sql/import_billing_actuals.py <csv_file>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    imported = 0
    skipped  = 0
    errors   = []

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with get_db() as cur:
        for i, row in enumerate(rows, start=2):
            try:
                intermediary   = row['intermediary'].strip()
                insurance_plan = row['insurance_plan'].strip()
                state          = row['state'].strip()
                primary_cpt    = row['primary_cpt'].strip()
                addon_cpt      = row['addon_cpt'].strip() or None
                avg_payment    = float(row['avg_payment'])
                session_count  = int(row['session_count'])
                min_payment    = float(row['min_payment']) if row['min_payment'] else None
                max_payment    = float(row['max_payment']) if row['max_payment'] else None
                effective_year = int(row['effective_year'])

                cur.execute(
                    """
                    INSERT INTO billing_actuals
                        (intermediary, insurance_plan, state, primary_cpt, addon_cpt,
                         avg_payment, session_count, min_payment, max_payment,
                         effective_year, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT ON CONSTRAINT billing_actuals_unique
                    DO UPDATE SET
                        avg_payment    = EXCLUDED.avg_payment,
                        session_count  = EXCLUDED.session_count,
                        min_payment    = EXCLUDED.min_payment,
                        max_payment    = EXCLUDED.max_payment,
                        effective_year = EXCLUDED.effective_year,
                        updated_at     = NOW()
                    """,
                    (intermediary, insurance_plan, state, primary_cpt, addon_cpt,
                     avg_payment, session_count, min_payment, max_payment, effective_year)
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")
                skipped += 1

    print(f"Import complete: {imported} imported, {skipped} skipped")
    if errors:
        print("Errors:")
        for err in errors[:20]:
            print(f"  {err}")


if __name__ == '__main__':
    main()
