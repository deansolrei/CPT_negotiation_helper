"""
load_claims_volume.py
---------------------
Seeds annual claims volume data for 2025 so the negotiation dashboard
can calculate real dollar impact:
  annual_revenue_current   = payer_allowed × annual_volume
  annual_revenue_at_target = target_allowed × annual_volume
  annual_revenue_gap       = the money being left on the table

IMPORTANT: The volumes below are ESTIMATES based on your clinic profile:
  - 4 providers, ~300 patients, primarily telehealth med management
  - Typical psychiatric clinic billing distribution

Replace with your actual 2025 billing data once you pull it from your
EHR/practice management system. Even rough estimates make the dashboard
dramatically more useful than no volume data at all.

How to get your real numbers:
  - Most EHRs have a "charges by CPT code" or "billing summary" report
  - Ask your biller for a CPT code frequency report for 2025
  - Export from your clearinghouse if available

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_claims_volume.py
"""

import json
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "http://localhost:8000/api"

# ── Estimated annual volume by CPT code (2025, all contracts combined) ──
# Based on: 4 PMHNPs, ~300 active patients, primarily telehealth med mgmt
# with some combined therapy (add-on psychotherapy).
#
# Assumptions:
#  - Average patient seen every 4-6 weeks (~9-10 visits/year)
#  - ~300 patients × 9 visits = ~2,700 total visits/year
#  - 99214 is the dominant code (~60% of established visits)
#  - Add-on 90833 billed on ~40% of 99214 visits
#  - New patient intakes ~60/year (turnover)
#  - 90792 used for ~50% of new intakes (prescriber eval with medical)
#
# Replace these with your actual numbers!
VOLUME_BY_CODE = {
    # ── Established Patient E/M (med management) ──────────────────
    "99214": 1620,   # ~60% of 2,700 visits — your highest-volume code
    "99213": 540,    # ~20% of visits (briefer follow-ups)
    "99215": 270,    # ~10% of visits (complex cases)
    "99212": 108,    # ~4% (very brief check-ins)

    # ── New Patient E/M ───────────────────────────────────────────
    "99204": 36,     # ~60% of ~60 new patients
    "99205": 18,     # ~30% of new patients (complex)
    "99203": 6,      # ~10% (lower complexity new)

    # ── Psychiatric Evaluations ───────────────────────────────────
    "90792": 48,     # prescriber intake with medical — most intakes
    "90791": 12,     # intake without medical services

    # ── Add-on Psychotherapy (with E/M) ──────────────────────────
    "90833": 648,    # billed on ~40% of 99214 visits (1620 × 0.40)
    "90836": 108,    # 45-min add-on, less common
    "90838": 54,     # 60-min add-on, occasional

    # ── Individual Psychotherapy (standalone) ─────────────────────
    "90837": 72,     # pure therapy visits (60 min)
    "90834": 36,     # pure therapy visits (45 min)
    "90832": 18,     # pure therapy visits (30 min)

    # ── Family Therapy ────────────────────────────────────────────
    "90847": 36,     # family with patient
    "90846": 18,     # family without patient

    # ── Group Therapy ─────────────────────────────────────────────
    "90853": 0,      # not currently running groups — update if you start

    # ── Crisis ───────────────────────────────────────────────────
    "90839": 12,     # occasional crisis presentations

    # ── Screening ────────────────────────────────────────────────
    "96127": 540,    # PHQ-9, GAD-7 — billed on many visits (per instrument)

    # ── BHI ──────────────────────────────────────────────────────
    "99484": 24,     # general BHI monthly management

    # ── Prolonged Services ────────────────────────────────────────
    "99417": 54,     # add-on prolonged E/M

    # ── Health Behavior ───────────────────────────────────────────
    "99406": 36,     # tobacco cessation brief
    "99407": 18,     # tobacco cessation intensive
}


def api_get(path):
    url = f"{BASE_URL}/{urllib.parse.quote(path, safe='=&?/')}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def api_post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 65)
    print("Claims Volume Seed — 2025 Estimated Annual Billing")
    print("=" * 65)
    print()
    print("NOTE: Using estimated volumes based on your clinic profile.")
    print("      Replace with actual 2025 data from your EHR/biller.")
    print()

    # ── Fetch all active contracts ─────────────────────────────────
    contracts = api_get("contracts?active_only=true")
    print(f"Found {len(contracts)} active contracts.")

    # ── Fetch benchmark rates to calculate revenue estimates ───────
    benchmarks = api_get("benchmark?source_name=Medicare 2026&locality=FL&year=2026")
    bench_map  = {b["cpt_code"]: float(b["allowed_amount"]) for b in benchmarks}

    # ── Distribute total volume proportionally across contracts ────
    # Simple approach: split estimated total volume by number of contracts
    # per payer. In reality you'd assign per-provider volumes.
    # Group contracts by payer for proportional splitting.
    from collections import defaultdict
    payer_contracts = defaultdict(list)
    for c in contracts:
        payer_contracts[c["payer_name"]].append(c)

    # Estimate volume per contract (split evenly within payer)
    # For payers with both group and individual contracts,
    # allocate 70% to group, 30% to individual
    total_imported = 0
    skipped        = 0

    print()
    print("Loading volume per contract:")
    print(f"  {'Contract':<50} {'Lines':>6}")
    print(f"  {'-'*50} {'-'*6}")

    for payer_name, payer_clist in payer_contracts.items():
        has_group = any(c["entity_type"] == "NPI2" for c in payer_clist)
        has_indiv = any(c["entity_type"] == "NPI1" for c in payer_clist)

        for contract in payer_clist:
            # Allocation weight: group gets 70% if mixed, else 100%
            if has_group and has_indiv:
                weight = 0.70 if contract["entity_type"] == "NPI2" else 0.30
            else:
                weight = 1.00

            lines_loaded = 0
            for cpt_code, total_vol in VOLUME_BY_CODE.items():
                vol = max(1, round(total_vol * weight)) if total_vol > 0 else 0
                if vol == 0:
                    continue
                try:
                    api_post("claims-volume", {
                        "contract_id":   contract["contract_id"],
                        "cpt_code":      cpt_code,
                        "modifier":      "95",
                        "calendar_year": 2025,
                        "annual_volume": vol,
                        "notes":         "Estimated 2025 volume. Replace with actual EHR data.",
                    })
                    lines_loaded += 1
                except urllib.error.HTTPError as e:
                    body = e.read().decode()
                    if "not found" in body.lower():
                        skipped += 1
                    else:
                        print(f"\n    ERROR on {cpt_code}: {body}")

            label = f"[{contract['contract_id']}] {contract['payer_name']} × {contract['provider_name'][:25]}"
            print(f"  {label:<50} {lines_loaded:>6}")
            total_imported += lines_loaded

    print()
    print(f"✓ {total_imported} volume records loaded  ({skipped} skipped — no fee schedule line)")
    print()

    # ── Show revenue impact preview ────────────────────────────────
    print("Estimated annual revenue impact (across all payers):")
    print(f"  {'Code':<8} {'Volume':>8} {'Med Rate':>10} {'Est Revenue':>13} {'At Target':>13} {'Gap':>12}")
    print(f"  {'-'*8} {'-'*8} {'-'*10} {'-'*13} {'-'*13} {'-'*12}")

    highlight = ["99214", "99213", "99215", "90833", "90792", "90837", "90791"]
    total_rev     = 0
    total_target  = 0
    for code in highlight:
        vol = VOLUME_BY_CODE.get(code, 0)
        med = bench_map.get(code)
        if not med or not vol:
            continue
        rev    = round(med * 0.85 * vol, 0)   # rough blended 85% of Medicare
        tgt    = round(med * 1.30 * vol, 0)   # at 130% target
        gap    = tgt - rev
        total_rev    += rev
        total_target += tgt
        print(f"  {code:<8} {vol:>8,} ${med:>9.2f} ${rev:>12,.0f} ${tgt:>12,.0f} ${gap:>11,.0f}")

    print(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*13} {'─'*13} {'─'*12}")
    print(f"  {'TOTAL':<8} {'':>8} {'':>10} ${total_rev:>12,.0f} ${total_target:>12,.0f} ${total_target-total_rev:>11,.0f}")
    print()
    print("The 'Gap' column is estimated additional annual revenue at your 130% target.")
    print()
    print("View full dashboard with live numbers:")
    print("  http://localhost:8000/api/dashboard/summary")
    print("  http://localhost:8000/api/dashboard/underpaid/1   (Florida Blue)")


if __name__ == "__main__":
    main()
