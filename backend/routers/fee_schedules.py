"""
routers/fee_schedules.py
------------------------
Endpoints for importing and viewing fee schedule lines and benchmark rates.

Direct Rate Import (SBH / Clinic Submit):
  POST /api/direct-rates/import
  CSV columns: payer_name, cpt_code, state, allowed_amount, effective_date
  Auto-creates payers and contracts as needed, linked to Jodene Jensen NPI1.
"""

import csv
import io
from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from backend.database import get_db
from ..models import (
    FeeScheduleImportRequest,
    FeeScheduleImportResponse,
    BenchmarkImportRequest,
    BenchmarkImportResponse,
    ClaimsVolumeIn,
    ClaimsVolume,
)

router = APIRouter(prefix="/api", tags=["Fee Schedules"])


# ── Direct Rate Import (SBH / Clinic Submit) ─────────────────

DIRECT_BILLING_PROVIDER = "Jodene Jensen, PMHNP-BC"   # NPI1 entity name in DB


@router.post("/direct-rates/import")
async def import_direct_rates(
    file: UploadFile = File(...),
    provider_name: str = Query(
        default=DIRECT_BILLING_PROVIDER,
        description="Legal name of the provider entity doing direct billing",
    ),
):
    """
    Import clinic-submit (SBH) direct billing rates from a CSV file.

    CSV columns: payer_name, cpt_code, state, allowed_amount, effective_date

    - payer_name: e.g. 'Aetna', 'Optum/UHC/Oscar', 'Cigna'
    - cpt_code:   e.g. '99214'
    - state:      two-letter state code e.g. 'FL'
    - allowed_amount: contracted rate e.g. '94.76'
    - effective_date: YYYY-MM-DD (optional, defaults to today)

    Auto-creates payers and contracts if they don't exist.
    Uses INSERT ON CONFLICT DO UPDATE — safe to re-upload.
    Rates are linked to the specified provider entity (Jodene Jensen by default).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = [r for r in reader if not (list(r.values())[0] or "").strip().startswith("#")]

    imported = 0
    skipped  = 0
    errors   = []

    with get_db() as cur:
        # Look up the provider entity
        cur.execute(
            "SELECT provider_entity_id FROM provider_entities WHERE legal_name = %s AND active = TRUE",
            (provider_name,),
        )
        pe = cur.fetchone()
        if not pe:
            return {"status": "error", "imported": 0, "skipped": 0,
                    "errors": [f"Provider entity '{provider_name}' not found in database."]}
        provider_entity_id = pe["provider_entity_id"]

        # Pre-load valid CPT codes
        cur.execute("SELECT cpt_code FROM cpt_codes")
        valid_cpts = {r["cpt_code"] for r in cur.fetchall()}

        for i, row in enumerate(rows, start=2):
            payer_name_raw  = (row.get("payer_name") or "").strip()
            cpt_code        = (row.get("cpt_code")   or "").strip()
            state           = (row.get("state")       or "").strip().upper() or None
            amount_raw      = (row.get("allowed_amount") or "").strip().replace("$", "").replace(",", "")
            eff_raw         = (row.get("effective_date") or "").strip()

            if not payer_name_raw or not cpt_code or not amount_raw:
                skipped += 1
                continue

            try:
                allowed_amount = float(amount_raw)
            except ValueError:
                errors.append(f"Row {i}: invalid amount '{amount_raw}'")
                skipped += 1
                continue

            effective_date = eff_raw if eff_raw else date.today().isoformat()

            # Auto-add unknown CPT codes
            if cpt_code not in valid_cpts:
                cur.execute(
                    "INSERT INTO cpt_codes (cpt_code, short_description, category) "
                    "VALUES (%s, %s, 'E/M') ON CONFLICT DO NOTHING",
                    (cpt_code, cpt_code),
                )
                valid_cpts.add(cpt_code)

            # Ensure payer exists (case-insensitive lookup, then create)
            cur.execute(
                "SELECT payer_id FROM payers WHERE lower(payer_name) = lower(%s)",
                (payer_name_raw,),
            )
            payer_row = cur.fetchone()
            if payer_row:
                payer_id = payer_row["payer_id"]
            else:
                cur.execute(
                    "INSERT INTO payers (payer_name) VALUES (%s) "
                    "ON CONFLICT DO NOTHING RETURNING payer_id",
                    (payer_name_raw,),
                )
                ins = cur.fetchone()
                if not ins:
                    cur.execute("SELECT payer_id FROM payers WHERE lower(payer_name) = lower(%s)",
                                (payer_name_raw,))
                    ins = cur.fetchone()
                payer_id = ins["payer_id"]

            # Ensure a direct-billing contract exists for (payer, provider_entity)
            cur.execute(
                """
                SELECT contract_id FROM contracts
                WHERE payer_id = %s AND provider_entity_id = %s AND active = TRUE
                LIMIT 1
                """,
                (payer_id, provider_entity_id),
            )
            contract_row = cur.fetchone()
            if contract_row:
                contract_id = contract_row["contract_id"]
            else:
                cur.execute(
                    """
                    INSERT INTO contracts
                        (payer_id, provider_entity_id, product_line, effective_date, active, notes)
                    VALUES (%s, %s, 'Commercial', %s, TRUE, 'Auto-created from SBH direct rate import')
                    RETURNING contract_id
                    """,
                    (payer_id, provider_entity_id, effective_date),
                )
                contract_id = cur.fetchone()["contract_id"]

            # Upsert the fee schedule line
            try:
                cur.execute(
                    """
                    INSERT INTO fee_schedule_lines
                        (contract_id, cpt_code, modifier, place_of_service,
                         unit_type, allowed_amount, state, effective_date)
                    VALUES (%s, %s, NULL, NULL, 'per_service', %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT fee_schedule_lines_unique
                    DO UPDATE SET
                        allowed_amount = EXCLUDED.allowed_amount,
                        state          = EXCLUDED.state,
                        effective_date = EXCLUDED.effective_date
                    """,
                    (contract_id, cpt_code, allowed_amount, state, effective_date),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i} ({payer_name_raw}/{cpt_code}/{state}): {e}")
                skipped += 1

    return {
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors[:20],
        "message":  f"Imported {imported} direct rate(s) for {provider_name}. {skipped} skipped.",
    }


@router.get("/direct-rates")
def get_direct_rates(state: str = Query(default="FL")):
    """Return all direct/clinic-submit rates for a given state."""
    state_upper = (state or "FL").upper()
    with get_db() as cur:
        cur.execute(
            """
            SELECT
                p.payer_name,
                fsl.cpt_code,
                cc.short_description,
                fsl.state,
                fsl.allowed_amount,
                fsl.effective_date,
                pe.legal_name AS provider
            FROM fee_schedule_lines fsl
            JOIN contracts         c   ON fsl.contract_id      = c.contract_id
            JOIN payers            p   ON c.payer_id           = p.payer_id
            JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
            JOIN cpt_codes         cc  ON cc.cpt_code          = fsl.cpt_code
            WHERE c.active = TRUE
              AND (c.end_date   IS NULL OR c.end_date   >= CURRENT_DATE)
              AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
              AND (fsl.state IS NULL OR fsl.state = %s)
            ORDER BY p.payer_name, fsl.cpt_code
            """,
            (state_upper,),
        )
        return cur.fetchall()




# ── Fee Schedule Import ───────────────────────────────────────

@router.post("/import-fee-schedule", response_model=FeeScheduleImportResponse)
def import_fee_schedule(payload: FeeScheduleImportRequest):
    """
    Import (upsert) a batch of fee schedule lines for a contract.
    Existing rows for the same contract + CPT code + modifier + effective_date
    are updated; new rows are inserted.

    Example request body:
    {
        "contract_id": 1,
        "lines": [
            {"cpt_code": "99214", "modifier": "95", "place_of_service": "10",
             "unit_type": "per_service", "allowed_amount": 135.00,
             "effective_date": "2026-01-01"}
        ]
    }
    """
    # Verify the contract exists
    with get_db() as cur:
        cur.execute(
            "SELECT contract_id FROM contracts WHERE contract_id = %s", (payload.contract_id,))
        if not cur.fetchone():
            raise HTTPException(
                status_code=404, detail=f"Contract {payload.contract_id} not found")

    upserted = 0
    with get_db() as cur:
        for line in payload.lines:
            cur.execute(
                """
                INSERT INTO fee_schedule_lines
                    (contract_id, cpt_code, modifier, place_of_service,
                     unit_type, allowed_amount, effective_date, end_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (contract_id, cpt_code, modifier, place_of_service, effective_date)
                DO UPDATE SET
                    allowed_amount   = EXCLUDED.allowed_amount,
                    unit_type        = EXCLUDED.unit_type,
                    end_date         = EXCLUDED.end_date,
                    notes            = EXCLUDED.notes
                """,
                (
                    payload.contract_id,
                    line.cpt_code,
                    line.modifier,
                    line.place_of_service,
                    line.unit_type,
                    line.allowed_amount,
                    line.effective_date,
                    line.end_date,
                    line.notes,
                ),
            )
            upserted += 1

    return FeeScheduleImportResponse(
        contract_id=payload.contract_id,
        lines_upserted=upserted,
        message=f"Successfully imported {upserted} fee schedule line(s) for contract {payload.contract_id}.",
    )


@router.get("/fee-schedule/{contract_id}")
def get_fee_schedule(contract_id: int):
    """Return all current fee schedule lines for a contract."""
    with get_db() as cur:
        cur.execute(
            """
            SELECT f.*, cc.short_description, cc.category
            FROM fee_schedule_lines f
            JOIN cpt_codes cc ON f.cpt_code = cc.cpt_code
            WHERE f.contract_id = %s
              AND (f.end_date IS NULL OR f.end_date >= CURRENT_DATE)
            ORDER BY cc.category, f.cpt_code
            """,
            (contract_id,),
        )
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No active fee schedule lines found for contract {contract_id}.",
        )
    return rows


# ── Benchmark Rates ───────────────────────────────────────────

@router.post("/import-benchmark", response_model=BenchmarkImportResponse)
def import_benchmark(payload: BenchmarkImportRequest):
    """
    Import (upsert) Medicare or other benchmark rates.
    Use source_name like 'Medicare 2026', locality like 'FL'.

    Example request body:
    {
        "source_name": "Medicare 2026",
        "locality": "FL",
        "effective_year": 2026,
        "rates": [
            {"cpt_code": "99214", "allowed_amount": 110.00},
            {"cpt_code": "90833", "allowed_amount": 62.00}
        ]
    }
    """
    upserted = 0
    with get_db() as cur:
        for rate in payload.rates:
            cur.execute(
                """
                INSERT INTO benchmark_fee_schedule
                    (source_name, locality, cpt_code, allowed_amount, effective_year, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_name, locality, cpt_code, effective_year)
                DO UPDATE SET
                    allowed_amount = EXCLUDED.allowed_amount,
                    notes          = EXCLUDED.notes
                """,
                (
                    payload.source_name,
                    payload.locality,
                    rate.cpt_code,
                    rate.allowed_amount,
                    payload.effective_year,
                    rate.notes,
                ),
            )
            upserted += 1

    return BenchmarkImportResponse(
        source_name=payload.source_name,
        lines_upserted=upserted,
        message=f"Successfully imported {upserted} benchmark rate(s) for {payload.source_name} ({payload.locality}).",
    )


@router.get("/benchmark")
def get_benchmark(source_name: str = "Medicare 2026", locality: str = "FL", year: int = 2026):
    """Return benchmark rates for a given source, locality, and year."""
    with get_db() as cur:
        cur.execute(
            """
            SELECT b.*, cc.short_description, cc.category
            FROM benchmark_fee_schedule b
            JOIN cpt_codes cc ON b.cpt_code = cc.cpt_code
            WHERE b.source_name    = %s
              AND b.locality       = %s
              AND b.effective_year = %s
            ORDER BY cc.category, b.cpt_code
            """,
            (source_name, locality, year),
        )
        return cur.fetchall()


# ── Claims Volume ─────────────────────────────────────────────

@router.post("/claims-volume", response_model=ClaimsVolume)
def upsert_claims_volume(payload: ClaimsVolumeIn):
    """
    Insert or update annual claims volume for a contract + CPT code + year.
    This unlocks revenue gap calculations in the dashboard.

    Example request body:
    {
        "contract_id": 1,
        "cpt_code": "99214",
        "modifier": "95",
        "calendar_year": 2025,
        "annual_volume": 420
    }
    """
    with get_db() as cur:
        cur.execute(
            "SELECT contract_id FROM contracts WHERE contract_id = %s", (payload.contract_id,))
        if not cur.fetchone():
            raise HTTPException(
                status_code=404, detail=f"Contract {payload.contract_id} not found")

        cur.execute(
            """
            INSERT INTO annual_claims_volume
                (contract_id, cpt_code, modifier, calendar_year, annual_volume, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (contract_id, cpt_code, modifier, calendar_year)
            DO UPDATE SET
                annual_volume = EXCLUDED.annual_volume,
                notes         = EXCLUDED.notes,
                updated_at    = NOW()
            RETURNING *
            """,
            (
                payload.contract_id,
                payload.cpt_code,
                payload.modifier,
                payload.calendar_year,
                payload.annual_volume,
                payload.notes,
            ),
        )
        return cur.fetchone()
