"""
load_other_payers.py
--------------------
Imports estimated fee schedule rates for all remaining Solrei payers:
  - Wellmark Iowa
  - Aetna
  - Ambetter
  - Cigna
  - Optum / UHC

Rates are estimated based on typical commercial reimbursement factors
relative to Medicare 2026. These should be replaced with actual contracted
rates as you obtain them from each payer.

Typical commercial NP reimbursement factors (relative to Medicare):
  - Wellmark Iowa:  ~85% of Medicare (BCBS affiliate, similar to FL Blue)
  - Aetna:          ~90% of Medicare (tends to be slightly higher than BCBS)
  - Ambetter:       ~80% of Medicare (ACA exchange, tends to be lower)
  - Cigna:          ~92% of Medicare (generally competitive)
  - Optum / UHC:    ~95% of Medicare (typically highest commercial payer)

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_other_payers.py
"""

import json
import urllib.request
import urllib.error
import urllib.parse

BASE_URL   = "http://localhost:8000/api"
IMPORT_URL = f"{BASE_URL}/import-fee-schedule"

# ── Payer rate factors (% of Medicare) ────────────────────────
# Replace these with actual contracted rates when you have them.
# Source: typical behavioral health commercial market benchmarks, FL 2026.
PAYER_FACTORS = {
    "Wellmark Iowa": {
        "factor":      0.85,
        "notes_label": "Estimated 85% of Medicare (BCBS affiliate). Replace with actual contract rate.",
    },
    "Aetna": {
        "factor":      0.90,
        "notes_label": "Estimated 90% of Medicare. Replace with actual contract rate.",
    },
    "Ambetter": {
        "factor":      0.80,
        "notes_label": "Estimated 80% of Medicare (ACA exchange). Replace with actual contract rate.",
    },
    "Cigna": {
        "factor":      0.92,
        "notes_label": "Estimated 92% of Medicare. Replace with actual contract rate.",
    },
    "Optum / UHC": {
        "factor":      0.95,
        "notes_label": "Estimated 95% of Medicare. Replace with actual contract rate.",
    },
}


def api_get(path):
    url = f"{BASE_URL}/{urllib.parse.quote(path, safe='=&?/')}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def api_post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 65)
    print("Payer Fee Schedule Import — Wellmark, Aetna, Ambetter, Cigna, Optum")
    print("=" * 65)
    print()
    print("NOTE: Rates marked 'Estimated' are based on typical commercial")
    print("      market benchmarks. Replace with actual contract rates when")
    print("      obtained from each payer.")
    print()

    # ── Fetch Medicare benchmarks ──────────────────────────────────
    print("Fetching Medicare 2026 benchmark rates...")
    benchmarks = api_get("benchmark?source_name=Medicare 2026&locality=FL&year=2026")
    if not benchmarks:
        print("ERROR: No Medicare 2026 benchmarks found. Run load_medicare_2026.py first.")
        return
    print(f"  {len(benchmarks)} benchmark rates loaded.")
    print()

    # ── Fetch all active contracts ─────────────────────────────────
    print("Fetching contracts...")
    contracts = api_get("contracts?active_only=true")
    print(f"  {len(contracts)} active contracts found.")
    print()

    # ── Import for each payer ──────────────────────────────────────
    grand_total = 0

    for payer_name, config in PAYER_FACTORS.items():
        factor = config["factor"]
        label  = config["notes_label"]

        # Find all contracts for this payer
        payer_contracts = [c for c in contracts if c["payer_name"] == payer_name]
        if not payer_contracts:
            print(f"  SKIP: No contracts found for {payer_name}")
            continue

        print(f"{'─' * 65}")
        print(f"  {payer_name}  ({factor*100:.0f}% of Medicare)")

        # Build fee schedule lines
        lines = []
        for b in benchmarks:
            rate = round(float(b["allowed_amount"]) * factor, 2)
            lines.append({
                "cpt_code":         b["cpt_code"],
                "modifier":         "95",    # telehealth synchronous
                "place_of_service": "10",    # telehealth in patient home
                "unit_type":        "per_service",
                "allowed_amount":   rate,
                "effective_date":   "2026-01-01",
                "end_date":         None,
                "notes":            f"{label} Medicare ref: ${float(b['allowed_amount']):.2f}",
            })

        # Import for each contract under this payer
        for contract in payer_contracts:
            payload = {"contract_id": contract["contract_id"], "lines": lines}
            try:
                result = api_post(IMPORT_URL, payload)
                print(f"    ✓ [{contract['contract_id']}] {contract['provider_name']}: "
                      f"{result['lines_upserted']} lines")
                grand_total += result["lines_upserted"]
            except urllib.error.HTTPError as e:
                print(f"    ✗ [{contract['contract_id']}] Error: {e.read().decode()}")

    print(f"{'─' * 65}")
    print()
    print(f"✓ Import complete: {grand_total} total lines imported across all payers.")
    print()
    print("Payer rate summary vs your 130% Medicare target:")
    print(f"  {'Payer':<20} {'Factor':>8}  {'99214 Rate':>12}  {'vs Target':>12}")
    print(f"  {'-'*20} {'-'*8}  {'-'*12}  {'-'*12}")

    m99214 = next((float(b["allowed_amount"]) for b in benchmarks if b["cpt_code"] == "99214"), None)
    if m99214:
        target = round(m99214 * 1.30, 2)
        print(f"  {'[Target 130%]':<20} {'130%':>8}  ${target:>11.2f}  {'baseline':>12}")
        for payer_name, config in PAYER_FACTORS.items():
            rate = round(m99214 * config["factor"], 2)
            gap  = round(target - rate, 2)
            print(f"  {payer_name:<20} {config['factor']*100:.0f}%{'':<5}  ${rate:>11.2f}  -${gap:>10.2f}")
        # Florida Blue reference
        fl_rate = round(m99214 * 0.80, 2)
        fl_gap  = round(target - fl_rate, 2)
        print(f"  {'Florida Blue':<20} {'80%':>8}  ${fl_rate:>11.2f}  -${fl_gap:>10.2f}")

    print()
    print("Next step: python3 backend/load_claims_volume.py")
    print("  (adds billing volume so revenue gap math lights up)")


if __name__ == "__main__":
    main()
