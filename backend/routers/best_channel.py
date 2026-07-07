from fastapi import APIRouter, Query
from ..database import get_db

router = APIRouter(prefix="/api", tags=["Best Channel"])

CARRIER_MAP = {
    "aetna": "Aetna",
    "aetna - allied plan": "Aetna",
    "aetna - pacificsource": "Aetna",
    "aetna - signature": "Aetna",
    "aetna banner": "Aetna",
    "aetna choice": "Aetna",
    "aetna (headway)": "Aetna",
    "ambetter": "Ambetter",
    "anthem blue cross and blue shield colorado": "Anthem BCBS Colorado",
    "anthem blue cross and blue shield nevada": "Anthem BCBS Nevada",
    "anthem blue cross and blue shield florida": "Florida Blue",
    "anthem blue cross and blue shield connecticut": "Anthem BCBS Connecticut",
    "anthem blue cross and blue shield maine": "Anthem BCBS Maine",
    "anthem blue cross and blue shield new hampshire": "Anthem BCBS New Hampshire",
    "anthem": "Anthem BCBS Colorado",
    "bcbs - anthem": "Anthem BCBS Colorado",
    "carefirst": "Anthem BCBS Colorado",
    "blue cross blue shield of arizona": "BCBS Arizona",
    "blue cross blue shield of massachusetts": "BCBS Massachusetts",
    "blue cross and blue shield of minnesota": "BCBS Minnesota",
    "blue cross blue shield - wellmark": "Wellmark Iowa",
    "wellmark": "Wellmark Iowa",
    "florida blue": "Florida Blue",
    "blue cross and blue shield of florida": "Florida Blue",
    "independence blue cross": "Independence Blue Cross PA",
    "premera blue cross washington": "Premera Blue Cross Washington",
    "regence bluecross blueShield of oregon": "Regence BCBS Oregon",
    "regence bluecross": "Regence BCBS Oregon",
    "regence blueShield of washington": "Regence Blue Shield Washington",
    "regence blueShield": "Regence Blue Shield Washington",
    "regence group": "Regence BCBS Oregon",
    "blue cross blue shield": None,
    "blue cross and blue shield": None,
    "bcbs": None,
    "blue shield": None,
    "cigna": "Cigna",
    "oscar": "Optum/UHC/Oscar",
    "oxford": "Optum/UHC/Oscar",
    "umr": "Optum/UHC/Oscar",
    "united healthcare": "Optum/UHC/Oscar",
    "united health": "Optum/UHC/Oscar",
    "uhc": "Optum/UHC/Oscar",
    "surest": "Optum/UHC/Oscar",
    "medica - united": "Optum/UHC/Oscar",
    "carelon": "Carelon Behavioral Health",
    "beacon": "Carelon Behavioral Health",
}

BCBS_BY_STATE = {
    "AK": "BCBS Massachusetts", "AZ": "BCBS Arizona", "CO": "Anthem BCBS Colorado",
    "CT": "Anthem BCBS Connecticut", "DC": "Blue Cross", "FL": "Florida Blue",
    "HI": "Blue Cross", "ID": "Blue Cross", "IA": "Wellmark Iowa",
    "KS": "Blue Cross", "ME": "Anthem BCBS Maine", "MD": "Blue Cross",
    "MN": "BCBS Minnesota", "MT": "Blue Cross", "NE": "Blue Cross",
    "NV": "Anthem BCBS Nevada", "NH": "Anthem BCBS New Hampshire",
    "NM": "BCBS Massachusetts", "ND": "Blue Cross", "OR": "Regence BCBS Oregon",
    "SD": "Blue Cross", "UT": "Blue Cross", "VT": "Blue Cross",
    "WA": "Regence Blue Shield Washington", "WY": "Blue Cross",
}

def _resolve_carrier(carrier_name, state):
    if not carrier_name: return None
    n = carrier_name.lower().strip()
    if "cash" in n or "self pay" in n or "self-pay" in n: return None
    if n in CARRIER_MAP:
        r = CARRIER_MAP[n]
        return BCBS_BY_STATE.get(state.upper(), "Blue Cross") if r is None else r
    best_key, best_len = None, 0
    for key, val in CARRIER_MAP.items():
        if n.startswith(key) and len(key) > best_len:
            best_key, best_len = key, len(key)
    if best_key:
        r = CARRIER_MAP[best_key]
        return BCBS_BY_STATE.get(state.upper(), "Blue Cross") if r is None else r
    for key, val in sorted(CARRIER_MAP.items(), key=lambda x: -len(x[0])):
        if key in n:
            r = val
            return BCBS_BY_STATE.get(state.upper(), "Blue Cross") if r is None else r
    return None

@router.get("/best-channel")
def get_best_channel(
    carrier: str = Query(...),
    state: str = Query(default="FL"),
    cpts: str = Query(default="99214"),
):
    state_upper = (state or "FL").upper()
    cpt_list = [c.strip() for c in cpts.split(",") if c.strip()] or ["99214"]
    canonical = _resolve_carrier(carrier, state_upper)
    if not canonical:
        return {"canonical_payer": None, "state": state_upper, "cpt_results": [],
                "overall_best_channel": None, "mapped": False, "raw_carrier": carrier,
                "note": "Carrier not mapped"}
    with get_db() as cur:
        cur.execute("""
            WITH
            sbh AS (SELECT ir.cpt_code, ir.allowed_amount AS clinic_rate
                FROM intermediary_rates ir JOIN intermediaries i ON ir.intermediary_id=i.intermediary_id
                WHERE i.name='SBH' AND ir.payer_name=%s AND ir.state=%s),
            headway AS (SELECT ir.cpt_code, ir.allowed_amount AS headway_rate
                FROM intermediary_rates ir JOIN intermediaries i ON ir.intermediary_id=i.intermediary_id
                WHERE i.name='Headway' AND ir.payer_name=%s AND ir.state=%s),
            alma AS (SELECT ir.cpt_code, ir.allowed_amount AS alma_rate
                FROM intermediary_rates ir JOIN intermediaries i ON ir.intermediary_id=i.intermediary_id
                WHERE i.name='Alma' AND ir.payer_name=%s AND ir.state=%s),
            grow AS (SELECT ir.cpt_code, ir.allowed_amount AS grow_rate
                FROM intermediary_rates ir JOIN intermediaries i ON ir.intermediary_id=i.intermediary_id
                WHERE i.name='Grow Therapy' AND ir.payer_name=%s AND ir.state=%s),
            medicare AS (SELECT cpt_code, allowed_amount AS medicare_rate
                FROM benchmark_fee_schedule
                WHERE source_name='Medicare 2026' AND effective_year=2026 AND locality=%s)
            SELECT COALESCE(s.cpt_code,h.cpt_code,a.cpt_code,g.cpt_code) AS cpt_code,
                s.clinic_rate, h.headway_rate, a.alma_rate, g.grow_rate, m.medicare_rate
            FROM sbh s FULL JOIN headway h USING(cpt_code) FULL JOIN alma a USING(cpt_code)
            FULL JOIN grow g USING(cpt_code) FULL JOIN medicare m USING(cpt_code)
            WHERE COALESCE(s.cpt_code,h.cpt_code,a.cpt_code,g.cpt_code)=ANY(%s)
            ORDER BY cpt_code
        """, (canonical,state_upper,canonical,state_upper,canonical,state_upper,
                canonical,state_upper,state_upper,cpt_list))
        rows = cur.fetchall()
    cpt_results, channel_votes = [], {}
    for row in rows:
        rates = {"Clinic Submit":row["clinic_rate"],"Headway":row["headway_rate"],
                 "Alma":row["alma_rate"],"Grow Therapy":row["grow_rate"]}
        available = {k:v for k,v in rates.items() if v is not None}
        best = max(available, key=available.get) if available else None
        if best: channel_votes[best] = channel_votes.get(best,0)+1
        pct = round(row["clinic_rate"]/row["medicare_rate"]*100,1) if row["clinic_rate"] and row["medicare_rate"] else None
        cpt_results.append({"cpt_code":row["cpt_code"],"clinic_rate":row["clinic_rate"],
            "headway_rate":row["headway_rate"],"alma_rate":row["alma_rate"],
            "grow_rate":row["grow_rate"],"medicare_rate":row["medicare_rate"],
            "pct_of_medicare":pct,"best_channel":best,
            "best_rate":available.get(best),"clinic_is_best":best=="Clinic Submit"})
    overall_best = max(channel_votes,key=channel_votes.get) if channel_votes else None
    return {"canonical_payer":canonical,"state":state_upper,"cpt_results":cpt_results,
            "overall_best_channel":overall_best,"channel_vote_counts":channel_votes,
            "mapped":True,"raw_carrier":carrier}
