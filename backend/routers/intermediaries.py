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

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from ..database import get_db

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
        cur.execute(
            "SELECT name FROM intermediaries WHERE active = TRUE ORDER BY name")
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
    writer.writerow(["# intermediary_name", "Required. One of: " +
                    ", ".join(intermediaries), "", "", "", "", ""])
    writer.writerow(
        ["# payer_name", "Optional. Leave blank for platform-wide rate", "", "", "", "", ""])
    writer.writerow(
        ["# state", "Optional. Default FL. Leave blank for national", "", "", "", "", ""])
    writer.writerow(
        ["# allowed_amount", "Required. Provider take-home $ (e.g. 145.00)", "", "", "", "", ""])
    writer.writerow(
        ["# effective_date", "Optional. YYYY-MM-DD", "", "", "", "", ""])
    writer.writerow(["# notes", "Optional free text", "", "", "", "", ""])
    writer.writerow([])

    # CPT codes to include in the template, in the specified order
    key_cpts = ["99214", "99215", "90833", "90836", "90838",
                "99204", "99205", "90785", "98003", "98002", "98006", "98007"]
    cpt_lookup = {r["cpt_code"]: r for r in cpt_rows}
    example_cpts = [cpt_lookup[c] for c in key_cpts if c in cpt_lookup]

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
    looks_like_cpt_col = "cpt" in header[0].lower(
    ) or "code" in header[0].lower()
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
    skipped = 0
    errors = []

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
                category = "Telehealth E/M" if cpt_code.startswith(
                    "980") else "E/M"
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
            intermediary_id = list(intermediary_map.values())[
                0] if intermediary_map else None
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

    header = [h.strip() for h in raw_rows[header_idx]]
    data_rows = raw_rows[header_idx + 1:]
    is_wide = _detect_wide_format(header)

    imported = 0
    skipped = 0
    errors = []

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
                intermediary_name = list(intermediary_map.keys())[
                    0] if intermediary_map else None

            if not intermediary_name or intermediary_name.lower() not in intermediary_map:
                return {
                    "status":   "error",
                    "imported": 0,
                    "skipped":  0,
                    "errors":   [f"Wide-format CSV detected. Please specify ?intermediary_name=Headway (or Alma, Grow Therapy) in the upload URL."],
                    "message":  "Intermediary name required for wide-format upload.",
                }

            intermediary_id = intermediary_map[intermediary_name.lower()]
            payer_names = [h.strip() for h in header[2:]]

            for i, row in enumerate(data_rows, start=header_idx + 2):
                if not row or not row[0].strip() or row[0].strip().startswith("#"):
                    skipped += 1
                    continue

                cpt_code = row[0].strip()
                desc = row[1].strip() if len(row) > 1 else cpt_code

                # Auto-add new CPT codes (e.g. 98000–98007 telehealth codes)
                if cpt_code not in valid_cpts:
                    try:
                        category = "Telehealth E/M" if cpt_code.startswith(
                            "980") else "E/M"
                        cur.execute(
                            """
                            INSERT INTO cpt_codes (cpt_code, short_description, category, is_time_based, is_addon, primary_code_required, telehealth_eligible)
                            VALUES (%s, %s, %s, FALSE, FALSE, FALSE, TRUE) ON CONFLICT (cpt_code) DO NOTHING
                            """,
                            (cpt_code, desc[:100], category),
                        )
                        valid_cpts.add(cpt_code)
                    except Exception as e:
                        errors.append(
                            f"Row {i}: could not add CPT {cpt_code} — {e}")
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
                    errors.append(
                        f"Row {i}: unknown intermediary '{iname}' — skipped")
                    skipped += 1
                    continue

                pname = (row.get("payer_name") or "").strip() or None
                cpt_code = (row.get("cpt_code") or "").strip()

                if not cpt_code:
                    skipped += 1
                    continue

                # Auto-add unknown CPT codes
                if cpt_code not in valid_cpts:
                    category = "Telehealth E/M" if cpt_code.startswith(
                        "980") else "E/M"
                    cur.execute(
                        "INSERT INTO cpt_codes (cpt_code, short_description, category, is_time_based, is_addon, primary_code_required, telehealth_eligible) VALUES (%s, %s, %s, FALSE, FALSE, FALSE, TRUE) ON CONFLICT DO NOTHING",
                        (cpt_code, cpt_code, category),
                    )
                    valid_cpts.add(cpt_code)

                amount_raw = (row.get("allowed_amount") or "").strip().replace(
                    "$", "").replace(",", "")
                if not amount_raw:
                    skipped += 1
                    continue
                try:
                    allowed_amount = float(amount_raw)
                except ValueError:
                    errors.append(
                        f"Row {i}: invalid amount '{amount_raw}' — skipped")
                    skipped += 1
                    continue

                state = (row.get("state") or "FL").strip() or "FL"
                eff_raw = (row.get("effective_date") or "").strip()
                effective_date = eff_raw if eff_raw else None
                notes = (row.get("notes") or "").strip() or None

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

VALID_STATES = {
    "AK", "AZ", "CO", "DC", "FL", "HI", "ID", "IA", "KS", "ME", "MD",
    "MN", "MT", "NE", "NV", "NH", "NM", "ND", "OR", "SD", "VT", "WA", "WY",
}

CHANNEL_COMPARISON_SQL = """
WITH
direct_rates AS (
    SELECT DISTINCT ON (p.payer_name, fsl.cpt_code)
        p.payer_name,
        fsl.cpt_code,
        fsl.allowed_amount AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id      = c.contract_id
    JOIN payers            p   ON c.payer_id           = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
    WHERE c.active = TRUE
      AND (c.end_date   IS NULL OR c.end_date   >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
    ORDER BY p.payer_name, fsl.cpt_code,
        CASE pe.entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
        fsl.allowed_amount DESC
),
medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name   = 'Medicare 2026'
      AND  effective_year = 2026
      AND  locality       = %(state)s
),
channel_cpts AS (
    SELECT unnest(ARRAY[
        '99214','99215','90833','90836','90838',
        '99204','99205','90785',
        '98002','98003','98006','98007'
    ]) AS cpt_code
),
all_combos AS (
    SELECT DISTINCT ir.payer_name, ir.cpt_code
    FROM   intermediary_rates ir
    WHERE  ir.payer_name IS NOT NULL
      AND  ir.cpt_code IN (SELECT cpt_code FROM channel_cpts)
    UNION
    SELECT DISTINCT p.payer_name, fsl.cpt_code
    FROM   fee_schedule_lines fsl
    JOIN   contracts c ON fsl.contract_id = c.contract_id
    JOIN   payers    p ON c.payer_id      = p.payer_id
    WHERE  c.active = TRUE
      AND (c.end_date   IS NULL OR c.end_date   >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
      AND  fsl.cpt_code IN (SELECT cpt_code FROM channel_cpts)
),
name_resolved AS (
    SELECT DISTINCT ON (ac.payer_name)
        ac.payer_name AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            (SELECT p.payer_name FROM payers p
             WHERE  lower(p.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM  all_combos ac
    LEFT JOIN intermediary_payer_map ipm
           ON ipm.intermediary_payer_name = ac.payer_name
    ORDER BY ac.payer_name, ipm.direct_payer_name NULLS LAST
),
headway AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS headway_rate,
        ir.updated_at     AS headway_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = %(state)s
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),
alma AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS alma_rate,
        ir.updated_at     AS alma_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = %(state)s
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),
grow AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS grow_rate,
        ir.updated_at     AS grow_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Grow Therapy' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = %(state)s
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),
combined AS (
    SELECT
        p.payer_id,
        ac.payer_name,
        ac.cpt_code,
        cc.short_description,
        cc.category,
        m.medicare_allowed,
        dr.direct_rate,
        CASE WHEN dr.direct_rate IS NOT NULL AND m.medicare_allowed > 0
             THEN ROUND((dr.direct_rate / m.medicare_allowed * 100)::numeric, 1)
        END AS direct_pct_of_medicare,
        h.headway_rate,    h.headway_updated_at,
        a.alma_rate,       a.alma_updated_at,
        g.grow_rate,       g.grow_updated_at,
        LEAST(h.headway_updated_at, a.alma_updated_at, g.grow_updated_at)
            AS oldest_intermediary_update,
        CASE
            WHEN GREATEST(
                COALESCE(dr.direct_rate, 0),
                COALESCE(h.headway_rate, 0),
                COALESCE(a.alma_rate,    0),
                COALESCE(g.grow_rate,    0)
            ) = 0 THEN 'No Data'
            WHEN COALESCE(dr.direct_rate, 0) >= COALESCE(h.headway_rate, 0)
             AND COALESCE(dr.direct_rate, 0) >= COALESCE(a.alma_rate,    0)
             AND COALESCE(dr.direct_rate, 0) >= COALESCE(g.grow_rate,    0)
             AND dr.direct_rate IS NOT NULL
            THEN 'Direct'
            ELSE 'Intermediary'
        END AS best_channel_type,
        CASE WHEN dr.direct_rate IS NOT NULL THEN TRUE ELSE FALSE END
            AS has_direct_contract
    FROM  all_combos ac
    JOIN  cpt_codes       cc  ON cc.cpt_code  = ac.cpt_code
    LEFT JOIN medicare    m   ON m.cpt_code   = ac.cpt_code
    LEFT JOIN name_resolved nr ON nr.intermediary_payer_name = ac.payer_name
    LEFT JOIN direct_rates dr ON dr.payer_name = nr.direct_payer_name
                              AND dr.cpt_code  = ac.cpt_code
    LEFT JOIN payers       p  ON p.payer_name  = nr.direct_payer_name
    LEFT JOIN headway      h  ON h.payer_name  = ac.payer_name AND h.cpt_code = ac.cpt_code
    LEFT JOIN alma         a  ON a.payer_name  = ac.payer_name AND a.cpt_code = ac.cpt_code
    LEFT JOIN grow         g  ON g.payer_name  = ac.payer_name AND g.cpt_code = ac.cpt_code
)
SELECT DISTINCT ON (payer_name, cpt_code)
    payer_id, payer_name, cpt_code, short_description, category,
    medicare_allowed, direct_rate, direct_pct_of_medicare,
    headway_rate, headway_updated_at,
    alma_rate,    alma_updated_at,
    grow_rate,    grow_updated_at,
    oldest_intermediary_update,
    best_channel_type, has_direct_contract
FROM combined
ORDER BY payer_name, cpt_code
"""


@router.get("/channel-comparison")
def get_channel_comparison(
    payer_id:   int = None,
    payer_name: str = None,
    cpt_code:   str = None,
    best_only:  bool = False,
    state:      str = Query(
        default="FL", description="Two-letter state code for Medicare benchmark"),
):
    """
    Return side-by-side comparison of direct billing vs each intermediary.
    State parameter controls both the Medicare benchmark locality and which
    intermediary rate rows are returned (exact state match; no FL fallback).
    """
    state_upper = state.upper() if state else "FL"
    if state_upper not in VALID_STATES:
        state_upper = "FL"

    # Build optional WHERE filters using named params (consistent with base query)
    conditions = []
    params: dict = {"state": state_upper}
    if payer_id:
        conditions.append("payer_id = %(payer_id)s")
        params["payer_id"] = payer_id
    if payer_name:
        conditions.append("payer_name = %(payer_name)s")
        params["payer_name"] = payer_name
    if cpt_code:
        conditions.append("cpt_code = %(cpt_code)s")
        params["cpt_code"] = cpt_code
    if best_only:
        conditions.append("best_channel_type = 'Intermediary'")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT * FROM ({CHANNEL_COMPARISON_SQL}) AS ch {where}"

    with get_db() as cur:
        cur.execute(sql, params)
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
def export_channel_comparison(
    payer_id: int = None,
    state: str = Query(default="FL"),
):
    """Export the full channel comparison as a CSV file."""
    where = "WHERE payer_id = %s" if payer_id else ""
    params = [payer_id] if payer_id else []

    with get_db() as cur:
        cur.execute(f"SELECT * FROM v_channel_comparison {where}", params)
        rows = cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404, detail="No channel comparison data found.")

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
