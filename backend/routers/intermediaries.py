"""
routers/intermediaries.py
--------------------------
Manages billing intermediary platforms (Headway, Alma, Grow Therapy)
and their negotiated rates per CPT code.

Endpoints:
  GET  /api/intermediaries                    - list all platforms
  GET  /api/intermediaries/template           - download blank CSV rate template
  POST /api/intermediaries/import             - upload filled CSV to import/update rates
  GET  /api/channel-comparison                - full direct vs intermediary comparison
  GET  /api/channel-comparison/summary        - best channel summary by payer

CSV Template format:
  intermediary_name, payer_name, cpt_code, state, allowed_amount, effective_date, notes

  - intermediary_name: must match an existing intermediary (e.g. "Headway")
  - payer_name: leave blank for platform-wide rate (applies to all payers)
  - state: leave blank for national rate; default is "FL"
  - allowed_amount: provider take-home in dollars (e.g. 145.00)
  - effective_date: YYYY-MM-DD or leave blank
  - notes: optional free text
"""

import csv
import io
from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from backend.database import get_db

router = APIRouter(prefix="/api", tags=["Intermediaries"])


# ── List all platforms ────────────────────────────────────────

@router.get("/intermediaries")
def list_intermediaries():
    """Return all intermediary platforms with their rate counts."""
    with get_db() as cur:
        cur.execute(
            """
            SELECT
                i.intermediary_id,
                i.name,
                i.display_name,
                i.website,
                i.fee_description,
                i.notes,
                i.active,
                COUNT(ir.rate_id) AS rate_count
            FROM intermediaries i
            LEFT JOIN intermediary_rates ir ON i.intermediary_id = ir.intermediary_id
            GROUP BY i.intermediary_id, i.name, i.display_name, i.website,
                     i.fee_description, i.notes, i.active
            ORDER BY i.name
            """
        )
        return cur.fetchall()


# ── CSV template download ─────────────────────────────────────

@router.get("/intermediaries/template")
def download_template():
    """
    Download a blank CSV template for entering intermediary rates.
    Fill in the template and upload via POST /api/intermediaries/import.
    """
    with get_db() as cur:
        # Get all active CPT codes for reference rows
        cur.execute(
            "SELECT cpt_code, short_description FROM cpt_codes ORDER BY cpt_code"
        )
        cpt_rows = cur.fetchall()

        # Get intermediary names
        cur.execute("SELECT name FROM intermediaries WHERE active = TRUE ORDER BY name")
        intermediaries = [r["name"] for r in cur.fetchall()]

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "intermediary_name",
        "payer_name",
        "cpt_code",
        "state",
        "allowed_amount",
        "effective_date",
        "notes",
    ])

    # Instructions rows (commented out in CSV with # prefix — just use empty rows)
    writer.writerow(["# INSTRUCTIONS:", "", "", "", "", "", ""])
    writer.writerow(["# intermediary_name", "Required. One of: " + ", ".join(intermediaries), "", "", "", "", ""])
    writer.writerow(["# payer_name", "Optional. Leave blank for platform-wide rate", "", "", "", "", ""])
    writer.writerow(["# state", "Optional. Default FL. Leave blank for national", "", "", "", "", ""])
    writer.writerow(["# allowed_amount", "Required. Provider take-home $ (e.g. 145.00)", "", "", "", "", ""])
    writer.writerow(["# effective_date", "Optional. YYYY-MM-DD", "", "", "", "", ""])
    writer.writerow(["# notes", "Optional free text", "", "", "", "", ""])
    writer.writerow([])

    # Example rows for each intermediary + a few key CPT codes
    key_cpts = ["99213", "99214", "99215", "90792", "99205", "99244"]
    example_cpts = [r for r in cpt_rows if r["cpt_code"] in key_cpts]

    for intermediary in intermediaries:
        for row in example_cpts:
            writer.writerow([
                intermediary,
                "",                      # payer_name (blank = all payers)
                row["cpt_code"],
                "FL",
                "",                      # allowed_amount — fill in
                date.today().isoformat(),
                row["short_description"][:50] if row["short_description"] else "",
            ])
        writer.writerow([])  # blank line between intermediaries

    output.seek(0)
    filename = f"intermediary_rates_template_{date.today()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── CSV import ────────────────────────────────────────────────

@router.post("/intermediaries/import")
async def import_rates(file: UploadFile = File(...)):
    """
    Upload a filled CSV file to import or update intermediary rates.

    Expected columns (in any order):
      intermediary_name, payer_name, cpt_code, state, allowed_amount,
      effective_date, notes

    - Rows starting with '#' are skipped (instruction/comment rows).
    - Blank allowed_amount rows are skipped.
    - Uses INSERT ... ON CONFLICT DO UPDATE so it's safe to re-upload.

    Returns a summary of rows imported, updated, and any errors.
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle Excel BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped  = 0
    errors   = []

    with get_db() as cur:
        # Build lookup caches
        cur.execute("SELECT name, intermediary_id FROM intermediaries")
        intermediary_map = {r["name"].strip().lower(): r["intermediary_id"]
                            for r in cur.fetchall()}

        cur.execute("SELECT payer_name, payer_id FROM payers")
        payer_map = {r["payer_name"].strip().lower(): r["payer_id"]
                     for r in cur.fetchall()}

        cur.execute("SELECT cpt_code FROM cpt_codes")
        valid_cpts = {r["cpt_code"] for r in cur.fetchall()}

        for i, row in enumerate(reader, start=2):  # row 2 = first data row
            # Skip comment rows
            first_val = (list(row.values())[0] or "").strip()
            if first_val.startswith("#"):
                skipped += 1
                continue

            # Resolve intermediary
            iname = (row.get("intermediary_name") or "").strip()
            if not iname:
                skipped += 1
                continue
            intermediary_id = intermediary_map.get(iname.lower())
            if not intermediary_id:
                errors.append(f"Row {i}: unknown intermediary '{iname}' — skipped")
                skipped += 1
                continue

            # Resolve payer (optional)
            pname = (row.get("payer_name") or "").strip()
            payer_id = None
            if pname:
                payer_id = payer_map.get(pname.lower())
                if not payer_id:
                    errors.append(f"Row {i}: unknown payer '{pname}' — skipped")
                    skipped += 1
                    continue

            # CPT code
            cpt_code = (row.get("cpt_code") or "").strip()
            if not cpt_code or cpt_code not in valid_cpts:
                if cpt_code:
                    errors.append(f"Row {i}: unknown CPT code '{cpt_code}' — skipped")
                skipped += 1
                continue

            # Allowed amount
            amount_raw = (row.get("allowed_amount") or "").strip().replace("$", "").replace(",", "")
            if not amount_raw:
                skipped += 1
                continue
            try:
                allowed_amount = float(amount_raw)
            except ValueError:
                errors.append(f"Row {i}: invalid allowed_amount '{amount_raw}' — skipped")
                skipped += 1
                continue

            # State
            state = (row.get("state") or "FL").strip() or "FL"

            # Effective date
            eff_raw = (row.get("effective_date") or "").strip()
            effective_date = eff_raw if eff_raw else None

            # Notes
            notes = (row.get("notes") or "").strip() or None

            # Upsert
            try:
                cur.execute(
                    """
                    INSERT INTO intermediary_rates
                        (intermediary_id, payer_id, cpt_code, state,
                         allowed_amount, effective_date, notes, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (intermediary_id, payer_id, cpt_code, state, effective_date)
                    DO UPDATE SET
                        allowed_amount = EXCLUDED.allowed_amount,
                        notes          = EXCLUDED.notes,
                        updated_at     = NOW()
                    """,
                    (intermediary_id, payer_id, cpt_code, state,
                     allowed_amount, effective_date, notes),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: DB error — {str(e)}")
                skipped += 1

    return {
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors[:20],  # cap at 20 errors shown
        "message":  f"Successfully imported {imported} rate(s). {skipped} row(s) skipped.",
    }


# ── Channel Comparison ────────────────────────────────────────

@router.get("/channel-comparison")
def get_channel_comparison(
    payer_id:  int = None,
    cpt_code:  str = None,
    best_only: bool = False,
):
    """
    Return side-by-side comparison of direct billing vs each intermediary.

    Optional filters:
      - payer_id: filter to a specific payer
      - cpt_code: filter to a specific CPT code
      - best_only: if true, only return rows where best_channel_type = 'Intermediary'
                   (i.e. an intermediary pays more than direct)
    """
    filters = []
    params  = []

    if payer_id:
        filters.append("payer_id = %s")
        params.append(payer_id)
    if cpt_code:
        filters.append("cpt_code = %s")
        params.append(cpt_code)
    if best_only:
        filters.append("best_channel_type = 'Intermediary'")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as cur:
        cur.execute(f"SELECT * FROM v_channel_comparison {where}", params)
        return cur.fetchall()


@router.get("/channel-comparison/summary")
def get_channel_comparison_summary():
    """
    Summary by payer: count of codes where direct is best vs intermediary is best.
    Useful for a quick 'which payers should we move to Headway/Alma/Grow?' view.
    """
    with get_db() as cur:
        cur.execute(
            """
            SELECT
                payer_id,
                payer_name,
                COUNT(*) FILTER (WHERE best_channel_type = 'Direct')       AS direct_best_count,
                COUNT(*) FILTER (WHERE best_channel_type = 'Intermediary') AS intermediary_best_count,
                COUNT(*)                                                    AS total_codes,
                ROUND(AVG(direct_rate)::numeric, 2)                        AS avg_direct_rate,
                ROUND(AVG(GREATEST(
                    COALESCE(headway_rate, 0),
                    COALESCE(alma_rate, 0),
                    COALESCE(grow_rate, 0)
                ))::numeric, 2)                                             AS avg_best_intermediary_rate
            FROM v_channel_comparison
            WHERE payer_id IS NOT NULL
            GROUP BY payer_id, payer_name
            ORDER BY intermediary_best_count DESC, payer_name
            """
        )
        return cur.fetchall()


# ── CSV export of channel comparison ─────────────────────────

@router.get("/channel-comparison/export")
def export_channel_comparison(payer_id: int = None):
    """Export the full channel comparison as a CSV file."""
    where  = "WHERE payer_id = %s" if payer_id else ""
    params = [payer_id] if payer_id else []

    with get_db() as cur:
        cur.execute(f"SELECT * FROM v_channel_comparison {where}", params)
        rows = cur.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No channel comparison data found.")

    columns = [
        "payer_id", "payer_name", "cpt_code", "short_description", "category",
        "modifier", "medicare_allowed", "direct_pct_of_medicare",
        "direct_rate", "headway_rate", "alma_rate", "grow_rate", "best_channel_type",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in columns})

    output.seek(0)
    filename = f"channel_comparison_export_{date.today()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
