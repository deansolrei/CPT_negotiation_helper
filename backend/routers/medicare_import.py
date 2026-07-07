import csv, io
from fastapi import APIRouter, UploadFile, File
from ..database import get_db

router = APIRouter(prefix="/api", tags=["Medicare Rates"])

@router.post("/medicare/import")
async def import_medicare_rates(file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode('utf-8-sig')
    except:
        text = content.decode('latin-1')
    imported = 0
    skipped = 0
    errors = []
    with get_db() as cur:
        cur.execute("DELETE FROM benchmark_fee_schedule WHERE source_name='Medicare 2026' AND effective_year=2026")
        for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            state = (row.get('state') or '').strip().upper()
            locality = (row.get('locality') or '').strip().upper()
            cpt_code = (row.get('cpt_code') or '').strip()
            amt_raw = (row.get('allowed_amount') or '').strip().replace('$','').replace(',','')
            if not state or not cpt_code or not amt_raw:
                skipped += 1
                continue
            try:
                amount = float(amt_raw)
            except:
                skipped += 1
                continue
            loc = locality if locality else state
            try:
                cur.execute(
                    "INSERT INTO benchmark_fee_schedule (source_name, effective_year, locality, cpt_code, allowed_amount) VALUES ('Medicare 2026', 2026, %s, %s, %s) ON CONFLICT (source_name, effective_year, locality, cpt_code) DO UPDATE SET allowed_amount=EXCLUDED.allowed_amount",
                    (loc, cpt_code, amount)
                )
                imported += 1
            except Exception as e:
                errors.append(str(e))
                skipped += 1
    return {'status':'ok','imported':imported,'skipped':skipped,'errors':errors[:5],'message':f'Imported {imported} Medicare rates.'}

@router.get("/medicare/rates")
def get_medicare_rates(state: str = 'FL', locality: str = None):
    loc = (locality or state).upper()
    with get_db() as cur:
        cur.execute("SELECT locality, cpt_code, allowed_amount FROM benchmark_fee_schedule WHERE source_name='Medicare 2026' AND effective_year=2026 AND locality=%s ORDER BY cpt_code", (loc,))
        return cur.fetchall()
