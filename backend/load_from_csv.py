"""
load_from_csv.py
----------------
Reads payer_rates_template_*.csv and imports the rates into PostgreSQL
via the FastAPI import endpoint.

Use this script whenever you update the rates CSV and want those changes
reflected in the dashboard.

Workflow:
  1. Edit payer_rates_template_2026-04-06.csv with actual payer rates
  2. Save the CSV
  3. Run this script:  python3 backend/load_from_csv.py
  4. Refresh the dashboard (↻ button)

The script imports into the NPI1 (individual provider / Jodene Jensen)
contract for each payer, which is the source of truth for the Rate
Comparison table. If no NPI1 contract exists, it falls back to NPI2.

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_from_csv.py
"""

import csv
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

BASE_URL    = "http://localhost:8000/api"
# Resolve CSV path relative to this file (../payer_rates_template_*.csv)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT  = os.path.dirname(_SCRIPT_DIR)

# ── Canonical payer name mapping ─────────────────────────────────────────────
# Maps lowercase keywords found in the CSV → canonical payer name used in the DB.
# Adjust if your DB payer names differ.
PAYER_ALIASES = {
    "aetna":         "Aetna",
    "ambetter":      "Ambetter",
    "bcbs":          "BCBS - Massachusetts",
    "massachusetts": "BCBS - Massachusetts",
    "carelon":       "Carelon",
    "beacon":        "Carelon",
    "cigna":         "Cigna",
    "florida blue":  "Florida Blue",
    "optum":         "Optum / UHC",
    "uhc":           "Optum / UHC",
    "oscar":         "Oscar",
    "quest":         "Quest Health",
    "wellmark":      "Wellmark Iowa",
}


def canonicalize(name: str) -> str:
    """Map a CSV payer name to the DB payer name."""
    low = name.lower().strip()
    # Longest-match wins (so "florida blue" beats "florida")
    for alias in sorted(PAYER_ALIASES, key=len, reverse=True):
        if alias in low:
            return PAYER_ALIASES[alias]
    return name.strip()


def parse_date(raw: str) -> str | None:
    """Accept M/D/YY, M/D/YYYY, or YYYY-MM-DD; return YYYY-MM-DD or None."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    print(f"  ⚠  Could not parse date '{raw}' — leaving null")
    return None


def find_csv() -> str:
    """Find the most-recently-modified payer_rates_template_*.csv in project root."""
    candidates = [
        f for f in os.listdir(_PROJ_ROOT)
        if f.startswith("payer_rates_template") and f.endswith(".csv")
    ]
    if not candidates:
        raise FileNotFoundError(
            "No payer_rates_template_*.csv found in project root.\n"
            "Expected: payer_rates_template_YYYY-MM-DD.csv"
        )
    candidates.sort(reverse=True)          # newest name first (YYYY-MM-DD sorts lexicographically)
    return os.path.join(_PROJ_ROOT, candidates[0])


def api_get(path: str):
    url = f"{BASE_URL}/{urllib.parse.quote(path, safe='=&?/')}"
    with urllib.request.urlopen(urllib.request.Request(url)) as r:
        return json.loads(r.read().decode())


def api_post(path: str, payload: dict):
    url  = f"{BASE_URL}/{path}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def load_contracts() -> dict:
    """
    Returns a dict:  canonical_payer_name → list of contract dicts
    Each contract has keys: contract_id, payer_name, provider_name, entity_type, npi_number
    """
    contracts = api_get("contracts?active_only=true")
    result: dict[str, list] = {}
    for c in contracts:
        canonical = canonicalize(c["payer_name"])
        result.setdefault(canonical, []).append(c)
    return result


def pick_contract(contracts: list) -> dict | None:
    """Prefer NPI1 (individual provider) over NPI2 (group)."""
    npi1 = [c for c in contracts if c.get("entity_type") == "NPI1"]
    if npi1:
        return npi1[0]
    npi2 = [c for c in contracts if c.get("entity_type") == "NPI2"]
    if npi2:
        return npi2[0]
    return contracts[0] if contracts else None


def read_csv(path: str) -> dict[str, list]:
    """
    Reads the rates CSV, skipping comments (#) and blank rows.
    Returns: { canonical_payer_name: [line_dict, ...] }
    """
    payer_lines: dict[str, list] = {}
    skipped = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip comment rows and blank rows
            payer_raw = (row.get("payer_name") or "").strip()
            if not payer_raw or payer_raw.startswith("#"):
                skipped += 1
                continue

            amount_raw = (row.get("allowed_amount") or "").strip()
            if not amount_raw or amount_raw.startswith("#"):
                skipped += 1
                continue

            try:
                amount = float(amount_raw)
            except ValueError:
                print(f"  ⚠  Skipping row — invalid allowed_amount: '{amount_raw}'")
                skipped += 1
                continue

            canonical = canonicalize(payer_raw)
            line = {
                "cpt_code":         (row.get("cpt_code") or "").strip(),
                "modifier":         (row.get("modifier") or "").strip() or None,
                "place_of_service": (row.get("place_of_service") or "").strip() or None,
                "unit_type":        "per_service",
                "allowed_amount":   amount,
                "effective_date":   parse_date(row.get("effective_date") or ""),
                "end_date":         None,
                "notes":            (row.get("notes") or "").strip() or None,
            }
            if not line["cpt_code"]:
                skipped += 1
                continue

            payer_lines.setdefault(canonical, []).append(line)

    if skipped:
        print(f"  (skipped {skipped} comment/blank/invalid rows)")
    return payer_lines


def main():
    print("=" * 65)
    print("Payer Rates CSV → PostgreSQL Import")
    print("=" * 65)

    # ── Find CSV ──────────────────────────────────────────────────
    csv_path = find_csv()
    print(f"\nCSV file: {os.path.basename(csv_path)}")

    # ── Load contracts from API ───────────────────────────────────
    print("Fetching active contracts from API…")
    try:
        contract_map = load_contracts()
    except Exception as e:
        print(f"\nERROR: Cannot reach API — is uvicorn running?\n  {e}")
        sys.exit(1)
    print(f"  {sum(len(v) for v in contract_map.values())} contracts found for "
          f"{len(contract_map)} payers.")

    # ── Read CSV ──────────────────────────────────────────────────
    print(f"\nReading rates from CSV…")
    payer_lines = read_csv(csv_path)
    total_csv_lines = sum(len(v) for v in payer_lines.values())
    print(f"  {total_csv_lines} rate rows across {len(payer_lines)} payers.")

    # ── Import payer by payer ─────────────────────────────────────
    print()
    grand_total = 0
    for canonical, lines in sorted(payer_lines.items()):
        print(f"{'─' * 65}")
        print(f"  {canonical}  ({len(lines)} codes in CSV)")

        contracts = contract_map.get(canonical)
        if not contracts:
            print(f"  ⚠  No active contract found for '{canonical}' — skipping.")
            print(f"     (Check PAYER_ALIASES in this script if the name doesn't match.)")
            continue

        contract = pick_contract(contracts)
        print(f"  → Contract {contract['contract_id']}  "
              f"({contract.get('entity_type','?')} · {contract.get('provider_name','?')})")

        # Filter out lines with no CPT code
        valid_lines = [l for l in lines if l["cpt_code"]]
        if not valid_lines:
            print("  ⚠  No valid lines — skipping.")
            continue

        try:
            result = api_post("import-fee-schedule", {
                "contract_id": contract["contract_id"],
                "lines":       valid_lines,
            })
            print(f"  ✓ {result['lines_upserted']} lines upserted")
            grand_total += result["lines_upserted"]
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ✗ HTTP {e.code}: {body}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print(f"{'─' * 65}")
    print(f"\n✓ Done — {grand_total} total lines upserted into PostgreSQL.")
    print("\nNext: refresh the dashboard (↻ button) to see the updated rates.")


if __name__ == "__main__":
    main()
