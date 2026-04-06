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


# ── CSV import (auto-detect format) ──────────────────────────

def _detect_wide_format(header: list[str]) -> bool:
    """Return True if the CSV is in wide/pivoted format (payers as columns)."""
    # Wide format: first col is CPT Code or similar, has 3+ columns, no 'intermediary_name' col
    if len(header) < 3:
        return False
    has_intermediary_col = any("intermediary" in h.lower() for h in header)
    looks_like_cpt_col   = "cpt" in header[0].lower() or "code" in header[0].lower()
    return looks_like_cpt_col and not has_intermediary_col


def _import_wide_format(
    reader, header: list[str], intermediary_map: dict, payer_name_map: dict,
    valid_cpts: set, cur
) -> tuple[int, int, list[str]]:
    """
    Parse a wide-format CSV (payers as columns) like the Headway rate sheet.

    Header: CPT Code | Description | Payer1 | Payer2 | ...
    Rows:   code     | description | rate   | rate   | ...

    The intermediary must be identified by the caller (passed via `intermediary_name` param).
    In this mode we use the first intermediary as default, or the one specified in the request.
    """
    payer_names = [h.strip() for h in header[2:]]
    imported = 0
    skipped  = 0
    errors   = []

    for i, row in enumerate(reader, start=2):
        if not row or not row[0].strip():
            skipped += 1
            continue

        # Skip comment / instruction rows
        if row[0].strip().startswith("#"):
            skipped += 1
            continue

        cpt_code = row[0].strip()

        # Auto-insert unknown CPT codes from the wide sheet
        if cpt_code not in valid_cpts:
            desc = row[1].strip() if len(row) > 1 else cpt_code
            try:
                category = "Telehealth E/M" if cpt_code.startswith("980") else "E/M"
                cur.execute(
                    """
                    INSERT INTO cpt_codes (cpt_code, short_description, full_description, category)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (cpt_code) DO NOTHING
                    """,
                    (cpt_code, desc[:100], desc, category),
                )
                valid_cpts.add(cpt_code)
            except Exception as e:
                errors.append(f"Row {i}: could not add CPT {cpt_code} — {e}")
                skipped += 1
                continue

        for col_idx, payer_name in enumerate(payer_names, start=2):
            raw = row[col_idx].strip() if col_idx < len(row) else ""
            if not raw:
                continue
            amount_str = raw.replace("$", "").replace(",", "").strip()
            if not amount_str:
                continue
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            if amount <= 0:
                continue

            # Determine intermediary_id — use the intermediary_name from payer_name_map
            # In wide format, there's no intermediary column; use context from caller
            intermediary_id = list(intermediary_map.values())[0] if intermediary_map else None
            if not intermediary_id:
                errors.append(f"Row {i}: no intermediary found — skipped")
                skipped += 1
                break

            # Ensure payer is in intermediary_payer_map
            try:
                cur.execute(
                    """
                    INSERT INTO intermediary_payer_map (intermediary_payer_name)
                    VALUES (%s) ON CONFLICT DO NOTHING
                    """,
                    (payer_name,),
                )
            except Exception:
                pass

            try:
                cur.execute(
                    """
                    INSERT INTO intermediary_rates
                        (intermediary_id, payer_name, cpt_code, state,
                         allowed_amount, effective_date, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NULL, NOW())
                    ON CONFLICT ON CONSTRAINT intermediary_rates_unique
                    DO UPDATE SET
                        allowed_amount = EXCLUDED.allowed_amount,
                        updated_at     = NOW()
                    """,
                    (intermediary_id, payer_name, cpt_code, "FL", amount),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Row {i} / {payer_name}: DB error — {str(e)}")
                skipped += 1

    return imported, skipped, errors


@router.post("/intermediaries/import")
async def import_rates(file: UploadFile = File(...), intermediary_name: str = None):
    """
    Upload a CSV to import or update intermediary rates.

    Accepts TWO formats automatically:

    1. LONG format (our standard template):
       Columns: intermediary_name, payer_name, cpt_code, state, allowed_amount, effective_date, notes

    2. WIDE format (Headway / Alma / Grow native export — payers as columns):
       Row 1 (optional): Title row, skipped
       Row 2: CPT Code | Description | Payer1 | Payer2 | ...
       Row 3+: code | description | $rate | $rate | ...
       Pass ?intermediary_name=Headway in the URL when uploading a wide-format file.

    Expected columns (long format only):
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

    # Read all rows to detect format
    raw_rows = list(csv.reader(io.StringIO(text)))

    # Find the actual header row (skip any "Florida Rates" or similar title rows)
    header_idx = 0
    for idx, row in enumerate(raw_rows):
        if row and ("cpt" in row[0].lower() or "code" in row[0].lower()
                    or "intermediary" in (row[0] if row else "").lower()):
            header_idx = idx
            break

    header    = [h.strip() for h in raw_rows[header_idx]]
    data_rows = raw_rows[header_idx + 1:]
    is_wide   = _detect_wide_format(header)

    imported = 0
    skipped  = 0
    errors   = []

    with get_db() as cur:
        cur.execute("SELECT name, intermediary_id FROM intermediaries")
        intermediary_map = {r["name"].strip().lower(): r["intermediary_id"]
                            for r in cur.fetchall()}

        cur.execute("SELECT cpt_code FROM cpt_codes")
        valid_cpts = {r["cpt_code"] for r in cur.fetchall()}

        if is_wide:
            # ── Wide format (Headway/Alma/Grow native sheet) ──────────
            # Intermediary must be specified via ?intermediary_name= param
            if not intermediary_name:
                # Try to guess from filename or default to first active intermediary
                intermediary_name = list(intermediary_map.keys())[0] if intermediary_map else None

            if not intermediary_name or intermediary_name.lower() not in intermediary_map:
                return {
                    "status":   "error",
                    "imported": 0,
                    "skipped":  0,
                    "errors":   [f"Wide-format CSV detected. Please specify ?intermediary_name=Headway (or Alma, Grow Therapy) in the upload URL."],
                    "message":  "Intermediary name required for wide-format upload.",
                }

            intermediary_id = intermediary_map[intermediary_name.lower()]
            payer_names     = [h.strip() for h in header[2:]]

            for i, row in enumerate(data_rows, start=header_idx + 2):
                if not row or not row[0].strip() or row[0].strip().startswith("#"):
                    skipped += 1
                    continue

                cpt_code = row[0].strip()
                desc     = row[1].strip() if len(row) > 1 else cpt_code

                # Auto-add new CPT codes (e.g. 98000–98007 telehealth codes)
                if cpt_code not in valid_cpts:
                    try:
                        category = "Telehealth E/M" if cpt_code.startswith("980") else "E/M"
                        cur.execute(
                            """
                            INSERT INTO cpt_codes (cpt_code, short_description, full_description, category)
                            VALUES (%s, %s, %s, %s) ON CONFLICT (cpt_code) DO NOTHING
                            """,
                            (cpt_code, desc[:100], desc, category),
                        )
                        valid_cpts.add(cpt_code)
                    except Exception as e:
                        errors.append(f"Row {i}: could not add CPT {cpt_code} — {e}")
                        skipped += 1
                        continue

                for col_idx, payer_name in enumerate(payer_names, start=2):
                    raw = row[col_idx].strip() if col_idx < len(row) else ""
                    if not raw:
                        continue
                    amount_str = raw.replace("$", "").replace(",", "").strip()
                    if not amount_str:
                        continue
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        continue
                    if amount <= 0:
                        continue

                    # Ensure payer is registered in the mapping table
                    cur.execute(
                        "INSERT INTO intermediary_payer_map (intermediary_payer_name) VALUES (%s) ON CONFLICT DO NOTHING",
                        (payer_name,),
                    )

                    try:
                        cur.execute(
                            """
                            INSERT INTO intermediary_rates
                                (intermediary_id, payer_name, cpt_code, state,
                                 allowed_amount, effective_date, updated_at)
                            VALUES (%s, %s, %s, %s, %s, NULL, NOW())
                            ON CONFLICT ON CONSTRAINT intermediary_rates_unique
                            DO UPDATE SET
                                allowed_amount = EXCLUDED.allowed_amount,
                                updated_at     = NOW()
                            """,
                            (intermediary_id, payer_name, cpt_code, "FL", amount),
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {i} / {payer_name}: {str(e)}")
                        skipped += 1

        else:
            # ── Long format (our standard template) ──────────────────
            dict_reader = csv.DictReader(io.StringIO(text))

            for i, row in enumerate(dict_reader, start=2):
                first_val = (list(row.values())[0] or "").strip()
                if first_val.startswith("#"):
                    skipped += 1
                    continue

                iname = (row.get("intermediary_name") or "").strip()
                if not iname:
                    skipped += 1
                    continue
                intermediary_id = intermediary_map.get(iname.lower())
                if not intermediary_id:
                    errors.append(f"Row {i}: unknown intermediary '{iname}' — skipped")
                    skipped += 1
                    continue

                pname    = (row.get("payer_name") or "").strip() or None
                cpt_code = (row.get("cpt_code") or "").strip()

                if not cpt_code:
                    skipped += 1
                    continue

                # Auto-add unknown CPT codes
                if cpt_code not in valid_cpts:
                    category = "Telehealth E/M" if cpt_code.startswith("980") else "E/M"
                    cur.execute(
                        "INSERT INTO cpt_codes (cpt_code, short_description, category) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (cpt_code, cpt_code, category),
                    )
                    valid_cpts.add(cpt_code)

                amount_raw = (row.get("allowed_amount") or "").strip().replace("$", "").replace(",", "")
                if not amount_raw:
                    skipped += 1
                    continue
                try:
                    allowed_amount = float(amount_raw)
                except ValueError:
                    errors.append(f"Row {i}: invalid amount '{amount_raw}' — skipped")
                    skipped += 1
                    continue

                state          = (row.get("state") or "FL").strip() or "FL"
                eff_raw        = (row.get("effective_date") or "").strip()
                effective_date = eff_raw if eff_raw else None
                notes          = (row.get("notes") or "").strip() or None

                if pname:
                    cur.execute(
                        "INSERT INTO intermediary_payer_map (intermediary_payer_name) VALUES (%s) ON CONFLICT DO NOTHING",
                        (pname,),
                    )

                try:
                    cur.execute(
                        """
                        INSERT INTO intermediary_rates
                            (intermediary_id, payer_name, cpt_code, state,
                             allowed_amount, effective_date, notes, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT ON CONSTRAINT intermediary_rates_unique
                        DO UPDATE SET
                            allowed_amount = EXCLUDED.allowed_amount,
                            notes          = EXCLUDED.notes,
                            updated_at     = NOW()
                        """,
                        (intermediary_id, pname, cpt_code, state,
                         allowed_amount, effective_date, notes),
                    )
                    imported += 1
                except Exception as e:
                    errors.append(f"Row {i}: DB error — {str(e)}")
                    skipped += 1

    fmt = "wide (payer-as-columns)" if is_wide else "long (row-per-rate)"
    return {
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors[:20],
        "message":  f"Imported {imported} rate(s) from {fmt} CSV. {skipped} row(s) skipped.",
    }


# ── Channel Comparison ────────────────────────────────────────

@router.get("/channel-comparison")
def get_channel_comparison(
    payer_id:   int = None,
    payer_name: str = None,
    cpt_code:   str = None,
    best_only:  bool = False,
):
    """
    Return side-by-side comparison of direct billing vs each intermediary.

    Optional filters:
      - payer_id:   filter to a specific payer (direct-contract payers only)
      - payer_name: filter by payer name text (works for all payers incl. intermediary-only)
      - cpt_code:   filter to a specific CPT code
      - best_only:  only return rows where an intermediary pays more than direct
    """
    filters = []
    params  = []

    if payer_id:
        filters.append("payer_id = %s")
        params.append(payer_id)
    if payer_name:
        filters.append("payer_name = %s")
        params.append(payer_name)
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
