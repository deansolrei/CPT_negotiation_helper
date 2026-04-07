"""
routers/payers.py
-----------------
Endpoints for payers, provider entities, and CPT codes.
These are mostly read-only reference data.
"""

from fastapi import APIRouter, HTTPException
from backend.database import get_db
from ..models import Payer, ProviderEntity, CptCode

router = APIRouter(prefix="/api", tags=["Reference Data"])


# ── Payers ────────────────────────────────────────────────────

@router.get("/payers", response_model=list[Payer])
def list_payers():
    """Return all payers."""
    with get_db() as cur:
        cur.execute("SELECT * FROM payers ORDER BY payer_name")
        return cur.fetchall()


@router.get("/payers/{payer_id}", response_model=Payer)
def get_payer(payer_id: int):
    """Return a single payer by ID."""
    with get_db() as cur:
        cur.execute("SELECT * FROM payers WHERE payer_id = %s", (payer_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail=f"Payer {payer_id} not found")
    return row


# ── Provider Entities ─────────────────────────────────────────

@router.get("/providers", response_model=list[ProviderEntity])
def list_providers():
    """Return all provider entities (group NPI2 + individual NPI1s)."""
    with get_db() as cur:
        cur.execute(
            "SELECT * FROM provider_entities WHERE active = TRUE ORDER BY entity_type, legal_name"
        )
        return cur.fetchall()


@router.get("/providers/{provider_entity_id}", response_model=ProviderEntity)
def get_provider(provider_entity_id: int):
    """Return a single provider entity by ID."""
    with get_db() as cur:
        cur.execute(
            "SELECT * FROM provider_entities WHERE provider_entity_id = %s",
            (provider_entity_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail=f"Provider {provider_entity_id} not found")
    return row


# ── CPT Codes ─────────────────────────────────────────────────

@router.get("/cpt-codes", response_model=list[CptCode])
def list_cpt_codes(category: str = None, telehealth_only: bool = False):
    """
    Return all CPT codes.
    Optional filters:
      - category: filter by category name (e.g. "E/M", "Psychotherapy")
      - telehealth_only: if true, return only telehealth-eligible codes
    """
    filters = []
    params = []

    if category:
        filters.append("category = %s")
        params.append(category)
    if telehealth_only:
        filters.append("telehealth_eligible = TRUE")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as cur:
        cur.execute(
            f"SELECT * FROM cpt_codes {where} ORDER BY category, cpt_code",
            params,
        )
        return cur.fetchall()


@router.get("/cpt-codes/{cpt_code}", response_model=CptCode)
def get_cpt_code(cpt_code: str):
    """Return a single CPT code."""
    with get_db() as cur:
        cur.execute("SELECT * FROM cpt_codes WHERE cpt_code = %s", (cpt_code,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail=f"CPT code {cpt_code} not found")
    return row
