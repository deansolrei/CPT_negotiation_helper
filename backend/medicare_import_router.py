"""
routers/medicare_import.py
--------------------------
Endpoint to import Medicare benchmark rates from the SLAVE sheet medicare_rates CSV.

CSV format (from populate_slave_v10.gs syncMedicareRates()):
  state, locality, cpt_code, allowed_amount

locality values:
  state code (e.g. 'FL') = statewide rate
  'FL-FTL'               = Fort Lauderdale locality
  'FL-MIA'               = Miami locality

Register in main.py:
  from backend.routers import medicare_import
  app.include_router(medicare_import.router)
"""

import csv
import io
from fastapi import APIRouter, UploadFile, File
from ..database import get_db

router = APIRouter(prefix="/api", tags=["Medicare Rates"])


@router.post("/medicare/import")
async def import_medicare_rates(file: UploadFile = File(...)):
    """
    Upload the medicare_rates CSV from the SLAVE Google Sheet.
    Clears existing Medicare 2026 rates and replaces with new data.

    Steps:
      1. Run syncMedicareRates() in the SLAVE sheet Apps Script
      2. Download the medicare_rates tab as CSV
      3. Upload here
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    imported = 0
    skipped  = 0
    errors   = []

    with get_db() as cur:
        # Clear existing 2026 rates
        cur.execute(
            "DELETE FROM benchmark_fee_schedule "
            "WHERE source_name = 'Medicare 2026' AND effective_year = 2026"
        )

        reader = csv.DictReader(io.StringIO(text))

        for i, row in enumerate(reader, start=2):
            state    = (row.get("state")          or "").strip().upper()
            locality = (row.get("locality")        or "").strip().upper()
            cpt_code = (row.get("cpt_code")        or "").strip()
            amt_raw  = (row.get("allowed_amount")  or "").strip().replace("$","").replace(",","")

            if not state or not cpt_code or not amt_raw:
                skipped += 1
                continue

            try:
                allowed_amount = float(amt_raw)
            except ValueError:
                errors.append(f"Row {i}: invalid amount '{amt_raw}'")
                skipped += 1
                continue

            # Use locality if provided, otherwise state code
            loc = locality if locality else state

            try:
                cur.execute(
                    """
                    INSERT INTO benchmark_fee_schedule
                        (source_name, effective_year, locality, cpt_code, allowed_amount)
                    VALUES ('Medicare 2026', 2026, %s, %s, %s)
                    ON CONFLICT (source_name, effective_year, locality, cpt_code)
                    DO UPDATE SET
                        allowed_amount = EXCLUDED.allowed_amount,
                        updated_at     = NOW()
                    """,
                    (loc, cpt_code, allowed_amount),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")
                skipped += 1

    return {
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors[:10],
        "message":  f"Imported {imported} Medicare rate(s). {skipped} skipped.",
    }


@router.get("/medicare/rates")
def get_medicare_rates(state: str = "FL", locality: str = None):
    """Return Medicare 2026 rates for a state."""
    loc = (locality or state).upper()
    with get_db() as cur:
        cur.execute(
            """
            SELECT locality, cpt_code, allowed_amount
            FROM   benchmark_fee_schedule
            WHERE  source_name   = 'Medicare 2026'
              AND  effective_year = 2026
              AND  locality       = %s
            ORDER BY cpt_code
            """,
            (loc,),
        )
        return cur.fetchall()
