"""
routers/letters.py
------------------
Generates professional rate negotiation letters for each payer,
populated with real data from the negotiation dashboard.

Endpoints:
  GET  /api/letters/preview/{payer_id}   - returns letter as plain text / JSON
  GET  /api/letters/download/{payer_id}  - returns letter as a downloadable .txt file
"""

from datetime import date
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from backend.database import get_db

router = APIRouter(prefix="/api", tags=["Negotiation Letters"])

CLINIC_NAME    = "Solrei Behavioral Health, Inc."
CLINIC_ADDRESS = "9100 Conroy Windermere Rd, Windermere, FL 34786"
CLINIC_NPI2    = "1003521006"
CLINIC_EIN     = "92-1227672"
CLINIC_CONTACT = "Dean Pedersen"
CLINIC_EMAIL   = "dean@solreibehavioralhealth.com"


def build_letter(payer: dict, codes: list, contract: dict) -> str:
    today       = date.today().strftime("%B %d, %Y")
    payer_name  = payer["payer_name"]
    total_gap   = sum(float(c["annual_revenue_gap"] or 0) for c in codes)
    top_codes   = sorted(codes, key=lambda c: float(c["annual_revenue_gap"] or 0), reverse=True)[:10]

    # Build the code-by-code table
    table_lines = []
    table_lines.append(f"  {'CPT':<8} {'Description':<38} {'Current':>10} {'Target':>10} {'Gap/Unit':>10} {'Est. Annual Gap':>16}")
    table_lines.append(f"  {'─'*8} {'─'*38} {'─'*10} {'─'*10} {'─'*10} {'─'*16}")
    for c in top_codes:
        desc  = (c["short_description"] or "")[:37]
        cur   = f"${float(c['payer_allowed'] or 0):>8.2f}"
        tgt   = f"${float(c['target_allowed'] or 0):>8.2f}"
        gap_u = f"${float(c['rate_gap_per_unit'] or 0):>8.2f}"
        gap_a = f"${float(c['annual_revenue_gap'] or 0):>13,.0f}" if c["annual_revenue_gap"] else "        (vol. TBD)"
        table_lines.append(f"  {c['cpt_code']:<8} {desc:<38} {cur:>10} {tgt:>10} {gap_u:>10} {gap_a:>16}")

    table = "\n".join(table_lines)
    total_gap_fmt = f"${total_gap:,.0f}" if total_gap else "(pending volume data)"
    pid   = contract.get("payer_contract_id") or "on file"

    letter = f"""
{today}

Re: Request for Fee Schedule Rate Review and Adjustment
Provider: {CLINIC_NAME}
NPI (Group): {CLINIC_NPI2}  |  EIN: {CLINIC_EIN}  |  Contract/Provider ID: {pid}

To the Provider Relations / Contracting Team at {payer_name}:

My name is {CLINIC_CONTACT}, and I am writing on behalf of {CLINIC_NAME}, a
psychiatric telehealth practice located in Windermere, Florida. We are currently
credentialed with {payer_name} under the above contract and have been proud to
serve your members with high-quality, accessible behavioral health care.

As part of our ongoing commitment to financial sustainability and continued network
participation, we are formally requesting a review and upward adjustment of our
current reimbursement rates for psychiatric services.

──────────────────────────────────────────────────────────────────────────────
WHY WE ARE REQUESTING A RATE ADJUSTMENT
──────────────────────────────────────────────────────────────────────────────

Behavioral health services are experiencing significant cost pressures including
rising overhead, workforce shortages, and increased clinical complexity among
patients. Our current contracted rates under {payer_name} fall below our target
benchmark of 130% of the 2026 Medicare Physician Fee Schedule — a standard
commonly used to ensure financial viability for specialty practices.

A review of our current fee schedule reveals that the majority of our most
frequently billed psychiatric CPT codes are reimbursed at rates materially below
this benchmark, representing an estimated annual revenue gap of approximately
{total_gap_fmt} for our practice.

──────────────────────────────────────────────────────────────────────────────
REQUESTED RATE ADJUSTMENTS
──────────────────────────────────────────────────────────────────────────────

The following table summarizes our highest-priority codes, the current contracted
rate, our requested target rate (130% of 2026 Medicare), and the per-unit gap:

{table}

Our target rates are based on 130% of the 2026 CMS Medicare Physician Fee
Schedule (non-facility, FL locality), which reflects the minimum threshold
necessary to sustain quality psychiatric care delivery.

──────────────────────────────────────────────────────────────────────────────
ABOUT SOLREI BEHAVIORAL HEALTH
──────────────────────────────────────────────────────────────────────────────

{CLINIC_NAME} is a psychiatric telehealth practice serving patients across
Florida. Our team of four board-certified Psychiatric Mental Health Nurse
Practitioners (PMHNPs) provides medication management, psychiatric evaluations,
and integrated supportive therapy to a panel of approximately 300 active patients.

  • All providers: PMHNP-BC certified
  • Service delivery: Telehealth (synchronous, HIPAA-compliant)
  • Specialties: Medication management, psychiatric evaluation, supportive therapy
  • Patient population: Adults with mood disorders, anxiety, ADHD, and other
    psychiatric conditions
  • Network status: Active, credentialed provider

We are committed to remaining an in-network provider for {payer_name} members and
believe that equitable reimbursement is essential to sustaining this commitment.

──────────────────────────────────────────────────────────────────────────────
REQUESTED NEXT STEPS
──────────────────────────────────────────────────────────────────────────────

We respectfully request:

  1. A formal review of our current fee schedule rates for the CPT codes listed
     above, with consideration of adjustment to 130% of the 2026 Medicare PFS.

  2. A meeting or call with your contracting team to discuss this request and
     explore a mutually agreeable rate amendment.

  3. A written response within 30 days outlining {payer_name}'s position and
     any proposed revised rates.

Please direct all correspondence regarding this matter to:

  {CLINIC_CONTACT}
  {CLINIC_NAME}
  {CLINIC_ADDRESS}
  Email: {CLINIC_EMAIL}

We value our relationship with {payer_name} and the patients we serve together.
Thank you for your time and consideration of this request. We look forward to
a productive conversation.

Respectfully,


{CLINIC_CONTACT}
{CLINIC_NAME}
{CLINIC_ADDRESS}
{CLINIC_EMAIL}

Enclosures:
  - Detailed rate comparison table (all CPT codes)
  - 2026 Medicare Physician Fee Schedule reference rates (CMS, FL locality)
"""
    return letter.strip()


@router.get("/letters/preview/{payer_id}")
def preview_letter(payer_id: int):
    """
    Return a structured preview of the negotiation letter for a payer,
    including the letter text and supporting data.
    """
    with get_db() as cur:
        # Get payer
        cur.execute("SELECT * FROM payers WHERE payer_id = %s", (payer_id,))
        payer = cur.fetchone()
        if not payer:
            raise HTTPException(status_code=404, detail=f"Payer {payer_id} not found")

        # Get underpaid codes from dashboard view
        cur.execute(
            """
            SELECT DISTINCT ON (cpt_code)
                cpt_code, short_description, payer_allowed, medicare_allowed,
                pct_of_medicare, target_pct_of_medicare, target_allowed,
                rate_gap_per_unit, annual_volume, annual_revenue_gap
            FROM v_negotiation_dashboard
            WHERE payer_id = %s AND is_underpaid = TRUE
            ORDER BY cpt_code, annual_revenue_gap DESC NULLS LAST
            """,
            (payer_id,),
        )
        codes = cur.fetchall()

        # Get primary contract info
        cur.execute(
            """
            SELECT c.*, pe.legal_name, pe.npi_number
            FROM contracts c
            JOIN provider_entities pe ON c.provider_entity_id = pe.provider_entity_id
            WHERE c.payer_id = %s AND c.active = TRUE AND pe.entity_type = 'NPI2'
            LIMIT 1
            """,
            (payer_id,),
        )
        contract = cur.fetchone() or {}

    if not codes:
        raise HTTPException(
            status_code=404,
            detail=f"No underpaid codes found for payer {payer_id}. "
                   "Import a fee schedule first.",
        )

    letter_text = build_letter(dict(payer), [dict(c) for c in codes], dict(contract))

    return {
        "payer_id":          payer_id,
        "payer_name":        payer["payer_name"],
        "underpaid_codes":   len(codes),
        "total_gap_estimate": sum(float(c["annual_revenue_gap"] or 0) for c in codes),
        "letter":            letter_text,
    }


@router.get("/letters/download/{payer_id}", response_class=PlainTextResponse)
def download_letter(payer_id: int):
    """
    Download the negotiation letter as a plain text file.
    """
    result   = preview_letter(payer_id)
    filename = f"Negotiation_Letter_{result['payer_name'].replace(' ', '_')}_{date.today()}.txt"
    return PlainTextResponse(
        content=result["letter"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
