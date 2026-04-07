"""
routers/fee_schedules.py
------------------------
Endpoints for importing and viewing fee schedule lines and benchmark rates.
"""

from fastapi import APIRouter, HTTPException
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
