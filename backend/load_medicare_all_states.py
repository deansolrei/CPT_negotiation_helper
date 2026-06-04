"""
load_medicare_all_states.py
---------------------------
Calculates and loads 2026 Medicare non-facility (telehealth/office) benchmark
rates for all 23 states where Solrei Behavioral Health has licensed providers.

Formula:
    Payment = (Work_RVU × Work_GPCI + PE_RVU × PE_GPCI + MP_RVU × MP_GPCI) × CF

    CF (Conversion Factor) = $33.40  (2026 non-qualifying APM)
    Work GPCI floor        = 1.000   (statutory minimum; Alaska = 1.500)
    Setting                = Non-facility (office/telehealth, POS 02/10/11)

Data sources:
    RVU components : CMS 2026 Physician Fee Schedule Final Rule (CMS-1832-F)
    GPCI values    : CMS 2026 Geographic Practice Cost Indices (PFS Final Rule)
                     https://www.cms.gov/medicare/payment/fee-schedules/physician
    G-code rates   : Approximate 2026 national rates (no state GPCI adjustment;
                     verify annually against CMS Collaborative Care code tables)

Usage:
    cd "/Users/deanpedersen/Projects/solrei/PROJECT - ACTIVE/Insurance CPT Negotiation Dashboard"
    python3 -m backend.load_medicare_all_states

    # Load a single state only:
    python3 -m backend.load_medicare_all_states --state FL

Options:
    --state XX   Load only the specified state abbreviation (e.g. --state AZ)
    --dry-run    Print calculated rates; do not post to API
    --verbose    Show every CPT rate for every state

Notes:
    - Rates for G0568/G0569/G0570 (CoCM) use fixed national rates because
      CMS has not published standard RVU components for these add-on codes.
    - GPCI values are hardcoded from the 2026 PFS Final Rule and should be
      reviewed each January when CMS releases the next year's final rule.
    - Multiple localities exist within some states; this script uses the
      primary/most representative locality for that state.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
API_URL   = "http://localhost:8000/api/import-benchmark"
CF        = 33.40   # 2026 CMS Conversion Factor (non-qualifying APM)
YEAR      = 2026

# ──────────────────────────────────────────────────────────────────────────────
# RVU components for each CPT code
# Source: CMS 2026 PFS Final Rule — Non-facility (office/telehealth) RVUs
# Format: (work_rvu, pe_nonfacility_rvu, mp_rvu, short_description)
# ──────────────────────────────────────────────────────────────────────────────
RVUS = {
    # ── Evaluation & Management ────────────────────────────────────────────
    "99202": (0.93,  1.39,  0.07,  "New pt E/M low complexity"),
    "99203": (1.60,  1.64,  0.10,  "New pt E/M moderate complexity"),
    "99204": (2.60,  2.27,  0.10,  "New pt E/M mod-high complexity"),
    "99205": (3.50,  2.78,  0.15,  "New pt E/M high complexity"),
    "99212": (0.70,  0.97,  0.05,  "Est pt E/M minimal complexity"),
    "99213": (1.30,  1.35,  0.09,  "Est pt E/M low complexity"),
    "99214": (1.92,  1.95,  0.14,  "Est pt E/M moderate complexity"),
    "99215": (2.80,  2.46,  0.18,  "Est pt E/M high complexity"),

    # ── Psychiatric Diagnostic Evaluations ────────────────────────────────
    "90791": (3.25,  2.22,  0.13,  "Psych eval w/o medical services"),
    "90792": (3.86,  2.43,  0.32,  "Psych eval w/ medical services"),

    # ── Individual Psychotherapy (standalone) ─────────────────────────────
    "90832": (1.50,  1.19,  0.09,  "Individual therapy 30 min"),
    "90834": (2.10,  1.56,  0.12,  "Individual therapy 45 min"),
    "90837": (2.83,  1.98,  0.15,  "Individual therapy 60 min"),

    # ── Add-on Psychotherapy with E/M ────────────────────────────────────
    # Add-on codes use facility PE RVUs (lower PE)
    "90833": (0.99,  0.32,  0.05,  "Add-on therapy 30 min with E/M"),
    "90836": (1.52,  0.42,  0.08,  "Add-on therapy 45 min with E/M"),
    "90838": (2.10,  0.55,  0.11,  "Add-on therapy 60 min with E/M"),

    # ── Family Psychotherapy ──────────────────────────────────────────────
    "90846": (2.10,  1.56,  0.12,  "Family therapy w/o patient"),
    "90847": (2.10,  1.56,  0.12,  "Family therapy w/ patient"),

    # ── Group Psychotherapy ───────────────────────────────────────────────
    "90853": (0.75,  0.61,  0.05,  "Group therapy per patient"),

    # ── Crisis Psychotherapy ──────────────────────────────────────────────
    "90839": (4.40,  2.66,  0.21,  "Crisis therapy first 60 min"),
    "90840": (2.20,  0.83,  0.09,  "Crisis therapy add-on 30 min"),

    # ── Screening ─────────────────────────────────────────────────────────
    "96127": (0.18,  0.33,  0.01,  "Brief behavioral assessment per instrument"),

    # ── Psychological Testing ─────────────────────────────────────────────
    "96130": (2.20,  1.49,  0.07,  "Psych testing evaluation first hour"),
    "96136": (1.19,  0.89,  0.06,  "Psych testing by NP first 30 min"),
    "96138": (0.75,  0.64,  0.08,  "Psych testing by tech first 30 min"),

    # ── Behavioral Health Integration ─────────────────────────────────────
    "99484": (1.00,  1.15,  0.06,  "General BHI 20+ min monthly"),

    # ── Prolonged Services ────────────────────────────────────────────────
    "99417": (0.54,  0.38,  0.03,  "Prolonged E/M add-on per 15 min"),
    "99354": (2.33,  1.57,  0.08,  "Prolonged face-to-face first 30-60 min"),
    "99355": (1.77,  1.00,  0.10,  "Prolonged face-to-face each addl 30 min"),

    # ── Health Behavior ───────────────────────────────────────────────────
    "99406": (0.24,  0.18,  0.02,  "Tobacco cessation 3-10 min"),
    "99407": (0.50,  0.29,  0.04,  "Tobacco cessation >10 min"),
    "96156": (1.05,  0.76,  0.09,  "Health behavior assessment"),
    "96158": (1.20,  0.87,  0.10,  "Health behavior intervention individual 30 min"),
    "96159": (0.60,  0.44,  0.06,  "Health behavior intervention addl 15 min"),
    "96164": (0.75,  0.49,  0.06,  "Health behavior group first 30 min"),
    "96165": (0.38,  0.24,  0.03,  "Health behavior group addl 15 min"),
    "96167": (1.20,  0.87,  0.10,  "Health behavior family w/ patient 30 min"),
    "96168": (0.60,  0.44,  0.06,  "Health behavior family addl 15 min"),
}

# ── CoCM G-codes — fixed national rates (no standard published RVUs) ─────────
# These codes do not have standard RVU breakdowns published by CMS.
# Same national rate is applied to all states. Verify annually.
GCODES_FIXED = {
    "G0568": (133.20, "CoCM initial month 60+ min; approximate 2026 national rate"),
    "G0569": (100.20, "CoCM subsequent month 30+ min; approximate 2026 national rate"),
    "G0570": ( 39.14, "CoCM additional 30 min add-on; approximate 2026 national rate"),
}

# ──────────────────────────────────────────────────────────────────────────────
# 2026 GPCI values for all 23 Solrei states
# Source: CMS 2026 Physician Fee Schedule Final Rule (CMS-1832-F)
#         https://www.cms.gov/medicare/payment/fee-schedules/physician
# Format: state_abbr → (locality_name, work_gpci, pe_nonfacility_gpci, mp_gpci)
#
# Notes:
#   • Work GPCI has a statutory floor of 1.000 (except Alaska = 1.500).
#   • PE and MP GPCIs can be above or below 1.000.
#   • States with multiple CMS localities use the primary/largest locality.
#   • Update annually each January when CMS publishes the new PFS Final Rule.
# ──────────────────────────────────────────────────────────────────────────────
GPCI = {
    #       State            Locality description            W_GPCI  PE_GPCI  MP_GPCI
    "AK": ("Alaska",                                         1.500,  1.528,   0.901),
    "AZ": ("Arizona (Phoenix/Maricopa)",                     1.000,  0.912,   0.861),
    "CO": ("Colorado (Denver)",                              1.020,  1.101,   0.815),
    "DC": ("Washington DC",                                  1.111,  1.342,   0.578),
    "FL": ("Florida (Rest of State / Orlando)",              1.000,  0.971,   0.869),
    "HI": ("Hawaii",                                         1.000,  1.188,   0.829),
    "ID": ("Idaho",                                          1.000,  0.864,   0.668),
    "IA": ("Iowa",                                           1.000,  0.848,   0.564),
    "KS": ("Kansas",                                         1.000,  0.858,   0.502),
    "ME": ("Maine",                                          1.000,  0.922,   0.782),
    "MD": ("Maryland (Baltimore)",                           1.030,  1.190,   0.638),
    "MN": ("Minnesota (Minneapolis)",                        1.020,  1.017,   0.634),
    "MT": ("Montana",                                        1.000,  0.861,   0.629),
    "NE": ("Nebraska (Omaha)",                               1.000,  0.869,   0.494),
    "NV": ("Nevada (Las Vegas)",                             1.000,  1.016,   0.831),
    "NH": ("New Hampshire",                                  1.000,  1.009,   0.748),
    "NM": ("New Mexico",                                     1.000,  0.880,   0.666),
    "ND": ("North Dakota",                                   1.000,  0.853,   0.565),
    "OR": ("Oregon (Portland)",                              1.010,  1.077,   0.885),
    "SD": ("South Dakota",                                   1.000,  0.852,   0.583),
    "VT": ("Vermont",                                        1.000,  0.920,   0.765),
    "WA": ("Washington (Seattle)",                           1.042,  1.147,   0.896),
    "WY": ("Wyoming",                                        1.000,  0.862,   0.578),
}


# ──────────────────────────────────────────────────────────────────────────────
# Rate calculation
# ──────────────────────────────────────────────────────────────────────────────

def calc_rate(w_rvu, pe_rvu, mp_rvu, w_gpci, pe_gpci, mp_gpci):
    """Calculate Medicare allowed amount using the standard formula."""
    return round((w_rvu * w_gpci + pe_rvu * pe_gpci + mp_rvu * mp_gpci) * CF, 2)


def build_rates_for_state(state, verbose=False):
    """Return the list of rate dicts for a given state."""
    loc_name, w_gpci, pe_gpci, mp_gpci = GPCI[state]
    rates = []

    for cpt, (w, pe, mp, desc) in RVUS.items():
        allowed = calc_rate(w, pe, mp, w_gpci, pe_gpci, mp_gpci)
        notes = (
            f"{desc}; "
            f"Work {w} + PE {pe} + MP {mp} × ${CF:.2f}; "
            f"GPCI W={w_gpci}/PE={pe_gpci}/MP={mp_gpci}"
        )
        rates.append({"cpt_code": cpt, "allowed_amount": allowed, "notes": notes})
        if verbose:
            print(f"    {cpt}  ${allowed:>7.2f}  {desc[:45]}")

    # G-codes: fixed national rate, no GPCI adjustment
    for cpt, (amount, note) in GCODES_FIXED.items():
        rates.append({"cpt_code": cpt, "allowed_amount": amount,
                      "notes": note + f"; no GPCI adjustment applied"})
        if verbose:
            print(f"    {cpt}  ${amount:>7.2f}  (fixed national rate)")

    return rates


# ──────────────────────────────────────────────────────────────────────────────
# API posting
# ──────────────────────────────────────────────────────────────────────────────

def post_state(state, rates, dry_run=False):
    """POST a state's rates to the benchmark import endpoint."""
    loc_name = GPCI[state][0]
    payload = {
        "source_name": f"Medicare {YEAR}",
        "locality": state,
        "effective_year": YEAR,
        "rates": rates,
    }
    if dry_run:
        print(f"  [DRY RUN] Would POST {len(rates)} rates for {state} ({loc_name})")
        return True

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            imported = result.get("lines_upserted", "?")
            print(f"  ✓ {state}  {imported:>3} rates  ({loc_name})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  ✗ {state}  HTTP {e.code}: {body[:120]}")
        return False
    except urllib.error.URLError as e:
        print(f"  ✗ {state}  Connection error: {e.reason}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load Medicare 2026 benchmark rates for all Solrei states."
    )
    parser.add_argument(
        "--state",
        metavar="XX",
        help="Load only this state (e.g. --state FL). Default: all 23 states.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate rates but do NOT post to API.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every CPT rate for every state.",
    )
    args = parser.parse_args()

    # Determine which states to load
    if args.state:
        state_upper = args.state.upper()
        if state_upper not in GPCI:
            print(f"✗ Unknown state: {args.state}")
            print(f"  Supported states: {', '.join(sorted(GPCI))}")
            sys.exit(1)
        states_to_load = [state_upper]
    else:
        states_to_load = sorted(GPCI)

    total_codes = len(RVUS) + len(GCODES_FIXED)
    mode_label  = " [DRY RUN]" if args.dry_run else ""

    print()
    print(f"Medicare {YEAR} Benchmark Rate Loader{mode_label}")
    print(f"{'─'*55}")
    print(f"  Conversion Factor : ${CF}")
    print(f"  CPT codes         : {total_codes} ({len(RVUS)} GPCI-adjusted + {len(GCODES_FIXED)} fixed G-codes)")
    print(f"  States to load    : {len(states_to_load)}")
    print()

    ok_count   = 0
    fail_count = 0

    for state in states_to_load:
        loc_name = GPCI[state][0]
        if args.verbose:
            print(f"  ── {state}: {loc_name}")
        rates = build_rates_for_state(state, verbose=args.verbose)
        success = post_state(state, rates, dry_run=args.dry_run)
        if success:
            ok_count += 1
        else:
            fail_count += 1

    print()
    print(f"{'─'*55}")
    if args.dry_run:
        print(f"  DRY RUN complete. {ok_count} state(s) would have been loaded.")
    else:
        print(f"  Done. {ok_count} succeeded, {fail_count} failed.")
        if fail_count == 0:
            print(f"  All {ok_count} states loaded into benchmark_fee_schedule.")
            print()
            print("  Next: refresh the dashboard and choose a state from the")
            print("  state selector to see GPCI-adjusted Medicare benchmarks.")
    print()


if __name__ == "__main__":
    main()
