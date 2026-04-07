"""
routers/contracts.py
--------------------
Endpoints for contracts between payers and provider entities.
"""

from fastapi import APIRouter, HTTPException
from ..database import get_db
from ..models import Contract

router = APIRouter(prefix="/api", tags=["Contracts"])

CONTRACT_QUERY = """
    SELECT
        c.contract_id,
        c.payer_id,
        p.payer_name,
        c.provider_entity_id,
        pe.legal_name      AS provider_name,
        pe.npi_number,
        pe.entity_type,
        c.payer_contract_id,
        c.product_line,
        c.line_of_business,
        c.effective_date,
        c.end_date,
        c.active,
        c.notes
    FROM contracts c
    JOIN payers p             ON c.payer_id           = p.payer_id
    JOIN provider_entities pe ON c.provider_entity_id = pe.provider_entity_id
"""


@router.get("/contracts", response_model=list[Contract])
def list_contracts(payer_id: int = None, active_only: bool = True):
    """
    Return all contracts with payer and provider details.
    Optional filters:
      - payer_id: filter to a specific payer
      - active_only: if true (default), return only active contracts
    """
    filters = []
    params = []

    if active_only:
        filters.append("c.active = TRUE")
    if payer_id:
        filters.append("c.payer_id = %s")
        params.append(payer_id)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as cur:
        cur.execute(
            f"{CONTRACT_QUERY} {where} ORDER BY p.payer_name, pe.entity_type",
            params,
        )
        return cur.fetchall()


@router.get("/contracts/{contract_id}", response_model=Contract)
def get_contract(contract_id: int):
    """Return a single contract by ID."""
    with get_db() as cur:
        cur.execute(
            f"{CONTRACT_QUERY} WHERE c.contract_id = %s",
            (contract_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail=f"Contract {contract_id} not found")
    return row
