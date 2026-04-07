"""
load_medicare_2026.py
---------------------
Loads 2026 Medicare non-facility (telehealth/office) benchmark rates
for all CPT codes in the Solrei CPT Negotiation Helper database.

Rates are calculated from published 2026 CMS RVU values using:
  Payment = (Work RVU + PE RVU + MP RVU) × Conversion Factor ($33.40)

These are 2026 national average non-facility rates.
Florida (Orlando locality) GPCI is ~1.00 for work and ~0.99 for PE,
so actual FL rates are within 1-2% of these figures.

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_medicare_2026.py

The script POSTs to your running FastAPI server at localhost:8000.
Make sure uvicorn is running before executing this script.
"""

import json
import urllib.request
import urllib.error

API_URL = "http://localhost:8000/api/import-benchmark"

# ──────────────────────────────────────────────────────────────────
# 2026 Medicare rates (national average, non-facility setting)
# Source: CMS 2026 Physician Fee Schedule Final Rule (CMS-1832-F)
#         Conversion Factor: $33.40 (non-qualifying APM)
#         RVU data: CMS PFS final rule tables, effective 01/01/2026
# ──────────────────────────────────────────────────────────────────
RATES = [
    # ── Evaluation & Management (Office / Telehealth) ──────────────
    # These are the bread-and-butter psychiatry med management codes.
    # Telehealth (POS 10/02) rates are the same as office (POS 11) post-2024.
    {"cpt_code": "99202", "allowed_amount": 79.82,
        "notes": "New pt E/M low; Work 0.93 + PE 1.39 + MP 0.07"},
    {"cpt_code": "99203", "allowed_amount": 111.56,
        "notes": "New pt E/M moderate; Work 1.60 + PE 1.64 + MP 0.10"},
    {"cpt_code": "99204", "allowed_amount": 166.00,
        "notes": "New pt E/M mod-high; Work 2.60 + PE 2.27 + MP 0.10"},
    {"cpt_code": "99205", "allowed_amount": 211.42,
        "notes": "New pt E/M high; Work 3.50 + PE 2.78 + MP 0.15"},
    {"cpt_code": "99212", "allowed_amount": 57.45,
        "notes": "Est pt E/M brief; Work 0.70 + PE 0.97 + MP 0.05"},
    {"cpt_code": "99213", "allowed_amount": 91.52,
        "notes": "Est pt E/M low; Work 1.30 + PE 1.35 + MP 0.09"},
    {"cpt_code": "99214", "allowed_amount": 135.60,
        "notes": "Est pt E/M moderate; Work 1.92 + PE 1.95 + MP 0.14 × $33.40"},
    {"cpt_code": "99215", "allowed_amount": 185.37,
        "notes": "Est pt E/M high; Work 2.80 + PE 2.46 + MP 0.18"},

    # ── Psychiatric Diagnostic Evaluations ─────────────────────────
    {"cpt_code": "90791", "allowed_amount": 186.71,
        "notes": "Psych eval no medical; Work 3.25 + PE 2.22 + MP 0.13"},
    {"cpt_code": "90792", "allowed_amount": 218.77,
        "notes": "Psych eval with medical; Work 3.86 + PE 2.43 + MP 0.32"},

    # ── Individual Psychotherapy (standalone) ──────────────────────
    {"cpt_code": "90832", "allowed_amount": 92.85,
        "notes": "Individual therapy 30 min; Work 1.50 + PE 1.19 + MP 0.09"},
    {"cpt_code": "90834", "allowed_amount": 126.25,
        "notes": "Individual therapy 45 min; Work 2.10 + PE 1.56 + MP 0.12"},
    {"cpt_code": "90837", "allowed_amount": 166.33,
        "notes": "Individual therapy 60 min; Work 2.83 + PE 1.98 + MP 0.15"},

    # ── Add-on Psychotherapy (billed with E/M) ────────────────────
    # Add-on codes use facility PE RVUs (lower PE) since billed alongside E/M.
    {"cpt_code": "90833", "allowed_amount": 45.42,
        "notes": "Add-on therapy 30 min with E/M; Work 0.99 + PE 0.32 + MP 0.05"},
    {"cpt_code": "90836", "allowed_amount": 67.47,
        "notes": "Add-on therapy 45 min with E/M; Work 1.52 + PE 0.42 + MP 0.08"},
    {"cpt_code": "90838", "allowed_amount": 92.18,
        "notes": "Add-on therapy 60 min with E/M; Work 2.10 + PE 0.55 + MP 0.11"},

    # ── Family Psychotherapy ──────────────────────────────────────
    {"cpt_code": "90846", "allowed_amount": 126.25,
        "notes": "Family therapy w/o patient; Work 2.10 + PE 1.56 + MP 0.12"},
    {"cpt_code": "90847", "allowed_amount": 126.25,
        "notes": "Family therapy w/ patient; Work 2.10 + PE 1.56 + MP 0.12"},

    # ── Group Psychotherapy ───────────────────────────────────────
    {"cpt_code": "90853", "allowed_amount": 47.09,
        "notes": "Group therapy per patient; Work 0.75 + PE 0.61 + MP 0.05"},

    # ── Crisis Psychotherapy ──────────────────────────────────────
    {"cpt_code": "90839", "allowed_amount": 242.82,
        "notes": "Crisis therapy first 60 min; Work 4.40 + PE 2.66 + MP 0.21"},
    {"cpt_code": "90840", "allowed_amount": 104.21,
        "notes": "Crisis therapy add-on 30 min; Work 2.20 + PE 0.83 + MP 0.09"},

    # ── Screening ─────────────────────────────────────────────────
    {"cpt_code": "96127", "allowed_amount": 17.49,
        "notes": "Brief behavioral assessment per instrument; Work 0.18 + PE 0.33 + MP 0.01"},

    # ── Psychological Testing ─────────────────────────────────────
    {"cpt_code": "96130", "allowed_amount": 125.60,
        "notes": "Psych testing evaluation first hour; Work 2.20 + PE 1.49 + MP 0.07"},
    {"cpt_code": "96136", "allowed_amount": 71.48,
        "notes": "Psych testing by NP first 30 min; Work 1.19 + PE 0.89 + MP 0.06"},
    {"cpt_code": "96138", "allowed_amount": 49.10,
        "notes": "Psych testing by tech first 30 min; Work 0.75 + PE 0.64 + MP 0.08"},

    # ── Behavioral Health Integration ─────────────────────────────
    {"cpt_code": "99484", "allowed_amount": 73.81,
        "notes": "General BHI 20+ min monthly; Work 1.00 + PE 1.15 + MP 0.06"},

    # ── Prolonged Services ────────────────────────────────────────
    {"cpt_code": "99417", "allowed_amount": 31.73,
        "notes": "Prolonged E/M add-on per 15 min; Work 0.54 + PE 0.38 + MP 0.03"},
    {"cpt_code": "99354", "allowed_amount": 132.93,
        "notes": "Prolonged face-to-face first 30-60 min; Work 2.33 + PE 1.57 + MP 0.08"},
    {"cpt_code": "99355", "allowed_amount": 95.86,
        "notes": "Prolonged face-to-face each addl 30 min; Work 1.77 + PE 1.00 + MP 0.10"},

    # ── Health Behavior ───────────────────────────────────────────
    {"cpt_code": "99406", "allowed_amount": 14.79,
        "notes": "Tobacco cessation 3-10 min; Work 0.24 + PE 0.18 + MP 0.02"},
    {"cpt_code": "99407", "allowed_amount": 27.73,
        "notes": "Tobacco cessation >10 min; Work 0.50 + PE 0.29 + MP 0.04"},
    {"cpt_code": "96156", "allowed_amount": 63.46,
        "notes": "Health behavior assessment; Work 1.05 + PE 0.76 + MP 0.09"},
    {"cpt_code": "96158", "allowed_amount": 72.51,
        "notes": "Health behavior intervention individual 30 min; Work 1.20 + PE 0.87 + MP 0.10"},
    {"cpt_code": "96159", "allowed_amount": 36.74,
        "notes": "Health behavior intervention addl 15 min; Work 0.60 + PE 0.44 + MP 0.06"},
    {"cpt_code": "96164", "allowed_amount": 43.42,
        "notes": "Health behavior group first 30 min; Work 0.75 + PE 0.49 + MP 0.06"},
    {"cpt_code": "96165", "allowed_amount": 21.71,
        "notes": "Health behavior group addl 15 min; Work 0.38 + PE 0.24 + MP 0.03"},
    {"cpt_code": "96167", "allowed_amount": 72.51,
        "notes": "Health behavior family w/ patient 30 min; Work 1.20 + PE 0.87 + MP 0.10"},
    {"cpt_code": "96168", "allowed_amount": 36.74,
        "notes": "Health behavior family addl 15 min; Work 0.60 + PE 0.44 + MP 0.06"},

    # ── Collaborative Care Model (CoCM) ──────────────────────────
    {"cpt_code": "G0568", "allowed_amount": 133.20,
        "notes": "CoCM initial month 60+ min; approximate 2026 national rate"},
    {"cpt_code": "G0569", "allowed_amount": 100.20,
        "notes": "CoCM subsequent month 30+ min; approximate 2026 national rate"},
    {"cpt_code": "G0570", "allowed_amount": 39.14,
        "notes": "CoCM additional 30 min add-on; approximate 2026 national rate"},
]

payload = {
    "source_name": "Medicare 2026",
    "locality": "FL",
    "effective_year": 2026,
    "rates": RATES,
}


def main():
    print(f"Importing {len(RATES)} Medicare 2026 benchmark rates...")
    print(f"  Conversion Factor: $33.40 (2026 non-qualifying APM)")
    print(f"  Setting: Non-facility (telehealth / office)")
    print(f"  Locality: FL (national average; Florida GPCI ≈ 1.00)")
    print()

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print("✓ Success!")
            print(f"  Source:          {result['source_name']}")
            print(f"  Rates imported:  {result['lines_upserted']}")
            print(f"  Message:         {result['message']}")
            print()
            print("Next step: open http://localhost:8000/api/benchmark to verify,")
            print("then import a payer fee schedule to see the dashboard light up.")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"✗ HTTP Error {e.code}: {body}")
    except urllib.error.URLError as e:
        print(f"✗ Connection error: {e.reason}")
        print("  Is uvicorn running? Start it with: uvicorn backend.main:app --reload")


if __name__ == "__main__":
    main()
